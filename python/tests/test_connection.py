"""SppConnection — self-healing persistent transport tests (fake in-memory streams)."""

import asyncio

import pytest

from untether_bt import SppConnection
from untether_bt import connection as conn_mod


class FakeWriter:
    def __init__(self) -> None:
        self.written = bytearray()
        self.closed = False

    def write(self, data: bytes) -> None:
        self.written += data

    async def drain(self) -> None:
        return None

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        return None


class FakeReader:
    """Yields queued chunks, then blocks (a quiet, still-open link)."""

    def __init__(self, chunks: list[bytes]) -> None:
        self._chunks = list(chunks)
        self._idle = asyncio.Event()

    async def read(self, _n: int) -> bytes:
        if self._chunks:
            return self._chunks.pop(0)
        await self._idle.wait()  # stay open but silent
        return b""


def _patch_open(monkeypatch, reader, writer, record=None):
    async def _open(host, port):  # noqa: ANN001
        if record is not None:
            record.append((host, port))
        return reader, writer

    monkeypatch.setattr(conn_mod.asyncio, "open_connection", _open)


async def _wait_until(pred, timeout=1.0):
    loop = asyncio.get_running_loop()
    end = loop.time() + timeout
    while loop.time() < end:
        if pred():
            return True
        await asyncio.sleep(0.005)
    return False


async def test_connect_handshake_and_chunks(monkeypatch):
    reader = FakeReader([b"\x01\x02", b"\x03"])
    writer = FakeWriter()
    _patch_open(monkeypatch, reader, writer)

    got = bytearray()
    states: list[bool] = []
    handshakes = 0

    async def on_connect():
        nonlocal handshakes
        handshakes += 1

    c = SppConnection(
        "h", 9999,
        on_chunk=got.extend,
        on_connect=on_connect,
        on_state=states.append,
    )
    await c.start()
    assert await _wait_until(lambda: bytes(got) == b"\x01\x02\x03")
    assert await _wait_until(lambda: c.connected)
    assert handshakes == 1
    assert states[0] is True

    await c.send(b"\xaa\xbb")
    assert writer.written == b"\xaa\xbb"

    await c.stop()
    assert states[-1] is False  # stop drives the disconnected callback
    assert writer.closed


async def test_send_before_connect_raises(monkeypatch):
    reader = FakeReader([])
    writer = FakeWriter()
    _patch_open(monkeypatch, reader, writer)
    c = SppConnection("h", 1)
    with pytest.raises(OSError):
        await c.send(b"x")  # never started -> no writer


async def test_reconnect_with_backoff(monkeypatch):
    """First connect attempt fails; the loop retries and succeeds."""
    attempts = []
    writer = FakeWriter()
    reader = FakeReader([])

    async def _open(host, port):  # noqa: ANN001
        attempts.append((host, port))
        if len(attempts) == 1:
            raise OSError("refused")
        return reader, writer

    monkeypatch.setattr(conn_mod.asyncio, "open_connection", _open)

    c = SppConnection("h", 7, reconnect_min=0.01, reconnect_max=0.02)
    await c.start()
    assert await _wait_until(lambda: c.connected, timeout=2.0)
    assert len(attempts) >= 2
    await c.stop()


async def test_stale_link_tears_down(monkeypatch):
    """A connected-but-silent link past stale_after is torn down and retried."""
    opens = []

    def fresh():
        return FakeReader([]), FakeWriter()

    streams = [fresh(), fresh()]

    async def _open(host, port):  # noqa: ANN001
        opens.append((host, port))
        return streams[min(len(opens) - 1, len(streams) - 1)]

    monkeypatch.setattr(conn_mod.asyncio, "open_connection", _open)

    c = SppConnection("h", 3, stale_after=0.05, reconnect_min=0.01, reconnect_max=0.02)
    await c.start()
    # first connection goes stale (no bytes) -> a second open happens
    assert await _wait_until(lambda: len(opens) >= 2, timeout=2.0)
    await c.stop()


async def test_write_lock_batches_with_send_raw(monkeypatch):
    reader = FakeReader([])
    writer = FakeWriter()
    _patch_open(monkeypatch, reader, writer)
    c = SppConnection("h", 5)
    await c.start()
    assert await _wait_until(lambda: c.connected)
    async with c.write_lock:
        await c.send_raw(b"\x01")
        await c.send_raw(b"\x02")
    assert writer.written == b"\x01\x02"
    await c.stop()
