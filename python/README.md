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

`AsyncSppBridge` is the asyncio twin (request/response). The same client also works against `socat`/`ser2net` over `/dev/rfcommN` on a BlueZ host.

## A connection that stays up (for daemons & HA coordinators)

A long-running host needs the opposite of request/response: one connection that heals itself. `SppConnection` is that loop — connect, run a startup handshake, read forever in the background, serialise writes, reconnect with capped backoff, and tear down when inbound bytes go quiet. Pure asyncio, no Home Assistant dependency; you bring the deframer.

```python
from untether_bt import SppConnection, DIVOOM_NEWMODE

leftover = b""
def on_chunk(chunk: bytes) -> None:
    global leftover
    frames, leftover = DIVOOM_NEWMODE.iter_frames(leftover + chunk)
    for f in frames:
        ...  # decode device state, push to your entities

conn = SppConnection(
    "192.168.1.50", 8888,
    on_chunk=on_chunk,
    on_connect=lambda: conn.send(DIVOOM_NEWMODE.build(0xAF, b"\x01")),  # handshake
    on_state=lambda up: print("link", "up" if up else "down"),
)
await conn.start()
await conn.send(DIVOOM_NEWMODE.build(0x74, b"\x32"))  # serialised write
# ... later: await conn.stop()
```

This is exactly the transport the example [`hass-pixoo-spp`](https://github.com/dallanwagz/hass-pixoo-spp) coordinator runs on — the integration keeps only its device-specific logic (handshake bytes, frame parsing, the chunked animation upload) and delegates the connection lifecycle here.

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

## Reverse-engineer an app, end to end

Drive the vendor app over ADB, mark each UI action, then see exactly which wire bytes each action
produced — the UI-action↔byte correlation every other toolchain leaves to manual work:

```python
from untether_bt import AndroidDriver, Capture, Recorder, correlate

drv = AndroidDriver(serial="ABC123")     # accessibility-label driving, not pixels
drv.enable_hci_snoop()                    # turn on Bluetooth HCI logging
drv.launch("com.vendor.app")

rec = Recorder()
drv.tap_and_mark("Power", rec)            # tap the labelled control + timestamp the action
drv.tap_and_mark("Brightness Up", rec)

cap = Capture.from_btsnoop(drv.pull_btsnoop())     # pull the capture (via adb bugreport)
for c in correlate(cap.wire_events(), rec.marks):
    print(c.mark.label, "→", [e.data.hex() for e in c.events])   # action → the frames it sent
```

Already have a capture? Skip the driver and decode it directly:

```python
cap = Capture.from_btsnoop(open("btsnoop_hci.log", "rb").read())
for a in cap.att():                       # GATT command/status bytes (BLE)
    print("TX" if a.sent else "RX", a.opcode_name, hex(a.att_handle or 0), a.value.hex())
```

`Capture` also exposes `hci_packets`/`l2cap_payloads` (the Classic/RFCOMM hook via
`include_l2cap=True`); the btsnoop layer (`parse_btsnoop`/`write_btsnoop`) is a clean,
signed-year-0-epoch-correct parser you can use standalone; and `AndroidDriver` runs adb through an
injectable runner, so it's testable without a device.

## Static & dynamic analysis (jadx / Frida)

Decompile the app and map its Bluetooth surface — *is it BLE or Classic SPP?*, which UUIDs, where
are the write call sites:

```python
from untether_bt import analyze_apk
a = analyze_apk("vendor.apk")          # runs jadx, walks the tree
print(a.summary())                      # transport: classic-spp | ble | both ; UUIDs ; call sites
```

Or hook the running app with Frida to dump the **outgoing command bytes** live (BLE *and* Classic,
at the API layer — works even on an encrypted link), as the same `WireEvent`s `correlate()` eats:

```python
from untether_bt import FridaSession           # pip install "untether-bt[frida]"
events = []
FridaSession("com.vendor.app").run(events.append, duration=20)
```

## Protocol primitives

```python
from untether_bt import Capture, GattClient, describe_uuid, parse_ssa_response, spp_channel

describe_uuid(0x180F)                      # '0x180F (Battery Service)'
spp_channel(parse_ssa_response(sdp_bytes)) # the dynamic RFCOMM channel — browse, don't hardcode
spp_channel(Capture.from_btsnoop(cap).sdp_records())  # …or recover it straight from a capture

async with GattClient("AA:BB:CC:DD:EE:FF") as g:   # wraps bleak; pip install "untether-bt[ble]"
    print(g.services())
    await g.subscribe(0xFFE1, print)        # CCCD handled for you
    await g.write(0xFFE1, b"\x01")
```

## What's here and what's next

**Now:** the framing/codec engine; the SPP bridge client (sync + async) plus the self-healing
`SppConnection` (dogfooded by the Pixoo HA integration); the advertisement decoder;
the full RE capture pipeline (live **ADB/UIAutomator driver** → btsnoop **+ btsnooz** → HCI/L2CAP/ATT
extraction → UI-action↔wire-byte correlation); **static + dynamic analysis** (jadx mapping + Frida
write hooks); the protocol primitives (**SDP** record parser — incl. recovering the RFCOMM channel
from a capture or live via BlueZ — **GATT** client over bleak, **Assigned-Numbers** resolver). Proven
on real hardware and uniquely ours (first-class Classic throughout).

**Roadmap:** growing the bundled Assigned-Numbers tables; publishing the spec map as a Classic-BT RE
handbook; contributing parsers upstream.

## License

MIT.
