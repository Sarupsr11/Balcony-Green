# Real-Time Weather & Location Integration

This module transforms the app from a simulation into a real-world monitor by integrating **Open-Meteo Data** and **Location Services**.

## Overview of Key Components

### 1. `WeatherService` (`weather_service.py`)
**Role:** The "Data Fetcher".
It connects to the [Open-Meteo API](https://open-meteo.com/) (Free, No Key) to get meteorological data.
- **Why Open-Meteo?** It provides a specific model for **Soil Moisture**, which is critical for this project.
- **Data Points:**
  - `temperature_2m`: Air temp (°C).
  - `relative_humidity_2m`: Air humidity (%).
  - `soil_moisture_0_to_1cm`: Volumetric soil water content ($m^3/m^3$). *We convert this to % for display.*
  - `rain`: Current precipitation (mm).

### 2. `LocationService` (`location_service.py`)
**Role:** The "Navigator".
It provides three ways to determine where the plant is located:
- **IP Location**: Uses `ip-api.com` to guess location based on internet connection (Fallback).
- **City Search**: Uses Open-Meteo Geocoding API to find coordinates from names (e.g., "Paris").
- **Reverse Geocoding**: Uses OpenStreetMap (Nominatim) to turn coordinates back into a city name for the UI.

### 3. Frontend Integration (`app.py`)
**Role:** The "Coordinator".
The logic flow for teammates to understand:

1.  **Session State**: We store `lat`, `lon`, and `loc_name` in `st.session_state` so they persist when the app reloads.
2.  **Sidebar Control**:
    - **Manual**: Direct entry.
    - **Search City**: Calls `LocationService.search_city(query)`.
    - **Auto-Locate**: Uses `streamlit-js-eval` to ask the browser for GPS permissions.
3.  **Data Flow**:
    ```text
    [Sidebar inputs] -> [st.session_state] -> [WeatherReader] -> [UI Dashboard]
    ```

## Usage Guide (for Testing)

1.  **Start the App**:
    ```bash
    streamlit run src/balconygreen/app.py
    ```
2.  **Select Location Source**:
    - Go to the Sidebar.
    - Choose **"Auto-Locate"** to test GPS (Allow permission in browser).
    - OR Choose **"Search City"** and type your city.
3.  **Verify**:
    - The "Ambient Weather" card should show the correct **City Name**.
    - The **Temp** and **Humidity** should match real conditions outside.

## How to Extend

### Adding New Weather Metrics (e.g., UV Index)
1.  **Edit `weather_service.py`**:
    - Add `uv_index` to the API `params` list.
    - Add it to the return dictionary.
2.  **Edit `app.py`**:
    - Add a new `st.metric("UV Index", ...)` card in the `weather_col` section.

### Switching Location Providers
If we need more precision than IP-API:
- Edit `LocationService.get_ip_location` to use a paid service like ipinfo.io (would require an API Key).
