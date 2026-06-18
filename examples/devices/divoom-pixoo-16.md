# Divoom Pixoo 16 (16×16 RGB LED BT display)

- **Vendor app:** `com.divoom.Divoom` (Android)
- **HA integration:** **not built** — protocol only (driven headless from a Raspberry Pi).
- **Contributed by:** dallanwagz · 2026-06-17

> Same family as the [Divoom TimeBox-mini](divoom-timebox-mini.md). **It's a "Timebox-family"
> device — binary opcodes like the TimeBox-mini — that reuses the *MiniToo transport* (ch2, `0xAF`
> handshake, no byte-stuffing).** Only the **deltas vs the TimeBox-mini** are documented here;
> anything not listed matches that profile. Tags: **Verified** / **Inferred** / **Unknown**.

## Transport

**Bluetooth Classic SPP / RFCOMM channel 2** *(delta: ch2, vs TimeBox=4, MiniToo=1)*. **Verified**
via HCI capture (`btrfcomm.channel == 2`) and a live RFCOMM client. If it's a BT speaker, **A2DP
sits on a separate BD_ADDR** (not the control MAC) — same pattern verified on the TimeBox-mini
(`-light` control vs `-audio` audio address). Same BLE-only-HA implication → **ESP32 SPP bridge**.

## Connection

- **RFCOMM channel 2.** BR/EDR bond, just-works. Single-bond. *(ch2 re-confirmed 2026-06-17 from a
  live **app** HCI snoop — `btrfcomm.channel == 2`, 3,300+ phone→device frames.)*
- **Handshake — what works for a raw client vs what the app does (corrected 2026-06-17):**
  - Our **headless RFCOMM client** must send the MiniToo burst incl. the **`0xAF` connected-flag
    `{01}`** or the screen stays on the BT icon. *(Verified — `0xAF` is a sufficient trigger.)*
  - But the **vendor app NEVER sends `0xAF`** (0 occurrences across multiple captured (re)connects).
    It *reads* the flag via **`0xB0` GET_CONNECTED_FLAG** and initializes the device with a
    **`0xBD` EXTERN burst + a JSON-over-SPP `{"Command":"Device/Set…"}` frame + GET-sync + set-time**.
    So `0xAF` is *a* way to wake the device, **not "what the app sends"** — don't document it as the
    app's handshake. (Textbook static-says-X / app-does-Y.)
