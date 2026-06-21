"""Live-driver tests — pure UI parsing + a fake-runner AndroidDriver (no device needed)."""

import zipfile

import pytest

from untether_bt import (
    AdbError,
    AndroidDriver,
    Recorder,
    extract_btsnoop_from_zip,
    find_node,
    make_record,
    parse_ui_dump,
    write_btsnoop,
)
from untether_bt.btsnoop import DLT_HCI_UART_H4

SAMPLE_XML = """<?xml version='1.0' encoding='UTF-8'?>
<hierarchy rotation="0">
  <node text="Power" content-desc="" resource-id="com.vendor:id/power"
        class="android.widget.Button" package="com.vendor" bounds="[10,20][110,80]"
        clickable="true" checked="false"/>
  <node text="" content-desc="Brightness" resource-id="com.vendor:id/bright"
        class="android.widget.Switch" package="com.vendor" bounds="[0,100][200,160]"
        clickable="true" checked="true"/>
</hierarchy>"""


# ---- pure UI parsing ----
def test_parse_and_find_and_center():
    nodes = parse_ui_dump(SAMPLE_XML)
    assert len(nodes) == 2
    power = find_node(nodes, "power")
    assert power.text == "Power" and power.center == (60, 50)
    bright = find_node(nodes, "Brightness")  # matches content-desc
    assert bright.resource_id == "com.vendor:id/bright" and bright.checked is True
    assert find_node(nodes, "nonexistent") is None


def test_match_by_resource_id():
    nodes = parse_ui_dump(SAMPLE_XML)
    assert find_node(nodes, "id/bright").desc == "Brightness"


# ---- btsnoop extraction from a (fake) bugreport zip ----
def test_extract_btsnoop_from_zip(tmp_path):
    snoop = write_btsnoop(
        DLT_HCI_UART_H4,
        [make_record(b"\x04\x0e", unix_us=1_000_000, received=True, command_or_event=True)],
    )
    zpath = tmp_path / "bugreport.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("bugreport-foo/version.txt", "x")
        z.writestr("FS/data/misc/bluetooth/logs/btsnoop_hci.log", snoop)
    assert extract_btsnoop_from_zip(str(zpath)) == snoop


def test_extract_btsnoop_missing_raises(tmp_path):
    zpath = tmp_path / "empty.zip"
    with zipfile.ZipFile(zpath, "w") as z:
        z.writestr("nothing.txt", "x")
    with pytest.raises(AdbError):
        extract_btsnoop_from_zip(str(zpath))


# ---- AndroidDriver with an injected fake runner ----
class FakeRunner:
    def __init__(self, responses=None):
        self.calls: list[tuple[str, ...]] = []
        self.responses = responses or {}

    def run(self, *args):
        self.calls.append(args)
        return self.responses.get(args, "")

    def run_bytes(self, *args):
        self.calls.append(args)
        return self.responses.get(args, b"")

    def shell(self, *args):
        return self.run("shell", *args)


def test_devices_parsing():
    r = FakeRunner({("devices",): "List of devices attached\nABC123\tdevice\nXYZ\toffline\n"})
    assert AndroidDriver(runner=r).devices() == ["ABC123"]


def test_tap_finds_node_and_taps_center():
    r = FakeRunner({("exec-out", "cat", "/sdcard/untether_ui.xml"): SAMPLE_XML.encode()})
    drv = AndroidDriver(runner=r)
    node = drv.tap("Power")
    assert node.text == "Power"
    assert ("shell", "input", "tap", "60", "50") in r.calls
    assert ("shell", "uiautomator", "dump", "/sdcard/untether_ui.xml") in r.calls


def test_tap_missing_raises():
    r = FakeRunner({("exec-out", "cat", "/sdcard/untether_ui.xml"): SAMPLE_XML.encode()})
    with pytest.raises(AdbError):
        AndroidDriver(runner=r).tap("DoesNotExist")


def test_enable_hci_snoop_issues_commands():
    r = FakeRunner()
    AndroidDriver(runner=r).enable_hci_snoop()
    assert ("shell", "settings", "put", "global", "bluetooth_hci_log", "1") in r.calls
    assert ("shell", "svc", "bluetooth", "disable") in r.calls
    assert ("shell", "svc", "bluetooth", "enable") in r.calls


def test_tap_and_mark_records_action():
    r = FakeRunner({("exec-out", "cat", "/sdcard/untether_ui.xml"): SAMPLE_XML.encode()})
    drv = AndroidDriver(runner=r)
    rec = Recorder()
    drv.tap_and_mark("Power", rec)
    assert [m.label for m in rec.marks] == ["Power"]
    assert ("shell", "input", "tap", "60", "50") in r.calls


def test_text_and_keys():
    r = FakeRunner()
    drv = AndroidDriver(runner=r)
    drv.text("hello world")
    drv.back()
    assert ("shell", "input", "text", "hello%sworld") in r.calls
    assert ("shell", "input", "keyevent", "4") in r.calls


def test_pull_btsnoop_path():
    snoop = b"btsnoop\x00rest"
    r = FakeRunner({
        ("exec-out", "cat", "/data/misc/bluetooth/logs/btsnoop_hci.log"): snoop,
        ("exec-out", "su", "0", "cat", "/data/misc/bluetooth/logs/btsnoop_hci.log"): snoop,
    })
    drv = AndroidDriver(runner=r)
    assert drv.pull_btsnoop_path() == snoop
    assert drv.pull_btsnoop_path(su=True) == snoop
