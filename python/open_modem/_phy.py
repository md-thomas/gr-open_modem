#!/usr/bin/env python
# -*- coding: utf-8 -*-
#
# Copyright 2026 mdthomas.
#
# SPDX-License-Identifier: GPL-3.0-or-later
#
"""Bridge between GNU Radio PDUs and open_wave's PHY.

Ports two functions from open_wave's own `audio_wav_test.py` - its offline
over-the-air test harness, the thing `radio_send.py`/`radio_listen.py`
(proven on real AIOC/Digirig hardware - see RADIO_SETUP.md) build on -
rather than importing it directly: `audio_wav_test` isn't part of the
installable `openwave` package (only the modules its pyproject.toml lists
as `py-modules` are; a plain top-level script like `audio_wav_test.py`
isn't importable after `pip install -e`), so `build_burst`/`decode_burst`
below are the same logic, kept to the package modules
(`openwave_link`/`openwave_modem`/`openwave_fec`/`openwave_audio`) that
pip install actually exposes.

Not a GNU Radio block itself - plain functions `open_modem_tx`/
`open_modem_rx` call into.
"""
import threading

import numpy as np
import pmt

import openwave_audio as audio
import openwave_fec as fec
import openwave_link as link
import openwave_modem as modem

MODULATORS = {
    'bpsk': modem.modulate_bpsk,
    'qpsk': modem.modulate_qpsk,
    '16qam': modem.modulate_qam16,
}
DEMODULATORS = {
    'bpsk': modem.demodulate_bpsk,
    'qpsk': modem.demodulate_qpsk,
    '16qam': modem.demodulate_qam16,
}
BITS_PER_SYMBOL = {'bpsk': 1, 'qpsk': 2, '16qam': 4}


def mode_params(mode_id, fec_preset=None, port='mic'):
    """mode_id -> (modulation name, symbol_rate, FEC generators, K, carrier_hz)."""
    m = link.WAVEFORM_MODES[mode_id]
    gens, k = fec.PRESETS[fec_preset or m['fec_preset']]
    carrier_hz = audio.PORT_PROFILES[port]['carrier_hz']
    return m['modulation'], m['symbol_rate'], gens, k, carrier_hz


def modulate_frame(raw_frame, mode_id, fec_preset=None, port='mic', level=audio.DEFAULT_LEVEL,
                    lead_in_s=audio.DEFAULT_LEAD_IN_S, tail_s=audio.DEFAULT_TAIL_S):
    """A link.build_frame()/build_ack_frame()-style IQ frame (lead-in zeros,
    IQ_MARKER, header, payload, CRC, trailing zeros) -> one audio burst's
    samples. The shared last step for build_burst/build_fragmented_bursts/
    build_ack_burst below - each just builds a different raw_frame first."""
    mod, rate, gens, k, carrier = mode_params(mode_id, fec_preset, port)
    frame = audio.frame_for_audio(raw_frame)
    symbols = MODULATORS[mod](fec.encode_frame(frame, gens, k, marker=link.AUDIO_MARKER))
    return audio.modulate(symbols, rate, carrier, level=level, lead_in_s=lead_in_s, tail_s=tail_s)


def build_burst(payload, mode_id, src_id='NOCALL', dst_id='ALL', fec_preset=None,
                 port='mic', level=audio.DEFAULT_LEVEL, lead_in_s=audio.DEFAULT_LEAD_IN_S,
                 tail_s=audio.DEFAULT_TAIL_S, seq=0, flags=0):
    """Payload bytes -> real audio samples (float, 48 kHz) for one burst.

    Single-frame only - raises if payload exceeds link.MAX_PAYLOAD_LEN; use
    build_fragmented_bursts for anything longer. seq/flags let a caller
    (open_modem_tx) set the Sequence Number and Flags (e.g.
    link.FLAG_ACK_REQUESTED, or a retransmission's unchanged seq) - both
    default to a plain first-send of a self-contained frame."""
    if len(payload) > link.MAX_PAYLOAD_LEN:
        raise ValueError(f"payload is {len(payload)} bytes, over the "
                          f"{link.MAX_PAYLOAD_LEN}-byte single-frame limit "
                          "(use build_fragmented_bursts instead)")
    raw_frame = link.build_frame(payload, mode_id=mode_id, src_id=src_id, dst_id=dst_id,
                                  seq=seq, flags=flags)
    return modulate_frame(raw_frame, mode_id, fec_preset, port, level, lead_in_s, tail_s)


