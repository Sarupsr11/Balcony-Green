#pragma once

#include <Arduino.h>

/*
   Device configuration structure

   Values are injected at build time by the backend
   using PlatformIO build flags.

   Example:

   -DWIFI_SSID="MyWifi"
   -DWIFI_PASSWORD="password"
   -DDEVICE_KEY="uuid"
   -DSENSOR_ID="uuid"
   -DBACKEND_URL="https://api.balconygreen.com"
*/

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

    /*
       Load configuration from firmware macros
    */
    static bool loadConfig(DeviceConfig &config);

};