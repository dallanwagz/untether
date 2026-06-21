"""Advertisement parsing tests."""

from untether_bt import (
    flags,
    local_name,
    manufacturer_data,
    parse_ad,
    service_data,
    service_uuids16,
)
from untether_bt.advertising import ADStructure


def test_parse_ad_length_prefixed():
    # Flags(0x01)=0x06, then Complete Local Name "Hi"
    payload = bytes.fromhex("020106") + bytes([0x03, 0x09]) + b"Hi"
    structs = parse_ad(payload)
    assert structs == [ADStructure(0x01, b"\x06"), ADStructure(0x09, b"Hi")]


def test_parse_ad_tolerates_zero_padding_and_truncation():
    payload = bytes.fromhex("020106") + b"\x00\x00\x00"  # trailing pad
    assert parse_ad(payload) == [ADStructure(0x01, b"\x06")]
    truncated = bytes([0x05, 0x09]) + b"Hi"  # claims 5 but only 2 follow
    assert parse_ad(truncated) == []


def test_manufacturer_data_little_endian_company_id():
    # 0xFF manufacturer, company 0x004C (Apple) little-endian = 4c 00
    payload = bytes([0x05, 0xFF, 0x4C, 0x00, 0xAB, 0xCD])
    cid, data = manufacturer_data(payload)
    assert cid == 0x004C and data == b"\xab\xcd"
    assert manufacturer_data(bytes([0x02, 0x01, 0x06])) is None


def test_govee_style_manufacturer_record():
    # Govee H5104-style: company 0x0001, then the 6-byte payload 01 01 04 a4 64 2b
    # (golden frame from real hardware). AD: len=0x09, type=0xFF, company=01 00 (LE).
    payload = bytes([0x09, 0xFF, 0x01, 0x00, 0x01, 0x01, 0x04, 0xA4, 0x64, 0x2B])
    cid, data = manufacturer_data(payload)
    assert cid == 0x0001
    assert data == bytes.fromhex("010104a4642b")
    packed = int.from_bytes(data[2:5], "big")        # 04 a4 64 = 304228
    assert round((packed // 1000) / 10, 1) == 30.4   # temperature °C
    assert round((packed % 1000) / 10, 1) == 22.8    # humidity %
    assert data[5] == 0x2B                            # battery 43%


def test_service_data_and_uuids():
    # Service Data 16-bit (0x16): uuid 0xEC88 LE = 88 ec, then payload
    payload = bytes([0x05, 0x16, 0x88, 0xEC, 0x11, 0x22])
    assert service_data(payload) == {0xEC88: b"\x11\x22"}
    uuidp = bytes([0x05, 0x03, 0x0F, 0x18, 0x0A, 0x18])  # complete 16-bit list
    assert service_uuids16(uuidp) == [0x180F, 0x180A]


def test_local_name_prefers_complete():
    short = bytes([0x04, 0x08]) + b"abc"
    comp = bytes([0x05, 0x09]) + b"Pixo"
    assert local_name(short) == "abc"
    assert local_name(short + comp) == "Pixo"
    assert local_name(b"\x02\x01\x06") is None


def test_flags():
    assert flags(bytes.fromhex("020106")) == 0x06
    assert flags(b"\x05\x09Pixo") is None
