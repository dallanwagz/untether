"""Golden-frame tests for the Outdoor Meter protocol decoder.

Every frame here was captured off real hardware via passive BLE scan (see
``captures/golden_frames.md``). Decoded values were cross-checked against the
SwitchBot vendor app's own display and against pySwitchbot 2.2.0.
"""

from __future__ import annotations

import pytest

from custom_components.switchbot_outdoor_meter.protocol import (
    MeterAdvertisement,
    ParseError,
    is_outdoor_meter,
    mac_from_manufacturer_data,
    parse,
)


def _hex(s: str) -> bytes:
    return bytes.fromhex(s)


# --- real captured golden frames --------------------------------------------

BASELINE = (
    "c2e77a0000010e0f079a2000",  # manufacturer data (company id stripped)
    "7700c5",  # service data (uuid fd3d)
)
WARMING_PEAK = ("c2e77a0000011f0f059e3d00", "7700c5")
# Sibling unit in a freezer — exercises the negative-sign path on real data.
FREEZER_SIBLING = ("d5dc53000002890f01114600", "770053")
# Same unit captured live with the app's display unit toggled to °F: byte[7] 0x0f->0x07.
FAHRENHEIT_MODE = ("c2e77a0000016807029b1d00", "7700c5")


def test_baseline_golden_frame() -> None:
    adv = parse(*map(_hex, BASELINE))
    assert adv == MeterAdvertisement(
        address="C2:E7:7A:00:00:01",
        temperature=26.7,
        humidity=32,
        battery=69,
        sequence=0x0E,
        fahrenheit_display=False,
    )


def test_warming_peak_golden_frame() -> None:
    adv = parse(*map(_hex, WARMING_PEAK))
    assert adv.temperature == 30.5
    assert adv.humidity == 61
    assert adv.battery == 69
    assert adv.sequence == 0x1F


def test_negative_temperature_golden_frame() -> None:
    adv = parse(*map(_hex, FREEZER_SIBLING))
    assert adv.address == "D5:DC:53:00:00:02"
    assert adv.temperature == -17.1
    assert adv.humidity == 70
    assert adv.battery == 83


def test_mac_is_big_endian_from_manufacturer_data() -> None:
    assert mac_from_manufacturer_data(_hex(BASELINE[0])) == "C2:E7:7A:00:00:01"


def test_display_unit_flag_tracks_byte7() -> None:
    # The display unit lives in byte[7] bit3 (set=°C, clear=°F), verified live by
    # toggling the app unit. Captured °C and °F frames of the same unit prove it.
    celsius = parse(*map(_hex, BASELINE))  # byte[7] == 0x0f
    assert celsius.fahrenheit_display is False
    fahrenheit = parse(*map(_hex, FAHRENHEIT_MODE))  # byte[7] == 0x07
    assert fahrenheit.fahrenheit_display is True
    # temperature/humidity still decode normally in °F mode (wire is always Celsius)
    assert fahrenheit.temperature == 27.2
    assert fahrenheit.humidity == 29


def test_uppercase_model_byte_accepted() -> None:
    # Some units broadcast 'W' (0x57) instead of 'w' (0x77).
    assert is_outdoor_meter(_hex("570020"))
    adv = parse(_hex(BASELINE[0]), _hex("5700c5"))
    assert adv.temperature == 26.7


def test_model_byte_encrypted_high_bit_accepted() -> None:
    # The model byte's high bit is the "encrypted" flag; mask it before matching.
    # 0xF7 = 0x77 | 0x80 ('w' with the flag set) must still match.
    assert is_outdoor_meter(_hex("f70020"))
    adv = parse(_hex(BASELINE[0]), _hex("f700c5"))
    assert adv.temperature == 26.7


def test_rejects_all_zero_frame() -> None:
    # A 0 C / 0 % / 0 % frame is not a real reading and must be suppressed.
    mfr = _hex("c2e77a0000010e0f000000")
    with pytest.raises(ParseError):
        parse(mfr, _hex("770000"))


def test_missing_service_data_yields_no_battery() -> None:
    adv = parse(_hex(BASELINE[0]), _hex("7700"))
    assert adv.battery is None
    assert adv.temperature == 26.7


def test_rejects_other_switchbot_model() -> None:
    # The 0x76 device captured nearby is a different SwitchBot product.
    with pytest.raises(ParseError):
        parse(_hex("ee16a611ddd500ff6a3344338206999e00"), _hex("7600"))


def test_rejects_short_manufacturer_data() -> None:
    with pytest.raises(ParseError):
        parse(_hex("c2e77a0000010e0f"), _hex("7700c5"))
