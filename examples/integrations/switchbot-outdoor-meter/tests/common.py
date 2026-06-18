"""Shared test helpers for the SwitchBot Outdoor Meter tests."""

from __future__ import annotations

from bleak.backends.device import BLEDevice
from bleak.backends.scanner import AdvertisementData
from homeassistant.components.bluetooth import BluetoothServiceInfoBleak

# Real captured advertisement of unit C2:E7:7A:00:00:01 (26.7 C / 32 % / batt 69 %).
SERVICE_UUID = "0000fd3d-0000-1000-8000-00805f9b34fb"
GOLDEN_MFR = bytes.fromhex("c2e77a0000010e0f079a2000")
GOLDEN_SVC = bytes.fromhex("7700c5")
GOLDEN_ADDRESS = "C2:E7:7A:00:00:01"


def make_service_info(
    address: str = GOLDEN_ADDRESS,
    manufacturer_data: bytes = GOLDEN_MFR,
    service_data: bytes = GOLDEN_SVC,
    name: str = "WoIOSensorTH",
) -> BluetoothServiceInfoBleak:
    """Build a BluetoothServiceInfoBleak for a meter advertisement."""
    return BluetoothServiceInfoBleak(
        name=name,
        address=address,
        rssi=-30,
        manufacturer_data={0x0969: manufacturer_data},
        service_data={SERVICE_UUID: service_data},
        service_uuids=[SERVICE_UUID],
        source="local",
        device=BLEDevice(address, name, {}),
        advertisement=AdvertisementData(
            local_name=name,
            manufacturer_data={0x0969: manufacturer_data},
            service_data={SERVICE_UUID: service_data},
            service_uuids=[SERVICE_UUID],
            tx_power=-127,
            rssi=-30,
            platform_data=(),
        ),
        connectable=False,
        time=0,
        tx_power=-127,
    )
