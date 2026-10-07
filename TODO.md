# gr-open_modem — TODO / Status

Companion to [REQUIREMENTS.md](REQUIREMENTS.md).

## Open

- [ ] **Back-to-back fragment bursts can confuse the receive-side burst
      detector.** Discovered while testing Phase 2b's fragmentation:
      `_phy.decode_burst`/`openwave_audio.demodulate`'s marker search finds
      the single strongest correlation peak in whatever buffer it's given,
      not necessarily the earliest one. If a fragmented message's second
      (or later) fragment's preamble has already arrived by the time the
      first fragment's `_step()` check runs, the search can lock onto the
      later marker first - leaving the earlier fragment's data effectively
      skipped and the later fragment arriving at `FragmentReassembler`
      with no run in progress, so it's discarded (not reassembled, not
      delivered, no error surfaced beyond the discard counter). Reproduced
      at both a slow mode (mode 1, the first ~14s fragment) and a fast one
      (mode 5) - duration isn't the determining factor, back-to-back
      timing is. Not yet hit in `open_modem_loopback.grc`'s own ACK demo
      (single-frame messages only) or in real open_wave usage (bursts are
      always short enough, and spaced out enough by human typing speed,
      that this doesn't arise) - but a real risk for fragmented sends
      specifically, since open_modem_tx currently publishes all of a
      message's fragments with no enforced gap between them. Candidate
      fixes: have open_modem_tx pace fragments with a real turnaround
      delay between them (matching a real half-duplex radio's own
      constraint anyway), and/or have `_step()` re-scan a trimmed,
      earlier sub-window first instead of handing the whole accumulated
      buffer to one `decode_burst` call. `qa_open_modem_rx.py`'s
      fragmentation test works around this by decoding each fragment in
      isolation and feeding `_dispatch()` directly, rather than through a
      shared receive buffer - see that test's own docstring.
- [ ] **Phase 5 — hardware validation. BLOCKED - deferred, come back to
      this later.** This development environment has no AIOC/Digirig
      attached (and no display for `open_modem_ht.grc`'s `qt_gui`), so
      none of the below can be done here - picking this up means working
      on a machine with the actual hardware. When that's available:
      - Bench-test against the AIOC/Digirig pair; compare decode
        reliability/SNR against the documented `ota_station.py` baseline
        in open_wave's `RADIO_SETUP.md` (BPSK 600/1200, QPSK 1200) to
        confirm no regression.
      - Actually run `open_modem_ht.grc` for the first time (so far only
        compile-checked, via temporarily stubbing `radio_select.detect()`
        - see TODO's Phase 4 entry) - real PTT keying, real audio
        levels, the lot.
      - Validate PTT timing accuracy against real hardware latency - see
        that entry below.
      - Check whether the back-to-back-fragment-burst issue above
        actually manifests on real radios, where turnaround/key timing
        may naturally separate fragments more than this environment's
        synthetic tests did (or may not).
      - Add `grcc` compile checks for the new `.grc` files, following
        `legacy/gnuradio/tests/test_flowgraphs_compile.py`'s pattern.
- [ ] **PTT timing accuracy** (the biggest open risk, flagged since the
      original plan): `open_modem_tx`'s lead-in/tail are baked into the
      burst samples and `ptt_control`'s unkey is scheduled from a
      `threading.Timer` sized to the burst duration — this hasn't been
      validated against the stream pipeline's own latency (resampling,
      Audio Sink buffering) the way the proven file-based `aplay` approach
      doesn't have to worry about. Needs a real hardware check in Phase 5,
      not just a software loopback.

## Done (most recent first)

- [x] **`margin_sweep.py` gained a `--level` flag** (default 0.5, unchanged
      - matches `audio_margin_sweep.py`'s own hardcoded convention),
      after a user's live reading didn't match a cliff table quoted in
      conversation: mode 2 at `sigma 0.9` was still decoding (SNR ~5 dB,
      quality 0.88), where the table said that sigma should read ~1.3 dB
      and fail outright. Root cause: that table was measured with
      `level=0.5` (the script's hardcoded default, inherited from
      `audio_margin_sweep.py`), but `open_modem_tx_0` in both
      `open_modem_noisy_loopback.grc` and `open_modem_constellation.grc`
      uses `tx_level=0.7` - a stronger burst against the same noise sigma
      reads a higher effective SNR, so the table was simply measured
      against the wrong signal level for those flowgraphs, not wrong
      about the decoder's own behavior. Re-measured mode 2 (`r1_2_k7`,
      40 trials) at the matching `level=0.7`:

      | sigma | SNR | delivered |
      |---|---|---|
      | 0.5 | 9.5 dB | 100% |
      | 0.7 | 6.6 dB | 100% |
      | 0.9 | 4.5 dB | 82.5% |
      | 1.1 | 2.4 dB | 12.5% |
      | 1.3 | 1.1 dB | 0% |

      matching the live reading (sigma 0.9 -> ~4.5 dB mean, individual
      bursts scattering above/below that, including readings over 5 dB)
      and shifting mode 2's real cliff for these flowgraphs to roughly
      `sigma` 1.0-1.1, not 0.7-0.9. Any `--level`-less `margin_sweep.py`
      comparison against a flowgraph must match that flowgraph's own
      `tx_level`, or the numbers aren't comparable - the two aren't
      interchangeable just because both are "noise standard deviation
      against a burst."
- [x] **Fixed two real bugs in `open_modem_constellation.grc`, found
      interactively** (user: "symbols stopped plotting... lowering sigma
      doesn't fix it"):
      1. The stock `pdu.pdu_to_tagged_stream` feeding the Constellation
         Sink hit this machine's same 16384-item buffer ceiling that
         `pdu_to_stream.py` was built to work around for the audio path -
         wrongly assumed symbol-rate PDUs (hundreds to low thousands per
         burst) would always stay under it. Confirmed live by tapping the
         raw stream with a `vector_sink_c`: growth stopped dead the
         instant `thread_body_wrapper` logged "Buffer too small for
         min_noutput_items", and - the important part - never resumed for
         the rest of the run, regardless of noise level. A dead block
         stays dead; that's why changing the noise slider looked like it
         should help and didn't. Fixed by generalizing `pdu_to_stream`
         itself to take a `dtype` ('float', the default, or 'complex')
         instead of being float-only, and using it (dtype='complex')
         in place of the stock block. New QA test deliberately exceeds
         16384 complex items to prove it.
      2. Fixing #1 uncovered a second, worse bug immediately: with
         nothing downstream rate-limiting the now-never-dying complex
         stream, it free-ran as fast as the CPU allowed between bursts -
         measured at 168 million samples in 5 seconds. `pdu_to_stream`'s
         always-fill-with-something-when-idle design (right for the
         audio case, where a real channel is never actually silent) does
         not generalize to a symbol stream with no real-time pacing
         behind it at all. Fixed with a `blocks.throttle` (9600 items/s)
         between the two - its own docstring says exactly this is its
         job ("should only be used in GUI apps where there is no other
         rate limiting block"). Verified over a full 40s run: steady
         ~9700 samples/s growth throughout, no stall, no runaway.
- [x] **Added a real constellation display** - `open_modem_rx` gained a
      `symbols_out` message port (and `_phy.decode_burst` now returns the
      demodulated `symbols`, a non-breaking additive change) publishing
      the actual post-recovery complex symbols for every burst it
      dispatches, truncated to the real frame length (new
      `_phy.burst_length_symbols`, factored out of `burst_length_samples`)
      so a plot isn't diluted by `demodulate()`'s long decision-directed
      tracking tail past the frame's end into trailing silence/noise -
      found via a QA test (`qa_open_modem_rx.py`) that initially asserted
      too strict a threshold on the untruncated array and failed, which is
      what surfaced the need for the truncation in the first place.
      `examples/open_modem_constellation.grc` wires this through a stock
      `PDU to Tagged Stream` (fine here - symbol counts per burst are
      hundreds to low thousands, well under the buffer ceiling that's a
      real problem for the much larger audio-sample-rate PDUs elsewhere in
      this module) to a QT GUI Constellation Sink, with noise_sigma as a
      live slider instead of a CLI flag. Verified end to end (not just
      compiled): ran it headlessly (`QT_QPA_PLATFORM=offscreen`), spied on
      `symbols_out`, confirmed real non-empty complex vectors (944 and 576
      symbols for a data burst and its ACK) actually reached the point
      where they'd be plotted.
- [x] **Fixed a real footgun in `examples/open_modem_noisy_loopback.grc`**,
      found interactively (user editing it in GNU Radio Companion): each
      of `open_modem_tx_0`, `open_modem_rx_0`, and `ack_responder_0`
      carried its own independent `mode_id`/`mode_ids` value, with no
      link between them. Changing TX's mode (to try a different Waveform
      Mode) without also updating RX's silently breaks delivery
      completely - not "worse under noise," totally broken even
      noise-free, confirmed directly: feeding a mode-2 burst to
      `_phy.decode_burst` with `mode_id=1` at zero added noise gave
      quality 0.23 (below the 0.4 threshold) - each mode modulates even
      its preamble differently, so a mismatched RX has nothing to
      correlate against. Fixed by adding one shared `mode_id` Parameter
      (`--mode-id`/`-m`) that all three blocks now reference instead of
      each carrying a literal - confirmed the generated code passes the
      same `mode_id` variable to all three constructors, and re-verified
      mode 2 end to end (`status: ok`, correct payload, both messages).
- [x] **Added `examples/open_modem_noisy_loopback.grc`** - the live,
      GNU-Radio-native counterpart to `apps/margin_sweep.py`'s offline
      noise sweep: the same TX/RX/ACK loop as `open_modem_loopback.grc`,
      with `analog.noise_source_f` + `blocks.add_ff` injecting Gaussian
      noise into the channel (not the stock `channels_channel_model`,
      complex-only and the wrong fit for this real-valued audio PHY).
      Noise level is a real CLI parameter (`--noise-sigma`/`-n`), not
      hardcoded. Verified at both ends: `--noise-sigma 0.1` decodes
      cleanly (SNR ~22-23 dB, status ok); `--noise-sigma 1.5` produces
      consistent `crc_fail` (SNR near 0 dB, every burst heard but
      corrupted) with visible retries, matching mode 1's measured cliff
      region from the margin-sweep entry below. Added `examples/README.md`
      (replacing `gr_modtool`'s placeholder `examples/README`) describing
      all three example flowgraphs.
- [x] **Noise-margin sweep, reproducing open_wave's own
      `audio_margin_sweep.py` against `_phy.py`** (the exact code
      `open_modem_tx`/`open_modem_rx` call - no DSP of their own around
      it). Added `apps/margin_sweep.py`, installed via
      `gr_python_install(PROGRAMS ...)`. First cross-checked for drift:
      fed `audio_wav_test.build_samples`/`decode_samples` and
      `_phy.build_burst`/`decode_burst` the identical burst and identical
      noise array - bit-identical burst, decode results matching to
      float precision. No implementation drift from wrapping the PHY in
      GNU Radio blocks.

      Then ran the actual sweep (24 trials/point, mic port, 30-char
      message, matching the documented methodology exactly), and - since
      the result didn't match open_wave's own docstring summary - ran
      open_wave's own `audio_margin_sweep.py` live on this machine with
      the identical arguments as a second, independent check: it
      produced numerically identical output to `margin_sweep.py`, SNR
      values and delivered-counts matching at every single sigma. So the
      gap below isn't translation drift in `_phy.py`'s wrapping - it's
      that open_wave's own docstring summary doesn't match what its own
      script actually outputs today, on this machine, with its own
      documented default invocation (environment/numpy drift since
      "measured 2026-10-04", or the one-line summary was always a loose
      rounding - not determined, and out of this module's scope to dig
      into further).

      Followed up with a tightened sweep (100 trials, finer sigma steps
      bracketing each cliff, 50% point by linear interpolation between
      the two bracketing sigmas):

      | Mode | FEC | open_wave's docstring | Measured here (both scripts agree) |
      |---|---|---|---|
      | 0 (BPSK 600) | r1_4_k9 | -1 dB | -1 to -2 dB (100%→88%→67% over -0.6→-2.7dB) - close match |
      | 1 (BPSK 1200) | r1_2_k3 | 4.5 dB | **~1.75 dB** (58% at 2.0dB, 39% at 1.4dB) |
      | 2 (QPSK 1200) | r1_2_k3 | 7 dB | **~5.0 dB** (55% at 5.1dB, 31% at 4.5dB) |

      Mode 0 still matches closely; modes 1/2's 50% points are real,
      reproducible numbers on this machine (confirmed via the live
      cross-check above, and stable between the 24- and 100-trial runs -
      not noise averaging out as more trials were added, which is what
      ruled out "just needs more trials" as the explanation). Relative
      ordering still holds (mode 0 most noise-tolerant, then 1, then 2).
      Also confirmed, across every mode/sigma tested: `open_modem_rx`'s
      default quality `threshold` (0.4) never rejected a burst
      `decode_frames` could still recover, and never accepted one it
      couldn't - the block's default isn't costing anything here.
- [x] **Phase 2b — fragmentation and ACK/retry.** `_phy.py` gained
      `modulate_frame` (factored out of `build_burst`),
      `build_fragmented_bursts` (wraps `openwave_link.build_fragmented_frames`,
      one audio burst per fragment), `build_ack_burst` (wraps
      `build_ack_frame`), and `publish_keyed_burst` (the audio_out+ptt
      publish/timer logic shared by `open_modem_tx` and the new
      `ack_responder` block). `open_modem_tx` now tracks its own `seq`,
      auto-fragments anything over `MAX_PAYLOAD_LEN`, and (for
      single-frame sends only - matching the archived
      `phy_sim_loopback.grc`'s `str_to_pdu_0`'s own reasoning, a
      fragmented send has no one seq to retry against) drives
      `openwave_link.RetryManager` from a background polling thread
      (no external 'tick' message port needed, unlike the legacy embedded
      block - GNU Radio Python blocks can just use `threading` directly)
      exposed via new `ack_received` (in) and `delivery_failed` (out)
      message ports. `open_modem_rx` gained `ack_needed`/`ack_received`
      (out) ports and dispatch logic: an ACK frame routes to
      `ack_received` instead of `pdu_out`; a fragmented Data frame feeds
      `openwave_link.FragmentReassembler`, only reaching `pdu_out` once
      `reassembler.feed()` reports `'complete'`; a frame with
      `needs_ack(header)` publishes `ack_needed` after delivering it.
      Added a new block, `ack_responder` (`ack_needed` in ->
      `audio_out`/`ptt` out, mirroring `open_modem_tx`'s own shape so both
      fan into the same downstream `pdu_to_stream`/`ptt_control` in a
      flowgraph) - RX itself can't send, so something has to turn its
      "this needs acking" notification into a real keyed burst, the same
      role the legacy `ack_responder_0` embedded block played. Extended
      `examples/open_modem_loopback.grc` to request+close a real ACK loop
      every message (verified over 13s/3 messages: every `note_ack()`
      call resolved, zero retries needed, `pending_seq` clean at the end)
      and `examples/open_modem_ht.grc` to match (compile-checked only, via
      the same temporary-stub approach as Phase 4, then reverted). All new
      logic covered by QA tests exercising the real PHY round-trip, not
      mocks (fragmentation, ACK dispatch, retry-then-resolve, and
      give-up-and-report-delivery_failed). See the Open section above for
      a real limitation this surfaced (back-to-back fragment bursts).
- [x] **Phase 4 — example flowgraphs.** `examples/open_modem_loopback.grc`
      (software loopback, no hardware, modeled on
      `open_modem/open_wave/legacy/gnuradio/phy_sim_loopback.grc`) actually
      runs here and decodes a real burst end to end (TX -> `pdu_to_stream`
      -> RX -> Message Debug, confirmed `status: ok` with the correct
      payload/src_id/snr_db). `examples/open_modem_ht.grc` (live
      AIOC/Digirig: Audio Source/Sink via Phase 3's `radio_select`,
      `open_modem_tx`/`rx`, `ptt_control`) compiles and its generated
      module imports cleanly, but - unlike the loopback - can't be run or
      even `grcc`-compiled against real detection in this environment: it
      has neither a display nor an AIOC/Digirig attached, and
      `radio_select.pick()` executes for real at both flowgraph-construction
      time AND grcc's own variable-value validation, so compiling it here
      needed temporarily stubbing `radio_select.detect()` (reverted before
      finishing). Phase 5 is the first time this file gets validated for
      real.
- [x] **Phase 3 — radio autodetection helper.** Added
      `python/open_modem/radio_select.py`, porting `radio_stations.py`'s
      local-machine USB-ID detection (same reason as `_phy.py` - that
      script isn't one of `openwave`'s installable modules either, so it's
      a port, not an import). `detect()`/`pick()` return/raise exactly like
      the original; `qa_radio_select.py` exercises both the shape of
      `detect()`'s result and the "no interface attached" error path
      (this dev machine has neither an AIOC nor a Digirig, which is
      exactly the case that path is for).
- [x] **Found and fixed a real, silent GRC footgun while wiring Phase 4's
      live flowgraph:** a `dtype: enum` block parameter in a `.block.yml`
      does NOT accept an arbitrary expression typed into it - GRC silently
      falls back to the enum's *default* option if the given text isn't
      one of its declared `options:`, with no error. `ptt_control`'s
      `ptt_line` (and `open_modem_tx`/`rx`'s `port`) were `dtype: enum`
      and meant to sometimes be set to a computed expression
      (`station['ptt_line']` from Phase 3's autodetection) - every Digirig
      user would have silently gotten `ptt_control(..., 'dtr')` instead
      (the enum's default), keying the wrong line and never transmitting,
      with nothing in the UI or logs suggesting why. Changed all three to
      plain `dtype: string`, which (confirmed empirically - see
      `open_modem_ht.grc`'s own `station` variable comment for a related
      GRC-version-specific gotcha) correctly passes an expression through
      unquoted while still auto-quoting a plain literal like `mic` or
      `dtr`.
- [x] **Added `python/open_modem/pdu_to_stream.py`**, because the stock
      `pdu.pdu_to_tagged_stream` block (the obvious choice to turn
      `open_modem_tx`'s audio_out PDU into a stream for `pdu_to_stream`/an
      Audio Sink) writes an entire burst as one tagged packet in a single
      `work()` call, needing an output buffer sized to the longest burst -
      and on this machine GNU Radio's buffer allocator silently clamps ANY
      requested `maxoutbuf` down to 16384 items regardless of what's
      asked for ("Block (...) max output buffer set to 16384 instead of
      requested ..."), well under even a single-byte-payload mode 0 burst
      (~47000 samples on the mic port) - so `pdu_to_tagged_stream` drops
      the burst outright here. `pdu_to_stream` instead queues each PDU and
      drains it a `work()` call at a time (filling with silence when
      idle, matching a real continuous Audio Source/Sink and fixing a
      second bug this uncovered: `open_modem_rx`'s periodic burst-scan
      never ran at all without that steady trickle, since nothing ever
      crossed its 1-second new-samples threshold after a short burst with
      no continuous audio behind it) - correct regardless of this or any
      other machine's buffer ceiling. Whether the 16384 clamp is specific
      to this (likely sandboxed) environment or a real GNU Radio 3.10.9.2
      limit on real hardware is untested - Phase 5 will tell.
- [x] **Phase 2 — wired in the real open_wave PHY.** Added
      `python/open_modem/_phy.py`, a port of `audio_wav_test.py`'s
      `build_samples`/`decode_samples`/`mode_params` (open_wave's own
      proven-on-air test harness) onto only the modules `pip install -e`
      actually exposes (`openwave_link`/`openwave_modem`/`openwave_fec`/
      `openwave_audio`) - `audio_wav_test.py` itself isn't importable after
      an editable install (see README's "Dependency"). `open_modem_tx`
      calls `_phy.build_burst`, `open_modem_rx` ports `radio_listen.py`'s
      `Listener` rolling-buffer/burst-detect state machine onto GNU
      Radio's `work()` and calls `_phy.decode_burst`/
      `_phy.burst_length_samples`. QA tests now assert a real round-trip
      (`open_modem_tx`'s audio_out PDU decodes back to the original
      payload via `_phy.decode_burst`, and separately via a full
      `open_modem_rx._step()`), not just instantiation. Also fixed two
      bugs found while wiring this in: `self._logger` isn't a real
      attribute on GNU Radio Python blocks (it's `self.logger`), and the
      editable `open_wave` install needs `--break-system-packages` on this
      (Debian, PEP 668) system.
- [x] Scaffolded the OOT module (`gr_modtool newmod`), added the three
      block skeletons (`open_modem_tx`, `open_modem_rx`, `ptt_control`) with
      real message-port wiring (not stream-based placeholders), fixed a
      `gr_modtool add -l python` CMakeLists gap (new block `.py` files
      weren't being added to the `gr_python_install(FILES ...)` list - see
      `python/open_modem/CMakeLists.txt`), confirmed it builds, installs to
      a user prefix, imports, passes its QA tests, and resolves in GRC's
      block path via `local_blocks_path`.

## How to use this file

Same convention as `open_modem`'s own `TODO.md`: move Open → Done with a
one-line summary when a phase actually lands; new work belongs here unless
it's about `open_wave`'s own internal PHY behavior, which belongs in that
repo's TODO instead.
