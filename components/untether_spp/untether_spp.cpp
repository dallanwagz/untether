#ifdef USE_ESP32
#include "untether_spp.h"
#include "esphome/core/log.h"

#include <cstring>
#include "esp_bt.h"
#include "esp_bt_main.h"
#include "esp_bt_device.h"
#include "esp_gap_bt_api.h"
#include "esp_spp_api.h"
#include "lwip/sockets.h"

namespace esphome {
namespace untether_spp {

static const char *const TAG = "untether_spp";
static const size_t RB_SIZE = 4096;     // SPP -> TCP staging
static const size_t TCP_RX = 990;       // TCP -> SPP chunk (~RFCOMM MTU)

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
    case ESP_BT_GAP_KEY_NOTIF_EVT:
    case ESP_BT_GAP_KEY_REQ_EVT:
    default:
      break;
  }
}

static void spp_cb(esp_spp_cb_event_t event, esp_spp_cb_param_t *param) {
  if (g_self != nullptr) g_self->on_spp_event(event, param);
}

void UntetherSpp::on_spp_event(esp_spp_cb_event_t event, esp_spp_cb_param_t *param) {
  switch (event) {
    case ESP_SPP_INIT_EVT:
      ESP_LOGCONFIG(TAG, "SPP init; connecting to target");
      this->want_reconnect_ = true;  // loop() will initiate (keeps connect off the cb thread)
      break;
    case ESP_SPP_DISCOVERY_COMP_EVT:
      if (param->disc_comp.status == ESP_SPP_SUCCESS && param->disc_comp.scn_num > 0) {
        this->channel_ = param->disc_comp.scn[0];
        ESP_LOGI(TAG, "SDP found SPP on channel %u", this->channel_);
        esp_spp_connect(ESP_SPP_SEC_NONE, ESP_SPP_ROLE_MASTER, this->channel_, this->target_);
      } else {
        ESP_LOGW(TAG, "SDP discovery failed (status %d)", param->disc_comp.status);
        this->want_reconnect_ = true;
      }
      break;
    case ESP_SPP_OPEN_EVT:
      this->spp_handle_ = param->open.handle;
      this->spp_open_ = true;
      this->spp_congested_ = false;
      this->backoff_ms_ = 1000;
      ESP_LOGI(TAG, "SPP OPEN (handle %u) — bridge live", (unsigned) this->spp_handle_);
      break;
    case ESP_SPP_CLOSE_EVT:
      this->spp_open_ = false;
      this->spp_handle_ = 0;
      this->want_reconnect_ = true;
      ESP_LOGW(TAG, "SPP CLOSE — will reconnect");
      break;
    case ESP_SPP_CONG_EVT:
      this->spp_congested_ = param->cong.cong;
      break;
    case ESP_SPP_DATA_IND_EVT:  // device -> us; stage for the TCP client
      if (this->rb_in_ != nullptr && param->data_ind.len > 0) {
        if (xRingbufferSend(this->rb_in_, param->data_ind.data, param->data_ind.len, 0) != pdTRUE)
          ESP_LOGW(TAG, "rb_in full, dropped %d bytes", param->data_ind.len);
      }
      break;
    case ESP_SPP_WRITE_EVT:
      if (param->write.cong) this->spp_congested_ = true;
      break;
    default:
      break;
  }
}

void UntetherSpp::try_connect_spp_() {
  const uint32_t now = millis();
  if (this->spp_open_ || !this->want_reconnect_) return;
  if (now - this->last_connect_attempt_ < this->backoff_ms_) return;
  this->last_connect_attempt_ = now;
  this->want_reconnect_ = false;
  if (this->channel_ > 0) {
    ESP_LOGI(TAG, "connecting SPP ch %u …", this->channel_);
    esp_spp_connect(ESP_SPP_SEC_NONE, ESP_SPP_ROLE_MASTER, this->channel_, this->target_);
  } else {
    ESP_LOGI(TAG, "SDP-discovering SPP channel …");
    esp_spp_start_discovery(this->target_);
  }
  this->backoff_ms_ = std::min<uint32_t>(this->backoff_ms_ * 2, 15000);  // capped backoff
}

void UntetherSpp::setup() {
  g_self = this;
  this->rb_in_ = xRingbufferCreate(RB_SIZE, RINGBUF_TYPE_BYTEBUF);
  if (this->rb_in_ == nullptr) { this->mark_failed(); return; }

  esp_bt_controller_config_t cfg = BT_CONTROLLER_INIT_CONFIG_DEFAULT();
  if (esp_bt_controller_init(&cfg) != ESP_OK ||
      esp_bt_controller_enable(ESP_BT_MODE_CLASSIC_BT) != ESP_OK ||
      esp_bluedroid_init() != ESP_OK || esp_bluedroid_enable() != ESP_OK) {
    ESP_LOGE(TAG, "Bluetooth Classic init failed");
    this->mark_failed();
    return;
  }
  esp_bt_dev_set_device_name(this->device_name_.c_str());
  esp_bt_gap_register_callback(gap_cb);

  // Just-works SSP (no PIN/IO) — matches the finicky vendor modules.
  esp_bt_io_cap_t iocap = ESP_BT_IO_CAP_NONE;
  esp_bt_gap_set_security_param(ESP_BT_SP_IOCAP_MODE, &iocap, sizeof(iocap));
  // We initiate; stay invisible/non-connectable as a peripheral.
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
  // ESP_SPP_INIT_EVT will fire -> loop() initiates the connect.
}

