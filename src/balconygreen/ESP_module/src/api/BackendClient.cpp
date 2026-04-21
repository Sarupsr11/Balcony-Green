#include "BackendClient.h"

String BackendClient::backend_url = "";
String BackendClient::device_key = "";
String BackendClient::device_id = "";

void BackendClient::begin(const String &url, const String &key, const String &dev_id) {
    backend_url = url;
    device_key  = key;
    device_id   = dev_id;
}


bool BackendClient::ping() {
    if (backend_url.length() == 0) return false;

    HTTPClient http;
    http.begin(backend_url + "/ping");
    int code = http.GET();
    Serial.printf("📊 Ping response: HTTP %d\n", code);
    http.end();
    return code == 200;
}

void BackendClient::sendReading(const String &sensor_id_,
                                float value,
                                const String &unit,
                                const String &source) {

    Serial.printf("➡️ sendReading called: sensor=%s value=%.2f unit=%s source=%s\n",
        sensor_id_.c_str(), value, unit.c_str(), source.c_str());

    if (!WiFi.isConnected()) {
        Serial.println("⚠️ sendReading skipped: Wi-Fi not connected");
        return;
    }
    if (backend_url.length() == 0) {
        Serial.println("⚠️ sendReading skipped: backend_url missing");
        return;
    }
    if (device_key.length() == 0) {
        Serial.println("⚠️ sendReading skipped: device_key missing");
        return;
    }

    JsonDocument doc;
    doc["sensor_id"] = sensor_id_;
    doc["value"] = value;
    doc["unit"] = unit;
    doc["sensor_name"] = source;

    String payload;
    serializeJson(doc, payload);

    Serial.printf("   Sensor: %s, Value: %.2f %s\n", sensor_id_.c_str(), value, unit.c_str());
    
    HTTPClient http;
    http.begin(backend_url + "/sensor_readings");
    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", "Bearer " + device_key);
    int code = http.POST(payload);


    http.end();
}

bool BackendClient::sendCameraImage(uint8_t *imageData, size_t imageSize, const String &sensor_id_) {
    if (!WiFi.isConnected() || backend_url.length() == 0 || device_key.length() == 0) return false;

    HTTPClient http;
    http.begin(backend_url + "/camera/upload/"+ sensor_id_);
    http.addHeader("Authorization", "Bearer " + device_key);
    http.addHeader("Content-Type", "application/octet-stream");

    int code = http.POST(imageData, imageSize);

    http.end();
    return code == 200;
}