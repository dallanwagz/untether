"""Static-analysis tests — analyze_tree against synthetic decompiled trees."""

from untether_bt import analyze_tree


def _tree(tmp_path, files: dict[str, str]):
    for rel, content in files.items():
        p = tmp_path / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_text(content)
    return tmp_path


def test_ble_only(tmp_path):
    _tree(tmp_path, {
        "com/vendor/Ble.java": (
            "BluetoothGatt gatt;\n"
            "void send(BluetoothGattCharacteristic c){ c.setValue(new byte[]{0x01,0x02}); "
            "gatt.writeCharacteristic(c); }\n"
            "UUID U = UUID.fromString(\"0000ffe1-0000-1000-8000-00805f9b34fb\");\n"
        ),
    })
    a = analyze_tree(tmp_path)
    assert a.transport == "ble"
    assert "0000ffe1-0000-1000-8000-00805f9b34fb" in a.gatt_uuids
    assert not a.has_spp_uuid
    kinds = a.by_kind()
    assert kinds["ble_write"] >= 1 and kinds["ble_gatt"] >= 1 and kinds["byte_builder"] >= 1


def test_classic_spp_only(tmp_path):
    _tree(tmp_path, {
        "Spp.java": (
            "import android.bluetooth.BluetoothSocket;\n"
            "sock = dev.createRfcommSocketToServiceRecord("
            "UUID.fromString(\"00001101-0000-1000-8000-00805f9b34fb\"));\n"
        ),
    })
    a = analyze_tree(tmp_path)
    assert a.transport == "classic-spp"
    assert a.has_spp_uuid
    assert a.by_kind()["rfcomm"] >= 1


def test_both_transports(tmp_path):
    _tree(tmp_path, {
        "a.java": "gatt.writeCharacteristic(c); BluetoothGatt g;\n",
        "b.java": "new BluetoothSocket(); createInsecureRfcommSocket();\n",
    })
    a = analyze_tree(tmp_path)
    assert a.transport == "both"


def test_unknown_when_no_signals(tmp_path):
    _tree(tmp_path, {"plain.java": "int x = 1; // nothing bluetooth here\n"})
    a = analyze_tree(tmp_path)
    assert a.transport == "unknown" and not a.findings and not a.gatt_uuids


def test_findings_have_file_and_line(tmp_path):
    _tree(tmp_path, {"x.java": "line0\ngatt.writeCharacteristic(c);\n"})
    a = analyze_tree(tmp_path)
    f = next(f for f in a.findings if f.kind == "ble_write")
    assert f.file == "x.java" and f.line == 2 and "writeCharacteristic" in f.snippet


def test_summary_renders(tmp_path):
    _tree(tmp_path, {"x.java": "gatt.writeCharacteristic(c);\n"})
    s = analyze_tree(tmp_path).summary()
    assert "transport: ble" in s
