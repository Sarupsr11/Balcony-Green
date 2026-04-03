from __future__ import annotations

import random
from typing import Any, Optional

import numpy as np  # type: ignore
import requests  # type: ignore
import streamlit as st  # type: ignore

try:
    from balconygreen.settings import API_BASE_URL
except ModuleNotFoundError:
    from settings import API_BASE_URL  # type: ignore


class SensorReader:
    def __init__(
        self,
        access_token: Optional[str],
        source: str = "Environment Sensors",
        city: str = "London",
        api_key: Optional[str] = None,
    ):
        self.access_token = access_token
        self.source = source
        self.city = city
        self.api_key = api_key
        self.get_lat_lon_url = "https://geocoding-api.open-meteo.com/v1/search"
        self.headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}

    def read(self) -> dict[str, float]:
        if self.source == "Environment Sensors":
            return self._read_user_sensors()
        if self.source == "Weather API":
            return self._read_weather_api()
        return {}

    def _read_user_sensors(self) -> dict[str, float]:
        if not self.access_token:
            st.info("Login required to read user sensors")
            return {}

        try:
            sensor_response = requests.get(f"{API_BASE_URL}/sensors", headers=self.headers, timeout=3)
            sensor_response.raise_for_status()
            devices = sensor_response.json()
        except Exception:
            devices = []

        try:
            readings_response = requests.get(f"{API_BASE_URL}/readings", headers=self.headers, timeout=3)
            readings_response.raise_for_status()
            stored_readings = readings_response.json()
        except Exception:
            stored_readings = []

        latest_by_sensor: dict[str, float] = {}
        for reading in stored_readings:
            sensor_name = str(reading.get("sensor_name", "")).strip()
            if sensor_name and sensor_name not in latest_by_sensor:
                latest_by_sensor[sensor_name] = float(reading.get("value", 0.0))

        readings: dict[str, float] = {}
        for device in devices:
            sensor_name = device["sensor_name"]
            if sensor_name in latest_by_sensor:
                readings[sensor_name] = latest_by_sensor[sensor_name]
                continue
            if sensor_name == "temperature":
                readings[sensor_name] = round(random.uniform(20, 30), 2)
            elif sensor_name == "humidity":
                readings[sensor_name] = round(random.uniform(40, 70), 2)
            elif sensor_name == "soil_moisture":
                readings[sensor_name] = round(random.uniform(10, 60), 2)
            elif sensor_name == "soil_ph":
                readings[sensor_name] = round(random.uniform(5.5, 7.5), 2)
            elif sensor_name == "light":
                readings[sensor_name] = round(random.uniform(1500, 18000), 2)

        return readings

    def _geocode_location(self):
        params = {"name": self.city, "count": 1, "language": "en", "format": "json"}
        response = requests.get(self.get_lat_lon_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "results" not in data or not data["results"]:
            raise ValueError(f"Location not found: {self.city}")

        location = data["results"][0]
        return location["latitude"], location["longitude"]

    def _read_weather_api(self) -> dict[str, float]:
        try:
            latitude, longitude = self._geocode_location()
            params = {
                "latitude": latitude,
                "longitude": longitude,
                "hourly": [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "shortwave_radiation",
                ],
                "timezone": "auto",
            }
            data = requests.get(self.api_key, params=params, timeout=5).json()
            return {
                "temperature": float(np.mean(data["hourly"]["temperature_2m"])),
                "humidity": float(np.mean(data["hourly"]["relative_humidity_2m"])),
                "light": float(np.mean(data["hourly"]["shortwave_radiation"]) * 120),
            }
        except Exception as exc:
            st.warning(f"Weather API error: {exc}")
            return {}

    def send_to_api(self, readings: dict[str, Any], source: str):
        if not self.access_token:
            return

        payloads = [{"sensor_name": key, "value": value, "source": source} for key, value in readings.items()]
        headers = {"Authorization": f"Bearer {self.access_token}"}

        for payload in payloads:
            try:
                requests.post(f"{API_BASE_URL}/user_sensors", json=payload, headers=headers, timeout=3)
            except Exception as exc:
                st.warning(f"Failed to send {payload['sensor_name']} to FastAPI: {exc}")
