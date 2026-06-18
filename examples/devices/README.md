# Device library

One profile per reverse-engineered device, contributed by people who used the skill. This is the
part that grows with every use — **add yours** (copy [`../_TEMPLATE.md`](../_TEMPLATE.md), fill it
from real captures, add a row below, open a PR — see [`../../CONTRIBUTING.md`](../../CONTRIBUTING.md)).

The phase-by-phase teaching path lives in the [reference walkthrough](../README.md) (the
Rongtai/Infinity massage chair); concise per-device profiles live here.

| Device | Transport | Profile | Integration |
|--------|-----------|---------|-------------|
| Rongtai / Infinity "EVOLUTION" massage chair | BLE GATT (vendor svc 0xFFF0) | [rongtai-infinity-evolution-chair.md](rongtai-infinity-evolution-chair.md) (full bit map) · also the [reference walkthrough](../README.md) | [hass-infinity-chair](https://github.com/dallanwagz/hass-infinity-chair) |
| Atorch J7-C USB power meter | Dual: BLE GATT (svc 0xFFE0) + Classic SPP | [atorch-j7c-usb-meter.md](atorch-j7c-usb-meter.md) | atorch-ble / j7c_ha |
| Divoom TimeBox-mini (11×11 LED) | Classic SPP, RFCOMM ch4 (byte-stuffed) | [divoom-timebox-mini.md](divoom-timebox-mini.md) | none (protocol only) |
| Divoom Pixoo 16 (16×16 LED) | Classic SPP, RFCOMM ch2 (MiniToo transport) | [divoom-pixoo-16.md](divoom-pixoo-16.md) | none (protocol only) |
| Govee H5075 / H5104 thermo-hygrometers | **Passive BLE advertisement** (svc 0xEC88) | [govee-h5075-h5104.md](govee-h5075-h5104.md) | govee_ble (core) · [worked clone](../integrations/govee-passive-th/) |
| SwitchBot Indoor/Outdoor Meter (W3400010) | **Passive BLE advertisement** (svc 0xFD3D, model 'w') | [switchbot-w3400010-outdoor-meter.md](switchbot-w3400010-outdoor-meter.md) | switchbot (core) · [worked clone](../integrations/switchbot-outdoor-meter/) |
| _your device here_ | | | |
