#!/usr/bin/env python3
"""Where does a mode stop decoding - through this module's own _phy (the
exact code open_modem_tx/open_modem_rx call; neither block adds any DSP
of its own around it, just message-passing/threading, so testing _phy
directly here is testing the real path, just without the overhead of
driving hundreds of trials through GNU Radio's scheduler).

Reproduces open_wave's own audio_margin_sweep.py methodology and
(as a cross-check that wrapping the PHY in GNU Radio blocks didn't change
its noise performance) its numbers:

  ./margin_sweep.py -m 1 2 --fec r1_2_k3
  ./margin_sweep.py -m 0 --fec r1_4_k9 --sigmas 1.3 1.6 2.0 --trials 30

open_wave's own measurement (2026-10-04, mic port, 30-char message, 24
bursts/point - see open_wave/RADIO_SETUP.md): mode 0 r1_4_k9 breaks near
-1 dB, mode 1 r1_2_k3 near 4.5 dB, mode 2 r1_2_k3 near 7 dB.

Also reports, alongside "delivered" (decode_frames succeeded), how many
of those would actually reach open_modem_rx's pdu_out - i.e. also clear
its own 'threshold' parameter's default (0.4) sync-quality gate before
decode_frames is even tried. If that number is ever lower than
"delivered", open_modem_rx's default threshold is rejecting bursts
decode_frames could still have recovered.
"""
import argparse

import numpy as np

from gnuradio.open_modem import _phy
import openwave_fec as fec
import openwave_link as link

RX_THRESHOLD = 0.4  # open_modem_rx's own default 'threshold' parameter


def main():
    p = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    p.add_argument('-m', '--modes', type=int, nargs='+', default=[0, 1, 2],
                   choices=sorted(link.WAVEFORM_MODES))
    p.add_argument('--fec', choices=sorted(fec.PRESETS), default='r1_2_k3')
    p.add_argument('--port', choices=('mic', 'data'), default='mic')
    p.add_argument('--text', default='K0MDT OpenWave test mode X #1', help='message to send')
    p.add_argument('--sigmas', type=float, nargs='+',
                   default=[0.10, 0.19, 0.27, 0.38, 0.55, 0.65, 0.78, 0.92, 1.1, 1.3, 1.6],
                   help='noise rms added to the audio (burst peak is 0.5)')
    p.add_argument('--trials', type=int, default=24)
    p.add_argument('--seed', type=int, default=7)
    args = p.parse_args()

    rng = np.random.default_rng(args.seed)
    payload = args.text.encode()
    for mode in args.modes:
        print(f"--- mode {mode} {args.fec}")
        for sigma in args.sigmas:
            delivered, rx_would_accept, snrs = 0, 0, []
            for _ in range(args.trials):
                s = _phy.build_burst(payload, mode, src_id='K0MDT', dst_id='ALL',
                                      fec_preset=args.fec, port=args.port, level=0.5, lead_in_s=0.5)
                x = np.concatenate([np.zeros(48000), s, np.zeros(48000)])
                noisy = (x + rng.normal(0, sigma, len(x))).astype(np.float32)
                r = _phy.decode_burst(noisy, mode, args.fec, args.port)
                ok = r['payload'] == payload
                delivered += ok
                rx_would_accept += ok and r['quality'] >= RX_THRESHOLD
                if r['quality'] >= 0.15 and np.isfinite(r['snr_db']):
                    snrs.append(r['snr_db'])
            mean_snr = np.mean(snrs) if snrs else float('nan')
            print(f"  sigma {sigma:.2f}: SNR {mean_snr:5.1f} dB  delivered {delivered}/{args.trials}"
                  f"  (open_modem_rx would accept {rx_would_accept}/{args.trials})", flush=True)


if __name__ == '__main__':
    main()
