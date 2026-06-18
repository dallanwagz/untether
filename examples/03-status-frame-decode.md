# 3 · Decoding the 17-byte status frame → sensors

The device streams a 17-byte `F0 … F1` frame on the notify char. The decompiled app named the
status fields (`nChairRunState`, `airBagStrength`, …) but not their byte offsets — so we found the
offsets empirically: **change one thing at a time and diff the frame.**

## The capture method (on-demand reads beat loggers)

A trivial reader, called right after the operator announces each change ("set speed to 1" → read):

```python
def read_frame():
    raw = get_state("sensor.<device>_raw_status")["state"]   # the integration exposed a raw-hex diagnostic sensor
    return [int(raw[i:i+2], 16) for i in range(0, len(raw), 2)]
```

No free-running logger to expire, and every sample is cleanly attributed to a known action.

## Real diffs that pinned bytes

**Speed** (manual mode, only speed changed):
```
speed 1 -> f0 65 06 00 2d 19 00 03 29 ...      b2 = 0x06   (0x06 >> 2 = 1)
speed 6 -> f0 65 1a 00 2c 6f 00 03 25 ...      b2 = 0x1a   (0x1a >> 2 = 6)
=> speed = (b2 >> 2) & 0x07
```

**Airbag zone**, one at a time → a bitmask in b12:
```
arm&shoulder -> ... 13 1c ...   b12 = 0x13   (0x10 set)
back&waist   -> ... 0b ...      b12 = 0x08
leg&foot     -> ... 07 ...      b12 = 0x04
buttock      -> ... 23 ...      b12 = 0x20
```

**The flag-bit trap (session timer).** The countdown read absurdly high and seemed offset by ~8191:
```
10:00 set -> b4=0x24 b5=0x43      naive b4*128+b5 = 4675   (way off)
30:00 set -> b4=0x2d b5=0x77
```
8191 = `0x1FFF` screamed "flag bits in the high byte." `b4`'s top 3 bits are a *different* field
(massage part), so mask them:
```
time_remaining_s = ((b4 & 0x1F) << 7) | (b5 & 0x7F)
10:00 -> (0x04<<7)|0x43 = 599s = 9:59   30:00 -> (0x0d<<7)|0x77 = 1783s = 29:43   # matches the screen
```
We confirmed units by having the operator read the chair's **on-screen clock** and pairing it with
the bytes.

## The resulting byte map

```
b1  bit0x40 powered; (b1>>3)&7 technique (1 kneading,2 knocking,3 sync,4 tapping,5 shiatsu)
b2  bit0x40 heat; (b2>>2)&7 speed 1-6; b2&3 roller width (1 narrow,2 medium,3 wide)
b3  &0x07 airbag strength 0-5; bit0x40 ionizer
b4  >>5 part (1 whole,2 partial,3 point);  b4&0x1F + b5 -> time remaining (s)
b6  >>5 foot-roller level 0-3
b7  run state (0 idle,1 resetting,2 ready,3 running)
b8  roller vertical position (0x20 waist .. 0x2c neck)
b10 bit0x40 zero gravity
b12 airbag zones: 0x10 arm&shoulder,0x08 back&waist,0x04 leg&foot,0x20 buttock
b13 program (b13>>2; 0x2d = a 3D preset)
b14 3D strength 1-5
```

## What it became: `parse_status()` → typed state → sensors

```python
def parse_status(data: bytes) -> ChairState | None:
    if len(data) != 17 or data[0] != 0xF0 or data[-1] != 0xF1:
        return None
    running = data[7] == 3
    return ChairState(
        powered=bool(data[1] & 0x40),
        technique=_TECHNIQUES.get((data[1] >> 3) & 0x07),
        speed=((data[2] >> 2) & 0x07) if running else None,
        width=_WIDTHS.get(data[2] & 0x03) if running else None,
        heat=bool(data[2] & 0x40),
        ionizer=bool(data[3] & 0x40),
        airbag_strength=data[3] & 0x07,
        part=_PARTS.get(data[4] >> 5),
        time_remaining=(((data[4] & 0x1F) << 7) | (data[5] & 0x7F)) if running else None,
        foot_roller=data[6] >> 5,
        zero_gravity=bool(data[10] & 0x40),
        airbag_arm_shoulder=bool(data[12] & 0x10),
        # ... etc
        raw=data.hex(),
    )
```

Each field becomes an entity — enum sensors carry `options` + translations:

```python
class InfinityChairTechniqueSensor(InfinityChairEntity, SensorEntity):
    _attr_translation_key = "technique"
    _attr_device_class = SensorDeviceClass.ENUM
    _attr_options = ["kneading", "knocking", "sync", "tapping", "shiatsu"]

    @property
    def native_value(self):
        return self.coordinator.data.technique if self.coordinator.data else None
```

## Honest gaps (documented, not hidden)

- **Live vs setting:** in motion-heavy techniques (kneading) `b2`'s width bits oscillate with the
  stroke, so speed/width/roller-position are surfaced *only while running*.
- **Not reported at all:** seat/recline positions are command-only; foot-roller and 3D *levels*
  are set-only; the three 3D presets all share `b13=0x2d` (indistinguishable). These are protocol
  limits, called out in the README so users aren't surprised.
