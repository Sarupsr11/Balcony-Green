#pragma once
#include <Arduino.h>
#include <WiFi.h>
#include <WebServer.h>
#include <DNSServer.h>
#include "ConfigManager.h"
#include "Config.h"

class MyWiFiManager {
public:
    // Initialize Wi-Fi manager with device config
    static void begin(DeviceConfig* cfg, ConfigManager* cfgMgr);

    // Loop handler (call in main loop)
    static void loop();

    // Wi-Fi status
    static bool isConnected();
    static String getIP();

    // Optional: Factory reset device config
    static void factoryReset();

private:
    // Core objects
    static WebServer* server;
    static DNSServer dnsServer;
    static ConfigManager* configManager;
    static bool isAPMode;  // Track if captive portal is active

    // Wi-Fi credentials
    static String wifiSSID;
    static String wifiPassword;

    // Device configuration pointer
    static DeviceConfig* configPtr;

    // Internal methods
    static void startAP();
    static void handleRoot();
    static void handleSetup();
};