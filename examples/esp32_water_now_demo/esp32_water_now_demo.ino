#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>
#include <Wire.h>
#include <Adafruit_GFX.h>
#include <Adafruit_SSD1306.h>
#include <DHT.h>
#include <time.h>

const char* WIFI_SSID = "Myphone";
const char* WIFI_PASSWORD = "12345678";
const char* API_BASE_URL = "http://172.27.137.65:8000";
const char* JWT_TOKEN = "eyJhbGciOiJIUzI1NiIsInR5cCI6IkpXVCJ9.eyJzdWIiOiJlODdiZjEwOS0zOTNhLTQwZGYtYTZiOS1lMzRhMGRhOTViMzEiLCJleHAiOjE3NzkwNDgyMjR9.cl7lSMkGkkse0kKDhpnw2dbontQxg9UjEQzqD7-YQ24";
const char* DEVICE_ID_OVERRIDE = "esp32";

const int RELAY_PIN = 26;
const int SOIL_SENSOR_PIN = 34;
const int DHT_PIN = 4;
const int OLED_SDA_PIN = 21;
const int OLED_SCL_PIN = 22;
const int LIGHT_SENSOR_SDA_PIN = 18;
const int LIGHT_SENSOR_SCL_PIN = 19;
const int SOIL_RAW_DRY = 3200;
const int SOIL_RAW_WET = 1200;
const float OFFLINE_MOISTURE_THRESHOLD_PCT = 32.0;
const int OFFLINE_PUMP_MS = 2500;

const unsigned long POLL_INTERVAL_MS = 5000;
const unsigned long TELEMETRY_INTERVAL_MS = 30000;
const unsigned long OFFLINE_COOLDOWN_MS = 60UL * 60UL * 1000UL;
const unsigned long DHT_MIN_INTERVAL_MS = 2500;
const unsigned long OLED_PAGE_INTERVAL_MS = 3500;
const unsigned long DISPLAY_REFRESH_INTERVAL_MS = 3000;
const unsigned long DISPLAY_KEEPALIVE_MS = 10000;
const unsigned long NTP_SYNC_TIMEOUT_MS = 8000;
const float ESTIMATED_PUMP_FLOW_ML_PER_SEC = 10.0f;
const bool DEMO_WATERING_ONLY = true;
const bool ROTATE_OLED_PAGES = false;
const size_t TELEMETRY_QUEUE_CAPACITY = 360;
const size_t MAX_TELEMETRY_FLUSH_PER_PASS = 8;

const uint8_t SCREEN_WIDTH = 128;
const uint8_t SCREEN_HEIGHT = 64;
const int OLED_RESET_PIN = -1;
const uint8_t OLED_I2C_ADDRESS = 0x3C;
const uint8_t OLED_I2C_ADDRESSES[] = {0x3C, 0x3D};
const uint8_t BH1750_I2C_ADDRESSES[] = {0x23, 0x5C};
const uint8_t BH1750_CONTINUOUS_HIGH_RES_MODE = 0x10;

Adafruit_SSD1306 display(SCREEN_WIDTH, SCREEN_HEIGHT, &Wire, OLED_RESET_PIN);
TwoWire lightWire = TwoWire(1);
DHT dht(DHT_PIN, DHT22);

struct TelemetrySample {
  time_t capturedEpoch = 0;
  int soilRaw = 0;
  float soilMoisture = 0.0f;
  float temperatureC = NAN;
  float humidityPct = NAN;
  float lightLux = NAN;
  bool hasTemperature = false;
  bool hasHumidity = false;
  bool hasLight = false;
};

String deviceId;
String shortDeviceName;
unsigned long lastPollMs = 0;
unsigned long lastTelemetryMs = 0;
unsigned long lastWaterMs = 0;
unsigned long lastDhtReadMs = 0;
unsigned long lastBackendSuccessMs = 0;
unsigned long lastSensorLogMs = 0;
unsigned long lastDisplayRefreshMs = 0;
unsigned long lastDisplayKeepaliveMs = 0;

