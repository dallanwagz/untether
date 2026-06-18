# CLAUDE.md — untether

This repo is a **living skill + a growing examples library** for reverse-engineering a
Bluetooth/BLE consumer device (controlled by a vendor Android/iOS app) into a local Home Assistant
integration. It is meant to get **better with every use**: each time the skill is applied to a new
device, that device's findings should be contributed back as a new example.

**Objective (the bar every run aims for):** produce an integration that installs out-of-the-box via
**HACS** *and* meets the requirements/guidelines to be **PR'd into Home Assistant Core** — a
properly built, tested, documented integration, not a one-off. Build to that standard from the
start; `SKILL.md` Phase 5 has the Core checklist and the HACS↔Core delta. Human-facing workflows,
prerequisites, and the cost/involvement tradeoffs live in [`docs/WORKFLOWS.md`](docs/WORKFLOWS.md).

## Interview the user FIRST (consent & comfort — do this before anything else)

Before you scan, download, decompile, or touch a device, **ask the user how they want to work.**
This is a trust matter, not a formality: the user decides how the skill behaves based on their own
comfort level, and you respect that choice for the rest of the session. Do not assume, and do not
nudge them toward the more invasive option.

Ask, plainly, which approach they want:

1. **With a connected Android device (adb access).** Unlocks the full **dynamic** half — driving the
   app, capturing what it emits, confirming the transport on real hardware. Be explicit about what
   this involves so consent is informed: USB debugging enabled, an `adb` connection from this
   machine, you reading the screen hierarchy / installing the vendor APK / capturing Bluetooth
   traffic **on the device they plug in**. Tell them what you will and won't touch.
2. **No device — static / off-device only.** Decompile an APK they provide or that you download
   (with their OK), produce the protocol spec, and hand them a checklist of what to confirm later.
   Slower to full truth, but nothing connects to their hardware.

Make clear there's no wrong answer and they can change their mind mid-session (start static, attach
a device later; or stop using the device at any point). If they're unsure, explain the trade-off in
one line and let them pick. **Their stated comfort level is a hard boundary** — if they chose
no-device, don't later reach for adb without asking again.

(For physical-action expectations once a device or the hardware is involved, see *The operator is
part of the loop* in `SKILL.md` — the user has a real, hands-on role and should know it up front.)

