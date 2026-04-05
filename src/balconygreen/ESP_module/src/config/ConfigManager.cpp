#include "ConfigManager.h"
#include "Config.h"



bool ConfigManager::loadConfig(DeviceConfig &config) {

    // Wrap macros in String() to avoid compiler errors
    config.wifi_ssid     = String(WIFI_SSID);
    config.wifi_password = String(WIFI_PASSWORD);
    config.device_key    = String(DEVICE_KEY);
    config.device_id    = String(DEVICE_ID);
    config.backend_url   = String(BACKEND_URL);
    config.sensor_id     = String(SENSOR_ID);

    Serial.println("Configuration loaded");

    Serial.print("SSID: ");
    Serial.println(config.wifi_ssid);

    Serial.print("Backend URL: ");
    Serial.println(config.backend_url);

    Serial.print("Device Key: ");
    Serial.println(config.device_key);

    Serial.print("Sensor ID: ");
    Serial.println(config.sensor_id);

    return true;
}