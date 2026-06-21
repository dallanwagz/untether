"""Frida runner tests — pure message parsing + the bundled hook script."""

from untether_bt import hook_script_path, parse_hook_message


def _send(payload):
    return {"type": "send", "payload": payload}


def test_ble_write_message():
    ev = parse_hook_message(_send({"t": "ble_write", "uuid": "0000ffe1-...", "hex": "7432", "ts": 1700}))
    assert ev is not None
    assert ev.sent and ev.transport == "att" and ev.data == b"\x74\x32"
    assert ev.timestamp_us == 1700 * 1000
    assert "ble_write" in ev.summary and "ffe1" in ev.summary


def test_ble_set_message():
    ev = parse_hook_message(_send({"t": "ble_set", "uuid": "x", "hex": "aabb", "ts": 0}))
    assert ev.data == b"\xaa\xbb" and ev.transport == "att"


def test_rfcomm_message():
    ev = parse_hook_message(_send({"t": "rfcomm_write", "hex": "0104007432aa0002", "ts": 5}))
    assert ev.transport == "rfcomm" and ev.data == bytes.fromhex("0104007432aa0002")


def test_non_write_messages_ignored():
    assert parse_hook_message(_send({"t": "ready"})) is None
    assert parse_hook_message(_send({"t": "err", "m": "boom"})) is None
    assert parse_hook_message({"type": "error", "description": "oops"}) is None
    assert parse_hook_message({}) is None


def test_bad_hex_returns_none():
    assert parse_hook_message(_send({"t": "ble_write", "hex": "zz", "ts": 1})) is None


def test_hook_script_bundled():
    p = hook_script_path()
    assert p.exists()
    js = p.read_text("utf-8")
    assert "BluetoothGattCharacteristic" in js
    assert "writeCharacteristic" in js
    assert "rfcomm_write" in js  # Classic path present
