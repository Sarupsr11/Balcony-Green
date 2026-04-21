/*
 * Balcony Green – ESP32-CAM Leaf Detection
 *
 * Board  : AI Thinker ESP32-CAM (OV2640)
 * Flash  : 4 MB (via UART programmer; IO0 → GND while uploading)
 *
 * What this does:
 *  1. Connects to WiFi and prints its IP on Serial.
 *  2. Serves /capture  → single JPEG snapshot (use this as BALCONYGREEN_CAMERA_URL)
 *  3. Serves /stream   → MJPEG live stream
 *  4. Serves /         → status page with a live preview
 *  5. Every 30 s it tells the backend API that a new image is available so the
 *     dashboard can run the disease-detection AI model on it.
 *
 * Dashboard setup (after flashing):
 *   1. Open the Balcony Green Streamlit app.
 *   2. In the camera input, choose "External HTTP Camera".
 *   3. Set the snapshot URL to  http://<IP_SHOWN_IN_SERIAL>/capture
 *      (or set env var  BALCONYGREEN_CAMERA_URL=http://<IP>/capture)
 */

#include <WiFi.h>
#include <WebServer.h>
#include <esp_camera.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

// ---------------------------------------------------------------------------
// WiFi
// ---------------------------------------------------------------------------
const char* WIFI_SSID     = "Myphone";
const char* WIFI_PASSWORD = "12345678";

// ---------------------------------------------------------------------------
// Backend API  (same values as the water-now demo)
// ---------------------------------------------------------------------------
const char* API_BASE_URL = "http://10.182.74.54:8000";
const char* JWT_TOKEN    =
  "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9"
  ".eyJzdWIiOiJkNzNiZjcyNC05MWQ1LTQyYWQt"
  "YTJhNi00ZWM4NzdiMWMzZjgiLCJleHAiOjE3"
  "NzYxNDgyMzB9.4fHvPCkyvh7f9mQAvETF1nUw"
  "wnwUOYlm3Jis76WgYIc";

// How often to notify the backend that a fresh image is ready (ms)
const unsigned long NOTIFY_INTERVAL_MS = 30000UL;

// ---------------------------------------------------------------------------
// AI Thinker ESP32-CAM pin map (OV2640)
// ---------------------------------------------------------------------------
#define PWDN_GPIO_NUM   32
#define RESET_GPIO_NUM  -1
#define XCLK_GPIO_NUM    0
#define SIOD_GPIO_NUM   26
#define SIOC_GPIO_NUM   27
#define Y9_GPIO_NUM     35
#define Y8_GPIO_NUM     34
#define Y7_GPIO_NUM     39
#define Y6_GPIO_NUM     36
#define Y5_GPIO_NUM     21
#define Y4_GPIO_NUM     19
#define Y3_GPIO_NUM     18
#define Y2_GPIO_NUM      5
#define VSYNC_GPIO_NUM  25
#define HREF_GPIO_NUM   23
#define PCLK_GPIO_NUM   22

// Onboard flash LED (active LOW on AI Thinker)
#define FLASH_LED_PIN   4

// ---------------------------------------------------------------------------
// Globals
// ---------------------------------------------------------------------------
WebServer server(80);
unsigned long lastNotifyMs = 0;
String  myIP;

// ---------------------------------------------------------------------------
// Helpers
// ---------------------------------------------------------------------------
String authHeader() {
  return String("Bearer ") + JWT_TOKEN;
}

// Capture one frame and return the buffer. Caller must esp_camera_fb_return(fb).
camera_fb_t* captureFrame() {
  camera_fb_t* fb = esp_camera_fb_get();
  if (!fb) {
    Serial.println("[CAM] Capture failed");
  }
  return fb;
}

