# 2 · GATT enumeration → the command + notify characteristics

The decompiled app spoke **Classic SPP** — but it never worked on the test phone, while the **iOS**
app did. The iOS device picker showed CoreBluetooth UUIDs (not MACs) ⇒ the real transport was
**BLE GATT**. So we connected to the device's BLE side and enumerated its GATT to find where to
send the frames from example 1.

## The probe (`bleak`, run from a laptop in range)

```python
import asyncio
from bleak import BleakScanner, BleakClient

async def main():
    dev = await BleakScanner.find_device_by_name("EVOLUTION-001013", timeout=15)
    async with BleakClient(dev) as client:
        for s in client.services:
            print("SERVICE", s.uuid)
            for c in s.characteristics:
                print("  CHAR", c.uuid, c.properties)

asyncio.run(main())
```

## The output (abridged)

```
SERVICE 0000180a-... (Device Information)         # read-only model/fw
SERVICE 0000fff0-... (Vendor specific)
  CHAR 0000fff1-...  ['write-without-response','write']     <- COMMAND characteristic
  CHAR 0734594a-a8e7-4b1a-a6b1-cd5243059a57  ['notify']     <- STATUS stream
  CHAR 0000fff2/fff5/fff6-... ['read']
SERVICE 00010203-0405-0607-0809-0a0b0c0d1911 ...  # Telink OTA/DFU — IGNORE
```

Then we *validated* before building anything — subscribe to the notify char, write a framed
command to `fff1`, and confirm both a physical reaction and a status change:

```python
# write Power (F0 83 01 7B F1) to fff1, watch the notify stream
await client.start_notify("0734594a-a8e7-4b1a-a6b1-cd5243059a57", on_notify)
await client.write_gatt_char("0000fff1-...", bytes([0xF0,0x83,0x01,0x7B,0xF1]), response=False)
# -> chair powered on; status byte 7 went 00 -> 02 (confirmed two-way control)
```

## What it became

Two constants the whole integration is built around (`protocol.py`):

```python
COMMAND_CHAR_UUID = "0000fff1-0000-1000-8000-00805f9b34fb"   # write build_frame() here
STATUS_CHAR_UUID  = "0734594a-a8e7-4b1a-a6b1-cd5243059a57"   # subscribe for ChairState
```

> **Caveats recorded:** the device also advertises with a rotating/resolvable BLE address, and
> macOS/iOS hide the MAC behind a per-host UUID — Android exposes the real MAC, which is what HA's
> Bluetooth integration discovers and connects by. Ignore the Telink OTA service entirely.
