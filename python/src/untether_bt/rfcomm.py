"""RFCOMM (TS 07.10 subset) frame decoder — read Bluetooth Classic serial multiplexing on the wire.

When you capture a Classic SPP session at HCI, the RFCOMM frames sit inside L2CAP payloads on a
dynamic CID (RFCOMM is L2CAP PSM ``0x0003``). The ``untether_spp`` bridge normally de-multiplexes
RFCOMM for you and hands up the clean serial stream — but when you're reading a raw ``btsnoop``
capture, or building a bridge, or debugging why a DLC won't open, you need to decode the frames
yourself. This module does that.

The frame layout (TS 07.10 *basic option*, with the opening/closing flags dropped per RFCOMM)::

    Address(1) · Control(1) · Length(1-2) · [Credits(1)] · Information(0..N) · FCS(1)

* **Address** packs EA, C/R, and the DLCI. RFCOMM splits the 6-bit DLCI into a 1-bit direction and a
  5-bit *server channel* (1-30, the number SDP advertises): ``DLCI = (server_channel << 1) | dir``.
  DLCI 0 is the multiplexer control channel.
* **Control** selects the frame type (SABM/UA/DM/DISC/UIH) with a P/F bit (``0x10``) on top.
* **FCS** is a CRC-8 over Address+Control+Length for SABM/DISC/UA/DM, but only Address+Control for
  UIH (the data frame). The CRC table and check are the canonical TS 07.10 / Linux-kernel ones.
* **Credits**: with credit-based flow control, a UIH frame on a *data* DLC with the P/F bit set
  carries a one-octet credit count right after the length.

See ``docs/CLASSIC-BT-RE-HANDBOOK.md`` for the full protocol map.
"""

from __future__ import annotations

from collections.abc import Iterable, Iterator
from dataclasses import dataclass

RFCOMM_PSM = 0x0003  # the L2CAP PSM RFCOMM rides on

# Frame type values (control field with the P/F bit masked off), per TS 07.10 / kernel rfcomm.h
_PF = 0x10
_TYPE_MASK = 0xEF  # ~P/F
_FRAME_TYPES: dict[int, str] = {
    0x2F: "SABM",  # command  — open a DLC
    0x63: "UA",    # response — accepted
    0x0F: "DM",    # response — refused / disconnected
    0x43: "DISC",  # command  — close a DLC
    0xEF: "UIH",   # command & response — data + MUX control
}

# Multiplexer control-channel command types (the type octet with EA/C-R bits masked off, &0xFC)
_MUX_COMMANDS: dict[int, str] = {
    0x08: "TEST",   # test
    0x28: "FCON",   # flow control on (aggregate)
    0x18: "FCOFF",  # flow control off (aggregate)
    0x38: "MSC",    # modem status command (RS-232 signals + break)
    0x24: "RPN",    # remote port negotiation
    0x14: "RLS",    # remote line status
    0x20: "PN",     # DLC parameter negotiation (frame size, credit-based flow control)
    0x04: "NSC",    # non-supported command response
}