// ---------------------------------------------------------------------------
// Camera init
// ---------------------------------------------------------------------------
bool initCamera() {
  camera_config_t config;
  config.ledc_channel = LEDC_CHANNEL_0;
  config.ledc_timer   = LEDC_TIMER_0;
  config.pin_d0       = Y2_GPIO_NUM;
  config.pin_d1       = Y3_GPIO_NUM;
  config.pin_d2       = Y4_GPIO_NUM;
  config.pin_d3       = Y5_GPIO_NUM;
  config.pin_d4       = Y6_GPIO_NUM;
  config.pin_d5       = Y7_GPIO_NUM;
  config.pin_d6       = Y8_GPIO_NUM;
  config.pin_d7       = Y9_GPIO_NUM;
  config.pin_xclk     = XCLK_GPIO_NUM;
  config.pin_pclk     = PCLK_GPIO_NUM;
  config.pin_vsync    = VSYNC_GPIO_NUM;
  config.pin_href     = HREF_GPIO_NUM;
  config.pin_sscb_sda = SIOD_GPIO_NUM;
  config.pin_sscb_scl = SIOC_GPIO_NUM;
  config.pin_pwdn     = PWDN_GPIO_NUM;
  config.pin_reset    = RESET_GPIO_NUM;
  config.xclk_freq_hz = 20000000;
  config.pixel_format = PIXFORMAT_JPEG;

  // Use UXGA (1600×1200) if PSRAM is present, else VGA (640×480)
  if (psramFound()) {
    config.frame_size   = FRAMESIZE_UXGA;
    config.jpeg_quality = 10;  // 0–63; lower = higher quality
    config.fb_count     = 2;
  } else {
    config.frame_size   = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count     = 1;
  }

  esp_err_t err = esp_camera_init(&config);
  if (err != ESP_OK) {
    Serial.printf("[CAM] Init failed: 0x%x\n", err);
    return false;
  }

  // Flip image if leaves are upside-down (comment out if not needed)
  sensor_t* s = esp_camera_sensor_get();
  s->set_vflip(s, 1);
  s->set_hmirror(s, 0);

  Serial.println("[CAM] OV2640 ready");
  return true;
}

// ---------------------------------------------------------------------------
// HTTP handlers
// ---------------------------------------------------------------------------

// GET /capture  – returns a single JPEG frame
void handleCapture() {
  camera_fb_t* fb = captureFrame();
  if (!fb) {
    server.send(500, "text/plain", "Camera capture failed");
    return;
  }

  server.sendHeader("Access-Control-Allow-Origin", "*");
  server.sendHeader("Cache-Control", "no-store");
  server.send_P(200, "image/jpeg",
                reinterpret_cast<const char*>(fb->buf),
                fb->len);
  esp_camera_fb_return(fb);
  Serial.println("[HTTP] /capture served");
}

// GET /stream  – MJPEG stream
void handleStream() {
  WiFiClient client = server.client();

  // Send multipart header
  client.println("HTTP/1.1 200 OK");
  client.println("Content-Type: multipart/x-mixed-replace; boundary=frame");
  client.println("Access-Control-Allow-Origin: *");
  client.println("Cache-Control: no-store");
  client.println();

  Serial.println("[HTTP] /stream started");

  while (client.connected()) {
    camera_fb_t* fb = captureFrame();
    if (!fb) {
      break;
    }

    client.printf(
      "--frame\r\n"
      "Content-Type: image/jpeg\r\n"
      "Content-Length: %u\r\n\r\n",
      fb->len
    );
    client.write(fb->buf, fb->len);
    client.print("\r\n");
    esp_camera_fb_return(fb);

    delay(50);  // ~20 fps cap
  }

  Serial.println("[HTTP] /stream ended");
}

