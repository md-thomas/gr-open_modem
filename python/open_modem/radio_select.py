#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""Autodetect a USB radio interface's ALSA audio device and PTT serial port.

Ports the local-machine detection logic from open_wave's own
`radio_stations.py` (not importable after an editable install - same
reason as `_phy.py`'s docstring: it's a top-level script, not one of the
`openwave` package's declared py-modules) - trimmed to this computer only
(no ssh/stations.toml multi-host scanning; a GNU Radio flowgraph runs on
one machine).

Meant to be called from a GRC flowgraph's Import + Variable blocks, e.g.:

  Import:   from gnuradio.open_modem import radio_select
  Variable: station = radio_select.pick()
  Audio Sink device_name:  station['tx_device']
  Audio Source device_name: station['rx_device']
  PTT Control ptt_port:    station['ptt_port']
  PTT Control ptt_line:    station['ptt_line']

pick() raises ValueError (at flowgraph-generation/run time, loudly) if no
interface, or more than one with no name given, is found - deliberately
not a silent fallback to a possibly-wrong device.
"""
import re
import subprocess

# How to recognise each interface: its USB sound card (ALSA card id or
# name) and its serial PTT port (a /dev/serial/by-id name pattern). See
# RADIO_SETUP.md for why these two are the ones in use.
PROFILES = {
    'aioc': {'card_id': 'AllInOneCable', 'serial': re.compile(r'AIOC', re.I), 'ptt_line': 'dtr'},
    'digirig': {'card_name': 'USB PnP Sound Device', 'serial': re.compile(r'CP210', re.I),
                'ptt_line': 'rts'},
}
SCAN_CMD = "arecord -l 2>/dev/null; echo ---; ls /dev/serial/by-id 2>/dev/null"


def detect():
    """Every known radio interface attached to this computer: a list of
    dicts with name, tx_device/rx_device (ALSA - plughw: for TX, since the
    CM108-based Digirig is stereo-only on playback), ptt_port (a
    /dev/serial/by-id path, or None if not found), ptt_line."""
    out = subprocess.run(['sh', '-c', SCAN_CMD], capture_output=True, text=True,
                          timeout=20, stdin=subprocess.DEVNULL).stdout
    cards_text, _, serial_text = out.partition('---')
    cards = re.findall(r'^card \d+: (\S+) \[(.*?)\]', cards_text, re.M)
    ports = [p for p in serial_text.split() if p]
    found = []
    for name, prof in PROFILES.items():
        card = next((cid for cid, cname in cards
                     if cid == prof.get('card_id') or cname.strip() == prof.get('card_name')), None)
        if card is None:
            continue
        port = next((f'/dev/serial/by-id/{p}' for p in ports if prof['serial'].search(p)), None)
        found.append({
            'name': name,
            'tx_device': f'plughw:CARD={card},DEV=0',
            'rx_device': f'hw:CARD={card},DEV=0',
            'ptt_port': port,
            'ptt_line': prof['ptt_line'],
        })
    return found


def pick(name=None):
    """The named interface ('aioc' or 'digirig'), or the only one attached
    if none is named. Raises ValueError if none is found, the named one
    isn't present, or more than one is attached with no name given."""
    found = detect()
    if name:
        matches = [s for s in found if s['name'] == name]
        if not matches:
            raise ValueError(f"no {name!r} radio interface detected (here: "
                              + (', '.join(s['name'] for s in found) or 'none') + ")")
        return matches[0]
    if len(found) != 1:
        raise ValueError("name the radio interface to use (here: "
                          + (', '.join(s['name'] for s in found) or 'none detected') + ")")
    return found[0]
