#include "ConfigManager.h"
#include "Config.h"
#include <FS.h>
#include <SPIFFS.h>

#define CONFIG_FILE "/config.json"

bool ConfigManager::begin() {
    if (!SPIFFS.begin(true)) {
        Serial.println("❌ Failed to mount SPIFFS, formatting...");
        return false;
    }
    return true;
}

bool ConfigManager::loadConfig(DeviceConfig &config) {
    if (!SPIFFS.exists(CONFIG_FILE)) {
        Serial.println("⚠ Config file not found, using defaults");
        config.wifi_ssid     = String(WIFI_SSID);
        config.wifi_password = String(WIFI_PASSWORD);
        config.device_key    = String(DEVICE_KEY);
        config.backend_url   = String(BACKEND_URL);
        return false;
    }

    File file = SPIFFS.open(CONFIG_FILE, "r");
    if (!file) {
        Serial.println("❌ Failed to open config file for reading");
        return false;
    }

    size_t size = file.size();
    if (size > 2048) {
        Serial.println("❌ Config file size too large");
        file.close();
        return false;
    }

    std::unique_ptr<char[]> buf(new char[size + 1]);
    file.readBytes(buf.get(), size);
    buf[size] = 0;
    file.close();

    JsonDocument doc;
    auto err = deserializeJson(doc, buf.get());
    if (err) {
        Serial.println("❌ Failed to parse config JSON");
        return false;
    }

    config.wifi_ssid     = doc["wifi_ssid"] | String(WIFI_SSID);
    config.wifi_password = doc["wifi_password"] | String(WIFI_PASSWORD);
    config.device_key    = doc["device_key"] | String(DEVICE_KEY);
    config.backend_url   = doc["backend_url"] | String(BACKEND_URL);

    Serial.println("✅ Configuration loaded");
    Serial.print("SSID: "); Serial.println(config.wifi_ssid);
    Serial.print("Backend URL: "); Serial.println(config.backend_url);
    Serial.print("Device Key: "); Serial.println(config.device_key);
    Serial.print("Sensor ID: "); Serial.println(config.sensor_id);

    return true;
}

bool ConfigManager::saveConfig(const DeviceConfig &config) {
    JsonDocument doc;
    doc["wifi_ssid"]     = config.wifi_ssid;
    doc["wifi_password"] = config.wifi_password;
    doc["device_key"]    = config.device_key;
    doc["backend_url"]   = config.backend_url;
    

    File file = SPIFFS.open(CONFIG_FILE, "w");
    if (!file) {
        Serial.println("❌ Failed to open config file for writing");
        return false;
    }

    if (serializeJson(doc, file) == 0) {
        Serial.println("❌ Failed to write config to file");
        file.close();
        return false;
    }

    file.close();
    Serial.println("✅ Configuration saved");
    return true;
}