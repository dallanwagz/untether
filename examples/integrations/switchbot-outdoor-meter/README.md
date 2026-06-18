# SwitchBot Outdoor Meter — Home Assistant integration

Local, cloud-free Home Assistant support for the **SwitchBot Indoor/Outdoor
Thermo-Hygrometer** (model **W3400010**, SwitchBot model name `WoIOSensorTH`).

The meter is a **passive BLE broadcaster**: it never needs to be connected to —
it advertises temperature, humidity and battery in its Bluetooth advertisement,
and this integration decodes that advertisement locally. No SwitchBot hub, no
SwitchBot account, no cloud.

> Built as a worked example for
> [`untether`](https://github.com/dallanwagz/untether). The
> protocol was reverse-engineered and verified on hardware; see the device
> profile in that repo for the full byte map and golden frames.

## Provided entities

| Entity | Source | Notes |
|--------|--------|-------|
| Temperature (°C) | advertisement | 0.1 °C resolution; HA converts to your unit |
| Humidity (%) | advertisement | whole percent |
| Battery (%) | advertisement service data | diagnostic |

## Requirements

- A Bluetooth adapter on the HA host, **or** an ESPHome/Shelly Bluetooth proxy
  near the meter (passive scanning is sufficient — no connection is made).
- Home Assistant 2024.12 or newer.

## Installation (HACS)

1. HACS → Integrations → ⋮ → **Custom repositories**.
2. Add `https://github.com/dallanwagz/untether` (or the integration's
   own repo) as an **Integration**.
3. Install **SwitchBot Outdoor Meter** and restart Home Assistant.
4. The meter is **auto-discovered** from its advertisement — confirm the
   discovery prompt under Settings → Devices & Services. (You can also add it
   manually via **Add Integration → SwitchBot Outdoor Meter**.)

## How it works

A `PassiveBluetoothProcessorCoordinator` scans in passive mode and feeds each
advertisement to `protocol.parse`, a dependency-free decoder unit-tested against
captured golden frames. Decoded values become sensor entities. Because the
device is broadcast-only, there is no polling, no connection slot contention,
and nothing to keep awake.

## Removal

Settings → Devices & Services → SwitchBot Outdoor Meter → ⋮ → **Delete**.
No device-side state is changed (the integration never connects), so removal is
clean and reversible.

## Development

```bash
pip install pytest-homeassistant-custom-component ruff mypy
PYTHONPATH=. pytest          # protocol golden frames + config-flow + coordinator
ruff check custom_components/
mypy custom_components/switchbot_outdoor_meter/
```
