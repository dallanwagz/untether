"""A self-healing persistent connection to an SPP-over-TCP bridge.

:class:`SppBridge`/:class:`AsyncSppBridge` are request/response clients — open, send, read for a
window, close. A long-running host (a Home Assistant coordinator, a daemon, a dashboard) needs the
opposite: **one connection that stays up and heals itself**. That's the loop every such integration
re-implements by hand — connect, run a startup handshake, read forever in the background, serialise
writes, reconnect with capped backoff, and tear down when inbound bytes go quiet.

:class:`SppConnection` is that loop, factored out and pure-asyncio (no Home Assistant, no framing
opinions). You give it callbacks; it gives you a connection that survives the device rebooting, the
bridge dropping TCP, or the link silently wedging:

* ``on_connect``  — awaited right after TCP is up (send your handshake / reset deframer state here)
* ``on_chunk``    — every inbound byte chunk (you deframe — this stays transport-, not protocol-aware)
* ``on_state``    — ``True`` when connected, ``False`` when dropped (drive availability from this)

Writes go through :meth:`send` (serialised behind a lock). For a multi-frame burst that must not be
interleaved (a chunked upload), hold :attr:`write_lock` yourself and call :meth:`send_raw`.
"""

from __future__ import annotations

import asyncio
import logging
from collections.abc import Awaitable, Callable

DEFAULT_PORT = 8888


class SppConnection:
    """A persistent, auto-reconnecting TCP connection to an ``untether_spp`` bridge.

    Pure asyncio: usable from any async host. The reader runs as a background task started by
    :meth:`start` and stopped by :meth:`stop`.
    """

    def __init__(
        self,
        host: str,
        port: int = DEFAULT_PORT,
        *,
        on_chunk: Callable[[bytes], None] | None = None,
        on_connect: Callable[[], Awaitable[None]] | None = None,
        on_state: Callable[[bool], None] | None = None,
        connect_timeout: float = 10.0,
        reconnect_min: float = 1.0,
        reconnect_max: float = 30.0,
        stale_after: float = 90.0,
        read_size: int = 512,
        logger: logging.Logger | None = None,
    ) -> None:
        self.host = host
        self.port = port
        self._on_chunk = on_chunk
        self._on_connect = on_connect
        self._on_state = on_state
        self._connect_timeout = connect_timeout
        self._reconnect_min = reconnect_min
        self._reconnect_max = reconnect_max
        self._stale_after = stale_after
        self._read_size = read_size
        self._log = logger or logging.getLogger(__name__)

        self.write_lock = asyncio.Lock()
        self._reader: asyncio.StreamReader | None = None
        self._writer: asyncio.StreamWriter | None = None
        self._task: asyncio.Task | None = None
        self._connected = False

    @property
    def connected(self) -> bool:
        return self._connected

    async def start(self) -> None:
        """Start the background connect/read loop (idempotent)."""
        if self._task is None or self._task.done():
            self._task = asyncio.ensure_future(self._run())

    async def stop(self) -> None:
        """Cancel the loop and close the connection."""
        task, self._task = self._task, None
        if task:
            task.cancel()
            try:
                await task
            except (asyncio.CancelledError, Exception):  # noqa: BLE001 - shutdown best-effort
                pass
        await self._close()

    async def send(self, data: bytes) -> None:
        """Serialise a single write to the device. Raises ``OSError`` if not connected."""
        async with self.write_lock:
            await self.send_raw(data)

    async def send_raw(self, data: bytes) -> None:
        """Write without taking the lock — only call while holding :attr:`write_lock`."""
        if self._writer is None:
            raise OSError("not connected")
        self._writer.write(data)
        await self._writer.drain()

    def _set_connected(self, value: bool) -> None:
        if value != self._connected:
            self._connected = value
            if self._on_state is not None:
                self._on_state(value)

    async def _close(self) -> None:
        self._set_connected(False)
        writer, self._writer, self._reader = self._writer, None, None
        if writer:
            writer.close()
            try:
                await writer.wait_closed()
            except (OSError, asyncio.CancelledError):
                pass

    async def _run(self) -> None:
        backoff = self._reconnect_min
        while True:
            try:
                await self._connect_once()
                backoff = self._reconnect_min
                await self._read_loop()
            except asyncio.CancelledError:
                raise
            except (OSError, asyncio.TimeoutError) as err:
                self._log.debug("SPP bridge %s:%s: %s", self.host, self.port, err)
            finally:
                await self._close()
            await asyncio.sleep(backoff)
            backoff = min(backoff * 2, self._reconnect_max)

    async def _connect_once(self) -> None:
        self._log.debug("Connecting to SPP bridge %s:%s", self.host, self.port)
        self._reader, self._writer = await asyncio.wait_for(
            asyncio.open_connection(self.host, self.port), timeout=self._connect_timeout
        )
        if self._on_connect is not None:
            await self._on_connect()
        self._set_connected(True)
        self._log.info("SPP bridge %s:%s connected", self.host, self.port)

    async def _read_loop(self) -> None:
        assert self._reader is not None
        while True:
            try:
                chunk = await asyncio.wait_for(
                    self._reader.read(self._read_size), timeout=self._stale_after
                )
            except asyncio.TimeoutError as err:
                raise OSError("stale: no inbound data") from err
            if not chunk:
                raise OSError("connection closed by peer")
            if self._on_chunk is not None:
                self._on_chunk(chunk)
