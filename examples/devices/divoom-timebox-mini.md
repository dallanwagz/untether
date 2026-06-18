# Divoom TimeBox-mini (11×11 RGB LED BT speaker/clock)

- **Vendor app:** `com.divoom.Divoom` (Android; "Divoom" on iOS)
- **HA integration:** **not built** — this profile captures the protocol only (driven headless from a Raspberry Pi, no HA).
- **Contributed by:** dallanwagz · 2026-06-17

> One of a 3-device family (TimeBox-mini, Pixoo 16, MiniToo). Shared: Bluetooth **Classic SPP**,
> the `01|LEN16|body|CRC16|02` envelope, `CRC = sum(LEN+body) & 0xFFFF`, the `0x74` brightness
> opcode. See [divoom-pixoo-16.md](divoom-pixoo-16.md) for the sibling's deltas. Everything below is
> tagged **Verified** (real capture/test) / **Inferred** (from code) / **Unknown**.

## Transport

**Bluetooth Classic SPP / RFCOMM channel 4** — *not BLE*. **Verified** by:
- a Linux `socket(AF_BLUETOOTH, SOCK_STREAM, BTPROTO_RFCOMM)` client on **channel 4** driving the
  device reliably for hours (headless, no app);
- `sdptool browse <mac>` → `Service Name: Serial Port 1 → RFCOMM Channel: 4`;
- on macOS it exposes a `/dev/cu.*` SPP serial port after pairing.

