#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
import pmt
from gnuradio import gr, gr_unittest
from gnuradio.open_modem import pdu_to_text


class qa_pdu_to_text(gr_unittest.TestCase):

    def setUp(self):
        self.tb = gr.top_block()

    def tearDown(self):
        self.tb = None

    def test_instance(self):
        pdu_to_text()

    def test_ok_frame_formats_src_id_and_payload(self):
        b = pdu_to_text()
        seen = []
        b.message_port_pub = lambda port, msg: seen.append(msg)

        meta = pmt.make_dict()
        meta = pmt.dict_add(meta, pmt.intern('status'), pmt.intern('ok'))
        meta = pmt.dict_add(meta, pmt.intern('src_id'), pmt.intern('K0MDT'))
        meta = pmt.dict_add(meta, pmt.intern('snr_db'), pmt.from_double(12.3))
        payload = b'hello there'
        data = pmt.init_u8vector(len(payload), list(payload))
        b._handle(pmt.cons(meta, data))

        self.assertEqual(len(seen), 1)
        text = pmt.symbol_to_string(seen[0])
        self.assertIn('K0MDT', text)
        self.assertIn('hello there', text)
        self.assertIn('12.3', text)

    def test_heard_but_undecoded_formats_status(self):
        b = pdu_to_text()
        seen = []
        b.message_port_pub = lambda port, msg: seen.append(msg)

        meta = pmt.make_dict()
        meta = pmt.dict_add(meta, pmt.intern('status'), pmt.intern('crc_fail'))
        meta = pmt.dict_add(meta, pmt.intern('snr_db'), pmt.from_double(1.5))
        b._handle(pmt.cons(meta, pmt.PMT_NIL))

        text = pmt.symbol_to_string(seen[0])
        self.assertIn('crc_fail', text)
        self.assertIn('1.5', text)


if __name__ == '__main__':
    gr_unittest.run(qa_pdu_to_text)
