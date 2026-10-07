#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""open_modem RX: a continuous float audio stream in, decoded frame PDUs out.

Stream input (float, 48 kHz - open_wave's PHY assumes this throughout, see
openwave_audio.AUDIO_SAMPLE_RATE), no stream output; a 'pdu_out' message
port carries each decoded frame. No stream output because a burst
detector's natural unit of work is "found a complete burst", not a
fixed-rate sample-for-sample transform.

Ports open_wave's own `radio_listen.py`'s `Listener` class (proven on real
AIOC/Digirig hardware - see RADIO_SETUP.md) onto GNU Radio's scheduler:
same rolling-buffer/try-every-candidate-mode/trim-past-the-burst state
machine, driven from work() instead of a time.sleep() loop, using
_phy.decode_burst/_phy.burst_length_samples for the actual PHY (framing,
FEC, demod - see that module's docstring for why it doesn't just import
open_wave's own audio_wav_test.py).

Message ports
  pdu_out (out): one PDU per delivered message. meta always has status,
      mode, snr_db, quality; for status 'ok' also src_id, dst_id, seq.
      data is the payload (u8vector) for 'ok' - the fully reassembled
      message for a fragmented run, delivered only once its last fragment
      arrives (openwave_link.FragmentReassembler) - else an empty PDU, a
      burst was heard but not decoded (see _phy.decode_burst's status
      values).
  ack_needed (out): a PMT long (the Sequence Number) when a decoded Data
      frame has its ACK-Requested flag set (openwave_link.needs_ack) -
      wire this to an ack_responder block to actually send the ACK back.
  ack_received (out): a PMT long (the acknowledged Sequence Number) when
      a decoded frame is itself an ACK response (openwave_link.is_ack) -
      wire this to this station's own open_modem_tx's 'ack_received'
      input to resolve its RetryManager.
  symbols_out (out): a PDU (empty dict, c32vector) of the demodulated
      complex symbols for every burst dispatched - 'ok' or merely heard -
      for a constellation display. Wire through a stock
      `PDU to Tagged Stream` (type complex) to a QT GUI Constellation
      Sink's stream input; symbol counts per burst are small enough
      (hundreds to low thousands, not the audio-sample-rate counts
      pdu_to_stream exists to work around - see that module's docstring)
      that the stock block's own buffering is fine here.

An ACK frame is never itself delivered on pdu_out, and a fragmented run's
intermediate fragments produce no pdu_out message at all (status
'waiting') - only once FragmentReassembler reports 'complete'. A fragment
that FragmentReassembler reports 'discarded'/'overflow' (lost fragment,
wrong source mid-run, etc.) is silently dropped - no partial-message
delivery, matching the archived legacy/gnuradio/phy_sim_loopback.grc's
stream_display_sink_0's own dispatch via openwave_link.LinkReceiver.
"""
import numpy
import pmt
from gnuradio import gr

from . import _phy
import openwave_link as link

SAMPLE_RATE = 48000
STEP_S = 1.0        # how often the buffer is searched for a burst
KEEP_S = 3.0         # audio kept while nothing has been heard
SETTLE_S = 0.2       # extra margin trimmed past a decoded burst's end


class open_modem_rx(gr.sync_block):
    """Continuous 48 kHz audio stream in -> decoded frame PDUs out."""

    def __init__(self, mode_ids=None, fec_preset='', port='mic', sample_rate=48000,
                 threshold=0.4, max_burst_s=6.0):
        gr.sync_block.__init__(self, name="open_modem_rx",
                                in_sig=[numpy.float32], out_sig=[])
        self.port = port
        self.modes = list(mode_ids) if mode_ids else _phy.modes_fitting_port(port)
        self.fec_preset = fec_preset or None
        self.threshold = threshold
        self.max_burst = int(max_burst_s * SAMPLE_RATE)

        self._buf = numpy.zeros(0, dtype=numpy.float32)
        self._base = 0          # absolute sample index of self._buf[0]
        self._since_step = 0
        self.reassembler = link.FragmentReassembler()

        self.message_port_register_out(pmt.intern('pdu_out'))
        self.message_port_register_out(pmt.intern('ack_needed'))
        self.message_port_register_out(pmt.intern('ack_received'))
        self.message_port_register_out(pmt.intern('symbols_out'))
        if sample_rate != SAMPLE_RATE:
            self.logger.warn(
                f"open_modem_rx: sample_rate {sample_rate} given, but open_wave's PHY "
                f"assumes {SAMPLE_RATE} Hz throughout - connect an Audio Source at "
                f"{SAMPLE_RATE} Hz, not {sample_rate}")

    def work(self, input_items, output_items):
        x = input_items[0]
        self._buf = numpy.concatenate([self._buf, x])
        self._since_step += len(x)
        if self._since_step >= int(STEP_S * SAMPLE_RATE):
            self._since_step = 0
            self._step()
        return len(x)

    def _end(self):
        return self._base + len(self._buf)

    def _trim_to(self, absolute):
        cut = min(max(0, absolute - self._base), len(self._buf))
        self._buf = self._buf[cut:]
        self._base += cut

    def _step(self):
        """Decode every complete burst currently in the buffer."""
        while len(self._buf) > SAMPLE_RATE:
            tries = []
            for m in self.modes:
                r = _phy.decode_burst(self._buf, m, self.fec_preset, self.port)
                r['mode'] = m
                tries.append(r)
            ok = [r for r in tries if r['status'] == 'ok']
            heard = [r for r in tries if r['quality'] >= self.threshold and r['timing'] is not None]
            if ok:
                r = max(ok, key=lambda r: r['quality'])
                length = _phy.burst_length_samples(r['mode'], self.fec_preset, self.port,
                                                    r['header']['payload_len'])
                self._emit_symbols(r)
                self._dispatch(r)
                self._trim_to(self._base + r['timing'] + length + int(SETTLE_S * SAMPLE_RATE))
            elif heard:
                r = max(heard, key=lambda r: r['quality'])
                if self._end() - (self._base + r['timing']) < self.max_burst:
                    return  # the burst may still be arriving: wait for more audio
                self._emit_symbols(r)
                self._emit_heard(r)
                self._trim_to(self._base + r['timing'] + int(0.5 * SAMPLE_RATE))
            else:
                self._trim_to(self._end() - int(KEEP_S * SAMPLE_RATE))
                return

    def _emit_symbols(self, r):
        symbols = r.get('symbols')
        if symbols is None or len(symbols) == 0:
            return
        if r['status'] == 'ok':
            # demodulate() keeps decision-directed tracking past the real
            # frame to the end of whatever buffer it was given - truncate
            # to just the marker+header+payload+CRC symbols so the plot
            # isn't diluted by a long tail of post-frame noise/silence.
            n = _phy.burst_length_symbols(r['mode'], self.fec_preset, self.port,
                                           r['header']['payload_len'])
            symbols = symbols[:n]
        data = pmt.init_c32vector(len(symbols), [complex(s) for s in symbols])
        self.message_port_pub(pmt.intern('symbols_out'), pmt.cons(pmt.make_dict(), data))

    def _dispatch(self, r):
        """A CRC-verified 'ok' frame: ACK response, fragment, or plain data."""
        header = r['header']
        if link.is_ack(header):
            self.message_port_pub(pmt.intern('ack_received'), pmt.from_long(header['seq']))
            return
        if link.parse_flags(header['flags'])['fragmented']:
            frag_status, reassembled = self.reassembler.feed(header, r['payload'])
            if frag_status != 'complete':
                return  # still waiting on more fragments, or this run was abandoned
            payload = reassembled
        else:
            payload = r['payload']
        self._emit_data(r, header, payload)
        if link.needs_ack(header):
            self.message_port_pub(pmt.intern('ack_needed'), pmt.from_long(header['seq']))

    def _emit_data(self, r, header, payload):
        meta = pmt.make_dict()
        meta = pmt.dict_add(meta, pmt.intern('status'), pmt.intern('ok'))
        meta = pmt.dict_add(meta, pmt.intern('mode'), pmt.from_long(r['mode']))
        meta = pmt.dict_add(meta, pmt.intern('snr_db'), pmt.from_double(r['snr_db']))
        meta = pmt.dict_add(meta, pmt.intern('quality'), pmt.from_double(r['quality']))
        meta = pmt.dict_add(meta, pmt.intern('src_id'),
                             pmt.intern(header['src_id'].decode(errors='replace')))
        meta = pmt.dict_add(meta, pmt.intern('dst_id'),
                             pmt.intern(header['dst_id'].decode(errors='replace')))
        meta = pmt.dict_add(meta, pmt.intern('seq'), pmt.from_long(header['seq']))
        data = pmt.init_u8vector(len(payload), list(payload))
        self.message_port_pub(pmt.intern('pdu_out'), pmt.cons(meta, data))

    def _emit_heard(self, r):
        """A burst was heard (sync quality cleared the threshold) but not
        decoded - status is one of decode_frames()'s failure statuses, or
        'no_frame'/'no_burst'; see _phy.decode_burst's docstring."""
        meta = pmt.make_dict()
        meta = pmt.dict_add(meta, pmt.intern('status'), pmt.intern(r['status']))
        meta = pmt.dict_add(meta, pmt.intern('mode'), pmt.from_long(r['mode']))
        meta = pmt.dict_add(meta, pmt.intern('snr_db'), pmt.from_double(r['snr_db']))
        meta = pmt.dict_add(meta, pmt.intern('quality'), pmt.from_double(r['quality']))
        self.message_port_pub(pmt.intern('pdu_out'), pmt.cons(meta, pmt.PMT_NIL))
