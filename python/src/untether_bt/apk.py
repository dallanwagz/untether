"""Static analysis of a vendor app — decompile with jadx, then map the Bluetooth surface.

This is Phase-0/1 of the methodology automated: get the APK (off a connected device or a local
file), decompile it, and answer the questions that steer everything downstream — **is this app BLE
GATT or Bluetooth Classic SPP?**, which **UUIDs**/characteristics does it touch, and **where** are
the command-building / write call sites.

``analyze_tree`` is pure (point it at any decompiled source tree); ``decompile_apk`` / ``pull_apk``
are thin wrappers around ``jadx`` and ``adb``.
"""

from __future__ import annotations

import re
from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path

from .android import AdbRunner, Runner

# --- signal patterns ---
_UUID128 = re.compile(
    r"\b[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}\b"
)
_SPP_UUID = re.compile(r"0000110[0-9a-fA-F]-0000-1000-8000-00805f9b34fb", re.IGNORECASE)

# kind -> regex. Order matters only for readability; every line is checked against all.
_SIGNALS: dict[str, re.Pattern[str]] = {
    "ble_write": re.compile(r"writeCharacteristic|writeDescriptor|\.setValue\("),
    "ble_notify": re.compile(r"setCharacteristicNotification|onCharacteristicChanged"),
    "ble_gatt": re.compile(r"BluetoothGatt|connectGatt|BluetoothLeScanner|BluetoothGattCharacteristic"),
    "rfcomm": re.compile(r"createRfcommSocket|createInsecureRfcommSocket|BluetoothSocket"),
    "byte_builder": re.compile(r"new byte\[\]\s*\{"),
}
_BLE_KINDS = {"ble_write", "ble_notify", "ble_gatt"}
_CLASSIC_KINDS = {"rfcomm"}


@dataclass(frozen=True)
class Finding:
    kind: str
    file: str   # path relative to the analyzed root
    line: int
    snippet: str


@dataclass
class ApkAnalysis:
    transport: str = "unknown"           # "ble" | "classic-spp" | "both" | "unknown"
    gatt_uuids: list[str] = field(default_factory=list)
    has_spp_uuid: bool = False
    findings: list[Finding] = field(default_factory=list)

    def by_kind(self) -> Counter[str]:
        return Counter(f.kind for f in self.findings)

    def summary(self) -> str:
        counts = self.by_kind()
        lines = [f"transport: {self.transport}"]
        if self.has_spp_uuid:
            lines.append("Serial Port (SPP) service UUID present (00001101)")
        if self.gatt_uuids:
            lines.append(f"{len(self.gatt_uuids)} distinct 128-bit UUID(s): " + ", ".join(self.gatt_uuids[:6]))
        lines += [f"  {k}: {counts[k]}" for k in sorted(counts)]
        return "\n".join(lines)


def analyze_tree(root: str | Path, *, max_snippet: int = 160) -> ApkAnalysis:
    """Walk a decompiled source tree (.java) and map its Bluetooth surface."""
    root = Path(root)
    findings: list[Finding] = []
    uuids: set[str] = set()
    has_spp = False
    kinds_seen: set[str] = set()
    for path in root.rglob("*.java"):
        try:
            text = path.read_text("utf-8", "replace")
        except OSError:
            continue
        rel = str(path.relative_to(root))
        for i, line in enumerate(text.splitlines(), 1):
            for u in _UUID128.findall(line):
                uuids.add(u.lower())
            if _SPP_UUID.search(line):
                has_spp = True
            for kind, pat in _SIGNALS.items():
                if pat.search(line):
                    kinds_seen.add(kind)
                    findings.append(Finding(kind, rel, i, line.strip()[:max_snippet]))

    ble = bool(kinds_seen & _BLE_KINDS)
    classic = has_spp or bool(kinds_seen & _CLASSIC_KINDS)
    transport = (
        "both" if ble and classic
        else "ble" if ble
        else "classic-spp" if classic
        else "unknown"
    )
    return ApkAnalysis(
        transport=transport,
        gatt_uuids=sorted(uuids),
        has_spp_uuid=has_spp,
        findings=findings,
    )


def decompile_apk(apk_path: str | Path, out_dir: str | Path, *, jadx: str = "jadx") -> Path:
    """Run ``jadx -d <out_dir> <apk>`` and return the output directory."""
    import subprocess

    out = Path(out_dir)
    p = subprocess.run(  # noqa: S603
        [jadx, "-d", str(out), str(apk_path)], capture_output=True, text=True
    )
    # jadx returns non-zero on partial-decompile warnings but still produces usable sources.
    if not any(out.rglob("*.java")):
        raise RuntimeError(f"jadx produced no sources: {p.stderr[:300]}")
    return out


def pull_apk(package: str, dest: str | Path, *, runner: Runner | None = None) -> Path:
    """Pull an installed app's base APK off a connected device via adb."""
    adb = runner if runner is not None else AdbRunner()
    paths = adb.run("shell", "pm", "path", package)
    base = None
    for line in paths.splitlines():
        line = line.strip()
        if line.startswith("package:") and line.endswith("base.apk"):
            base = line[len("package:") :]
            break
    if base is None:  # no explicit base.apk (single non-split) — take the first
        for line in paths.splitlines():
            if line.startswith("package:"):
                base = line.strip()[len("package:") :]
                break
    if base is None:
        raise RuntimeError(f"package {package} not found on device")
    dest = Path(dest)
    adb.run("pull", base, str(dest))
    return dest


def analyze_apk(apk_path: str | Path, *, jadx: str = "jadx") -> ApkAnalysis:
    """Decompile an APK (to a temp dir) and analyze it."""
    import tempfile

    with tempfile.TemporaryDirectory() as d:
        out = decompile_apk(apk_path, d, jadx=jadx)
        return analyze_tree(out)
