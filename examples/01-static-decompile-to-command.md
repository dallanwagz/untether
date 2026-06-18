# 1 · Decompiled frame builder → `build_frame()` → an HA button

## What static analysis found (jadx)

Decompiling the vendor APK surfaced the authoritative frame builder. The command on the wire is
**not** the bare 3-byte payload — `BluetoothChatService.write()` wraps it in start/end markers, and
`ClsUnit.getData()` spells out the full frame:

```java
// rongtai/infinify/ClsUnit.java  — the authoritative wire frame
public byte[] getData(byte b) {
    byte[] bArr = new byte[5];
    bArr[0] = -16;                                   // 0xF0  SOI (start of frame)
    bArr[1] = -125;                                  // 0x83  VOI (command type)
    bArr[2] = b;                                     //       messageId
    bArr[3] = (byte) (((byte) (~((byte) (bArr[1] + bArr[2])))) & 127);  // checksum
    bArr[4] = -15;                                   // 0xF1  EOI (end of frame)
    return bArr;
}
```

So: `F0 83 <id> <checksum> F1`, with `checksum = (~(0x83 + id)) & 0x7F`.

> **Trap caught here:** an earlier read of `MainActivity.sendMessage()` showed only a 3-byte
> `[0x83, id, cksum]` array — but `write()` prepends `SOI` and appends `EOI`. Sending the bare 3
> bytes did nothing; the device only accepts the framed 5 bytes. *The wire frame ≠ the payload.*

Grepping the constants gave the **command catalog** (every messageId):

```java
// rongtai/infinify/BluetoothTransfer.java (excerpt)
H10_KEY_POWER_SWITCH = 1;
H10_KEY_CHAIR_AUTO_0 = 16; ... H10_KEY_CHAIR_AUTO_5 = 21;   // auto programs
H10_KEY_KNEAD = 32; H10_KEY_KNOCK = 33; H10_KEY_PRESS = 34; // shiatsu
H10_KEY_HEAT = 39;  H10_KEY_AIRBAG_AUTO = 68;
H10_KEY_ZERO_GRAVITY = 112;
H10_KEY_WORK_TIME_10MIN = 80; ... 30MIN = 82;              // session length
```

…and the **gating logic** (why a command silently does nothing):

```java
// blocked unless the chair is running, except power / pad-moves / zero-gravity
if (messageId != 1 && messageId != 112 && ... && recievedState.nChairRunState == 0) return;
```

## What it became in Home Assistant

`protocol.py` — pure, no HA deps, unit-tested against the formula above:

```python
_SOI, _VOI, _EOI = 0xF0, 0x83, 0xF1

COMMANDS = {"power": 1, "auto_recover": 16, ..., "shiatsu": 34,
            "heat": 39, "airbag_auto": 68, "zero_gravity": 112,
            "session_10min": 80, "session_20min": 81, "session_30min": 82}

def build_frame(message_id: int) -> bytes:
    checksum = (~(_VOI + message_id)) & 0x7F
    return bytes([_SOI, _VOI, message_id, checksum, _EOI])
```

Each catalog entry becomes a momentary **button**:

```python
class InfinityChairButton(InfinityChairEntity, ButtonEntity):
    def __init__(self, coordinator, key, message_id):
        super().__init__(coordinator, key)
        self._attr_translation_key = key
        self._message_id = message_id

    async def async_press(self) -> None:
        await self.coordinator.send_command(self._message_id)   # -> build_frame -> write to fff1
```

```python
# button platform setup
async_add_entities(InfinityChairButton(coordinator, key, mid) for key, mid in COMMANDS.items())
```

Pressing **Shiatsu** in HA → `send_command(34)` → `build_frame(34)` = `F0 83 22 5A F1` → written to
the command characteristic. The gating finding became a documented note: manual techniques only act
once the chair is running, so press **Power** first.
