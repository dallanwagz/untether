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
