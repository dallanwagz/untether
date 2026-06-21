"""SPP bridge client tests — against real localhost TCP servers (sync + async)."""

import asyncio
import socketserver
import threading

from untether_bt import AsyncSppBridge, DIVOOM_NEWMODE, SppBridge

# a brightness-echo-shaped reply frame the device would send back
REPLY = DIVOOM_NEWMODE.build(0x46, b"\x00\x00\x00\xff\x50\x00\x32\x00")


async def test_async_bridge_round_trip():
    received: list[bytes] = []

    async def handle(reader, writer):
        data = await reader.read(100)
        received.append(data)
        writer.write(REPLY)
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        async with AsyncSppBridge("127.0.0.1", port) as bridge:
            await bridge.send_frame(0x74, b"\x32")
            await asyncio.sleep(0.1)
            frames = await bridge.read_frames(0.5)

    assert received and received[0] == DIVOOM_NEWMODE.build(0x74, b"\x32")
    assert [f.type for f in frames] == [0x46]


async def test_async_bridge_request_helper():
    async def handle(reader, writer):
        await reader.read(100)
        writer.write(REPLY)
        await writer.drain()
        await asyncio.sleep(0.05)
        writer.close()

    server = await asyncio.start_server(handle, "127.0.0.1", 0)
    port = server.sockets[0].getsockname()[1]
    async with server:
        async with AsyncSppBridge("127.0.0.1", port) as bridge:
            frames = await bridge.request(0x74, b"\x32", window=0.5)
    assert any(f.type == 0x46 for f in frames)


def test_sync_bridge_round_trip():
    received: list[bytes] = []

    class Handler(socketserver.BaseRequestHandler):
        def handle(self):
            received.append(self.request.recv(100))
            self.request.sendall(REPLY)

    srv = socketserver.TCPServer(("127.0.0.1", 0), Handler)
    srv.allow_reuse_address = True
    port = srv.server_address[1]
    t = threading.Thread(target=srv.handle_request, daemon=True)
    t.start()
    try:
        with SppBridge("127.0.0.1", port) as b:
            b.send_frame(0x74, b"\x32")
            frames = b.read_frames(0.5)
    finally:
        t.join(timeout=2)
        srv.server_close()

    assert received and received[0] == DIVOOM_NEWMODE.build(0x74, b"\x32")
    assert any(f.type == 0x46 for f in frames)


def test_send_frame_uses_framing():
    # the bridge builds with its configured framing — verify without a network
    bridge = SppBridge("x", framing=DIVOOM_NEWMODE)
    assert bridge.framing.build(0x74, b"\x32").hex() == "0104007432aa0002"
