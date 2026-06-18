---
name: untether
description: >-
  Reverse-engineer a Bluetooth / BLE consumer device (controlled by a vendor Android/iOS app)
  into a local Home Assistant integration. Covers static APK decompilation AND dynamic
  ADB/UIAutomator + packet capture, cataloging every command, matching commands to features,
  decoding the status frame byte-by-byte, and shipping an integration that installs via HACS AND
  is structured to be PR-able into Home Assistant Core. Use when someone wants to control a
  BLE/Bluetooth gadget from Home Assistant without the cloud/app.
---

# untether — Android (BLE) app → Home Assistant integration

A phase-gated methodology to turn a vendor-app-controlled Bluetooth device into a local HA
integration. Works for BLE GATT devices (the common case) and Bluetooth Classic SPP devices.
The long-form field-manual of every technique lives in [`docs/TECHNIQUES.md`](docs/TECHNIQUES.md).

## Objective — what "done" means (read this first)

**The deliverable is a Home Assistant integration that installs out-of-the-box via HACS *and*
meets the requirements and guidelines to be submitted as a PR into Home Assistant Core**, so others
can use it. Not a one-off script, not a personal `custom_components/` hack — a properly-structured,
tested, documented integration that a core reviewer would accept.

Concretely, you are done when:
- it **installs cleanly via HACS** (custom repository) and a user can add the device through the UI;
- the protocol logic is a **pure, unit-tested module** with golden-frame tests;
- it passes **`hassfest` + `ruff` + `mypy`** and follows HA's async/coordinator/config-flow patterns;
- it declares and meets at least **Bronze on the Integration Quality Scale**;
- the only remaining steps to land in Core are **mechanical** (move the dir, drop the HACS-only
  bits, open the docs + brands PRs) — see Phase 5 for the exact HACS↔Core delta and checklist.

Build for Core from the start. Retrofitting a quick hack into a core-quality integration is far
more work than doing it right once. Phase 5 spells out the requirements; everything before it
exists to give you a correct, verified protocol to build on.

## The one principle that matters most: do BOTH static and dynamic

- **Static** (decompile the app) gives you the **protocol spec**: exact frame format, the
  checksum, the *full* command catalog (every messageId), the command-gating logic, and the
  field list of the status struct. It tells you *how* packets are built.
