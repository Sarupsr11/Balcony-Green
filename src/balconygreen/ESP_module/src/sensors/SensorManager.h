#ifndef SENSOR_MANAGER_H
#define SENSOR_MANAGER_H

#include <Arduino.h>
#include <DHT.h>
#include "esp_camera.h"
#include "config/Config.h"

// ========================
// CONFIGURATION
// ========================

#define DHT_TYPE DHT22

#define SOIL_PIN 34
#define LIGHT_PIN 35

#define ONE_WIRE_BUS 4

// ========================
// SENSOR MANAGER CLASS
// ========================

class SensorManager {

public:
    SensorManager();

    void begin();

    // Sensor readings
    float getTemperature();
    float getHumidity();
    float getSoilMoisture();
    float getLight();
    float getSoilTemperature();

    // Camera
    bool cameraAvailable();
    camera_fb_t* captureFrame();
    bool captureImage();
    bool captureImageToSD(const String &filename);

    // Status flags
    bool hasTemperature();
    bool hasHumidity();
    bool hasSoilSensor();
    bool hasLightSensor();
    bool hasSoilTempSensor();
    bool hasCamera();

private:
    DHT dht;

    bool hasDHT = false;
    bool hasSoil = false;
    bool hasLight = false;
    bool hasSoilTemp = false;
    bool hasCameraSensor = false;

    void initDHT();
    void initSoilSensor();
    void initLightSensor();
    void initCamera();
};

#endif