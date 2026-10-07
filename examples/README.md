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
- **`open_modem_ht.grc`** — the live station: a real AIOC/Digirig over USB
  audio, autodetected via `radio_select`. Needs real hardware and a
  display; see the repo README/TODO.md for what's and isn't validated yet.
