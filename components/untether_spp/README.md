# `untether_spp` — Bluetooth Classic SPP ↔ TCP bridge(s) (ESPHome external component)

The piece that lets Home Assistant reach **Classic Bluetooth SPP** devices — which HA's BLE-only
stack can't. A classic **ESP32 (WROOM-32)** connects (RFCOMM master) to each device's SPP channel
and exposes its raw byte stream as a **TCP server**. HA — or the untether Python tooling — opens
`tcp://<esp32-ip>:<port>` and gets a clean pipe to that device.

**One ESP32 can bridge up to 4 devices at once**, each on its own TCP port, over the single shared
BR/EDR radio. (Hardware-verified driving 4 simultaneously across two wire dialects — see *Status*.)

> **Hardware:** classic **ESP32 only** (BR/EDR). Not S3/C3 (BLE-only). **esp-idf** framework
> required. This component forces **BR/EDR-only** controller mode and **disables BLE** to fit
> Classic BT in RAM — so don't run `bluetooth_proxy`/`esp32_ble_tracker` on the same node.

## Use it

Single device (flat form):

```yaml
external_components:
  - source: github://dallanwagz/untether@main
    components: [untether_spp]
    refresh: 0s

untether_spp:
  mac_address: AA:BB:CC:DD:EE:FF   # the SPP device's BD_ADDR
  channel: 4                       # RFCOMM SCN (TimeBox-mini ch4 / Pixoo ch2); 0 = SDP-discover
  tcp_port: 8888                   # bridge listens here; one client at a time
```

Multiple devices (one TCP port each, up to 4):

```yaml
untether_spp:
  devices:
    - mac_address: B1:21:81:xx:xx:xx   # a Pixoo (NewMode) — wants the 0xAF handshake
      channel: 2
      tcp_port: 8888
      on_open_hex: "01 04 00 af 01 b4 00 02"   # auto-sent once when the link opens
    - mac_address: 11:75:58:xx:xx:xx   # a TimeBox-mini (byte-stuffed dialect)
      channel: 4
      tcp_port: 8889
    - mac_address: B1:21:81:yy:yy:yy   # let the bridge SDP-discover the channel
      channel: 0
      tcp_port: 8890
```

Per-device options: `mac_address` (required), `channel` (RFCOMM SCN; `0` = SDP-discover),
`tcp_port` (required, unique), `on_open_hex` (optional bytes auto-sent once after the link opens —
e.g. a device's connect handshake). Optional top-level `device_name` sets the bridge's BT name.

Then from anywhere on the LAN, talk to a given device on its port:

```sh
nc <esp32-ip> 8888           # raw pipe — send a framed command, read replies
# or: socket.create_connection((esp32_ip, 8888)) and speak the device's wire protocol
```

## How it works

- **SPP clients:** one `esp_spp` RFCOMM-master link per device (`ESP_SPP_SEC_NONE`, ERTM off,
  just-works SSP). The single Bluedroid SPP callback is demultiplexed per device by handle (data /
  congestion / write / close) or remote BD_ADDR (open). Connections are **established one at a time**
  (serialized, with a timeout) because `ESP_SPP_DISCOVERY_COMP` carries no address to attribute SDP
  results. Capped-backoff reconnect per device (1 s → 60 s).
- **TCP bridges:** a non-blocking TCP server per device in `loop()`. Device→client bytes are staged
  in a per-device FreeRTOS ring buffer and drained to that device's socket; client→device bytes are
  `recv`'d and `esp_spp_write`'d (paused on SPP congestion). One client per port. A client that
  disconnects is reaped even while its SPP link is down or congested (so a stuck device can never
  wedge its TCP server).
- **ACL limit:** each device needs its own BR/EDR ACL link; the controller defaults to 2, so the
  component raises `CONFIG_BTDM_CTRL_BR_EDR_MAX_ACL_CONN` to the device count automatically.
- It's a **transport bridge** — it does **not** parse the protocol. Each device's dialect (framing,
  byte-stuffing, image format) is handled entirely by the client; the bridge just pipes bytes, so
  mixing dialects (Pixoo NewMode + TimeBox byte-stuffed) on one ESP32 works fine.

## Status

**Hardware-verified.** Built under ESP-IDF 5.5 and confirmed driving **4 devices simultaneously** on
one classic ESP32 — two Pixoos + a TimeBox-mini + a MiniToo (both the Pixoo NewMode and the
byte-stuffed TimeBox dialects), each independently controllable with bidirectional readback. RAM
~22 % static, Flash ~54 %.

## Caveats & operating notes

- **Up to 4 devices** per node (RAM for the per-device ring buffers + shared-radio airtime). For
  more, use multiple ESP32s.
- **Throughput is modest and shared.** Classic SPP on these modules sustains only ~3–15 KB/s per
  link, and all links share one radio. Rate-limit bulk writes; don't blast.
- **Single-bond is per device, not per host:** one host per box, but this one ESP32 *is* that host
  for all its devices. Keep the vendor app / other hosts (a phone, a Pi) **off** any box the bridge
  holds — a competing host will silently keep a device from connecting.
- **Rebooting/reflashing the bridge orphans the device links**, so devices page-timeout briefly
  until their stale links clear; a device stuck "unreachable" usually just needs a **power-cycle**.
- One TCP client per port; binary-clean (no framing added).
