#include "MyWiFiManager.h"
#include <ArduinoJson.h>
#include <SPIFFS.h>

WebServer* MyWiFiManager::server = nullptr;
DNSServer MyWiFiManager::dnsServer;
ConfigManager* MyWiFiManager::configManager = nullptr;
bool MyWiFiManager::isAPMode = false;
String MyWiFiManager::wifiSSID = "";
String MyWiFiManager::wifiPassword = "";
DeviceConfig* MyWiFiManager::configPtr = nullptr;

void MyWiFiManager::begin(DeviceConfig* cfg, ConfigManager* cfgMgr) {
    configPtr = cfg;
    configManager = cfgMgr;

    // Load config from SPIFFS
    if (!configManager->begin()) {
        Serial.println("❌ Failed to initialize SPIFFS");
    }
    configManager->loadConfig(*configPtr);

    wifiSSID = configPtr->wifi_ssid;
    wifiPassword = configPtr->wifi_password;

    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("Already connected to Wi-Fi");
        return;
    }

    if (wifiSSID.length() > 0 && wifiPassword.length() > 0) {
        Serial.printf("Connecting to Wi-Fi: %s\n", wifiSSID.c_str());
        WiFi.begin(wifiSSID.c_str(), wifiPassword.c_str());

        int attempts = 0;
        while (WiFi.status() != WL_CONNECTED && attempts < 20) {
            delay(500);
            Serial.print(".");
            attempts++;
        }

        if (WiFi.status() == WL_CONNECTED) {
            Serial.printf("\nConnected! IP: %s\n", WiFi.localIP().toString().c_str());
            isAPMode = false;
            return;
        }
        Serial.println("\nFailed to connect, starting AP...");
    } else {
        Serial.println("No Wi-Fi credentials, starting AP for provisioning...");
    }

    startAP();
}

bool MyWiFiManager::isConnected() {
    return WiFi.status() == WL_CONNECTED;
}

String MyWiFiManager::getIP() {
    return WiFi.localIP().toString();
}

void MyWiFiManager::loop() {
    if (isAPMode) {
        dnsServer.processNextRequest();
    }
    if (server) server->handleClient();
}

void MyWiFiManager::factoryReset() {
    isAPMode = false;
    SPIFFS.remove("/config.json");
    Serial.println("Factory reset done. Rebooting...");
    delay(1000);
    ESP.restart();
}

void MyWiFiManager::startAP() {
    isAPMode = true;
    String apSSID = "ESP32_" + String((uint64_t)ESP.getEfuseMac(), HEX);
    const char* apPassword = "setup1234";

    Serial.println("\n📡 Starting Access Point Mode...");
    WiFi.softAP(apSSID.c_str(), apPassword);
    IPAddress ip = WiFi.softAPIP();
    

    dnsServer.start(53, "*", ip);

    server = new WebServer(80);

    server->on("/", handleRoot);
    server->on("/setup", HTTP_POST, handleSetup);

    // Captive portal detection
    server->on("/generate_204", handleRoot);
    server->on("/hotspot-detect.html", handleRoot);
    server->on("/ncsi.txt", handleRoot);

    server->onNotFound([]() {
        server->sendHeader("Location", "/", true);
        server->send(302, "text/plain", "");
    });

    server->begin();
    Serial.println("Captive portal started");
}

void MyWiFiManager::handleRoot() {
    

    String html = "<html><body>";
    html += "<h2>Device Setup</h2>";
    html += "<form method='POST' action='/setup'>";
    html += "Device Key:<br><input name='device_key' required><br><br>";
    html += "WiFi SSID:<br><input name='wifi_ssid' required><br><br>";
    html += "WiFi Password:<br><input type='password' name='wifi_password' required><br><br>";
    html += "<input type='submit' value='Connect'>";
    html += "</form></body></html>";

    server->send(200, "text/html", html);
}

void MyWiFiManager::handleSetup() {
    if (!server->hasArg("device_key") ||
        !server->hasArg("wifi_ssid") ||
        !server->hasArg("wifi_password")) {
        server->send(400, "text/html", "<h3>Missing required fields</h3>");
        return;
    }

    configPtr->device_key = server->arg("device_key");
    configPtr->wifi_ssid  = server->arg("wifi_ssid");
    configPtr->wifi_password = server->arg("wifi_password");

    // Save to SPIFFS
    if (configManager->saveConfig(*configPtr)) {
        Serial.println("✅ Configuration saved");
    }

    server->send(200, "text/html", "<h3>Saved! Rebooting...</h3>");
    delay(2000);
    ESP.restart();
}