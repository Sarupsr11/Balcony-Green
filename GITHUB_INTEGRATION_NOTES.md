# GitHub Integration Notes

This folder is the dumped GitHub codebase with local integration work added on top.

## Added locally

- Trained watering AI artifacts under `src/balconygreen/models/watering_ai/`
- Watering inference service in `src/balconygreen/watering_ai.py`
- Dashboard integration in `src/balconygreen/dashboard.py`
- Streamlit entry point in `src/balconygreen/app.py`
- Backend fixes for sensors, readings, and image upload metadata
- Relay command queue for `water_now` plus ESP32 polling example under `examples/esp32_water_now_demo/`
- Calibration API and dashboard wizard for each plant and soil sensor
- Feedback logging for labels like `better`, `worse`, `overwatered`, and `underwatered`
- Water usage analytics and pump-failure detection based on real telemetry after executed commands
- ESP32 offline fallback watering mode for Wi-Fi/API outages

## Current watering AI inputs

- `soil_moisture_pct`
- `soil_raw`
- `temperature_c`
- `humidity_pct`
- `light_lux`
- `weather_temp_c`
- `weather_humidity_pct`
- `forecast_rain_mm`
- `disease_score`
- `disease_confidence`
- recent moisture/raw trends
- time-of-day features

## Known environment requirements

- `streamlit-cookies-manager` is required for the auth UI
- `torch`, `torchvision`, and `timm` are required for tomato disease inference
- `scikit-learn`, `pandas`, and `joblib` are required for the watering model
