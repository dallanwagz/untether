"""Length-prefixed serial framing — the codec engine behind many Bluetooth-serial protocols.

Lots of Classic-SPP gadgets (and SPP-like BLE services) wrap their payloads in a frame like::

    SOI | LEN16(LE) | <type> <args...> | CRC16(LE) | EOI

…sometimes with byte-stuffing so the SOI/EOI markers can't appear inside the body. This module
captures that whole family as one configurable :class:`Framing`, with the two battle-tested Divoom
presets (NewMode = no stuffing; TimeBox-mini = byte-stuffed) ready to use.

The inbound parser (:meth:`Framing.iter_frames`) is hardened: for unstuffed framings (where a body
byte can collide with SOI/EOI) it validates length bounds + the trailing EOI + the CRC and resyncs
past a stray SOI, so noise or a mid-stream marker can't desync it.
"""

from __future__ import annotations

from collections.abc import Callable
from dataclasses import dataclass


def crc_sum16(data: bytes) -> int:
    """The Divoom checksum: 16-bit little-endian sum of the LEN bytes + body."""
    return sum(data) & 0xFFFF


@dataclass(frozen=True)
class Stuffing:
    """Byte-stuffing codec: each target byte becomes ``escape, byte+offset``.

    The Divoom TimeBox-mini uses ``0x01->03 04, 0x02->03 05, 0x03->03 06`` (escape 0x03, offset 3),
    so the 0x01/0x02 frame markers never occur inside the encoded body.
    """

    escape: int = 0x03
    targets: tuple[int, ...] = (0x01, 0x02, 0x03)
    offset: int = 0x03

    def encode(self, data: bytes) -> bytes:
        out = bytearray()
        for b in data:
            if b in self.targets:
                out += bytes((self.escape, b + self.offset))
            else:
                out.append(b)
        return bytes(out)

    def decode(self, data: bytes) -> bytes:
        out = bytearray()
        i = 0
        n = len(data)
        while i < n:
            if data[i] == self.escape and i + 1 < n:
                out.append((data[i + 1] - self.offset) & 0xFF)
                i += 2
            else:
                out.append(data[i])
                i += 1
        return bytes(out)


@dataclass(frozen=True)
class Frame:
    """A decoded frame: the first body byte is the ``type``, the rest is ``args``."""

    type: int
    args: bytes

    @property
    def body(self) -> bytes:
        return bytes((self.type,)) + self.args

    def hex(self) -> str:
        return self.body.hex()


@dataclass(frozen=True)
class Framing:
    """A configurable ``SOI | LEN | body | CRC | EOI`` framing.

    Defaults match the Divoom NewMode envelope (Pixoo/MiniToo): 1-byte SOI/EOI, 2-byte LE length
    that counts the CRC, a 2-byte LE summed CRC, no byte-stuffing.
    """

    soi: int = 0x01
    eoi: int = 0x02
    len_bytes: int = 2
    crc_bytes: int = 2
    len_counts_crc: bool = True
    crc: Callable[[bytes], int] = crc_sum16
    stuffing: Stuffing | None = None
    max_frame: int = 4096  # reject implausibly large LEN so a stray SOI can't stall the parser

    # ---- build -------------------------------------------------------------
    def build(self, type_byte: int, payload: bytes = b"") -> bytes:
        """Encode one frame for ``type_byte`` + ``payload``."""
        body = bytes((type_byte,)) + bytes(payload)
        ln = len(body) + (self.crc_bytes if self.len_counts_crc else 0)
        len_field = ln.to_bytes(self.len_bytes, "little")
        crcd = len_field + body
        crc = self.crc(crcd).to_bytes(self.crc_bytes, "little")
        inner = crcd + crc
        if self.stuffing is not None:
            inner = self.stuffing.encode(inner)
        return bytes((self.soi,)) + inner + bytes((self.eoi,))

    # ---- parse -------------------------------------------------------------
    def iter_frames(self, buf: bytes) -> tuple[list[Frame], bytes]:
        """Split a byte buffer into complete frames; return ``(frames, leftover)``.

        ``leftover`` is the trailing partial frame to prepend to the next read.
        """
        if self.stuffing is not None:
            return self._iter_stuffed(buf)
        return self._iter_unstuffed(buf)

    def _decode_inner(self, inner: bytes) -> Frame | None:
        """Validate LEN+body+CRC of an (already unstuffed) inner region -> Frame or None."""
        min_len = self.len_bytes + 1 + self.crc_bytes
        if len(inner) < min_len:
            return None
        ln = int.from_bytes(inner[: self.len_bytes], "little")
        body_len = ln - (self.crc_bytes if self.len_counts_crc else 0)
        if body_len < 1:
            return None
        body_start = self.len_bytes
        crc_start = body_start + body_len
        if crc_start + self.crc_bytes != len(inner):
            return None
        body = inner[body_start:crc_start]
        crc_stored = int.from_bytes(inner[crc_start:], "little")
        if crc_stored != self.crc(inner[:crc_start]):
            return None
        return Frame(body[0], body[1:])

    def _iter_unstuffed(self, buf: bytes) -> tuple[list[Frame], bytes]:
        frames: list[Frame] = []
        i, n = 0, len(buf)
        hdr = 1 + self.len_bytes
        while i < n:
            if buf[i] != self.soi:
                i += 1
                continue
            if i + hdr > n:
                break  # need the LEN field
            ln = int.from_bytes(buf[i + 1 : i + 1 + self.len_bytes], "little")
            if ln < 1 + self.crc_bytes or ln > self.max_frame:
                i += 1  # implausible -> stray SOI, resync
                continue
            body_len = ln - (self.crc_bytes if self.len_counts_crc else 0)
            end = i + 1 + self.len_bytes + body_len + self.crc_bytes  # index of EOI
            if end >= n:
                break  # incomplete
            if buf[end] != self.eoi:
                i += 1  # not a real boundary -> resync
                continue
            inner = buf[i + 1 : end]
            frame = self._decode_inner(inner)
            if frame is None:
                i += 1  # bad CRC/shape -> resync
                continue
            frames.append(frame)
            i = end + 1
        return frames, buf[i:]

    def _iter_stuffed(self, buf: bytes) -> tuple[list[Frame], bytes]:
        # Stuffing guarantees SOI/EOI never occur inside the encoded body, so framing is
        # unambiguous: each frame is the bytes between an SOI and the next EOI.
        assert self.stuffing is not None
        frames: list[Frame] = []
        i, n = 0, len(buf)
        while i < n:
            if buf[i] != self.soi:
                i += 1
                continue
            j = buf.find(self.eoi, i + 1)
            if j == -1:
                break  # incomplete
            frame = self._decode_inner(self.stuffing.decode(buf[i + 1 : j]))
            if frame is not None:
                frames.append(frame)
            i = j + 1
        return frames, buf[i:]


# Battle-tested presets.
DIVOOM_NEWMODE = Framing()                       # Pixoo / MiniToo (no byte-stuffing)
DIVOOM_STUFFED = Framing(stuffing=Stuffing())    # TimeBox-mini (byte-stuffed)
