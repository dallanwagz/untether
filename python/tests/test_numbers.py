"""Assigned-Numbers resolver tests."""

from untether_bt import (
    ad_type_name,
    appearance_name,
    company_name,
    describe_uuid,
    gatt_name,
    parse_class_of_device,
    protocol_name,
    sdp_service_name,
    uuid128_to_16,
    uuid16_to_128,
)
from untether_bt.numbers import COMPANY_IDS, GATT_CHARACTERISTICS, SDP_SERVICE_CLASSES


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
    assert company_name(0xF000) is None  # unassigned in the registry
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
    assert describe_uuid(0x0003, namespace="protocol") == "0x0003 (RFCOMM)"


# ---- the grown / authoritative tables ----

def test_tables_are_substantial():
    # the full SIG registries, not a hand-picked handful
    assert len(COMPANY_IDS) > 3000
    assert len(GATT_CHARACTERISTICS) > 400
    assert len(SDP_SERVICE_CLASSES) > 50


def test_company_corrections_from_authoritative_source():
    # the old curated table had 0x0001 and 0x004F wrong; the authoritative import fixes them
    assert company_name(0x004C) == "Apple, Inc."
    assert "Nokia" in company_name(0x0001)            # was incorrectly "Ericsson"
    assert "Govee" in company_name(0x0001)            # ...with the reuse gotcha annotated
    assert company_name(0x02E5).startswith("Espressif")


def test_protocol_identifiers():
    assert protocol_name(0x0003) == "RFCOMM"
    assert protocol_name(0x0100) == "L2CAP"
    assert protocol_name(0x0007) == "ATT"
    assert protocol_name(0x9999) is None


def test_ad_types():
    assert ad_type_name(0x01) == "Flags"
    assert ad_type_name(0x09) == "Complete Local Name"
    assert ad_type_name(0xFF) == "Manufacturer Specific Data"


def test_appearance():
    assert appearance_name(0x0040) == "Phone"        # category 1, no subcategory
    assert appearance_name(0x0000) == "Unknown"


def test_class_of_device():
    # major device = Phone (0x02), minor = Smartphone (0x03), service bit 21 = Audio
    cod = (1 << 21) | (0x02 << 8) | (0x03 << 2)
    decoded = parse_class_of_device(cod)
    assert decoded["major_device_class"].startswith("Phone")
    assert decoded["minor_device_class"] == "Smartphone"
    assert any("Audio" in s for s in decoded["major_service_classes"])
    assert decoded["major"] == 0x02 and decoded["minor"] == 0x03
