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
  `apps/margin_sweep.py`'s offline noise sweep.
- **`open_modem_ht.grc`** — the live station: a real AIOC/Digirig over USB
  audio, autodetected via `radio_select`. Needs real hardware and a
  display; see the repo README/TODO.md for what's and isn't validated yet.
