#include <Arduino.h>

#include "network/WiFiManager.h"
#include "sensors/SensorManager.h"
#include "api/BackendClient.h"
#include "config/Config.h"
#include "config/ConfigManager.h"
#include "esp_camera.h"

SensorManager sensors;
ConfigManager configManager;
DeviceConfig config;

unsigned long lastRead = 0;
#define IMAGE_INTERVAL 600000  // 10 minutes
unsigned long lastImage = 0;

// =========================
// Dummy camera image
// =========================
const uint8_t dummyImage[10] = {0xFF, 0xD8, 0xFF, 0xE0, 0x00, 0x10, 0x4A, 0x46, 0x49, 0x46}; // minimal JPEG header



// Store sensor IDs returned from backend
String tempSensorId = "";
String humiditySensorId = "";
String lightSensorId = "";
String soilSensorId = "";
String soilTempSensorId = "";

void syncSensorsWithBackend() {
    if (WiFi.status() != WL_CONNECTED) return;

    HTTPClient http;
    http.begin(String(config.backend_url) + "/device/sync_sensors");
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", "Bearer " + config.device_key);

    // Build JSON payload
    JsonDocument doc;
    doc["device_id"] = config.device_id;
    JsonArray arr = doc.createNestedArray("sensors");

    if (sensors.hasTemperature()) arr.add("temperature");
    if (sensors.hasHumidity()) arr.add("humidity");
    if (sensors.hasLightSensor()) arr.add("light");
    if (sensors.hasSoilSensor()) arr.add("soil_moisture");
    if (sensors.hasSoilTempSensor()) arr.add("soil_temperature");

    String payload;
    serializeJson(doc, payload);

    int code = http.POST(payload);
    if (code == 200) {
        JsonDocument resp;
        deserializeJson(resp, http.getString());
        JsonObject obj = resp.as<JsonObject>();

        if (obj["temperature"].is<String>()) tempSensorId = obj["temperature"].as<String>();
        if (obj["humidity"].is<String>()) humiditySensorId = obj["humidity"].as<String>();
        if (obj["light"].is<String>()) lightSensorId = obj["light"].as<String>();
        if (obj["soil_moisture"].is<String>()) soilSensorId = obj["soil_moisture"].as<String>();
        if (obj["soil_temperature"].is<String>()) soilTempSensorId = obj["soil_temperature"].as<String>();
    } else {
        Serial.printf("Sensor sync failed: HTTP %d\n", code);
    }

    http.end();
}

void setup() {
    Serial.begin(115200);
    delay(5000);
    Serial.println("Starting device...");

    // Load config
    if (!configManager.loadConfig(config)) {
        Serial.println("No configuration found. Device will not function.");
        return;
    }

    Serial.println("Config loaded");

    // Connect to WiFi
    WiFiManager::connect(config.wifi_ssid, config.wifi_password);

    // Initialize backend
    BackendClient::begin(config.backend_url, config.device_key, config.device_id);

    if (BackendClient::ping()) Serial.println("Backend reachable");
    else Serial.println("Cannot reach backend");

    // Initialize sensors
    sensors.begin();

    // Sync sensors with backend to get sensor IDs
    syncSensorsWithBackend();
}

void loop() {
    if (config.device_key.length() == 0) return;

    unsigned long now = millis();

    // =========================
    // Sensor readings
    // =========================
    if (now - lastRead > SENSOR_READ_INTERVAL) {
        lastRead = now;

        float temperature = sensors.getTemperature();
        float humidity    = sensors.getHumidity();
        float light       = sensors.getLight();
        float soilMoist   = sensors.getSoilMoisture();
        float soilTemp    = sensors.getSoilTemperature();

        if (!isnan(temperature) && tempSensorId.length())
            BackendClient::sendReading(tempSensorId, temperature, "C", "temperature");

        if (!isnan(humidity) && humiditySensorId.length())
            BackendClient::sendReading(humiditySensorId, humidity, "%", "humidity");

        if (!isnan(light) && lightSensorId.length())
            BackendClient::sendReading(lightSensorId, light, "lx", "light_sensor");

        if (!isnan(soilMoist) && soilSensorId.length())
            BackendClient::sendReading(soilSensorId, soilMoist, "%", "soil_moisture");

        if (!isnan(soilTemp) && soilTempSensorId.length())
            BackendClient::sendReading(soilTempSensorId, soilTemp, "C", "soil_temp");
    }

    // =========================
    // Camera upload (real or dummy)
    // =========================
    if (now - lastImage > IMAGE_INTERVAL) {
        lastImage = now;

        if (sensors.cameraAvailable()) {
            Serial.println("Capturing real camera image...");
            camera_fb_t *fb = sensors.captureFrame();
            if (fb) {
                bool success = BackendClient::sendCameraImage(fb->buf, fb->len, "plant_camera");
                Serial.println(success ? "Image uploaded" : "Image upload failed");
                esp_camera_fb_return(fb);
            }

        } else {
            Serial.println("Camera not detected, sending dummy image for testing...");
            bool success = BackendClient::sendCameraImage(
                (uint8_t*)dummyImage,
                sizeof(dummyImage),
                "plant_camera"
            );
            Serial.println(success ? "Dummy image uploaded" : "Dummy image upload failed");
        }
    }
}