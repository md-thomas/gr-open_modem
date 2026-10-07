#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""A decoded-frame PDU (what open_modem_rx's pdu_out carries) in, one
human-readable line of text out - for a QT GUI Message Edit Box used as a
read-only display, the way the archived legacy/gnuradio/phy_sim_loopback.grc's
"Received"/"Link Stats" boxes worked (fed via their 'val' message port,
never typed into). That port wants a plain string/symbol; pdu_out's PDU
(a meta dict plus a u8vector payload, or PMT_NIL for a heard-but-undecoded
burst) isn't one, hence this adapter.
"""
import pmt
from gnuradio import gr


class pdu_to_text(gr.basic_block):
    """Decoded-frame PDU in -> one text line out."""

    def __init__(self):
        gr.basic_block.__init__(self, name="pdu_to_text", in_sig=[], out_sig=[])
        self.message_port_register_in(pmt.intern('pdu_in'))
        self.message_port_register_out(pmt.intern('text'))
        self.set_msg_handler(pmt.intern('pdu_in'), self._handle)

    def _handle(self, msg):
        meta = pmt.car(msg) if pmt.is_pair(msg) else pmt.make_dict()
        data = pmt.cdr(msg) if pmt.is_pair(msg) else msg
        d = pmt.to_python(meta) or {}
        snr = d.get('snr_db', float('-inf'))
        if d.get('status') == 'ok' and pmt.is_u8vector(data):
            payload = bytes(pmt.u8vector_elements(data)).decode(errors='replace')
            text = f"[{d.get('src_id', '?')}] {payload}  (SNR {snr:.1f} dB)"
        else:
            text = f"(heard, not decoded: {d.get('status', '?')}, SNR {snr:.1f} dB)"
        self.message_port_pub(pmt.intern('text'), pmt.string_to_symbol(text))
