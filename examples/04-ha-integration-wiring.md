# 4 · Wiring it into Home Assistant (via Bluetooth proxies)

The user already had ESPHome Bluetooth **proxies** around the house, so the integration is a HACS
custom component that connects through the proxy mesh — no dedicated hardware next to the device.

## Connect through whatever proxy is in range

The coordinator uses HA's Bluetooth stack to get a `BLEDevice` (routed via the best proxy) and
`bleak-retry-connector` to establish the link, then subscribes to the notify char:

```python
from homeassistant.components import bluetooth
from bleak_retry_connector import BleakClientWithServiceCache, establish_connection

async def _async_ensure_connected(self) -> None:
    if self.connected:
        return
    async with self._lock:
        ble_device = bluetooth.async_ble_device_from_address(
            self.hass, self.address, connectable=True)        # picks the proxy with best signal
        if ble_device is None:
            raise BleakError(f"{self.address} not reachable via any Bluetooth proxy/adapter")
        client = await establish_connection(
            BleakClientWithServiceCache, ble_device, self.address,
            disconnected_callback=self._on_disconnect)
        await client.start_notify(STATUS_CHAR_UUID, self._on_notify)   # -> parse_status -> push state
        self._client = client
        self.async_update_listeners()

async def send_command(self, message_id: int) -> None:
    await self._async_ensure_connected()
    await self._client.write_gatt_char(COMMAND_CHAR_UUID, build_frame(message_id), response=False)
```

Notifications flow straight into the decoder:

```python
def _on_notify(self, _char, data: bytearray) -> None:
    state = parse_status(bytes(data))
    if state is not None:
        self.async_set_updated_data(state)        # all sensors update
```

## A generic service for the long tail

Rather than a button for all ~60 vendor commands, a single service fires any messageId from
automations / Alexa routines:

```python
async def _handle_send_command(call: ServiceCall) -> None:
    message_id = call.data["message_id"]
    for entry in hass.config_entries.async_loaded_entries(DOMAIN):
        await entry.runtime_data.send_command(message_id)

hass.services.async_register(DOMAIN, "send_command", _handle_send_command, schema=SEND_COMMAND_SCHEMA)
```

```yaml
# automation: zero-gravity via the service
action:
  - service: infinity_chair.send_command
    data: {message_id: 112}
```

## A composed action: "Return to origin"

Decoded run-state (`b7`) let us build a higher-level button — send the chair home from any state,
which is voice-friendly ("Alexa, return to origin"):

```python
async def async_press(self) -> None:
    state = self.coordinator.data.run_state if self.coordinator.data else None
    if state in ("running", "ready"):
        await self.coordinator.send_command(POWER)            # one press resets to home
    elif state != "resetting":                                # idle/reclined: power on, settle, off
        await self.coordinator.send_command(POWER)
        await asyncio.sleep(4)
        await self.coordinator.send_command(POWER)
```

## Gotcha baked into the docs

These devices accept **one** BLE central — keep the vendor app disconnected while HA controls the
device, or they fight over the single slot. (See example 5 for diagnosing slot contention.)
