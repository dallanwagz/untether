#ifdef USE_ESP32
#include "untether_spp.h"
#include "esphome/core/log.h"

#include <algorithm>
#include <cstring>
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_gap_bt_api.h"
#include "esp_spp_api.h"
#include "lwip/sockets.h"

namespace esphome {
namespace untether_spp {

static const char *const TAG = "untether_spp";
static const size_t RB_SIZE = 4096;             // per-device SPP -> TCP staging
static const size_t TCP_RX = 990;               // TCP -> SPP chunk (~RFCOMM MTU)
static const uint32_t CONNECT_TIMEOUT_MS = 12000;  // abandon a stuck connect/discovery, then retry

// Bluedroid callbacks are C-style with no user pointer, so route through a singleton.
static UntetherSpp *g_self = nullptr;

static void gap_cb(esp_bt_gap_cb_event_t event, esp_bt_gap_cb_param_t *param) {
  switch (event) {
    case ESP_BT_GAP_AUTH_CMPL_EVT:
      ESP_LOGI(TAG, "GAP auth %s", param->auth_cmpl.stat == ESP_BT_STATUS_SUCCESS ? "ok" : "FAIL");
      break;
    case ESP_BT_GAP_CFM_REQ_EVT:  // just-works: auto-accept the numeric comparison
      esp_bt_gap_ssp_confirm_reply(param->cfm_req.bda, true);
      break;
    default:
      break;
  }
}

static void spp_cb(esp_spp_cb_event_t event, esp_spp_cb_param_t *param) {
  if (g_self != nullptr) g_self->on_spp_event(event, param);
}

void UntetherSpp::add_device(uint8_t b0, uint8_t b1, uint8_t b2, uint8_t b3, uint8_t b4, uint8_t b5,
                             uint8_t channel, uint16_t tcp_port, const std::vector<uint8_t> &on_open) {
  auto d = std::unique_ptr<SppDevice>(new SppDevice());
  d->target[0] = b0; d->target[1] = b1; d->target[2] = b2;
  d->target[3] = b3; d->target[4] = b4; d->target[5] = b5;
  d->channel = channel;
  d->tcp_port = tcp_port;
  d->on_open = on_open;
  this->devices_.push_back(std::move(d));
}

SppDevice *UntetherSpp::by_handle_(uint32_t handle) {
  for (auto &d : this->devices_)
    if (d->spp_open && d->spp_handle == handle)
      return d.get();
  return nullptr;
}

SppDevice *UntetherSpp::by_bda_(const esp_bd_addr_t bda) {
  for (auto &d : this->devices_)
    if (memcmp(d->target, bda, sizeof(esp_bd_addr_t)) == 0)
      return d.get();
  return nullptr;
}

void UntetherSpp::on_spp_event(esp_spp_cb_event_t event, esp_spp_cb_param_t *param) {
  switch (event) {
    case ESP_SPP_INIT_EVT:
      ESP_LOGCONFIG(TAG, "SPP init; %u device(s) queued", (unsigned) this->devices_.size());
      this->spp_ready_ = true;
      for (auto &d : this->devices_)
        d->want_reconnect = true;  // loop() initiates connects (keeps them off the cb thread)
      break;

    case ESP_SPP_DISCOVERY_COMP_EVT: {
      // DISCOVERY_COMP carries no BD_ADDR, so it belongs to the (serialized) connecting device.
      if (this->connecting_idx_ < 0 || this->connecting_idx_ >= (int) this->devices_.size())
        break;
      SppDevice &d = *this->devices_[this->connecting_idx_];
      if (param->disc_comp.status == ESP_SPP_SUCCESS && param->disc_comp.scn_num > 0) {
        d.channel = param->disc_comp.scn[0];
        ESP_LOGI(TAG, "[:%u] SDP found SPP on channel %u", d.tcp_port, d.channel);
        this->connect_started_ = millis();  // give the connect its own timeout budget
        esp_spp_connect(ESP_SPP_SEC_NONE, ESP_SPP_ROLE_MASTER, d.channel, d.target);
      } else {
        ESP_LOGW(TAG, "[:%u] SDP discovery failed (status %d)", d.tcp_port, param->disc_comp.status);
        d.want_reconnect = true;
        this->connecting_idx_ = -1;
      }
      break;
    }

    case ESP_SPP_OPEN_EVT: {
      SppDevice *d = this->by_bda_(param->open.rem_bda);
      if (param->open.status != ESP_SPP_SUCCESS) {
        ESP_LOGW(TAG, "SPP open failed (status %d)", param->open.status);
        if (d != nullptr) d->want_reconnect = true;
      } else if (d != nullptr) {
        d->spp_handle = param->open.handle;
        d->spp_open = true;
        d->spp_congested = false;
        d->backoff_ms = 1000;
        d->open_at = millis();
        d->pending_on_open = !d->on_open.empty();
        ESP_LOGI(TAG, "[:%u] SPP OPEN (handle %u) — bridge live", d->tcp_port,
                 (unsigned) d->spp_handle);
      } else {
        ESP_LOGW(TAG, "SPP OPEN for unconfigured device; ignoring");
      }
      this->connecting_idx_ = -1;  // this attempt is resolved
      break;
    }

    case ESP_SPP_CLOSE_EVT: {
      SppDevice *d = this->by_handle_(param->close.handle);
      if (d != nullptr) {
        d->spp_open = false;
        d->spp_handle = 0;
        d->want_reconnect = true;
        ESP_LOGW(TAG, "[:%u] SPP CLOSE — will reconnect", d->tcp_port);
      }
      // A failed connect can close before any OPEN (no matching handle); the loop() timeout
      // clears connecting_idx_ in that case.
      break;
    }

    case ESP_SPP_CONG_EVT: {
      SppDevice *d = this->by_handle_(param->cong.handle);
      if (d != nullptr) d->spp_congested = param->cong.cong;
      break;
    }

    case ESP_SPP_DATA_IND_EVT: {  // device -> us; stage for that device's TCP client
      SppDevice *d = this->by_handle_(param->data_ind.handle);
      if (d != nullptr && d->rb_in != nullptr && param->data_ind.len > 0) {
        if (xRingbufferSend(d->rb_in, param->data_ind.data, param->data_ind.len, 0) != pdTRUE)
          ESP_LOGW(TAG, "[:%u] rb_in full, dropped %d bytes", d->tcp_port, param->data_ind.len);
      }
      break;
    }

    case ESP_SPP_WRITE_EVT: {
      SppDevice *d = this->by_handle_(param->write.handle);
      if (d != nullptr && param->write.cong) d->spp_congested = true;
      break;
    }

    default:
      break;
  }
}

void UntetherSpp::manage_connections_() {
  if (!this->spp_ready_) return;
  const uint32_t now = millis();

  // One connect/discovery outstanding at a time (DISCOVERY_COMP has no BD_ADDR to attribute).
  if (this->connecting_idx_ >= 0) {
    if (now - this->connect_started_ > CONNECT_TIMEOUT_MS) {
      if (this->connecting_idx_ < (int) this->devices_.size()) {
        SppDevice &d = *this->devices_[this->connecting_idx_];
        ESP_LOGW(TAG, "[:%u] connect timed out; will retry", d.tcp_port);
        d.want_reconnect = true;
      }
      this->connecting_idx_ = -1;
    }
    return;  // wait for the current attempt (or its timeout) before starting another
  }

  for (size_t i = 0; i < this->devices_.size(); i++) {
    SppDevice &d = *this->devices_[i];
    if (d.spp_open || !d.want_reconnect) continue;
    if (now - d.last_attempt < d.backoff_ms) continue;
    d.last_attempt = now;
    d.want_reconnect = false;
    this->connecting_idx_ = (int) i;
    this->connect_started_ = now;
    d.backoff_ms = std::min<uint32_t>(d.backoff_ms * 2, 15000);  // capped backoff
    if (d.channel > 0) {
      ESP_LOGI(TAG, "[:%u] connecting SPP ch %u …", d.tcp_port, d.channel);
      esp_spp_connect(ESP_SPP_SEC_NONE, ESP_SPP_ROLE_MASTER, d.channel, d.target);
    } else {
      ESP_LOGI(TAG, "[:%u] SDP-discovering SPP channel …", d.tcp_port);
      esp_spp_start_discovery(d.target);
    }
    break;  // only one at a time
  }
}

void UntetherSpp::send_on_open_(SppDevice &d) {
  // Fire the optional handshake once, ~300ms after the link opens (some modules drop writes sent
  // the instant SPP comes up). Runs in loop(), so esp_spp_write stays off the BT callback thread.
  if (!d.pending_on_open || !d.spp_open || d.spp_congested) return;
  if (millis() - d.open_at < 300) return;
  d.pending_on_open = false;
  esp_spp_write(d.spp_handle, d.on_open.size(), const_cast<uint8_t *>(d.on_open.data()));
  ESP_LOGI(TAG, "[:%u] sent on_open handshake (%u bytes)", d.tcp_port, (unsigned) d.on_open.size());
}

void UntetherSpp::tcp_setup_(SppDevice &d) {
  d.listen_fd = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (d.listen_fd < 0) { ESP_LOGE(TAG, "[:%u] listen socket failed", d.tcp_port); return; }
  int one = 1;
  setsockopt(d.listen_fd, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
  fcntl(d.listen_fd, F_SETFL, fcntl(d.listen_fd, F_GETFL) | O_NONBLOCK);
  struct sockaddr_in addr = {};
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = htonl(INADDR_ANY);
  addr.sin_port = htons(d.tcp_port);
  if (::bind(d.listen_fd, (struct sockaddr *) &addr, sizeof(addr)) < 0 ||
      ::listen(d.listen_fd, 1) < 0) {
    ESP_LOGE(TAG, "[:%u] bind/listen failed", d.tcp_port);
    ::close(d.listen_fd);
    d.listen_fd = -1;
    return;
  }
  ESP_LOGCONFIG(TAG, "[:%u] TCP bridge listening", d.tcp_port);
}

void UntetherSpp::tcp_service_(SppDevice &d) {
  if (d.listen_fd < 0) { this->tcp_setup_(d); return; }

  // Accept one client (non-blocking).
  if (d.client_fd < 0) {
    int fd = ::accept(d.listen_fd, nullptr, nullptr);
    if (fd >= 0) {
      fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
      int one = 1;
      setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
      d.client_fd = fd;
      ESP_LOGI(TAG, "[:%u] TCP client connected", d.tcp_port);
    }
    return;
  }

  // SPP -> TCP: drain the ring buffer to the client.
  size_t item_size = 0;
  while (true) {
    void *item = xRingbufferReceive(d.rb_in, &item_size, 0);
    if (item == nullptr) break;
    int sent = ::send(d.client_fd, item, item_size, 0);
    vRingbufferReturnItem(d.rb_in, item);
    if (sent < 0) {
      if (errno != EWOULDBLOCK && errno != EAGAIN) {
        ESP_LOGW(TAG, "[:%u] client send err %d, dropping client", d.tcp_port, errno);
        ::close(d.client_fd);
        d.client_fd = -1;
      }
      break;
    }
  }
  if (d.client_fd < 0) return;

  // TCP -> SPP: forward client bytes to the device.
  if (d.spp_open && !d.spp_congested) {
    uint8_t buf[TCP_RX];
    int n = ::recv(d.client_fd, buf, sizeof(buf), 0);
    if (n > 0) {
      if (esp_spp_write(d.spp_handle, n, buf) != ESP_OK) d.spp_congested = true;
    } else if (n == 0) {
      ESP_LOGI(TAG, "[:%u] TCP client closed", d.tcp_port);
      ::close(d.client_fd);
      d.client_fd = -1;
    } else if (errno != EWOULDBLOCK && errno != EAGAIN) {
      ESP_LOGW(TAG, "[:%u] client recv err %d", d.tcp_port, errno);
      ::close(d.client_fd);
      d.client_fd = -1;
    }
  } else {
    // SPP down or congested: detect a departed client (EOF) WITHOUT consuming its bytes, so a
    // stuck/congested link can never wedge the TCP server (unread data stays buffered = client
    // backpressure; the slot is freed the instant the client actually leaves).
    uint8_t probe;
    int n = ::recv(d.client_fd, &probe, 1, MSG_PEEK);
    if (n == 0) {
      ESP_LOGI(TAG, "[:%u] TCP client closed (spp down/congested)", d.tcp_port);
      ::close(d.client_fd);
      d.client_fd = -1;
    } else if (n < 0 && errno != EWOULDBLOCK && errno != EAGAIN) {
      ::close(d.client_fd);
      d.client_fd = -1;
    }
  }
}

void UntetherSpp::setup() {
  g_self = this;
  if (this->devices_.empty()) {
    ESP_LOGE(TAG, "no devices configured");
    this->mark_failed();
    return;
  }
  for (auto &d : this->devices_) {
    d->rb_in = xRingbufferCreate(RB_SIZE, RINGBUF_TYPE_BYTEBUF);
    if (d->rb_in == nullptr) {
      ESP_LOGE(TAG, "ring buffer alloc failed");
      this->mark_failed();
      return;
    }
  }

  esp_bt_controller_config_t cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  if (esp_bt_controller_init(&cfg) != ESP_OK ||
      esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT) != ESP_OK ||
      esp_bluedroid_init() != ESP_OK || esp_bluedroid_enable() != ESP_OK) {
    ESP_LOGE(TAG, "Bluetooth Classic init failed");
    this->mark_failed();
    return;
  }
  esp_bt_gap_set_device_name(this->device_name_.c_str());
  esp_bt_gap_register_callback(gap_cb);

  // Just-works SSP (no PIN/IO) — matches the finicky vendor modules.
  esp_bt_io_cap_t iocap = ESP_BT_IO_CAP_NONE;
  esp_bt_gap_set_security_param(ESP_BT_SP_IOCAP_MODE, &iocap, sizeof(iocap));
  esp_bt_gap_set_scan_mode(ESP_BT_NON_CONNECTABLE, ESP_BT_NON_DISCOVERABLE);

  esp_spp_register_callback(spp_cb);
  esp_spp_cfg_t spp_cfg = {};
  spp_cfg.mode = ESP_SPP_MODE_CB;
  spp_cfg.enable_l2cap_ertm = false;  // ERTM off for finicky modules
  spp_cfg.tx_buffer_size = 0;
  if (esp_spp_enhanced_init(&spp_cfg) != ESP_OK) {
    ESP_LOGE(TAG, "esp_spp_enhanced_init failed");
    this->mark_failed();
    return;
  }
  // ESP_SPP_INIT_EVT -> loop() initiates the connects. TCP listeners come up lazily in loop().
}

void UntetherSpp::loop() {
  this->manage_connections_();
  for (auto &d : this->devices_) {
    this->send_on_open_(*d);
    this->tcp_service_(*d);
  }
}

void UntetherSpp::dump_config() {
  ESP_LOGCONFIG(TAG, "untether_spp (Classic SPP <-> TCP bridge, %u device(s)):",
                (unsigned) this->devices_.size());
  for (auto &d : this->devices_) {
    ESP_LOGCONFIG(TAG, "  - %02X:%02X:%02X:%02X:%02X:%02X  ch %u%s  ->  tcp :%u  [%s]",
                  d->target[0], d->target[1], d->target[2], d->target[3], d->target[4], d->target[5],
                  d->channel, d->channel == 0 ? " (SDP)" : "", d->tcp_port,
                  d->spp_open ? "open" : "down");
  }
}

}  // namespace untether_spp
}  // namespace esphome
#endif  // USE_ESP32
