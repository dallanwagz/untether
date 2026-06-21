"""SDP (Service Discovery Protocol) decoding — find a Classic device's RFCOMM/SPP channel.

The SPP server channel is **dynamic** — you must browse SDP for it, not hardcode "channel 1". This
module parses SDP **data elements** (the nested type/size-prefixed encoding from Core Vol 3 Part B)
and walks a service record's ProtocolDescriptorList to the RFCOMM channel.

Feed it the bytes of a ServiceSearchAttribute *response* — captured in a btsnoop (SDP rides L2CAP
PSM 0x0001) or returned by a live query. (Issuing the query needs a Classic stack — BlueZ D-Bus, or
the ``untether_spp`` bridge already does SDP-discovery on-device with ``channel: 0``.)
"""

from __future__ import annotations

from .numbers import uuid128_to_16

# Attribute IDs
ATTR_SERVICE_CLASS_ID_LIST = 0x0001
ATTR_PROTOCOL_DESCRIPTOR_LIST = 0x0004
ATTR_SERVICE_NAME = 0x0100

# Protocol UUIDs (16-bit)
UUID_L2CAP = 0x0100
UUID_RFCOMM = 0x0003

_SIZES = {0: 1, 1: 2, 2: 4, 3: 8, 4: 16}        # size-index < 5 → fixed byte counts
_ADDL = {5: 1, 6: 2, 7: 4}                        # size-index ≥ 5 → length in N following bytes


def _uuid_value(raw: bytes) -> int | str:
    """16/32-bit UUID → int; 128-bit → its 16-bit form if on the base UUID, else the canonical str."""
    if len(raw) in (2, 4):
        return int.from_bytes(raw, "big")
    if len(raw) == 16:
        h = raw.hex()
        full = f"{h[:8]}-{h[8:12]}-{h[12:16]}-{h[16:20]}-{h[20:]}"
        u16 = uuid128_to_16(full)
        return u16 if u16 is not None else full
    return raw.hex()


def parse_data_element(data: bytes, offset: int = 0) -> tuple[object, int]:
    """Parse one SDP data element at ``offset``; return ``(value, next_offset)``.

    uint/int → int, uuid → int|str, string/url → bytes, bool → bool, sequence/alternative → list.
    """
    header = data[offset]
    offset += 1
    type_ = header >> 3
    size_index = header & 0x07
    if size_index < 5:
        size = 0 if type_ == 0 else _SIZES[size_index]  # nil has no data
    else:
        addl = _ADDL[size_index]
        size = int.from_bytes(data[offset : offset + addl], "big")
        offset += addl
    raw = data[offset : offset + size]
    end = offset + size

    if type_ == 0:           # nil
        value: object = None
    elif type_ == 1:         # unsigned int
        value = int.from_bytes(raw, "big")
    elif type_ == 2:         # signed int
        value = int.from_bytes(raw, "big", signed=True)
    elif type_ == 3:         # uuid
        value = _uuid_value(raw)
    elif type_ in (4, 8):    # text string / url
        value = raw
    elif type_ == 5:         # bool
        value = bool(raw[0]) if raw else False
    elif type_ in (6, 7):    # sequence / alternative
        seq: list[object] = []
        p = offset
        while p < end:
            item, p = parse_data_element(data, p)
            seq.append(item)
        value = seq
    else:
        value = raw
    return value, end


def record_to_dict(record_seq: list) -> dict[int, object]:
    """A service record is a sequence of alternating (attribute-id, value)."""
    return {record_seq[i]: record_seq[i + 1] for i in range(0, len(record_seq) - 1, 2)}


def parse_records(data: bytes) -> list[dict[int, object]]:
    """Parse a *sequence of service records* (the attribute-lists element) into dicts."""
    top, _ = parse_data_element(data, 0)
    if not isinstance(top, list):
        return []
    out: list[dict[int, object]] = []
    for rec in top:
        if isinstance(rec, list):
            out.append(record_to_dict(rec))
    return out


def parse_ssa_response(pdu: bytes) -> list[dict[int, object]]:
    """Parse a raw SDP ServiceSearchAttributeResponse PDU (0x07) into service-record dicts.

    Assumes a single (non-continued) response.
    """
    # header: pdu_id(1) txn(2) param_len(2) | attr_list_byte_count(2) | <DE> | continuation(>=1)
    if len(pdu) < 7 or pdu[0] != 0x07:
        raise ValueError("not an SDP ServiceSearchAttributeResponse (0x07)")
    count = int.from_bytes(pdu[5:7], "big")
    return parse_records(pdu[7 : 7 + count])


def rfcomm_channel(record: dict[int, object]) -> int | None:
    """Extract the RFCOMM server channel from a record's ProtocolDescriptorList, or None."""
    pdl = record.get(ATTR_PROTOCOL_DESCRIPTOR_LIST)
    if not isinstance(pdl, list):
        return None
    for proto in pdl:
        if isinstance(proto, list) and proto and proto[0] == UUID_RFCOMM and len(proto) >= 2:
            ch = proto[1]
            if isinstance(ch, int):
                return ch
    return None


def find_rfcomm_channels(records: list[dict[int, object]]) -> list[int]:
    """All RFCOMM channels advertised across the given records."""
    return [c for r in records if (c := rfcomm_channel(r)) is not None]


def spp_channel(records: list[dict[int, object]]) -> int | None:
    """The RFCOMM channel of the Serial Port (SPP, 0x1101) record, if present."""
    for r in records:
        classes = r.get(ATTR_SERVICE_CLASS_ID_LIST)
        if isinstance(classes, list) and 0x1101 in classes:
            ch = rfcomm_channel(r)
            if ch is not None:
                return ch
    # fall back to any RFCOMM channel
    chans = find_rfcomm_channels(records)
    return chans[0] if chans else None
