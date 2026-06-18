# Govee BLE (RE dry-run) — Home Assistant integration

The **capstone** of the Govee reverse-engineering dry run: a Home Assistant integration for Govee
passive-BLE thermo-hygrometers (**H5075**, **H5104**), built to Core-PR quality from a byte map that
was reverse-engineered from the Govee Android app **and validated on live hardware against the
device LCD and the shipping HA Core `govee_ble` integration**.

> These models already have native HA Core support. This integration is a *demonstration* of the
> end state the [untether](https://github.com/dallanwagz/untether) skill aims for —
> a pure, unit-tested protocol module wired into the passive-BLE coordinator pattern — not something
> to install alongside the official integration.

## What's here (and why it's structured this way)

| File | Role |
|------|------|
| `custom_components/govee_ble_re/protocol.py` | **Pure decode logic, no HA imports.** The reusable, PR-able spec. |
| `tests/test_protocol.py` | **Golden-frame tests** — every frame is a real capture cross-checked vs the LCD / HA Core. |
| `__init__.py` | `PassiveBluetoothProcessorCoordinator` fed by `protocol.parse_advertisement`; `runtime_data`. |
| `sensor.py` | `SensorEntityDescription`s (temp / humidity / battery) via a passive data processor. |
| `config_flow.py` | Bluetooth auto-discovery + manual picker; `unique_id` = address; abort-if-configured. |
| `manifest.json` | `bluetooth` matchers (`connectable: false`), `iot_class: local_push`, `quality_scale: bronze`. |
| `quality_scale.yaml` | Bronze rules, each done / todo / exempt. |
| `strings.json` + `translations/en.json`, `hacs.json` | UI strings; HACS install metadata. |

## The decode (validated)

Both models broadcast a 3-byte packed temp+humidity word: `temp = (v // 1000) / 10`,
`hum = (v % 1000) / 10`, top bit = temperature sign; battery is a separate byte (`& 0x7F`).
- **H5075** — manufacturer record `0xEC88`, packed value at `data[1:4]`, battery `data[4]`.
- **H5104** — manufacturer record `0x0001` (+ a `0xEC88` service-UUID), packed value at `data[2:5]`,
  battery `data[5]`.

Golden frames (live, validated):
- `GVH5075_DC1B` `0003ed733e00` → **25.7 °C (78.3 °F) / 39.5 % / 62 %** (matched the LCD).
- `GVH5104_6D7B` `010104a4652b` → **30.4 °C (86.72 °F) / 22.9 % / 43 %** (matched HA Core exactly).

## Run the tests

```sh
python3 -m venv .venv && .venv/bin/pip install pytest
.venv/bin/python -m pytest tests/ -q     # 6 passed
```

## Status — honest

- ✅ **`protocol.py` is complete and unit-tested** against real golden frames (the durable artifact).
- 🟡 **The HA-coupled files follow the documented Core passive-BLE pattern but have not been run
  against a Home Assistant dev checkout** (no HA env here). Before a real Core PR: run
  `hassfest` + `ruff` + `mypy`, add `tests/test_config_flow.py` to 100 %, submit the docs
  (home-assistant.io) and brand/logo (home-assistant/brands) PRs. The HACS↔Core delta is in the
  skill's `SKILL.md` Phase 5.
- **Out of scope:** H5127 (presence/motion) — different format/transport; see the dry-run notes.
