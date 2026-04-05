#ifndef BACKEND_CLIENT_H
#define BACKEND_CLIENT_H

#include <Arduino.h>
#include <WiFi.h>
#include <HTTPClient.h>
#include <ArduinoJson.h>

class BackendClient {

public:

    // Initialize backend
    static void begin(const String &url, const String &key, const String &s_id);

    // Device registration (optional)
    static bool activateDevice();

    // Backend health check
    static bool ping();

    // Send numeric sensor reading
    static void sendReading(const String &sensor_id,
                            float value,
                            const String &unit,
                            const String &source);

    // Upload camera image
    static bool sendCameraImage(uint8_t *imageData,
                                size_t imageSize,
                                const String &sensor_id);

private:

    static String backend_url;
    static String device_key;
    static String sensor_id;

};

#endif