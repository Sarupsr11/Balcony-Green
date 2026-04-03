# ESP32 Water Now Demo

This example lets an ESP32 poll the FastAPI backend for queued `water_now` commands, post soil telemetry, and fall back to local watering when Wi-Fi or the API is down.

## Demo setup

1. Register your ESP32 sensors in the Streamlit app using the same `device_info` value, for example `esp32-balcony-1`.
2. Put that same value into `DEVICE_ID` in `esp32_water_now_demo.ino`.
3. Log in through the app and copy the JWT token into `JWT_TOKEN`.
4. Start the FastAPI backend and the Streamlit app.
5. Flash the sketch to the ESP32.
6. Open the plant page and press `Send Water Now Command`.
7. Save a calibration in the dashboard so analytics and pump-failure checks become more accurate.

## What happens

- The dashboard queues a `water_now` command for a specific device.
- The ESP32 polls `/devices/{device_id}/next_command`.
- When a command appears, the relay is switched for the requested pump duration.
- The ESP32 posts `soil_raw` and `soil_moisture` readings to `/user_sensors` with its `device_id`.
- The ESP32 sends `/devices/{device_id}/ack_command` so the dashboard can show the command as executed.
- If Wi-Fi or the backend is unavailable, the sketch can still water from a local moisture threshold after a cooldown period.

## Demo note

This is a secure-enough demo path because it still uses bearer auth, but for a real product you would usually give each ESP32 its own device credential instead of reusing a user JWT.
