# Contributing

This library gets better every time someone uses the skill and feeds back what they learned —
**device profiles** (one per gadget taken from its app into Home Assistant) and **methodology
improvements** (techniques, traps, and patterns the method was missing). Contributions from humans
and from AI agents (via the skill) are both welcome and follow the same workflow.

> **Using an AI agent?** Point it at [`AGENTS.md`](AGENTS.md) — that's the machine-readable contract
> for contributing back. This page is the human-facing version of the same thing.

## The idea

The more devices and hard-won lessons accumulate here, the further ahead the next person starts.
So after you take a device app → HA, or discover something the methodology lacks, **open a pull
request.** Do it proactively.

## What you can contribute

| Type | Where it goes | Branch prefix |
|------|---------------|---------------|
| **Device profile** — a gadget you reverse-engineered | `examples/devices/<vendor>-<model>.md` + a row in `examples/devices/README.md` | `device/` |
| **Methodology improvement** — a new technique/trap/pattern | edit `SKILL.md` (phase-level patterns can add a numbered walkthrough) | `method/` |
| **Correction** — fix a wrong/outdated claim (with evidence) | the file in question | `fix/` |
| **Worked integration / reference** — a complete, tested example | `examples/integrations/<name>/` | `example/` |
| **Docs** — clarify or expand guidance | the doc | `docs/` |

## Add a device profile

1. Use the skill ([`SKILL.md`](SKILL.md)) to take your device from app → HA.
2. `cp examples/_TEMPLATE.md examples/devices/<vendor>-<device>.md` (kebab-case).
3. Fill every section from your **real** captures — tag each claim **Verified** / **Inferred** /
   **Unknown**.
4. Add a row to the table in [`examples/devices/README.md`](examples/devices/README.md).
5. Open a PR on a `device/` branch (never `main`), filling the
   [pull request template](.github/PULL_REQUEST_TEMPLATE.md).

## What makes a good profile

- **Transport stated and justified** (Classic SPP vs BLE GATT vs passive advertisement, and how you
  confirmed it).
- **A real golden frame** for the status/advertisement decode — at least one full hex frame with its
  decoded meaning, so the mapping is reproducible/testable.
- **The command frame format + checksum**, and the command catalog (a table is fine).
- **The transition shown**: the HA snippet (button / sensor / service) each finding became.
- **Honest gaps**: what the device does *not* report (command-only positions, set-only levels,
  indistinguishable presets). These save the next person hours.

## Improving the methodology

If your project surfaced a technique or trap not covered in `SKILL.md` (a new way to capture
packets, a new decode pattern, a host/proxy gotcha), edit `SKILL.md` too — that's how the *method*
improves, not just the examples. Ground it in the **real case** that surfaced it, not abstract
advice. Phase-level patterns can also extend the numbered walkthrough.

## Corrections & self-correction

Found that a *merged* profile or claim is wrong? Open a `fix/` PR that walks it back **with stronger
evidence** (wire captures, golden frames). Correcting the record is how the library earns trust —
the git history has prior examples where a second pass corrected the first.

## Workflow & conventions

- **Branch** off `main` with the prefix above; **never push to `main`.**
- **One logical contribution per PR.** Split unrelated changes.
- **[Conventional Commits](https://www.conventionalcommits.org/)** for messages (`feat:`, `fix:`,
  `docs:`).
- Fill the **[PR template](.github/PULL_REQUEST_TEMPLATE.md)**; a human reviews and merges (don't
  self-merge).
- External contributor? **Fork → branch → PR.** Collaborators can branch directly.

## Ground rules (non-negotiable)

- **No fabrication.** Real captures and real shipped code only. Label guesses; document unknowns.
- **Redact secrets** — no tokens, Wi-Fi/OAuth/account creds, API keys, in files *or* PR text; scrub
  personal data from logs. (BLE MACs, GATT UUIDs, and RFCOMM channels are fine.) Need to *keep* a
  credential for ongoing validation? See [`docs/SECRETS.md`](docs/SECRETS.md) — Keychain or an
  encrypted vault, never plaintext-in-git.
- **Authorized targets only** — your own hardware, or devices you're authorized to analyze.
- Keep snippets short and faithful; link the full integration repo if it's public.
- Be respectful of device vendors and other contributors.