int lastSoilRaw = 0;
float lastSoilMoisture = 0.0;
float lastTemperatureC = NAN;
float lastHumidityPct = NAN;
float lastLightLux = NAN;
bool displayAvailable = false;
bool lightSensorAvailable = false;
uint8_t oledAddress = OLED_I2C_ADDRESS;
int oledSdaPin = OLED_SDA_PIN;
int oledSclPin = OLED_SCL_PIN;
uint8_t lightSensorBus = 0;
uint8_t lightSensorAddress = 0;
int lightSensorSdaPin = -1;
int lightSensorSclPin = -1;
bool pumpActive = false;
String lastStatusLine = "Booting";
String backendStatusLine = "API init";
String lastCommandType = "None";
int lastCommandPumpMs = 0;
float lastWaterEstimateMl = 0.0;
String lastCommandResult = "Idle";
String lastCommandMessage = "No command";
unsigned long pumpStartedMs = 0;
unsigned long pumpTargetMs = 0;
String lastRenderedDisplayKey = "";
TelemetrySample telemetryQueue[TELEMETRY_QUEUE_CAPACITY];
size_t telemetryQueueHead = 0;
size_t telemetryQueueCount = 0;
unsigned long telemetryDroppedCount = 0;

void drawLine(uint8_t row, const String& text);

String authHeader() {
  return String("Bearer ") + JWT_TOKEN;
}

String getDeviceId() {
  String configuredDeviceId = String(DEVICE_ID_OVERRIDE);
  configuredDeviceId.trim();
  if (configuredDeviceId.length() > 0) {
    return configuredDeviceId;
  }

  uint64_t chipId = ESP.getEfuseMac();
  char buffer[32];
  snprintf(
    buffer,
    sizeof(buffer),
    "esp32-%04X%08X",
    uint16_t(chipId >> 32),
    uint32_t(chipId)
  );
  return String(buffer);
}

String getShortDeviceName() {
  int dashPos = deviceId.lastIndexOf('-');
  String suffix = dashPos >= 0 ? deviceId.substring(dashPos + 1) : deviceId;
  if (suffix.length() > 4) {
    suffix = suffix.substring(suffix.length() - 4);
  }
  return String("BG-") + suffix;
}

String getApiHost() {
  String host = API_BASE_URL;
  int schemePos = host.indexOf("://");
  if (schemePos >= 0) {
    host = host.substring(schemePos + 3);
  }

  int pathPos = host.indexOf('/');
  if (pathPos >= 0) {
    host = host.substring(0, pathPos);
  }
  return host;
}

String formatHexAddress(uint8_t value) {
  char buffer[8];
  snprintf(buffer, sizeof(buffer), "0x%02X", value);
  return String(buffer);
}

String clipText(const String& value, size_t maxLen) {
  if (value.length() <= maxLen) {
    return value;
  }
  if (maxLen <= 3) {
    return value.substring(0, maxLen);
  }
  return value.substring(0, maxLen - 3) + "...";
}

String formatTemperatureLine() {
  if (isnan(lastTemperatureC)) {
    return "Temp -- C";
  }
  return "Temp " + String(lastTemperatureC, 1) + " C";
}

String formatHumidityLine() {
  if (isnan(lastHumidityPct)) {
    return "Hum -- %";
  }
  return "Hum " + String(lastHumidityPct, 1) + " %";
}

String formatLightLine() {
  if (isnan(lastLightLux)) {
    return "Light -- lx";
  }
  return "Light " + String(lastLightLux, 0) + " lx";
}

String syncAgeLabel() {
  if (lastBackendSuccessMs == 0) {
    return "never";
  }

  unsigned long ageSeconds = (millis() - lastBackendSuccessMs) / 1000UL;
  if (ageSeconds < 90) {
    return String(ageSeconds) + "s ago";
  }

  return String(ageSeconds / 60UL) + "m ago";
}

float estimatedWaterMlForMs(unsigned long pumpMs) {
  return (pumpMs / 1000.0f) * ESTIMATED_PUMP_FLOW_ML_PER_SEC;
}

bool clockSynced() {
  return time(nullptr) > 1700000000;
}

void syncClock() {
  if (WiFi.status() != WL_CONNECTED || clockSynced()) {
    return;
  }

  configTime(0, 0, "pool.ntp.org", "time.nist.gov", "time.google.com");
  unsigned long startedMs = millis();
  while (!clockSynced() && millis() - startedMs < NTP_SYNC_TIMEOUT_MS) {
    delay(200);
  }

  Serial.println(clockSynced() ? "Clock sync ok" : "Clock sync pending");
}

