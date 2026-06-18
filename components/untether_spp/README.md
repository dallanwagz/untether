# `untether_spp` — Bluetooth Classic SPP ↔ TCP bridge (ESPHome external component)

The piece that lets Home Assistant reach a **Classic Bluetooth SPP** device — which HA's BLE-only
stack can't. A classic **ESP32 (WROOM-32)** connects (RFCOMM master) to the device's SPP channel and
exposes the raw byte stream as a **TCP server**. HA — or the untether Python tooling — opens
`tcp://<esp32-ip>:<port>` and gets a clean pipe to the device.

> **Hardware:** classic **ESP32 only** (BR/EDR). Not S3/C3 (BLE-only). **esp-idf** framework
> required. This component forces **BR/EDR-only** controller mode and **disables BLE** to fit
> Classic BT in RAM — so don't run `bluetooth_proxy`/`esp32_ble_tracker` on the same node.

## Use it

```yaml
external_components:
  - source: github://dallanwagz/untether@main
    components: [untether_spp]
    refresh: 0s                                  # always re-pull during development

untether_spp:
  mac_address: AA:BB:CC:DD:EE:FF   # <-- the SPP device's BD_ADDR (e.g. your TimeBox-mini)
  channel: 4                       # RFCOMM SCN (TimeBox-mini ch4 / Pixoo ch2); 0 = SDP-discover
  tcp_port: 8888                   # bridge listens here; one client at a time
  on_open_hex: ""                  # optional: bytes auto-sent once after SPP opens (handshake)
```

Then from anywhere on the LAN:

```sh
# raw pipe to the SPP device — send a framed command, read replies
nc <esp32-ip> 8888
# or in Python: socket.create_connection((esp32_ip, 8888)) and speak the device's wire protocol
```

### `on_open_hex` — auto-handshake on connect

Some devices need a connect handshake before they accept commands (Divoom NewMode panels want the
`0xAF` connected-flag frame first). The bridge is transparent, so normally the TCP client sends that
itself. Set `on_open_hex` to have the bridge fire it for you, once, ~300ms after the SPP link opens —
then a bare `nc … | brightness` works without the client knowing the handshake:

```yaml
untether_spp:
  mac_address: AA:BB:CC:DD:EE:FF
  channel: 2
  on_open_hex: "01 04 00 af 01 b4 00 02"   # Divoom Pixoo NewMode connect handshake
```

Spaces and colons are ignored; `"010400af01b40002"` is identical. Leave it empty (default) to send
nothing on open.

## How it works

- **SPP client:** `esp_spp` in callback mode, `ESP_SPP_SEC_NONE`, role master, ERTM off (matches
  finicky modules). Connects to `mac_address` on `channel` (or SDP-discovers when `channel: 0`),
  just-works SSP (auto-accepts pairing), with capped-backoff reconnect.
- **TCP bridge:** a non-blocking TCP server in `loop()`. Device→client bytes are staged in a
  FreeRTOS ring buffer by the SPP callback and drained to the socket; client→device bytes are
  `recv`'d and `esp_spp_write`'d (paused on SPP congestion). One client at a time.

## Status / caveats

- **Hardware-verified** — built under ESP-IDF 5.5 (`esp_spp_api`) and confirmed on a classic ESP32
  driving a Divoom Pixoo 16 over RFCOMM ch2 (handshake + brightness over `nc`).
- Single TCP client; binary-clean (no framing added — the device's own framing passes through).
- One SPP link per node. For multiple SPP devices, use multiple ESP32s (or extend to multi-handle).
- It's a transport bridge — it does **not** parse the protocol. Decode lives in your HA integration
  / the untether device profile.
