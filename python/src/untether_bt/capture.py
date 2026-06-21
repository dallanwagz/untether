"""Capture + correlation — the heart of the app→protocol RE pipeline.

Load an Android/btmon `btsnoop` capture, get a unified list of **wire events** (the meaningful
GATT / L2CAP bytes, both directions, timestamped), and **correlate** them to UI-action marks — i.e.
answer "when I tapped *Power*, what bytes went out?" That UI-action↔wire-byte correlation is the
step every existing toolchain leaves to ad-hoc manual work; here it's a function.

Marks come from whatever drove the app (the ADB/UIAutomator driver, or a human announcing actions);
:class:`Recorder` is a tiny helper to timestamp them. Correlation is pure and unit-tested.
"""

from __future__ import annotations

import time
from dataclasses import dataclass, field

from .btsnoop import parse_btsnoop
from .hci import AttPdu, HciPacket, att_pdus, hci_packets, l2cap_payloads


@dataclass(frozen=True)
class WireEvent:
    """One meaningful exchanged frame, transport-agnostic."""

    timestamp_us: int
    sent: bool                # True = app→device (outgoing)
    transport: str            # "att" | "l2cap"
    summary: str              # human-readable (e.g. "write_cmd handle=0x002a")
    data: bytes               # the payload bytes you reverse

    def direction(self) -> str:
        return "TX" if self.sent else "RX"


@dataclass(frozen=True)
class Mark:
    timestamp_us: int
    label: str


@dataclass
class Correlation:
    mark: Mark
    events: list[WireEvent] = field(default_factory=list)


class Capture:
    """A decoded btsnoop capture with RE-friendly views."""

    def __init__(self, packets: list[HciPacket]) -> None:
        self.packets = packets

    @classmethod
    def from_btsnoop(cls, data: bytes) -> Capture:
        return cls(hci_packets(parse_btsnoop(data)))

    def att(self) -> list[AttPdu]:
        return att_pdus(self.packets)

    def wire_events(self, *, include_l2cap: bool = False) -> list[WireEvent]:
        """The unified RE view: ATT PDUs (always) + raw non-ATT L2CAP (optional, e.g. RFCOMM)."""
        events: list[WireEvent] = [
            WireEvent(
                a.timestamp_us,
                a.sent,
                "att",
                f"{a.opcode_name}"
                + (f" handle=0x{a.att_handle:04x}" if a.att_handle is not None else ""),
                a.value,
            )
            for a in self.att()
        ]
        if include_l2cap:
            for lp in l2cap_payloads(self.packets):
                if lp.cid == 0x0004:  # ATT already covered above
                    continue
                events.append(
                    WireEvent(lp.timestamp_us, lp.sent, "l2cap", f"cid=0x{lp.cid:04x}", lp.payload)
                )
        events.sort(key=lambda e: e.timestamp_us)
        return events


def correlate(
    events: list[WireEvent],
    marks: list[Mark],
    *,
    window_us: int = 2_000_000,
) -> list[Correlation]:
    """Attribute each wire event to the most recent preceding mark (within ``window_us``).

    Returns one :class:`Correlation` per mark, in mark order, each holding the events that fired
    after that mark and before the next one (and within the window). The classic RE move: drive one
    UI action at a time, mark it, and read back exactly the frames it produced.
    """
    marks = sorted(marks, key=lambda m: m.timestamp_us)
    result = [Correlation(m) for m in marks]
    if not marks:
        return result
    for ev in sorted(events, key=lambda e: e.timestamp_us):
        # find the latest mark at or before this event
        idx = -1
        for i, m in enumerate(marks):
            if m.timestamp_us <= ev.timestamp_us:
                idx = i
            else:
                break
        if idx < 0:
            continue
        if ev.timestamp_us - marks[idx].timestamp_us <= window_us:
            result[idx].events.append(ev)
    return result


class Recorder:
    """Timestamp UI-action marks while you (or a driver) exercise the app."""

    def __init__(self) -> None:
        self.marks: list[Mark] = []

    def mark(self, label: str, *, unix_us: int | None = None) -> Mark:
        m = Mark(unix_us if unix_us is not None else int(time.time() * 1_000_000), label)
        self.marks.append(m)
        return m
