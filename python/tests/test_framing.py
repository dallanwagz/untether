"""Codec tests — pinned to golden vectors captured from real Divoom hardware."""

import pytest

from untether_bt import DIVOOM_NEWMODE, DIVOOM_STUFFED, Frame, Framing, Stuffing, crc_sum16


# ---- NewMode (no byte-stuffing): golden frames from live Pixoo capture ----
def test_newmode_golden():
    assert DIVOOM_NEWMODE.build(0xAF, b"\x01").hex() == "010400af01b40002"          # handshake
    assert DIVOOM_NEWMODE.build(0x74, b"\x32").hex() == "0104007432aa0002"          # brightness 50
    assert DIVOOM_NEWMODE.build(0x74, b"\x64").hex() == "0104007464dc0002"          # brightness 100


def test_crc_carry_past_0xffff():
    # a payload whose byte-sum exceeds 0xFFFF proves the &0xFFFF masking
    payload = b"\xff" * 600
    f = DIVOOM_NEWMODE.build(0x44, payload)
    assert f[0] == 0x01 and f[-1] == 0x02
    inner = f[1:-1]
    crc = int.from_bytes(inner[-2:], "little")
    assert crc == crc_sum16(inner[:-2])
    assert sum(inner[:-2]) > 0xFFFF


@pytest.mark.parametrize("t,payload", [(0x74, b"\x32"), (0xAF, b"\x01"), (0x44, bytes(range(80)))])
def test_newmode_round_trip(t, payload):
    frames, leftover = DIVOOM_NEWMODE.iter_frames(DIVOOM_NEWMODE.build(t, payload))
    assert leftover == b"" and frames == [Frame(t, payload)]


def test_frame_body_helper():
    assert Frame(0x74, b"\x32").body == b"\x74\x32"
    assert Frame(0x74, b"\x32").hex() == "7432"


# ---- inbound parser robustness (unstuffed) ----
ECHO = bytes.fromhex("011b00044655000000ff5000640001036400ffffff00010000000000d30502")


def test_split_byte_by_byte():
    stream = ECHO + DIVOOM_NEWMODE.build(0x74, b"\x32") + ECHO
    got, leftover = [], b""
    for byte in stream:
        frames, leftover = DIVOOM_NEWMODE.iter_frames(leftover + bytes((byte,)))
        got.extend(frames)
    assert leftover == b"" and len(got) == 3


def test_leading_garbage_resyncs():
    junk = b"\x99\x01\x05\x77\x88\x00\xab\x02\x13"
    frames, leftover = DIVOOM_NEWMODE.iter_frames(junk + ECHO)
    assert len(frames) == 1 and leftover == b""


def test_stray_soi_bad_eoi_skipped():
    bad = b"\x01\x04\x00\xde\xad\xbe\xef"  # end byte != EOI
    frames, _ = DIVOOM_NEWMODE.iter_frames(bad + ECHO)
    assert len(frames) == 1


def test_absurd_length_does_not_stall():
    frames, _ = DIVOOM_NEWMODE.iter_frames(b"\x01\xff\xff" + ECHO)
    assert len(frames) == 1


def test_partial_trailing_carried():
    frames, leftover = DIVOOM_NEWMODE.iter_frames(ECHO + b"\x01\x1b\x00\x04")
    assert len(frames) == 1 and leftover == b"\x01\x1b\x00\x04"


def test_bad_crc_rejected():
    f = bytearray(DIVOOM_NEWMODE.build(0x74, b"\x32"))
    f[4] ^= 0xFF  # corrupt a body byte; CRC no longer matches
    frames, _ = DIVOOM_NEWMODE.iter_frames(bytes(f))
    assert frames == []


# ---- stuffing (TimeBox-mini) ----
def test_stuffing_round_trip():
    s = Stuffing()
    assert s.encode(b"\x01\x02\x03\x10") == b"\x03\x04\x03\x05\x03\x06\x10"
    assert s.decode(s.encode(bytes(range(8)))) == bytes(range(8))


def test_stuffed_framing_round_trip():
    # pick a payload whose CRC/body forces stuffing, then round-trip through iter_frames
    for level in range(0, 256):
        raw = DIVOOM_STUFFED.build(0x74, bytes((level,)))
        frames, leftover = DIVOOM_STUFFED.iter_frames(raw)
        assert leftover == b""
        assert frames == [Frame(0x74, bytes((level,)))]


def test_stuffed_markers_absent_in_body():
    # the whole point of stuffing: no SOI/EOI inside the encoded inner region
    raw = DIVOOM_STUFFED.build(0x01, b"\x01\x02\x02\x01")
    assert raw[0] == 0x01 and raw[-1] == 0x02
    assert 0x01 not in raw[1:-1] and 0x02 not in raw[1:-1]


def test_custom_framing_no_len_crc_counting():
    # a framing where LEN counts only the body (not the CRC)
    fr = Framing(len_counts_crc=False)
    frames, _ = fr.iter_frames(fr.build(0x10, b"\xaa\xbb"))
    assert frames == [Frame(0x10, b"\xaa\xbb")]
