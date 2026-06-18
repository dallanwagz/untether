<!--
Thanks for contributing back to the skill! Fill this out so a reviewer can merge with confidence.
Agents: see AGENTS.md. One logical change per PR. Never push to main.
-->

## What this contributes

<!-- One or two sentences. Which type? device profile / methodology improvement / correction /
     worked integration / docs. What device or technique? -->

- **Type:** <!-- device profile | method | fix | example | docs -->
- **Device(s):** <!-- vendor + model, or "n/a" -->
- **Transport:** <!-- BLE GATT | Classic SPP | passive advertisement | n/a -->

## What's novel / why it's worth landing

<!-- The reusable lesson: a new technique, a confirmed byte map, a corrected claim, a host gotcha.
     If it corrects something already merged, say what was wrong and what the new evidence is. -->

## Evidence (faithful, not fabricated)

- [ ] Every claim is tagged **Verified** / **Inferred** / **Unknown** (no guess presented as fact)
- [ ] At least one **real golden frame** (full hex + decoded meaning) for each decode
- [ ] The **transition is shown** — each finding maps to a concrete HA artifact (button/sensor/service)
- [ ] Honest **gaps** documented (command-only / set-only / indistinguishable / not reported)

<!-- Paste the key golden frame(s) here so a reviewer can recompute: -->
```
<golden frame hex>  →  <decoded meaning>
```

## Hygiene

- [ ] **Secrets redacted** (no tokens / Wi-Fi / OAuth / account creds / API keys in files or PR text)
- [ ] **Authorized target** (hardware/software the user owns or is authorized to analyze)
- [ ] Branch off `main` with the right prefix (`device/ method/ fix/ example/ docs/`); **not** pushed to `main`
- [ ] Added a row to `examples/devices/README.md` (if a new device profile)
- [ ] If `SKILL.md` changed, the technique is grounded in a real case (not abstract advice)

## Anything the reviewer should know

<!-- Open questions, things you couldn't verify without more hardware, follow-ups. -->
