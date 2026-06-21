"""BLE advertisement parsing — the passive-broadcast layer.

Many BLE sensors never accept a connection; they broadcast their state in the advertisement's
manufacturer- or service-data. This module parses the AD structure list per the Core Specification
Supplement (each element is ``[length][AD type][data]``, where ``length`` counts the type byte but
not itself), and pulls out the fields you actually reverse-engineer against.

Note the endianness traps the spec calls out: the 16-bit Company Identifier (in manufacturer data)
and 16-bit Service-Data UUIDs are **little-endian**.
"""

from __future__ import annotations

from dataclasses import dataclass

# AD type codes (Assigned Numbers / CSS)
AD_FLAGS = 0x01
AD_UUID16_INCOMPLETE = 0x02
AD_UUID16_COMPLETE = 0x03
AD_NAME_SHORT = 0x08
AD_NAME_COMPLETE = 0x09
AD_TX_POWER = 0x0A
AD_SERVICE_DATA_16 = 0x16
AD_SERVICE_DATA_32 = 0x20
AD_SERVICE_DATA_128 = 0x21
AD_MANUFACTURER = 0xFF


@dataclass(frozen=True)
class ADStructure:
    type: int
    data: bytes


def parse_ad(payload: bytes) -> list[ADStructure]:
    """Parse a raw advertisement (or scan-response) payload into AD structures.

    Tolerant of the trailing zero-padding controllers add, and of truncation.
    """
    out: list[ADStructure] = []
    i, n = 0, len(payload)
    while i < n:
        length = payload[i]
        if length == 0:
            break  # padding
        if i + 1 + length > n:
            break  # truncated
        out.append(ADStructure(payload[i + 1], payload[i + 2 : i + 1 + length]))
        i += 1 + length
    return out


def _structs(ad: bytes | list[ADStructure]) -> list[ADStructure]:
    return parse_ad(ad) if isinstance(ad, (bytes, bytearray)) else ad


def manufacturer_data(ad: bytes | list[ADStructure]) -> tuple[int, bytes] | None:
    """Return ``(company_id, data)`` from the Manufacturer Specific Data (0xFF), or None.

    ``company_id`` is decoded little-endian per spec.
    """
    for s in _structs(ad):
        if s.type == AD_MANUFACTURER and len(s.data) >= 2:
            return int.from_bytes(s.data[:2], "little"), s.data[2:]
    return None


def service_data(ad: bytes | list[ADStructure]) -> dict[int, bytes]:
    """Map 16-bit Service-Data UUID -> its data bytes (UUID decoded little-endian)."""
    out: dict[int, bytes] = {}
    for s in _structs(ad):
        if s.type == AD_SERVICE_DATA_16 and len(s.data) >= 2:
            out[int.from_bytes(s.data[:2], "little")] = s.data[2:]
    return out


def service_uuids16(ad: bytes | list[ADStructure]) -> list[int]:
    """All advertised 16-bit service UUIDs (complete + incomplete lists), little-endian."""
    out: list[int] = []
    for s in _structs(ad):
        if s.type in (AD_UUID16_INCOMPLETE, AD_UUID16_COMPLETE):
            for j in range(0, len(s.data) - 1, 2):
                out.append(int.from_bytes(s.data[j : j + 2], "little"))
    return out


def local_name(ad: bytes | list[ADStructure]) -> str | None:
    """The advertised local name (complete preferred over shortened)."""
    short = None
    for s in _structs(ad):
        if s.type == AD_NAME_COMPLETE:
            return s.data.decode("utf-8", "replace")
        if s.type == AD_NAME_SHORT and short is None:
            short = s.data.decode("utf-8", "replace")
    return short


def flags(ad: bytes | list[ADStructure]) -> int | None:
    """The Flags byte (0x01), if present. bit0 LE Limited Disc, bit1 LE General Disc,
    bit2 BR/EDR Not Supported."""
    for s in _structs(ad):
        if s.type == AD_FLAGS and s.data:
            return s.data[0]
    return None
