#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""Turns a 'this frame wants acknowledging' notification into a real ACK
burst - the piece that closes the ACK loop: open_modem_rx can recognize
that a received frame requested an ACK (its 'ack_needed' output), but
can't itself key PTT and send one back (it's a stream-input sink with no
notion of this station's own TX chain/mode/level) - this block can.

A separate block, rather than folding this into open_modem_rx directly,
because sending an ACK needs the SAME audio_out/ptt wiring (mode, level,
lead-in/tail, PTT keying) open_modem_tx already has, and duplicating that
inside the receive path would mean two places to keep in sync. Message
ports deliberately mirror open_modem_tx's own audio_out/ptt shape, so both
fan into the same downstream pdu_to_stream and ptt_control in a flowgraph
(message ports accept more than one upstream connection) - see
examples/open_modem_loopback.grc and REQUIREMENTS.md for the half-duplex
caveat this doesn't try to solve (a real radio can't key for an ACK and
simultaneously be mid-receive; nothing here arbitrates that, matching the
archived legacy/gnuradio/phy_sim_loopback.grc's own ack_responder_0
embedded block, which had the same gap).

Message ports
  ack_needed (in): a PMT long (the Sequence Number) - wire open_modem_rx's
      same-named output here.
  audio_out (out), ptt (out): identical in shape to open_modem_tx's own.
"""
import pmt
from gnuradio import gr

from . import _phy

SAMPLE_RATE = 48000


class ack_responder(gr.basic_block):
    """'ack_needed' (seq) in -> an ACK burst + PTT timing out."""

    def __init__(self, station_id='NOCALL', dst_id='ALL', mode_id=0,
                 fec_preset='', port='mic', tx_level=0.7):
        gr.basic_block.__init__(self, name="ack_responder", in_sig=[], out_sig=[])
        self.station_id = station_id
        self.dst_id = dst_id
        self.mode_id = mode_id
        self.fec_preset = fec_preset or None
        self.port = port
        self.tx_level = tx_level

        self.message_port_register_in(pmt.intern('ack_needed'))
        self.set_msg_handler(pmt.intern('ack_needed'), self._handle_ack_needed)
        self.message_port_register_out(pmt.intern('audio_out'))
        self.message_port_register_out(pmt.intern('ptt'))

    def _publish_audio(self, msg):
        self.message_port_pub(pmt.intern('audio_out'), msg)

    def _publish_ptt(self, msg):
        self.message_port_pub(pmt.intern('ptt'), msg)

    def _handle_ack_needed(self, msg):
        acked_seq = pmt.to_long(msg)
        try:
            samples = _phy.build_ack_burst(acked_seq, self.mode_id, self.station_id, self.dst_id,
                                            fec_preset=self.fec_preset, port=self.port,
                                            level=self.tx_level)
        except ValueError as exc:
            self.logger.error(f"ack_needed: not sent: {exc}")
            return
        _phy.publish_keyed_burst(samples, self._publish_audio, self._publish_ptt, SAMPLE_RATE)
