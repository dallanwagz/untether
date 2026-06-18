"""Sensor platform for the SwitchBot Outdoor Meter."""

from __future__ import annotations

from homeassistant.components.bluetooth.passive_update_processor import (
    PassiveBluetoothDataProcessor,
    PassiveBluetoothDataUpdate,
    PassiveBluetoothEntityKey,
    PassiveBluetoothProcessorEntity,
)
from homeassistant.components.sensor import (
    SensorDeviceClass,
    SensorEntity,
    SensorEntityDescription,
    SensorStateClass,
)
from homeassistant.const import (
    PERCENTAGE,
    SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
    EntityCategory,
    UnitOfTemperature,
)
from homeassistant.core import HomeAssistant
from homeassistant.helpers.device_registry import (
    CONNECTION_BLUETOOTH,
    CONNECTION_NETWORK_MAC,
    DeviceInfo,
)
from homeassistant.helpers.entity_platform import AddEntitiesCallback

from .coordinator import OutdoorMeterConfigEntry
from .protocol import MeterAdvertisement

type MeterProcessor = PassiveBluetoothDataProcessor[
    "float | int | None", "MeterAdvertisement | None"
]

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
    "rssi": SensorEntityDescription(
        key="rssi",
        device_class=SensorDeviceClass.SIGNAL_STRENGTH,
        native_unit_of_measurement=SIGNAL_STRENGTH_DECIBELS_MILLIWATT,
        state_class=SensorStateClass.MEASUREMENT,
        entity_category=EntityCategory.DIAGNOSTIC,
        entity_registry_enabled_default=False,
    ),
}


def _sensor_update_to_bluetooth_data_update(
    adv: MeterAdvertisement | None,
) -> PassiveBluetoothDataUpdate[float | int | None]:
    """Convert decoded meter state into a passive Bluetooth data update."""
    if adv is None:
        return PassiveBluetoothDataUpdate(
            devices={}, entity_descriptions={}, entity_data={}, entity_names={}
        )

    values: dict[str, float | int] = {
        "temperature": adv.temperature,
        "humidity": adv.humidity,
    }
    if adv.battery is not None:
        values["battery"] = adv.battery
    if adv.rssi is not None:
        values["rssi"] = adv.rssi

    short = adv.address.replace(":", "")[-4:]
    # The SwitchBot BLE address is also the device's MAC, so add the network-MAC
    # connection too — this lets the device be matched on platforms (macOS) that do
    # not expose the address as a Bluetooth connection.
    connections = {
        (CONNECTION_BLUETOOTH, adv.address),
        (CONNECTION_NETWORK_MAC, adv.address),
    }
    keys = {name: PassiveBluetoothEntityKey(name, None) for name in values}
    return PassiveBluetoothDataUpdate(
        devices={
            None: DeviceInfo(
                connections=connections,
                manufacturer="SwitchBot",
                model="Indoor/Outdoor Meter",
                model_id="W3400010",
                name=f"Indoor/Outdoor Meter {short}",
            )
        },
        entity_descriptions={
            keys[name]: SENSOR_DESCRIPTIONS[name] for name in values
        },
        entity_data={keys[name]: value for name, value in values.items()},
        entity_names={keys[name]: None for name in values},
    )


async def async_setup_entry(
    hass: HomeAssistant,
    entry: OutdoorMeterConfigEntry,
    async_add_entities: AddEntitiesCallback,
) -> None:
    """Set up Outdoor Meter sensors from a config entry."""
    coordinator = entry.runtime_data
    processor = PassiveBluetoothDataProcessor(_sensor_update_to_bluetooth_data_update)
    entry.async_on_unload(
        processor.async_add_entities_listener(
            OutdoorMeterSensorEntity, async_add_entities
        )
    )
    entry.async_on_unload(coordinator.async_register_processor(processor))


class OutdoorMeterSensorEntity(
    PassiveBluetoothProcessorEntity[MeterProcessor], SensorEntity
):
    """A sensor backed by the meter's passive advertisement."""

    @property
    def native_value(self) -> float | int | None:
        """Return the current value of the sensor."""
        return self.processor.entity_data.get(self.entity_key)
