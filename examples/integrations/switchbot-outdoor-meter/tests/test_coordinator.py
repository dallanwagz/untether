"""Tests for the coordinator parser and the sensor data-update conversion."""

from __future__ import annotations

from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothEntityKey,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature

from custom_components.switchbot_outdoor_meter.coordinator import parse_service_info
from custom_components.switchbot_outdoor_meter.sensor import (
    _sensor_update_to_bluetooth_data_update,
)
from tests.common import GOLDEN_ADDRESS, make_service_info


def test_parse_service_info_decodes_meter() -> None:
    adv = parse_service_info(make_service_info())
    assert adv is not None
    assert adv.address == GOLDEN_ADDRESS
    assert adv.temperature == 26.7
    assert adv.humidity == 32
    assert adv.battery == 69
    assert adv.rssi == -30  # populated from the service info by the coordinator


def test_parse_service_info_ignores_other_model() -> None:
    info = make_service_info(
        manufacturer_data=bytes.fromhex("ee16a611ddd500ff6a3344338206999e00"),
        service_data=bytes.fromhex("7600"),
    )
    assert parse_service_info(info) is None


def test_sensor_conversion_emits_sensors() -> None:
    adv = parse_service_info(make_service_info())
    update = _sensor_update_to_bluetooth_data_update(adv)

    temp_key = PassiveBluetoothEntityKey("temperature", None)
    humidity_key = PassiveBluetoothEntityKey("humidity", None)
    battery_key = PassiveBluetoothEntityKey("battery", None)
    rssi_key = PassiveBluetoothEntityKey("rssi", None)

    assert update.entity_data[temp_key] == 26.7
    assert update.entity_data[humidity_key] == 32
    assert update.entity_data[battery_key] == 69
    assert update.entity_data[rssi_key] == -30
    assert (
        update.entity_descriptions[temp_key].native_unit_of_measurement
        == UnitOfTemperature.CELSIUS
    )
    assert (
        update.entity_descriptions[battery_key].native_unit_of_measurement
        == PERCENTAGE
    )

    device = update.devices[None]
    assert device["manufacturer"] == "SwitchBot"
    assert device["model_id"] == "W3400010"


def test_sensor_conversion_handles_no_data() -> None:
    update = _sensor_update_to_bluetooth_data_update(None)
    assert update.entity_data == {}


def test_sensor_conversion_omits_battery_when_absent() -> None:
    adv = parse_service_info(make_service_info(service_data=bytes.fromhex("7700")))
    update = _sensor_update_to_bluetooth_data_update(adv)
    assert PassiveBluetoothEntityKey("battery", None) not in update.entity_data
    assert PassiveBluetoothEntityKey("temperature", None) in update.entity_data
