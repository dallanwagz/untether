# Worked examples

Real artifacts from reverse-engineering an Infinity / Rongtai massage chair (vendor app
`rongtai.infinity`) into a Home Assistant integration, showing how each RE finding turned into a
concrete HA action or sensor. They map onto the phases in [`../SKILL.md`](../SKILL.md).

| # | File | Phase | The transition it shows |
|---|------|-------|--------------------------|
| 1 | [01-static-decompile-to-command.md](01-static-decompile-to-command.md) | 1, 5 | Decompiled Java frame builder → `build_frame()` → an HA **button** |
| 2 | [02-gatt-enumeration.md](02-gatt-enumeration.md) | 0, 3 | `bleak` GATT dump → the command + notify characteristic UUIDs |
| 3 | [03-status-frame-decode.md](03-status-frame-decode.md) | 4 | Live one-variable diffs → byte map → `parse_status()` → **sensors** |
| 4 | [04-ha-integration-wiring.md](04-ha-integration-wiring.md) | 5 | Connect via Bluetooth **proxies**, buttons, `send_command` service |
| 5 | [05-reliability-watchdog.md](05-reliability-watchdog.md) | 6 | Diagnosing recurring stalls: advertising? free slots? → auto-recover |

The single biggest lesson lives across #1 and #2: the decompiled Android app spoke **Bluetooth
Classic SPP** and never actually worked — the device was really driven over **BLE GATT** (the iOS
app's path). The SPP command catalog from #1 was correct, but it had to be sent down the BLE pipe
discovered in #2. *Static gave the spec; dynamic gave the truth.*

## Growing device library

The docs above are the phase-by-phase **reference walkthrough** (one device). Concise per-device
profiles from everyone who uses the skill collect in **[`devices/`](devices/)** — that's the part
that grows with each use. Add yours: copy [`_TEMPLATE.md`](_TEMPLATE.md) → `devices/<vendor>-<device>.md`,
fill it from real captures, add a row to [`devices/README.md`](devices/README.md), and open a PR.
See [`../CONTRIBUTING.md`](../CONTRIBUTING.md).
