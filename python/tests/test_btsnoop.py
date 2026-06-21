"""btsnoop parser/writer tests."""

from datetime import datetime, timezone

import pytest

from untether_bt import make_record, parse_btsnoop, write_btsnoop
from untether_bt.btsnoop import (
    BTSNOOP_EPOCH_DELTA_US,
    DLT_HCI_UART_H4,
    iter_btsnoop,
)


def test_round_trip_and_flags():
    u0 = int(datetime(2026, 6, 20, 12, 0, 0, tzinfo=timezone.utc).timestamp() * 1_000_000)
    recs = [
        make_record(b"\x02\x40\x00\x05\x00", unix_us=u0, received=False, command_or_event=False),
        make_record(b"\x04\x0e\x04\x01", unix_us=u0 + 1000, received=True, command_or_event=True),
    ]
    blob = write_btsnoop(DLT_HCI_UART_H4, recs)
    assert blob[:8] == b"btsnoop\x00"
    snoop = parse_btsnoop(blob)
    assert snoop.datalink == DLT_HCI_UART_H4 and snoop.is_h4
    assert len(snoop.records) == 2
    r0, r1 = snoop.records
    assert r0.sent and not r0.received and not r0.is_command_or_event
    assert r1.received and r1.is_command_or_event
    assert r0.data == b"\x02\x40\x00\x05\x00"


def test_year0_epoch_conversion():
    u = int(datetime(2026, 1, 1, tzinfo=timezone.utc).timestamp() * 1_000_000)
    rec = make_record(b"\x00", unix_us=u, received=False, command_or_event=False)
    assert rec.timestamp_us == u + BTSNOOP_EPOCH_DELTA_US  # stored as year-0 µs
    assert rec.unix_us == u
    assert rec.datetime.year == 2026 and rec.datetime.month == 1


def test_bad_magic_raises():
    with pytest.raises(ValueError):
        parse_btsnoop(b"not a snoop file at all............")


def test_truncated_tail_is_ignored():
    u0 = 1_000_000_000_000
    rec = make_record(b"\xaa\xbb", unix_us=u0, received=True, command_or_event=False)
    blob = write_btsnoop(DLT_HCI_UART_H4, [rec])
    # append a partial record header (not enough bytes) -> must be skipped, not crash
    snoop = parse_btsnoop(blob + b"\x00\x00\x00")
    assert len(snoop.records) == 1


def test_iter_btsnoop_yields_datalink():
    rec = make_record(b"\x01\x02", unix_us=5_000_000, received=False, command_or_event=True)
    blob = write_btsnoop(DLT_HCI_UART_H4, [rec])
    items = list(iter_btsnoop(blob))
    assert len(items) == 1 and items[0][0] == DLT_HCI_UART_H4


# ---- btsnooz (Android bug-report) ----
import struct  # noqa: E402
import zlib  # noqa: E402

from untether_bt import is_btsnooz, load_btsnoop  # noqa: E402
from untether_bt.hci import H4_COMMAND, H4_EVENT, hci_packets  # noqa: E402


def _snooz(version, last_ts_ms, records):
    body = b""
    for r in records:
        if version == 1:
            delta, typ, pkt = r
            body += struct.pack("<HIb", len(pkt) + 1, delta, typ) + pkt
        else:
            delta, typ, pkt, orig = r
            body += struct.pack("<HHIb", len(pkt) + 1, orig, delta, typ) + pkt
    return struct.pack("<bQ", version, last_ts_ms) + zlib.compress(body)


def test_btsnooz_v1_round_trip():
    blob = _snooz(1, 2000, [(0, 0x20, b"\x03\x0c\x00"), (10, 0x10, b"\x0e\x04\x01\x00")])
    assert is_btsnooz(blob)
    snoop = load_btsnoop(blob)               # auto-detects btsnooz
    pkts = hci_packets(snoop)
    assert [p.kind for p in pkts] == [H4_COMMAND, H4_EVENT]   # OUT_CMD -> 0x01, IN_EVT -> 0x04
    assert pkts[0].sent and not pkts[1].sent
    assert pkts[0].payload == b"\x03\x0c\x00"                 # H4 indicator stripped
    assert pkts[1].timestamp_us - pkts[0].timestamp_us == 10_000  # 10ms delta preserved
    assert snoop.records[1].unix_us == 2_000_000             # last record == last_timestamp_ms


def test_btsnooz_v2_with_original_length():
    # v2 carries the original (untruncated) length separately
    blob = _snooz(2, 5000, [(0, 0x21, b"\xaa\xbb", 9)])  # OUT_ACL, captured 2 bytes, orig 9
    snoop = load_btsnoop(blob)
    r = snoop.records[0]
    assert r.included_len == 3                # 1 (H4 0x02) + 2 captured
    assert r.original_len == 10               # orig 9 + 1 H4 byte
    assert r.truncated


def test_is_btsnooz_rejects_real_btsnoop():
    blob = write_btsnoop(DLT_HCI_UART_H4, [make_record(b"\x04", unix_us=1, received=True, command_or_event=True)])
    assert not is_btsnooz(blob)
    assert load_btsnoop(blob).records[0].data == b"\x04"  # passes through unchanged
