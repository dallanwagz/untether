<!--
Device profile template. Copy to examples/devices/<vendor>-<device>.md and fill from REAL
captures. Delete these comments and any sections that genuinely don't apply (say why). Keep it
faithful — label guesses, document unknowns, redact secrets.
-->

# <Vendor> <Device> (<model>)

- **Vendor app:** `<android.package.name>` (and/or iOS app name)
- **HA integration:** <link to HACS repo / ESPHome config, or "not published">
- **Contributed by:** <name/handle> · <date>

## Transport

Classic SPP **or** BLE GATT — and **how you confirmed it** (decompiled socket/UUID type, iOS
device-picker showing UUIDs vs MAC, a GATT scan, bonding state, …). Note the HA host approach used
(Bluetooth proxy / local adapter / the [`untether_spp`](../components/untether_spp/) ESP32 SPP↔TCP
bridge for Classic devices).

## Connection

- **BLE:** service UUID, **command** characteristic (write), **status/notify** characteristic;
  any service to ignore (OTA/DFU). Address note (static vs rotating/RPA).
- **SPP:** RFCOMM channel, security (secure/insecure), ERTM on/off.

## Command frame

```
<frame layout, e.g.  SOI VOI <id> <checksum> EOI  =  F0 83 <id> <cksum> F1>
checksum = <formula>
```

### Command catalog

| Command | messageId | notes (gating, toggle, etc.) |
|---|---|---|
| power | 1 | toggle |
| … | … | … |

## Status frame

One or more **golden frames** (full hex) + what they mean:

```
<idle>     f0 .. f1
<running>  f0 .. f1
```

### Byte map

| Byte | Meaning |
|---|---|
| b1 | … |
| … | … |

## Home Assistant transition

The key snippets the findings became — `build_frame()`, `parse_status()`, and how a finding maps
to a button / sensor / service. Short, real excerpts.

```python
def build_frame(message_id): ...
def parse_status(data): ...
```

## Gaps & gotchas

What the device does **not** report (command-only positions, set-only levels, indistinguishable
presets), single-central/slot constraints, reconnect quirks — anything that saves the next person
time.
