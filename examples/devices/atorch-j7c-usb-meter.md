<!-- Contributed as a test pass of the skill. Findings re-derived from the app, then graded
against the existing atorch_ble integration (the control). -->

# Atorch J7-C USB power meter

- **Vendor app:** `com.tang.etest.e_test` ("E_Test")
- **HA integration:** [`atorch-ble`](https://github.com/dallanwagz?tab=repositories) / `j7c_ha` (the control for this pass)
- **Contributed by:** Claude (skill test pass) · 2026-06-17

## Transport

The app is **dual-transport** — `Model/UUIDs.java` defines both BLE (service `ffe0`, notify
`ffe1`) and Classic SPP (`00001101`), and `Model/BLEService.java` implements both a `BluetoothGatt`
path and a `BluetoothSocket` (SPP) path. At runtime E_Test drives the J7-C over **SPP**; Home
Assistant drives it over **BLE** (HA is BLE-only). The meter is dual-mode, so both work — but see
the type-byte gotcha below.

How confirmed: decompiled `UUIDs.java` (both UUID sets present), and a live HA capture connects over
BLE on `ffe0/ffe1`.

## Connection (BLE, for HA)

- Service `0000ffe0-…`, notify characteristic `0000ffe1-…` (status stream).
- Command path is the same characteristic family; the meter mostly streams unprompted.

## Frame format

Atorch frames are `FF 55 <dir> <type> … <checksum>`. The decoded USB-meter payload is 36 bytes.

- magic `FF 55`, direction `01` (from device), **type `0x03` = J7-C USB meter** (BLE).
- checksum (last byte): `(sum(payload[0x03:0x23]) & 0xFF) ^ 0x44`.

## Status frame — byte map (big-endian fields)

Re-derived from `MainActivity.textValue(byte[] bArr)` (USB section) and confirmed against the
control's `decode_usb_meter`:

| Bytes | Field | Scale |
|---|---|---|
| 4–6  | voltage | /100 → V |
| 7–9  | current | /100 → A |
| 10–12 | capacity | mAh |
| 13–16 | energy | /100 → Wh |
| 17–18 | USB D+ voltage | /100 → V |
| 19–20 | USB D− voltage | /100 → V |
| 21–22 | temperature | °C |
| 23–24 (hours, u16), 25 (min), 26 (sec) | duration | h/m/s |

### Golden frame (real capture)

```
ff5501030003860000d2000d6d00000952011901180028000409163c0c800000032000d8
        ^^ ^^                                                          ^^ checksum
        || type 0x03 (USB)
        | dir 01
 voltage  000386=902 -> 9.02 V    current 0000d2=210 -> 2.10 A    capacity 000d6d=3437 mAh
 energy   00000952=2386 -> 23.86 Wh   D+ 0119 -> 2.81 V   D- 0118 -> 2.80 V   temp 0028 -> 40 °C
 duration hours 0004=4, min 09=9, sec 16=22 -> 4:09:22
```

## Home Assistant transition

The byte map became `atorch_ble`'s pure decoder (`decode_usb_meter`), e.g.:

```python
voltage_v       = int.from_bytes(payload[0x04:0x07], "big") / 100.0
current_a       = int.from_bytes(payload[0x07:0x0A], "big") / 100.0
capacity_mah    = int.from_bytes(payload[0x0A:0x0D], "big")
energy_wh       = int.from_bytes(payload[0x0D:0x11], "big") / 100.0
voltage_dplus_v = int.from_bytes(payload[0x11:0x13], "big") / 100.0
voltage_dminus_v= int.from_bytes(payload[0x13:0x15], "big") / 100.0
temperature_c   = int.from_bytes(payload[0x15:0x17], "big")
duration_s      = int.from_bytes(payload[0x17:0x19],"big")*3600 + payload[0x19]*60 + payload[0x1A]
```

Each field → a sensor; power is derived coordinator-side as `voltage_v * current_a`.

## Gaps & gotchas

- **Transport-dependent type byte (the catch of this pass):** E_Test decodes its **SPP** frames in
  a branch keyed on `bArr[3] == 2`, but the meter's **BLE** frame (what HA reads) carries type
  `0x03`. The *field offsets matched exactly* across both — only the type byte differs. Lesson:
  trust the transport HA actually uses for the header/type, not just the app's branch condition.
- **Duration quirk:** E_Test reads the duration "hours" as a **2-byte** big-endian counter
  (`u16(0x17:0x19)`) rather than a days+hours split. The control deliberately mirrors this so HA
  matches the device's own display — a "bug" that's correct-by-bug-for-bug.
- **Single BLE central** and the recurring reconnect/slot stalls — see the reference walkthrough's
  reliability example.

## Grade vs control

All 8 USB-meter fields' offsets + scales re-derived from the app **match `atorch_ble` exactly**,
including the quirky duration. The only divergence is the transport-dependent type byte (above),
which is itself a clean illustration of the skill's #1 principle.