- **Single-bond fragility is family-wide:** the app-initiated **re-bond** of the Pixoo hit the same
  "Fail to pair" trap as the TimeBox-mini (drops on disconnect, won't cleanly re-pair). The Pi's
  insecure-RFCOMM path re-grabs it without that.

## Command frame

**Same envelope, but NO byte-stuffing** ("NewMode") — *delta vs TimeBox-mini*:
```
01 | LEN16(LE) | TYPE | payload | CRC16(LE) | 02      CRC = sum(LEN+body) & 0xFFFF
(no 01/02/03 escaping — LEN16 prefix makes it unnecessary)
```

**Golden frame — `0xAF` connected-flag handshake:**
```
body  = AF 01
frame = 01 04 00 AF 01 B4 00 02        (CRC 0x04+0x00+0xAF+0x01 = 0x00B4)
```
**Brightness — identical to TimeBox-mini:** `0x74 <0..100>` → `01 04 00 74 32 AA 00 02` (50%).
*(Both Verified on-device.)*

### Command catalog

| Command | TYPE/body | notes |
|---|---|---|
| connected-flag | `AF 01` | wakes a raw client; **the app never sends this** (uses 0xB0 GET + 0xBD/JSON init) |
| brightness | `74 <0..100>` | same as TimeBox-mini; **app-confirmed** `01 04 00 74 00 78 00 02` |
| still image | `44` + `00 0A 0A 04` + `<aa-frame>` | palette-indexed; **app-confirmed** (see Image payload) |
| animation | `8B` + chunked payload | shared-palette; **app-confirmed** (see Image payload) |
| frame speed/delay | `16 <ms16LE>` | app sends with the editor push, e.g. `16 64 00` |
| **content (HOT) transfer** | `9B`/`9D`/`9E` chunks | the app streams clock-face/animation resources via the HOT file-transfer family (carrying `aa`-frames), not raw 0x44 |
| **EXTERN sub-protocol** | `BD <ext> …` | **SUPPORTED on the Pixoo** (corrects the earlier claim) — app drives ext `0x2F` OPEN_SCREEN_CTRL, `0x32`/`0x33` equalizer/light-effect, `0x26` language, etc., and the device **replies** `04 BD 55 …`. (The TimeBox-mini is silent to all of `0xBD`.) |
| power/blank (screen) | `BD 2F <arg>` | **app uses EXTERN `0x2F` OPEN_SCREEN_CTRL**, e.g. `01 05 00 bd 2f 02 f3 00 02`. (Earlier headless `0xbd 2f` "did nothing" was a wrong-arg/length probe, **not** model-gating — the Pixoo does support `0xBD`.) Exact off/on arg TBD. |
| state queries (GET) | `31`,`09`,`46`,`B0`,`42`,`A2`,`36/37/97` | app reads brightness/vol/box-mode/conn-flag/alarm/scene/versions on connect — replies decode (see Status frame) |

> **Correction to the earlier profile + my own PR #5:** I had written that the `0xBD` EXTERN
> sub-protocol was "model-gated and silent on TimeBox-family models." That's true for the
> **TimeBox-mini** but **wrong for the Pixoo** — a live app HCI snoop shows the Pixoo both *receiving*
> and *answering* `0xBD` commands. Same family, same app build, **different per-model support** — the
> one-app-many-models rule, and a reminder that "silent on device A" ≠ "silent on device B."

The TimeBox-mini appliance opcodes (`0x43` alarm, `0x71/0x72` tools, …) were **not** tried on the
Pixoo — **Unknown** whether it accepts them (we only needed image + brightness). See work queue.

## Status frame — queryable (was "Unknown"), confirmed from the live app

Same decoded `04 <opcode> 55 <data>` ACK/echo envelope as the TimeBox-mini — and an **app HCI snoop
proves the vendor app actively queries device state on connect** and decodes the replies:
```
01 06 00 04 31 55 55 e5 00 02   GET-brightness  → 04 31 55 <55=85>     (real telemetry)
01 05 00 04 18 55 76 00 02      set-time ack    → 04 18 55  (no value)
01 07 00 04 b0 55 01 49 5a 01 02  GET-conn-flag → 04 b0 55 01 49
01 69 00 04 42 55 …               GET-alarm     → full multi-slot alarm table
01 4d 00 04 1f 55 00…00 c5 00 02  GET-power-sched → scheduled-on/off struct
01 07 00 04 bd 55 27 01 45 01 02  EXTERN reply  → 04 bd 55 <ext 0x27> 01
```
So the Pixoo is **pollable** (brightness, volume, box-mode, conn-flag, alarm, versions) — not
write-only. The app also sends one **JSON-over-SPP `0x01`** `{"Command":"Device/Set…"}` frame on
connect (the token-bearing path → **contents REDACTED**, presence noted).

## Home Assistant transition

No HA built. The reusable artifact is the framer (shared via the MiniToo transport) + the
palette-frame encoder:

```python
def build_frame(t, payload=b""):                    # 01 | LEN16 | TYPE | payload | CRC16 | 02
    body = bytes([t]) + bytes(payload)
    inner = bytes([(len(body)+2)&0xFF, (len(body)+2)>>8 & 0xFF]) + body
    crc = sum(inner) & 0xFFFF
    return b"\x01" + inner + bytes([crc&0xFF, crc>>8 & 0xFF]) + b"\x02"

# still: build_frame(0x44, b"\x00\x0a\x0a\x04" + aa_frame(img))
```

### Image payload — palette-indexed `aa`-frame (the big delta) — *Verified*

A still is **not** raw RGB — it's an indexed `aa` block:
```
aa-frame = AA | LEN16(LE) | timecode16(LE) | reset | palCount | palette(RGB888 × palCount) | packed-indices
  indices 0-based (pixel = palette[idx]), packed LSB-first, row-major
  bpp by palette size: pc<=2 →1, <=4 →2, <=16 →4, else →8
  a SOLID colour (palCount=1) carries NO index data (bpp 0)
still body = 00 0A 0A 04 | <aa-frame>     ; on wire: build_frame(0x44, still body)
```
**Worked golden frame — solid red 16×16, timecode=0x0064:**
```
aa-frame   = AA 0A 00 64 00 00 01 FF 00 00
             (AA | LEN=0x000A | tc=0x0064 | reset=00 | pc=01 | RGB=FF0000 | no idx)
still body = 00 0A 0A 04 AA 0A 00 64 00 00 01 FF 00 00
```
**ANIMATION (`0x8b`, chunked):** **one shared palette** — frame 0 = still format (reset=0) with the
palette; frames 1..N = `reset=1, palCount=0, NO palette`, full bitmap indexing frame 0's palette
(1-based; index 0 = black/off). *(Verified — red→blue→green→yellow clip.)*

**Hard device limits (Verified, hard-won — the Pixoo traps):**
- **Animations cap at bpp4 = a 16-colour shared palette.** A >16-colour (bpp8) animation is accepted
  but **renders garbage** (`ANIM_MAX_COLORS = 16`).
- **Streaming stills at video rate needs a *fixed* palette + fixed bpp.** If palette/bpp change
  frame-to-frame the decoder **desyncs into parallel-line garbage** (even though a *one-off* 8bpp
  still is fine). Fix: pin every streamed frame to one fixed ≤16-colour palette in fixed order
  (4bpp) and force a full index map so even all-black is a normal indexed frame (not the special
  "solid, no-index" form).
- **~18 fps/device is safe**; faster + heavy frames overloads the single BT adapter → links drop
  (`errno 107`).

## Gaps & gotchas (deltas)

- `0xAF` handshake wakes a **raw RFCOMM client** — but the **app never sends it** (it uses
  `0xB0` GET + `0xBD`/JSON init); see Connection.
- **Don't** byte-stuff Pixoo frames (opposite of TimeBox-mini) — **app-confirmed** (the `01` bytes in
  a captured still are not escaped).
