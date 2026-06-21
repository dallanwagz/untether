"""Assigned-Numbers resolver tests."""

from untether_bt import (
    company_name,
    describe_uuid,
    gatt_name,
    sdp_service_name,
    uuid128_to_16,
    uuid16_to_128,
)


def test_base_uuid_round_trip():
    assert uuid16_to_128(0x180F) == "0000180f-0000-1000-8000-00805f9b34fb"
    assert uuid128_to_16("0000180F-0000-1000-8000-00805F9B34FB") == 0x180F
    assert uuid128_to_16("0000180f-0000-1000-8000-00805f9b34fb") == 0x180F


def test_non_base_uuid_does_not_contract():
    assert uuid128_to_16("12345678-1234-1234-1234-123456789abc") is None
    # right suffix but nonzero high word -> not a base 16-bit UUID
    assert uuid128_to_16("1234180f-0000-1000-8000-00805f9b34fb") is None


def test_lookups():
    assert company_name(0x004C) == "Apple, Inc."
    assert company_name(0xDEAD) is None
    assert gatt_name(0x180F) == "Battery Service"
    assert gatt_name(0x2902) == "Client Characteristic Configuration (CCCD)"
    assert sdp_service_name(0x1101) == "Serial Port (SPP)"


def test_namespaces_are_distinct():
    # 0x1101 is an SDP service class, not a GATT service
    assert sdp_service_name(0x1101) is not None
    assert gatt_name(0x1101) is None


def test_describe_uuid():
    assert describe_uuid(0x180F) == "0x180F (Battery Service)"
    assert describe_uuid(0x1101, namespace="sdp") == "0x1101 (Serial Port (SPP))"
    assert describe_uuid("0000180f-0000-1000-8000-00805f9b34fb") == "0x180F (Battery Service)"
    assert describe_uuid("12345678-1234-1234-1234-123456789abc") == "12345678-1234-1234-1234-123456789abc"
