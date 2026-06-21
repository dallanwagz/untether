"""untether-bt — a Bluetooth Swiss-army-knife for reverse engineering, troubleshooting, and engineering.

First-class Bluetooth **Classic (RFCOMM/SPP)** support — reachable from any host or from Home
Assistant via the companion ``untether_spp`` ESP32 bridge — plus the protocol primitives the
BLE-only ecosystem leaves to you. v0.1 ships the framing/codec engine, the SPP bridge client, and
the advertisement decoder; more primitives (btsnoop, SDP, GATT-over-bleak, the RE pipeline) follow.
"""

from __future__ import annotations

from .advertising import (
    ADStructure,
    flags,
    local_name,
    manufacturer_data,
    parse_ad,
    service_data,
    service_uuids16,
)
from .framing import (
    DIVOOM_NEWMODE,
    DIVOOM_STUFFED,
    Frame,
    Framing,
    Stuffing,
    crc_sum16,
)
from .spp import AsyncSppBridge, SppBridge

__version__ = "0.1.0"

__all__ = [
    "__version__",
    # framing
    "Framing",
    "Frame",
    "Stuffing",
    "crc_sum16",
    "DIVOOM_NEWMODE",
    "DIVOOM_STUFFED",
    # spp
    "SppBridge",
    "AsyncSppBridge",
    # advertising
    "ADStructure",
    "parse_ad",
    "manufacturer_data",
    "service_data",
    "service_uuids16",
    "local_name",
    "flags",
]
