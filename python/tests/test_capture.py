"""HCI/ATT extraction + capture correlation tests (synthetic btsnoop)."""

from untether_bt import (
    Capture,
    Mark,
    att_pdus,
    correlate,
    hci_packets,
    make_record,
    parse_btsnoop,
    write_btsnoop,
)
from untether_bt.btsnoop import DLT_HCI_UART_H4
from untether_bt.hci import H4_ACL, H4_COMMAND, H4_EVENT


def _acl_att(handle: int, opcode: int, att_handle: int | None, value: bytes) -> bytes:
    """Build an H4 ACL record carrying one ATT PDU on CID 0x0004 (single fragment, pb=0b00)."""
    att = bytes([opcode])
    if att_handle is not None:
        att += att_handle.to_bytes(2, "little")
    att += value
    l2cap = len(att).to_bytes(2, "little") + (0x0004).to_bytes(2, "little") + att
    hf = handle & 0x0FFF  # pb=0b00, bc=0b00
    acl = hf.to_bytes(2, "little") + len(l2cap).to_bytes(2, "little") + l2cap
    return bytes([H4_ACL]) + acl


def _record(h4: bytes, unix_us: int, sent: bool, cmd_evt: bool = False):
    return make_record(h4, unix_us=unix_us, received=not sent, command_or_event=cmd_evt)


def test_hci_classification_and_direction():
    recs = [
        _record(bytes([H4_COMMAND, 0x03, 0x0C, 0x00]), 1_000_000, sent=True, cmd_evt=True),
        _record(bytes([H4_EVENT, 0x0E, 0x04, 0x01]), 1_000_100, sent=False, cmd_evt=True),
        _record(_acl_att(0x40, 0x52, 0x002A, b"\x32"), 1_000_200, sent=True),
    ]
    pkts = hci_packets(parse_btsnoop(write_btsnoop(DLT_HCI_UART_H4, recs)))
    assert [p.kind for p in pkts] == [H4_COMMAND, H4_EVENT, H4_ACL]
    assert [p.sent for p in pkts] == [True, False, True]
    assert pkts[0].kind_name == "command"


def test_att_extraction():
    recs = [
        _record(_acl_att(0x40, 0x52, 0x002A, b"\xde\xad"), 2_000_000, sent=True),     # write_cmd
        _record(_acl_att(0x40, 0x1B, 0x002C, b"\xbe\xef\x01"), 2_000_500, sent=False),  # notify
        _record(_acl_att(0x40, 0x0A, 0x002C, b""), 2_000_700, sent=True),             # read_req
    ]
    pkts = hci_packets(parse_btsnoop(write_btsnoop(DLT_HCI_UART_H4, recs)))
    pdus = att_pdus(pkts)
    assert [(p.opcode_name, p.att_handle, p.value, p.sent) for p in pdus] == [
        ("write_cmd", 0x002A, b"\xde\xad", True),
        ("notify", 0x002C, b"\xbe\xef\x01", False),
        ("read_req", 0x002C, b"", True),
    ]


def test_wire_events_and_correlation():
    # power tapped at t0 -> write at t0+0.1s ; stop tapped at t0+3s -> write at t0+3.1s
    t0 = 10_000_000
    recs = [
        _record(_acl_att(0x40, 0x52, 0x002A, b"\x01"), t0 + 100_000, sent=True),
        _record(_acl_att(0x40, 0x52, 0x002A, b"\x00"), t0 + 3_100_000, sent=True),
        _record(_acl_att(0x40, 0x1B, 0x002C, b"\x99"), t0 - 50_000, sent=False),  # before any mark
    ]
    cap = Capture.from_btsnoop(write_btsnoop(DLT_HCI_UART_H4, recs))
    events = cap.wire_events()
    assert len(events) == 3 and events[0].timestamp_us < events[1].timestamp_us

    marks = [Mark(t0, "power"), Mark(t0 + 3_000_000, "stop")]
    corr = correlate(events, marks, window_us=2_000_000)
    assert [c.mark.label for c in corr] == ["power", "stop"]
    assert [e.data for e in corr[0].events] == [b"\x01"]   # power -> the 0x01 write
    assert [e.data for e in corr[1].events] == [b"\x00"]   # stop  -> the 0x00 write
    # the pre-mark event is attributed to nothing
    assert sum(len(c.events) for c in corr) == 2


def test_correlation_window_excludes_late_events():
    t0 = 0
    events = Capture(
        hci_packets(
            parse_btsnoop(
                write_btsnoop(
                    DLT_HCI_UART_H4,
                    [_record(_acl_att(0x40, 0x52, 0x2A, b"\x05"), t0 + 5_000_000, sent=True)],
                )
            )
        )
    ).wire_events()
    corr = correlate(events, [Mark(t0, "tap")], window_us=2_000_000)
    assert corr[0].events == []  # event is 5s after the mark, beyond the 2s window


def test_sdp_records_from_capture():
    from untether_bt import spp_channel

    # build a minimal SDP SSA response advertising SPP on RFCOMM channel 5
    def u8(v):
        return bytes([0x08, v])

    def u16(v):
        return bytes([0x09]) + v.to_bytes(2, "big")

    def uuid16(v):
        return bytes([0x19]) + v.to_bytes(2, "big")

    def seq(*e):
        body = b"".join(e)
        return bytes([0x35, len(body)]) + body
    record = seq(
        u16(0x0001), seq(uuid16(0x1101)),
        u16(0x0004), seq(seq(uuid16(0x0100)), seq(uuid16(0x0003), u8(5))),
    )
    de = seq(record)
    pdu = bytes([0x07, 0x00, 0x01]) + (len(de) + 3).to_bytes(2, "big") \
        + len(de).to_bytes(2, "big") + de + b"\x00"
    # wrap as an L2CAP payload (SDP CID) inside an ACL HCI record
    l2cap = len(pdu).to_bytes(2, "little") + (0x0040).to_bytes(2, "little") + pdu
    acl = (0x40).to_bytes(2, "little") + len(l2cap).to_bytes(2, "little") + l2cap
    rec = _record(bytes([H4_ACL]) + acl, 1, sent=False)

    cap = Capture.from_btsnoop(write_btsnoop(DLT_HCI_UART_H4, [rec]))
    records = cap.sdp_records()
    assert spp_channel(records) == 5


def test_l2cap_non_att_payload_extracted():
    # a Classic-style payload on a dynamic CID (the RFCOMM hook) shows up in include_l2cap view
    handle, cid = 0x40, 0x0040
    body = b"\x01\x04\x00\x74\x32\xaa\x00\x02"
    l2cap = len(body).to_bytes(2, "little") + cid.to_bytes(2, "little") + body
    acl = (handle & 0x0FFF).to_bytes(2, "little") + len(l2cap).to_bytes(2, "little") + l2cap
    rec = _record(bytes([H4_ACL]) + acl, 1, sent=True)
    cap = Capture.from_btsnoop(write_btsnoop(DLT_HCI_UART_H4, [rec]))
    events = cap.wire_events(include_l2cap=True)
    assert any(e.transport == "l2cap" and e.data == body for e in events)
