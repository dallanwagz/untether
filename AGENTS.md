# AGENTS.md — instructions for AI agents working in this repo

This file is the contract for any AI coding agent (Claude Code, Codex, Cursor, Copilot, etc.) that
clones this repo to do reverse-engineering work and contribute back. If you are an agent, **read
this first.** Humans: see [`CONTRIBUTING.md`](CONTRIBUTING.md) (same workflow, more prose).

## What this repo is

A **living skill** — [`SKILL.md`](SKILL.md) is a phase-gated methodology for turning a
vendor-app-controlled Bluetooth/BLE device into a local Home Assistant integration — plus a
**growing library of device profiles** under [`examples/devices/`](examples/devices/). The goal of
every integration is one that installs via **HACS** *and* is structured to be PR-able into **Home
Assistant Core**. See `SKILL.md`'s *Objective* section.

## The prime directive: leave the library better than you found it

This skill improves only if each use feeds back what it learned. **After you take a device from app
→ HA (or discover a technique, trap, or pattern the methodology lacks), contribute it back as a
pull request.** That is the entire point. Do it proactively — don't wait to be asked.

## Read order (do this before contributing)

1. **`AGENTS.md`** (this file) — the contribution contract.
2. **`SKILL.md`** — the methodology you'll follow and possibly improve.
3. **`CONTRIBUTING.md`** — contribution detail + the "what makes a good profile" bar.
4. **`CLAUDE.md`** — Claude-specific behavior (consent interview, routing); other agents can skim it
   for the operating norms.
5. **`examples/devices/_TEMPLATE.md`** + an existing profile (e.g. `atorch-j7c-usb-meter.md`) — copy
   the shape.

## What to contribute (pick the type that fits)

| Type | Where it goes | Branch prefix |
|------|---------------|---------------|
| **Device profile** (a new gadget you RE'd) | `examples/devices/<vendor>-<model>.md` (+ a row in `examples/devices/README.md`) | `device/` |
| **Methodology improvement** (new technique/trap/pattern) | edit `SKILL.md`; phase-level patterns may add a numbered walkthrough | `method/` |
| **Correction** (fix a wrong/outdated claim in a profile or SKILL.md) | the file in question | `fix/` |
| **Worked integration / reference** (a complete, tested integration example) | `examples/integrations/<name>/` | `example/` |
| **Docs** (clarify/expand guidance) | the doc | `docs/` |

A single PR should be **one logical contribution.** Split unrelated changes.

## How to contribute (the workflow)

1. **Do the work** using `SKILL.md`. Capture real evidence (golden frames, GATT/RFCOMM details,
   command catalog, the honest gaps).
2. **Branch** off `main` with the prefix above, e.g. `device/govee-h5075`, `method/passive-adv-host-range`.
3. **Fill the artifact.** For a device profile, copy `examples/_TEMPLATE.md` and fill every section
   from real captures. Tag each claim **Verified** (proven on hardware), **Inferred** (from code, not
   confirmed), or **Unknown** — never present a guess as fact.
4. **Self-check against the quality bar** (below) before opening the PR.
5. **Open a PR** filling [`.github/PULL_REQUEST_TEMPLATE.md`](.github/PULL_REQUEST_TEMPLATE.md).
   **Never push to `main`.** Use [Conventional Commits](https://www.conventionalcommits.org/) for
   commit messages (`feat:`, `fix:`, `docs:`).
6. **Stop at the PR.** A human reviews and merges. Don't self-merge.

## Quality bar (non-negotiables — a reviewer will hold you to these)

- **Faithful, not fabricated.** Every byte map, golden frame, and snippet comes from a real capture
  or real shipped code. Label guesses; document unknowns. If you can't verify something, say so.
- **At least one real golden frame** per status/advertisement decode (full hex + decoded meaning),
  so the mapping is reproducible and testable.
- **Redact secrets.** No tokens, Wi-Fi/OAuth/account creds, or API keys in committed files *or* PR
  text. BLE MACs, GATT UUIDs, and RFCOMM channels are fine. Scrub personal data from log excerpts.
  Never aggregate secrets into a repo (even private). A credential the validation genuinely needs
  goes in Keychain / an encrypted vault — see [`docs/SECRETS.md`](docs/SECRETS.md).
- **Show the transition.** Connect each RE finding to the concrete HA artifact it became (a button,
  a sensor, a service) — that's the point of the library.
- **Authorized targets only.** Work on hardware/software the user owns or is authorized to analyze.
  Don't connect to / pair with a device whose ownership is unclear; passive observation of a
  broadcast HA already receives is fine, actively connecting to someone else's device is not.
- **Be honest about limits.** If a refusal or a dead end is the right answer, say so plainly rather
  than working around it.

## Self-correction is welcome

If you find that a *previously merged* profile or methodology claim is wrong, **open a `fix/` PR that
walks it back with evidence.** Correcting the record (with stronger evidence) is exactly how the
library earns trust — see the git history for prior examples.

## Keep the installed skill in sync

`SKILL.md` here is the source of truth. If you edit it and you also have a local install at
`~/.claude/skills/untether/SKILL.md`, update that copy too (it's a mirror).