**Optional validation accelerator — HA MCP.** If the user has the
[HA MCP server](https://homeassistant-ai.github.io/ha-mcp/) connected, the HA-side validation
(read entity state, call services, traces) becomes clean tool calls instead of hand-rolled
REST/WS. Mention it as *optional* during setup, have them confirm it works before starting (see
[`docs/HA-MCP.md`](docs/HA-MCP.md)), and respect the privacy trade — it needs a full-access HA
token, so never push it; if they decline, fall back to the REST/WS API. It does **not** help the RE
itself and does **not** replace the low-level Bluetooth WS calls (advertisement / connection-slot
diagnostics, config-entry disable) the skill sometimes needs.

## Supported entry paths (within the lane the user chose)

Once the user has picked their comfort lane, figure out the mechanical specifics from what they
give you and proceed — **state your read and confirm, don't silently route across the
device/no-device boundary they set.** Only ask again when a step is a new outward action
(downloading a binary, connecting hardware) or genuinely ambiguous.

| The user gives you… | Path | What the skill does |
|---|---|---|
| A **Play Store / APKPure link** or just an **app name** | *No device* | Resolve the package id from the link (or `WebSearch` the name → `details?id=`). Confirm the id and **ask before downloading** (apkeep is a third-party fetch). Install apkeep if missing (`cargo install apkeep`), pull with `apkeep -a <pkg> -d apk-pure <dir>`, then jadx. → SKILL Phase 1. |
| An **APK / XAPK file** already on disk | *No device* | Skip the download. Unzip an XAPK to its base APK, jadx straight away. → Phase 1. |
| **A plugged-in Android device** (`adb devices` shows it) | *With device* | `adb shell pm path <pkg>` → `adb pull`. This unlocks the **dynamic** half too: UIAutomator-driven taps, HCI snoop, logcat. → Phases 1–2. Prefer this when available — static alone is just the spec. |
| **No app at all**, but the **physical device** in hand | *Hardware-first* | Skip static; scan/enumerate GATT directly (`bleak`/nRF Connect), then decode the status frame by one-variable diffs + screen cross-checks. → Phases 3–4. Static can come later if an APK turns up. |
| Their **own findings** from a finished project | *Contribute* | Go straight to the self-improvement loop below — capture it as a device profile. |

Cross-cutting, regardless of path:
- **Transport first (Phase 0).** BLE GATT vs Classic SPP decides everything downstream and HA is
  BLE-only. Determine it before building — and remember the app you can decompile may not be the
  working transport.
- **Static and dynamic are complementary, not alternatives.** A no-device path gives you the spec
  but not the truth on real hardware; flag that gap and close it as soon as a device or the
  physical unit is available.
- **Persist what you pull** (APK + decompiled tree) in a durable place, not `/tmp`.

## The self-improvement loop (do this proactively)

When you (Claude) have used [`SKILL.md`](SKILL.md) to take a device from app → HA — **or** the user
brings findings from such a project — offer to capture it as a contribution:

1. Copy [`examples/_TEMPLATE.md`](examples/_TEMPLATE.md) → `examples/devices/<vendor>-<device>.md`
   (kebab-case, e.g. `rongtai-evolution-chair.md`).
2. Fill it from the project's **real** captures: transport + how it was determined, GATT
   chars / RFCOMM channel, the frame format + checksum, the command catalog, the status byte map
   **with golden frames**, the key HA snippets (`build_frame`/`parse_status`/entity wiring), and the
   honest gaps.
3. Add a row to the device table in [`examples/devices/README.md`](examples/devices/README.md).
4. If the project also taught a *new technique or gotcha not in the methodology*, improve
   `SKILL.md` (and, if it's a phase-level pattern, add/extend a numbered walkthrough doc).
5. Commit on a **branch** (prefix `device/ method/ fix/ example/ docs/`) and open a **PR** filling
   [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md) — never push to `main`
   directly. The full contributor contract (for any agent) is [`AGENTS.md`](AGENTS.md).

Keep the installed skill in sync: this repo's `SKILL.md` is the source of truth; if you edit it,
also update `~/.claude/skills/untether/SKILL.md` (a copy).

## Non-negotiables for contributions

- **Faithful, not fabricated.** Every byte map, golden frame, and snippet must come from real
  hardware captures or real shipped code. If a field is a guess, label it; if something isn't
  reported by the device, say so (the "honest gaps" section exists for this).
- **Redact secrets.** No HA long-lived tokens, Wi-Fi credentials, OAuth/eWeLink creds, or API
  keys. Device BLE MACs and GATT UUIDs are fine. Scrub personal identifiers from log excerpts.
- **Show the transition.** Every example must connect an RE finding to the concrete HA artifact it
  became (a button, a sensor, a service) — that's the point of the library.
- **Link the integration** if it's public (HACS repo / ESPHome config), but the example must stand
  on its own.

## Operating notes (scope & etiquette)

This skill does **authorized, defensive** interoperability work: reverse-engineering apps and
devices the user owns so they can be driven locally from Home Assistant, no cloud or vendor app.
A few ground rules keep that clean:

- **Authorized targets only.** Work on hardware/software the user owns or is explicitly authorized
  to analyze. If a task's scope is unclear (a device that isn't theirs, a service whose terms you'd
  be breaking), ask before proceeding — don't assume.
- **Be honest about refusals.** If some specific request can't be done, say so plainly and explain
  why, so the user can decide how to proceed. Don't reword or reroute a request to get past a
  decision — surface it. A clear "I won't do X, here's why" is more useful than a quiet workaround.
- **Secrets stay out** (also in *Non-negotiables* above): no HA tokens, Wi-Fi/OAuth/eWeLink creds,
  or API keys in committed files or pasted output. BLE MACs and GATT UUIDs are fine. A credential
  the validation genuinely needs goes in Keychain / an encrypted vault, never plaintext-in-git —
  [`docs/SECRETS.md`](docs/SECRETS.md). Don't aggregate secrets into a repo, even a private one.
- **Confirm before outward or irreversible actions.** Writing to a peripheral, changing pairing/
  bonding, OTA/firmware flashes, or RF transmits can brick a device or affect others nearby — get
  an explicit go-ahead first, and prefer read-only enumeration until you understand the target.
- **Single BLE central etiquette.** Most devices accept one connection; keep the vendor app
  disconnected while you hold the link, and hand it back when done so the user isn't locked out.
- **Capture, don't fabricate.** Decoders and byte maps come from real captures verified against a
  golden frame (see *Non-negotiables*). An unverified guess is labeled as one.

## Layout

- `SKILL.md` — the phase-gated methodology (the source of truth; mirrored to `~/.claude/skills/`).
- `examples/01..05-*.md` — the annotated **reference walkthrough** (one device, phase by phase).
- `examples/_TEMPLATE.md` — the device-profile template for new contributions.
- `examples/devices/` — one concise profile per contributed device (the growing library).
- `CONTRIBUTING.md` — the human-facing contribution guide (same loop, more detail).
- `docs/WORKFLOWS.md` — human-facing: the objective, supported workflows, prerequisites
  (required / nice-to-have), the cost-vs-involvement tradeoffs, and the human's role.
- `docs/HA-MCP.md` — the optional HA MCP prerequisite: capability doc (can/can't do), setup +
  working-confirmation, and the token/privacy/convenience trade.
- `docs/SECRETS.md` — how to keep the credentials your validation needs (Keychain / encrypted
  vault), never plaintext-in-git; what is / isn't a secret.

## Conventions

- Examples are Markdown; prefer short, real code/data excerpts over full file dumps.
- Reference bytes in the documented form (`b1`, `(b2>>2)&7`, etc.) and include at least one full
  golden frame per status decode so it's testable.
- One device per `examples/devices/*.md`. Keep the reference walkthrough (01–05) as the teaching
  path; new devices go in `devices/`.