# Canonical TS 07.10 FCS CRC-8 table (matches the Linux kernel rfcomm_crc_table).
_CRC = (
    0x00, 0x91, 0xe3, 0x72, 0x07, 0x96, 0xe4, 0x75, 0x0e, 0x9f, 0xed, 0x7c, 0x09, 0x98, 0xea, 0x7b,
    0x1c, 0x8d, 0xff, 0x6e, 0x1b, 0x8a, 0xf8, 0x69, 0x12, 0x83, 0xf1, 0x60, 0x15, 0x84, 0xf6, 0x67,
    0x38, 0xa9, 0xdb, 0x4a, 0x3f, 0xae, 0xdc, 0x4d, 0x36, 0xa7, 0xd5, 0x44, 0x31, 0xa0, 0xd2, 0x43,
    0x24, 0xb5, 0xc7, 0x56, 0x23, 0xb2, 0xc0, 0x51, 0x2a, 0xbb, 0xc9, 0x58, 0x2d, 0xbc, 0xce, 0x5f,
    0x70, 0xe1, 0x93, 0x02, 0x77, 0xe6, 0x94, 0x05, 0x7e, 0xef, 0x9d, 0x0c, 0x79, 0xe8, 0x9a, 0x0b,
    0x6c, 0xfd, 0x8f, 0x1e, 0x6b, 0xfa, 0x88, 0x19, 0x62, 0xf3, 0x81, 0x10, 0x65, 0xf4, 0x86, 0x17,
    0x48, 0xd9, 0xab, 0x3a, 0x4f, 0xde, 0xac, 0x3d, 0x46, 0xd7, 0xa5, 0x34, 0x41, 0xd0, 0xa2, 0x33,
    0x54, 0xc5, 0xb7, 0x26, 0x53, 0xc2, 0xb0, 0x21, 0x5a, 0xcb, 0xb9, 0x28, 0x5d, 0xcc, 0xbe, 0x2f,
    0xe0, 0x71, 0x03, 0x92, 0xe7, 0x76, 0x04, 0x95, 0xee, 0x7f, 0x0d, 0x9c, 0xe9, 0x78, 0x0a, 0x9b,
    0xfc, 0x6d, 0x1f, 0x8e, 0xfb, 0x6a, 0x18, 0x89, 0xf2, 0x63, 0x11, 0x80, 0xf5, 0x64, 0x16, 0x87,
    0xd8, 0x49, 0x3b, 0xaa, 0xdf, 0x4e, 0x3c, 0xad, 0xd6, 0x47, 0x35, 0xa4, 0xd1, 0x40, 0x32, 0xa3,
    0xc4, 0x55, 0x27, 0xb6, 0xc3, 0x52, 0x20, 0xb1, 0xca, 0x5b, 0x29, 0xb8, 0xcd, 0x5c, 0x2e, 0xbf,
    0x90, 0x01, 0x73, 0xe2, 0x97, 0x06, 0x74, 0xe5, 0x9e, 0x0f, 0x7d, 0xec, 0x99, 0x08, 0x7a, 0xeb,
    0x8c, 0x1d, 0x6f, 0xfe, 0x8b, 0x1a, 0x68, 0xf9, 0x82, 0x13, 0x61, 0xf0, 0x85, 0x14, 0x66, 0xf7,
    0xa8, 0x39, 0x4b, 0xda, 0xaf, 0x3e, 0x4c, 0xdd, 0xa6, 0x37, 0x45, 0xd4, 0xa1, 0x30, 0x42, 0xd3,
    0xb4, 0x25, 0x57, 0xc6, 0xb3, 0x22, 0x50, 0xc1, 0xba, 0x2b, 0x59, 0xc8, 0xbd, 0x2c, 0x5e, 0xcf,
)


def _crc(fields: bytes) -> int:
    """CRC-8 over ``fields`` with the TS 07.10 table (init 0xff)."""
    fcs = 0xFF
    for b in fields:
        fcs = _CRC[fcs ^ b]
    return fcs


def fcs(fields: bytes) -> int:
    """The FCS octet for the given covered fields (Address+Control[+Length])."""
    return 0xFF - _crc(fields)


def check_fcs(fields: bytes, fcs_byte: int) -> bool:
    """True if ``fcs_byte`` is the correct FCS for ``fields`` (kernel ``__check_fcs`` form)."""
    return _CRC[_crc(fields) ^ fcs_byte] == 0xCF


@dataclass(frozen=True)
class MuxCommand:
    """A multiplexer control-channel command carried in a UIH frame on DLCI 0."""

    type: str          # "PN" | "MSC" | "RPN" | ... | "UNKNOWN"
    command: bool      # True = command, False = response (the C/R bit of the type octet)
    value: bytes       # the command's value octets

    @property
    def is_response(self) -> bool:
        return not self.command


@dataclass(frozen=True)
class RfcommFrame:
    """One decoded RFCOMM frame."""

    dlci: int
    server_channel: int
    direction: int        # the DLCI direction bit
    cr: int               # the address-field C/R bit
    frame_type: str       # "SABM" | "UA" | "DM" | "DISC" | "UIH" | "UNKNOWN"
    poll_final: bool      # the control-field P/F bit
    length: int
    information: bytes
    credits: int | None   # credit-based flow-control octet, if present
    fcs: int
    fcs_ok: bool

    @property
    def is_mux_control(self) -> bool:
        """True if this is a multiplexer control frame (DLCI 0)."""
        return self.dlci == 0

    def mux_command(self) -> MuxCommand | None:
        """Decode the MUX command if this is a UIH frame on DLCI 0, else None."""
        if not (self.is_mux_control and self.frame_type == "UIH" and self.information):
            return None
        type_octet = self.information[0]
        name = _MUX_COMMANDS.get(type_octet & 0xFC, "UNKNOWN")
        command = bool((type_octet >> 1) & 0x01)
        # value follows an EA-terminated length octet (single-octet length in practice)
        value = self.information[2:] if len(self.information) >= 2 else b""
        return MuxCommand(name, command, value)


