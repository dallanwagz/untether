"""btsnoop capture file parser/writer — the format every host-side BT RE workflow consumes.

`btsnoop` is what Android's "Bluetooth HCI snoop log" writes (`btsnoop_hci.log`) and what
`btmon -w` / Wireshark read. It captures HCI packets — the choke point where essentially all
Bluetooth activity (BLE *and* Classic) is observable — so it's the most practical RE capture point
(you sidestep RF hopping and key problems).

Format (verified against the FTE spec + Wireshark `wiretap/btsnoop.c`):
  * 16-byte header: ``b"btsnoop\\0"`` · version u32 = 1 · datalink-type u32  (all big-endian)
  * records: ``orig_len u32 · incl_len u32 · flags u32 · drops u32 · timestamp i64`` then data

The notorious gotcha: the timestamp is **signed µs since midnight Jan 1, year 0** — subtract
:data:`BTSNOOP_EPOCH_DELTA_US` to get a Unix-epoch timestamp.
"""

from __future__ import annotations

import struct
from collections.abc import Iterator
from dataclasses import dataclass
from datetime import datetime, timezone

BTSNOOP_MAGIC = b"btsnoop\x00"

# Datalink types
DLT_HCI_UNENCAP_H1 = 1001  # un-encapsulated HCI (no H4 indicator byte; type from flags)
DLT_HCI_UART_H4 = 1002     # each record's data starts with the 1-byte H4 indicator (Android default)
DLT_HCI_BSCP = 1003
DLT_HCI_SERIAL_H5 = 1004
DLT_LINUX_MONITOR = 2001

# Year-0 µs → Unix µs. (Wireshark's constant; resolves 1970→year-0 exactly.)
BTSNOOP_EPOCH_DELTA_US = 0x00DCDDB30F2F8000

# Record flag bits
_FLAG_RECEIVED = 0x01      # 0 = Sent (Host→Controller), 1 = Received (Controller→Host)
_FLAG_CMD_EVT = 0x02       # 0 = ACL/SCO/ISO data, 1 = Command or Event

_HEADER = struct.Struct(">8sII")
_REC = struct.Struct(">IIIIq")  # orig_len, incl_len, flags, drops, timestamp(i64)


@dataclass(frozen=True)
class BtsnoopRecord:
    original_len: int
    included_len: int
    flags: int
    cumulative_drops: int
    timestamp_us: int  # raw: µs since year 0
    data: bytes

    @property
    def received(self) -> bool:
        """True if Controller→Host; False if Host→Controller (the app's outgoing bytes)."""
        return bool(self.flags & _FLAG_RECEIVED)

    @property
    def sent(self) -> bool:
        return not self.received

    @property
    def is_command_or_event(self) -> bool:
        return bool(self.flags & _FLAG_CMD_EVT)

    @property
    def unix_us(self) -> int:
        return self.timestamp_us - BTSNOOP_EPOCH_DELTA_US

    @property
    def datetime(self) -> datetime:
        return datetime.fromtimestamp(self.unix_us / 1_000_000, tz=timezone.utc)

    @property
    def truncated(self) -> bool:
        return self.included_len < self.original_len


@dataclass(frozen=True)
class Btsnoop:
    datalink: int
    records: list[BtsnoopRecord]

    @property
    def is_h4(self) -> bool:
        return self.datalink == DLT_HCI_UART_H4


def iter_btsnoop(data: bytes) -> Iterator[tuple[int, BtsnoopRecord]]:
    """Yield ``(datalink, record)`` for each record. Raises ValueError on a bad header."""
    if len(data) < _HEADER.size or data[:8] != BTSNOOP_MAGIC:
        raise ValueError("not a btsnoop file (bad magic)")
    _magic, version, datalink = _HEADER.unpack_from(data, 0)
    if version != 1:
        raise ValueError(f"unsupported btsnoop version {version}")
    off = _HEADER.size
    n = len(data)
    while off + _REC.size <= n:
        orig, incl, flags, drops, ts = _REC.unpack_from(data, off)
        off += _REC.size
        if off + incl > n:
            break  # truncated tail
        yield datalink, BtsnoopRecord(orig, incl, flags, drops, ts, data[off : off + incl])
        off += incl


def parse_btsnoop(data: bytes) -> Btsnoop:
    """Parse a whole btsnoop file into a :class:`Btsnoop`."""
    datalink = -1
    records: list[BtsnoopRecord] = []
    for datalink, rec in iter_btsnoop(data):
        records.append(rec)
    if datalink == -1:  # header was valid but no records
        _magic, _v, datalink = _HEADER.unpack_from(data, 0)
    return Btsnoop(datalink=datalink, records=records)


def write_btsnoop(datalink: int, records: list[BtsnoopRecord]) -> bytes:
    """Serialize records back to a btsnoop file (useful for tests, slicing, and re-export)."""
    out = bytearray(_HEADER.pack(BTSNOOP_MAGIC, 1, datalink))
    for r in records:
        out += _REC.pack(r.original_len, r.included_len, r.flags, r.cumulative_drops, r.timestamp_us)
        out += r.data
    return bytes(out)


def make_record(
    data: bytes,
    *,
    unix_us: int,
    received: bool,
    command_or_event: bool,
) -> BtsnoopRecord:
    """Build a record from Unix-epoch µs (handles the year-0 offset + flags)."""
    flags = (_FLAG_RECEIVED if received else 0) | (_FLAG_CMD_EVT if command_or_event else 0)
    return BtsnoopRecord(
        original_len=len(data),
        included_len=len(data),
        flags=flags,
        cumulative_drops=0,
        timestamp_us=unix_us + BTSNOOP_EPOCH_DELTA_US,
        data=data,
    )