String formatIsoTimestamp(time_t epoch) {
  if (epoch <= 0) {
    return "";
  }

  struct tm timeInfo;
  gmtime_r(&epoch, &timeInfo);
  char buffer[32];
  strftime(buffer, sizeof(buffer), "%Y-%m-%dT%H:%M:%SZ", &timeInfo);
  return String(buffer);
}

void enqueueTelemetrySample(const TelemetrySample& sample) {
  if (telemetryQueueCount >= TELEMETRY_QUEUE_CAPACITY) {
    telemetryQueueHead = (telemetryQueueHead + 1) % TELEMETRY_QUEUE_CAPACITY;
    telemetryQueueCount--;
    telemetryDroppedCount++;
  }

  size_t index = (telemetryQueueHead + telemetryQueueCount) % TELEMETRY_QUEUE_CAPACITY;
  telemetryQueue[index] = sample;
  telemetryQueueCount++;
}

TelemetrySample& peekTelemetrySample() {
  return telemetryQueue[telemetryQueueHead];
}

void popTelemetrySample() {
  if (telemetryQueueCount == 0) {
    return;
  }

  telemetryQueueHead = (telemetryQueueHead + 1) % TELEMETRY_QUEUE_CAPACITY;
  telemetryQueueCount--;
}

bool initDisplay() {
  const int oledPinPairs[][2] = {
    {OLED_SDA_PIN, OLED_SCL_PIN},
    {OLED_SCL_PIN, OLED_SDA_PIN},
  };

  for (uint8_t pinIndex = 0; pinIndex < 2; pinIndex++) {
    int sdaPin = oledPinPairs[pinIndex][0];
    int sclPin = oledPinPairs[pinIndex][1];

    Wire.end();
    Wire.begin(sdaPin, sclPin);
    delay(20);
    logI2CBusScan(Wire, pinIndex == 0 ? "OLED GPIO21/GPIO22" : "OLED GPIO22/GPIO21");

    for (uint8_t i = 0; i < sizeof(OLED_I2C_ADDRESSES); i++) {
      uint8_t candidateAddress = OLED_I2C_ADDRESSES[i];
      Wire.beginTransmission(candidateAddress);
      if (Wire.endTransmission() != 0) {
        continue;
      }

      if (display.begin(SSD1306_SWITCHCAPVCC, candidateAddress, true, false)) {
        oledAddress = candidateAddress;
        oledSdaPin = sdaPin;
        oledSclPin = sclPin;
        display.ssd1306_command(SSD1306_DISPLAYON);
        display.dim(false);
        display.clearDisplay();
        display.display();
        return true;
      }
    }
  }

  return false;
}

void wakeDisplay() {
  if (!displayAvailable) {
    return;
  }

  display.ssd1306_command(SSD1306_DISPLAYON);
  display.dim(false);
  lastDisplayKeepaliveMs = millis();
}

void showBootSplash() {
  if (!displayAvailable) {
    return;
  }

  wakeDisplay();
  display.clearDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextWrap(false);
  drawLine(0, "Balcony Green");
  drawLine(2, "OLED online");
  drawLine(3, "WiFi booting");
  drawLine(5, "Keep awake");
  display.display();
  delay(1200);
}

bool configureLightSensor(TwoWire& bus, uint8_t address) {
  bus.beginTransmission(address);
  bus.write(BH1750_CONTINUOUS_HIGH_RES_MODE);
  return bus.endTransmission() == 0;
}

void logI2CBusScan(TwoWire& bus, const char* label) {
  String found;
  for (uint8_t address = 1; address < 127; address++) {
    bus.beginTransmission(address);
    if (bus.endTransmission() == 0) {
      if (found.length() > 0) {
        found += ", ";
      }
      found += formatHexAddress(address);
    }
  }

  Serial.print("I2C scan ");
  Serial.print(label);
  Serial.print(": ");
  Serial.println(found.length() > 0 ? found : "none");
}

bool initBh1750OnBus(TwoWire& bus, uint8_t busId) {
  for (uint8_t i = 0; i < sizeof(BH1750_I2C_ADDRESSES); i++) {
    uint8_t address = BH1750_I2C_ADDRESSES[i];
    bus.beginTransmission(address);
    if (bus.endTransmission() == 0 && configureLightSensor(bus, address)) {
      lightSensorBus = busId;
      lightSensorAddress = address;
      delay(180);
      return true;
    }
  }
  return false;
}

