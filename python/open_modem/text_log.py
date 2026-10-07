#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""A scrolling, multi-line, read-only text log widget - fed by 'text'
messages (plain PMT strings, the same shape `pdu_to_text` already
produces). Each message appends a new line, unlike `QT GUI Message Edit
Box` used as a display (single-line, each message replaces the last).

GNU Radio has no stock scrolling-text-log QT GUI block - only
single-line ones (`qtgui_edit_box_msg`, `qtgui_entry`, `qtgui_label`).
This one is a plain PyQt `QPlainTextEdit`, exposed the same way GRC's own
stock QT GUI blocks expose their widget for `gui_hint` grid placement
(a `qwidget()` method returning a real `QWidget`) - just without the
`sip.wrapinstance()` step those need, since this one's widget is already
a native PyQt object, not a wrapped C++ one.
"""
import pmt
from gnuradio import gr
from PyQt5 import QtCore, QtWidgets


class text_log(gr.basic_block):
    """'text' message port in -> a line appended to a scrolling QPlainTextEdit."""

    def __init__(self, max_lines=200):
        gr.basic_block.__init__(self, name="text_log", in_sig=[], out_sig=[])
        self._widget = QtWidgets.QPlainTextEdit()
        self._widget.setReadOnly(True)
        self._widget.setMaximumBlockCount(max_lines)  # oldest lines auto-trimmed
        self.message_port_register_in(pmt.intern('text'))
        self.set_msg_handler(pmt.intern('text'), self._handle)

    def qwidget(self):
        return self._widget

    def _handle(self, msg):
        text = pmt.symbol_to_string(msg) if pmt.is_symbol(msg) else str(msg)
        # Message handlers run on GNU Radio's own thread, not the Qt GUI
        # thread - touching a QWidget directly from here would be unsafe.
        # QueuedConnection marshals the call onto the widget's own thread.
        QtCore.QMetaObject.invokeMethod(
            self._widget, "appendPlainText", QtCore.Qt.QueuedConnection,
            QtCore.Q_ARG(str, text))
