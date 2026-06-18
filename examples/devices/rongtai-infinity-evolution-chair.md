<!-- The device behind the reference walkthrough (examples/01–05). This profile adds the full,
     bit-by-bit status decode + the pure parse_status() it became — the painstaking core of a
     connectable-GATT decode, kept as example code for the next person/agent. -->

# Rongtai / Infinity "EVOLUTION" massage chair (BLE GATT)

- **Vendor app:** `rongtai.infinity` (Android)
- **HA integration:** `hass-infinity-chair` (shipped HACS custom integration)
- **Contributed by:** Claude (skill) · 2026-06-17

> This is the device behind the **[reference walkthrough](../README.md)** (examples/01–05). It's a
> **connectable BLE GATT** device — you connect, write a command characteristic, and subscribe to a
> notify characteristic that streams a 17-byte status frame. The interesting part, and what this
> profile captures, is the **status frame decoded bit-by-bit** (validated against the chair's panel,
> one variable at a time).

## Transport

**BLE GATT.** Confirmed the hard way — this is the skill's headline trap: the Android app's code
spoke **Bluetooth Classic SPP** and never worked; the device is actually driven over **BLE GATT**
(the iOS app's path). Static analysis of the Android app gave a correct *command catalog* that went
down the wrong pipe until a GATT scan + live control proved BLE was the working transport.
**Host:** any HA Bluetooth proxy (ESPHome/Shelly) or local adapter.

## Connection

- **Service** `0000fff0-…` (vendor `0xFFF0`).
- **Command** characteristic (write): `0000fff1-0000-1000-8000-00805f9b34fb`.
- **Status / notify** characteristic: `0734594a-a8e7-4b1a-a6b1-cd5243059a57` (17-byte frames).
- **Single BLE central** — keep the vendor app off the link while HA holds it.

## Command frame

```
F0 83 <messageId> <checksum> F1            (5 bytes)
checksum = (~(0x83 + messageId)) & 0x7F
```
Golden command frames: `power(1)` → `f0 83 01 7b f1` · `shiatsu(34)` → `f0 83 22 5a f1` ·
`zero_gravity(112)` → `f0 83 70 0c f1`.

### Command catalog (friendly name → messageId)

| Command | id | Command | id | Command | id |
|---|---|---|---|---|---|
| power (toggle) | 1 | knead | 32 | airbag_auto | 68 |
| auto_recover | 16 | knock | 33 | zero_gravity | 112 |
| auto_stretch | 17 | shiatsu | 34 | session_10min | 80 |
| auto_relax | 18 | tap | 35 | session_20min | 81 |
| auto_pain_recovery | 19 | knead_knock | 36 | session_30min | 82 |
| auto_upper_body | 20 | heat | 39 | | |
| auto_lower_body | 21 | | | | |

Gating: manual techniques (`knead`…`knead_knock`) only take effect **while the chair is running**;
`power`, `zero_gravity`, and pad-move work while idle. `power` also stops a running program.

## Status frame — the full bit-by-bit map

17 bytes, `F0 b1..b15 F1` (indices: `data[0]=F0` … `data[16]=F1`). Every field below was validated
against the chair's own panel, one variable at a time.

| Byte | Bits | Field | Decode |
|---|---|---|---|
| b1 | `0x40` | powered | `bool(data[1] & 0x40)` |
| b1 | `(>>3)&7` | technique/MODE | 1 kneading · 2 knocking · 3 sync · 4 tapping · 5 shiatsu |
| b2 | `0x40` | heat | `bool(data[2] & 0x40)` |
| b2 | `(>>2)&7` | manual speed | 1..6 (live; running only) |
| b2 | `&0x03` | roller width | 1 narrow · 2 medium · 3 wide (live; running only) |
| b3 | `&0x07` | airbag strength | 0 off, 1..5 |
| b3 | `0x40` | ionizer | `bool(data[3] & 0x40)` |
| b4 | `(>>5)` | massage part/scope | 1 whole · 2 partial · 3 point |
| b4/b5 | `((b4&0x1F)<<7)\|(b5&0x7F)` | time remaining (s) | running only |
| b6 | `(>>5)` | foot-roller level | 0 off, 1..3 |
| b7 | byte | run state | 0 idle · 1 resetting · 2 ready · 3 running |
| b8 | byte | roller vertical position | `0x20` waist … `0x2C` neck → 0–100% (running only) |
| b10 | `0x40` | zero gravity | `bool(data[10] & 0x40)` |
| b12 | bits | airbag zones | `0x10` arm&shoulder · `0x08` back&waist · `0x04` leg&foot · `0x20` buttock (`0x40` = back/roller active, **not** a zone) |
| b13 | byte | active program | program # = `b13 >> 2`; `0x05` recover, `0x09` stretch, `0x0D` relax, `0x11` pain-recovery, `0x15` upper, `0x19` lower, `0x1C/0x1D` manual, `0x2D` 3D |
| b14 | byte | 3D strength level | 1..5 |

### Golden status frames (real captures)

```
idle      f0 05 03 00 09 30 00 00 2b 00 00 00 03 00 05 0b f1   run_state=idle, powered, program=recover-id idle
running   f0 45 27 02 44 57 00 03 2b 00 20 00 41 15 03 4f f1   powered, running, zero-gravity, airbag zones, 3D str=3
recover   f0 4d 29 02 2d 6f 10 03 2b 00 09 00 43 05 03 59 f1   running 'recover' program (b13=0x05), arm&shoulder airbag
lower     f0 4d 25 02 4d 70 10 03 21 00 00 00 43 19 01 3d f1   running 'lower_body' (b13=0x19), roller near waist (b8=0x21)
```

## Home Assistant transition

The byte map became `hass-infinity-chair`'s pure, unit-tested `protocol.py` — the durable artifact.
Each decoded field → a sensor/binary-sensor; each command → a button; a generic `send_command`
service fires any messageId. The full decoder (this is the "great example code" — a complete
connectable-GATT decode):

```python
_SOI, _EOI, _VOI = 0xF0, 0xF1, 0x83
_TECHNIQUES = {1: "kneading", 2: "knocking", 3: "sync", 4: "tapping", 5: "shiatsu"}
_WIDTHS = {1: "narrow", 2: "medium", 3: "wide"}
_PARTS = {1: "whole", 2: "partial", 3: "point"}
_RUN_STATES = {0: "idle", 1: "resetting", 2: "ready", 3: "running"}
_PROGRAM_NAMES = {0x05: "recover", 0x09: "stretch", 0x0D: "relax", 0x11: "pain_recovery",
                  0x15: "upper_body", 0x19: "lower_body", 0x1C: "manual", 0x1D: "manual", 0x2D: "3d"}
_ROLLER_MIN, _ROLLER_MAX = 0x20, 0x2C

def build_frame(message_id: int) -> bytes:
    checksum = (~(_VOI + message_id)) & 0x7F
    return bytes([_SOI, _VOI, message_id, checksum, _EOI])

def parse_status(data: bytes):
    if len(data) != 17 or data[0] != _SOI or data[-1] != _EOI:
        return None
    run = data[7]; running = run == 3; airbag = data[12]
    # roller position / speed / width are LIVE readings — surface only while running
    speed = ((data[2] >> 2) & 0x07) if running else None
    width = _WIDTHS.get(data[2] & 0x03) if running else None
    time_remaining = (((data[4] & 0x1F) << 7) | (data[5] & 0x7F)) if running else None
    roller = max(0, min(100, round((data[8]-_ROLLER_MIN)*100/(_ROLLER_MAX-_ROLLER_MIN)))) if running else None
    return {
        "powered": bool(data[1] & 0x40),
        "running": running,
        "run_state": _RUN_STATES.get(run),
        "program": _PROGRAM_NAMES.get(data[13]),
        "technique": _TECHNIQUES.get((data[1] >> 3) & 0x07),
        "heat": bool(data[2] & 0x40),
        "ionizer": bool(data[3] & 0x40),
        "strength": data[14],
        "airbag_strength": data[3] & 0x07,
        "time_remaining": time_remaining,
        "roller_position": roller,
        "speed": speed,
        "width": width,
        "foot_roller": data[6] >> 5,
        "part": _PARTS.get(data[4] >> 5),
        "zero_gravity": bool(data[10] & 0x40),
        "airbag_arm_shoulder": bool(airbag & 0x10),
        "airbag_back_waist": bool(airbag & 0x08),
        "airbag_leg_foot": bool(airbag & 0x04),
        "airbag_buttock": bool(airbag & 0x20),
    }
```

## Gaps & gotchas (honest protocol limits)

- **Manual technique (MODE) is not reliably reported** — kneading and tapping produce *identical*
  frames, so the live "technique" field can't always distinguish them.
- **Live value vs. setting:** roller position, speed, and width are *live motion readings* (they
  oscillate while some techniques run), so they're only surfaced **while a program is running** —
  idle frames carry defaults/garbage in those bytes.
- **3D presets aren't individually distinguishable:** 3D-1/2/3 all report program id `0x2D`.
- **Roller position is read-only telemetry** — the chair moves but there's no "go to position"
  command; you only observe `b8`.
- **The wire frame ≠ the payload:** every command is wrapped `F0 … F1` with the `(~(0x83+id))&0x7F`
  checksum — sending the raw messageId does nothing.
