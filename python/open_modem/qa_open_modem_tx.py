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
from gnuradio.open_modem import open_modem_tx
from gnuradio.open_modem import _phy
import openwave_link as link


class qa_open_modem_tx(gr_unittest.TestCase):

    def setUp(self):
        self.tb = gr.top_block()

    def tearDown(self):
        self.tb = None

    def test_instance(self):
        tx = open_modem_tx()
        tx.stop()

    def test_pdu_in_emits_audio_and_ptt_key_unkey(self):
        tx = open_modem_tx(station_id='K0MDT', dst_id='ALL', mode_id=1, port='mic')
        events = []
        tx.message_port_pub = lambda port, msg: events.append((pmt.symbol_to_string(port), msg))

        tx._handle_pdu_in(pmt.intern("hello"))

        ports = [p for p, _ in events]
        self.assertEqual(ports[0], 'audio_out')
        audio_msg = events[0][1]
        samples = numpy.array(pmt.f32vector_elements(pmt.cdr(audio_msg)), dtype=numpy.float32)

        time.sleep(len(samples) / _phy.audio.AUDIO_SAMPLE_RATE + 0.2)  # let the 'unkey' Timer fire
        ptt_syms = [pmt.symbol_to_string(m) for p, m in events if p == 'ptt']
        self.assertEqual(ptt_syms, ['key', 'unkey'])
        self.assertGreater(len(samples), 0)
        # round-trip through the real PHY: what open_modem_rx would see
        r = _phy.decode_burst(samples, 1, None, 'mic')
        self.assertEqual(r['status'], 'ok')
        self.assertEqual(r['payload'], b'hello')
        self.assertEqual(r['header']['src_id'], b'K0MDT')
        tx.stop()

    def test_long_payload_fragments_into_several_bursts(self):
        tx = open_modem_tx(station_id='K0MDT', mode_id=1, port='mic')
        audio_events = []
        tx.message_port_pub = lambda port, msg: (
            audio_events.append(msg) if pmt.symbol_to_string(port) == 'audio_out' else None)

        payload = (b'x' * (link.MAX_PAYLOAD_LEN + 50))
        tx._handle_pdu_in(pmt.cons(pmt.make_dict(),
                                    pmt.init_u8vector(len(payload), list(payload))))

        self.assertEqual(len(audio_events), 2)  # 1024 + 50 bytes -> 2 fragments
        reassembler = link.FragmentReassembler()
        reassembled = None
        for msg in audio_events:
            samples = numpy.array(pmt.f32vector_elements(pmt.cdr(msg)), dtype=numpy.float32)
            r = _phy.decode_burst(samples, 1, None, 'mic')
            self.assertEqual(r['status'], 'ok')
            self.assertTrue(link.parse_flags(r['header']['flags'])['fragmented'])
            status, result = reassembler.feed(r['header'], r['payload'])
            if status == 'complete':
                reassembled = result
        self.assertEqual(reassembled, payload)
        tx.stop()

    def test_ack_requested_retries_then_resolves_on_ack_received(self):
        tx = open_modem_tx(station_id='K0MDT', mode_id=1, port='mic',
                            ack_requested=True, ack_max_retries=3, ack_timeout_s=0.2)
        events = []
        tx.message_port_pub = lambda port, msg: events.append((pmt.symbol_to_string(port), msg))

        tx._handle_pdu_in(pmt.intern("ack me"))
        first_seq = tx.retry_mgr.pending_seq
        self.assertIsNotNone(first_seq)

        time.sleep(0.9)  # >= one retry-poll tick (0.5s) past the 0.2s timeout
        audio_count_before_ack = len([p for p, _ in events if p == 'audio_out'])
        self.assertGreaterEqual(audio_count_before_ack, 2)  # original send + >=1 retry

        tx._handle_ack_received(pmt.from_long(first_seq))
        self.assertIsNone(tx.retry_mgr.pending_seq)

        audio_count_at_ack = len([p for p, _ in events if p == 'audio_out'])
        time.sleep(0.9)
        self.assertEqual(len([p for p, _ in events if p == 'audio_out']), audio_count_at_ack)
        self.assertEqual([m for p, m in events if p == 'delivery_failed'], [])
        tx.stop()

    def test_ack_requested_gives_up_and_reports_delivery_failed(self):
        tx = open_modem_tx(station_id='K0MDT', mode_id=1, port='mic',
                            ack_requested=True, ack_max_retries=1, ack_timeout_s=0.2)
        events = []
        tx.message_port_pub = lambda port, msg: events.append((pmt.symbol_to_string(port), msg))

        tx._handle_pdu_in(pmt.intern("never acked"))
        time.sleep(1.5)  # 1 retry allowed, each gated by the 0.5s poll tick + 0.2s timeout

        self.assertEqual(len([p for p, _ in events if p == 'delivery_failed']), 1)
        self.assertIsNone(tx.retry_mgr.pending_seq)
        tx.stop()


if __name__ == '__main__':
    gr_unittest.run(qa_open_modem_tx)
