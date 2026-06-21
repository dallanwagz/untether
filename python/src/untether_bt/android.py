"""Drive an Android device over ADB to reverse-engineer its Bluetooth app.

The live half of the RE loop: enable HCI snoop, drive the vendor app by accessibility label while
**marking** each UI action, then pull the capture and (with :func:`untether_bt.capture.correlate`)
see exactly which wire bytes each action produced.

The driver runs adb through an injectable runner, so the pure logic is fully unit-tested and the
real device path is a thin shell. Capture is pulled via ``adb bugreport`` (works unrooted) or a
direct path (rooted).
"""

from __future__ import annotations

import glob
import os
import tempfile
import zipfile
from typing import Protocol

from .capture import Recorder
from .uiauto import UiNode, find_node, parse_ui_dump

_UI_REMOTE = "/sdcard/untether_ui.xml"
_DEFAULT_SNOOP_PATH = "/data/misc/bluetooth/logs/btsnoop_hci.log"


class AdbError(RuntimeError):
    pass


class Runner(Protocol):
    def run(self, *args: str) -> str: ...
    def run_bytes(self, *args: str) -> bytes: ...
    def shell(self, *args: str) -> str: ...


class AdbRunner:
    """Default runner: shells out to the ``adb`` binary (optionally targeting a serial)."""

    def __init__(self, serial: str | None = None, adb_path: str = "adb", timeout: float = 90.0):
        self._base = [adb_path] + (["-s", serial] if serial else [])
        self._timeout = timeout

    def _exec(self, args: tuple[str, ...], *, text: bool):
        import subprocess

        p = subprocess.run(  # noqa: S603
            [*self._base, *args], capture_output=True, timeout=self._timeout
        )
        if p.returncode != 0:
            raise AdbError(f"adb {' '.join(args)} failed: {p.stderr.decode('utf-8', 'replace')[:300]}")
        return p.stdout.decode("utf-8", "replace") if text else p.stdout

    def run(self, *args: str) -> str:
        return self._exec(args, text=True)

    def run_bytes(self, *args: str) -> bytes:
        return self._exec(args, text=False)

    def shell(self, *args: str) -> str:
        return self.run("shell", *args)


def extract_btsnoop_from_zip(zip_path: str) -> bytes:
    """Pull the btsnoop_hci.log out of an ``adb bugreport`` zip."""
    with zipfile.ZipFile(zip_path) as z:
        names = z.namelist()
        cands = [n for n in names if "btsnoop" in n.lower()]
        if not cands:
            raise AdbError("no btsnoop log found in bugreport zip")
        # prefer the real uncompressed btsnoop_hci.log, then largest
        cands.sort(key=lambda n: (not n.endswith("btsnoop_hci.log"), -z.getinfo(n).file_size))
        return z.read(cands[0])


class AndroidDriver:
    """High-level ADB driver for app-driven Bluetooth reverse engineering."""

    def __init__(self, serial: str | None = None, runner: Runner | None = None):
        self.adb: Runner = runner if runner is not None else AdbRunner(serial)

    # ---- device ----
    def devices(self) -> list[str]:
        out = self.adb.run("devices")
        return [
            line.split("\t", 1)[0]
            for line in out.splitlines()[1:]
            if "\tdevice" in line
        ]

    def launch(self, package: str) -> None:
        self.adb.shell("monkey", "-p", package, "-c", "android.intent.category.LAUNCHER", "1")

    # ---- UI (accessibility-hierarchy driven) ----
    def dump_ui(self) -> list[UiNode]:
        self.adb.shell("uiautomator", "dump", _UI_REMOTE)
        raw = self.adb.run_bytes("exec-out", "cat", _UI_REMOTE)
        return parse_ui_dump(raw.decode("utf-8", "replace"))

    def tap_xy(self, x: int, y: int) -> None:
        self.adb.shell("input", "tap", str(x), str(y))

    def tap(self, label: str, *, fields: tuple[str, ...] = ("text", "desc", "resource_id")) -> UiNode:
        """Find a node by accessibility label and tap its center. Raises if not found."""
        node = find_node(self.dump_ui(), label, fields=fields)
        if node is None or node.center is None:
            raise AdbError(f"no tappable node matching {label!r}")
        self.tap_xy(*node.center)
        return node

    def text(self, value: str) -> None:
        self.adb.shell("input", "text", value.replace(" ", "%s"))

    def key(self, code: int) -> None:
        self.adb.shell("input", "keyevent", str(code))

    def back(self) -> None:
        self.key(4)

    def home(self) -> None:
        self.key(3)

    def swipe(self, x1: int, y1: int, x2: int, y2: int, ms: int = 300) -> None:
        self.adb.shell("input", "swipe", str(x1), str(y1), str(x2), str(y2), str(ms))

    # ---- HCI snoop capture ----
    def enable_hci_snoop(self, *, restart_bt: bool = True) -> None:
        """Turn on Bluetooth HCI snoop logging.

        Note: on many builds the durable switch is the Developer Options toggle
        ("Enable Bluetooth HCI snoop log"); this sets the setting and (by default) restarts the
        Bluetooth stack so it takes effect. If captures come back empty, flip the toggle by hand.
        """
        self.adb.shell("settings", "put", "global", "bluetooth_hci_log", "1")
        if restart_bt:
            self.adb.shell("svc", "bluetooth", "disable")
            self.adb.shell("svc", "bluetooth", "enable")

    def pull_btsnoop(self) -> bytes:
        """Pull the current capture via ``adb bugreport`` (works unrooted). Returns btsnoop bytes."""
        with tempfile.TemporaryDirectory() as d:
            self.adb.run("bugreport", d)
            zips = glob.glob(os.path.join(d, "*.zip"))
            if not zips:
                raise AdbError("adb bugreport produced no zip")
            zips.sort(key=os.path.getmtime, reverse=True)
            return extract_btsnoop_from_zip(zips[0])

    def pull_btsnoop_path(self, path: str = _DEFAULT_SNOOP_PATH, *, su: bool = False) -> bytes:
        """Pull the capture directly from its path (rooted devices)."""
        args = ("exec-out", "su", "0", "cat", path) if su else ("exec-out", "cat", path)
        return self.adb.run_bytes(*args)

    # ---- the harness helper ----
    def tap_and_mark(self, label: str, recorder: Recorder, **kw: object) -> UiNode:
        """Tap a labelled node and timestamp the action into ``recorder`` for later correlation."""
        node = self.tap(label, **kw)  # type: ignore[arg-type]
        recorder.mark(label)
        return node