bool initLightSensor() {
  lightWire.begin(LIGHT_SENSOR_SDA_PIN, LIGHT_SENSOR_SCL_PIN);
  logI2CBusScan(lightWire, "GPIO18/GPIO19");
  if (initBh1750OnBus(lightWire, 1)) {
    lightSensorSdaPin = LIGHT_SENSOR_SDA_PIN;
    lightSensorSclPin = LIGHT_SENSOR_SCL_PIN;
    return true;
  }

  lightWire.begin(LIGHT_SENSOR_SCL_PIN, LIGHT_SENSOR_SDA_PIN);
  logI2CBusScan(lightWire, "GPIO19/GPIO18");
  if (initBh1750OnBus(lightWire, 2)) {
    lightSensorSdaPin = LIGHT_SENSOR_SCL_PIN;
    lightSensorSclPin = LIGHT_SENSOR_SDA_PIN;
    return true;
  }

  Wire.begin(OLED_SDA_PIN, OLED_SCL_PIN);
  logI2CBusScan(Wire, "GPIO21/GPIO22");
  if (initBh1750OnBus(Wire, 3)) {
    lightSensorSdaPin = OLED_SDA_PIN;
    lightSensorSclPin = OLED_SCL_PIN;
    return true;
  }

  Wire.begin(OLED_SCL_PIN, OLED_SDA_PIN);
  logI2CBusScan(Wire, "GPIO22/GPIO21");
  if (initBh1750OnBus(Wire, 4)) {
    lightSensorSdaPin = OLED_SCL_PIN;
    lightSensorSclPin = OLED_SDA_PIN;
    return true;
  }

  lightSensorBus = 0;
  lightSensorAddress = 0;
  lightSensorSdaPin = -1;
  lightSensorSclPin = -1;
  return false;
}

void drawLine(uint8_t row, const String& text) {
  display.setCursor(0, row * 9);
  display.println(clipText(text, 21));
}

void updateDisplay(const String& statusLine) {
  if (!displayAvailable) {
    return;
  }

  String previousStatusLine = lastStatusLine;
  lastStatusLine = statusLine;
  unsigned long elapsedMs = 0;
  if (pumpActive) {
    elapsedMs = millis() - pumpStartedMs;
    if (elapsedMs > pumpTargetMs) {
      elapsedMs = pumpTargetMs;
    }
  }
  int pageIndex = ROTATE_OLED_PAGES ? int((millis() / OLED_PAGE_INTERVAL_MS) % 4UL) : 0;
  String wifiLabel = WiFi.status() == WL_CONNECTED ? "Connected" : "Offline";
  String renderKey =
    String(pageIndex) + "|" + statusLine + "|" + backendStatusLine + "|" + wifiLabel + "|" +
    String(lastSoilRaw) + "|" + String(lastSoilMoisture, 1) + "|" +
    String(lastTemperatureC, 1) + "|" + String(lastHumidityPct, 1) + "|" +
    String(lastLightLux, 0) + "|" + String(lastCommandPumpMs) + "|" +
    lastCommandResult + "|" + lastCommandMessage + "|" + String(elapsedMs / 100);
  if (!pumpActive && statusLine == previousStatusLine && millis() - lastDisplayRefreshMs < DISPLAY_REFRESH_INTERVAL_MS) {
    return;
  }
  if (renderKey == lastRenderedDisplayKey) {
    return;
  }
  lastRenderedDisplayKey = renderKey;
  lastDisplayRefreshMs = millis();

  display.clearDisplay();
  wakeDisplay();
  display.setTextColor(SSD1306_WHITE);
  display.setTextSize(1);
  display.setTextWrap(false);

  if (pumpActive) {
    drawLine(0, DEMO_WATERING_ONLY ? "WATERING DEMO" : "WATERING NOW");
    drawLine(1, "Name " + shortDeviceName);
    drawLine(2, DEMO_WATERING_ONLY ? "Mode simulated" : "Type " + lastCommandType);
    drawLine(3, "Time " + String(elapsedMs / 1000.0f, 1) + "/" + String(pumpTargetMs / 1000.0f, 1) + " s");
    drawLine(4, "Est " + String(estimatedWaterMlForMs(elapsedMs), 0) + " mL");
    drawLine(5, "Target " + String(lastWaterEstimateMl, 0) + " mL");
    drawLine(6, "State " + statusLine);
    display.display();
    return;
  }

  if (pageIndex == 0) {
    drawLine(0, "Sensors Live");
    drawLine(1, "Soil " + String(lastSoilMoisture, 1) + "%");
    drawLine(2, "Raw " + String(lastSoilRaw));
    drawLine(3, formatTemperatureLine());
    drawLine(4, formatHumidityLine());
    drawLine(5, formatLightLine());
    drawLine(6, "API " + backendStatusLine);
  } else if (pageIndex == 1) {
    drawLine(0, "2/4 Connect");
    drawLine(1, "WiFi " + wifiLabel);
    drawLine(2, "SSID " + String(WIFI_SSID));
    drawLine(3, "API " + getApiHost());
    drawLine(4, "Sync " + syncAgeLabel());
    drawLine(5, "State " + statusLine);
    drawLine(6, "API " + backendStatusLine);
  } else if (pageIndex == 2) {
    drawLine(0, "3/4 Command");
    drawLine(1, "Type " + lastCommandType);
    drawLine(2, "Pump " + String(lastCommandPumpMs) + " ms");
    drawLine(3, "Result " + lastCommandResult);
    drawLine(4, "Est " + String(lastWaterEstimateMl, 0) + " mL");
    drawLine(5, "Note " + lastCommandMessage);
    drawLine(6, "API " + backendStatusLine);
  } else {
    drawLine(0, "4/4 Device");
    drawLine(1, "Name " + shortDeviceName);
    drawLine(2, "Board ESP32");
    drawLine(3, "Pins S34 D4 L18/19");
    drawLine(4, "OLED 21/22 BH1750");
    drawLine(5, "SSID " + String(WIFI_SSID));
    drawLine(6, "Setup " + statusLine);
  }

  display.display();
}

