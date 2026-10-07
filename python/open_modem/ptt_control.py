#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""Key/unkey a radio's PTT over a serial line (AIOC: DTR, Digirig: RTS).

Message-only block, no stream ports. Port it from open_wave's own
ptt_play.py (serial.Serial(port, 9600, dsrdtr=False, rtscts=False); clear
both dtr/rts, then setattr(ptt, line, True/False)) - same serial handling,
just message-driven instead of one blocking call around `aplay`.

Message port 'ptt' in: a PMT symbol 'key' or 'unkey' (anything else is
logged and ignored). Phase 2/3 wires open_modem_tx's own 'ptt' output port
to this, timed against the modulated burst's duration so key precedes the
audio by the mode's lead-in and unkey follows its tail - see
RADIO_SETUP.md's lead-in-covers-squelch-open-time note and
gr-open_modem/REQUIREMENTS.md for why that timing is the risky part.
"""
import pmt
from gnuradio import gr


class ptt_control(gr.basic_block):
    """PTT control for an AIOC/Digirig-style serial PTT line."""

    def __init__(self, ptt_port='/dev/ttyACM0', ptt_line='dtr'):
        gr.basic_block.__init__(self, name="ptt_control", in_sig=[], out_sig=[])
        self.ptt_port = ptt_port
        self.ptt_line = ptt_line
        self._serial = None
        self.message_port_register_in(pmt.intern('ptt'))
        self.set_msg_handler(pmt.intern('ptt'), self._handle_ptt)

    def _ensure_open(self):
        if self._serial is None:
            import serial
            self._serial = serial.Serial(self.ptt_port, 9600, dsrdtr=False, rtscts=False)
            self._serial.dtr = False
            self._serial.rts = False
        return self._serial

    def _handle_ptt(self, msg):
        if not pmt.is_symbol(msg):
            self.logger.warn("ptt: ignoring non-symbol message")
            return
        cmd = pmt.symbol_to_string(msg)
        try:
            ptt = self._ensure_open()
        except Exception as exc:
            self.logger.error(f"ptt: could not open {self.ptt_port}: {exc}")
            return
        if cmd == 'key':
            setattr(ptt, self.ptt_line, True)
        elif cmd == 'unkey':
            setattr(ptt, self.ptt_line, False)
        else:
            self.logger.warn(f"ptt: ignoring unknown command {cmd!r}")

    def stop(self):
        if self._serial is not None:
            self._serial.dtr = False
            self._serial.rts = False
            self._serial.close()
            self._serial = None
        return True
