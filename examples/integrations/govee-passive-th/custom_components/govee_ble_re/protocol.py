"""Pure decode logic for Govee passive BLE thermo-hygrometers.

NO Home Assistant imports — this module is the reusable, unit-tested protocol spec (the
`protocol.py` pattern from the untether skill). Everything here was reverse-engineered
from the Govee Android app (``com.govee.home``) and **validated on live hardware against the device
LCD and the shipping Home Assistant Core ``govee_ble`` integration** (see
``~/repo/govee-re/notes/live-validation-log.md``).

Supported models (the dry-run scope): **H5075** and **H5104** thermo-hygrometers. Both broadcast
temperature/humidity/battery in a BLE advertisement (no connection). Occupancy models (H5127) are a
different format/transport and are intentionally out of scope here.
"""

from __future__ import annotations

from dataclasses import dataclass

# BLE manufacturer "company id"s the sensors advertise under.
COMPANY_ID_H5075 = 0xEC88  # H5072/H5075 carry the data in this manufacturer record
COMPANY_ID_H5104 = 0x0001  # H51xx (incl. H5104) carry the data in company 0x0001

# 16-bit service UUID both families also advertise (the app's discovery gate).
SERVICE_UUID_GOVEE_TH = "0000ec88-0000-1000-8000-00805f9b34fb"

# Sentinel: an all-FF packed value means "no reading yet / sensor fault".
_FAULT = 0xFFFFFF
_SIGN_BIT = 0x800000
_MASK = 0x7FFFFF


@dataclass(frozen=True, slots=True)
class GoveeReading:
    """A decoded sensor reading. Temperature in °C, humidity in %RH, battery in %."""

    model: str
    temperature_c: float
    humidity: float
    battery: int


def _decode_packed_th(packed: bytes) -> tuple[float, float] | None:
    """Decode the 3-byte big-endian temp+humidity word shared by both models.

    The single integer encodes both fields: ``temp = (v // 1000) / 10`` and
    ``hum = (v % 1000) / 10``. The top bit is the temperature sign. This matches the Govee app's
    ``IThBroadParse.parseThValue`` and HA Core's ``govee-ble`` exactly (verified on hardware).
    """
    if len(packed) != 3:
        return None
    raw = int.from_bytes(packed, "big")
    if raw == _FAULT:
        return None
    value = raw & _MASK
    temperature = (value // 1000) / 10.0
    if raw & _SIGN_BIT:
        temperature = -temperature
    humidity = (value % 1000) / 10.0
    if not (-40.0 <= temperature <= 100.0) or not (0.0 <= humidity <= 100.0):
        return None
    return temperature, humidity


def parse_advertisement(
    manufacturer_data: dict[int, bytes],
    *,
    local_name: str | None = None,
) -> GoveeReading | None:
    """Decode a Govee advertisement into a :class:`GoveeReading`, or ``None`` if it isn't one of ours.

    ``manufacturer_data`` maps company-id -> the bytes that follow the company id (the same shape
    Home Assistant and bleak expose). ``local_name`` (e.g. ``GVH5075_DC1B``) is used only to label
    the model and never to gate the decode.
    """
    # H5075 family: data in manufacturer record 0xEC88, packed value at data[1:4], battery data[4].
    data = manufacturer_data.get(COMPANY_ID_H5075)
    if data is not None and len(data) >= 5:
        th = _decode_packed_th(data[1:4])
        if th is not None:
            return GoveeReading("H5075", th[0], th[1], data[4] & 0x7F)

    # H5104 family: data in manufacturer record 0x0001, packed value at data[2:5], battery data[5].
    data = manufacturer_data.get(COMPANY_ID_H5104)
    if data is not None and len(data) >= 6:
        th = _decode_packed_th(data[2:5])
        if th is not None:
            return GoveeReading("H5104", th[0], th[1], data[5] & 0x7F)

    return None
