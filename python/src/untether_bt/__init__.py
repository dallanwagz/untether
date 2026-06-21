"""untether-bt — a Bluetooth Swiss-army-knife for reverse engineering, troubleshooting, and engineering.

First-class Bluetooth **Classic (RFCOMM/SPP)** support — reachable from any host or from Home
Assistant via the companion ``untether_spp`` ESP32 bridge — plus the protocol primitives the
BLE-only ecosystem leaves to you. Includes: the framing/codec engine, the SPP bridge client, the
advertisement decoder, and the full reverse-engineering pipeline: the live ADB/UIAutomator driver
(drive the vendor app, mark each action) → btsnoop capture → HCI/ATT extraction → UI-action↔
wire-byte correlation. jadx/Frida wrappers and SDP/GATT-over-bleak follow.
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
from .android import AdbError, AdbRunner, AndroidDriver, extract_btsnoop_from_zip
from .apk import (
    ApkAnalysis,
    Finding,
    analyze_apk,
    analyze_tree,
    decompile_apk,
    pull_apk,
)
from .frida import FridaSession, hook_script_path, parse_hook_message
from .gatt import GattClient, normalize_uuid
from .numbers import (
    company_name,
    describe_uuid,
    gatt_name,
    sdp_service_name,
    uuid16_to_128,
    uuid128_to_16,
)
from .sdp import (
    find_rfcomm_channels,
    parse_data_element,
    parse_records,
    parse_ssa_response,
    rfcomm_channel,
    spp_channel,
)
from .uiauto import UiNode, find_node, parse_ui_dump
from .btsnoop import Btsnoop, BtsnoopRecord, make_record, parse_btsnoop, write_btsnoop
from .capture import Capture, Correlation, Mark, Recorder, WireEvent, correlate
from .framing import (
    DIVOOM_NEWMODE,
    DIVOOM_STUFFED,
    Frame,
    Framing,
    Stuffing,
    crc_sum16,
)
from .hci import AttPdu, HciPacket, L2capPayload, att_pdus, hci_packets, l2cap_payloads
from .spp import AsyncSppBridge, SppBridge

__version__ = "0.5.0"

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
    # capture / reverse-engineering
    "Btsnoop",
    "BtsnoopRecord",
    "parse_btsnoop",
    "write_btsnoop",
    "make_record",
    "HciPacket",
    "L2capPayload",
    "AttPdu",
    "hci_packets",
    "l2cap_payloads",
    "att_pdus",
    "Capture",
    "WireEvent",
    "Mark",
    "Correlation",
    "Recorder",
    "correlate",
    # android live driver (RE pipeline)
    "AndroidDriver",
    "AdbRunner",
    "AdbError",
    "extract_btsnoop_from_zip",
    "UiNode",
    "parse_ui_dump",
    "find_node",
    # static analysis (jadx)
    "ApkAnalysis",
    "Finding",
    "analyze_tree",
    "analyze_apk",
    "decompile_apk",
    "pull_apk",
    # dynamic instrumentation (frida)
    "FridaSession",
    "parse_hook_message",
    "hook_script_path",
    # assigned numbers
    "uuid16_to_128",
    "uuid128_to_16",
    "company_name",
    "gatt_name",
    "sdp_service_name",
    "describe_uuid",
    # sdp
    "parse_data_element",
    "parse_records",
    "parse_ssa_response",
    "rfcomm_channel",
    "find_rfcomm_channels",
    "spp_channel",
    # gatt (over bleak)
    "GattClient",
    "normalize_uuid",
]
