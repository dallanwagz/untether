"""Client for a Bluetooth-Classic SPP device reached over TCP.

Host BLE stacks (bleak, CoreBluetooth, WinRT, Web Bluetooth) can't speak Classic RFCOMM/SPP, so a
Classic device is normally unreachable from a modern host or from Home Assistant. The companion
``untether_spp`` ESP32 firmware bridges it: it RFCOMM-connects to the device and re-exposes the raw
byte stream as a TCP server. This module is the host-side client for that bridge — a clean framed
pipe to the device, in sync and asyncio flavours.

(The same client also works against any TCP→serial bridge, e.g. ``socat`` over ``/dev/rfcommN`` on
a Linux/BlueZ host.)
"""

from __future__ import annotations

import asyncio
import socket
import time

from .framing import DIVOOM_NEWMODE, Frame, Framing

DEFAULT_PORT = 8888


class SppBridge:
    """Synchronous TCP client to an ``untether_spp`` bridge (good for scripts and the CLI)."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        framing: Framing = DIVOOM_NEWMODE,
        connect_timeout: float = 6.0,
    ) -> None:
        self.host = host
        self.port = port
        self.framing = framing
        self._connect_timeout = connect_timeout
        self._sock: socket.socket | None = None
        self._leftover = b""

    def connect(self) -> SppBridge:
        self._sock = socket.create_connection((self.host, self.port), timeout=self._connect_timeout)
        self._sock.settimeout(0.3)
        self._leftover = b""
        return self

    def send(self, data: bytes) -> None:
        if self._sock is None:
            raise RuntimeError("not connected")
        self._sock.sendall(data)

    def send_frame(self, type_byte: int, payload: bytes = b"") -> None:
        """Build a frame with this bridge's framing and send it."""
        self.send(self.framing.build(type_byte, payload))

    def read_frames(self, window: float = 1.0) -> list[Frame]:
        """Read for up to ``window`` seconds and return the frames decoded in that time."""
        if self._sock is None:
            raise RuntimeError("not connected")
        out: list[Frame] = []
        end = time.monotonic() + window
        while time.monotonic() < end:
            try:
                chunk = self._sock.recv(4096)
            except (TimeoutError, socket.timeout):
                continue
            if not chunk:
                break
            frames, self._leftover = self.framing.iter_frames(self._leftover + chunk)
            out.extend(frames)
        return out

    def request(self, type_byte: int, payload: bytes = b"", window: float = 1.0) -> list[Frame]:
        """Send a frame, then collect reply frames for ``window`` seconds."""
        self.send_frame(type_byte, payload)
        return self.read_frames(window)

    def close(self) -> None:
        if self._sock is not None:
            try:
                self._sock.close()
            finally:
                self._sock = None

    def __enter__(self) -> SppBridge:
        return self.connect()

    def __exit__(self, *exc: object) -> None:
        self.close()


class AsyncSppBridge:
    """asyncio TCP client to an ``untether_spp`` bridge (for HA coordinators and async apps)."""

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        framing: Framing = DIVOOM_NEWMODE,
        connect_timeout: float = 6.0,
    ) -> None:
        self.host = host
        self.port = port
        self.framing = framing
        self._connect_timeout = connect_timeout
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._leftover = b""

    async def connect(self) -> AsyncSppBridge:
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self._connect_timeout
        )
        self._leftover = b""
        return self

    async def send(self, data: bytes) -> None:
        if self._writer is None:
            raise RuntimeError("not connected")
        self._writer.write(data)
        await self._writer.drain()

    async def send_frame(self, type_byte: int, payload: bytes = b"") -> None:
        await self.send(self.framing.build(type_byte, payload))

    async def read_frames(self, window: float = 1.0) -> list[Frame]:
        if self._reader is None:
            raise RuntimeError("not connected")
        out: list[Frame] = []
        loop = asyncio.get_running_loop()
        end = loop.time() + window
        while loop.time() < end:
            try:
                chunk = await asyncio.wait_for(self._reader.read(4096), timeout=end - loop.time())
            except asyncio.TimeoutError:
                break
            if not chunk:
                break
            frames, self._leftover = self.framing.iter_frames(self._leftover + chunk)
            out.extend(frames)
        return out

    async def request(
        self, type_byte: int, payload: bytes = b"", window: float = 1.0
    ) -> list[Frame]:
        await self.send_frame(type_byte, payload)
        return await self.read_frames(window)

    async def aclose(self) -> None:
        if self._writer is not None:
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except OSError:
                pass
            finally:
                self._writer = None
                self._reader = None

    async def __aenter__(self) -> AsyncSppBridge:
        return await self.connect()

    async def __aexit__(self, *exc: object) -> None:
        await self.aclose()
