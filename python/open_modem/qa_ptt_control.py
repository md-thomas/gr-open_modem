#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
import pmt
from gnuradio import gr, gr_unittest
from gnuradio.open_modem import ptt_control


class qa_ptt_control(gr_unittest.TestCase):

    def setUp(self):
        self.tb = gr.top_block()

    def tearDown(self):
        self.tb = None

    def test_instance(self):
        ptt_control()

    def test_missing_serial_port_logs_instead_of_raising(self):
        # No real PTT hardware in this test environment - a nonexistent
        # port must be handled (logged), not raise out of the msg handler.
        ptt = ptt_control(ptt_port='/dev/nonexistent-ptt-port', ptt_line='dtr')
        ptt._handle_ptt(pmt.intern('key'))  # must not raise
        self.assertIsNone(ptt._serial)

    def test_ignores_non_symbol_message(self):
        ptt = ptt_control()
        ptt._handle_ptt(pmt.from_long(42))  # must not raise


if __name__ == '__main__':
    gr_unittest.run(qa_ptt_control)
