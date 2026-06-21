"""GATT client tests — pure UUID normalization + a fake bleak backend."""

import pytest

from untether_bt import GattClient, normalize_uuid

BASE = "-0000-1000-8000-00805f9b34fb"


def test_normalize_uuid():
    assert normalize_uuid(0xFFE1) == "0000ffe1" + BASE
    assert normalize_uuid("FFE1") == "0000ffe1" + BASE
    assert normalize_uuid("0000ffe1" + BASE) == "0000ffe1" + BASE
    assert normalize_uuid("12345678-1234-1234-1234-123456789abc") == "12345678-1234-1234-1234-123456789abc"


# --- fake bleak-compatible backend ---
class _Char:
    def __init__(self, uuid):
        self.uuid = uuid


class _Svc:
    def __init__(self, uuid, chars):
        self.uuid = uuid
        self.characteristics = [_Char(c) for c in chars]


class FakeBleak:
    def __init__(self):
        self.services = [_Svc("0000180f" + BASE, ["00002a19" + BASE])]
        self.connected = False
        self.reads = {"00002a19" + BASE: b"\x55"}
        self.writes: list[tuple[str, bytes, bool]] = []
        self.notifies: dict[str, object] = {}

    async def connect(self):
        self.connected = True

    async def disconnect(self):
        self.connected = False

    async def read_gatt_char(self, uuid):
        return self.reads[uuid]

    async def write_gatt_char(self, uuid, data, response=True):
        self.writes.append((uuid, data, response))

    async def start_notify(self, uuid, cb):
        self.notifies[uuid] = cb


async def test_gatt_client_flow():
    fake = FakeBleak()
    async with GattClient.from_client(fake) as g:
        assert fake.connected
        assert g.services() == {"0000180f" + BASE: ["00002a19" + BASE]}
        assert await g.read(0x2A19) == b"\x55"            # 16-bit int normalized to the char UUID
        await g.write(0xFFE1, b"\x74\x32", response=False)
        assert fake.writes == [("0000ffe1" + BASE, b"\x74\x32", False)]
        got = []
        await g.subscribe(0x2A19, got.append)
        fake.notifies["00002a19" + BASE](0, bytearray(b"\xab"))   # simulate a notification
        assert got == [b"\xab"]
    assert not fake.connected


def test_connect_imports_bleak_when_no_backend():
    import asyncio
    import importlib.util

    if importlib.util.find_spec("bleak") is not None:
        pytest.skip("bleak installed; skipping the import-failure path")
    g = GattClient("AA:BB:CC:DD:EE:FF")
    with pytest.raises((ImportError, ModuleNotFoundError)):
        asyncio.run(g.connect())
