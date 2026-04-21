#pragma once

#include <Arduino.h>
#include <FS.h>
#include <SPIFFS.h>
#include <ArduinoJson.h>

struct DeviceConfig {
    String wifi_ssid;
    String wifi_password;
    String device_key;
    String backend_url;
    String device_id;
    String sensor_id;
};

class ConfigManager {
public:

    // Initialize SPIFFS
    static bool begin();

    // Load config from SPIFFS (fallback to build-time macros if not present)
    static bool loadConfig(DeviceConfig &config);

    // Save config to SPIFFS
    static bool saveConfig(const DeviceConfig &config);

private:
    static constexpr const char* CONFIG_FILE = "/config.json";
};