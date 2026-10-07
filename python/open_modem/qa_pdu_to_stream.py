#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
import numpy
import pmt
from gnuradio import gr, gr_unittest, blocks
from gnuradio.open_modem import pdu_to_stream


class qa_pdu_to_stream(gr_unittest.TestCase):

    def setUp(self):
        self.tb = gr.top_block()

    def tearDown(self):
        self.tb = None

    def test_instance(self):
        pdu_to_stream()

    def test_drains_a_burst_larger_than_one_work_call(self):
        # Larger than any single scheduler buffer this system allocates
        # (observed clamped to 16384 items) - the point of this block.
        samples = numpy.linspace(-0.5, 0.5, 50000, dtype=numpy.float32)
        src = pdu_to_stream()
        sink = blocks.vector_sink_f()
        self.tb.connect(src, sink)
        self.tb.start()

        pdu = pmt.cons(pmt.make_dict(), pmt.init_f32vector(len(samples), [float(s) for s in samples]))
        src.to_basic_block()._post(pmt.intern('pdus'), pdu)

        import time
        deadline = time.time() + 5
        while len(sink.data()) < len(samples) and time.time() < deadline:
            time.sleep(0.05)
        self.tb.stop()
        self.tb.wait()

        out = numpy.array(sink.data(), dtype=numpy.float32)
        self.assertGreaterEqual(len(out), len(samples))
        # Idle output is silence (zeros), including before the PDU is even
        # delivered - find where the real burst starts rather than assuming
        # index 0.
        start = next(i for i in range(len(out) - len(samples) + 1)
                     if abs(out[i] - samples[0]) < 1e-5)
        numpy.testing.assert_allclose(out[start:start + len(samples)], samples, atol=1e-6)

    def test_complex_dtype_drains_a_burst_larger_than_one_work_call(self):
        # The symbol-rate (not audio-sample-rate) use case open_modem_rx's
        # symbols_out needs - confirmed live to also exceed this system's
        # buffer ceiling once enough bursts queue up through the stock
        # pdu_to_tagged_stream block, which (unlike this one) never
        # recovers once that happens. 20000 is already past the 16384
        # ceiling on its own, which is the point.
        symbols = numpy.exp(1j * numpy.linspace(0, 8 * numpy.pi, 20000)).astype(numpy.complex64)
        src = pdu_to_stream(dtype='complex')
        sink = blocks.vector_sink_c()
        self.tb.connect(src, sink)
        self.tb.start()

        pdu = pmt.cons(pmt.make_dict(), pmt.init_c32vector(len(symbols), [complex(s) for s in symbols]))
        src.to_basic_block()._post(pmt.intern('pdus'), pdu)

        import time
        deadline = time.time() + 5
        while len(sink.data()) < len(symbols) and time.time() < deadline:
            time.sleep(0.05)
        self.tb.stop()
        self.tb.wait()

        out = numpy.array(sink.data(), dtype=numpy.complex64)
        self.assertGreaterEqual(len(out), len(symbols))
        start = next(i for i in range(len(out) - len(symbols) + 1)
                     if abs(out[i] - symbols[0]) < 1e-5)
        numpy.testing.assert_allclose(out[start:start + len(symbols)], symbols, atol=1e-6)


if __name__ == '__main__':
    gr_unittest.run(qa_pdu_to_stream)
