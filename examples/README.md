# Examples

Compile any of these with `grcc <file>.grc` (see the repo README's
"Examples" section for the `GRC_BLOCKS_PATH` env var needed on a
user-prefix install), then run the generated `<file>.py`.

- **`open_modem_loopback.grc`** — TX/RX/ACK round trip, no hardware, no
  channel impairment. The simplest "does this actually work" check.
- **`open_modem_noisy_loopback.grc`** — the same loop with an adjustable
  noisy channel (`--noise-sigma`/`-n`) in between, so you can watch
  delivery degrade, retries fire, and `delivery_failed` eventually trigger
  as noise increases. The live, GNU-Radio-native counterpart to
  `apps/margin_sweep.py`'s offline noise sweep. The Waveform Mode under
  test (`--mode-id`/`-m`) is a single shared Parameter that
  `open_modem_tx_0`, `open_modem_rx_0`, and `ack_responder_0` all
  reference - change it once and all three stay in sync. (Earlier
  revisions had each block carry its own copy; setting TX and RX to
  different modes independently doesn't just decode worse under noise, it
  fails outright even noise-free, since each mode modulates even its
  preamble differently - there's nothing for a mismatched RX to lock
  onto.)
- **`open_modem_constellation.grc`** — the same noisy-channel loop, with
  `open_modem_rx_0`'s actual demodulated symbols (post carrier/timing
  recovery, truncated to the real frame) fed to a QT GUI Constellation
  Sink via a live noise slider (not a CLI flag this time - drag it while
  watching the plot). Tight clusters at the mode's ideal points means a
  clean decode; a smeared ring or blob means you've found the cliff. The
  visual counterpart to `apps/margin_sweep.py`'s numbers and
  `open_modem_noisy_loopback.grc`'s console output. The symbol stream
  goes through `pdu_to_stream` (dtype `complex`, not the stock `PDU to
  Tagged Stream`) and then a `Throttle` (9600 items/s) before the sink -
  both load-bearing, not cosmetic; see `TODO.md` for the two real bugs
  (a dead-forever block, then a 168-million-samples-in-5-seconds runaway)
  that showed up without them.
- **`open_modem_ht.grc`** — the live station: a real AIOC/Digirig over USB
  audio, autodetected via `radio_select` (`--radio aioc`/`--radio digirig`
  to name one if more than one is attached). Needs real hardware and a
  display; see the repo README/TODO.md for what's and isn't validated
  yet. `--mode-id`/`-m`, `--station-id`/`-s`, `--dst-id`/`-d`, and
  `--tx-level`/`-l` are CLI flags, same idea as `open_modem_noisy_loopback.grc`'s
  shared `mode_id`. One real difference from the other three examples,
  though, not a bug: `open_modem_rx_0.mode_ids` is left at its default
  (`[]`, "try every mode the port fits"), not pinned to `[mode_id]` - a
  live station should be able to hear a peer transmitting in a different
  mode than this station's own TX default, unlike the self-talking-to-self
  loopback/constellation examples where TX and RX obviously must match.
