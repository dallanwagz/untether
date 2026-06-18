<!-- Contributed from a full run of the skill (static + dynamic, Claude-driven) against a SwitchBot
     Indoor/Outdoor Meter, whose native HA Core integration (`switchbot` + pySwitchbot) is a published
     "answer key". The library's second PASSIVE-ADVERTISEMENT profile (after Govee). -->

# SwitchBot Indoor/Outdoor Meter (W3400010, "WoIOSensorTH") — passive BLE advertisement

- **Vendor app:** `com.theswitchbot.switchbot` (v9.28; "SwitchBot" on iOS)
- **HA integration:** native HA Core [`switchbot`](https://www.home-assistant.io/integrations/switchbot/)
  (+ [`pySwitchbot`](https://github.com/sblibs/pySwitchbot) parser, `SwitchbotModel.IO_METER`).
  A worked, independently-written clone (built before reading core) with passing golden-frame +
  config-flow tests lives in
  [`examples/integrations/switchbot-outdoor-meter/`](../integrations/switchbot-outdoor-meter/).
- **Contributed by:** Claude (skill run) · 2026-06-17

> **Passive advertisement sensor** (like the Govee profile, unlike the rest of the library). The meter
> **broadcasts** temperature/humidity/battery in its BLE advertisement — HA never connects
> (`connectable: false`). No command frame, no GATT write, no notify subscription. The whole
> integration is: match the advertisement → decode manufacturer + service data → publish sensors.
> The device has **no display**, so the operator-in-the-loop cross-check came from the *vendor app's*
> reading, not the device.

## Transport

**Passive BLE advertisement (broadcast).** Confirmed four ways:
- a live passive scan (`bleak`, macOS) decodes temperature/humidity/battery purely from advertisements —
  no pairing, no connection;
- pySwitchbot maps service-data byte `0x77`/`0x57` (`'w'`/`'W'`) → `SwitchbotModel.IO_METER` and decodes
  it from the advertisement;
- the decompiled vendor app's stored-history parser (`IMeterDataHandler.parseSampleData`) uses the
  **same** field encoding (masks/sign/÷10) as the advertisement;
- adding the device in the app needs a one-time pairing-mode button press, but normal reads (app *and*
  HA) come from the broadcast — no held connection.

The device *also* exposes a GATT server for configuration/history/OTA (service
`cba20d00-224d-11e6-9fb8-0002a5d5c51b`, write `cba20002…`, notify `cba20003…`) — **not needed** for
reading temperature/humidity/battery and unused by HA for this model.

**HA host:** any Bluetooth proxy (ESPHome/Shelly) or local adapter — passive scanning only.

## Connection / discovery keys

No connection. Discovery + decode key on:
- **manufacturer company id** `0x0969` (2409)
- **16-bit service UUID** `0xFD3D` (full `0000fd3d-0000-1000-8000-00805f9b34fb`)
- **service-data model byte** `service_data[0] == 0x77` (`'w'`) — some units broadcast `0x57` (`'W'`).
  *(Note: `company_id + service_uuid` alone matches **every** SwitchBot product; the model byte is what
  pins it to the Outdoor Meter — see Gaps.)*

The real BLE MAC is embedded in the **first six manufacturer-data bytes** (big-endian, exactly as the
vendor app's *Device Info → BLE MAC* shows it). macOS/iOS hide the MAC behind a CoreBluetooth UUID, so
read it from the advert payload (or from Android).

## Status frame = the advertisement (golden frames, hardware-verified)

Temperature/humidity sit in the **manufacturer data**; battery sits in the **service data**.

```
manufacturer data (company 0x0969 stripped, 12 bytes):
  [0:6] BLE MAC (big-endian)
  [6]   rolling sequence counter (increments every advert)        [Verified]
  [7]   bit3 = display unit (1=°C, 0=°F); other low bits vary     [bit3 Verified (tracks app toggle); other bits 0x0f vs 0x0b across units — bit2 differs, undecoded]
  [8]   bits[3:0] = temperature 0.1°C decimal                     [Verified]
  [9]   bit7 = sign (1=+, 0=−); bits[6:0] = integer °C            [Verified]
  [10]  bit7 = pySwitchbot's `fahrenheit` field (always 0 here);  [Verified humidity; flag never set on this model]
        bits[6:0] = humidity %
  [11]  0x00 constant                                             [Unknown]
service data (UUID 0xFD3D, 3 bytes):
  [0]   model byte (0x77 'w' / 0x57 'W')
  [1]   0x00
  [2]   bits[6:0] = battery %                                     [Verified]
```

Decode:
```
temp_c = (±1) * ((mfr[9] & 0x7F) + (mfr[8] & 0x0F)/10)     # sign = mfr[9] & 0x80
hum_%  =  mfr[10] & 0x7F
batt_% =  svc[2]  & 0x7F
```

**Golden frames (real captures, cross-checked against the SwitchBot app + pySwitchbot):**
```
unit C2:E7:7A:00:00:01 (on the desk)
  mfr 0x0969 = c2e77a000001 0e 0f 07 9a 20   svc 0xFD3D = 77 00 c5
  temp_data 07 9a 20 -> 26.7°C / 32% / batt 69%        [== app display 28.1°C/31% as it settled; firmware V0.4]

warming test (operator cupped/breathed on the sensor — ONE-VARIABLE temp+humidity rise):
  seq  temp_data  decoded
  0x14 05 9b 3d   27.5°C 61%        # integer byte 9b->9e tracks 27->30, decimal nibble matches,
  0x19 00 9d 3d   29.0°C 61%        # humidity 0x3d=61 from breath, battery unchanged (69%)
  0x1f 05 9e 3d   30.5°C 61%

negative-sign path (same-model sibling D5:DC:53:00:00:02, in a freezer):
  mfr 0x0969 = d5dc53000002 89 0f 01 11 46   svc 0xFD3D = 77 00 53
  temp_data 01 11 46 -> mfr[9]=0x11 bit7=0 (negative) -> −17.1°C / 70% / batt 83%

display-unit flag (same unit C2:E7:7A:00:00:01; app Temperature Unit toggled):
  app °C -> mfr[7]=0x0f (bit3 set)    c2e77a000001 70 0f 05 9b 1e 00 / 7700c5
  app °F -> mfr[7]=0x07 (bit3 clear)  c2e77a000001 68 07 02 9b 1d 00 / 7700c5   (app showed 81.6°F)
  tracked the toggle BOTH ways; mfr[10] bit7 stayed 0 throughout.
```

## Home Assistant transition

The byte map becomes a pure, dependency-free `protocol.parse()` feeding a
`PassiveBluetoothProcessorCoordinator` → temperature/humidity/battery sensors (full integration, all
gates green — `ruff`/`mypy`/20 `pytest` incl. config-flow 100% — in
[`examples/integrations/switchbot-outdoor-meter/`](../integrations/switchbot-outdoor-meter/)):
```python
def parse(manufacturer_data: bytes, service_data: bytes) -> MeterAdvertisement:
    if not is_outdoor_meter(service_data):          # service_data[0] in (0x77, 0x57)
        raise ParseError(...)
    temp_lo, temp_hi, humidity_byte = manufacturer_data[8:11]
    sign = 1 if temp_hi & 0x80 else -1
    temperature = round(sign * ((temp_hi & 0x7F) + (temp_lo & 0x0F) / 10), 1)
    humidity = humidity_byte & 0x7F
    battery = service_data[2] & 0x7F if len(service_data) >= 3 else None
    return MeterAdvertisement(
        address=mac_from_manufacturer_data(manufacturer_data),  # mfr[0:6], big-endian
        temperature=temperature, humidity=humidity, battery=battery,
        sequence=manufacturer_data[6], fahrenheit_display=bool(humidity_byte & 0x80),
    )
```
Each becomes a `SensorEntityDescription` (temperature °C / humidity % / battery % diagnostic) on a
`PassiveBluetoothProcessorEntity`; the MAC becomes the config-entry `unique_id` and the `DeviceInfo`
Bluetooth connection.

## Validation against the "answer key"

Graded against the merged HA Core decoder (**pySwitchbot 2.2.0**, `process_wosensorth`) and the
**vendor app** on live hardware:
- pySwitchbot run on our captured frame returned `temp 26.7/28.x, humidity, battery 69, model 'w'
  IO_METER` — **identical** to the hand-decode;
- the SwitchBot app's device page showed **28.1 °C / 31 %** at the same instant the passive scan
  decoded **28.1 °C / 31 %**, and *Firmware & Battery* showed **69 %** == `svc[2] & 0x7F` — exact match;
- the app's own decompiled `IMeterDataHandler` uses the identical encoding (`& 0x7F` integer, nibble
  `/10`, `& 0x80` sign, `& 0x7F` humidity).

Four-way agreement: hand-decode == pySwitchbot == vendor app display == app source.

## Gaps & gotchas

- **Multiple same-model units = an attribution trap.** Three Outdoor Meters (all model byte `0x77`) and
  other SwitchBot gear were broadcasting at once. `company_id + service_uuid` matches them all; the
  first one seen is **not** necessarily "yours." Pin the target by **RSSI + the embedded MAC**, and
  confirm against the vendor app's *Device Info → BLE MAC* (or, where present, the device display).
  Documented per *(model × unit)*: a negative seen on one unit says nothing about another.
- **No display on this model.** The usual operator screen cross-check is unavailable — use the **app's**
  reading as ground truth instead. Plan for this when the device is a bare outdoor probe.
- **Battery lives in the *service* data, temperature/humidity in the *manufacturer* data** — two
  different advert fields. Easy to miss if you only decode one.
- **`mfr[6]` is a sequence counter, not a sensor.** It increments every advertisement (proved during
  the warming series); don't mistake it for a reading.
- **Display-unit flag is `mfr[7]` bit 3, NOT `mfr[10]` bit 7.** Toggling the app's *Temperature Unit*
  (Profile ▸ Preferences — an account-wide app preference) flips `mfr[7]` bit 3 on the wire (`0x0f`↔
  `0x07`, set = °C, clear = °F), confirmed by toggling **both directions** and re-reading. So even
  though the W3400010 has no screen, the app's unit preference **is** written to the device and
  broadcast. Meanwhile `mfr[10]` bit 7 — the field **pySwitchbot decodes as `fahrenheit`** — stayed
  `0` in *both* modes, so on this model pySwitchbot's `fahrenheit` is always-false and the real unit
  flag (`mfr[7]` bit 3) is **undecoded by pySwitchbot/HA**. HA ignores units anyway (the frontend
  converts), so this is a fidelity finding, not a functional gap — but it corrects the obvious
  assumption that `mfr[10]` bit 7 is the unit flag.
- **App add-flow needs a one-time pairing-mode press** (hold the button ~2 s until the light flashes
  white) — but that's only to register the device in the app; passive reads (app and HA) never need it.
