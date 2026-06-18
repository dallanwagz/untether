#pragma once
#ifdef USE_ESP32

#include "esphome/core/component.h"
#include "esp_bt_defs.h"
#include "esp_spp_api.h"
#include "freertos/FreeRTOS.h"
#include "freertos/ringbuf.h"

#include <string>
#include <vector>

namespace esphome {
namespace untether_spp {

// Classic SPP <-> TCP bridge. RFCOMM master/initiator to a fixed MAC+channel, raw byte pipe to a
// single TCP client. See __init__.py for the config schema.
class UntetherSpp : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  void set_target_mac(uint8_t b0, uint8_t b1, uint8_t b2, uint8_t b3, uint8_t b4, uint8_t b5) {
    target_[0] = b0; target_[1] = b1; target_[2] = b2;
    target_[3] = b3; target_[4] = b4; target_[5] = b5;
  }
  void set_channel(uint8_t ch) { channel_ = ch; }
  void set_tcp_port(uint16_t port) { tcp_port_ = port; }
  void set_device_name(const std::string &name) { device_name_ = name; }
  void set_on_open(const std::vector<uint8_t> &bytes) { on_open_ = bytes; }

  // Called from the Bluedroid GAP/SPP task callbacks (registered as static trampolines).
  void on_spp_event(esp_spp_cb_event_t event, esp_spp_cb_param_t *param);

 protected:
  // --- TCP side (runs in loop(), main task) ---
  void tcp_setup_();
  void tcp_service_();
  void try_connect_spp_();
  void send_on_open_();

  esp_bd_addr_t target_{};
  uint8_t channel_{0};         // 0 => SDP discover
  uint16_t tcp_port_{8888};
  std::string device_name_{"untether-spp"};

  // SPP state (written in BT task, read in loop)
  volatile bool spp_open_{false};
  volatile bool spp_congested_{false};
  volatile uint32_t spp_handle_{0};
  volatile bool want_reconnect_{false};
  uint32_t last_connect_attempt_{0};
  uint32_t backoff_ms_{1000};

  // Optional handshake auto-sent once, shortly after SPP opens (see on_open_hex).
  std::vector<uint8_t> on_open_;
  volatile bool pending_on_open_{false};
  uint32_t spp_open_at_{0};

  // SPP -> TCP buffer (filled in BT task, drained in loop)
  RingbufHandle_t rb_in_{nullptr};

  // TCP server / client
  int listen_fd_{-1};
  int client_fd_{-1};
};

}  // namespace untether_spp
}  // namespace esphome
#endif  // USE_ESP32
