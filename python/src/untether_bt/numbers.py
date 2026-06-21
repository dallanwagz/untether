"""Assigned Numbers — resolve company IDs and UUIDs to names, and convert 16↔128-bit UUIDs.

Two things every decoder needs: the **base-UUID expansion** (normative: a 16-bit UUID ``0xXXXX`` is
``0000XXXX-0000-1000-8000-00805f9b34fb``), and lookups for company identifiers + 16-bit UUIDs. The
lookups live in two distinct namespaces — an SDP **Service Class** ``0x1101`` (Serial Port) is *not*
a GATT service — which this module keeps separate.

The bundled tables are a curated common subset; the full, authoritative registry is the SIG's
machine-readable YAML at https://bitbucket.org/bluetooth-SIG/public (note: Bitbucket, not GitHub).
"""

from __future__ import annotations

_BASE_SUFFIX = "-0000-1000-8000-00805f9b34fb"


def uuid16_to_128(u16: int) -> str:
    """Expand a 16-bit (or 32-bit) UUID to its full 128-bit form via the Bluetooth base UUID."""
    return f"{u16:08x}{_BASE_SUFFIX}"


def uuid128_to_16(uuid: str) -> int | None:
    """Contract a 128-bit UUID to 16 bits iff it sits on the base UUID, else None."""
    u = uuid.lower().replace("{", "").replace("}", "")
    if len(u) == 36 and u[8:] == _BASE_SUFFIX and u[:4] == "0000":
        try:
            return int(u[4:8], 16)
        except ValueError:
            return None
    return None


# --- curated registries (common subset) ---
COMPANY_IDS: dict[int, str] = {
    0x0001: "Ericsson Technology (reused by some vendors, e.g. Govee, in mfr data)",
    0x0006: "Microsoft",
    0x004C: "Apple, Inc.",
    0x0059: "Nordic Semiconductor ASA",
    0x00E0: "Google",
    0x0075: "Samsung Electronics",
    0x0157: "Anhui Huami (Xiaomi/Amazfit)",
    0x02E5: "Espressif Inc.",
    0x0499: "Ruuvi Innovations",
    0x004F: "Garmin",
    0x0822: "Govee / Shenzhen Intellirocks",
}

GATT_SERVICES: dict[int, str] = {
    0x1800: "Generic Access",
    0x1801: "Generic Attribute",
    0x180A: "Device Information",
    0x180F: "Battery Service",
    0x181A: "Environmental Sensing",
    0x1809: "Health Thermometer",
    0x180D: "Heart Rate",
    0xFFE0: "Vendor serial-like service (common 0xFFE0)",
    0xFFF0: "Vendor service (common 0xFFF0)",
}

GATT_CHARACTERISTICS: dict[int, str] = {
    0x2A00: "Device Name",
    0x2A19: "Battery Level",
    0x2A6E: "Temperature",
    0x2A6F: "Humidity",
    0x2A37: "Heart Rate Measurement",
    0x2A29: "Manufacturer Name String",
    0xFFE1: "Vendor notify/write characteristic (common 0xFFE1)",
}

GATT_DESCRIPTORS: dict[int, str] = {
    0x2900: "Characteristic Extended Properties",
    0x2901: "Characteristic User Description",
    0x2902: "Client Characteristic Configuration (CCCD)",
    0x2904: "Characteristic Presentation Format",
}

SDP_SERVICE_CLASSES: dict[int, str] = {
    0x1101: "Serial Port (SPP)",
    0x1105: "OBEX Object Push",
    0x110A: "Audio Source (A2DP)",
    0x110B: "Audio Sink (A2DP)",
    0x110E: "A/V Remote Control",
    0x111E: "Handsfree",
    0x1124: "Human Interface Device (HID)",
    0x1200: "PnP Information",
}


def company_name(cid: int) -> str | None:
    return COMPANY_IDS.get(cid)


def gatt_name(u16: int) -> str | None:
    """Resolve a 16-bit GATT UUID (service, characteristic, or descriptor)."""
    return GATT_SERVICES.get(u16) or GATT_CHARACTERISTICS.get(u16) or GATT_DESCRIPTORS.get(u16)


def sdp_service_name(u16: int) -> str | None:
    return SDP_SERVICE_CLASSES.get(u16)


def describe_uuid(uuid: int | str, *, namespace: str = "gatt") -> str:
    """Best-effort human label for a UUID (int 16-bit or 128-bit string).

    ``namespace`` selects which 16-bit table to consult: ``"gatt"`` (default) or ``"sdp"``.
    """
    u16: int | None
    if isinstance(uuid, int):
        u16 = uuid
        full = uuid16_to_128(uuid)
    else:
        u16 = uuid128_to_16(uuid)
        full = uuid.lower()
    name = None
    if u16 is not None:
        name = sdp_service_name(u16) if namespace == "sdp" else gatt_name(u16)
    label = f"0x{u16:04X}" if u16 is not None else full
    return f"{label} ({name})" if name else label
