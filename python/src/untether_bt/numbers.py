"""Assigned Numbers — resolve company IDs, UUIDs, and Classic descriptors to human names.

Two things every decoder needs: the **base-UUID expansion** (normative: a 16-bit UUID ``0xXXXX`` is
``0000XXXX-0000-1000-8000-00805f9b34fb``), and lookups against the SIG registries. Those registries
live in *distinct namespaces* — an SDP **Service Class** ``0x1101`` (Serial Port) is not a GATT
service, and a **protocol identifier** ``0x0003`` (RFCOMM) is neither — so this module keeps them
apart and you pick the namespace.

The bundled tables are the **full** SIG Assigned Numbers (company IDs; GATT service / characteristic /
descriptor UUIDs; SDP service classes; protocol identifiers; AD/EIR types; Class of Device; GAP
appearance), generated into :mod:`untether_bt._assigned_numbers` from the SIG's machine-readable
source — see ``tools/gen_assigned_numbers.py`` to regenerate. A thin overrides layer adds RE-friendly
annotations on top (e.g. the CCCD, the SPP class, and the common vendor ``0xFFE0``/``0xFFE1``).
"""

from __future__ import annotations

from . import _assigned_numbers as _an

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


# --- RE-friendly overrides on top of the authoritative tables ---------------
# Kept tiny on purpose: only entries where a hand-written label beats the registry name for someone
# reverse-engineering a device (vendor catch-alls, common abbreviations).
_COMPANY_OVERRIDES: dict[int, str] = {
    # 0x0001 is Nokia in the registry, but it's the value non-member vendors most often *reuse*
    # inside BLE manufacturer-specific data (Govee being the classic example) — flag it.
    0x0001: "Nokia Mobile Phones (note: 0x0001 is widely reused by non-member vendors, "
    "e.g. Govee, inside BLE manufacturer data)",
}
_GATT_OVERRIDES: dict[int, str] = {
    0x2902: "Client Characteristic Configuration (CCCD)",
    0xFFE0: "Vendor serial-like service (common 0xFFE0)",
    0xFFE1: "Vendor notify/write characteristic (common 0xFFE1)",
    0xFFF0: "Vendor service (common 0xFFF0)",
    0xFFF1: "Vendor write characteristic (common 0xFFF1)",
}
_SDP_OVERRIDES: dict[int, str] = {
    0x1101: "Serial Port (SPP)",
}

# --- merged public tables (authoritative base + overrides) ------------------
COMPANY_IDS: dict[int, str] = {**_an.COMPANY_IDS, **_COMPANY_OVERRIDES}
GATT_SERVICES: dict[int, str] = dict(_an.GATT_SERVICES)
GATT_CHARACTERISTICS: dict[int, str] = dict(_an.GATT_CHARACTERISTICS)
GATT_DESCRIPTORS: dict[int, str] = dict(_an.GATT_DESCRIPTORS)
SDP_SERVICE_CLASSES: dict[int, str] = {**_an.SDP_SERVICE_CLASSES, **_SDP_OVERRIDES}
PROTOCOL_IDS: dict[int, str] = dict(_an.PROTOCOL_IDS)
AD_TYPES: dict[int, str] = dict(_an.AD_TYPES)

# one GATT lookup spanning services + characteristics + descriptors, with overrides winning
_GATT_ALL: dict[int, str] = {
    **GATT_SERVICES,
    **GATT_CHARACTERISTICS,
    **GATT_DESCRIPTORS,
    **_GATT_OVERRIDES,
}


def company_name(cid: int) -> str | None:
    """Resolve a 16-bit company identifier (the value in BLE manufacturer-specific data)."""
    return COMPANY_IDS.get(cid)


def gatt_name(u16: int) -> str | None:
    """Resolve a 16-bit GATT UUID (service, characteristic, or descriptor)."""
    return _GATT_ALL.get(u16)


def sdp_service_name(u16: int) -> str | None:
    """Resolve a 16-bit SDP Service Class / profile identifier (e.g. 0x1101 Serial Port)."""
    return SDP_SERVICE_CLASSES.get(u16)


def protocol_name(u16: int) -> str | None:
    """Resolve an SDP protocol identifier (e.g. 0x0003 RFCOMM, 0x0100 L2CAP, 0x0007 ATT)."""
    return PROTOCOL_IDS.get(u16)


def ad_type_name(value: int) -> str | None:
    """Resolve an advertising-data / EIR type byte (e.g. 0x01 Flags, 0xFF Manufacturer data)."""
    return AD_TYPES.get(value)


def appearance_name(value: int) -> str | None:
    """Resolve a 16-bit GAP Appearance value (category in the high 10 bits, subcategory in the low 6).

    Returns ``"Category: Subcategory"`` when the subcategory is known, else the category name.
    """
    category, sub = value >> 6, value & 0x3F
    cat_name = _an.APPEARANCE_CATEGORIES.get(category)
    if cat_name is None:
        return None
    sub_name = _an.APPEARANCE_SUBCATEGORIES.get(category, {}).get(sub)
    return f"{cat_name}: {sub_name}" if sub_name else cat_name


def parse_class_of_device(cod: int) -> dict[str, object]:
    """Decode a 24-bit Class of Device into its major service / major+minor device classes.

    Layout (Assigned Numbers, Baseband): bits 0-1 format (00), bits 2-7 minor device class,
    bits 8-12 major device class, bits 13-23 major service classes (a bitfield).
    """
    services = [
        name for bit, name in _an.COD_MAJOR_SERVICE_CLASSES.items() if cod & (1 << bit)
    ]
    major = (cod >> 8) & 0x1F
    minor = (cod >> 2) & 0x3F
    major_name = _an.COD_MAJOR_DEVICE_CLASSES.get(major)
    minor_name = _an.COD_MINOR_DEVICE_CLASSES.get(major, {}).get(minor)
    return {
        "major_service_classes": services,
        "major_device_class": major_name,
        "minor_device_class": minor_name,
        "major": major,
        "minor": minor,
    }


def describe_uuid(uuid: int | str, *, namespace: str = "gatt") -> str:
    """Best-effort human label for a UUID (int 16-bit or 128-bit string).

    ``namespace`` selects which 16-bit table to consult: ``"gatt"`` (default), ``"sdp"``
    (service classes), or ``"protocol"`` (SDP protocol identifiers).
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
        if namespace == "sdp":
            name = sdp_service_name(u16)
        elif namespace == "protocol":
            name = protocol_name(u16)
        else:
            name = gatt_name(u16)
    label = f"0x{u16:04X}" if u16 is not None else full
    return f"{label} ({name})" if name else label
