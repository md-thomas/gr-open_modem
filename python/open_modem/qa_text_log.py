#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
import os
os.environ.setdefault('QT_QPA_PLATFORM', 'offscreen')  # no display in CI/ctest

import pmt
from gnuradio import gr, gr_unittest
from PyQt5 import QtWidgets

from gnuradio.open_modem import text_log


class qa_text_log(gr_unittest.TestCase):

    def setUp(self):
        self.tb = gr.top_block()
        # One QApplication for the whole test process - constructing a
        # QWidget (text_log's QPlainTextEdit) needs one to already exist.
        self.qapp = QtWidgets.QApplication.instance() or QtWidgets.QApplication([])

    def tearDown(self):
        self.tb = None

    def test_instance(self):
        text_log()

    def test_appends_rather_than_replaces(self):
        block = text_log(max_lines=50)
        block._handle(pmt.intern("first line"))
        block._handle(pmt.intern("second line"))
        # QueuedConnection defers appendPlainText onto the Qt event loop -
        # pump it so the deferred calls actually run before we check.
        for _ in range(10):
            self.qapp.processEvents()

        text = block.qwidget().toPlainText()
        self.assertIn("first line", text)
        self.assertIn("second line", text)
        # both present (appended), not just the most recent one replacing
        # the first - the whole point of this block vs a single-line box
        self.assertLess(text.index("first line"), text.index("second line"))

    def test_max_lines_trims_oldest(self):
        block = text_log(max_lines=3)
        for i in range(10):
            block._handle(pmt.intern(f"line {i}"))
        for _ in range(10):
            self.qapp.processEvents()

        text = block.qwidget().toPlainText()
        self.assertNotIn("line 0", text)
        self.assertIn("line 9", text)


if __name__ == '__main__':
    gr_unittest.run(qa_text_log)
