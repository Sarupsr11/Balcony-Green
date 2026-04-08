#include <Arduino.h>
#include "network/MyWiFiManager.h"
#include "sensors/SensorManager.h"
#include "api/BackendClient.h"
#include "config/Config.h"
#include "config/ConfigManager.h"
#include "esp_camera.h"

// ------------------------
// Global instances
// ------------------------
SensorManager sensors;
ConfigManager configManager;
DeviceConfig config;

// ------------------------
// Timing
// ------------------------
unsigned long lastRead = 0;
unsigned long lastImage = 0;
#define IMAGE_INTERVAL 600000  // 10 minutes

// Dummy camera image for testing
const uint8_t dummyImage[10] = {0xFF,0xD8,0xFF,0xE0,0x00,0x10,0x4A,0x46,0x49,0x46};

// Sensor IDs returned from backend
String tempSensorId = "";
String humiditySensorId = "";
String lightSensorId = "";
String soilSensorId = "";
String soilTempSensorId = "";

bool sensorsSynced = false;
unsigned long lastSyncAttempt = 0;
#define SENSOR_SYNC_INTERVAL 10000  // retry every 10 seconds if sync fails

// ------------------------
// Sync sensors with backend
// ------------------------
bool syncSensorsWithBackend() {
    if (!MyWiFiManager::isConnected()) return false;

    HTTPClient http;
    String url = String(config.backend_url) + "/device/sync_sensors";
    Serial.printf("🔌 Syncing sensors with backend: %s\n", url.c_str());
    Serial.printf("🔑 Using Device Key: %s\n", config.device_key.c_str());
    
    http.begin(url);
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", "Bearer " + config.device_key);

    JsonDocument doc;
    doc["device_id"] = config.device_id;
    JsonArray arr = doc["sensors"].to<JsonArray>();
    

    if (sensors.hasTemperature()) arr.add("temperature");
    if (sensors.hasHumidity()) arr.add("humidity");
    if (sensors.hasLightSensor()) arr.add("light");
    if (sensors.hasSoilSensor()) arr.add("soil_moisture");
    if (sensors.hasSoilTempSensor()) arr.add("soil_temperature");


    String payload;
    serializeJson(doc, payload);
    ;

    int code = http.POST(payload);
    Serial.printf("📨 Response code: %d\n", code);
    
    if (code == 200) {
        String respBody = http.getString();
        JsonDocument resp;
        auto err = deserializeJson(resp, respBody);
        if (err) {
            Serial.printf("❌ JSON parse failed: %s\n", err.c_str());
            Serial.printf("📄 Raw response: %s\n", respBody.c_str());
            http.end();
            return false;
        }

        JsonObject obj = resp.as<JsonObject>();
        

        if (!obj.isNull()) {
            if (obj["temperature"].is<String>()) tempSensorId = obj["temperature"].as<String>();
            if (obj["humidity"].is<String>()) humiditySensorId = obj["humidity"].as<String>();
            if (obj["light"].is<String>()) lightSensorId = obj["light"].as<String>();
            if (obj["soil_moisture"].is<String>()) soilSensorId = obj["soil_moisture"].as<String>();
            if (obj["soil_temperature"].is<String>()) soilTempSensorId = obj["soil_temperature"].as<String>();
        }

        
        http.end();
        return true;
    } else {
        Serial.printf("❌ Sensor sync failed: HTTP %d\n", code);
        Serial.printf("📄 Response: %s\n", http.getString().c_str());
        http.end();
        return false;
    }
}

// ------------------------
// Setup
// ------------------------
void setup() {
    Serial.begin(115200);
    delay(2000);

    Serial.println("\n\n=== BalconyGreen ESP32 Device Starting ===\n");

    // Initialize SPIFFS
    if (!configManager.begin()) {
        Serial.println("❌ Failed to initialize SPIFFS");
    }

    // Clear configuration on fresh boot to force AP mode
    // Serial.println("🧹 Clearing saved configuration for fresh setup...");
    // SPIFFS.remove("/config.json");
    // Serial.println("✅ Configuration cleared\n");

    Serial.println("📂 Loading configuration...");
    if (!configManager.loadConfig(config)) {
        Serial.println("⚠️  No configuration found. Device will start in AP mode.");
    } else {
        Serial.println("✅ Configuration loaded from SPIFFS");
    }

    // Start Wi-Fi manager with captive portal
    Serial.println("🔌 Starting Wi-Fi manager...");
    MyWiFiManager::begin(&config, &configManager);

    // Wait for Wi-Fi to connect or provisioning to complete
    int waitCounter = 0;
    while (!MyWiFiManager::isConnected()) {
        if (waitCounter % 10 == 0) {
            Serial.println("⏳ Waiting for Wi-Fi connection or AP startup...");
        }
        MyWiFiManager::loop();
        delay(500);
        waitCounter++;
    }

    Serial.printf("✅ Wi-Fi connected! IP: %s\n\n", MyWiFiManager::getIP().c_str());

    // Initialize backend
    BackendClient::begin(config.backend_url, config.device_key, config.device_id);
    if (BackendClient::ping())
        Serial.println("Backend reachable");
    else
        Serial.println("Backend not reachable");

    // Initialize sensors
    sensors.begin();

    // Attempt sensor sync with backend, but do not block forever
    Serial.println("🔄 Attempting to sync sensors with backend...");
    int syncAttempts = 0;
    while (syncAttempts < 3 && !sensorsSynced) {
        if (syncSensorsWithBackend()) {
            sensorsSynced = true;
            Serial.println("✅ Sensor sync successful!");
            break;
        } else {
            syncAttempts++;
            Serial.printf("❌ Sensor sync failed (%d/3), retrying in 5 seconds...\n", syncAttempts);
            delay(5000);
        }
    }

    if (!sensorsSynced) {
        Serial.println("⚠️ Sensor sync did not complete during setup. Main loop will continue and retry periodically.");
        lastSyncAttempt = millis();
    }
}

// ------------------------
// Loop
// ------------------------
void loop() {
    // Handle captive portal if still running
    MyWiFiManager::loop();

    if (!MyWiFiManager::isConnected()) return;

    unsigned long now = millis();

    if (!sensorsSynced && now - lastSyncAttempt >= SENSOR_SYNC_INTERVAL) {
        lastSyncAttempt = now;
        Serial.println("🔄 Retrying sensor sync with backend...");
        if (syncSensorsWithBackend()) {
            sensorsSynced = true;
            Serial.println("✅ Sensor sync successful!");
        } else {
            Serial.println("❌ Sensor sync retry failed");
        }
    }

    if (!sensorsSynced) return;

    // Sensor readings
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

    // Camera image uploads
    if (now - lastImage > IMAGE_INTERVAL) {
        lastImage = now;

        if (sensors.cameraAvailable()) {
            camera_fb_t *fb = sensors.captureFrame();
            if (fb) {
                bool success = BackendClient::sendCameraImage(fb->buf, fb->len, "plant_camera");
                Serial.println(success ? "Image uploaded" : "Image upload failed");
                esp_camera_fb_return(fb);
            }
        } else {
            bool success = BackendClient::sendCameraImage((uint8_t*)dummyImage, sizeof(dummyImage), "plant_camera");
            Serial.println(success ? "Dummy image uploaded" : "Dummy image upload failed");
        }
    }
}