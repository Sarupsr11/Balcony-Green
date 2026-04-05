#include "WiFiManager.h"

void WiFiManager::connect(const String &ssid, const String &password) {
    if (WiFi.status() == WL_CONNECTED) {
        Serial.println("Already connected to WiFi");
        return;
    }

    Serial.printf("Connecting to WiFi: %s\n", ssid.c_str());
    WiFi.begin(ssid.c_str(), password.c_str());

    int attempts = 0;
    while (WiFi.status() != WL_CONNECTED && attempts < 20) {
        delay(500);
        Serial.print(".");
        attempts++;
    }

    if (WiFi.status() == WL_CONNECTED) {
        Serial.printf("\nConnected! IP: %s\n", WiFi.localIP().toString().c_str());
    } else {
        Serial.println("\nFailed to connect to WiFi");
    }
}