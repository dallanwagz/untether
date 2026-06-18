"""Pure protocol logic for the SwitchBot Indoor/Outdoor Meter (W3400010).

This module has **no Home Assistant dependencies** so it can be unit-tested in
isolation against the captured golden frames (see ``tests/test_protocol.py``).
It decodes the device's BLE *passive advertisement* — the meter never needs to be
connected to; it broadcasts temperature, humidity and battery in its
manufacturer-specific data and service data.

Reverse-engineered and verified on hardware (unit ``C2:E7:7A:00:00:01``):
a controlled warming test drove temperature 26.7 -> 30.5 C monotonically while the
byte map below tracked it exactly, and the values matched the vendor app's own
display (28.1 C / 31 % / batt 69 %) to the decimal.
"""

from __future__ import annotations

from dataclasses import dataclass

# BLE company identifier used by SwitchBot manufacturer data (decimal 2409).
MANUFACTURER_ID = 0x0969

# 16-bit service UUID SwitchBot advertises its service data under (0xFD3D).
SERVICE_UUID = "0000fd3d-0000-1000-8000-00805f9b34fb"

# service_data[0]: the high bit is SwitchBot's "encrypted" flag, the low 7 bits are
# the model character. Both 'w' (0x77) and 'W' (0x57) map to the Indoor/Outdoor
# Meter ("WoIOSensorTH"). Mask the high bit before comparing so an advert that sets
# the encrypted/status flag (e.g. 0xF7 / 0xD7) still matches.
MODEL_CHARS = ("w", "W")
_MODEL_MASK = 0x7F

# manufacturer_data[7] bit 3 carries the display-unit preference written from the
# app (verified by toggling the app unit and watching the byte flip both ways):
# set (0x08) => Celsius, clear => Fahrenheit. Note pySwitchbot reads a *different*
# bit (manufacturer_data[10] bit7) for its `fahrenheit` field, which stays 0 on the
# display-less W3400010 — so this is the only advert field that tracks the unit.
_UNIT_FLAG_INDEX = 7
_UNIT_CELSIUS_BIT = 0x08

# Lengths we slice into.
_MAC_LEN = 6  # manufacturer_data[0:6] is the BLE MAC
_MIN_MFR_LEN = 11  # we read manufacturer_data[8:11]
_MIN_SVC_LEN = 3  # we read service_data[2]


@dataclass(frozen=True, slots=True)
class MeterAdvertisement:
    """Decoded state from one Outdoor Meter advertisement."""

    address: str
    """BLE MAC, ``AA:BB:CC:DD:EE:FF`` (big-endian, as the vendor app shows it)."""

    temperature: float
    """Temperature in degrees Celsius, 0.1 C resolution."""

    humidity: int
    """Relative humidity, whole percent."""

    battery: int | None
    """Battery level in percent, or ``None`` when service data is absent."""

    sequence: int
    """Rolling frame counter (manufacturer_data[6]); increments each broadcast."""

    fahrenheit_display: bool
    """Whether the device's stored display unit is Fahrenheit (``manufacturer_data[7]``
    bit 3 clear). Written from the SwitchBot app's account-wide unit preference and
    broadcast even though the W3400010 has no screen — verified by toggling the app
    unit and watching the byte flip both ways. Not consumed by Home Assistant (the
    frontend converts units); decoded for wire fidelity."""

    rssi: int | None = None
    """Received signal strength, populated by the coordinator (not the wire frame)."""


class ParseError(ValueError):
    """Raised when the advertisement is not a decodable Outdoor Meter frame."""


def is_outdoor_meter(service_data: bytes | None) -> bool:
    """Return whether ``service_data`` identifies a SwitchBot Outdoor Meter."""
    return (
        service_data is not None
        and len(service_data) >= 1
        and chr(service_data[0] & _MODEL_MASK) in MODEL_CHARS
    )


def mac_from_manufacturer_data(manufacturer_data: bytes) -> str:
    """Extract the BLE MAC embedded in the first six manufacturer-data bytes."""
    if len(manufacturer_data) < _MAC_LEN:
        raise ParseError("manufacturer data too short to contain a MAC")
    return ":".join(f"{b:02X}" for b in manufacturer_data[:_MAC_LEN])


def parse(manufacturer_data: bytes, service_data: bytes) -> MeterAdvertisement:
    """Decode an Outdoor Meter advertisement.

    ``manufacturer_data`` is the value *after* the 2-byte company identifier has
    been stripped (i.e. the dict value keyed by :data:`MANUFACTURER_ID`).
    ``service_data`` is the value keyed by :data:`SERVICE_UUID`.

    Wire format (manufacturer data, 12 bytes on the W3400010)::

        [0:6]  BLE MAC (big-endian)
        [6]    rolling sequence counter
        [7]    bit3 = display unit (1 = Celsius, 0 = Fahrenheit); other low bits vary (0x0f/0x0b seen), undecoded
        [8]    bits[3:0] = temperature 0.1 C decimal
        [9]    bit7      = sign (1 = positive); bits[6:0] = integer C
        [10]   bit7 = pySwitchbot `fahrenheit` (0 here); bits[6:0] = humidity %
        [11]   constant 0x00 (unknown)

    Service data (3 bytes): ``[0]`` model byte, ``[1]`` 0x00,
    ``[2]`` bits[6:0] = battery %.
    """
    if not is_outdoor_meter(service_data):
        raise ParseError("service data is not a SwitchBot Outdoor Meter frame")
    if len(manufacturer_data) < _MIN_MFR_LEN:
        raise ParseError(
            f"manufacturer data too short: {len(manufacturer_data)} < {_MIN_MFR_LEN}"
        )

    temp_lo, temp_hi, humidity_byte = manufacturer_data[8:11]
    sign = 1 if temp_hi & 0x80 else -1
    temperature = round(sign * ((temp_hi & 0x7F) + (temp_lo & 0x0F) / 10), 1)
    humidity = humidity_byte & 0x7F
    # Display unit: byte[7] bit3 set => Celsius, clear => Fahrenheit.
    fahrenheit_display = not manufacturer_data[_UNIT_FLAG_INDEX] & _UNIT_CELSIUS_BIT

    battery = service_data[2] & 0x7F if len(service_data) >= _MIN_SVC_LEN else None

    # Suppress all-zero frames (no plausible real reading is 0 C / 0 % / 0 %), the
    # same guard pySwitchbot applies to avoid publishing spurious values.
    if temperature == 0 and humidity == 0 and not battery:
        raise ParseError("all-zero frame (no reading)")

    return MeterAdvertisement(
        address=mac_from_manufacturer_data(manufacturer_data),
        temperature=temperature,
        humidity=humidity,
        battery=battery,
        sequence=manufacturer_data[6],
        fahrenheit_display=fahrenheit_display,
    )
