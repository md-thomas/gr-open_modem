# gr-open_modem — Requirements

See [TODO.md](TODO.md) for status and this repo's own [README.md](README.md)
for the day-to-day how-to (build, install, test). This document is the
"why/what".

## 1. Purpose

Give GNU Radio flowgraphs access to open_wave's modem/PHY and link-layer
framing as ordinary blocks, and give a GNU-Radio-native way to key/unkey a
radio's PTT over a serial line - so HT-over-USB-soundcard stations (AIOC,
Digirig) and SDR stations (ADALM-Pluto, RTL-SDR - already used elsewhere in
this `gnuradio` directory) can be built from the same block set and share
the same modem code, instead of each having its own.

## 2. Structure

A standard `gr_modtool`-scaffolded, pure-Python OOT module (no C++, no
pybind - `lib/`, `include/` are unused). Depends on `open_wave` as an
editable install from a sibling checkout (see README's "Dependency"), the
same pattern `open_modem`'s README documents for `web_sdr`/`web_siggen`.

Blocks (all message-driven except `open_modem_rx`'s/`pdu_to_stream`'s
stream side, no fixed-rate stream transform otherwise):
- `open_modem_tx` — text/bytes PDU in (auto-fragmenting over
  `MAX_PAYLOAD_LEN`); modulated audio burst PDU(s) and 'key'/'unkey'
  PTT-timing messages out per burst. Optional ACK/retry
  (`openwave_link.RetryManager`) for single-frame sends, via an
  `ack_received` input and `delivery_failed` output.
- `open_modem_rx` — continuous float audio stream in; decoded/reassembled
  frame PDUs out, plus `ack_needed`/`ack_received` dispatch for ACK
  frames and frames requesting one.
- `ack_responder` — turns `open_modem_rx`'s `ack_needed` into a real ACK
  burst (RX can't send one itself); same audio_out/ptt shape as
  `open_modem_tx`, so both fan into the same downstream blocks.
- `ptt_control` — 'key'/'unkey' messages in; toggles a serial DTR/RTS line.
- `pdu_to_stream` — a float-PDU message port in, a float stream out,
  drained incrementally (not the stock `pdu.pdu_to_tagged_stream`, which
  needs a buffer sized to a whole burst - see TODO.md).

## 3. Requirements on this module specifically

- **No DSP reimplementation.** Modulation, demodulation, framing, FEC, and
  burst detection belong to `open_wave`; these blocks call into it (via
  `python/open_modem/_phy.py`) rather than duplicating its logic. `_phy.py`
  itself is a necessary exception in the strictest sense — it reimplements
  `audio_wav_test.py`'s two top-level functions, because that script isn't
  part of the installable `openwave` package — but it calls the same
  underlying `openwave_link`/`openwave_modem`/`openwave_fec`/
  `openwave_audio` functions, line for line, rather than any new DSP.
- **PTT timing must not block the GNU Radio scheduler thread.** `ptt_play.py`
  (the proven pure-Python version) blocks on `time.sleep`/`aplay`; this
  module's `ptt_control` must stay message-driven and non-blocking.
- **A user-prefix install (no root) must work for development** —
  `CMAKE_INSTALL_PREFIX=$HOME/.local`, GRC told about it via
  `local_blocks_path` in `~/.gnuradio/config.conf` (additive, unlike
  `global_blocks_path`).

## 4. Non-goals

- **Not a replacement for `ota_station.py`.** That pure-Python stack is
  already proven on real radios (AIOC + Digirig, both directions,
  2026-10-04); this module is a parallel, GNU-Radio-native path, evaluated
  against it (Phase 5), not a mandate to retire it.
- **Not a new modem.** Every modulation/framing choice already made in
  `open_wave` (BPSK/QPSK/16-QAM, the frame header/CRC/ACK/fragmentation
  format, the FEC presets) is inherited as-is, not redesigned here.

## 5. Related/adjacent projects

- **open_wave** (`$HOME/Projects/open_wave`) — the PHY and link-layer this
  module wraps; see its own `REQUIREMENTS.md`/`RADIO_SETUP.md`.
- **open_modem** (`$HOME/Projects/open_modem`) — the meta-repo aggregating
  `open_wave` and the `general_*` demo modems; this module depends on the
  sibling `open_wave` checkout directly, not through that meta-repo (see
  README's "Dependency").
- **`../pluto_test.grc` / `../rtlsdr_test.grc`** — this directory's existing
  SDR flowgraphs; a motivation for building this as GNU Radio blocks rather
  than extending the pure-Python radio stack.
