"""Frida dynamic instrumentation — dump an app's outgoing Bluetooth writes live.

Hooks the Android Bluetooth APIs (``BluetoothGattCharacteristic.setValue`` / ``writeCharacteristic``
for BLE, ``OutputStream.write`` on Bluetooth sockets for Classic RFCOMM/SPP) at the **API layer** —
so it captures plaintext command bytes even on an encrypted link, and works for *both* transports
(Frida app-hooking is the most robust path for Classic, where OTA sniffing barely exists).

The hook script (``frida_hooks/android_bt.js``) ``send()``s each write to the host; this module
turns those messages into :class:`~untether_bt.capture.WireEvent`s — the same objects
:func:`~untether_bt.capture.correlate` consumes, so dynamic captures feed the same pipeline.

``parse_hook_message`` is pure/tested; :class:`FridaSession` is a thin wrapper over the optional
``frida`` package (``pip install untether-bt[frida]``) and a rooted/Frida-served device.
"""

from __future__ import annotations

from collections.abc import Callable
from importlib import resources
from pathlib import Path

from .capture import WireEvent


def hook_script_path() -> Path:
    """Filesystem path to the bundled Android hook script."""
    return Path(str(resources.files("untether_bt").joinpath("frida_hooks/android_bt.js")))


def parse_hook_message(message: dict, data: bytes | None = None) -> WireEvent | None:
    """Turn a Frida ``send()`` message into a :class:`WireEvent` (or None for non-write messages)."""
    if not isinstance(message, dict) or message.get("type") != "send":
        return None
    p = message.get("payload")
    if not isinstance(p, dict):
        return None
    t = p.get("t")
    ts_us = int(p.get("ts", 0)) * 1000  # JS Date.now() is ms
    try:
        payload = bytes.fromhex(p.get("hex", ""))
    except ValueError:
        return None
    if t in ("ble_write", "ble_set"):
        uuid = p.get("uuid", "")
        return WireEvent(ts_us, sent=True, transport="att", summary=f"{t} {uuid}", data=payload)
    if t == "rfcomm_write":
        return WireEvent(ts_us, sent=True, transport="rfcomm", summary="rfcomm_write", data=payload)
    return None  # 'ready' / 'err' / unknown


class FridaSession:
    """Attach Frida to an app and stream its outgoing BT writes as WireEvents.

    Needs the ``frida`` package and a Frida-served device (USB, rooted/jailbroken or a repackaged
    app). Example::

        events = []
        FridaSession("com.vendor.app").run(events.append, duration=20)
        # later: correlate(events, recorder.marks)
    """

    def __init__(self, package: str, *, serial: str | None = None, script_path: str | Path | None = None):
        self.package = package
        self.serial = serial
        self.script_path = Path(script_path) if script_path else hook_script_path()

    def run(
        self,
        on_event: Callable[[WireEvent], None],
        *,
        spawn: bool = True,
        duration: float | None = None,
    ) -> None:
        import time

        import frida  # optional dependency

        device = frida.get_device(self.serial) if self.serial else frida.get_usb_device()
        pid = device.spawn([self.package]) if spawn else None
        session = device.attach(pid if pid is not None else self.package)

        def _on_message(message: dict, data: bytes | None) -> None:
            event = parse_hook_message(message, data)
            if event is not None:
                on_event(event)

        script = session.create_script(self.script_path.read_text("utf-8"))
        script.on("message", _on_message)
        script.load()
        if pid is not None:
            device.resume(pid)
        try:
            if duration is None:
                while True:  # until interrupted
                    time.sleep(0.5)
            else:
                time.sleep(duration)
        finally:
            try:
                session.detach()
            except Exception:
                pass
