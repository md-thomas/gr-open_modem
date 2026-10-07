#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
import time

import numpy
import pmt
from gnuradio import gr, gr_unittest
from gnuradio.open_modem import ack_responder
from gnuradio.open_modem import _phy


class qa_ack_responder(gr_unittest.TestCase):

    def setUp(self):
        self.tb = gr.top_block()

    def tearDown(self):
        self.tb = None

    def test_instance(self):
        ack_responder()

    def test_ack_needed_emits_a_real_ack_burst_and_keys_ptt(self):
        resp = ack_responder(station_id='K0MDT', mode_id=1, port='mic')
        events = []
        resp.message_port_pub = lambda port, msg: events.append((pmt.symbol_to_string(port), msg))

        resp._handle_ack_needed(pmt.from_long(42))

        ports = [p for p, _ in events]
        self.assertEqual(ports[0], 'audio_out')
        samples = numpy.array(pmt.f32vector_elements(pmt.cdr(events[0][1])), dtype=numpy.float32)
        self.assertGreater(len(samples), 0)

        time.sleep(len(samples) / _phy.audio.AUDIO_SAMPLE_RATE + 0.2)
        ptt_syms = [pmt.symbol_to_string(m) for p, m in events if p == 'ptt']
        self.assertEqual(ptt_syms, ['key', 'unkey'])

        # the burst really is an ACK for seq 42, decodable with the plain demodulator
        import openwave_link as link
        r = _phy.decode_burst(samples, 1, None, 'mic')
        self.assertEqual(r['status'], 'ok')
        self.assertTrue(link.is_ack(r['header']))
        self.assertEqual(r['header']['seq'], 42)


if __name__ == '__main__':
    gr_unittest.run(qa_ack_responder)
