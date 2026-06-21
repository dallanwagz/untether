<p align="center">
  <img src="assets/untether-logo.png" alt="untether — free your devices from their apps" width="680">
</p>

<p align="center"><strong>Local control. No cloud. No leash.</strong></p>

<p align="center">
  <strong>untether</strong> — reverse-engineer a Bluetooth/BLE gadget that's locked to its vendor app, and free it:
  decode its radio protocol and rebuild it as a local, cloud-free Home Assistant integration.
</p>

---

A [Claude Code](https://claude.com/claude-code) **skill** with a structured, phase-gated
methodology for reverse-engineering a Bluetooth / BLE consumer device (controlled by a vendor
Android or iOS app) into a **local Home Assistant integration** — no cloud, no vendor app.
*(Formerly `android-ble-to-ha`.)*

**The objective:** an integration that installs out-of-the-box via **HACS** *and* is structured to
be submitted as a **PR into Home Assistant Core**, so others can use it — a properly built, tested,
documented integration, not a one-off script. New here? Start with
**[docs/WORKFLOWS.md](docs/WORKFLOWS.md)** — workflows, prerequisites, the cost/involvement
tradeoffs, and what's required of you.

It covers the whole pipeline, and insists on doing **both** halves of the work:

- **Static** — decompile the APK (jadx): the write path, frame format (framing + checksum), the
  full command catalog, the command-gating logic, and the status-struct field list. *The spec.*
- **Dynamic** — drive the app over ADB + UIAutomator (accessibility-hierarchy taps, not pixels)
  and capture what each press emits (HCI snoop / logcat / live status diffing); enumerate GATT;
  match commands to features. *The truth on your actual hardware.*

…then decode the status frame byte-by-byte, and ship a HACS integration (pure unit-tested
`protocol.py`, a reconnecting coordinator with a staleness watchdog, config flow, entities, and a
generic `send_command` service).

See **[SKILL.md](SKILL.md)** for the full methodology, and **[examples/](examples/)** for real
artifacts from a worked project (a massage chair) — each shows an RE finding and the exact Home
Assistant code it became, from a decompiled Java frame builder all the way to live sensors.

For **Bluetooth Classic SPP** devices (which HA's BLE-only stack can't reach), the repo also ships
a hardware-verified bridge: **[`components/untether_spp`](components/untether_spp/)**, an ESPHome
external component for a classic ESP32 that RFCOMM-connects to **up to 4 SPP devices at once** (each
on its own TCP port, over one shared radio) and re-exposes their byte streams as TCP servers —
`nc <esp32-ip> 8888` and you're talking to a device. Verified driving 4 devices simultaneously
across two wire dialects (Pixoo NewMode + TimeBox byte-stuffed).

And the host-side toolkit is a pip-installable Python library, **[`python/`](python/)** (`untether-bt`):
the framing/codec engine, the SPP-bridge client (sync + async), a BLE advertisement decoder, and the
reverse-engineering pipeline (btsnoop parser → HCI/ATT extraction → UI-action↔wire-byte correlation)
— first-class Bluetooth **Classic** support the BLE-only ecosystem (bleak/HA/ESPHome) lacks. The
live ADB/jadx/Frida driver + SDP/GATT primitives are next on the roadmap.

## Install (as a Claude Code skill)

```sh
mkdir -p ~/.claude/skills/untether
cp SKILL.md ~/.claude/skills/untether/SKILL.md
```

Then invoke it in Claude Code with `/untether`.

## Contributing — a library that grows with every use

This is meant to get better each time someone uses it. After you take a device from app → HA,
contribute a **device profile** (copy [`examples/_TEMPLATE.md`](examples/_TEMPLATE.md) →
`examples/devices/`) so the next person starts further ahead — and improve `SKILL.md` if you found
a technique it's missing.

- **AI agents:** read [`AGENTS.md`](AGENTS.md) — the contract for contributing back (what to
  contribute, branch conventions, the quality bar).
- **Humans:** see [`CONTRIBUTING.md`](CONTRIBUTING.md). Both flow through the
  [PR template](.github/PULL_REQUEST_TEMPLATE.md).
- [`CLAUDE.md`](CLAUDE.md) drives the contribute-back loop when Claude uses the skill.

## Key principle

Static = the spec; dynamic = the truth. The app you can decompile **may not even be the working
transport** (e.g. an Android app speaks Classic SPP while the device is really driven over BLE by
the iOS app) — so verify the transport with dynamic evidence before building anything.
