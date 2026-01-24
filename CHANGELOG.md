# Changelog

All notable changes to this project will be documented in this file.

## [Unreleased] - 2026-01-24

### Added
- **Weather Integration**: Added `src/balconygreen/weather_service.py` to fetch real-time weather data (Temperature, Humidity, Rain, Soil Moisture/Ground) using the Open-Meteo API.
- **Location Settings**: Added a Sidebar in the Streamlit app to configure Latitude and Longitude.
- **Documentation**: 
    - `current_status.md`: Overview of project status, architecture, and roadmap.
    - `UPDATE.md`: Detailed log of the latest specific update session.
    - `src/balconygreen/WEATHER_README.md`: Technical documentation for the weather service.
- **Testing**: Added `tests/test_weather_integration.py` to validate API connectivity.
- **Setup**: Added `setup.sh` for easy environment initialization.

### Changed
- **App Architecture (`src/balconygreen/app.py`)**:
    - Split sensor data processing into `WeatherReader` (API) and `HardwareSensorReader` (Mock/Local).
    - Redesigned "Live Monitoring" UI to display Ambient Weather and Plant Sensor data in separate columns.
    - Replaced raw JSON display with graphical metrics (`st.metric`).
- **Dependencies**: Updated `pyproject.toml` (locally) or `setup.sh` to include `requests` and ML libraries.

### Fixed
- Addressed missing dependencies for running the `model-making` branch locally.