def parse_rfcomm(data: bytes, *, credit_aware: bool = True) -> RfcommFrame | None:
    """Decode a single RFCOMM frame, or ``None`` if the bytes aren't a well-formed frame.

    ``credit_aware``: treat a UIH-on-data-DLC frame with P/F set as carrying a leading credit octet
    (the convention once credit-based flow control is negotiated).
    """
    if len(data) < 4:  # address + control + length + fcs minimum
        return None
    addr, ctrl = data[0], data[1]
    dlci = addr >> 2
    frame_type = _FRAME_TYPES.get(ctrl & _TYPE_MASK, "UNKNOWN")
    poll_final = bool(ctrl & _PF)

    o = 2
    if data[o] & 0x01:  # EA = 1 -> single-octet length
        length = data[o] >> 1
        o += 1
    else:
        if len(data) < o + 2:
            return None
        length = (data[o] >> 1) | (data[o + 1] << 7)
        o += 2

    credits: int | None = None
    if credit_aware and frame_type == "UIH" and poll_final and dlci != 0:
        if o >= len(data):
            return None
        credits = data[o]
        o += 1

    if o + length >= len(data):  # need length bytes of info + 1 FCS octet
        return None
    information = data[o : o + length]
    fcs_byte = data[o + length]

    covered = data[0:2] if frame_type == "UIH" else data[0:3]
    return RfcommFrame(
        dlci=dlci,
        server_channel=dlci >> 1,
        direction=dlci & 0x01,
        cr=(addr >> 1) & 0x01,
        frame_type=frame_type,
        poll_final=poll_final,
        length=length,
        information=information,
        credits=credits,
        fcs=fcs_byte,
        fcs_ok=check_fcs(covered, fcs_byte),
    )


def iter_rfcomm(
    payloads: Iterable, *, require_valid_fcs: bool = True
) -> Iterator[RfcommFrame]:
    """Decode RFCOMM frames from L2CAP payloads (e.g. ``hci.l2cap_payloads(...)``).

    Because a btsnoop capture doesn't label which dynamic CID is RFCOMM, this tries to decode every
    payload and (by default) keeps only those with a valid FCS — a strong signal that the CID really
    carried RFCOMM. Pass ``require_valid_fcs=False`` to keep every parseable frame.

    Accepts any iterable of objects exposing a ``.payload`` (bytes) attribute, or raw ``bytes``.
    """
    for item in payloads:
        raw = getattr(item, "payload", item)
        if not isinstance(raw, (bytes, bytearray)):
            continue
        frame = parse_rfcomm(bytes(raw))
        if frame is None:
            continue
        if require_valid_fcs and not frame.fcs_ok:
            continue
        yield frame


def build_address(server_channel: int, *, direction: int, cr: int, ea: int = 1) -> int:
    """Build the RFCOMM address octet from a server channel + direction/C-R/EA bits (handy for tests)."""
    dlci = (server_channel << 1) | (direction & 0x01)
    return (dlci << 2) | ((cr & 0x01) << 1) | (ea & 0x01)


def build_frame(
    address: int, control: int, information: bytes = b"", *, credits: int | None = None
) -> bytes:
    """Build a well-formed RFCOMM frame (with correct length + FCS). Mirror of :func:`parse_rfcomm`."""
    if len(information) < 128:
        length = bytes([(len(information) << 1) | 0x01])
    else:
        length = bytes([(len(information) << 1) & 0xFF, len(information) >> 7])
    is_uih = (control & _TYPE_MASK) == 0xEF
    covered = bytes([address, control]) if is_uih else bytes([address, control]) + length[:1]
    body = bytes([address, control]) + length
    if credits is not None:
        body += bytes([credits & 0xFF])
    body += information
    return body + bytes([fcs(covered)])
