"""HCI / L2CAP / ATT decoding over a btsnoop capture — extract the bytes you reverse.

Layered on :mod:`untether_bt.btsnoop`. The high-value RE extractions:
  * :func:`hci_packets` — classify each record (Command/Event/ACL/SCO/ISO) with direction + time.
  * :func:`l2cap_payloads` — ACL → L2CAP, yielding ``(time, sent, handle, cid, payload)`` (the
    generic hook for *any* upper layer, including Classic RFCOMM on its dynamic CID).
  * :func:`att_pdus` — the BLE workhorse: GATT Write/Notify/Indicate with handle + value, i.e. the
    actual command/status bytes an app exchanges.

Limitation (first pass): L2CAP fragment reassembly handles the common single-fragment case (app
GATT writes/notifies at typical MTU fit one ACL fragment); continuation fragments are skipped and
counted, not stitched. Full reassembly + RFCOMM CID tracking come next.
"""

from __future__ import annotations

from dataclasses import dataclass

from .btsnoop import Btsnoop, parse_btsnoop

# H4 transport indicator bytes (present per-record when datalink is H4)
H4_COMMAND = 0x01
H4_ACL = 0x02
H4_SCO = 0x03
H4_EVENT = 0x04
H4_ISO = 0x05
_H4_NAMES = {0x01: "command", 0x02: "acl", 0x03: "sco", 0x04: "event", 0x05: "iso"}

# L2CAP fixed CIDs
CID_ATT = 0x0004
CID_LE_SIGNALING = 0x0005
CID_SMP = 0x0006

# ATT opcodes that carry a handle (+ value)
ATT_WRITE_REQ = 0x12
ATT_WRITE_CMD = 0x52
ATT_NOTIFY = 0x1B
ATT_INDICATE = 0x1D
ATT_READ_REQ = 0x0A
ATT_READ_RSP = 0x0B
_ATT_HANDLE_VALUE = {ATT_WRITE_REQ, ATT_WRITE_CMD, ATT_NOTIFY, ATT_INDICATE}
_ATT_NAMES = {
    0x12: "write_req", 0x52: "write_cmd", 0x1B: "notify", 0x1D: "indicate",
    0x0A: "read_req", 0x0B: "read_rsp", 0x13: "write_rsp", 0x01: "error_rsp",
}


@dataclass(frozen=True)
class HciPacket:
    timestamp_us: int  # Unix µs
    sent: bool         # True = Host→Controller (the app's outgoing direction)
    kind: int          # H4_* type
    payload: bytes     # bytes after the H4 indicator

    @property
    def kind_name(self) -> str:
        return _H4_NAMES.get(self.kind, f"0x{self.kind:02x}")


@dataclass(frozen=True)
class L2capPayload:
    timestamp_us: int
    sent: bool
    handle: int  # ACL connection handle
    cid: int
    payload: bytes


@dataclass(frozen=True)
class AttPdu:
    timestamp_us: int
    sent: bool
    handle: int        # ACL connection handle
    opcode: int
    att_handle: int | None  # attribute handle (for write/notify/indicate/read)
    value: bytes

    @property
    def opcode_name(self) -> str:
        return _ATT_NAMES.get(self.opcode, f"0x{self.opcode:02x}")


def hci_packets(snoop: Btsnoop | bytes) -> list[HciPacket]:
    """Classify each record into an :class:`HciPacket` (handles H4 indicator vs H1)."""
    if isinstance(snoop, (bytes, bytearray)):
        snoop = parse_btsnoop(bytes(snoop))
    out: list[HciPacket] = []
    for r in snoop.records:
        if not r.data:
            continue
        if snoop.is_h4:
            kind, payload = r.data[0], r.data[1:]
        else:
            # H1 / un-encapsulated: no indicator byte; derive from flags.
            if r.is_command_or_event:
                kind = H4_EVENT if r.received else H4_COMMAND
            else:
                kind = H4_ACL
            payload = r.data
        out.append(HciPacket(r.unix_us, r.sent, kind, payload))
    return out


def _acl_fragments(packets: list[HciPacket]):
    """Yield (packet, handle, pb, l2cap_payload_fragment) for ACL packets."""
    for p in packets:
        if p.kind != H4_ACL or len(p.payload) < 4:
            continue
        hf = p.payload[0] | (p.payload[1] << 8)
        handle = hf & 0x0FFF
        pb = (hf >> 12) & 0x3
        total = p.payload[2] | (p.payload[3] << 8)
        frag = p.payload[4 : 4 + total]
        yield p, handle, pb, frag


def l2cap_payloads(packets: list[HciPacket]) -> list[L2capPayload]:
    """Extract L2CAP B-frames (single-fragment) as ``(time, sent, handle, cid, payload)``."""
    out: list[L2capPayload] = []
    for p, handle, pb, frag in _acl_fragments(packets):
        # pb 0b00 = first auto-flushable, 0b10 = first non-flushable -> start of an L2CAP PDU.
        # pb 0b01 = continuation -> skip (not reassembled in this pass).
        if pb == 0b01 or len(frag) < 4:
            continue
        l2_len = frag[0] | (frag[1] << 8)
        cid = frag[2] | (frag[3] << 8)
        body = frag[4 : 4 + l2_len]
        out.append(L2capPayload(p.timestamp_us, p.sent, handle, cid, body))
    return out


def att_pdus(packets: list[HciPacket]) -> list[AttPdu]:
    """Extract ATT PDUs (the GATT command/status bytes) from the capture."""
    out: list[AttPdu] = []
    for lp in l2cap_payloads(packets):
        if lp.cid != CID_ATT or not lp.payload:
            continue
        opcode = lp.payload[0]
        if opcode in _ATT_HANDLE_VALUE and len(lp.payload) >= 3:
            att_handle = lp.payload[1] | (lp.payload[2] << 8)
            value = lp.payload[3:]
        elif opcode == ATT_READ_REQ and len(lp.payload) >= 3:
            att_handle = lp.payload[1] | (lp.payload[2] << 8)
            value = b""
        else:
            att_handle, value = None, lp.payload[1:]
        out.append(AttPdu(lp.timestamp_us, lp.sent, lp.handle, opcode, att_handle, value))
    return out
