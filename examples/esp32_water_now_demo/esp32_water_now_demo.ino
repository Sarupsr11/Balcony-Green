#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

const char* WIFI_SSID = "YOUR_WIFI_NAME";
const char* WIFI_PASSWORD = "YOUR_WIFI_PASSWORD";
const char* API_BASE_URL = "http://192.168.1.10:8000";
const char* JWT_TOKEN = "PASTE_USER_JWT_HERE";
const char* DEVICE_ID = "esp32-balcony-1";

const int RELAY_PIN = 26;
const int SOIL_SENSOR_PIN = 34;
const int SOIL_RAW_DRY = 3200;
const int SOIL_RAW_WET = 1200;
const float OFFLINE_MOISTURE_THRESHOLD_PCT = 32.0;
const int OFFLINE_PUMP_MS = 2500;

const unsigned long POLL_INTERVAL_MS = 5000;
const unsigned long TELEMETRY_INTERVAL_MS = 30000;
const unsigned long OFFLINE_COOLDOWN_MS = 60UL * 60UL * 1000UL;

unsigned long lastPollMs = 0;
unsigned long lastTelemetryMs = 0;
unsigned long lastWaterMs = 0;

String authHeader() {
  return String("Bearer ") + JWT_TOKEN;
}

void connectWifi() {
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 12000) {
    delay(500);
  }
}

int readSoilRaw() {
  return analogRead(SOIL_SENSOR_PIN);
}

float rawToMoisturePct(int rawValue) {
  float span = float(SOIL_RAW_DRY - SOIL_RAW_WET);
  if (span <= 1.0) {
    return 0.0;
  }
  float moisture = ((SOIL_RAW_DRY - rawValue) * 100.0) / span;
  if (moisture < 0.0) {
    return 0.0;
  }
  if (moisture > 100.0) {
    return 100.0;
  }
  return moisture;
}

void runPump(int pumpMs) {
  digitalWrite(RELAY_PIN, LOW);
  delay(pumpMs);
  digitalWrite(RELAY_PIN, HIGH);
  lastWaterMs = millis();
}

void postReading(const char* sensorName, float value) {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  HTTPClient http;
  String url = String(API_BASE_URL) + "/user_sensors";
  http.begin(url);
  http.addHeader("Authorization", authHeader());
  http.addHeader("Content-Type", "application/json");

  DynamicJsonDocument doc(512);
  doc["sensor_name"] = sensorName;
  doc["value"] = value;
  doc["source"] = "ESP32 Telemetry";
  doc["device_id"] = DEVICE_ID;

  String body;
  serializeJson(doc, body);
  http.POST(body);
  http.end();
}

void postTelemetry() {
  int soilRaw = readSoilRaw();
  float soilMoisture = rawToMoisturePct(soilRaw);
  postReading("soil_raw", soilRaw);
  postReading("soil_moisture", soilMoisture);
}

bool fetchNextCommand(String& commandId, int& pumpMs) {
  if (WiFi.status() != WL_CONNECTED) {
    return false;
  }

  HTTPClient http;
  String url = String(API_BASE_URL) + "/devices/" + DEVICE_ID + "/next_command";
  http.begin(url);
  http.addHeader("Authorization", authHeader());

  int statusCode = http.GET();
  if (statusCode != 200) {
    http.end();
    return false;
  }

  DynamicJsonDocument doc(2048);
  DeserializationError err = deserializeJson(doc, http.getString());
  http.end();
  if (err) {
    return false;
  }

  if (String((const char*)doc["status"]) != "ok") {
    return false;
  }

  JsonObject command = doc["command"];
  if (String((const char*)command["command_type"]) != "water_now") {
    return false;
  }

  commandId = String((const char*)command["id"]);
  pumpMs = int(command["payload"]["pump_ms"] | 0);
  return pumpMs > 0;
}

void acknowledgeCommand(const String& commandId, const char* status, const char* message) {
  if (WiFi.status() != WL_CONNECTED) {
    return;
  }

  HTTPClient http;
  String url = String(API_BASE_URL) + "/devices/" + DEVICE_ID + "/ack_command";
  http.begin(url);
  http.addHeader("Authorization", authHeader());
  http.addHeader("Content-Type", "application/json");

  DynamicJsonDocument doc(512);
  doc["command_id"] = commandId;
  doc["status"] = status;
  doc["message"] = message;

  String body;
  serializeJson(doc, body);
  http.POST(body);
  http.end();
}

void offlineFallbackWatering() {
  float soilMoisture = rawToMoisturePct(readSoilRaw());
  bool cooldownReady = millis() - lastWaterMs >= OFFLINE_COOLDOWN_MS;

  if (soilMoisture <= OFFLINE_MOISTURE_THRESHOLD_PCT && cooldownReady) {
    runPump(OFFLINE_PUMP_MS);
  }
}

void setup() {
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH);
  Serial.begin(115200);
  connectWifi();
}

void loop() {
  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  }

  if (WiFi.status() == WL_CONNECTED && millis() - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMs = millis();
    postTelemetry();
  }

  bool commandExecuted = false;
  if (WiFi.status() == WL_CONNECTED && millis() - lastPollMs >= POLL_INTERVAL_MS) {
    lastPollMs = millis();

    String commandId;
    int pumpMs = 0;
    if (fetchNextCommand(commandId, pumpMs)) {
      runPump(pumpMs);
      postTelemetry();
      acknowledgeCommand(commandId, "executed", "Relay executed water_now successfully");
      commandExecuted = true;
    }
  }

  if (!commandExecuted && WiFi.status() != WL_CONNECTED) {
    offlineFallbackWatering();
  }
}
