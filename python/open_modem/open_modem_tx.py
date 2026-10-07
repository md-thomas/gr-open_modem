#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""open_modem TX: a message in, real open_wave audio burst(s) (+ PTT timing)
out - with fragmentation and optional ACK/retry for single-frame messages.

Message-only block, no stream ports - a stock `PDU to Tagged Stream` block
downstream turns the 'audio_out' PDU into a float stream for an Audio Sink.

Message ports
  pdu_in (in): a PDU (meta dict, u8vector payload) or a plain PMT string -
      the text/bytes to send. Longer than link.MAX_PAYLOAD_LEN auto-
      fragments into several bursts (_phy.build_fragmented_bursts, in turn
      openwave_link.build_fragmented_frames) - each its own independent,
      separately keyed burst, same as open_wave's own
      legacy/gnuradio/phy_sim_loopback.grc's str_to_pdu_0 did.
  ack_received (in): a PMT long - the Sequence Number of an ACK heard for
      one of this block's own frames (wire open_modem_rx's 'ack_received'
      output here). Resolves a pending ack_requested send; a stale/
      mismatched seq is ignored.
  audio_out (out): a PDU (dict(sample_rate=...), f32vector burst samples)
      per burst - lead-in/tail silence baked in, as before.
  ptt (out): 'key'/'unkey' per burst, as before.
  delivery_failed (out): a PMT long (the seq that was being retried) when
      ack_requested and ack_max_retries is exceeded with no ACK heard.

ack_requested only applies to a message that fits in a single frame - a
fragmented send has no single seq to retry against (RetryManager tracks
one pending frame at a time), matching phy_sim_loopback.grc's str_to_pdu_0
class docstring for the same reason. Retries are driven by a background
thread polling openwave_link.RetryManager.poll() every 0.5s - not an
externally-wired periodic message port, unlike the legacy embedded
block's 'tick' input, since GNU Radio Python blocks can just use
threading directly.
"""
import threading

import pmt
from gnuradio import gr

from . import _phy
import openwave_link as link

SAMPLE_RATE = 48000
RETRY_POLL_S = 0.5


class open_modem_tx(gr.basic_block):
    """Text/bytes in -> real open_wave audio burst(s) + PTT timing out."""

    def __init__(self, station_id='NOCALL', dst_id='ALL', mode_id=0,
                 fec_preset='', port='mic', lead_in_s=0.25, tail_s=0.02, tx_level=0.7,
                 ack_requested=False, ack_max_retries=3, ack_timeout_s=2.0):
        gr.basic_block.__init__(self, name="open_modem_tx", in_sig=[], out_sig=[])
        self.station_id = station_id
        self.dst_id = dst_id
        self.mode_id = mode_id
        self.fec_preset = fec_preset or None
        self.port = port
        self.lead_in_s = lead_in_s
        self.tail_s = tail_s
        self.tx_level = tx_level
        self.ack_requested = ack_requested

        self.seq = 0
        self.retry_mgr = link.RetryManager(max_retries=ack_max_retries, timeout_s=ack_timeout_s)
        self._pending_payload = None
        self._stop_event = threading.Event()
        self._retry_thread = threading.Thread(target=self._retry_poll_loop, daemon=True)

        self.message_port_register_in(pmt.intern('pdu_in'))
        self.message_port_register_in(pmt.intern('ack_received'))
        self.set_msg_handler(pmt.intern('pdu_in'), self._handle_pdu_in)
        self.set_msg_handler(pmt.intern('ack_received'), self._handle_ack_received)
        self.message_port_register_out(pmt.intern('audio_out'))
        self.message_port_register_out(pmt.intern('ptt'))
        self.message_port_register_out(pmt.intern('delivery_failed'))
        self._retry_thread.start()

    def _publish_audio(self, msg):
        self.message_port_pub(pmt.intern('audio_out'), msg)

    def _publish_ptt(self, msg):
        self.message_port_pub(pmt.intern('ptt'), msg)

    def _payload_from_msg(self, msg):
        if pmt.is_symbol(msg):
            return pmt.symbol_to_string(msg).encode()
        if pmt.is_pair(msg):
            data = pmt.cdr(msg)
            if pmt.is_u8vector(data):
                return bytes(pmt.u8vector_elements(data))
        self.logger.warn(f"pdu_in: unrecognized message type, ignoring: {msg}")
        return None

    def _handle_pdu_in(self, msg):
        payload = self._payload_from_msg(msg)
        if payload is None:
            return
        flags = link.FLAG_ACK_REQUESTED if self.ack_requested else 0
        try:
            bursts, next_seq = _phy.build_fragmented_bursts(
                payload, self.seq, self.mode_id, self.station_id, self.dst_id, flags=flags,
                fec_preset=self.fec_preset, port=self.port, level=self.tx_level,
                lead_in_s=self.lead_in_s, tail_s=self.tail_s)
        except ValueError as exc:
            self.logger.error(f"pdu_in: not sent: {exc}")
            return
        fragmented = len(bursts) > 1
        first_seq = self.seq
        self.seq = next_seq

        for samples in bursts:
            _phy.publish_keyed_burst(samples, self._publish_audio, self._publish_ptt, SAMPLE_RATE)

        if self.ack_requested and not fragmented:
            self._pending_payload = payload
            self.retry_mgr.note_sent(first_seq)

    def _handle_ack_received(self, msg):
        self.retry_mgr.note_ack(pmt.to_long(msg))

    def _retry_poll_loop(self):
        while not self._stop_event.wait(RETRY_POLL_S):
            status = self.retry_mgr.poll()
            if status == 'retry':
                seq = self.retry_mgr.pending_seq
                try:
                    samples = _phy.build_burst(
                        self._pending_payload, self.mode_id, self.station_id, self.dst_id,
                        fec_preset=self.fec_preset, port=self.port, level=self.tx_level,
                        lead_in_s=self.lead_in_s, tail_s=self.tail_s,
                        seq=seq, flags=link.FLAG_ACK_REQUESTED)
                except ValueError as exc:
                    self.logger.error(f"retry: not resent: {exc}")
                    continue
                _phy.publish_keyed_burst(samples, self._publish_audio, self._publish_ptt, SAMPLE_RATE)
                self.retry_mgr.note_sent(seq)
            elif status == 'give_up':
                self.message_port_pub(pmt.intern('delivery_failed'), pmt.from_long(self.seq))
                self._pending_payload = None

    def stop(self):
        self._stop_event.set()
        self._retry_thread.join(timeout=RETRY_POLL_S * 2)
        return True
