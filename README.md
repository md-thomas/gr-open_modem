# gr-open_modem

A GNU Radio out-of-tree module wrapping [open_wave](https://github.com/md-thomas/open_wave)'s
digital modem/PHY (framing, FEC, BPSK/QPSK/16-QAM, audio modulation) as
GNU Radio blocks, plus a PTT control block for keying a radio over a serial
line (AIOC: DTR, Digirig: RTS) - so an HT on a USB sound-card interface and
an SDR (Pluto, RTL-SDR - see `../pluto_test.grc`/`../rtlsdr_test.grc`) can
share the same flowgraph framework and the same modem code.

## Why this exists alongside open_wave's own `ota_station.py`

open_wave already has a proven, pure-Python HT radio path (`arecord`/`aplay`
+ pyserial PTT - see its own `RADIO_SETUP.md`, verified on an AIOC and a
Digirig in both directions). This module doesn't replace that; it buys
composability with GNU Radio's own SDR blocks and visualization (GUI
constellation/FFT, like the project's own archived
`open_wave/legacy/gnuradio/phy_sim_loopback.grc`), at the cost of a second
audio/PTT implementation to validate against the first. See
`REQUIREMENTS.md` for the non-goals.

## Status

Phases 1-4 and 2b are done - see `TODO.md` for the detailed, most-recent-first
log, including several real bugs this uncovered (a `gr_modtool` CMakeLists
gap, a silent GRC `dtype: enum` footgun, a GNU Radio buffer-allocator
ceiling on this machine, and a receive-side limitation with back-to-back
fragment bursts) and how each was fixed, worked around, or - for the last
one - documented as a known open risk.

- `open_modem_tx`/`open_modem_rx` call into `python/open_modem/_phy.py`,
  which reuses open_wave's own framing/FEC/modulation code
  (`openwave_link`/`openwave_modem`/`openwave_fec`/`openwave_audio`) rather
  than reimplementing it - the same logic open_wave's own proven
  `audio_wav_test.py` uses, ported rather than imported since
  `audio_wav_test.py` itself isn't one of the installable package's
  modules (see `_phy.py`'s docstring).
- Fragmentation (anything over `MAX_PAYLOAD_LEN`) and single-frame
  ACK/retry (`openwave_link.RetryManager`, a new `ack_responder` block to
  actually send the ACK back) both work, verified via QA tests exercising
  the real PHY and via `examples/open_modem_loopback.grc` actually closing
  a live ACK loop over several messages. Back-to-back fragment bursts have
  a known, documented receive-side limitation - see `TODO.md`'s Open
  section before relying on fragmentation for anything time-critical.
- `radio_select.py` autodetects an attached AIOC/Digirig (ported from
  `radio_stations.py`, same reason as `_phy.py`).
- `examples/open_modem_loopback.grc` is a real, runnable, no-hardware demo
  of the full TX -> RX round trip with ACK - run it and watch Message
  Debug print a decoded frame and its ACK resolve.
- `examples/open_modem_ht.grc` is the live AIOC/Digirig station (Audio
  Source/Sink + `open_modem_tx`/`rx` + `ptt_control` + `ack_responder`,
  devices resolved via `radio_select`). It compiles and its generated code
  looks right, but **has not been run** - this development environment has
  neither the hardware nor a display. Phase 5 is that first real test.
- Hardware PTT timing accuracy (lead-in/tail baked into the burst vs. the
  stream pipeline's own latency) is still unvalidated - flagged in
  `TODO.md` as the biggest remaining risk.

## Dependency

Needs `open_wave` importable. It isn't on PyPI, and `pip install -e`'s
editable mode (modern setuptools, strict `py-modules`) only exposes the
modules its `pyproject.toml` actually lists - not top-level scripts like
`audio_wav_test.py`, which is why `_phy.py` reimplements its two functions
instead of importing it. This system's apt-packaged GNU Radio Python is
"externally managed" (PEP 668), so the editable install needs
`--break-system-packages` (still a `--user` install, not a system one):

```
pip install --user --break-system-packages -e ../../open_wave
```

matching the same sibling-repo/editable-install convention
`open_modem`'s own README documents for `web_sdr`/`web_siggen`.

## Build

Pure-Python blocks, no C++ - still built/installed through the standard
OOT CMake flow so GRC's `.block.yml` files land where it looks for them:

```
mkdir build && cd build
cmake -DCMAKE_INSTALL_PREFIX=$HOME/.local ..
make && make install
```

A user-prefix install needs GRC told where to find it - this repo's setup
added `local_blocks_path = $HOME/.local/share/gnuradio/grc/blocks` to
`~/.gnuradio/config.conf`'s `[grc]` section (that key is additive to the
system default, unlike `global_blocks_path`).

## Tests

```
cd build && ctest --output-on-failure
```

## Examples

```
cd examples
GRC_BLOCKS_PATH="$HOME/.local/share/gnuradio/grc/blocks" grcc open_modem_loopback.grc
python3 open_modem_loopback.py
```

No hardware needed - a message strobe sends a test burst (ACK requested)
through the real PHY every few seconds. Message Debug prints the decoded
frame, the PTT key/unkey events a real radio flowgraph would act on
instead (one pair for the data burst, one for the ACK responding to it),
and the ACK loop closes within the same process - no `delivery_failed`
message should ever appear here.

`open_modem_ht.grc` needs a real AIOC or Digirig attached (it autodetects
via `radio_select`, failing loudly at startup if it finds none or more than
one - name which with `--radio aioc`/`--radio digirig`) and a display (it's
`qt_gui`, with a "Send" box). See open_wave's own `RADIO_SETUP.md` for
antenna/level/licensing setup - the same cautions apply here.
