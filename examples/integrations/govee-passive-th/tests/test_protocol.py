"""Golden-frame tests for the Govee decoder.

Every frame here is a REAL advertisement captured from the user's own hardware and cross-checked
against the device LCD and/or HA Core's ``govee_ble`` values (see live-validation-log.md). These
are the regression anchors the untether skill insists on.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "custom_components" / "govee_ble_re"))

from protocol import (  # noqa: E402
    COMPANY_ID_H5075,
    COMPANY_ID_H5104,
    parse_advertisement,
)


def test_h5075_golden_frame():
    # GVH5075_DC1B, validated: LCD 78.3°F (=25.7°C) / 38%, HA Core matched.
    md = {COMPANY_ID_H5075: bytes.fromhex("0003ed733e00")}
    r = parse_advertisement(md, local_name="GVH5075_DC1B")
    assert r is not None
    assert r.model == "H5075"
    assert r.temperature_c == 25.7
    assert r.humidity == 39.5
    assert r.battery == 62
    assert round(r.temperature_c * 9 / 5 + 32, 1) == 78.3


def test_h5104_golden_frame():
    # GVH5104_6D7B, validated against HA Core: 86.72°F (=30.4°C) / 22.9% / batt.
    md = {COMPANY_ID_H5104: bytes.fromhex("010104a4652b")}
    r = parse_advertisement(md, local_name="GVH5104_6D7B")
    assert r is not None
    assert r.model == "H5104"
    assert r.temperature_c == 30.4
    assert r.humidity == 22.9
    assert r.battery == 43
    assert round(r.temperature_c * 9 / 5 + 32, 2) == 86.72


def test_h5104_matches_ha_core_humidity_sibling_frame():
    # The a464 packet decodes to 22.8% (vs a465 -> 22.9%); both are valid per-packet, proving the
    # %1000 humidity field (the swing was packet jitter, not a decode error).
    md = {COMPANY_ID_H5104: bytes.fromhex("010104a4642b")}
    r = parse_advertisement(md)
    assert r is not None and r.humidity == 22.8


def test_fault_sentinel_rejected():
    # All-FF packed value = no reading -> not a valid sensor frame.
    assert parse_advertisement({COMPANY_ID_H5075: bytes.fromhex("00ffffff3e00")}) is None


def test_non_govee_advertisement_ignored():
    assert parse_advertisement({0x004C: bytes.fromhex("0215")}) is None
    assert parse_advertisement({}) is None


def test_negative_temperature_sign_bit():
    # Synthetic: sign bit set on the packed word -> negative temperature, humidity still decodes.
    # H5075 layout: data[0]=flag, data[1:4]=packed value, data[4]=battery.
    packed = (0x800000 | 12345).to_bytes(3, "big")  # value 12345 -> temp 1.2°C (negated), hum 34.5%
    md = {COMPANY_ID_H5075: b"\x00" + packed + b"\x55"}
    r = parse_advertisement(md)
    assert r is not None
    assert r.temperature_c == -1.2
    assert r.humidity == 34.5
    assert r.battery == 0x55
