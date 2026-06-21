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


# --- btsnooz (Android bug-report) -------------------------------------------
# Android bug reports embed a compressed "btsnooz" blob (NOT standard btsnoop). Format per AOSP
# btsnooz.py: header `<bQ` (version 1|2, last_timestamp_ms), then a zlib stream of records —
# v1 `<HIb` (length, delta_ms, type), v2 `<HHIb` (length, orig_packet_len, delta_ms, type); each
# record's HCI payload is `length-1` bytes; timestamps are reconstructed from the trailing
# last_timestamp by subtracting the summed deltas. We emit a standard H4 btsnoop.

# snooz type -> H4 indicator
_SNOOZ_H4 = {0x10: 0x04, 0x11: 0x02, 0x12: 0x03, 0x20: 0x01, 0x21: 0x02, 0x22: 0x03}
_SNOOZ_IN = {0x10, 0x11, 0x12}  # IN_EVT / IN_ACL / IN_SCO -> received


def is_btsnooz(data: bytes) -> bool:
    return len(data) >= 9 and data[:8] != BTSNOOP_MAGIC and data[0] in (1, 2)


def decompress_btsnooz(snooz: bytes) -> bytes:
    """Decompress an Android btsnooz blob into a standard btsnoop file (bytes).

    ``last_timestamp_ms`` is treated as Unix-epoch ms (so the resulting absolute times are correct
    if it was; relative timing is exact regardless).
    """
    import zlib

    if len(snooz) < 9:
        raise ValueError("btsnooz too short")
    version, last_ts_ms = struct.unpack_from("<bQ", snooz, 0)
    if version not in (1, 2):
        raise ValueError(f"unsupported btsnooz version {version}")
    data = zlib.decompress(snooz[9:])

    parsed: list[tuple[int, int, bytes, int | None]] = []  # (delta_ms, type, pkt, orig_len)
    off, n, total_delta = 0, len(data), 0
    while off < n:
        if version == 1:
            length, delta_ms, typ = struct.unpack_from("<HIb", data, off)
            hdr, orig_len = 7, None
        else:
            length, orig_packet_len, delta_ms, typ = struct.unpack_from("<HHIb", data, off)
            hdr, orig_len = 9, orig_packet_len
        pkt = data[off + hdr : off + hdr + (length - 1)]
        parsed.append((delta_ms, typ, pkt, orig_len))
        total_delta += delta_ms
        off += hdr + (length - 1)

    ts_ms = last_ts_ms - total_delta
    records: list[BtsnoopRecord] = []
    for delta_ms, typ, pkt, orig_len in parsed:
        ts_ms += delta_ms
        h4 = _SNOOZ_H4.get(typ)
        if h4 is None:
            continue
        h4_data = bytes((h4,)) + pkt
        records.append(
            BtsnoopRecord(
                original_len=(orig_len + 1) if orig_len is not None else len(h4_data),
                included_len=len(h4_data),
                flags=(_FLAG_RECEIVED if typ in _SNOOZ_IN else 0)
                | (_FLAG_CMD_EVT if h4 in (0x01, 0x04) else 0),
                cumulative_drops=0,
                timestamp_us=ts_ms * 1000 + BTSNOOP_EPOCH_DELTA_US,
                data=h4_data,
            )
        )
    return write_btsnoop(DLT_HCI_UART_H4, records)


def load_btsnoop(data: bytes) -> Btsnoop:
    """Parse a capture whether it's standard btsnoop or a btsnooz blob (auto-detected)."""
    return parse_btsnoop(decompress_btsnooz(data) if is_btsnooz(data) else data)
