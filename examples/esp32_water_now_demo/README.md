# ESP32 Water Now Demo

This example lets an ESP32 poll the FastAPI backend for queued `water_now` commands, post soil and environment telemetry, and show local status on a small I2C OLED.

The OLED and BH1750 use separate I2C buses in this sketch:

- OLED on `GPIO21`/`GPIO22`
- BH1750 on `GPIO18`/`GPIO19`

## Wiring

| Part | Pin | ESP32 |
| --- | --- | --- |
| Capacitive soil sensor | `AOUT` | `GPIO34` |
| Capacitive soil sensor | `VCC` | `3.3V` |
| Capacitive soil sensor | `GND` | `GND` |
| DHT22 | `DATA` | `GPIO4` |
| DHT22 | `VCC` | `3.3V` |
| DHT22 | `GND` | `GND` |
| BH1750 | `SDA` | `GPIO18` |
| BH1750 | `SCL` | `GPIO19` |
| BH1750 | `VCC` | `3.3V` |
| BH1750 | `GND` | `GND` |
| OLED | `SDA` | `GPIO21` |
| OLED | `SCL` | `GPIO22` |
| OLED | `VCC` | `3.3V` |
| OLED | `GND` | `GND` |

## Arduino libraries

Install these libraries in the Arduino IDE before compiling:

- `ArduinoJson`
- `DHT sensor library`
- `Adafruit GFX Library`
- `Adafruit SSD1306`

## Demo setup

1. Log in through the app and copy the JWT token into `JWT_TOKEN`.
2. Set your Wi-Fi details and backend URL in the sketch.
3. Start the FastAPI backend and the Streamlit app.
4. Flash the sketch to the ESP32.
5. Read the auto-generated `deviceId` from Serial or the backend and use that same value when you register sensors in the dashboard.
6. Open the plant page and press `Send Water Now Command`.
7. Save a calibration in the dashboard so analytics and pump-failure checks become more accurate.

## What happens

- The dashboard queues a `water_now` command for a specific device.
- The ESP32 polls `/devices/{device_id}/next_command`.
- The relay runs for the requested pump duration when a command appears.
- The ESP32 posts `soil_raw`, `soil_moisture`, `temperature`, `humidity`, and `light` readings to `/user_sensors`.
- The OLED rotates across four pages for sensors, connectivity, last command, and short device identity.
- If Wi-Fi or the backend is unavailable, the sketch can still water from a local moisture threshold after a cooldown period.

## Demo note

This is still a demo path because it uses bearer auth copied from a user session. For a real device fleet, use per-device credentials instead of a shared user JWT.