// GET /  – status page with live preview
void handleRoot() {
  String html = R"rawhtml(<!DOCTYPE html>
<html>
<head>
  <meta charset="utf-8">
  <title>Balcony Green Camera</title>
  <style>
    body { font-family: sans-serif; background:#1a1a2e; color:#eee; text-align:center; padding:20px; }
    img  { max-width:100%; border:2px solid #00d4aa; border-radius:8px; margin-top:16px; }
    h1   { color:#00d4aa; }
    p    { margin:6px 0; }
    a    { color:#00d4aa; }
  </style>
</head>
<body>
  <h1>Balcony Green – Leaf Camera</h1>
  <p>IP: )rawhtml" + myIP + R"rawhtml(</p>
  <p>
    <a href="/capture">Single snapshot</a> &nbsp;|&nbsp;
    <a href="/stream">MJPEG stream</a>
  </p>
  <p>Set <code>BALCONYGREEN_CAMERA_URL=http://)rawhtml" + myIP + R"rawhtml(/capture</code> in your .env</p>
  <img src="/stream" alt="Live feed">
</body>
</html>)rawhtml";

  server.send(200, "text/html", html);
}

// ---------------------------------------------------------------------------
// Notify backend that a fresh image is available at our /capture URL
// ---------------------------------------------------------------------------
void notifyBackend() {
  if (WiFi.status() != WL_CONNECTED) return;

  String captureUrl = "http://" + myIP + "/capture";

  HTTPClient http;
  http.begin(String(API_BASE_URL) + "/image_uploads");
  http.addHeader("Authorization", authHeader());
  http.addHeader("Content-Type", "application/json");

  DynamicJsonDocument doc(256);
  doc["file_path"] = captureUrl;
  doc["file_type"] = "image/jpeg";
  doc["source"]    = "ESP32-CAM";

  String body;
  serializeJson(doc, body);

  int code = http.POST(body);
  http.end();

  if (code == 200) {
    Serial.println("[API] Backend notified – image URL logged");
  } else {
    Serial.printf("[API] Notify failed: HTTP %d\n", code);
  }
}

// ---------------------------------------------------------------------------
// WiFi
// ---------------------------------------------------------------------------
void connectWiFi() {
  Serial.printf("\n[WiFi] Connecting to %s", WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);

  int tries = 0;
  while (WiFi.status() != WL_CONNECTED && tries < 24) {
    delay(500);
    Serial.print(".");
    tries++;
  }

  if (WiFi.status() == WL_CONNECTED) {
    myIP = WiFi.localIP().toString();
    Serial.println("\n[WiFi] Connected!");
    Serial.println("==============================================");
    Serial.println("  Snapshot URL  : http://" + myIP + "/capture");
    Serial.println("  Stream URL    : http://" + myIP + "/stream");
    Serial.println("  Status page   : http://" + myIP + "/");
    Serial.println("==============================================");
    Serial.println("  Set in Streamlit: External HTTP Camera");
    Serial.println("  BALCONYGREEN_CAMERA_URL=http://" + myIP + "/capture");
    Serial.println("==============================================");
  } else {
    Serial.println("\n[WiFi] Failed – running without network");
  }
}

// ---------------------------------------------------------------------------
// Setup & Loop
// ---------------------------------------------------------------------------
void setup() {
  Serial.begin(115200);
  Serial.println("\n[BOOT] Balcony Green ESP32-CAM");

  pinMode(FLASH_LED_PIN, OUTPUT);
  digitalWrite(FLASH_LED_PIN, LOW);  // LED off (active LOW)

  if (!initCamera()) {
    Serial.println("[BOOT] Camera init failed – halting");
    while (true) { delay(1000); }
  }

  connectWiFi();

  server.on("/",        HTTP_GET, handleRoot);
  server.on("/capture", HTTP_GET, handleCapture);
  server.on("/stream",  HTTP_GET, handleStream);
  server.begin();
  Serial.println("[HTTP] Server started on port 80");
}

void loop() {
  // Reconnect if WiFi dropped
  if (WiFi.status() != WL_CONNECTED) {
    connectWiFi();
  }

  server.handleClient();

  // Periodic backend notification
  if (WiFi.status() == WL_CONNECTED &&
      millis() - lastNotifyMs >= NOTIFY_INTERVAL_MS) {
    lastNotifyMs = millis();
    notifyBackend();
  }
}
