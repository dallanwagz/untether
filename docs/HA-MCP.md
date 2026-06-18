# Optional prerequisite: the Home Assistant MCP server

[HA MCP](https://homeassistant-ai.github.io/ha-mcp/) is a Model Context Protocol server that gives
an AI client (Claude, etc.) **structured, tool-based access to a running Home Assistant** — search
entities, read their state, call services, read history/traces, manage automations, and more.

For this skill it is an **optional** prerequisite. It does **not** help with the reverse-engineering
itself; it makes the **Home-Assistant-side validation** dramatically more convenient — and
validation is a large part of getting an integration right. If you don't set it up, nothing is
blocked: the skill falls back to the raw HA REST/WebSocket API (which is what it used to build every
example in this repo).

- **Project / docs:** https://homeassistant-ai.github.io/ha-mcp/
- **macOS setup guide:** https://homeassistant-ai.github.io/ha-mcp/guide-macos/

## Setup, in one paragraph

Install it (macOS one-liner from the guide), then add the server to your AI client's MCP config
with two env vars: `HOMEASSISTANT_URL` and a **long-lived access token** (HA → your profile →
Security → Long-lived access tokens). Restart the client. Full steps and the config block are in the
[macOS guide](https://homeassistant-ai.github.io/ha-mcp/guide-macos/).

## Confirm it works BEFORE starting the skill

Do this first so the skill can rely on it:

1. In your client, ask: **"Using the HA MCP, list a few of my entities and tell me the state of one
   sensor."** You should get real entities back, not an error. (The guide's own smoke test is
   "Can you see my Home Assistant?")
2. Confirm a **read** of a specific entity you care about (e.g. the device you're integrating, or
   any sensor) returns a live value.
3. Confirm a **harmless service call** round-trips — e.g. toggle a non-critical `input_boolean` or
   read an automation trace — so you know write/control works, not just read.

If all three succeed, tell the skill you have HA MCP available and it'll use the MCP-accelerated
validation path. If any fail, fix the token/URL/restart per the guide, or just proceed without it
(the skill will use the REST/WS API directly).

## What it unlocks (and what it doesn't)

### Unlocks — the validation loop, made easy

These are exactly the checks this skill does repeatedly, and the MCP turns each into a clean tool
call instead of hand-rolled API code:

- **Read entity state on demand** — "did the sensor update / change after I sent that command?"
  This is the backbone of operator-in-the-loop validation (Phase 4) and post-build verification.
- **Call services** — flip a switch, reload, trigger your new `send_command` service, fire a button
  — to drive and re-test the integration end-to-end.
- **History / statistics / automation traces** — confirm a value moved over time, debug why an
  automation that uses your new entities didn't fire.
- **Search & system overview** — find the entities/devices your integration created, confirm unique
  IDs and device-registry wiring look right.

### Does NOT unlock — the RE itself, and some low-level HA internals

- **None of the reverse-engineering.** Decompiling the APK, ADB/UIAutomator, GATT enumeration,
  packet capture, status-frame decoding — all of that is on the device/phone/`bleak` side and has
  nothing to do with HA MCP. It cannot read your device's BLE traffic.
- **Low-level Bluetooth diagnostics this skill sometimes needs.** Freeing a single-central BLE slot
  by **disabling a config entry**, watching **`bluetooth/subscribe_advertisements`**, or reading
  **`bluetooth/subscribe_connection_allocations`** (per-proxy free slots) are specialized WS calls.
  They're **not** part of the MCP's documented tool categories — if your build doesn't expose them,
  keep using the raw HA WS/REST API for those specific steps (as the examples in this repo did).
  Verify against your server's live tool list rather than assuming.
- **It is not required to ship.** You still need GitHub access and a Bluetooth host (proxy/adapter
  or ESP32) — see the main prerequisites.

## Where it sits in the token / privacy / convenience equation

- **Convenience: high.** It removes a whole class of glue code. Without it, validating "did the
  voltage sensor change after the power-cycle?" means writing and debugging a WS/REST snippet; with
  it, it's one tool call. This is its real value for the skill.
- **Tokens: modest, usually net-neutral-to-positive.** Each MCP call costs some tokens (tool
  schema + the result), but validation results are small (an entity-state JSON, a short history
  slice) — nothing like the large UIAutomator screen dumps that dominate the dynamic-capture
  budget. It often *saves* tokens versus iterating on hand-written API scripts. Caveat: the server
  exposes 90+ tools; if your client loads all tool schemas eagerly that's some up-front overhead —
  on-demand/deferred tool loading keeps it small.
- **Privacy / blast radius: this is the real trade.** HA MCP needs a **long-lived token with full
  Home Assistant access**, and the server can **read and control your entire home** (lights,
  locks, cameras, backups, system). That's a broad grant to hand an AI client. Mitigations: use it
  on a host you trust, prefer a **local URL** over exposing HA to the internet, treat the token as
  a secret (never commit it — same rule as everywhere in this repo), and revoke it when you're done
  if you only needed it for one integration. If that blast radius isn't acceptable to you, **don't
  enable it** — the skill works fine without it, and you keep HA access scoped to the specific
  REST/WS calls the skill makes.

## How it relates to our workflow (summary)

| Skill phase | With HA MCP | Without (REST/WS fallback) |
|---|---|---|
| Phase 0–3 (RE: transport, decompile, GATT, capture) | no change — not HA's job | no change |
| Phase 4 (validate control + decode) | read state / call services as tool calls — fast | hand-rolled `/api/states`, service calls |
| Phase 5 (build the integration) | end-to-end re-test of entities/services via tools | scripted API checks |
| Phase 6 (reliability) | history/traces to spot stalls; **but** advertisement & slot-allocation diagnostics stay raw WS | raw WS for all of it |

Bottom line: **really useful for validation, irrelevant to the RE, and a deliberate privacy
trade.** Optional by design — turn it on if the convenience is worth the access you're granting.
