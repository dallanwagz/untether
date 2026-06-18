# Workflows, prerequisites & what's expected of you

This is the human-facing guide to using the `untether` skill: what it produces, the ways
you can run it, what you need before starting, and the cost/involvement tradeoffs so you can pick
the path that fits your comfort level and budget.

For the full methodology see [`../SKILL.md`](../SKILL.md); for how Claude behaves when you invoke it
(the consent interview, routing) see [`../CLAUDE.md`](../CLAUDE.md).

## The objective

The skill aims to deliver a **Home Assistant integration that installs out-of-the-box via HACS and
is structured to be submitted as a PR into Home Assistant Core** — so it's not just yours, it's
usable by everyone. That means a properly-built integration (pure unit-tested protocol module,
config flow, coordinator, tests, translations, quality-scale ≥ Bronze, passes `hassfest`/`ruff`/
`mypy`), not a personal script. The path from "installed via HACS" to "in Core" is kept mechanical.

You don't have to take it all the way to a Core PR — but the code is built so you *can*, with no
rewrite.

## How to start

1. **Tell Claude what you've got** — a Play Store/APKPure link, an APK file, an app name, and/or a
   connected Android phone. Whatever you have is fine; it determines the workflow.
2. **Answer the consent interview.** Before touching anything, Claude asks how you want to work —
   with a connected Android device (adb access) or device-free/static-only. **You decide**, and
   that choice is respected for the session. There's no wrong answer.
3. **Confirm the prerequisites** (below) for your chosen workflow.
4. **Go.** Claude works the phases; you play your role (below) where the workflow needs a human.

## Prerequisites

### Required (depends on workflow)

| You need… | For | Notes |
|---|---|---|
| The app — an **APK/XAPK**, a **store link**, or an **app name** | the protocol spec (almost everything) | A link/name lets Claude fetch it with `apkeep` (it asks first). No app at all ⇒ only the hardware-first path is possible. |
| A **GitHub account + access** (`gh` authenticated) | shipping the HACS repo and any Core/docs/brands PRs | Needed to actually deliver. Confirm `gh auth status`. |
| The **physical device** (powered, in range, vendor app disconnected) | a **verified** integration (decoding real status frames) | Without it you get an *unverified* spec + a checklist to finish later. |
| A **Bluetooth host for HA** — an ESPHome/Shelly proxy or local adapter (BLE), or an ESP32 WROOM-32 (Classic SPP) | the integration to run | BLE is native to HA via proxies; Classic SPP needs an ESP32 bridge. |

### Nice to have

- **A connected Android device with adb** — unlocks the dynamic half (confirming the transport,
  mapping each app feature to its packet). Optional but it's how you turn a *spec* into *truth*.
- **HCI snoop log access / a rootable device** — the gold-standard packet capture. Falls back to
  `logcat` and live status-diffing if unavailable.
- **A second/sibling device** — handy for the Classic "bonded-elsewhere" diagnostic.
- **Bluetooth proxies already in your HA** — lets the integration run with no hardware sitting next
  to the device.
- **The [HA MCP server](https://homeassistant-ai.github.io/ha-mcp/)** — gives Claude structured
  tool access to your running Home Assistant, which makes the validation steps (does the sensor
  update? does the service call work?) fast and clean. It doesn't help the reverse-engineering and
  isn't required, but it's *really* useful for validation. It's a deliberate privacy trade (a
  full-access HA token). See **[HA-MCP.md](HA-MCP.md)** for what it does/doesn't unlock, setup, how
  to confirm it's working before you start, and the token/privacy/convenience equation.

### Not required

- A rooted phone, paid tools, the vendor cloud account, or any specific OS — the toolchain is
  `jadx` + `adb` + `bleak` + `gh`, all free.

## The workflows (and what each costs you)

The numbers are **rough order-of-magnitude estimates** for one typical device. Real cost depends on
app size, protocol complexity, and how many decode iterations it takes. Use them for *relative*
comparison, not as a quote.

| Workflow | Need a device? | Token cost | Your involvement | Result |
|---|---|---|---|---|
| **Static only** | No | **Low** (~30–150k) | **Low** — provide the app, answer questions | Complete protocol *spec* + HACS-ready scaffold, **unverified** (ships with a work queue) |
| **Dynamic, Claude drives** (ADB + UIAutomator) | Yes | **High** (~200–600k+) | **Low–Medium** — plug in a phone, grant adb, occasional confirm | On-hardware truth, hands-off |
| **Dynamic, you drive** (operator-in-the-loop) | Yes | **Medium** (~80–250k) | **High** — you tap, read the screen aloud, change one thing at a time | Same verified truth, far fewer tokens |
| **Build + ship** (always, after the above) | — | **Medium–High** (~100–300k) | **Low–Medium** — review/approve PRs | The core-grade integration, tests, repo, PRs |

**The core tradeoff:** *more automation = more tokens, less of your time; more hands-on = fewer
tokens, more of your time.*

- Letting Claude drive the app through UIAutomator is powerful and hands-off, but it's the **single
  biggest token sink** — every screen snapshot is a large chunk of text the model reads and re-reads
  at each step.
- If you're cost-sensitive or happy to be hands-on, the **operator-in-the-loop** path gets the same
  verified result for far fewer tokens: you press the buttons and read the display, Claude captures
  and decodes.
- If you'd rather not connect a phone at all, **static-only** is completely legitimate — you just
  get an integration that's *unverified* until someone runs the included work queue on real hardware.

## What's required of you (the human's role)

This is a **two-person activity**. Software can read bytes; only you can act on and observe the
physical device. Depending on the workflow, expect to:

- **Decide and consent** — pick the workflow and your comfort level up front; you can change your
  mind mid-session.
- **Provide access** — the app (or link), GitHub auth, and (if you chose it) a phone with USB
  debugging on.
- **Drive the hardware on cue** — in the operator-in-the-loop path: change one setting at a time,
  press physical buttons, put the device in a given mode, hold it in range, power-cycle when asked.
  One change at a time, and tell Claude when it's done so captures attribute cleanly.
- **Validate that things actually happened** — confirm the motor moved / light changed / relay
  clicked, not just that a packet went out. A command accepted on the wire that does nothing is a
  real finding only you can report.
- **Read the device's own screen back** — "it shows 40°C", "timer says 4:09" — this is how units
  and mappings get nailed down.
- **Review and approve** — the contribution is a PR, never a silent push; you review before merge,
  and again before anything goes to Core.

If you chose static-only, your role is mostly the first two plus reviewing the result — at the cost
of an unverified integration you (or a future device) finish later.

## After it works

Every finished device should make the next one easier. Claude will offer to contribute a **device
profile** back to this repo (transport, frame format, command catalog, golden frames, gaps) and to
fold any new technique into the methodology — always as a reviewable PR. See
[`../CONTRIBUTING.md`](../CONTRIBUTING.md).