- **Dynamic** (drive the app over ADB + capture what it sends, or diff the device's live status)
  gives you the **truth on your actual hardware**: which UI feature maps to which packet, which
  transport actually works, and everything static missed.
- **Neither alone is enough.** The decompiled app is a *starting point*, not gospel — it may
  target a different/older model, and **the app you can decompile may not even be the working
  path.** (Real case: a device's Android app used Bluetooth Classic SPP and never worked; the
  device was actually driven over BLE GATT — only the iOS app worked. Static analysis of the
  Android app gave a perfect command catalog that went down the wrong pipe until dynamic checks
  caught it.)

Always confirm the transport and the command→feature mapping with dynamic evidence before you
build anything.

## The one-app-many-models problem (the catalog is a SUPERSET — find your model's subset)

A single vendor app almost always drives a whole **product family** from one binary, and the
decompiled command catalog is the **union of every model's features** — not what *your* device
supports. Treat the static catalog as a **superset to be filtered**, never as your device's
capability list. (Real case: the Divoom app is one APK with a ~120-opcode `CMD_TYPE` enum spanning
clocks, speakers with FM/SD/mic, 64-px panels, drawing pads, and an entire second-level "extern
command" sub-protocol — but a basic 11×11 TimeBox-mini implements only a fraction of it.)

**Why it bites:** you'll decompile a clean builder for a feature, send it, and get *nothing* — not
because your framing is wrong but because **that opcode isn't implemented on your model.** Without
expecting this you'll burn time debugging a frame that was never going to work.

**How to find which model supports what:**
1. **Static — find the model-gating, not just the catalog.** Grep for where the app branches on
   device type / product id / SKU before enabling a feature: a `DeviceType`/`productId` enum, per-model
   capability flags (`support_*`, `hasFm`, `is64` …), a downloaded/embedded capability table, or UI
   screens/buttons shown only for certain products. The device picker (the app's product carousel) and
   its per-product enable/disable logic is a map of the family. This tells you *the app's belief* about
   each model — still verify it.
2. **Ask the device what it is.** Where the protocol has a device-info/version query, send it: it
   returns a **model id + firmware version** you can map to a capability set. (Some models don't
   implement even this — see #3.)
3. **Dynamic = ground truth: probe-and-listen — but read silence carefully.** Send each candidate
   opcode to the *actual* device and watch for a reply. An **ack/echo or a GET reply ⇒ supported.**
   Silence is **asymmetric evidence**, and getting this wrong will mislabel features:
   - **Silence on a GET/query ⇒ strong "unsupported."** A query whose entire purpose is to return data
     but answers nothing is genuinely not implemented.
   - **Silence on a SET ⇒ ambiguous** — it may be a perfectly supported **fire-and-forget / set-only**
     command (plenty exist) that simply isn't acked. Do **not** call it unsupported on silence alone.
   Disambiguate a silent SET by: its **matching GET**, a **sibling GET in the same sub-protocol**, or
   an **operator eyeball** of the device (did the screen change?). (Worked example: the TimeBox-mini
   acks every core display/audio/tool/alarm/brightness opcode, but is silent to the **entire `0xBD`
   "extern command" sub-protocol** — and crucially its *GETs* (device-info, get-time) are silent too,
   which is what proves the whole sub-protocol — including `OPEN_SCREEN_CTRL` screen-power — is
   unimplemented on this model. Conversely, several silent *SETs* like the animation-frame and
   auto-power-off opcodes are real and work; their silence means "no ack," not "unsupported." When a
   silent SET has no GET to lean on, that's where the operator-in-the-loop closes it.) Probe the *safe*
   opcodes this way; never blind-fire destructive ones (OTA, factory-reset, name-change) to test
   support.
4. **Document support per model, not per app — and don't generalize a negative across the family.**
   Your device profile should state which opcodes are **Verified on this model**, which are **in the
   app but silent here (other-model)**, and which are **Unknown/untested**. Support is per
   *(model × opcode)*: "silent on model A" does **not** imply "silent on model B," even with the same
   app build. (Real miss-then-fix: an entire `0xBD` "extern command" sub-protocol was silent on a
   TimeBox-mini, so it got documented as "model-gated, silent on the family" — but a live app capture
   on the **Pixoo** of the *same* family showed the app both sending and receiving `0xBD`. The
   negative was real for one model and wrong as a family generalization.) Tag a negative with the
   model you proved it on, and re-verify per device.

This is a first-class part of the method, alongside transport determination: **static gives the
family superset; dynamic tells you your model's slice.**

## The operator is part of the loop (the human does real work — tell them so)

This methodology is a **two-person activity**, and the user is not a spectator. Much of what makes
the decode correct comes from a human at the physical device doing things software can't observe or
verify. Set this expectation at the start so they know what they're signing up for, then lean on it:

- **Trigger one change at a time, on cue.** The cleanest status-frame decode comes from the operator
  announcing an action ("setting speed to 1 now"), performing it on the device or vendor app, and you
  reading the resulting frame. On-demand, operator-announced reads beat free-running loggers — no
  attribution guesswork, no expired capture window.
- **Validate that the physical action actually happened.** You see bytes; only the human sees the
  motor move, the light change, the relay click. Ask them to confirm the real-world effect, not just
  that a packet went out — a command that's accepted on the wire but does nothing physically is a
  gating/precondition finding, and only the operator can tell you.
- **Read the device's own screen/indicators back to you.** This is how you nail units and mappings:
  the operator reads the on-device display ("it shows 40°C", "timer says 4:09") and you pair that with
  the captured byte. Screen cross-checks resolve scale factors, flag bits, and packed fields that are
  ambiguous from bytes alone.
- **Drive the hardware where you can't.** Pressing physical buttons, putting the device in a given
  mode/state, holding it in range, power-cycling — these are the operator's job. Make the asks
  specific and one-at-a-time, and wait for their "done" before reading.
- **Be explicit about turn-taking.** Tell the operator exactly what to do and what you'll do in
  response, so neither of you acts at the same time and muddies attribution.

(Worked example of this rhythm: decoding a massage chair frame by frame — the user changed one
setting at a time while seated in the chair, read the panel aloud, and confirmed each motion, while
the skill captured and diffed the notify frames. That back-and-forth *is* the method, not a
fallback.) Consent for the level of involvement is set up front — see `CLAUDE.md`, *Interview the
user FIRST*.

## Prerequisites — run this checklist before doing any work

After the consent interview (see `CLAUDE.md`, *Interview the user FIRST*), confirm you actually
have what the chosen workflow needs. **Walk this list explicitly with the user and don't start
until the "required" column for their workflow is satisfied** — half-starting and discovering a
missing piece wastes their tokens and time.

| Need | Required for | How to check / get it |
|---|---|---|
| **The app, as one of:** an **APK/XAPK on disk**, a **Play Store / APKPure link**, or an **app name** | static analysis (every workflow) | A link/name lets you fetch it with `apkeep` (ask first). No app at all ⇒ you can only do the *hardware-first* path (Phase 3+). |
| **A connected Android device** (`adb devices` shows it authorized) | the dynamic half (Phase 2 capture, command→feature mapping) | Optional. Without it you produce a verified *spec* but not on-hardware *truth* — flag the gap. |
| **The physical target device** (powered, in BLE/Classic range, not held by the vendor app) | validating control + decoding the status frame (Phase 4) | Required to ship a *verified* integration. Single-central: keep the vendor app off the link. |
| **A GitHub account + access** (and `gh` authenticated, or git push rights) | shipping: the HACS repo, and the eventual Core/docs/brands PRs | Required to deliver the objective. Confirm `gh auth status` early. For Core you'll also touch `home-assistant/core`, `home-assistant.io`, and `home-assistant/brands`. |
| **A Bluetooth host for HA** — an ESPHome/Shelly **proxy** near the device (BLE), a local adapter, or an **ESP32 (WROOM-32)** for Classic SPP | runtime (Phase 5) | BLE → proxy/adapter. Classic SPP → ESP32 bridge (HA can't speak SPP natively). |
| **Python + `jadx`, `adb`, `bleak`** on this machine | most phases | `command -v jadx adb`; `pip install bleak`. |
| **HA MCP server** (optional) | *convenience* for HA-side validation (Phases 4–6) | Structured tool access to a running HA — read entity state, call services, history/traces. Doesn't help the RE itself, and doesn't replace the raw WS calls this skill uses to free a BLE slot / watch advertisements. See [`docs/HA-MCP.md`](docs/HA-MCP.md) for setup, a working-confirmation check, and the token/privacy/convenience trade. If absent, fall back to the HA REST/WS API. |

State which workflow the prerequisites point to, what's missing, and what that means for the result
(e.g. "APK only, no device → I can give you a complete protocol spec + a HACS-ready integration,
but it's **unverified** until someone runs the Phase-4 work queue on real hardware"). Let the user
decide whether that's acceptable or they want to add a device.

## Cost & involvement — pick your tradeoff (the user decides)

Different workflows cost different amounts of **tokens** and demand different amounts of **human
involvement**. Spell this out so the user chooses with eyes open — there's no single right answer,
and comfort (e.g. not wanting to connect a phone) is a legitimate deciding factor.

The numbers below are **rough order-of-magnitude estimates** for a typical single device; real cost
scales with app size, protocol complexity, and how many iterations a decode takes. Use them for
*relative* tradeoffs, not as a quote.

| Workflow | Token cost | Human involvement | What you get | What you give up |
|---|---|---|---|---|
| **Static only** (APK/link, **no device**) | **Low** (~30–150k) | **Low** — provide the app, answer a few questions | Full protocol *spec*: framing, checksum, command catalog, status field list; a HACS-ready integration scaffold | **Unverified** — transport + byte map not confirmed on hardware; ships with a work queue someone must run later |
| **Static + dynamic, Claude drives** (ADB + UIAutomator) | **High** (~200k–600k+) | **Low–Medium** — connect a device + grant adb; occasional physical confirm | On-hardware *truth*: transport confirmed, each UI feature mapped to its packet, captured frames | Highest token use — every `uiautomator dump` is a large XML the model reads, across many iterations |
| **Static + dynamic, human drives** (operator-in-the-loop) | **Medium** (~80k–250k) | **High** — you tap the app/device, read the screen aloud, change one setting at a time on cue | Same on-hardware truth, far fewer tokens — *you* do the UI labor instead of automated dumps | Your hands-on time; slower wall-clock; needs you present at the device |
| **Status-frame decode** (part of the above) | adds **Medium–High** | **High** if human-driven, **Medium** if Claude-driven | The byte map → real sensors (the painstaking core) | Many capture/diff cycles; the dominant cost driver for rich devices |
| **Build + test + ship** (Phase 5/7) | **Medium–High** (~100k–300k) | **Low–Medium** — review the PR, approve pushes | The actual core-grade integration, tests, HACS repo, PRs | — |

The headline tradeoff to put to the user: **more automation = more tokens, less of your time;
more hands-on = fewer tokens, more of your time.** Driving UIAutomator yourself (Claude tapping
through the accessibility tree) is powerful and hands-off but is the **single biggest token sink**,
because each screen dump is a large XML the model must read and re-read every step. If a user is
cost-sensitive *or* wants to stay hands-on, the **operator-in-the-loop** path (you press the
buttons and read the screen, Claude captures and decodes) gets the same verified result for far
fewer tokens. If a user won't connect a device at all, **static-only** is completely fine — just be
explicit that the integration ships unverified with a checklist to finish later.

## Phase 0 — Recon & transport determination (do this FIRST)

The critical early fork: **Bluetooth Classic SPP/RFCOMM vs BLE GATT.** It dictates everything
downstream, and HA's Bluetooth stack is **BLE-only**.

Signals to determine transport:
- In the decompiled app: `BluetoothSocket` / `createRfcommSocketToServiceRecord` + UUID
  `00001101` ⇒ **Classic SPP**. `BluetoothGatt` / `BluetoothLeScanner` / `writeCharacteristic`
  ⇒ **BLE**.
- Does the app actually work? If the Android app "never worked" but iOS does → suspect a
  *different transport*. Tells:
  - The iOS app's device picker showing **CoreBluetooth UUIDs** (e.g. `702AB39E-…`) instead of
    MAC addresses ⇒ **BLE** (iOS hides BLE MACs). A MAC ⇒ Classic.
  - In iOS **Settings ▸ Bluetooth**: a system-paired **Classic** device shows with an ⓘ button;
    a **BLE** device an app is holding shows "Connected" *without* an ⓘ.
- Scan it: does the device expose a connectable BLE GATT server with a vendor service
  (`0xFFE0` / `0xFFF0`)? Then BLE is available regardless of what the Android app does.

Host implications:
- **BLE** → native to HA via Bluetooth proxies (ESPHome/Shelly) or a local adapter.
- **Classic SPP** → HA can't speak it; you need an ESP32 bridge (original ESP32 / WROOM-32 only —
  S3/C3 are BLE-only) running an SPP component, or an RFCOMM-host integration.

### A third case: passive advertisement (BLE broadcast — no connection)

Some BLE devices (many sensors: thermo-hygrometers, contact/motion, beacons) **never get connected
to at all** — they **broadcast** their state in the advertisement's *manufacturer data* / *service
data*, and the app (and HA) just decode it. Tells: the device's GATT exposes nothing useful, the app
reads values without pairing, or the HA matcher is `connectable: false`. This is the *simplest* host
case — any proxy/adapter passively scanning is enough, no slot/central contention, nothing to
disconnect. The "decode" is the advertisement byte map (Phase 4 applies to the advert instead of a
notify frame), and Phase 5 uses HA's **`PassiveBluetoothProcessorCoordinator`** (`connectable:
false`) rather than a connecting coordinator. Capture passively via
`bluetooth/subscribe_advertisements` — and note **proxy-visible ≠ phone-visible**: a good proxy hears
a weak broadcaster a cheap RE phone misses, so capture from the proxy/adapter.

> **Attribution trap: many instances of the SAME model broadcasting at once.** A passive matcher keyed
> on `company_id + service_uuid` (the usual case) matches *every* unit of a vendor's family in range —
> and a vendor-dense home can have several. **The first advertiser you see is not necessarily "the one
> on your desk."** (Real case: a single SwitchBot Outdoor Meter test turned up *three* model-`0x77`
> meters plus other SwitchBot gear; the first-seen unit at −68 dBm was an outdoor one, not the −30 dBm
> reference on the bench.) Pin the target by **RSSI + a stable per-unit id from the payload** (SwitchBot
> embeds the real MAC in the first manufacturer-data bytes), then **confirm with the operator** — the
> vendor app's *Device Info → MAC*, or the device's own display where it has one. Tag every per-unit
> negative with the unit you proved it on; "silent/absent on unit A" says nothing about unit B, even
> same model. (When the device has **no display** — many bare outdoor probes — the app's reading *is*
> your ground-truth cross-check; plan for that.)
>
> **Validate against a published integration when one exists (the "answer key").** If the device
> already has *any* shipped decoder — a merged HA Core integration, a maintained parser library
> (e.g. `govee-ble`), an ESPHome component — grade your reverse-engineered byte map against it on
> live data. Matching independently-merged code *and* the device's own display is the strongest
> validation there is, and it's how you learn exactly what core-quality looks like. (Bonus: where
> your decode and the library disagree, the device's screen breaks the tie — sometimes you've found
> a real upstream bug.)

## Phase 1 — Static analysis (decompile the APK)

1. **Get the APK.** Two paths:
   - **With a device:** `adb shell pm path <pkg>` → `adb pull <path>`.
   - **No device (the common case):** download it from APKPure with **apkeep** — you only need the
     package id. If the user hands you a **Play Store link**
     (`https://play.google.com/store/apps/details?id=<pkg>` or a search URL), the package id is the
     `id=` query param; if it's a search link with no `id=`, resolve it first (open the listing /
     `WebSearch` the app name → grab the `details?id=` URL). Then:
     - **Ask before downloading.** Confirm the resolved package id with the user and ask whether to
       proceed — e.g. *"Resolved this to `com.tang.etest.e_test`. Want me to install apkeep and pull
       the APK directly (no Android device needed)?"* (use `AskUserQuestion`). Downloading a
       third-party binary is an outward action, so get the nod first.
     - **Install apkeep if missing:** `cargo install apkeep` (Rust), or grab a release binary from
       `github.com/EFForg/apkeep`. Check `command -v apkeep` first.
     - **Download:** `apkeep -a <pkg> -d apk-pure <dir>`. This yields a `.apk` (or an `.xapk`/split
       bundle — unzip and use the base APK). **Verify you got the right package id** (the listing
       sometimes differs from what you searched).
   - Decompile with **jadx** (`jadx -d out app.apk`), then browse `out/sources/<pkg>/`. (Heads-up:
     some jadx flag combos — e.g. `-ds`/`--deobf` — write sources *flat* under the output root
     rather than `sources/<pkg>/`; if greps come up empty, search from the jadx root.)
   - **Persist the decompiled tree + the APK in a durable location (a repo), not `/tmp`** — RE you
     can't reproduce is RE you'll redo.
2. Find the **write path** and **framing**:
   - Classic: `BluetoothChatService` / `ConnectedThread.write()` — note that `write()` usually
     **wraps** the payload with start/end markers (e.g. SOI `0xF0` … EOI `0xF1`). The raw command
     bytes are NOT the wire frame. Find the authoritative builder (e.g. a `ClsUnit.getData()`):
     `F0 <type> <id> <checksum> F1`.
   - BLE: the `writeCharacteristic` call + the service/characteristic UUIDs.
3. **Catalog every command.** Grep the constants (`*_KEY_*`, `AUTO_MODE_*`, etc.) and the
   `sendMessage`/`buildFrame` code. Produce: friendly name → messageId → wire bytes, plus the
   **checksum formula** (e.g. `(~(0x83 + id)) & 0x7F`). Remember this catalog is the **family
   superset**, not your model's subset — also grab the **model-gating** (device-type/product-id
   branches, `support_*` flags) so you know which of these your device should even implement (see
   *The one-app-many-models problem*); dynamic probing in Phase 4 settles it.
4. Find the **gating logic** — which commands are dropped in which states (e.g. "blocked unless
   `runState != 0`"). This is *why your command does nothing* until a precondition is met.
5. Find the **status struct** — the class with the ~dozens of fields the app parses from inbound
   frames (e.g. `BluetoothTransfer`). The byte-offset parser is often "not decompiled," so treat
   this as the **menu of fields to hunt for** in Phase 4, not the offsets themselves.
6. Note bonding/security expectations (secure vs insecure RFCOMM, just-works SSP, PIN).

## Phase 2 — Dynamic analysis (ADB + UIAutomator + capture)

Goal: confirm transport works, and **match each UI feature to the packet/state it produces.**

First check you actually have a device: `adb devices` must show exactly one `device` (not
`unauthorized` — accept the on-phone RSA prompt — and not an unrelated TV box / emulator; if
several are attached, target one with `adb -s <serial> …`).

### Driving the UI by the accessibility hierarchy (not pixel taps)

Pixel coordinates break across screen sizes and layouts; the **UIAutomator XML hierarchy** is
robust. The loop is always **dump → find node → act → re-dump**.

1. **Dump and pull the current screen:**
   ```
   adb shell uiautomator dump /sdcard/u.xml && adb pull /sdcard/u.xml
   ```
2. **Find the node** by `text`, `resource-id`, or `content-desc` (content-desc is often the only
   label on icon-only buttons). Each node carries `bounds="[x1,y1][x2,y2]"`.
3. **Compute the tap center** from those bounds and tap it:
   `cx = (x1+x2)/2`, `cy = (y1+y2)/2` → `adb shell input tap <cx> <cy>`.
4. **Re-dump before the next interaction** — the hierarchy is a *snapshot*; after any tap or screen
   transition the old bounds are stale. Treat a fresh dump as mandatory per step, and add a short
   settle (`sleep 0.5`–`1`) after taps that animate or navigate.

A small helper that does dump→match→center→tap pays for itself immediately:
```bash
# uiauto.sh — drive an Android UI by accessibility label, not pixels.
#   uiauto.sh dump                 # pretty-print current screen's tappable nodes
#   uiauto.sh tap   "<substring>"  # tap center of first node whose text/desc/id contains it
#   uiauto.sh text  "<string>"     # type into the focused field
#   uiauto.sh back                 # system Back
set -euo pipefail
ADB=(adb)                              # e.g. ADB=(adb -s <serial>) for a specific device
_dump(){ "${ADB[@]}" shell uiautomator dump /sdcard/u.xml >/dev/null 2>&1 \
         || "${ADB[@]}" shell uiautomator dump --compressed /sdcard/u.xml >/dev/null; \
         "${ADB[@]}" exec-out cat /sdcard/u.xml; }
case "${1:-}" in
  tap)
    q="$2"
    # first node whose text|content-desc|resource-id contains the query → tap its center
    coords=$(_dump | tr '>' '>\n' | grep -iE "(text|content-desc|resource-id)=\"[^\"]*$q[^\"]*\"" | head -1 \
      | grep -oE 'bounds="\[[0-9]+,[0-9]+\]\[[0-9]+,[0-9]+\]"' \
      | grep -oE '[0-9]+' | paste -sd, -)
    [ -z "$coords" ] && { echo "no node matching: $q" >&2; exit 1; }
    IFS=, read x1 y1 x2 y2 <<<"$coords"
    "${ADB[@]}" shell input tap $(((x1+x2)/2)) $(((y1+y2)/2)) ;;
  text) "${ADB[@]}" shell input text "${2// /%s}" ;;
  back) "${ADB[@]}" shell input keyevent 4 ;;
  dump|"") _dump | tr '>' '>\n' | grep -oE '(text|content-desc|resource-id)="[^"]+"|bounds="[^"]+"' ;;
esac
```

### Interactions beyond a tap

- **Scroll to reach an off-screen node:** `adb shell input swipe <x1> <y1> <x2> <y2> <ms>` (e.g.
  swipe up: same x, large y → small y, ~300 ms), then re-dump. If a node isn't in the dump, it's
  not rendered — scroll until it appears.
- **Toggles / checkboxes / sliders:** tap the **row** (the labeled node), not the tiny widget; the
  switch usually has no text of its own. Confirm the flip by re-dumping and reading the widget's
  `checked="true|false"`. A slider you nudge with small swipes, reading the resulting value off the
  device's own screen.
- **Text entry:** focus the field (tap it), then `adb shell input text "…"` (`%s` for spaces);
  dismiss the keyboard / submit with `adb shell input keyevent 66` (Enter) or `4` (Back).
- **Navigation:** Back = `input keyevent 4`, Home = `3`. After navigating, **re-dump to confirm you
  landed on the expected screen** before acting (match on a known label).

### Gotchas

- **`uiautomator dump` fails** with "ERROR: could not get idle state" on screens with constant
  animation, video, or a WebView (the accessibility tree never goes idle). Retry; use
  `uiautomator dump --compressed`; or briefly stop the animation (pause a spinner). Last resort:
  fall back to a one-off pixel tap, but re-establish hierarchy control as soon as the screen settles.
- **Stale bounds** are the #1 silent failure — you tap where a button *used to be*. If a tap seems
  to do nothing, re-dump and verify the node is still there at those bounds.
- **`adb pull` of `/sdcard/u.xml`** can lag the write; `adb exec-out cat /sdcard/u.xml` (used above)
  avoids the pull round-trip and the staleness it invites.

### Capture what each press emits

With each press driven reproducibly, record what goes out the radio, best→worst:
- **HCI snoop log** (gold standard): Developer Options → "Enable Bluetooth HCI snoop log"
  (or `settings`/`getprop`), reproduce, pull `btsnoop_hci.log`, decode in Wireshark. Shows the
  exact bytes, the ATT/L2CAP channel, and which device. Often disabled by default and needs a BT
  restart to take effect; if unrooted you may not get it.
- **logcat**: the app's own `Log.d(...)` lines reveal `sendMessage`/connection attempts
  (secure→insecure→reflection fallbacks tell you the security mode).
- **Live status diffing** (if you have direct device access): subscribe to the device's status
  stream and diff it as you press each button (see Phase 4). This often *replaces* HCI snoop.
- `adb shell dumpsys bluetooth_manager` → bonded devices. Not bonded ⇒ the app uses
  insecure/no-pairing; match that in your client (e.g. `SEC_NONE`, not authenticate).

## Phase 3 — Find the characteristics (BLE) / channel (SPP)

- **BLE**: connect and **enumerate GATT** (Python `bleak`: `BleakScanner` → `BleakClient` →
  `client.services`; or nRF Connect; or an ESP32 scan). Identify:
  - the **command** characteristic (`write` / `write-without-response`, often `0xFFF1`/`0xFFE1`),
  - the **notify** characteristic (the status stream),
  - and ignore OTA/DFU services (e.g. Telink `00010203-…`).
  - Address caveat: the device may use a **rotating resolvable-private address (RPA)** — connect
    by *name* or bond+resolve; don't hardcode a MAC that rotates. (macOS/iOS expose a per-host
    CoreBluetooth UUID, not the MAC; **Android exposes the real MAC** — use it for HA.)
- **SPP**: SDP discovery → RFCOMM channel; match the phone's plain `RfcommSocket` (ERTM **off**)
  for finicky modules.

## Phase 4 — Validate control + decode the status frame

1. **Validate:** send a known command (framed *exactly* per Phase 1 — SOI/EOI + checksum) to the
   command characteristic; confirm a **physical effect AND a change in the status stream**. If
   nothing happens, check, in order: framing, gating precondition (power/run state first),
   security mode, wrong characteristic/channel.
2. **Decode the status frame byte-by-byte** — the painstaking core:
   - Subscribe to the notify char; capture the raw N-byte frame (`SOI … EOI`).
   - Change **one setting at a time** and diff. **On-demand reads triggered by the operator's
     announced action** ("set speed to 1" → read) beat free-running loggers: no window to expire,
     clean attribution. (If you must log continuously, run a *single* instance writing to one file
     — multiple stray loggers truncating the same file = garbage.)
   - Patterns to expect:
     - **Flag bits inflating a value:** a counter reading far too high often has flag bits in the
       high byte. (A "timer" read ~8191 too high; masking — `((b4 & 0x1F)<<7) | (b5 & 0x7F)` —
       matched the on-screen clock exactly. The high bits were a separate field, e.g. "part".)
     - **One byte packing several settings** (e.g. `b2 = heat(0x40) | speed(bits 2–4) |
       width(bits 0–1)`; `b3 = airbag-strength(low) | ionizer(0x40)`).
     - **Bit-shifted indices** (`(b1>>3)&7` = technique; `b13>>2` = program #).
     - **Live value vs. setting:** motion-heavy modes make some bytes oscillate (live roller
       width while kneading vs. the static setting while tapping). Surface "live" sensors only
       while running.
     - **Transport-dependent header/type bytes:** the same device can frame differently per
       transport. (Real case: the Atorch E_Test app decodes its **SPP** frames in a branch keyed
       on type byte `2`, but the meter's **BLE** frame — what HA decodes — carries type `0x03`.
       The *field offsets* matched exactly; only the type byte differed.) Validate the header/type
       against the transport HA actually uses, not just what the app's code checks.
   - **Cross-check against the device's own SCREEN** — have the operator read the display and
     pair it with the captured byte. This is how you nail units and mappings.
   - Use the Phase-1 field list as the menu of what to look for.
3. **Document the gaps honestly.** Not everything is reported: positions are often **command-only**
   (the device moves but never reports the resulting angle), some sub-levels are **set-only**, and
   some presets share an ID (**not individually distinguishable**). Write these down — they're
   real protocol limits, not your bug.

## Phase 5 — Build the Home Assistant integration

Pick the host:
- **BLE + you have ESPHome/Shelly Bluetooth proxies** (active connections) → a **HACS custom
  integration** is best. Connect through the proxy mesh via HA's stack
  (`bluetooth.async_ble_device_from_address(..., connectable=True)` +
  `bleak_retry_connector.establish_connection`). No hardware by the device.
- **BLE + no proxy near the device** → an **ESPHome BLE config** on an ESP32 next to it
  (`esp32_ble_tracker` + `ble_client`, write the command char, decode notify into sensors).
- **Classic SPP** → an ESP32 (original ESP32/WROOM-32) running an SPP component bridging to HA.

**Build it to Core standard from the start (see Objective).** The same code base ships as a HACS
custom integration *and* is one mechanical step from a Core PR. Structure:
- `protocol.py` — **pure** logic (build frames + parse status + the command catalog), **no HA
  deps**, **unit-tested against captured golden frames**. This is your reusable, PR-able spec.
- `coordinator.py` — a `DataUpdateCoordinator` that owns the BLE connection, subscribes to notify,
  pushes a decoded dataclass; **capped-backoff reconnect** + a **staleness watchdog** (tear down &
  reconnect if the link is up but frames stop). Store it on `entry.runtime_data`.
- `config_flow.py` — Bluetooth auto-discovery (manifest `bluetooth` matcher on `local_name`) +
  manual fallback; set a **unique_id** (the address) and `_abort_if_unique_id_configured()`.
- Entities — a **button per command**, sensors/binary-sensors per decoded field (ENUM sensors
  with `options` + translations), and a generic **`send_command` service** to fire any messageId
  from automations (covers the long tail without a button each). Every entity gets a stable
  `unique_id` and a `DeviceInfo`.
- `manifest.json`, `strings.json` + `translations/en.json`, `tests/`, and (HACS only) `hacs.json`.

### Home Assistant Core requirements — the bar a reviewer holds you to

The integration must satisfy these to be PR-able into core (they're also just good practice for
HACS). Treat it as the Phase-5 definition-of-done checklist:

- **Async, no blocking I/O in the event loop.** All BLE/file/network calls are `await`ed or run in
  the executor. Nothing blocks at import time.
- **Config flow only** (no YAML setup). Discoverable via the `bluetooth` matcher; manual fallback.
  Unique IDs on the entry and every entity; reject duplicates.
- **`manifest.json`** with: `domain`, `name`, `codeowners` (a real GitHub `@handle`),
  `config_flow: true`, `iot_class` (`local_push` for notify-driven), `integration_type: device`,
  `dependencies: [bluetooth_adapters]`, `bluetooth` matchers, `requirements` (PyPI-published,
  version-pinned, e.g. `bleak-retry-connector`), and **`quality_scale`**. (Core has **no `version`
  field** — that's HACS-only.)
- **DataUpdateCoordinator** pattern; `entry.runtime_data` for state; `async_setup_entry` /
  `async_unload_entry` clean teardown.
- **Tests** in `tests/components/<domain>/`: config flow at **100%** (all paths — success, already
  configured, cannot-connect), plus coordinator/protocol coverage. `protocol.py` tested against the
  **golden frames** you captured.
- **Passes `hassfest`** (manifest/services/strings validation), **`ruff`**, and **`mypy`**. Full
  type hints. `strings.json` + `translations/en.json` for every UI string and entity.
- **Integration Quality Scale:** declare and meet at least **Bronze** (`quality_scale.yaml` with
  each rule marked `done`/`exempt`). Aim Silver/Gold where the protocol allows.
- **Two companion PRs Core requires** (open alongside the code PR):
  - **docs** → `home-assistant/home-assistant.io` (a page under `source/_integrations/`),
  - **brand/logo** → `home-assistant/brands`.

### HACS ↔ Core delta (ship HACS now, PR Core later with minimal change)

Keep the difference mechanical so "make it core-ready" is never a rewrite:

| | HACS custom integration | Home Assistant Core |
|---|---|---|
| Location | `custom_components/<domain>/` | `homeassistant/components/<domain>/` |
| `manifest.json` `version` | **required** | **must be removed** |
| `hacs.json` | required (repo root) | not used (delete) |
| `codeowners` | nice | **required** (real handle) |
| Tests | encouraged | **required** (config-flow 100%) |
| `quality_scale` | optional | **required** (≥ Bronze) |
| Review | none | full core review + `hassfest`/CI |
| Docs + brands PRs | optional | **required** |

So: build under `custom_components/` with `hacs.json` + `version` so it installs today; the path to
core is *delete `hacs.json` + the `version` field, move the dir into `homeassistant/components/`,
confirm `codeowners`/`quality_scale`/tests, then open the code + docs + brands PRs.* Write the code
this way the first time.

Behavioral gotchas:
- **Single BLE central:** most devices accept ONE connection — keep the vendor app disconnected
  while HA controls it, or they fight over the slot.
- **Reconnect stalls / slot contention:** the link can get stuck (connect timeouts). HA's
  `bluetooth/subscribe_connection_allocations` (WS) shows per-proxy free slots — use it to tell
  *starvation* from a *device hang*.

## Phase 6 — Operational reliability & root-causing recurring stalls

For a device that periodically goes "stuck reconnecting," instrument it instead of just rebooting:
a watchdog that, **on a stall and before recovering**, captures the deciding signals:
- **Is the device still advertising?** (advertising + a reachable proxy has a free slot ⇒ a
  *connect/code* issue; not advertising ⇒ a *hardware/firmware* hang).
  - **Classic single-bond caveat — "advertising vs. pageable":** for a Bluetooth-Classic device
    that bonds to ONE host, *not advertising* does **not** automatically mean a hang. A box that's
    **bonded to another host (the vendor app / a second computer) and searching for it** will
    *answer a direct page* (forms a half-open, **un-authenticated** ACL — `hcitool con` shows
    `state 5`, no `AUTH ENCRYPT`, often a bogus handle like `0x0F00`), so it *looks* reachable, yet
    it **won't appear in an inquiry scan** and **won't complete a connection**. Disambiguate:
    inquiry-scan and confirm *other* devices (and any same-model sibling) show up — your scanner
    works; if the target is **absent while a sibling of the same model is present**, it's
    *connectable-but-not-discoverable* ⇒ **bonded elsewhere — free it / "Remove device" in the
    vendor app** (toggling the phone's BT off isn't enough; the bond lives in the app). A *truly*
    silent radio (no page response either) is the hardware/firmware hang. Clear the wedged ghost
    ACL with `hciconfig hciX down/up` (a `bluetoothctl disconnect` won't).
- Per-proxy **connection-slot allocations**, recent **coordinator log** entries, device **uptime**.
Then power-cycle (e.g. a smart plug) and log the recovery time. Accumulate incidents to a CSV to
distinguish a code bug from hardware — the evidence you need before filing a fix/PR.

## Tooling checklist
`jadx` (decompile) · `adb` + `uiautomator` (drive UI) · HCI snoop / `logcat` (capture) ·
`bleak` / nRF Connect / ESP32 (enumerate + control) · HA REST + WS API (`/api/states`,
`system_log/list`, `bluetooth/subscribe_advertisements`, `bluetooth/subscribe_connection_allocations`)
· ESPHome (proxy / SPP bridge) · `gh` + git (ship) · `hassfest` / `ruff` / `mypy` / `pytest` (core
gates) · HACS (install).

## Hard-won principles (the TL;DR)
1. **Build for Home Assistant Core from the start** — the deliverable is a HACS-installable,
   core-PR-able integration, not a one-off (see Objective). Retrofitting quality is the expensive path.
2. **Static = the spec; dynamic = the truth. Do both.**
3. **Verify the transport before building** — the decompiled app may not be the working path.
4. The **wire frame ≠ the payload** (framing markers + checksum).
5. Decode status by **one-variable diffs + screen cross-checks**; watch for flag bits, packed
   bytes, and live-vs-setting.
6. **Document the gaps** (command-only, set-only, indistinguishable) — they're protocol limits.
7. A **pure, unit-tested `protocol.py`** is your durable, PR-able artifact.
8. **Name the tradeoff** — more automation costs tokens, more hands-on costs the user's time; let
   them choose.

## Phase 7 — Contribute back (keep this skill improving)

This skill is a living library: every device you finish should make the next one easier. After you
ship an integration, **proactively offer to contribute a device profile** to
`github.com/dallanwagz/untether`:

1. Clone the repo (or a fork). Copy `examples/_TEMPLATE.md` →
   `examples/devices/<vendor>-<device>.md`.
2. Fill it from your **real** captures: transport (+ how confirmed), GATT chars / RFCOMM channel,
   the frame format + checksum, the command catalog, the status **byte map with at least one golden
   frame**, the key HA snippets (`build_frame` / `parse_status` / entity wiring), and the honest
   gaps.
3. Add a row to `examples/devices/README.md`.
4. If you discovered a technique or trap this methodology lacks, **edit `SKILL.md` too** — that's
   how the method (not just the catalog) improves.
5. Commit on a branch and open a **PR** (never push to `main`). **Redact secrets** (tokens,
   Wi-Fi/OAuth creds); BLE MACs and GATT UUIDs are fine.

See that repo's `CONTRIBUTING.md` and `CLAUDE.md` for the full convention.
