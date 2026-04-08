#include "SensorManager.h"
#include <OneWire.h>
#include <DallasTemperature.h>
#include "FS.h"
#include "SD_MMC.h"

// ------------------------
// Config flags
// ------------------------
#define ENABLE_CAMERA false
#define ENABLE_SD     false
#define ANALOG_THRESHOLD 100

// ------------------------
// Global sensor objects
// ------------------------
OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature soilTempSensor(&oneWire);

// ------------------------
// Constructor
// ------------------------
SensorManager::SensorManager() : dht(DHT_PIN, DHT_TYPE) {}

// ------------------------
// Initialize sensors
// ------------------------
void SensorManager::begin() {
    Serial.println("Initializing sensors...");

    // -------- DHT Sensor --------
    pinMode(DHT_PIN, INPUT_PULLUP);
    dht.begin();
    delay(2500);

    float t = NAN;
    float h = NAN;
    for (int i = 0; i < 5; i++) {
        t = dht.readTemperature();
        h = dht.readHumidity();
        Serial.printf("DHT init attempt %d: temp=%.2f, hum=%.2f\n", i + 1, t, h);
        if (!isnan(t) && !isnan(h)) {
            hasDHT = true;
            break;
        }
        delay(500);
    }

    Serial.println(hasDHT ? "DHT sensor detected" : "DHT not detected");

    // -------- Soil Moisture --------
    int soil = analogRead(SOIL_PIN);
    hasSoil = soil > ANALOG_THRESHOLD;
    Serial.println(hasSoil ? "Soil moisture sensor detected" : "Soil sensor not detected");

    // -------- Light Sensor --------
    int light = analogRead(LIGHT_PIN);
    hasLight = light > ANALOG_THRESHOLD;
    Serial.println(hasLight ? "Light sensor detected" : "Light sensor not detected");

    // -------- Soil Temperature (DS18B20) --------
    soilTempSensor.begin();
    soilTempSensor.requestTemperatures();
    float soilTemp = soilTempSensor.getTempCByIndex(0);
    hasSoilTemp = soilTemp != DEVICE_DISCONNECTED_C;
    Serial.println(hasSoilTemp ? "Soil temperature sensor detected" : "Soil temperature sensor not detected");

    // -------- Camera Initialization --------
#if ENABLE_CAMERA
    camera_config_t config;
    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;
    config.pin_d0 = 5; config.pin_d1 = 18; config.pin_d2 = 19; config.pin_d3 = 21;
    config.pin_d4 = 36; config.pin_d5 = 39; config.pin_d6 = 34; config.pin_d7 = 35;
    config.pin_xclk = 0; config.pin_pclk = 22; config.pin_vsync = 25; config.pin_href = 23;
    config.pin_sscb_sda = 26; config.pin_sscb_scl = 27; config.pin_pwdn = 32; config.pin_reset = -1;
    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;
    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;

    esp_err_t err = esp_camera_init(&config);
    hasCameraSensor = (err == ESP_OK);
    Serial.println(hasCameraSensor ? "Camera detected" : "Camera not detected");
#else
    Serial.println("Camera disabled in config");
#endif

    // -------- SD Card --------
#if ENABLE_SD
    if (SD_MMC.begin()) {
        Serial.println("SD Card mounted");
    } else {
        Serial.println("SD Card mount failed");
    }
#else
    Serial.println("SD card disabled in config");
#endif

    Serial.println("Sensor initialization complete");
}

// ------------------------
// Sensor readings
// ------------------------
float SensorManager::getTemperature() {
    float temp = NAN;
    for (int i = 0; i < 5; i++) {
        temp = dht.readTemperature();
        Serial.printf("DHT temperature read attempt %d: %.2f\n", i + 1, temp);
        if (!isnan(temp)) {
            hasDHT = true;
            return temp;
        }
        delay(500);
    }
    return NAN;
}

float SensorManager::getHumidity() {
    float humidity = NAN;
    for (int i = 0; i < 5; i++) {
        humidity = dht.readHumidity();
        Serial.printf("DHT humidity read attempt %d: %.2f\n", i + 1, humidity);
        if (!isnan(humidity)) {
            hasDHT = true;
            return humidity;
        }
        delay(500);
    }
    return NAN;
}

float SensorManager::getSoilMoisture() {
    if (!hasSoil) return NAN;
    int raw = analogRead(SOIL_PIN);
    return map(raw, 0, 4095, 100, 0); // 0-100%
}

float SensorManager::getLight() {
    if (!hasLight) return NAN;
    int raw = analogRead(LIGHT_PIN);
    return map(raw, 0, 4095, 0, 1000); // approximate lux
}

float SensorManager::getSoilTemperature() {
    if (!hasSoilTemp) return NAN;
    soilTempSensor.requestTemperatures();
    return soilTempSensor.getTempCByIndex(0);
}

// ------------------------
// Camera functions
// ------------------------
bool SensorManager::cameraAvailable() { return hasCameraSensor; }

camera_fb_t* SensorManager::captureFrame() {
#if ENABLE_CAMERA
    if (!hasCameraSensor) return nullptr;
    return esp_camera_fb_get();
#else
    return nullptr;
#endif
}

bool SensorManager::captureImage() {
#if ENABLE_CAMERA
    camera_fb_t *fb = captureFrame();
    if (!fb) { Serial.println("Camera capture failed"); return false; }
    Serial.printf("Image captured: %d bytes\n", fb->len);
    esp_camera_fb_return(fb);
    return true;
#else
    return false;
#endif
}

bool SensorManager::captureImageToSD(const String &filename) {
#if ENABLE_CAMERA && ENABLE_SD
    camera_fb_t *fb = captureFrame();
    if (!fb) { Serial.println("Camera capture failed"); return false; }
    File file = SD_MMC.open("/" + filename, FILE_WRITE);
    if (!file) { Serial.println("File creation failed"); esp_camera_fb_return(fb); return false; }
    file.write(fb->buf, fb->len);
    file.close();
    esp_camera_fb_return(fb);
    Serial.println("Photo saved");
    return true;
#else
    return false;
#endif
}

// ------------------------
// Status flags
// ------------------------
bool SensorManager::hasTemperature() { return hasDHT; }
bool SensorManager::hasHumidity()    { return hasDHT; }
bool SensorManager::hasSoilSensor()  { return hasSoil; }
bool SensorManager::hasLightSensor() { return hasLight; }
bool SensorManager::hasSoilTempSensor() { return hasSoilTemp; }