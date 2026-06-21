# The Technique Catalog — everything this skill does to take a device from app → Home Assistant

A complete field-manual of the methods, procedures, and tradecraft this skill uses to reverse-
engineer a vendor-app-controlled Bluetooth device and rebuild it as a local, cloud-free Home
Assistant integration. This is the long-form companion to [`SKILL.md`](../SKILL.md): the *what* and
*why* of every move, drawn from real devices taken end-to-end.

**The mission in one line:** take a gadget you own, that only its phone app can talk to, and free it
— decode its radio protocol, rebuild it as a local integration, and verify the rebuild against
ground truth. No cloud. No vendor app. No guessing.

---

## 0 · The governing principles

1. **Static = the spec; dynamic = the truth. Do both.** Decompiling the app tells you *how* packets
   are built (framing, checksum, the full command catalog). Driving the real hardware tells you what
   actually works. Neither alone is enough — the app you can decompile **may not even be the working
   transport**.
2. **Build for Home Assistant Core from the start.** The deliverable is an integration that installs
   via HACS *and* is structured to be PR-able into HA Core — pure unit-tested protocol module,
   config flow, coordinator, tests, quality scale. Not a one-off script.
3. **Faithful, not fabricated.** Every byte map and golden frame comes from a real capture or real
   shipped code, tagged Verified / Inferred / Unknown. Guesses are labeled; gaps are documented.
4. **The human is in the loop.** Decoding is a two-person activity — software reads bytes, the
   operator acts on and observes the physical device.
5. **Authorized, defensive, consensual.** Own the target (or be authorized). Interview the user for
   consent and comfort before touching anything. Secrets live in a vault, never in git.

---

## 1 · Transport determination — the early fork that dictates everything

Before any decode, answer one question: **how does this device actually talk?** Three answers, each
a different world:

- **BLE GATT (connectable)** — connect, write a command characteristic, subscribe to a notify
  characteristic. Native to HA via Bluetooth proxies/adapters.
- **Bluetooth Classic SPP / RFCOMM** — a serial stream over an RFCOMM channel. HA *can't speak it*;
  needs a classic ESP32 (WROOM-32) bridge. This repo ships one:
  [`components/untether_spp`](../components/untether_spp/), a hardware-verified ESPHome external
  component that RFCOMM-connects to up to 4 devices at once and re-exposes each byte stream as its
  own TCP server, so HA / a `nc` client gets a clean pipe (mixed dialects on one ESP32 are fine).
- **Passive BLE advertisement (broadcast)** — the device never gets connected to at all; it
  *broadcasts* its state in the advertisement's manufacturer/service data. Simplest host case.

**The tells:** decompiled `BluetoothSocket` / `createRfcommSocketToServiceRecord` + UUID `0x1101`
⇒ Classic SPP; `BluetoothGatt` / `writeCharacteristic` ⇒ BLE; a `connectable: false` matcher or an
app that reads values without pairing ⇒ passive advertisement. iOS device-picker showing
CoreBluetooth UUIDs (not MACs) ⇒ BLE; a system-paired Classic device shows an ⓘ button.

**The #1 trap, proven in the field:** a device's Android app spoke Classic SPP and *never worked* —
the device was really driven over BLE GATT by the iOS app. Static analysis gave a perfect command
catalog that went down the wrong pipe until dynamic checks caught it.

---

## 2 · Static analysis — decompiling the app

- **Acquire the APK without a device or credentials:** `apkeep -a <pkg> -d apk-pure` straight from
  a Play Store link. Resolve a search link to its package id first. Unzip XAPK/split bundles.
