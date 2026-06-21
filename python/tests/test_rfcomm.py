"""RFCOMM (TS 07.10 subset) frame decoder tests.

FCS is validated against golden frames from real RFCOMM captures (independently documented):
the SABM on DLCI 0 is ``03 3f 01 1c`` and the matching UA is ``03 73 01 d7``.
"""

from untether_bt import MuxCommand, RfcommFrame, check_fcs, iter_rfcomm, parse_rfcomm
from untether_bt.rfcomm import build_address, build_frame, fcs


def test_fcs_golden_frames():
    assert fcs(bytes([0x03, 0x3F, 0x01])) == 0x1C   # SABM DLCI 0
    assert fcs(bytes([0x03, 0x73, 0x01])) == 0xD7   # UA   DLCI 0
    assert check_fcs(bytes([0x03, 0x3F, 0x01]), 0x1C)
    assert not check_fcs(bytes([0x03, 0x3F, 0x01]), 0x00)


def test_parse_sabm_on_control_channel():
    f = parse_rfcomm(bytes([0x03, 0x3F, 0x01, 0x1C]))
    assert isinstance(f, RfcommFrame)
    assert f.frame_type == "SABM"
    assert f.dlci == 0 and f.is_mux_control
    assert f.poll_final is True
    assert f.cr == 1
    assert f.length == 0 and f.information == b""
    assert f.fcs == 0x1C and f.fcs_ok


def test_parse_ua_response():
    f = parse_rfcomm(bytes([0x03, 0x73, 0x01, 0xD7]))
    assert f.frame_type == "UA" and f.fcs_ok and f.poll_final


def test_dlci_decode_direction_and_server_channel():
    # server channel 5, direction bit 1 -> DLCI = (5<<1)|1 = 11
    addr = build_address(5, direction=1, cr=1)
    f = parse_rfcomm(build_frame(addr, 0x2F | 0x10))  # SABM
    assert f.server_channel == 5
    assert f.direction == 1
    assert f.dlci == 11


def test_uih_data_round_trip_and_fcs_coverage():
    addr = build_address(3, direction=0, cr=1)
    frame = build_frame(addr, 0xEF, b"\x01\x02\x03\x04")  # UIH, no P/F
    f = parse_rfcomm(frame)
    assert f.frame_type == "UIH"
    assert f.server_channel == 3 and f.dlci == 6
    assert f.information == b"\x01\x02\x03\x04"
    assert f.credits is None
    assert f.fcs_ok  # UIH FCS covers only address+control


def test_uih_credit_based_flow_control():
    # UIH on a data DLC with P/F set carries a leading credit octet
    addr = build_address(2, direction=1, cr=1)
    frame = build_frame(addr, 0xEF | 0x10, b"payload", credits=7)
    f = parse_rfcomm(frame)
    assert f.frame_type == "UIH" and f.poll_final
    assert f.credits == 7
    assert f.information == b"payload"
    assert f.fcs_ok


def test_two_octet_length_for_large_frames():
    addr = build_address(1, direction=1, cr=1)
    info = bytes(range(200))  # > 127 -> 2-octet length indicator
    f = parse_rfcomm(build_frame(addr, 0xEF, info))
    assert f.length == 200 and f.information == info and f.fcs_ok


def test_mux_command_decode():
    # a UIH on DLCI 0 carrying a PN command (type octet 0x20 | EA, then length, then value)
    addr = build_address(0, direction=0, cr=1)   # DLCI 0
    pn_value = b"\x09\xf0\x00"
    info = bytes([0x20 | 0x02 | 0x01, (len(pn_value) << 1) | 0x01]) + pn_value  # PN command
    f = parse_rfcomm(build_frame(addr, 0xEF, info))
    cmd = f.mux_command()
    assert isinstance(cmd, MuxCommand)
    assert cmd.type == "PN" and cmd.command is True
    assert cmd.value == pn_value


def test_msc_command_type():
    addr = build_address(0, direction=0, cr=1)
    info = bytes([0x38 | 0x02 | 0x01, 0x03]) + b"\x0b\x8d"  # MSC command
    f = parse_rfcomm(build_frame(addr, 0xEF, info))
    assert f.mux_command().type == "MSC"


def test_rejects_garbage_and_short_frames():
    assert parse_rfcomm(b"\x01\x02") is None       # too short
    assert parse_rfcomm(b"\x03\x3f\x01\x00") is not None  # parses, but...
    assert parse_rfcomm(b"\x03\x3f\x01\x00").fcs_ok is False  # ...bad FCS flagged


def test_iter_rfcomm_filters_by_fcs():
    good = build_frame(build_address(1, direction=1, cr=1), 0xEF, b"hi")
    bad = b"\xde\xad\xbe\xef\x00\x11\x22"  # not RFCOMM
    frames = list(iter_rfcomm([good, bad]))
    assert len(frames) == 1 and frames[0].information == b"hi"
    # without the filter, the junk may parse too (or not), but the good one always survives
    assert any(fr.information == b"hi" for fr in iter_rfcomm([good, bad], require_valid_fcs=False))


def test_iter_rfcomm_accepts_payload_objects():
    class P:
        def __init__(self, payload):
            self.payload = payload

    good = build_frame(build_address(4, direction=0, cr=1), 0xEF, b"\xaa")
    frames = list(iter_rfcomm([P(good)]))
    assert len(frames) == 1 and frames[0].server_channel == 4
