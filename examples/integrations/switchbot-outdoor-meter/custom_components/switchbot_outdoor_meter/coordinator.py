"""Passive Bluetooth coordinator for the SwitchBot Outdoor Meter."""

from __future__ import annotations

import logging
from dataclasses import replace

from homeassistant.components.bluetooth import BluetoothServiceInfoBleak
from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothProcessorCoordinator,
)
from homeassistant.config_entries import ConfigEntry

from .protocol import (
    MANUFACTURER_ID,
    SERVICE_UUID,
    MeterAdvertisement,
    ParseError,
    parse,
)

_LOGGER = logging.getLogger(__name__)

type OutdoorMeterCoordinator = PassiveBluetoothProcessorCoordinator[
    MeterAdvertisement | None
]
type OutdoorMeterConfigEntry = ConfigEntry[OutdoorMeterCoordinator]


def parse_service_info(
    service_info: BluetoothServiceInfoBleak,
) -> MeterAdvertisement | None:
    """Decode a Bluetooth advertisement into meter state, or ``None`` if irrelevant.

    Returning ``None`` (rather than raising) keeps the passive processor running on
    advertisements that are not decodable Outdoor Meter frames.
    """
    manufacturer_data = service_info.manufacturer_data.get(MANUFACTURER_ID)
    service_data = service_info.service_data.get(SERVICE_UUID)
    if manufacturer_data is None or service_data is None:
        return None
    try:
        adv = parse(manufacturer_data, service_data)
    except ParseError:
        _LOGGER.debug("Ignoring non-meter advertisement from %s", service_info.address)
        return None
    return replace(adv, rssi=service_info.rssi)
