#pragma once

#include <WiFi.h>
#include <Arduino.h>

class WiFiManager {
public:
    static void connect(const String &ssid, const String &password);
};