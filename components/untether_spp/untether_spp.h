#pragma once
#ifdef USE_ESP32

#include "esphome/core/component.h"
#include "esp_bt_defs.h"
#include "esp_spp_api.h"
#include "freertos/FreeRTOS.h"
#include "freertos/ringbuf.h"

#include <cstring>
#include <memory>
#include <string>
#include <vector>

namespace esphome {
namespace untether_spp {

// One bridged Classic-SPP device: a fixed MAC+channel RFCOMM link exposed as its own TCP server.
struct SppDevice {
  esp_bd_addr_t target{};
  uint8_t channel{0};            // 0 => SDP-discover the SPP channel
  uint16_t tcp_port{0};
  std::vector<uint8_t> on_open;  // optional handshake sent once after the link opens

  // SPP link state (written in the BT task, read in loop())
  volatile bool spp_open{false};
  volatile bool spp_congested{false};
  volatile uint32_t spp_handle{0};
  volatile bool want_reconnect{false};
  uint32_t last_attempt{0};
  uint32_t backoff_ms{1000};

  // on_open handshake bookkeeping
  volatile bool pending_on_open{false};
  uint32_t open_at{0};

  // SPP -> TCP staging (filled in the BT task, drained in loop())
  RingbufHandle_t rb_in{nullptr};

  // TCP server / single client for this device
  int listen_fd{-1};
  int client_fd{-1};
};

// Bridges 1..N Classic-SPP devices over one shared BR/EDR radio. Each device gets an independent
// RFCOMM master link and TCP server; the single Bluedroid SPP callback is demultiplexed by handle
// (or remote BD_ADDR on open). See __init__.py for the config schema.
class UntetherSpp : public Component {
 public:
  void setup() override;
  void loop() override;
  void dump_config() override;
  float get_setup_priority() const override { return setup_priority::AFTER_WIFI; }

  void set_device_name(const std::string &name) { device_name_ = name; }
  void add_device(uint8_t b0, uint8_t b1, uint8_t b2, uint8_t b3, uint8_t b4, uint8_t b5,
                  uint8_t channel, uint16_t tcp_port, const std::vector<uint8_t> &on_open);

  // Called from the Bluedroid GAP/SPP task callbacks (registered as static trampolines).
  void on_spp_event(esp_spp_cb_event_t event, esp_spp_cb_param_t *param);

 protected:
  void manage_connections_();          // serialized connect/discovery state machine
  void send_on_open_(SppDevice &d);
  void tcp_setup_(SppDevice &d);
  void tcp_service_(SppDevice &d);
  SppDevice *by_handle_(uint32_t handle);
  SppDevice *by_bda_(const esp_bd_addr_t bda);

  std::string device_name_{"untether-spp"};
  std::vector<std::unique_ptr<SppDevice>> devices_;

  bool spp_ready_{false};              // set on ESP_SPP_INIT_EVT
  int connecting_idx_{-1};             // device index with a connect/discovery in flight, else -1
  uint32_t connect_started_{0};
};

}  // namespace untether_spp
}  // namespace esphome
#endif  // USE_ESP32
