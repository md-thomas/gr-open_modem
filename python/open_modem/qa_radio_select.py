#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
import unittest

from gnuradio.open_modem import radio_select


class qa_radio_select(unittest.TestCase):

    def test_detect_returns_a_list_of_known_shape(self):
        found = radio_select.detect()
        self.assertIsInstance(found, list)
        for st in found:
            self.assertIn(st['name'], radio_select.PROFILES)
            for key in ('tx_device', 'rx_device', 'ptt_port', 'ptt_line'):
                self.assertIn(key, st)

    def test_pick_raises_with_a_clear_message_when_none_found(self):
        # This test environment has no AIOC/Digirig attached - exercises
        # the "name the interface" / "none detected" error path.
        if radio_select.detect():
            self.skipTest("a real radio interface is attached to this machine")
        with self.assertRaises(ValueError):
            radio_select.pick()


if __name__ == '__main__':
    unittest.main()
