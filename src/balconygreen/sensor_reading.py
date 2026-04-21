from __future__ import annotations

import datetime
import unicodedata
from typing import Any, Optional

import numpy as np  # type: ignore
import requests  # type: ignore
import streamlit as st  # type: ignore

try:
    from balconygreen.settings import API_BASE_URL
except ModuleNotFoundError:
    from settings import API_BASE_URL  # type: ignore


LIVE_SENSOR_MAX_AGE_SECONDS = 10 * 60
READING_METADATA_KEYS = {"timestamp", "source", "device_id"}


class SensorReader:
    def __init__(
        self,
        access_token: Optional[str],
        source: str = "Environment Sensors",
        city: str = "London",
        api_key: Optional[str] = None,
        device_id: Optional[str] = None,
    ):
        self.access_token = access_token
        self.source = source
        self.city = city
        self.api_key = api_key
        self.device_id = device_id
        self.get_lat_lon_url = "https://geocoding-api.open-meteo.com/v1/search"
        self.headers = {"Authorization": f"Bearer {access_token}"} if access_token else {}

    @staticmethod
    def _normalize_location_name(value: Any) -> str:
        text = str(value or "").strip().lower()
        if not text:
            return ""
        normalized = unicodedata.normalize("NFKD", text)
        ascii_only = normalized.encode("ascii", "ignore").decode("ascii")
        return "".join(ch for ch in ascii_only if ch.isalnum())

    @staticmethod
    def _safe_float(value: Any) -> float | None:
        try:
            return None if value in (None, "") else float(value)
        except Exception:
            return None

    @staticmethod
    def _parse_timestamp(value: Any) -> datetime.datetime | None:
        if value in (None, ""):
            return None
        if isinstance(value, datetime.datetime):
            parsed = value
        else:
            try:
                parsed = datetime.datetime.fromisoformat(str(value).replace("Z", "+00:00"))
            except ValueError:
                return None
        if parsed.tzinfo is None:
            return parsed.replace(tzinfo=datetime.timezone.utc)
        return parsed.astimezone(datetime.timezone.utc)

    def _is_fresh_reading(self, timestamp: Any) -> bool:
        parsed = self._parse_timestamp(timestamp)
        if parsed is None:
            return False
        age_seconds = (datetime.datetime.now(tz=datetime.timezone.utc) - parsed).total_seconds()
        return age_seconds <= LIVE_SENSOR_MAX_AGE_SECONDS

    def read(self) -> dict[str, Any]:
        if self.source == "Environment Sensors":
            return self._read_user_sensors()
        if self.source == "Weather API":
            return self._read_weather_api()
        return {}

    def _read_user_sensors(self) -> dict[str, Any]:
        if not self.access_token:
            st.info("Login required to read user sensors")
            return {}

        try:
            sensor_response = requests.get(f"{API_BASE_URL}/sensors", headers=self.headers, timeout=3)
            sensor_response.raise_for_status()
            devices = sensor_response.json()
        except Exception:
            devices = []

        if self.device_id:
            devices = [
                device
                for device in devices
                if str(device.get("device_info", "")).strip() == self.device_id
            ]
        registered_sensor_names = {
            str(device.get("sensor_name", "")).strip()
            for device in devices
            if str(device.get("sensor_name", "")).strip()
        }
        use_registration_filter = bool(registered_sensor_names)

        try:
            params = {"device_id": self.device_id} if self.device_id else None
            readings_response = requests.get(f"{API_BASE_URL}/readings", params=params, headers=self.headers, timeout=3)
            readings_response.raise_for_status()
            stored_readings = readings_response.json()
        except Exception:
            stored_readings = []

        latest_by_sensor: dict[str, float] = {}
        latest_metadata: dict[str, str] = {}
        for reading in stored_readings:
            sensor_name = str(reading.get("sensor_name", "")).strip()
            if not sensor_name or sensor_name in latest_by_sensor:
                continue
            if use_registration_filter and sensor_name not in registered_sensor_names:
                continue
            if not self._is_fresh_reading(reading.get("timestamp")):
                continue
            value = self._safe_float(reading.get("value"))
            if value is None:
                continue
            latest_by_sensor[sensor_name] = value
            if not latest_metadata:
                latest_metadata = {
                    "timestamp": str(reading.get("timestamp", "") or ""),
                    "source": str(reading.get("source", "") or self.source),
                    "device_id": str(reading.get("device_id", "") or self.device_id or ""),
                }

        if not latest_by_sensor:
            return {}
        return {**latest_by_sensor, **latest_metadata}

    def _geocode_location(self) -> dict[str, Any]:
        params = {"name": self.city, "count": 5, "language": "en", "format": "json"}
        response = requests.get(self.get_lat_lon_url, params=params, timeout=10)
        response.raise_for_status()
        data = response.json()

        if "results" not in data or not data["results"]:
            raise ValueError(f"Location not found: {self.city}")

        results = [result for result in data["results"] if isinstance(result, dict)]
        normalized_query = self._normalize_location_name(self.city)
        location = next(
            (
                result
                for result in results
                if self._normalize_location_name(result.get("name")) == normalized_query
            ),
            results[0],
        )
        country = str(location.get("country_code") or location.get("country") or "").strip()
        matched_name = str(location.get("name") or self.city).strip() or self.city
        matched_label = f"{matched_name}, {country}" if country else matched_name
        return {
            "latitude": location["latitude"],
            "longitude": location["longitude"],
            "matched_location_label": matched_label,
            "matched_location_type": (
                "exact"
                if self._normalize_location_name(location.get("name")) == normalized_query
                else "closest"
            ),
            "query_location": str(self.city or "").strip(),
        }

    def _read_weather_api(self) -> dict[str, Any]:
        try:
            geocoded = self._geocode_location()
            latitude = float(geocoded["latitude"])
            longitude = float(geocoded["longitude"])
            params = {
                "latitude": latitude,
                "longitude": longitude,
                "current": [
                    "temperature_2m",
                    "precipitation_probability",
                    "wind_speed_10m",
                ],
                "hourly": [
                    "temperature_2m",
                    "relative_humidity_2m",
                    "shortwave_radiation",
                    "precipitation",
                    "precipitation_probability",
                    "wind_speed_10m",
                ],
                "timezone": "auto",
            }
            response = requests.get(self.api_key, params=params, timeout=5)
            response.raise_for_status()
            data = response.json()

            current = data.get("current", {})
            hourly = data["hourly"]
            window = 6
            temperatures = hourly.get("temperature_2m", [])[:window]
            humidities = hourly.get("relative_humidity_2m", [])[:window]
            light_levels = hourly.get("shortwave_radiation", [])[:window]
            rainfall = hourly.get("precipitation", [])[:window]
            rain_probabilities = hourly.get("precipitation_probability", [])[:window]
            wind_speeds = hourly.get("wind_speed_10m", [])[:window]

            weather_temp = float(np.mean(temperatures))
            weather_humidity = float(np.mean(humidities))
            weather_light = float(np.mean(light_levels) * 120)
            forecast_rain = float(np.sum(rainfall))
            current_temp = float(current.get("temperature_2m", temperatures[0] if temperatures else weather_temp))
            current_wind_speed = float(current.get("wind_speed_10m", wind_speeds[0] if wind_speeds else 0.0))
            rain_chance = float(current.get("precipitation_probability", max(rain_probabilities) if rain_probabilities else 0.0))

            return {
                "temperature": weather_temp,
                "humidity": weather_humidity,
                "light": weather_light,
                "weather_temp_c": weather_temp,
                "weather_humidity_pct": weather_humidity,
                "forecast_rain_mm": forecast_rain,
                "current_temp_c": current_temp,
                "current_wind_speed_kmh": current_wind_speed,
                "rain_chance_pct": rain_chance,
                "matched_location_label": geocoded["matched_location_label"],
                "matched_location_type": geocoded["matched_location_type"],
                "query_location": geocoded["query_location"],
            }
        except Exception as exc:
            st.warning(f"Weather API error: {exc}")
            return {}

    def send_to_api(self, readings: dict[str, Any], source: str):
        if not self.access_token:
            return

        device_id = str(readings.get("device_id", "") or self.device_id or "").strip() or None
        payloads = []
        for key, value in readings.items():
            if key in READING_METADATA_KEYS:
                continue
            numeric_value = self._safe_float(value)
            if numeric_value is None:
                continue
            payloads.append(
                {
                    "sensor_name": key,
                    "value": numeric_value,
                    "source": source,
                    "device_id": device_id,
                }
            )
        if not payloads:
            return
        headers = {"Authorization": f"Bearer {self.access_token}"}

        for payload in payloads:
            try:
                requests.post(f"{API_BASE_URL}/user_sensors", json=payload, headers=headers, timeout=3)
            except Exception as exc:
                st.warning(f"Failed to send {payload['sensor_name']} to FastAPI: {exc}")
