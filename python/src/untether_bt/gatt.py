"""GATT client — a thin, ergonomic wrapper over ``bleak`` (we never rebuild BLE transport).

Handles the ergonomics that trip people up: normalizing 16-bit ↔ 128-bit UUIDs, discovering the
service/characteristic tree, and — the #1 gotcha — that to receive notifications you subscribe via
the characteristic (bleak writes the CCCD for you). ``bleak`` is an optional dependency
(``pip install untether-bt[ble]``); the UUID/normalization logic is pure and unit-tested, and the
client accepts an injected backend so its behaviour is testable without a radio.
"""

from __future__ import annotations

from collections.abc import Callable

from .numbers import uuid16_to_128


def normalize_uuid(uuid: int | str) -> str:
    """Normalize a UUID to canonical lowercase 128-bit form (16-bit int or short string → base UUID)."""
    if isinstance(uuid, int):
        return uuid16_to_128(uuid)
    u = uuid.lower().replace("{", "").replace("}", "")
    if len(u) == 4:        # "ffe1"
        return uuid16_to_128(int(u, 16))
    if len(u) == 8:        # 32-bit
        return f"{u}-0000-1000-8000-00805f9b34fb"
    return u


class GattClient:
    """Connect to a BLE device and read/write/subscribe its GATT characteristics."""

    def __init__(self, address: str, *, timeout: float = 10.0, backend: object | None = None):
        self.address = address
        self._timeout = timeout
        self._client = backend  # a bleak.BleakClient-compatible object, or None until connect()

    @classmethod
    def from_client(cls, client: object, address: str = "") -> GattClient:
        """Wrap an already-constructed (or fake) bleak-compatible client."""
        return cls(address, backend=client)

    async def connect(self) -> GattClient:
        if self._client is None:
            import bleak  # optional dependency

            self._client = bleak.BleakClient(self.address, timeout=self._timeout)
        await self._client.connect()
        return self

    def services(self) -> dict[str, list[str]]:
        """Map service UUID → list of characteristic UUIDs (after connect/discovery)."""
        out: dict[str, list[str]] = {}
        for svc in self._client.services:  # type: ignore[union-attr]
            out[str(svc.uuid)] = [str(c.uuid) for c in svc.characteristics]
        return out

    async def read(self, char: int | str) -> bytes:
        return bytes(await self._client.read_gatt_char(normalize_uuid(char)))  # type: ignore[union-attr]

    async def write(self, char: int | str, data: bytes, *, response: bool = True) -> None:
        await self._client.write_gatt_char(normalize_uuid(char), data, response=response)  # type: ignore[union-attr]

    async def subscribe(self, char: int | str, callback: Callable[[bytes], None]) -> None:
        """Subscribe to notifications/indications (bleak writes the CCCD for you)."""
        await self._client.start_notify(  # type: ignore[union-attr]
            normalize_uuid(char), lambda _handle, data: callback(bytes(data))
        )

    async def unsubscribe(self, char: int | str) -> None:
        await self._client.stop_notify(normalize_uuid(char))  # type: ignore[union-attr]

    async def disconnect(self) -> None:
        if self._client is not None:
            await self._client.disconnect()

    async def __aenter__(self) -> GattClient:
        return await self.connect()

    async def __aexit__(self, *exc: object) -> None:
        await self.disconnect()
