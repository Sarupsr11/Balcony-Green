#pragma once

// Use the build system macro if present, otherwise default to empty string
#ifndef WIFI_SSID
#define WIFI_SSID ""
#endif

#ifndef WIFI_PASSWORD
#define WIFI_PASSWORD ""
#endif

#ifndef BACKEND_URL
#define BACKEND_URL "http://10.66.165.182:8000"
#endif

#ifndef DEVICE_KEY
#define DEVICE_KEY ""
#endif

#ifndef DEVICE_ID
#define DEVICE_ID ""
#endif

#ifndef SENSOR_ID
#define SENSOR_ID ""
#endif

#define SENSOR_READ_INTERVAL 60000
#define DHT_PIN 5
#define DHT_TYPE DHT22