void setBackendStatus(const String& statusLine) {
  backendStatusLine = statusLine;
  updateDisplay(lastStatusLine);
}

void recordBackendSuccess(const String& statusLine) {
  lastBackendSuccessMs = millis();
  Serial.println("Backend sync ok");
  setBackendStatus(statusLine);
}

void logSensorSnapshot() {
  Serial.print("Sensors | soil_raw=");
  Serial.print(lastSoilRaw);
  Serial.print(" soil_moisture=");
  Serial.print(lastSoilMoisture, 1);
  Serial.print("%");

  if (isnan(lastTemperatureC) || isnan(lastHumidityPct)) {
    Serial.print(" temp=NA hum=NA");
  } else {
    Serial.print(" temp=");
    Serial.print(lastTemperatureC, 1);
    Serial.print("C hum=");
    Serial.print(lastHumidityPct, 1);
    Serial.print("%");
  }

  if (isnan(lastLightLux)) {
    Serial.print(" light=NA");
  } else {
    Serial.print(" light=");
    Serial.print(lastLightLux, 0);
    Serial.print("lx");
  }

  Serial.println();
}

void recordBackendFailure(int statusCode) {
  if (WiFi.status() != WL_CONNECTED) {
    Serial.println("Backend sync failed: no WiFi");
    setBackendStatus("No WiFi");
    return;
  }

  if (statusCode == 401 || statusCode == 403) {
    Serial.println("Backend sync failed: auth expired");
    setBackendStatus("Auth expired");
    return;
  }

  if (statusCode <= 0) {
    Serial.println("Backend sync failed: API offline");
    setBackendStatus("API offline");
    return;
  }

  Serial.print("Backend sync failed: HTTP ");
  Serial.println(statusCode);
  setBackendStatus("API " + String(statusCode));
}

