"""The Govee BLE (RE dry-run) integration — passive advertisement thermo-hygrometers.

Demonstrates the Home Assistant Core passive-BLE pattern: a ``PassiveBluetoothProcessorCoordinator``
fed by the pure, unit-tested ``protocol.parse_advertisement``. No connection is made to the device
(``connectable: false``) — readings come from the broadcast advertisement.
"""

from __future__ import annotations

import logging

from homeassistant.components.bluetooth import BluetoothScanningMode, BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataUpdate,
    PassiveBluetoothProcessorCoordinator,
)
from homeassistant.config_entries import ConfigEntry
from homeassistant.const import (
    PERCENTAGE,
    Platform,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.sensor import SensorDeviceClass, SensorStateClass
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_registry import async_get as async_get_entity_registry

from .protocol import GoveeReading, parse_advertisement

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]

type GoveeBLEConfigEntry = ConfigEntry[PassiveBluetoothProcessorCoordinator[PassiveBluetoothDataUpdate]]

# Entity descriptions live in sensor.py; here we only map decoded fields -> (key, value).
_TEMPERATURE = "temperature"
_HUMIDITY = "humidity"
_BATTERY = "battery"


def _service_info_to_update(
    service_info: BluetoothServiceInfoBleak,
) -> PassiveBluetoothDataUpdate:
    """Turn a raw advertisement into a HA passive-update payload (or an empty one)."""
    reading: GoveeReading | None = parse_advertisement(
        service_info.manufacturer_data, local_name=service_info.name
    )
    if reading is None:
        return PassiveBluetoothDataUpdate(
            devices={}, entity_descriptions={}, entity_data={}, entity_names={}
        )
    return PassiveBluetoothDataUpdate(
        devices={None: {"name": reading.model, "model": reading.model, "manufacturer": "Govee"}},
        entity_descriptions={},  # filled by the sensor platform's processor
        entity_data={
            _TEMPERATURE: reading.temperature_c,
            _HUMIDITY: reading.humidity,
            _BATTERY: reading.battery,
        },
        entity_names={_TEMPERATURE: None, _HUMIDITY: None, _BATTERY: None},
    )


async def async_setup_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    """Set up Govee BLE from a config entry."""
    address = entry.unique_id
    assert address is not None
    coordinator = PassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address,
        mode=BluetoothScanningMode.PASSIVE,
        update_method=_service_info_to_update,
    )
    entry.runtime_data = coordinator
    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # start_polling-equivalent for passive listeners; cancels on unload
    entry.async_on_unload(coordinator.async_start())
    return True


async def async_unload_entry(hass: HomeAssistant, entry: GoveeBLEConfigEntry) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
