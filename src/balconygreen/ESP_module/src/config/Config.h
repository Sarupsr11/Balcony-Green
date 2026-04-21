#pragma once

// ------------------------
// Default WiFi credentials
// ------------------------
#ifndef WIFI_SSID
#define WIFI_SSID ""       // Will be set via captive portal
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""   // Will be set via captive portal
#endif

// ------------------------
// Backend info
// ------------------------
#ifndef BACKEND_URL
#define BACKEND_URL "https://balconygreen-production.up.railway.app"
#endif

// ------------------------
// Device registration info
// ------------------------
#ifndef DEVICE_KEY
#define DEVICE_KEY ""      // Set after user registers device
#endif





// ------------------------
// Sensor config
// ------------------------
#define SENSOR_READ_INTERVAL 60000    // 1 min interval
#define DHT_PIN 4                      // DHT sensor pin
#define DHT_TYPE DHT22                  // DHT sensor type