It's a BT **speaker**, so it also carries an **A2DP audio** profile — and **A2DP lives on a
separate BD_ADDR, not the control MAC**. *(Now **Verified**, 2026-06-17: the phone enumerates the
device as two addresses — `…:72:1E` `TimeBox-mini-light` = the SPP control endpoint, and a distinct
`…:C3:2C:2A` `TimeBox-mini-audio` = the A2DP endpoint. `dumpsys bluetooth_manager` shows the phone
bonded to the **audio** address only; the control endpoint is **not bonded** → SPP control is
insecure/just-works, no link key. This corrects the earlier "Inferred coexistence on one MAC" and
matches the Pixoo's separate-address SDP.)*

**HA host implication:** HA's BT stack is BLE-only → this needs an **ESP32 (WROOM-32) SPP bridge**
or an RFCOMM-host integration, **not** a BLE proxy.

## Connection

- **RFCOMM channel 4.** Classic **BR/EDR bond**, just-works SSP (no PIN observed).
- Plain `RfcommSocket` works; pin the source adapter by BD_ADDR to survive `hciN` renumbering.
- **Single-bond:** ONE host at a time (phone *or* Pi). The other must release it first.

## Command frame

```
01 | LEN16(LE) | body | CRC16(LE) | 02
   LEN  = len(body) + 2             (body + the 2 CRC bytes)
   CRC  = sum(LEN bytes + body) & 0xFFFF   (little-endian)
   body = <opcode> <args...>
BYTE-STUFFING (TimeBox-mini only): inside LEN..CRC, escape 01→03 04, 02→03 05, 03→03 06
```

**Golden command frame — brightness = 50% (`0x74 0x32`):**
```
body  = 74 32
inner = 04 00 74 32                 (LEN=04 00)
CRC   = 0x04+0x00+0x74+0x32 = 0x00AA → AA 00
frame = 01 04 00 74 32 AA 00 02     (no 01/02/03 in inner → no stuffing)
```
*(Verified — `0x74` RE'd from a live app capture; frame from the verified builder.)*

### Command catalog

body = opcode + args (before framing/stuffing). All **Verified** from `tshark` captures of the app unless noted.

| Command | body | notes |
|---|---|---|
| static image | `44 00 0A 0A 04` + 182B RGB444 | 11×11, raw (see Image payload) |
| animation frame | `49 …` (multi-frame colour) | **correction (decompile):** `0x49` is
  `SET_MUL_BOX_COLOR`; the app's real per-frame animation path is **`0xB1 SET_USER_GIF`** (large/new
  anims use `0x8C/0x8D`). `0x49` is streamed (no ack). |
| set view | `45 <type>` | 00 clock,01 temp,02 off,03 anim,04 graph,05 image,06 stopwatch,07 scoreboard |
| clock + colour | `45 00 <h24> <r> <g> <b> FF` | |
| set time | `18 <yy> <cc> <mo> <dd> <hh> <mm> <ss>` | |
| volume | `08 <0..16>` | |
| tool select | `71 <toolid>` | 00 stopwatch, 01 scoreboard |
| stopwatch | `72 00 <1=start\|0=stop>` | |
| scoreboard | `71 01` then `72 01 01 <red16LE> <blue16LE>` | capture + replay verified |
| alarm | `43 <idx> <en> <hh> <mm> <days> 00 01 00 00 <vol>` | days bit0=Sun..bit6=Sat |
| sleep timer | `40 0a <sound> ff 00 00 32 ff 55 00 32` + `a3 01 <sound> 32` | sound idx 1..6; timer phone-side |
| launch game | `a0 <gameid16LE>` | phone = controller |
| brightness | `74 <0..100>` | percent (same opcode as Pixoo) |
| shake→brightness | `a7 <0\|1>` | set-only |
| sound→brightness (idle) | `b2 <0\|1>` | set-only |
| auto power-off | `ab <minutes16LE>` | 0=never; presets 30/60/180/360/720 |
| temp/weather view | `45 01` + app pushes weather *data* | **Inferred** — data payload not decoded |

## Status frame — **Verified** (2026-06-17), was *Unknown*

The device is **not** write-only. On connect it sends a greeting, and it **ACKs almost every write**
with a framed reply (captured live over RFCOMM ch4):

**Greeting (on connect, stable):** `00 05 48 45 4C 4C 4F 00` = `len16(0x0005) | "HELLO" | 00`
(a plain boot banner — *not* the `01…02` envelope).

**ACK frame:**
```
01 | LEN16(LE) | 04 <id> 55 <value…> | CRC16(LE) | 02
  04        ack/response type byte (constant)
  <id>      the opcode being acked  (brightness is the exception — see below)
  55        constant marker ('U')
  <value…>  echoed value / status (0..N bytes; some acks carry none)
  same LEN/CRC rule as outbound; byte-stuffing ALSO applies inbound, incl. the CRC bytes
```

**Golden inbound frames:**
```
brightness=50 → 01 06 00 04 32 55 32 C3 00 02     body 04 32 55 32  (value 0x32=50 echoed)
view=off      → 01 06 00 04 45 55 03 05 A6 00 02  body 04 45 55 02  (0x02 stuffed → 03 05)
image push    → 01 06 00 04 44 55 00 A3 00 02     body 04 44 55 00  (still image accepted)
```

**ACK-id map (every catalog opcode probed live):** view `0x45`, volume `0x08`, image `0x44`,
time `0x18`, tool `0x71`, scoreboard `0x72`, alarm `0x43`, sleep `0x40`, game `0xa0`,
shake→bri `0xa7`, sound→bri `0xb2` — each acks under **its own opcode** and echoes the set value.
**Brightness (`0x74`) is the one anomaly — it acks under id `0x32`, not `0x74`** (the firmware
reports brightness as `SPP_LIGHT_ADJUST_LEVEL 0x32`, a separate report opcode from the
`SET_SYSTEM_BRIGHT 0x74` setter — confirmed in the decompile, `0x31` is the matching get). Streamed/​
set-only commands are **silent** (no ack): animation frame `0x49`, sleep-aux `0xa3`, auto-power-off
`0xab`.

**This is also a queryable status channel — not write-only (the big correction).** The app's
**GET_* opcodes** return real device state, wrapped in the same `04 <echoed-opcode> 55 <data>` ACK
(decompile: parser `s.h()` switches on the echoed opcode to route each GET reply). Captured live:
| query | opcode | reply body | decoded |
|---|---|---|---|
| volume | 0x09 | `04 09 55 08` | 8 |
| brightness | 0x31 | `04 31 55 3c` | 60 |
| auto-power-off | 0xAC | `04 ac 55 00 00` | minutes16=0 (never) |
| **device temperature** | 0x59 | `04 59 55 4a 25 00` | type, **temp16=0x0025** — a real sensor |
| shake→bri / sound→bri | 0xA8 / 0xB3 | `04 a8 55 01` / `04 b3 55 01` | on/off flags |
| display/light state | 0x46 | `04 46 55 00 4a4c4b … 64` | 23-byte LightModel (mode, palette, level) |
| alarm table | 0x42 | `04 42 55 00 01 07 1e 7f …` | full alarm readback |

So for HA this device is **pollable**: brightness, volume, temperature, power-off timer, display
mode and the alarm table are all readable via GET_* (request/response — there's **no unsolicited
telemetry**, so poll). Every settings *write* is also confirmed by its `04 <opcode> 55 <value>`
echo (use that for write-verification + reconnect-health).

> The full app command surface is a **~120-opcode family superset** (one APK drives the whole Divoom
> line). This profile documents the slice **Verified on the TimeBox-mini**; opcodes that exist in the
> app but are **silent on this model** (e.g. the entire `0xBD` EXTERN_CMD sub-protocol) are called out
> under Gaps. See SKILL.md *The one-app-many-models problem*.

## Home Assistant transition

No HA integration was built. The reusable, unit-testable artifact (the `protocol.py` equivalent) is
the frame builder + image encoder:

```python
def build_packet(body):                       # 01 | LEN16 | body | CRC16 | 02  (+ byte-stuffing)
    inner = [len(body)+2 & 0xFF, (len(body)+2)>>8 & 0xFF] + body
    ck = sum(inner)
    inner += [ck & 0xFF, (ck >> 8) & 0xFF]
    out = []
    for b in inner:                            # stuff 01/02/03 (TimeBox-mini only)
        out += [0x03, b+0x03] if b in (1,2,3) else [b]
    return bytes([0x01] + out + [0x02])

def encode_frame(img):                         # 11x11 -> 182B raw RGB444, row-major
    nib = []
    for y in range(11):
        for x in range(11):
            r,g,b,a = img.convert("RGBA").getpixel((x,y))
            if a < 32: r=g=b=0
            nib += [r>>4, g>>4, b>>4]
    nib += [0]*(len(nib)%2)
    return [lo|(hi<<4) for lo,hi in zip(nib[::2], nib[1::2])]

static_image_packet = lambda img: build_packet([0x44,0x00,0x0A,0x0A,0x04] + encode_frame(img))
brightness_packet   = lambda lvl: build_packet([0x74, max(0,min(100,lvl))])
```

### Image payload — RGB444 raw, 182 bytes — *Verified*

11×11 = 121 px; **4 bits each R,G,B** (high nibble), alpha<32→black; 363 nibbles → pad 364 → **182
bytes**, `byte = lo_nibble | (hi_nibble<<4)`, row-major; **no palette, no compression**.
Worked example — top-left pixel `#FF0000`, rest black: nibbles `F,0,0,…` → bytes `0F 00 00 00 …`;
still body = `44 00 0A 0A 04 0F 00 00 00 …(→187B)…`. *(Verified format, computed from the verified encoder.)*

## Gaps & gotchas

- **Single-bond.** Phone and Pi fight over the one slot. A box **bonded-and-searching for its host
  does NOT advertise** (invisible to inquiry scans) yet still answers a *direct page* with a
  half-open, **un-authenticated** ACL (`state 5`, no AUTH ENCRYPT) — looks "reachable" but never
  completes. Distinguish *bonded-elsewhere* (free it / unbind in the app) from *off/faulty*. **Cost
  us hours.** *(Reproduced live 2026-06-17: with the Pi released and phone BT healthy, the **app**
  still couldn't bond the control endpoint — repeated `BONDING→BOND_STATE_NONE` → app dialog "**Fail
  to pair… Check if Device is paired by another smartphone**" — while the Pi opened RFCOMM ch4 to the
  same device in **2.4 s**. The device was alive the whole time; the app's bond step on the
  insecure-SPP endpoint is the fragile one. The phone is bonded only to the **audio** BD_ADDR; the
  control endpoint is never bonded.)*
- **Byte-stuffing is mandatory** here (and absent on the Pixoo — don't share one builder). It applies
  **inbound too**, including to the CRC bytes.
- **Status IS reported** — corrected: per-write `04 <opcode> 55 <value>` acks **and** GET_* queries
  return real telemetry (see Status frame). Not free-running, so poll.
- **No screen-power/blank opcode on this model.** The whole `0xBD` EXTERN_CMD sub-protocol
  (`OPEN_SCREEN_CTRL`, device-info, screen-mirror, …) is **silent** on the TimeBox-mini — it's a
  newer-model feature. Power management = `0xAB` auto-power-off + `0x1F` scheduled on/off only. This
  is the **one-app-many-models** rule in action: probe-and-listen (ack/reply vs silence) tells you
  your model's slice of the ~120-opcode app superset.
- **Silence on a SET is ambiguous.** `0x49`/`0xab`/`0xa3` are silent yet real (set-only); so are the
  scrolling-text `0x86`/`0x87`, 12-24h `0x2D`, °C/°F `0x2B`, next-track `0x12`, scheduled-on/off
  `0x1F` SETs — **accepted-or-unsupported, indeterminate** without a GET or an operator eyeball.
  (play/pause `0x0A` *does* ack.) Only silence on a **GET** is firm proof of "unsupported" — which is
  what closed C6. See SKILL.md.
- **3 s connect timeout too tight** — module pages slowly; use ≥6 s, retry, treat
  `EBUSY/EBADE/EHOSTDOWN/ETIMEDOUT` as transient.
- A wedged **ghost ACL** (bogus handle e.g. `0x0F00`, `state 5`) survives `bluetoothctl disconnect`;
  clear it with `hciconfig hciX down/up`.

## Work queue

Most items below were **closed in a 2026-06-17 live session** (driven headless over RFCOMM ch4 from
a Raspberry Pi — the phone app could not bond this device, see gotchas).

- **C1 SDP / addresses — DONE.** Two BD_ADDRs: control SPP `…:72:1E` + separate A2DP `…:C3:2C:2A`
  (settles the A2DP "Inferred"; see Transport).
- **C2 framing/CRC — DONE.** brightness=50 ack `01 06 00 04 32 55 32 C3 00 02` round-trips the
  `01|LEN|body|CRC|02` envelope and `sum(LEN+body)&0xFFFF`.
- **C3 stuffing — DONE, both directions.** Outbound: brightness=1 (`body 74 01`) goes out
  `01 04 00 74 03 04 79 00 02` (the `01` stuffed to `03 04`). Inbound: acks show `01→03 04`,
  `02→03 05`, `03→03 06`, and the **CRC bytes get stuffed too**.
- **C4 status frames — DONE.** Decoded the ACK protocol (`04 <opcode> 55 <value>`) + the "HELLO"
  greeting — see Status frame. Not a free-running sensor stream; it's a per-write echo/ack.
- **C5 image — DONE.** A 182 B `0x44` still is accepted and acked (`04 44 55 00`).
- **C6 power/blank opcode — RESOLVED (none).** `view=off (45 02)` only switches the *view*. The
  app's screen-power command (`OPEN_SCREEN_CTRL`, ext 47 under `0xBD`) and the whole `0xBD`
  sub-protocol are **silent** on this model → no screen-power opcode; use `0xAB`/`0x1F`. (Model-gated
  — see Gaps.)
- **NEW (decompile + live):** GET_* telemetry (vol 0x09, brightness 0x31, temp 0x59, auto-off 0xAC,
  display 0x46, alarm 0x42, …) all answer live — documented under Status frame. The full ~120-opcode
  app superset (FM/SD/mic/drawing-pad/64-px/OTA/EXTERN) is enumerated in the session notes; only the
  TimeBox-mini-applicable subset is verified here.