void connectWifi() {
  Serial.print("Connecting to WiFi: ");
  Serial.println(WIFI_SSID);
  WiFi.begin(WIFI_SSID, WIFI_PASSWORD);
  updateDisplay("Connecting WiFi");

  unsigned long start = millis();
  while (WiFi.status() != WL_CONNECTED && millis() - start < 12000) {
    delay(500);
  }

  if (WiFi.status() == WL_CONNECTED) {
    Serial.print("WiFi connected, IP: ");
    Serial.println(WiFi.localIP());
    syncClock();
    updateDisplay("WiFi connected");
    setBackendStatus("WiFi ok");
  } else {
    Serial.print("WiFi timeout for SSID: ");
    Serial.println(WIFI_SSID);
    updateDisplay("WiFi timeout");
    setBackendStatus("No WiFi");
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

bool readDht(float& temperatureC, float& humidityPct) {
  if (lastDhtReadMs != 0 && millis() - lastDhtReadMs < DHT_MIN_INTERVAL_MS) {
    if (isnan(lastTemperatureC) || isnan(lastHumidityPct)) {
      return false;
    }

    temperatureC = lastTemperatureC;
    humidityPct = lastHumidityPct;
    return true;
  }

  float nextHumidity = dht.readHumidity();
  float nextTemperature = dht.readTemperature();
  if (isnan(nextHumidity) || isnan(nextTemperature)) {
    return false;
  }

  lastDhtReadMs = millis();
  humidityPct = nextHumidity;
  temperatureC = nextTemperature;
  return true;
}

bool readLightLux(float& lightLux) {
  if (!lightSensorAvailable) {
    return false;
  }

  TwoWire& activeBus = lightSensorBus == 2 ? Wire : lightWire;
  if (activeBus.requestFrom((int)lightSensorAddress, 2) != 2) {
    lightSensorAvailable = configureLightSensor(activeBus, lightSensorAddress);
    return false;
  }

  uint16_t rawValue = (uint16_t(activeBus.read()) << 8) | uint16_t(activeBus.read());
  lightLux = rawValue / 1.2f;
  return true;
}

void refreshCachedReadings() {
  lastSoilRaw = readSoilRaw();
  lastSoilMoisture = rawToMoisturePct(lastSoilRaw);

  float temperatureC = NAN;
  float humidityPct = NAN;
  if (readDht(temperatureC, humidityPct)) {
    lastTemperatureC = temperatureC;
    lastHumidityPct = humidityPct;
  }

  float lightLux = NAN;
  if (readLightLux(lightLux)) {
    lastLightLux = lightLux;
  }

  if (lastSensorLogMs == 0 || millis() - lastSensorLogMs >= 5000) {
    lastSensorLogMs = millis();
    logSensorSnapshot();
  }
}

void runPump(int pumpMs) {
  lastCommandPumpMs = pumpMs;
  lastWaterEstimateMl = estimatedWaterMlForMs(pumpMs);
  lastCommandResult = "Running";
  lastCommandMessage = DEMO_WATERING_ONLY ? "Simulated water" : "Pump active";
  pumpActive = true;
  pumpStartedMs = millis();
  pumpTargetMs = (unsigned long)pumpMs;
  updateDisplay(DEMO_WATERING_ONLY ? "Sim watering" : "Pump active");
  if (!DEMO_WATERING_ONLY) {
    digitalWrite(RELAY_PIN, LOW);
  }

  while (millis() - pumpStartedMs < pumpTargetMs) {
    updateDisplay(DEMO_WATERING_ONLY ? "Sim watering" : "Pump active");
    delay(150);
  }

  if (!DEMO_WATERING_ONLY) {
    digitalWrite(RELAY_PIN, HIGH);
  }
  pumpActive = false;
  lastWaterMs = millis();
  refreshCachedReadings();
  lastCommandResult = "Complete";
  lastCommandMessage = DEMO_WATERING_ONLY ? "Simulated complete" : "Pump complete";
  updateDisplay(DEMO_WATERING_ONLY ? "Watering shown" : "Pump complete");
}

TelemetrySample captureTelemetrySample() {
  refreshCachedReadings();

  TelemetrySample sample;
  sample.capturedEpoch = clockSynced() ? time(nullptr) : 0;
  sample.soilRaw = lastSoilRaw;
  sample.soilMoisture = lastSoilMoisture;
  sample.temperatureC = lastTemperatureC;
  sample.humidityPct = lastHumidityPct;
  sample.lightLux = lastLightLux;
  sample.hasTemperature = !isnan(lastTemperatureC);
  sample.hasHumidity = !isnan(lastHumidityPct);
  sample.hasLight = !isnan(lastLightLux);
  return sample;
}

bool postTelemetrySample(const TelemetrySample& sample) {
  if (WiFi.status() != WL_CONNECTED) {
    recordBackendFailure(0);
    return false;
  }

  HTTPClient http;
  String url = String(API_BASE_URL) + "/user_sensors/bulk";
  http.begin(url);
  http.addHeader("Authorization", authHeader());
  http.addHeader("Content-Type", "application/json");

  DynamicJsonDocument doc(2048);
  JsonArray readings = doc.createNestedArray("readings");
  String timestamp = formatIsoTimestamp(sample.capturedEpoch);

  auto appendReading = [&](const char* sensorName, float value, bool include) {
    if (!include) {
      return;
    }

    JsonObject item = readings.createNestedObject();
    item["sensor_name"] = sensorName;
    item["value"] = value;
    item["source"] = "ESP32 Telemetry";
    item["device_id"] = deviceId;
    if (timestamp.length() > 0) {
      item["timestamp"] = timestamp;
    }
  };

  appendReading("soil_raw", sample.soilRaw, true);
  appendReading("soil_moisture", sample.soilMoisture, true);
  appendReading("temperature", sample.temperatureC, sample.hasTemperature);
  appendReading("humidity", sample.humidityPct, sample.hasHumidity);
  appendReading("light", sample.lightLux, sample.hasLight);

  String body;
  serializeJson(doc, body);
  int statusCode = http.POST(body);
  http.end();
  if (statusCode == 200) {
    recordBackendSuccess(telemetryQueueCount > 1 ? "Backfill live" : "Dashboard live");
    return true;
  }

  recordBackendFailure(statusCode);
  return false;
}

void queueTelemetrySample() {
  enqueueTelemetrySample(captureTelemetrySample());
  if (telemetryDroppedCount > 0) {
    Serial.print("Telemetry buffer drops: ");
    Serial.println(telemetryDroppedCount);
  }
}

void flushTelemetryQueue() {
  if (WiFi.status() != WL_CONNECTED || telemetryQueueCount == 0) {
    return;
  }

  size_t sentCount = 0;
  while (telemetryQueueCount > 0 && sentCount < MAX_TELEMETRY_FLUSH_PER_PASS) {
    if (!postTelemetrySample(peekTelemetrySample())) {
      break;
    }
    popTelemetrySample();
    sentCount++;
  }

  if (sentCount > 0) {
    updateDisplay(telemetryQueueCount > 0 ? "Backfill queued" : "Telemetry sent");
  }
}

bool fetchNextCommand(String& commandId, int& pumpMs) {
  if (WiFi.status() != WL_CONNECTED) {
    recordBackendFailure(0);
    return false;
  }

  HTTPClient http;
  String url = String(API_BASE_URL) + "/devices/" + deviceId + "/next_command";
  http.begin(url);
  http.addHeader("Authorization", authHeader());

  int statusCode = http.GET();
  if (statusCode != 200) {
    http.end();
    recordBackendFailure(statusCode);
    return false;
  }

  recordBackendSuccess("Dashboard live");
  DynamicJsonDocument doc(2048);
  DeserializationError err = deserializeJson(doc, http.getString());
  http.end();
  if (err) {
    setBackendStatus("Bad API JSON");
    return false;
  }

  String responseStatus = String((const char*)doc["status"]);
  if (responseStatus == "empty") {
    return false;
  }
  if (responseStatus != "ok") {
    setBackendStatus("API state err");
    return false;
  }

  JsonObject command = doc["command"];
  if (String((const char*)command["command_type"]) != "water_now") {
    return false;
  }

  commandId = String((const char*)command["id"]);
  pumpMs = int(command["payload"]["pump_ms"] | 0);
  lastCommandType = "water_now";
  lastCommandPumpMs = pumpMs;
  lastCommandResult = "Received";
  lastCommandMessage = "Command ready";
  return pumpMs > 0;
}

void acknowledgeCommand(const String& commandId, const char* status, const char* message) {
  if (WiFi.status() != WL_CONNECTED) {
    lastCommandResult = "Ack wait";
    lastCommandMessage = "No WiFi";
    recordBackendFailure(0);
    return;
  }

  HTTPClient http;
  String url = String(API_BASE_URL) + "/devices/" + deviceId + "/ack_command";
  http.begin(url);
  http.addHeader("Authorization", authHeader());
  http.addHeader("Content-Type", "application/json");

  DynamicJsonDocument doc(512);
  doc["command_id"] = commandId;
  doc["status"] = status;
  doc["message"] = message;

  String body;
  serializeJson(doc, body);
  int statusCode = http.POST(body);
  http.end();
  if (statusCode == 200) {
    lastCommandResult = String(status);
    lastCommandMessage = message;
    recordBackendSuccess("Ack sent");
    return;
  }

  lastCommandResult = "Ack failed";
  lastCommandMessage = "HTTP " + String(statusCode);
  recordBackendFailure(statusCode);
}

void offlineFallbackWatering() {
  refreshCachedReadings();
  bool cooldownReady = millis() - lastWaterMs >= OFFLINE_COOLDOWN_MS;

  if (lastSoilMoisture <= OFFLINE_MOISTURE_THRESHOLD_PCT && cooldownReady) {
    lastCommandType = "offline_auto";
    lastCommandPumpMs = OFFLINE_PUMP_MS;
    lastCommandResult = "Triggered";
    lastCommandMessage = "Offline auto";
    runPump(OFFLINE_PUMP_MS);
    updateDisplay("Offline watering");
    return;
  }

  updateDisplay("Offline monitor");
}

void setup() {
  pinMode(RELAY_PIN, OUTPUT);
  digitalWrite(RELAY_PIN, HIGH);
  Serial.begin(115200);
  deviceId = getDeviceId();
  shortDeviceName = getShortDeviceName();
  Serial.print("Device ID: ");
  Serial.println(deviceId);
  Serial.print("Short name: ");
  Serial.println(shortDeviceName);

  dht.begin();
  lightSensorAvailable = initLightSensor();
  if (lightSensorAvailable) {
    Serial.print("BH1750 ready on GPIO");
    Serial.print(lightSensorSdaPin);
    Serial.print("/GPIO");
    Serial.print(lightSensorSclPin);
    Serial.print(" at ");
    Serial.println(formatHexAddress(lightSensorAddress));
  } else {
    Serial.println("BH1750 not detected on GPIO18/GPIO19, GPIO19/GPIO18, GPIO21/GPIO22, or GPIO22/GPIO21");
  }

  displayAvailable = initDisplay();
  if (displayAvailable) {
    Serial.print("OLED ready on GPIO");
    Serial.print(oledSdaPin);
    Serial.print("/GPIO");
    Serial.print(oledSclPin);
    Serial.print(" at ");
    Serial.println(formatHexAddress(oledAddress));
  } else {
    Serial.println("OLED not detected on GPIO21/GPIO22 or GPIO22/GPIO21 at 0x3C/0x3D");
  }
  if (displayAvailable) {
    showBootSplash();
    setBackendStatus("API init");
    updateDisplay("Display ready");
  }

  refreshCachedReadings();
  updateDisplay("Starting up");
  connectWifi();
}

void loop() {
  if (displayAvailable && millis() - lastDisplayKeepaliveMs >= DISPLAY_KEEPALIVE_MS) {
    wakeDisplay();
  }

  if (WiFi.status() != WL_CONNECTED) {
    connectWifi();
  }

  if (millis() - lastTelemetryMs >= TELEMETRY_INTERVAL_MS) {
    lastTelemetryMs = millis();
    queueTelemetrySample();
    if (WiFi.status() == WL_CONNECTED) {
      flushTelemetryQueue();
    } else {
      updateDisplay("Telemetry queued");
    }
  } else if (WiFi.status() == WL_CONNECTED && telemetryQueueCount > 0) {
    flushTelemetryQueue();
  }

  bool commandExecuted = false;
  if (WiFi.status() == WL_CONNECTED && millis() - lastPollMs >= POLL_INTERVAL_MS) {
    lastPollMs = millis();

    String commandId;
    int pumpMs = 0;
    if (fetchNextCommand(commandId, pumpMs)) {
      runPump(pumpMs);
      queueTelemetrySample();
      acknowledgeCommand(commandId, "executed", "water_now ok");
      flushTelemetryQueue();
      updateDisplay("Command executed");
      commandExecuted = true;
    }
  }

  if (!commandExecuted && WiFi.status() != WL_CONNECTED) {
    offlineFallbackWatering();
  }

  if (WiFi.status() == WL_CONNECTED && lastBackendSuccessMs != 0 && millis() - lastBackendSuccessMs > (TELEMETRY_INTERVAL_MS * 2)) {
    setBackendStatus("No backend sync");
  }

  if (!commandExecuted && WiFi.status() == WL_CONNECTED && millis() - lastTelemetryMs < TELEMETRY_INTERVAL_MS) {
    refreshCachedReadings();
    updateDisplay("Waiting");
    delay(1000);
  }
}
