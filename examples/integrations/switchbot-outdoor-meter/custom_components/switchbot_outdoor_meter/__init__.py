"""The SwitchBot Outdoor Meter integration.

A passive BLE thermo-hygrometer (model W3400010): it broadcasts temperature,
humidity and battery in its advertisement and is never connected to.
"""

from __future__ import annotations

import logging

from homeassistant.components.bluetooth import BluetoothScanningMode
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothProcessorCoordinator,
)
from homeassistant.const import Platform
from homeassistant.core import HomeAssistant

from .coordinator import OutdoorMeterConfigEntry, parse_service_info

_LOGGER = logging.getLogger(__name__)

PLATFORMS: list[Platform] = [Platform.SENSOR]


async def async_setup_entry(
    hass: HomeAssistant, entry: OutdoorMeterConfigEntry
) -> bool:
    """Set up the Outdoor Meter from a config entry."""
    address = entry.unique_id
    assert address is not None  # set in the config flow

    coordinator = PassiveBluetoothProcessorCoordinator(
        hass,
        _LOGGER,
        address=address,
        mode=BluetoothScanningMode.PASSIVE,
        update_method=parse_service_info,
    )
    entry.runtime_data = coordinator

    await hass.config_entries.async_forward_entry_setups(entry, PLATFORMS)
    # Start scanning only after the platforms have registered their processors.
    entry.async_on_unload(coordinator.async_start())
    return True


async def async_unload_entry(
    hass: HomeAssistant, entry: OutdoorMeterConfigEntry
) -> bool:
    """Unload a config entry."""
    return await hass.config_entries.async_unload_platforms(entry, PLATFORMS)