- **Decompile with `jadx`**; persist the tree + APK in a durable repo (RE you can't reproduce is RE
  you'll redo). Watch for flat-vs-`sources/` layout depending on flags.
- **Find the write path and framing.** The wire frame ≠ the payload — `write()` usually wraps the
  bytes with start/end markers + a checksum (e.g. `F0 <type> <id> <cksum> F1`). Find the
  authoritative builder, not the raw command bytes.
- **Catalog every command** — friendly name → messageId → wire bytes, plus the **checksum formula**
  (recovered by reading the builder, e.g. `(~(0x83+id)) & 0x7F`, or a BCC = XOR of all bytes).
- **Find the command-gating logic** — which commands are dropped in which states. This is *why your
  command does nothing* until a precondition (power, run-state) is met.
- **The one-app-many-models problem.** One app binary drives a whole product family; the catalog is
  the **union of every model's features**, not your device's. Find the model-gating (`DeviceType` /
  `productId` / `support_*` flags) and treat the catalog as a **superset to filter** with dynamic
  probing. (Real case: one app, ~120 opcodes, an 11×11 display that implements a fraction of them.)

---

## 3 · Dynamic analysis — driving the app, capturing the radio

- **Drive the UI by the accessibility hierarchy, not pixels:** `uiautomator dump` → parse the XML →
  compute a node's center from its `bounds` → `input tap`. Re-dump every step (the tree is a
  snapshot; stale bounds are the #1 silent failure). Scroll/swipe to render off-screen nodes, type
  with `input text`, navigate with keyevents. A `uiauto.sh tap "<label>"` helper pays for itself.
- **Capture what each press emits, best→worst:** HCI snoop log (gold standard — enable "full",
  reproduce, `adb bugreport` → `btsnoop_hci.log` → `tshark -Y 'btspp && hci_h4.direction==0'`);
  app `logcat`; live status-diffing.
- **Map UI feature → packet → state.** Press one control, capture one frame, attribute cleanly.
- **Read silence carefully (asymmetric evidence):** silence on a **GET** ⇒ strong "unsupported";
  silence on a **SET** ⇒ ambiguous (could be a real fire-and-forget command). Disambiguate a silent
  SET with its matching GET or an operator eyeball.
- **Detect framing quirks on the wire:** byte-stuffing (escape `01/02/03`), multi-frame passthrough
  envelopes (e.g. a base64 `ptReal` wrapper), per-model dialect differences (channel, stuffing,
  raw-RGB vs palette) *within one app*.

---

## 4 · Finding the channel — GATT enumeration / RFCOMM discovery / advertisement keys

- **BLE:** enumerate GATT with `bleak` (or nRF Connect / an ESP32 scan) → identify the **command**
  characteristic (write), the **notify** characteristic (status), and ignore OTA/DFU services
  (Telink `00010203-…`, TI `F000FF…`). Beware rotating resolvable-private addresses — connect by
  name or by a stable id embedded in the payload, not a MAC that rotates.
- **SPP:** SDP discovery → RFCOMM channel; match the phone's plain `RfcommSocket` (ERTM off) for
  finicky modules. The `untether_spp` bridge handles both — pass the channel or `channel: 0` to
  SDP-discover — and lets you validate control over `nc` before any HA code.
- **Passive:** the advertisement *is* the channel — key on `local_name` prefix, 16-bit service UUID,
  and manufacturer company id.

---

## 5 · Decoding the status frame — the painstaking core

- **One variable at a time, on cue.** The operator announces an action ("set speed to 1 now"),
  performs it, and you read the resulting frame. On-demand operator-announced reads beat
  free-running loggers — no attribution guesswork, no expired window.
- **Cross-check against the device's own screen.** The operator reads the display ("it shows 40°C",
  "timer says 4:09") and you pair it with the captured byte. This nails units and scale factors.
- **Validate the physical effect, not just the packet.** A command accepted on the wire that does
  *nothing* physically is a gating/precondition finding — only the human can report it.
- **Patterns to expect:** flag bits inflating a value (high-byte flags — mask them); one byte packing
  several settings; bit-shifted indices; packed temp+humidity in a single integer
  (`temp=(v//1000)/10`, `hum=(v%1000)/10`, top bit = sign); live value vs. static setting; a fault
  sentinel (`FF FF FF`).
- **Document the gaps honestly** — command-only positions, set-only levels, indistinguishable
  presets. Real protocol limits, not your bug.
