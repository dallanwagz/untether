"""SDP data-element parsing + RFCOMM/SPP channel extraction tests."""

from untether_bt import (
    find_rfcomm_channels,
    parse_data_element,
    parse_records,
    parse_ssa_response,
    rfcomm_channel,
    spp_channel,
)


# --- tiny SDP data-element builders (for crafting test inputs) ---
def u8(v):
    return bytes([0x08, v])


def u16(v):
    return bytes([0x09]) + v.to_bytes(2, "big")


def uuid16(v):
    return bytes([0x19]) + v.to_bytes(2, "big")


def uuid128(hexstr):
    return bytes([0x1C]) + bytes.fromhex(hexstr.replace("-", ""))


def seq(*els):
    body = b"".join(els)
    return bytes([0x35, len(body)]) + body  # sequence, 1-byte length


def test_parse_primitives():
    assert parse_data_element(u16(0x1101))[0] == 0x1101
    assert parse_data_element(uuid16(0x0003))[0] == 0x0003
    assert parse_data_element(seq(u8(1), u8(2), u8(3)))[0] == [1, 2, 3]


def test_uuid128_on_base_collapses_to_16():
    assert parse_data_element(uuid128("0000180f-0000-1000-8000-00805f9b34fb"))[0] == 0x180F


def test_rfcomm_channel_from_record():
    pdl = seq(seq(uuid16(0x0100)), seq(uuid16(0x0003), u8(4)))  # L2CAP, then RFCOMM ch4
    record = seq(u16(0x0004), pdl)
    rec = parse_records(seq(record))[0]
    assert rfcomm_channel(rec) == 4


def test_spp_channel_prefers_the_spp_record():
    spp = seq(
        u16(0x0001), seq(uuid16(0x1101)),                                  # ServiceClassIDList = SPP
        u16(0x0004), seq(seq(uuid16(0x0100)), seq(uuid16(0x0003), u8(2))),  # RFCOMM ch2
    )
    other = seq(
        u16(0x0001), seq(uuid16(0x1124)),                                  # HID, not SPP
        u16(0x0004), seq(seq(uuid16(0x0100)), seq(uuid16(0x0003), u8(9))),  # RFCOMM ch9
    )
    records = parse_records(seq(other, spp))
    assert find_rfcomm_channels(records) == [9, 2]
    assert spp_channel(records) == 2  # picks the SPP one, not the first


def test_parse_ssa_response():
    spp = seq(
        u16(0x0001), seq(uuid16(0x1101)),
        u16(0x0004), seq(seq(uuid16(0x0100)), seq(uuid16(0x0003), u8(3))),
    )
    de = seq(spp)
    pdu = bytes([0x07, 0x00, 0x01]) + len(de + b"\x00").to_bytes(2, "big") \
        + len(de).to_bytes(2, "big") + de + b"\x00"  # +continuation byte
    recs = parse_ssa_response(pdu)
    assert spp_channel(recs) == 3
