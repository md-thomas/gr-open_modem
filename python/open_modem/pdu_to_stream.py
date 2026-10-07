#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""A float- or complex-PDU message port in, a matching stream out - drained
incrementally.

Exists because the stock `pdu.pdu_to_tagged_stream` writes an entire PDU as
one tagged packet in a single work() call, which needs an output buffer
sized to the longest burst that will ever arrive - and on this machine GNU
Radio's buffer allocator silently clamps any requested `maxoutbuf` down to
16384 items regardless of what's asked for ("Block (...) max output buffer
set to 16384 instead of requested ..."). For open_modem_tx's audio_out
bursts that's an easy, well under even a single-byte-payload mode 0 burst
(~47000 samples). It turns out the same ceiling also bites
open_modem_rx's symbols_out - low thousands of symbols per burst looked
safely under 16384 in isolation, but once several bursts' worth queue up
across the run it's exceeded there too, confirmed live: a `vector_sink_c`
tapping the stock block's output stopped growing the instant its thread
hit that same "Buffer too small" error, and - this is the part that
matters - never recovered for the rest of the run, regardless of anything
downstream (e.g. the noise level). A dead block stays dead; this isn't
specific to audio-rate PDUs, it's anything going through
`pdu.pdu_to_tagged_stream` on this build, given enough volume.

This block instead queues each incoming PDU's samples and drains them a
work()-call's worth at a time, so no single buffer ever needs to hold a
whole burst - correct regardless of buffer size. When idle (no queued
burst) it fills the output with zeros (silence for float/audio use; for
complex/symbol use there's no real "idle" equivalent, but returning a
real value instead of nothing keeps the same incremental-drain contract
and avoids ever blocking downstream). Still needs a Throttle, or real-rate
hardware downstream, for the float/audio case to avoid pegging a CPU
core - see dtype='float' users (open_modem_tx's audio_out) for why; the
dtype='complex' case (open_modem_rx's symbols_out) is bursty by nature
and doesn't carry that same expectation."""
import collections

import numpy
import pmt
from gnuradio import gr

_DTYPES = {
    'float': (numpy.float32, pmt.is_f32vector, pmt.f32vector_elements, pmt.init_f32vector),
    'complex': (numpy.complex64, pmt.is_c32vector, pmt.c32vector_elements, pmt.init_c32vector),
}


class pdu_to_stream(gr.sync_block):
    """'pdus' message port (f32vector or c32vector PDUs) in -> a matching
    stream out, selected by dtype ('float', the default, or 'complex')."""

    def __init__(self, dtype='float'):
        self._np_dtype, self._is_vector, self._vector_elements, _ = _DTYPES[dtype]
        gr.sync_block.__init__(self, name="pdu_to_stream", in_sig=[], out_sig=[self._np_dtype])
        self._queue = collections.deque()
        self._current = numpy.zeros(0, dtype=self._np_dtype)
        self._pos = 0
        self.message_port_register_in(pmt.intern('pdus'))
        self.set_msg_handler(pmt.intern('pdus'), self._enqueue)

    def _enqueue(self, msg):
        data = pmt.cdr(msg) if pmt.is_pair(msg) else msg
        if not self._is_vector(data):
            self.logger.warn(f"pdus: ignoring a PDU whose data isn't a {self._np_dtype.__name__} vector")
            return
        self._queue.append(numpy.array(self._vector_elements(data), dtype=self._np_dtype))

    def work(self, input_items, output_items):
        out = output_items[0]
        pos = 0
        while pos < len(out):
            if self._pos >= len(self._current):
                if not self._queue:
                    out[pos:] = 0
                    return len(out)
                self._current = self._queue.popleft()
                self._pos = 0
            n = min(len(out) - pos, len(self._current) - self._pos)
            out[pos:pos + n] = self._current[self._pos:self._pos + n]
            pos += n
            self._pos += n
        return len(out)
