# untether-bt

**A Bluetooth Swiss-army-knife for reverse engineering, troubleshooting, and engineering — with first-class Bluetooth *Classic* (RFCOMM/SPP) support the BLE-only ecosystem lacks.**

The modern Bluetooth stack (`bleak` → Home Assistant → ESPHome `bluetooth_proxy`) is **BLE-only by design** — `bleak` closed Classic support as *wontfix*. So a Bluetooth **Classic SPP** device (countless LED panels, meters, serial gadgets, massage chairs…) has no first-class path to a modern host or to Home Assistant. `untether-bt` fixes that, and gives you the protocol primitives you'd otherwise hand-roll.

> Part of the [untether](https://github.com/dallanwagz/untether) project (the methodology + the `untether_spp` ESP32 firmware). This is the host-side Python library.

## Install

```sh
pip install untether-bt           # core (no heavy deps)
pip install "untether-bt[ble]"    # + bleak, for GATT/LE work
```

## Reach a Classic-SPP device from anywhere

Host BLE stacks can't speak RFCOMM/SPP. Flash an ESP32 with the companion [`untether_spp`](https://github.com/dallanwagz/untether/tree/main/components/untether_spp) firmware (it RFCOMM-connects to the device and serves the byte stream over TCP), then:

```python
from untether_bt import SppBridge, DIVOOM_NEWMODE

with SppBridge("192.168.1.50", 8888, framing=DIVOOM_NEWMODE) as dev:
    dev.send_frame(0x74, b"\x32")        # set brightness 50 (framed: 01 04 00 74 32 aa 00 02)
    for f in dev.request(0x46):          # send a query, collect replies
        print(f.type, f.args.hex())
```

`AsyncSppBridge` is the asyncio twin (for Home Assistant coordinators). The same client also works against `socat`/`ser2net` over `/dev/rfcommN` on a BlueZ host.

## The framing/codec engine

Many BT-serial protocols wrap payloads as `SOI | LEN16 | body | CRC16 | EOI`, sometimes byte-stuffed. `Framing` captures the whole family, with hardened resync on the inbound parser:

```python
from untether_bt import Framing, Stuffing, DIVOOM_NEWMODE, DIVOOM_STUFFED

DIVOOM_NEWMODE.build(0xAF, b"\x01").hex()   # '010400af01b40002'
frames, leftover = DIVOOM_STUFFED.iter_frames(raw)   # byte-stuffed (TimeBox-mini), auto de-stuffed
custom = Framing(crc_bytes=1, stuffing=Stuffing(escape=0x7D))   # roll your own device's dialect
```

## Decode passive BLE advertisements

```python
from untether_bt import parse_ad, manufacturer_data, service_data, local_name

cid, data = manufacturer_data(adv_bytes)   # company id (little-endian) + payload
temp = ((int.from_bytes(data[2:5], "big")) // 1000) / 10   # e.g. Govee H5104 packed temp
```

## What's here (v0.1) and what's next

**Now:** the framing/codec engine, the SPP bridge client (sync + async), and the advertisement decoder — the pieces that are both proven on real hardware and uniquely ours.

**Roadmap:** a btsnoop/`btsnooz` parser, HCI/L2CAP decoders, a host-side SDP browser, a GATT client (wrapping `bleak`), the Assigned-Numbers resolver, the Home-Assistant coordinator helpers, and the agent-drivable app→HA reverse-engineering pipeline (ADB/UIAutomator + HCI capture + UI-action↔wire-byte correlation).

## License

MIT.
