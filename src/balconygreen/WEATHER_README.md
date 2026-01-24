# Weather & Soil Data Integration

This module integrates real-time weather and soil data using the [Open-Meteo API](https://open-meteo.com/). It replaces the previous random mock data generator.

## Features
- **Real-time Weather**: Fetches Temperature, Humidity, and Rain.
- **Soil Moisture Estimation**: Uses Open-Meteo's `soil_moisture_0_to_1cm` model to estimate surface soil moisture.
- **Location Aware**: Users can configure Latitude and Longitude via the Sidebar.

## How it Works

### 1. WeatherService (`weather_service.py`)
A dedicated service class that handles the API communication.
- **Endpoint**: `https://api.open-meteo.com/v1/forecast`
- **Parameters**: `latitude`, `longitude`, `current=temperature_2m,...`
- **Error Handling**: Gracefully handles timeouts and connection errors.

### 2. Integration in `app.py`
The `SensorReader` class wraps the `WeatherService`.
- It takes `lat` and `lon` from the Streamlit sidebar input.
- Converts soil moisture from `m³/m³` (fraction) to `%` for easier reading.

## Usage
1. Run the app:
   ```bash
   streamlit run src/balconygreen/app.py
   ```
2. Open the **Sidebar** (left panel).
3. Enter your **Latitude** and **Longitude**.
   - *Default:* Berlin (52.52, 13.41)
4. Click **Start Stream** to see live data updates.

## Extending
To add more metrics (e.g., UV Index, Wind Speed):
1. Modify `WeatherService.get_current_weather` params to include new variables from Open-Meteo docs.
2. Update the return dictionary.
3. The UI will automatically display the new keys because `placeholder.json(...)` handles dynamic dictionaries.
