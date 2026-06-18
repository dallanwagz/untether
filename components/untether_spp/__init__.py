"""untether_spp — a Bluetooth Classic SPP ↔ TCP bridge for ESPHome (classic ESP32 / WROOM-32).

Connects (as RFCOMM master/initiator) to a target device's SPP channel and bridges the raw byte
stream to a TCP server on the ESP32. Home Assistant — or any client (e.g. the untether Python
tooling) — opens `tcp://<esp32>:<tcp_port>` and gets a clean pipe to the Classic-SPP device that
HA's BLE-only Bluetooth stack can't reach.

Requires the **esp-idf** framework on a **classic ESP32** (BR/EDR). Enabling Classic BT here is
heavy, so this component forces **BR/EDR-only** controller mode and disables BLE — do not run an
`esp32_ble_tracker` / `bluetooth_proxy` on the same node.
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

untether_spp_ns = cg.esphome_ns.namespace("untether_spp")
UntetherSpp = untether_spp_ns.class_("UntetherSpp", cg.Component)

CONFIG_SCHEMA = cv.Schema(
    {
        cv.GenerateID(): cv.declare_id(UntetherSpp),
        # The Classic-SPP device to connect to.
        cv.Required(CONF_MAC_ADDRESS): cv.mac_address,
        # RFCOMM channel (SCN). 0 = SDP-discover the SPP channel by UUID.
        cv.Optional(CONF_CHANNEL, default=0): cv.int_range(min=0, max=30),
        # TCP port the bridge listens on (one client at a time).
        cv.Optional(CONF_TCP_PORT, default=8888): cv.port,
        # Local BT device name advertised by this bridge.
        cv.Optional(CONF_DEVICE_NAME, default="untether-spp"): cv.string_strict,
    }
).extend(cv.COMPONENT_SCHEMA)


async def to_code(config):
    # --- Classic BT + SPP, BLE off (memory) ---
    esp32.add_idf_sdkconfig_option("CONFIG_BT_ENABLED", True)
    esp32.add_idf_sdkconfig_option("CONFIG_BT_CLASSIC_ENABLED", True)
    esp32.add_idf_sdkconfig_option("CONFIG_BT_SPP_ENABLED", True)
    esp32.add_idf_sdkconfig_option("CONFIG_BT_BLE_ENABLED", False)
    # BR/EDR-only controller (lighter than dual-mode BTDM).
    esp32.add_idf_sdkconfig_option("CONFIG_BTDM_CTRL_MODE_BR_EDR_ONLY", True)
    esp32.add_idf_sdkconfig_option("CONFIG_BTDM_CTRL_MODE_BLE_ONLY", False)
    esp32.add_idf_sdkconfig_option("CONFIG_BTDM_CTRL_MODE_BTDM", False)

    var = cg.new_Pvariable(config[CONF_ID])
    await cg.register_component(var, config)

    parts = config[CONF_MAC_ADDRESS].parts  # [b0..b5], display order = esp_bd_addr_t order
    cg.add(var.set_target_mac(parts[0], parts[1], parts[2], parts[3], parts[4], parts[5]))
    cg.add(var.set_channel(config[CONF_CHANNEL]))
    cg.add(var.set_tcp_port(config[CONF_TCP_PORT]))
    cg.add(var.set_device_name(config[CONF_DEVICE_NAME]))