- **Palette/bpp must be stable across a stream** — the #1 Pixoo trap (parallel-line garbage).
- Power/blank: **`0xBD` ext `0x2F` OPEN_SCREEN_CTRL** (corrected — the Pixoo *does* support `0xBD`;
  the earlier `0xbd 2f` "failed" was a bad probe). Exact off/on arg TBD.
- The `T_JSON (0x01)` path carries an account **token / device-password / user-id** → **REDACTED**;
  the Pixoo/TimeBox binary opcodes are token-free. *(The app sends one such `{"Command":"Device/Set…"}`
  frame on connect.)*

## Work queue

Most items **closed 2026-06-17 via a live app HCI capture** (pixoo1 connected to the Divoom app →
`adb bugreport` → `btsnoop_hci.log` → `tshark -Y 'btspp && hci_h4.direction==0'`).
- **C1** SDP browse → Serial Port (ch2) + A2DP record (settles A2DP "Inferred"). ch2 also
  re-confirmed from the app snoop.
- **C5 — DONE (app-confirmed).** The Design editor still went out as
  `01 11 00 44 00 0a 0a 04 | aa 0a 00 f4 01 00 01 FF FF FF | 14 05 02` — the documented
  `44 00 0A 0A 04 AA <len16><tc16><reset><palCount><RGB888>` layout, palCount=1 solid (no indices),
  **RGB888 palette**, **NewMode no-stuffing**. Exactly matches our encoder.
- **C5b — DONE (app-confirmed path).** The same frame also went via `0x8b` shared-palette
  (`…8b 01 0a … aa 0a 00 f4 01 00 01 FFFFFF…`) + a `0x16` speed frame. The >16-colour garble is a
  device decode limit already verified headless (`ANIM_MAX_COLORS=16`).
- **C6 — RESOLVED (opcode found).** The app drives screen control via **`0xBD` ext `0x2F`
  OPEN_SCREEN_CTRL** (`01 05 00 bd 2f 02 f3 00 02`); the Pixoo supports the `0xBD` sub-protocol.
  Exact off/on arg still to pin down with an explicit in-app screen toggle.
- **C3** Does the Pixoo accept the TimeBox `0x43/0x71/0x72` catalog? — still open; not needed here.
- **NEW from the app capture:** status is queryable (GET_* telemetry), content rides the HOT
  (`0x9b/0x9d/0x9e`) file-transfer, and the app's connect-init is `0xBD`+JSON+GET (never `0xAF`).