void UntetherSpp::tcp_setup_() {
  this->listen_fd_ = ::socket(AF_INET, SOCK_STREAM, IPPROTO_TCP);
  if (this->listen_fd_ < 0) { ESP_LOGE(TAG, "listen socket failed"); return; }
  int one = 1;
  setsockopt(this->listen_fd_, SOL_SOCKET, SO_REUSEADDR, &one, sizeof(one));
  fcntl(this->listen_fd_, F_SETFL, fcntl(this->listen_fd_, F_GETFL) | O_NONBLOCK);
  struct sockaddr_in addr = {};
  addr.sin_family = AF_INET;
  addr.sin_addr.s_addr = htonl(INADDR_ANY);
  addr.sin_port = htons(this->tcp_port_);
  if (::bind(this->listen_fd_, (struct sockaddr *) &addr, sizeof(addr)) < 0 ||
      ::listen(this->listen_fd_, 1) < 0) {
    ESP_LOGE(TAG, "bind/listen :%u failed", this->tcp_port_);
    ::close(this->listen_fd_);
    this->listen_fd_ = -1;
    return;
  }
  ESP_LOGCONFIG(TAG, "TCP bridge listening on :%u", this->tcp_port_);
}

void UntetherSpp::tcp_service_() {
  if (this->listen_fd_ < 0) { this->tcp_setup_(); return; }

  // Accept one client (non-blocking).
  if (this->client_fd_ < 0) {
    int fd = ::accept(this->listen_fd_, nullptr, nullptr);
    if (fd >= 0) {
      fcntl(fd, F_SETFL, fcntl(fd, F_GETFL) | O_NONBLOCK);
      int one = 1;
      setsockopt(fd, IPPROTO_TCP, TCP_NODELAY, &one, sizeof(one));
      this->client_fd_ = fd;
      ESP_LOGI(TAG, "TCP client connected");
    }
    return;
  }

  // SPP -> TCP: drain the ring buffer to the client.
  size_t item_size = 0;
  while (true) {
    void *item = xRingbufferReceive(this->rb_in_, &item_size, 0);
    if (item == nullptr) break;
    int sent = ::send(this->client_fd_, item, item_size, 0);
    vRingbufferReturnItem(this->rb_in_, item);
    if (sent < 0) {
      if (errno != EWOULDBLOCK && errno != EAGAIN) {
        ESP_LOGW(TAG, "client send err %d, dropping client", errno);
        ::close(this->client_fd_);
        this->client_fd_ = -1;
      }
      break;  // back off this iteration
    }
  }

  // TCP -> SPP: forward client bytes to the device.
  if (this->client_fd_ >= 0 && this->spp_open_ && !this->spp_congested_) {
    uint8_t buf[TCP_RX];
    int n = ::recv(this->client_fd_, buf, sizeof(buf), 0);
    if (n > 0) {
      esp_spp_write(this->spp_handle_, n, buf);
    } else if (n == 0) {
      ESP_LOGI(TAG, "TCP client closed");
      ::close(this->client_fd_);
      this->client_fd_ = -1;
    } else if (errno != EWOULDBLOCK && errno != EAGAIN) {
      ESP_LOGW(TAG, "client recv err %d", errno);
      ::close(this->client_fd_);
      this->client_fd_ = -1;
    }
  }
}

void UntetherSpp::loop() {
  this->try_connect_spp_();
  this->tcp_service_();
}

void UntetherSpp::dump_config() {
  ESP_LOGCONFIG(TAG, "untether_spp (Classic SPP <-> TCP bridge):");
  ESP_LOGCONFIG(TAG, "  Target: %02X:%02X:%02X:%02X:%02X:%02X", target_[0], target_[1], target_[2],
                target_[3], target_[4], target_[5]);
  if (this->channel_ > 0)
    ESP_LOGCONFIG(TAG, "  RFCOMM channel: %u", this->channel_);
  else
    ESP_LOGCONFIG(TAG, "  RFCOMM channel: SDP-discover");
  ESP_LOGCONFIG(TAG, "  TCP port: %u", this->tcp_port_);
  ESP_LOGCONFIG(TAG, "  SPP open: %s", this->spp_open_ ? "yes" : "no");
}

}  // namespace untether_spp
}  // namespace esphome
#endif  // USE_ESP32
