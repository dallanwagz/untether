// untether-bt — Frida hooks for Android Bluetooth app RE.
//
// Dumps the OUTGOING command bytes an app sends — the primary RE target ("when I tap X, what bytes
// go out?") — for both BLE GATT and Bluetooth Classic (RFCOMM/SPP), at the API layer (before the
// radio, so it works even when the link is encrypted). Each write is `send()`-ed to the host runner
// (untether_bt.frida) as a structured message; the host turns it into a WireEvent and correlates it.
//
// Load with: frida -U -f <pkg> -l android_bt.js  (or via untether_bt.frida.FridaSession)

function toHex(arr) {
  if (!arr) return "";
  var s = "";
  for (var i = 0; i < arr.length; i++) {
    var b = arr[i] & 0xff;
    s += ("0" + b.toString(16)).slice(-2);
  }
  return s;
}

Java.perform(function () {
  // ---- BLE GATT writes ----
  try {
    var Char = Java.use("android.bluetooth.BluetoothGattCharacteristic");
    Char.setValue.overload("[B").implementation = function (v) {
      try { send({ t: "ble_set", uuid: this.getUuid().toString(), hex: toHex(v), ts: Date.now() }); } catch (e) {}
      return this.setValue(v);
    };
    var Gatt = Java.use("android.bluetooth.BluetoothGatt");
    Gatt.writeCharacteristic.overload("android.bluetooth.BluetoothGattCharacteristic").implementation = function (c) {
      try {
        var v = c.getValue();
        send({ t: "ble_write", uuid: c.getUuid().toString(), hex: v ? toHex(v) : "", ts: Date.now() });
      } catch (e) {}
      return this.writeCharacteristic(c);
    };
  } catch (e) {
    send({ t: "err", m: "gatt hooks: " + e });
  }

  // ---- Bluetooth Classic (RFCOMM/SPP) writes ----
  // The SPP output stream is a private inner class; hook OutputStream.write broadly and emit only
  // when the concrete stream belongs to a Bluetooth socket (filter by class name).
  try {
    var OS = Java.use("java.io.OutputStream");
    var isBt = function (self) {
      try { return self.getClass().getName().indexOf("Bluetooth") >= 0; } catch (e) { return false; }
    };
    OS.write.overload("[B", "int", "int").implementation = function (b, off, len) {
      if (isBt(this)) {
        try {
          var slice = Java.array("byte", b).slice(off, off + len);
          send({ t: "rfcomm_write", hex: toHex(slice), ts: Date.now() });
        } catch (e) {}
      }
      return this.write(b, off, len);
    };
    OS.write.overload("[B").implementation = function (b) {
      if (isBt(this)) {
        try { send({ t: "rfcomm_write", hex: toHex(b), ts: Date.now() }); } catch (e) {}
      }
      return this.write(b);
    };
  } catch (e) {
    send({ t: "err", m: "rfcomm hooks: " + e });
  }

  send({ t: "ready" });
});
