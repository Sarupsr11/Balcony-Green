#include "SensorManager.h"

#include <OneWire.h>
#include <DallasTemperature.h>
#include "esp_camera.h"
#include "FS.h"
#include "SD_MMC.h"

// ========================
// CONFIG FLAGS
// ========================

#define ENABLE_CAMERA false
#define ENABLE_SD     false

// Detection thresholds
#define ANALOG_THRESHOLD 100

// ========================
// GLOBAL SENSOR OBJECTS
// ========================

OneWire oneWire(ONE_WIRE_BUS);
DallasTemperature soilTempSensor(&oneWire);

// ========================
// CONSTRUCTOR
// ========================

SensorManager::SensorManager() : dht(DHT_PIN, DHT_TYPE) {}


// ========================
// INITIALIZATION
// ========================

void SensorManager::begin() {

    Serial.println("Initializing sensors...");

    // -------- DHT Sensor --------
    dht.begin();
    delay(2000); // allow sensor to stabilize

    float t = dht.readTemperature();

    if (!isnan(t)) {
        hasDHT = true;
        Serial.println("DHT sensor detected");
    } else {
        Serial.println("DHT not detected");
    }

    float humidity = dht.readHumidity();

    if (!isnan(humidity)) {
        hasDHT = true;
        Serial.println("DHT sensor detected");
    } else {
        Serial.println("DHT not detected");
    }

    // -------- Soil Moisture --------
    int soil = analogRead(SOIL_PIN);

    if (soil > ANALOG_THRESHOLD) {
        hasSoil = true;
        Serial.println("Soil moisture sensor detected");
    } else {
        Serial.println("Soil sensor not detected");
    }

    // -------- Light Sensor --------
    int light = analogRead(LIGHT_PIN);

    if (light > ANALOG_THRESHOLD) {
        hasLight = true;
        Serial.println("Light sensor detected");
    } else {
        Serial.println("Light sensor not detected");
    }

    // -------- Soil Temperature (DS18B20) --------
    soilTempSensor.begin();
    soilTempSensor.requestTemperatures();

    float soilTemp = soilTempSensor.getTempCByIndex(0);

    if (soilTemp != DEVICE_DISCONNECTED_C) {
        hasSoilTemp = true;
        Serial.println("Soil temperature sensor detected");
    } else {
        Serial.println("Soil temperature sensor not detected");
    }

    // -------- Camera Initialization --------
#if ENABLE_CAMERA

    camera_config_t config;

    config.ledc_channel = LEDC_CHANNEL_0;
    config.ledc_timer = LEDC_TIMER_0;

    config.pin_d0 = 5;
    config.pin_d1 = 18;
    config.pin_d2 = 19;
    config.pin_d3 = 21;
    config.pin_d4 = 36;
    config.pin_d5 = 39;
    config.pin_d6 = 34;
    config.pin_d7 = 35;

    config.pin_xclk = 0;
    config.pin_pclk = 22;
    config.pin_vsync = 25;
    config.pin_href = 23;

    config.pin_sscb_sda = 26;
    config.pin_sscb_scl = 27;

    config.pin_pwdn = 32;
    config.pin_reset = -1;

    config.xclk_freq_hz = 20000000;
    config.pixel_format = PIXFORMAT_JPEG;

    config.frame_size = FRAMESIZE_VGA;
    config.jpeg_quality = 12;
    config.fb_count = 1;

    esp_err_t err = esp_camera_init(&config);

    if (err == ESP_OK) {
        hasCamera = true;
        Serial.println("Camera detected");
    } else {
        Serial.println("Camera not detected");
    }

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


// ========================
// SENSOR READ FUNCTIONS
// ========================

float SensorManager::getTemperature() {

    // -------- DHT Sensor --------
    dht.begin();
    delay(2000); // allow sensor to stabilize

    float temp = NAN;

    // retry multiple times
    for (int i = 0; i < 5; i++) {
        temp = dht.readTemperature();
        if (!isnan(temp)) break;
        delay(500);
    }

    if (!isnan(temp)) {
        hasDHT = true;
        Serial.println("DHT sensor detected");
    } else {
        Serial.println("DHT not detected");
    }
    return temp;
}

float SensorManager::getHumidity() {

    // -------- DHT Sensor --------
    dht.begin();
    delay(2000); // allow sensor to stabilize

    float humidity = NAN;

    // retry multiple times
    for (int i = 0; i < 5; i++) {
        humidity = dht.readHumidity();
        if (!isnan(humidity)) break;
        delay(500);
    }

    if (!isnan(humidity)) {
        hasDHT = true;
        Serial.println("DHT sensor detected");
    } else {
        Serial.println("DHT not detected");
    }
    return humidity;
}

float SensorManager::getSoilMoisture() {

    if (!hasSoil) return NAN;

    int raw = analogRead(SOIL_PIN);
    Serial.println(analogRead(SOIL_PIN));
    return map(raw, 0, 4095, 100, 0);
}

float SensorManager::getLight() {

    if (!hasLight) return NAN;

    int raw = analogRead(LIGHT_PIN);
    Serial.println(analogRead(LIGHT_PIN));
    return map(raw, 0, 4095, 0, 1000);
}

float SensorManager::getSoilTemperature() {

    if (!hasSoilTemp) return NAN;

    soilTempSensor.requestTemperatures();
    return soilTempSensor.getTempCByIndex(0);
}


// ========================
// CAMERA FUNCTIONS
// ========================

bool SensorManager::cameraAvailable() {
    return hasCamera;
}

camera_fb_t* SensorManager::captureFrame() {

#if ENABLE_CAMERA
    if (!hasCamera) return nullptr;
    return esp_camera_fb_get();
#else
    return nullptr;
#endif
}

bool SensorManager::captureImage() {

#if ENABLE_CAMERA
    camera_fb_t *fb = captureFrame();

    if (!fb) {
        Serial.println("Camera capture failed");
        return false;
    }

    Serial.printf("Image captured: %d bytes\n", fb->len);

    esp_camera_fb_return(fb);
    return true;
#else
    return false;
#endif
}

bool SensorManager::captureImageToSD(String filename) {

#if ENABLE_CAMERA && ENABLE_SD

    camera_fb_t *fb = captureFrame();

    if (!fb) {
        Serial.println("Camera capture failed");
        return false;
    }

    File file = SD_MMC.open("/" + filename, FILE_WRITE);

    if (!file) {
        Serial.println("File creation failed");
        esp_camera_fb_return(fb);
        return false;
    }

    file.write(fb->buf, fb->len);
    file.close();

    esp_camera_fb_return(fb);

    Serial.println("Photo saved");

    return true;

#else
    return false;
#endif
}


// ========================
// STATUS FUNCTIONS
// ========================

bool SensorManager::hasTemperature() { return hasDHT; }
bool SensorManager::hasHumidity() { return hasDHT; }
bool SensorManager::hasSoilSensor() { return hasSoil; }
bool SensorManager::hasLightSensor() { return hasLight; }
bool SensorManager::hasSoilTempSensor() { return hasSoilTemp; }