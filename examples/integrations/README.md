# Worked integrations

Complete, **tested** integrations produced with the skill — the end state a device profile builds
toward. Where `examples/devices/` holds the *protocol* per device, this holds full *integrations*
that show the [Phase 5](../../SKILL.md) patterns wired together: a pure `protocol.py` with
golden-frame tests, a coordinator, config flow, sensors, manifest, and a quality-scale file.

Contribute one with an `example/` branch (see [`AGENTS.md`](../../AGENTS.md)). Keep secrets out and
every golden frame real.

| Integration | Transport | Models | Notes |
|-------------|-----------|--------|-------|
| [govee-passive-th](govee-passive-th/) | Passive BLE advertisement (`connectable: false`) | H5075, H5104 | Capstone of the Govee dry-run; `protocol.py` unit-tested vs live golden frames; validated against merged HA Core. |
| [switchbot-outdoor-meter](switchbot-outdoor-meter/) | Passive BLE advertisement (`connectable: false`) | W3400010 (WoIOSensorTH) | Written from scratch *before* reading core's `switchbot`; `ruff`/`mypy`/20 `pytest` green (config-flow 100%); validated 4 ways (hand-decode == pySwitchbot == vendor app == app source). |
