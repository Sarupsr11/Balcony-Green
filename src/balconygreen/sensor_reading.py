import requests  # type: ignore
import streamlit as st  # type: ignore
import random
from typing import Any, Dict, Optional
import numpy as np # type: ignore

FASTAPI_URL = "http://127.0.0.1:8000"


# =========================
# SENSOR READER (USER DEVICES OR WEATHER API)
# =========================
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

        # ✅ ADD: headers from access token
        self.headers = (
            {"Authorization": f"Bearer {access_token}"}
            if access_token else {}
        )

    def read(self) -> Dict[str, float]:
        if self.source == "Environment Sensors":
            return self._read_user_sensors()
        elif self.source == "Weather API":
            return self._read_weather_api()
        return {}
    


    # -------------------------
    # USER SENSORS
    # -------------------------
    def _read_user_sensors(self) -> Dict[str, float]:
        """Fetch readings from user-registered devices (simulated here)"""
        if not self.access_token:
            st.info("Login required to read user sensors")
            return {}
        

        try:
            # ✅ user_id REMOVED — backend infers from token
            response = requests.get(
                f"{FASTAPI_URL}/readings",
                headers=self.headers,
                timeout=3,
            )
            devices = response.json()
        except Exception:
            devices = []

        readings = {}
        for d in devices:
            sensor_name = d["sensor_name"]

            # Simulated readings
            if sensor_name == "temperature":
                readings[sensor_name] = round(random.uniform(20, 30), 2)
            elif sensor_name == "humidity":
                readings[sensor_name] = round(random.uniform(40, 70), 2)
            elif sensor_name == "soil_moisture":
                readings[sensor_name] = round(random.uniform(10, 60), 2)
            elif sensor_name == "soil_ph":
                readings[sensor_name] = round(random.uniform(5.5, 7.5), 2)

        return readings

    # -------------------------
    # WEATHER API
    # -------------------------

    

    def _geocode_location(self):
        
        params = {
            "name": self.city,
            "count": 1,
            "language": "en",
            "format": "json"
        }

        r = requests.get(self.get_lat_lon_url, params=params, timeout=10)
        r.raise_for_status()
        data = r.json()

        if "results" not in data or not data["results"]:
            raise ValueError(f"Location not found: {self.city}")

        loc = data["results"][0]
        return loc["latitude"], loc["longitude"], loc["name"], loc.get("country")

    def _read_weather_api(self) -> Dict[str, float]:
        # if not self.api_key:
        #     st.warning("Weather API key not provided")
        #     return {}

        try:
            lat, lon, name, country = self._geocode_location()
            params = {
                "latitude": lat,
                "longitude": lon,
                "hourly": [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "shortwave_radiation"
                ],
                "timezone": "auto"
            }
            
            data = requests.get(self.api_key, params, timeout=5).json()
            
            return {
                "temperature": np.mean(data["hourly"]["temperature_2m"]),
                "humidity": np.mean(data["hourly"]["relative_humidity_2m"]),
            }
        except Exception as e:
            st.warning(f"Weather API error: {e}")
            return {}

    # -------------------------
    # SEND TO FASTAPI
    # -------------------------
    def send_to_api(self, readings: Dict[str, Any], source: str):
        if not self.access_token:
            return  # guests do not save data

        
        payloads = [
            {"sensor_name": k, "value": v, "source": source} for k, v in readings.items()
        ]

        headers = {"Authorization": f"Bearer {self.access_token}"}

        for payload in payloads:
            try:
                r = requests.post(
                    f"{FASTAPI_URL}/user_sensors",
                    json=payload,  # ✅ must be json, not data
                    headers=headers,
                    timeout=3
                )
                print(r.status_code, r.text)  # debug
            except Exception as e:
                st.warning(f"Failed to send {payload['sensor_name']} to FastAPI: {e}")