- **Validate against a published integration — the "answer key."** When the device already has a
  shipped decoder (a merged HA Core integration, a parser library like `govee-ble`/`pySwitchbot`, an
  ESPHome component), grade your independent byte map against it **on live data**. Matching
  independently-merged code *and* the device's own display is the strongest validation there is —
  and where they disagree, the screen breaks the tie (sometimes you've found a real upstream bug).

---

## 6 · The Home Assistant WebSocket API as a capture & control instrument

The HA stack itself is a powerful, proxy-backed BLE instrument — no extra hardware:

- **`bluetooth/subscribe_advertisements`** — capture raw manufacturer/service data for any device a
  proxy hears (decode passively without ever touching the device). The proxy hears weak broadcasters
  a cheap RE phone misses: **proxy-visible ≠ phone-visible** — capture from the proxy/adapter.
- **`bluetooth/subscribe_connection_allocations`** — per-proxy free connection slots; distinguishes
  *starvation* from a *device hang*.
- **Config-entry disable / reload** — free a single-central BLE slot so the vendor app (or a raw
  client) can connect, without un-pairing.
- **`get_states` / entity & device registries** — read what HA Core already decodes for a device
  (the live answer-key comparison), and discover which models the user actually owns.

---

## 7 · Building the integration — Core-grade from the first commit

- **`protocol.py`** — pure logic (build frames + parse status + command catalog), **no HA deps**,
  **unit-tested against captured golden frames.** The durable, PR-able artifact.
- **Coordinator** — a `DataUpdateCoordinator` (connectable BLE) or `PassiveBluetoothProcessorCoordinator`
  (`connectable: false`, advertisement-driven), or — for a Classic-SPP device behind the
  `untether_spp` bridge — a coordinator that opens an `asyncio` TCP stream to `tcp://<esp32>:port`
  and reads the same framed bytes; all on `entry.runtime_data` with capped-backoff reconnect + a
  staleness watchdog. The bridge is transparent, so `protocol.py` is identical regardless of
  transport.
- **Config flow** — Bluetooth auto-discovery (manifest matcher on `local_name`) + manual fallback;
  `unique_id` = address; abort-if-configured.
- **Entities** — a button per command, sensors/binary-sensors per decoded field (ENUM sensors with
  translations), a generic `send_command` service for the long tail.
- **Core bar:** async / no blocking I/O; `manifest.json` (matchers, `iot_class`, pinned PyPI
  requirements, `codeowners`, `quality_scale`); tests (config flow 100%); passes
  `hassfest`/`ruff`/`mypy`; ≥ Bronze on the Integration Quality Scale; docs + brands companion PRs.
  The **HACS↔Core delta** is mechanical (drop `version`/`hacs.json`, move the dir, open the PRs).

---

## 8 · Operational reliability — root-causing recurring stalls

Instrument, don't just reboot. On a stall, *before* recovering, capture the deciding signals:

- **Is the device still advertising?** (advertising + a free proxy slot ⇒ a connect/code issue; not
  advertising ⇒ a hardware/firmware hang.)
- **Classic single-bond "advertising vs. pageable" caveat:** a Classic device bonded to another host
  answers a direct page with a half-open un-authenticated ACL (looks reachable) but won't appear in
  an inquiry scan or complete — disambiguate with a same-model sibling, free the bond *in the vendor
  app* (toggling phone BT isn't enough), clear the ghost ACL with `hciconfig down/up`.
- Accumulate incidents to a CSV; power-cycle via a smart plug and log recovery time. The evidence to
  tell a code bug from hardware before filing a fix.

---

## 9 · Verification tradecraft — trust nothing, prove everything

- **Golden frames as regression anchors** — every decode pinned to ≥1 full hex frame with its
  decoded meaning, unit-tested.
- **Four-way agreement** — hand-decode == parser library == vendor app display == app source code.
- **Adversarial review of contributions** — treat empirical claims as guilty-until-verified.
  (Real case: a contributed profile's "live captures" were checked by querying the network for the
  cited device MACs and decoding their live advertisements against HA Core — confirming the byte map
  matched reality before merge. A fabricated version would have failed that exact check.)
- **Self-correction with stronger evidence** — when a *merged* claim turns out wrong, walk it back
  with wire evidence. (Real case: a "model-gated, silent on the family" claim from one unit was
  corrected by a live app capture on a sibling that showed the opposite — support is per
  (model × opcode), and a negative is only proven on the unit you tested.)

---

## 10 · The contribution flywheel — a library that compounds

Every finished device makes the next one easier. After shipping, contribute back a **device
profile** (byte map + golden frames + the honest gaps) and any new **technique** the methodology
lacked, as a reviewed PR (`device/ method/ fix/ example/ docs/` branch, conventional commits, never
push to main). Agents and humans follow the same contract ([`AGENTS.md`](../AGENTS.md)). The result
is a self-improving body of tradecraft — and a growing trophy wall.

---

## The toolchain

`apkeep` (credential-free APK pull) · `jadx` (decompile) · `adb` + `uiautomator` (drive the UI) ·
HCI snoop / `tshark` / `logcat` (capture) · `bleak` / nRF Connect / ESP32 (enumerate + control) ·
the HA REST + WebSocket API (capture/control via the proxy mesh) · ESPHome (BLE proxy, and the
`untether_spp` Classic-SPP↔TCP bridge in this repo) ·
`pytest` + `pytest-homeassistant-custom-component` / `hassfest` / `ruff` / `mypy` (Core gates) ·
HACS (ship) · macOS Keychain / `sops`+`age` (secrets, never git).

## Devices taken end-to-end (the trophy wall)

| Device | Transport | What it taught |
|---|---|---|
| Rongtai / Infinity massage chair | BLE GATT (svc 0xFFF0) | the reference walkthrough; SPP-app-but-BLE-device transport trap; operator-in-the-loop decode |
| Atorch J7-C USB power meter | Dual BLE GATT + Classic SPP | transport-dependent type bytes; control-as-answer-key |
| Divoom TimeBox-mini | Classic SPP (ch4, byte-stuffed) | RFCOMM, byte-stuffing, the single-bond trap |
| Divoom Pixoo 16 | Classic SPP (ch2, MiniToo transport) | per-model dialect within one app; app-driven HCI capture; one-app-many-models |
| Govee H5075 / H5104 | Passive BLE advertisement | the passive pattern; packed temp/humidity; answer-key validation vs merged core |
| SwitchBot W3400010 | Passive BLE advertisement | mfr-data vs service-data split; the multi-instance attribution trap; survived adversarial review |

---

*Static gives the spec. Dynamic gives the truth. The operator gives the ground. The answer key keeps
us honest. The library remembers.*