def build_fragmented_bursts(payload, seq_start, mode_id, src_id='NOCALL', dst_id='ALL', flags=0,
                             fec_preset=None, port='mic', level=audio.DEFAULT_LEVEL,
                             lead_in_s=audio.DEFAULT_LEAD_IN_S, tail_s=audio.DEFAULT_TAIL_S):
    """Payload bytes (any length) -> (list of audio bursts, next_seq), one
    burst per fragment - see link.build_fragmented_frames's docstring (a
    single-chunk payload comes back as a length-1 list, identical to
    build_burst, with no fragmentation flags set). flags is ORed with
    FLAG_FRAGMENTED/FLAG_MORE_FRAGMENTS automatically per fragment when
    there's more than one - pass link.FLAG_ACK_REQUESTED here for a
    caller that wants the (single-fragment-only) ACK/retry path."""
    raw_frames, next_seq = link.build_fragmented_frames(payload, seq_start, mode_id=mode_id,
                                                          src_id=src_id, dst_id=dst_id, flags=flags)
    bursts = [modulate_frame(f, mode_id, fec_preset, port, level, lead_in_s, tail_s)
              for f in raw_frames]
    return bursts, next_seq


def build_ack_burst(acked_seq, mode_id, src_id='NOCALL', dst_id='ALL', fec_preset=None,
                     port='mic', level=audio.DEFAULT_LEVEL, lead_in_s=audio.DEFAULT_LEAD_IN_S,
                     tail_s=audio.DEFAULT_TAIL_S):
    """The over-the-air ACK burst for acked_seq - see link.build_ack_frame."""
    raw_frame = link.build_ack_frame(acked_seq, mode_id=mode_id, src_id=src_id, dst_id=dst_id)
    return modulate_frame(raw_frame, mode_id, fec_preset, port, level, lead_in_s, tail_s)


def publish_keyed_burst(samples, publish_audio, publish_ptt, sample_rate=audio.AUDIO_SAMPLE_RATE):
    """Publish one audio burst (as a PDU, via publish_audio(pmt_msg)) and the
    matching PTT key/unkey messages (via publish_ptt(pmt_msg); 'unkey' is
    scheduled, via a threading.Timer, for the burst's real-time duration
    after 'key') - shared by open_modem_tx and ack_responder so a station's
    data frames and its ACK responses key PTT identically."""
    meta = pmt.make_dict()
    meta = pmt.dict_add(meta, pmt.intern('sample_rate'), pmt.from_long(sample_rate))
    data = pmt.init_f32vector(len(samples), [float(s) for s in samples])
    publish_audio(pmt.cons(meta, data))
    publish_ptt(pmt.intern('key'))
    threading.Timer(len(samples) / sample_rate, lambda: publish_ptt(pmt.intern('unkey'))).start()


def decode_burst(x, mode_id, fec_preset=None, port='mic'):
    """Audio samples -> dict: rms, peak, quality (0..1), snr_db, timing
    (sample index of the burst marker, or None), status ('no_burst',
    'no_frame', a decode_frames() failure status, or 'ok'), header, payload."""
    mod, rate, gens, k, carrier = mode_params(mode_id, fec_preset, port)
    out = {'rms': float(x.std()) if len(x) else 0.0,
           'peak': float(np.abs(x).max()) if len(x) else 0.0,
           'quality': 0.0, 'snr_db': float('-inf'), 'status': 'no_burst',
           'payload': None, 'header': None, 'timing': None}
    symbols, info = audio.demodulate(x, rate, carrier, MODULATORS[mod](link.AUDIO_MARKER),
                                      constellation=modem._CONSTELLATIONS[mod])
    out['quality'], out['snr_db'] = float(info['quality']), float(info['snr_db'])
    out['timing'] = info['timing']
    if info['quality'] < 0.15:
        return out
    n = 8 // BITS_PER_SYMBOL[mod]
    symbols = symbols[:len(symbols) - len(symbols) % n]
    bits = DEMODULATORS[mod](symbols)
    frames = list(fec.decode_frames(bits, gens, k, first_marker_bit=info['marker_index'] * BITS_PER_SYMBOL[mod],
                                     marker=link.AUDIO_MARKER))
    out['status'] = 'no_frame'
    for status, header, payload in frames:
        out['status'] = status
        if status == 'ok':
            out['payload'], out['header'] = payload, header
            break
    return out


def burst_length_samples(mode_id, fec_preset, port, payload_len):
    """On-air length, in samples, of a frame whose payload is payload_len
    bytes - how far to trim a receive buffer past a decoded burst."""
    mod, rate, gens, k, _ = mode_params(mode_id, fec_preset, port)
    frame = audio.frame_for_audio(link.build_frame(bytes(payload_len), mode_id=mode_id))
    return (len(MODULATORS[mod](fec.encode_frame(frame, gens, k, marker=link.AUDIO_MARKER)))
            * audio.samples_per_symbol(rate))


def modes_fitting_port(port='mic'):
    """Mode IDs whose symbol rate fits within port's max_symbol_rate."""
    cap = audio.PORT_PROFILES[port]['max_symbol_rate']
    return [m for m, v in sorted(link.WAVEFORM_MODES.items()) if v['symbol_rate'] <= cap]
