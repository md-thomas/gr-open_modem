#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""A float-PDU message port in, a float stream out - drained incrementally.

Exists because the stock `pdu.pdu_to_tagged_stream` writes an entire PDU as
one tagged packet in a single work() call, which needs an output buffer
sized to the longest burst that will ever arrive. For open_modem_tx's
audio_out bursts that's impractical: a mic-port (600/1200 baud) burst can
be tens of thousands of samples, and on this machine GNU Radio's buffer
allocator silently clamps any requested `maxoutbuf` down to 16384 items
regardless of what's asked for ("Block (...) max output buffer set to
16384 instead of requested ...") - well under even a single-byte-payload
mode 0 burst (~47000 samples) - so pdu_to_tagged_stream drops the burst
outright on this build (see TODO.md).

This block instead queues each incoming PDU's samples and drains them a
work()-call's worth at a time, so no single buffer ever needs to hold a
whole burst - correct regardless of buffer size. When idle (no queued
burst) it fills the output with silence rather than returning 0: a real
audio channel is never actually silent/absent between bursts, and
anything downstream that infers elapsed time from sample count (e.g.
open_modem_rx's periodic burst-detect scan) needs that steady trickle of
samples the way it would get them from a real Audio Source. Same reason
this and any flowgraph using it still needs a Throttle, or real-rate
hardware downstream, to avoid pegging a CPU core."""
import collections

import numpy
import pmt
from gnuradio import gr


class pdu_to_stream(gr.sync_block):
    """'pdus' message port (f32vector PDUs) in -> float stream out."""

    def __init__(self):
        gr.sync_block.__init__(self, name="pdu_to_stream", in_sig=[], out_sig=[numpy.float32])
        self._queue = collections.deque()
        self._current = numpy.zeros(0, dtype=numpy.float32)
        self._pos = 0
        self.message_port_register_in(pmt.intern('pdus'))
        self.set_msg_handler(pmt.intern('pdus'), self._enqueue)

    def _enqueue(self, msg):
        data = pmt.cdr(msg) if pmt.is_pair(msg) else msg
        if not pmt.is_f32vector(data):
            self.logger.warn("pdus: ignoring a PDU whose data isn't an f32vector")
            return
        self._queue.append(numpy.array(pmt.f32vector_elements(data), dtype=numpy.float32))

    def work(self, input_items, output_items):
        out = output_items[0]
        pos = 0
        while pos < len(out):
            if self._pos >= len(self._current):
                if not self._queue:
                    out[pos:] = 0.0
                    return len(out)
                self._current = self._queue.popleft()
                self._pos = 0
            n = min(len(out) - pos, len(self._current) - self._pos)
            out[pos:pos + n] = self._current[self._pos:self._pos + n]
            pos += n
            self._pos += n
        return len(out)
