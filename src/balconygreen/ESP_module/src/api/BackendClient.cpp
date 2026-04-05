#include "BackendClient.h"

String BackendClient::backend_url = "";
String BackendClient::device_key = "";
String BackendClient::sensor_id = "";

// ============================
// Initialization
// ============================

void BackendClient::begin(const String &url, const String &key, const String &s_id) {

    backend_url = url;
    device_key = key;
    sensor_id = s_id;

    Serial.println("BackendClient initialized");
    Serial.println("Backend URL: " + backend_url);
}

// ============================
// Device Activation
// ============================

bool BackendClient::activateDevice() {

    // For now just return true
    return true;
}

// ============================
// Ping Backend
// ============================

bool BackendClient::ping() {

    if (WiFi.status() != WL_CONNECTED) return false;

    HTTPClient http;

    String url = backend_url + "/ping";

    http.begin(url);

    int response = http.GET();

    http.end();

    Serial.print("Ping response: ");
    Serial.println(response);

    return response == 200;
}

// ============================
// Send Sensor Reading
// ============================

void BackendClient::sendReading(const String &sensor_id,
                                float value,
                                const String &unit,
                                const String &sensor_name) {

    if (WiFi.status() != WL_CONNECTED) return;

    HTTPClient http;

    String url = backend_url + "/sensor_readings";

    http.begin(url);

    http.addHeader("Content-Type", "application/json");
    http.addHeader("Authorization", "Bearer " + device_key);

    JsonDocument doc;

    doc["sensor_id"] = sensor_id;
    doc["value"] = value;
    doc["unit"] = unit;
    doc["sensor_name"] = sensor_name;

    String payload;

    serializeJson(doc, payload);

    Serial.println("Sending reading:");
    Serial.println(payload);

    int response = http.POST(payload);

    Serial.print("HTTP Response: ");
    Serial.println(response);

    http.end();
}

// ============================
// Upload Camera Image
// ============================

bool BackendClient::sendCameraImage(uint8_t *imageData,
                                    size_t imageSize,
                                    const String &sensor_id) {

    if (WiFi.status() != WL_CONNECTED) return false;

    HTTPClient http;

    String url = backend_url + "/camera/upload/" + sensor_id;

    http.begin(url);

    http.addHeader("Authorization", "Bearer " + device_key);

    String boundary = "----ESP32Boundary";
    http.addHeader("Content-Type", "multipart/form-data; boundary=" + boundary);

    // -------------------------
    // MULTIPART BODY PARTS
    // -------------------------

    String head =
        "--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"file\"; filename=\"plant.jpg\"\r\n"
        "Content-Type: image/jpeg\r\n\r\n";

    // ✅ ADD plant field
    String plantField =
        "\r\n--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"plant\"\r\n\r\n"
        "tomato\r\n";

    // ✅ ADD mode field
    String modeField =
        "--" + boundary + "\r\n"
        "Content-Disposition: form-data; name=\"mode\"\r\n\r\n"
        "binary\r\n";

    String tail = "--" + boundary + "--\r\n";

    // -------------------------
    // TOTAL LENGTH
    // -------------------------

    size_t totalLen = head.length() +
                      imageSize +
                      plantField.length() +
                      modeField.length() +
                      tail.length();

    http.addHeader("Content-Length", String(totalLen));

    WiFiClient *stream = http.getStreamPtr();

    int response = http.sendRequest("POST");

    if (response <= 0) {
        Serial.println("Upload failed");
        http.end();
        return false;
    }

    // -------------------------
    // SEND DATA
    // -------------------------

    stream->print(head);
    stream->write(imageData, imageSize);

    stream->print(plantField);
    stream->print(modeField);
    stream->print(tail);

    Serial.print("Camera upload response: ");
    Serial.println(response);

    http.end();

    return response == 200;
}