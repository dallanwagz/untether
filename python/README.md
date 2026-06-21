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

## Reverse-engineer an Android capture

Decode an Android `btsnoop_hci.log` and see exactly which bytes each UI action produced — the
correlation step every other toolchain leaves to manual work:

```python
from untether_bt import Capture, Mark, correlate

cap = Capture.from_btsnoop(open("btsnoop_hci.log", "rb").read())
for a in cap.att():                       # the GATT command/status bytes (BLE)
    print("TX" if a.sent else "RX", a.opcode_name, hex(a.att_handle or 0), a.value.hex())

# attribute frames to the UI actions you marked while driving the app
marks = [Mark(t_power_us, "power"), Mark(t_stop_us, "stop")]
for c in correlate(cap.wire_events(), marks):
    print(c.mark.label, "→", [e.data.hex() for e in c.events])
```

`Capture` also exposes `hci_packets`/`l2cap_payloads` (the Classic/RFCOMM hook via `include_l2cap=True`),
and the btsnoop layer (`parse_btsnoop`/`write_btsnoop`) is a clean, signed-year-0-epoch-correct
parser you can use standalone.

## What's here and what's next

**Now:** the framing/codec engine, the SPP bridge client (sync + async), the advertisement decoder,
and the reverse-engineering pipeline (btsnoop parser + HCI/L2CAP/ATT extraction + UI-action↔wire-byte
correlation) — the pieces that are proven on real hardware and uniquely ours (first-class Classic).

**Roadmap:** `btsnooz` (Android bug-report) decompression, the ADB/UIAutomator driver + jadx/Frida
wrappers (the live half of the RE loop), a host-side SDP browser, a GATT client (wrapping `bleak`),
the Assigned-Numbers resolver, and the Home-Assistant coordinator helpers.

## License

MIT.
