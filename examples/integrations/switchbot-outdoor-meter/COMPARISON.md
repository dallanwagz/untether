# Learning from the maintainers: this build vs. HA Core's `switchbot`

This integration was written **from scratch, before reading Home Assistant Core's
implementation**, then graded by an independent reviewer against core's `switchbot`
integration and the `pySwitchbot` library. This file records what that comparison
taught us — the point of the exercise is to learn the maintainers' patterns, not
to ship a duplicate.

## Headline reality

**The W3400010 (`SwitchbotModel.IO_METER`, model bytes `'w'`/`'W'`) is already
fully supported by HA Core's `switchbot` integration** — it's listed in
`NON_CONNECTABLE_SUPPORTED_MODEL_TYPES` → `HYGROMETER`, decoded by pySwitchbot's
`process_wosensorth`. So the *real-world* PR-maximizing move is **not** a new
integration (core closes duplicates); it's to verify the device under the existing
`switchbot` integration and, if something's wrong, fix it in
[`home-assistant/core`](https://github.com/home-assistant/core/tree/dev/homeassistant/components/switchbot)
or [`pySwitchbot`](https://github.com/sblibs/pySwitchbot). This build is kept as a
*teaching* example of the passive-sensor pattern.

## Decode: independently correct ✔

The reviewer diffed our `protocol.py` against pySwitchbot byte-by-byte —
**identical**: temp source `mfr[8:11]`, decimal `& 0x0F /10`, integer `& 0x7F`,
sign `& 0x80`, humidity `& 0x7F`, battery from **service** data `[2] & 0x7F`, min
length `>= 11`. Independent RE landed exactly on the shipped decoder.

### …and one place we go *beyond* pySwitchbot

A live test (toggling the app's Temperature Unit while watching the advert) showed
the **display-unit flag is `mfr[7]` bit 3** (set = °C, clear = °F), tracking the
app toggle both directions. pySwitchbot instead reads `mfr[10]` bit 7 for its
`fahrenheit` field — which stayed **0 in both modes** on this display-less unit.
So pySwitchbot's `fahrenheit` is always-false here and the real flag is undecoded
upstream. Functionally moot for HA (the frontend converts units), but it's a small
real gap in the shipped parser — a candidate `pySwitchbot` issue/PR if confirmed
across more meter models.

## What we already got right (matches core)

- `local_push` + `connectable: false` + `dependencies: [bluetooth_adapters]` manifest.
- `runtime_data`-typed config entry alias.
- Idiomatic config flow: `async_step_bluetooth` → `set_unique_id` →
  `_abort_if_unique_id_configured` → `not_supported` abort → `_set_confirm_only`
  confirm; `async_step_user` enumerating `async_discovered_service_info(connectable=False)`.
- Correct entity device/state classes; battery as `DIAGNOSTIC`.
- `strings.json` referencing shared translation keys, not hardcoded text.
- HA-free, unit-tested parser; `quality_scale.yaml` with correct passive-device exemptions.

## What we changed after the review (applied)

| Fix | Why | Where |
|-----|-----|-------|
| **Mask the model byte's high bit** before matching (`chr(service_data[0] & 0x7F)`) | The high bit is SwitchBot's *encrypted* flag; raw `in (0x77, 0x57)` would reject a flag-set advert (0xF7/0xD7). Also corrected the wrong "upper/lower case of one byte" comment — `'w'` and `'W'` are distinct model chars. | `protocol.py` |
| **Suppress all-zero frames** (`0 °C / 0 % / 0 %` → `ParseError`) | pySwitchbot does this to avoid publishing spurious readings. | `protocol.py` |
| **Add an RSSI diagnostic sensor** (disabled by default) | Core ships an RSSI sensor for every device. | `sensor.py`, `coordinator.py` |
| **macOS `CONNECTION_NETWORK_MAC` fallback** in `DeviceInfo` | Core adds it so the device matches where the address isn't exposed as a BT connection. | `sensor.py` |
| **Device name from the model friendly name** (`Indoor/Outdoor Meter <id>`) | Core derives the name from the parser's `modelFriendlyName`, not an ad-hoc string. | `sensor.py` |
| Fixed humidity-range docstring (`& 0x7F` is 0–127, not 0–99) | Accuracy. | `protocol.py` |

## What we deliberately did NOT change (conscious, documented)

- **Parser stays inline** rather than a published PyPI lib. Core *requires* the
  protocol in a separately-versioned package (for SwitchBot that's `pySwitchbot`).
  This example keeps it inline because the whole point is to *show* the byte map;
  the SKILL's HACS↔Core delta already calls out "move parser to a lib" as a Core
  step. **For a genuinely new device, do this.**
- **Hand-built `PassiveBluetoothDataUpdate`** rather than `sensor-state-data`'s
  `SensorUpdate` + `sensor_update_to_bluetooth_data_update`. The latter is the
  blessed path for `govee_ble`/`xiaomi_ble`; we kept the explicit form because it's
  self-contained and readable for teaching. Note core's *own* switchbot uses
  neither (it runs an active coordinator) — so there's no single "correct" target.
- **No shared base entity** for three sensors — acceptable per the reviewer; core
  favors one for larger integrations.
- **Kept HACS artifacts** (`hacs.json`, `pytest.ini`, `custom_components/` layout,
  the `enable_custom_integrations` + D-Bus-history `conftest` shims). These are
  correct for a HACS/custom-component example; a **Core PR would delete them** (see
  `SKILL.md` → *HACS ↔ Core delta*).

## Verdict (reviewer)

Well-engineered, decode correct, **but not core-mergeable as a new integration** —
the device is already supported. Must-fixes for a hypothetical new device:
(1) don't duplicate core support, (2) parser in a published lib, (3) the model-byte
mask (now fixed), (4) drop HACS-only artifacts. The correctness fixes above are
genuine improvements regardless and have been applied.
