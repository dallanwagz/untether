"""Sensor platform — temperature, humidity, battery from the passive advertisement."""

from __future__ import annotations

from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothDataUpdate,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import PERCENTAGE, UnitOfTemperature
from homeassistant.core import HomeAssistant
from homeassistant.helpers.entity import EntityCategory
from homeassistant.helpers.entity_platform import AddConfigEntryEntitiesCallback

from . import GoveeBLEConfigEntry

SENSOR_DESCRIPTIONS: dict[str, SensorEntityDescription] = {
    "temperature": SensorEntityDescription(
        key="temperature",
        device_class=SensorDeviceClass.TEMPERATURE,
        native_unit_of_measurement=UnitOfTemperature.CELSIUS,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "humidity": SensorEntityDescription(
        key="humidity",
        device_class=SensorDeviceClass.HUMIDITY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
    ),
    "battery": SensorEntityDescription(
        key="battery",
        device_class=SensorDeviceClass.BATTERY,
        native_unit_of_measurement=PERCENTAGE,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
    ),
}


def _sensor_update_to_entities(
    data: PassiveBluetoothDataUpdate,
) -> PassiveBluetoothDataUpdate:
    """Attach our SensorEntityDescriptions to the keys produced in __init__."""
    return PassiveBluetoothDataUpdate(
        devices=data.devices,
        entity_descriptions={
            key: SENSOR_DESCRIPTIONS[key]
            for key in data.entity_data
            if key in SENSOR_DESCRIPTIONS
        },
        entity_data=data.entity_data,
        entity_names=data.entity_names,
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: GoveeBLEConfigEntry,
    async_add_entities: AddConfigEntryEntitiesCallback,
) -> None:
    """Set up the sensor platform for a Govee BLE device."""
    coordinator = entry.runtime_data
    processor = PassiveBluetoothDataProcessor(_sensor_update_to_entities)
    entry.async_on_unload(
        processor.async_add_entities_listener(GoveeBLESensor, async_add_entities)
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class GoveeBLESensor(PassiveBluetoothProcessorEntity, SensorEntity):
    """A Govee passive-advertisement sensor."""

    @property
    def native_value(self) -> str | int | float | None:
        """Return the latest decoded value for this key."""
        return self.processor.entity_data.get(self.entity_key)
