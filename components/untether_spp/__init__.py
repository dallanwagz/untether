"""untether_spp — Bluetooth Classic SPP <-> TCP bridge(s) for ESPHome (classic ESP32 / WROOM-32).

Bridges one OR MORE Classic-SPP devices from a single classic ESP32: one shared BR/EDR radio and
Bluedroid stack, N independent RFCOMM master links, each exposed as its own TCP server. Home
Assistant — or any client (`nc`, the untether Python tooling) — opens `tcp://<esp32>:<tcp_port>` for
a given device and gets a clean pipe to it, reaching Classic-SPP devices HA's BLE-only stack can't.

Two config forms:

    # single device (flat)
    untether_spp:
      mac_address: AA:BB:CC:DD:EE:FF
      channel: 2
      tcp_port: 8888

    # multiple devices (one TCP port each)
    untether_spp:
      devices:
        - mac_address: AA:BB:CC:DD:EE:FF
          channel: 2
          tcp_port: 8888
        - mac_address: 11:22:33:44:55:66
          channel: 4
          tcp_port: 8889

Requires the **esp-idf** framework on a **classic ESP32** (BR/EDR). This forces BR/EDR-only
controller mode and disables BLE to fit Classic BT in RAM — don't run esp32_ble_tracker /
bluetooth_proxy on the same node. The shared radio's airtime is split across all links.
"""

import esphome.codegen as cg
import esphome.config_validation as cv
from esphome.components import esp32
from esphome.const import CONF_ID, CONF_MAC_ADDRESS

CODEOWNERS = ["@dallanwagz"]
DEPENDENCIES = ["esp32"]

CONF_CHANNEL = "channel"
CONF_TCP_PORT = "tcp_port"
CONF_DEVICE_NAME = "device_name"
CONF_ON_OPEN_HEX = "on_open_hex"
CONF_DEVICES = "devices"

# One shared radio + limited RAM (a ring buffer per device) + split airtime -> keep this modest.
MAX_DEVICES = 4

untether_spp_ns = cg.esphome_ns.namespace("untether_spp")
UntetherSpp = untether_spp_ns.class_("UntetherSpp", cg.Component)


def _hex_bytes(value):
    """A hex string (spaces/colons allowed) -> list[int]. e.g. '01 04 00 af' -> [1, 4, 0, 175]."""
    value = cv.string_strict(value)
    cleaned = value.replace(" ", "").replace(":", "")
    if len(cleaned) % 2 != 0:
        raise cv.Invalid(f"{CONF_ON_OPEN_HEX} must have an even number of hex digits")
    try:
        return list(bytes.fromhex(cleaned))
    except ValueError as err:
        raise cv.Invalid(f"{CONF_ON_OPEN_HEX} is not valid hex: {err}")


DEVICE_SCHEMA = cv.Schema(
    {
        cv.Required(CONF_MAC_ADDRESS): cv.mac_address,
        cv.Optional(CONF_CHANNEL, default=0): cv.int_range(min=0, max=30),
        cv.Required(CONF_TCP_PORT): cv.port,
        cv.Optional(CONF_ON_OPEN_HEX, default=""): _hex_bytes,
    }
)


def _validate(config):
    """Accept the flat single-device form or a devices list; normalize to a devices list."""
    has_flat = CONF_MAC_ADDRESS in config
    has_list = CONF_DEVICES in config
    if has_flat and has_list:
        raise cv.Invalid(
            "use either a top-level 'mac_address' (single device) OR a 'devices:' list, not both"
        )
    if not has_flat and not has_list:
        raise cv.Invalid("untether_spp needs a 'mac_address' (single device) or a 'devices:' list")

    config = dict(config)
    if has_flat:
        config[CONF_DEVICES] = [
            {
                CONF_MAC_ADDRESS: config[CONF_MAC_ADDRESS],
                CONF_CHANNEL: config[CONF_CHANNEL],
                CONF_TCP_PORT: config.get(CONF_TCP_PORT, 8888),
                CONF_ON_OPEN_HEX: config[CONF_ON_OPEN_HEX],
            }
        ]
    # strip the flat keys so to_code only ever reads CONF_DEVICES
    for k in (CONF_MAC_ADDRESS, CONF_CHANNEL, CONF_TCP_PORT, CONF_ON_OPEN_HEX):
        config.pop(k, None)

    devices = config[CONF_DEVICES]
    if not 1 <= len(devices) <= MAX_DEVICES:
        raise cv.Invalid(f"untether_spp supports 1..{MAX_DEVICES} devices (got {len(devices)})")
    ports = [d[CONF_TCP_PORT] for d in devices]
    if len(set(ports)) != len(ports):
        raise cv.Invalid("each device needs a unique tcp_port")
    macs = [str(d[CONF_MAC_ADDRESS]) for d in devices]
    if len(set(macs)) != len(macs):
        raise cv.Invalid("each device needs a unique mac_address")
    return config


CONFIG_SCHEMA = cv.All(
    cv.Schema(
        {
            cv.GenerateID(): cv.declare_id(UntetherSpp),
            # Local BT device name advertised by this bridge (shared across all links).
            cv.Optional(CONF_DEVICE_NAME, default="untether-spp"): cv.string_strict,
            # --- single-device (flat) form ---
            cv.Optional(CONF_MAC_ADDRESS): cv.mac_address,
            cv.Optional(CONF_CHANNEL, default=0): cv.int_range(min=0, max=30),
            cv.Optional(CONF_TCP_PORT): cv.port,
            cv.Optional(CONF_ON_OPEN_HEX, default=""): _hex_bytes,
            # --- multi-device form ---
            cv.Optional(CONF_DEVICES): cv.ensure_list(DEVICE_SCHEMA),
        }
    ).extend(cv.COMPONENT_SCHEMA),
    _validate,
)


async def to_code(config):
    # --- Classic BT + SPP, BLE off (memory) ---
    esp32.add_idf_sdkconfig_option("CONFIG_BT_ENABLED", True)
    esp32.add_idf_sdkconfig_option("CONFIG_BT_CLASSIC_ENABLED", True)
    esp32.add_idf_sdkconfig_option("CONFIG_BT_SPP_ENABLED", True)
    esp32.add_idf_sdkconfig_option("CONFIG_BT_BLE_ENABLED", False)
    esp32.add_idf_sdkconfig_option("CONFIG_BTDM_CTRL_MODE_BR_EDR_ONLY", True)
    esp32.add_idf_sdkconfig_option("CONFIG_BTDM_CTRL_MODE_BLE_ONLY", False)
    esp32.add_idf_sdkconfig_option("CONFIG_BTDM_CTRL_MODE_BTDM", False)

    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)
    cg.add(var.set_device_name(config[CONF_DEVICE_NAME]))

    for dev in config[CONF_DEVICES]:
        p = dev[CONF_MAC_ADDRESS].parts  # [b0..b5], display order = esp_bd_addr_t order
        cg.add(
            var.add_device(
                p[0], p[1], p[2], p[3], p[4], p[5],
                dev[CONF_CHANNEL],
                dev[CONF_TCP_PORT],
                dev[CONF_ON_OPEN_HEX],
            )
        )
