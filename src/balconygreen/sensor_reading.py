import json
import logging
import random
import time
from pathlib import Path
from PIL import Image # type: ignore
import io
import os

import numpy as np  # type: ignore
import requests  # type: ignore

FASTAPI_URL =  os.getenv("FASTAPI_URL","https://balconygreen-production.up.railway.app")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# =========================
# WEATHER CACHE MANAGER
# =========================
class WeatherCache:
    def __init__(self, cache_dir: str = "weather_cache"):
        self.cache_dir = Path(cache_dir)
        self.cache_dir.mkdir(exist_ok=True)
        logger.debug(f"WeatherCache initialized with cache_dir: {cache_dir}")

    def get_cached_weather(self, city: str) -> dict[str, float] | None:
        cache_file = self.cache_dir / f"{city.lower().replace(' ', '_')}.json"
        logger.debug(f"Attempting to get cached weather for city: {city}")
        if cache_file.exists():
            try:
                with open(cache_file) as f:
                    data = json.load(f)
                if time.time() - data.get("timestamp", 0) < 24 * 3600:
                    logger.debug(f"Cache hit for {city}, returning cached data")
                    return data.get("readings", {})
                else:
                    logger.debug(f"Cache expired for {city}")
            except Exception as e:
                logger.error(f"Error reading cache file for {city}: {e}")
        logger.debug(f"No valid cache for {city}")
        return None

    def cache_weather_data(self, city: str, readings: dict[str, float]):
        cache_file = self.cache_dir / f"{city.lower().replace(' ', '_')}.json"
        data = {"timestamp": time.time(), "city": city, "readings": readings}
        try:
            with open(cache_file, "w") as f:
                json.dump(data, f)
            logger.debug(f"Successfully cached weather data for {city}")
        except Exception as e:
            logger.error(f"Error caching weather data for {city}: {e}")

    def get_offline_weather(self, city: str) -> dict[str, float]:
        return {
            "temperature": 22.0 + random.uniform(-2, 2),
            "humidity": 60.0 + random.uniform(-10, 10),
        }


# =========================
# SENSOR READER
# =========================
class SensorReader:
    ESSENTIAL_KEYS = ["device_id", "device_key", "sensor_map", "device_type"]

    def __init__(
        self,
        use_simulated: bool = True,
        city: str = "London",
        api_key: str | None = None,
        devices_dir: str = "device_data/devices",
    ):
        self.use_simulated = use_simulated
        self.city = city
        self.api_key = api_key
        self.devices_dir = Path(devices_dir)
        self.weather_cache = WeatherCache()
        logger.info(f"SensorReader initialized - use_simulated={use_simulated}, city={city}")

        # Devices loaded: type -> list of device info dicts
        self.devices_by_type: dict = {"physical": [], "weather_api": []}

        # Try backend first
        self.load_devices_from_backend()

        # Fallback to local JSON files if backend fails or no devices
        if not any(self.devices_by_type.values()):
            logger.warning("No devices loaded from backend, falling back to local JSON files")
            self.load_devices_from_files()

    # -------------------------
    # Load devices from backend
    # -------------------------
    def load_devices_from_backend(self):
        try:
            response = requests.get(f"{FASTAPI_URL}/all_devices", timeout=5)
            response.raise_for_status()
            devices = response.json()
            logger.info(f"Loaded {len(devices)} devices from backend")
            for device in devices:
                sensor_map = {s: s for s in device.get("sensors", [])}  # sensor names as keys
                device_info = {
                    "device_id": device["id"],
                    "device_key": device["key"],  # not needed for reading
                    "sensor_map": sensor_map,
                    "device_type": device.get("type", "physical"),
                    "city": device.get("city"),
                }
                self.devices_by_type.setdefault(device_info["device_type"], []).append(device_info)

        except Exception as e:
            logger.error(f"Failed to load devices from backend: {e}")

    # -------------------------
    # Load devices from JSON files
    # -------------------------
    def load_devices_from_files(self):
        if not self.devices_dir.exists():
            logger.warning(f"Devices folder does not exist: {self.devices_dir}")
            return

        for file in self.devices_dir.glob("*.json"):
            try:
                device_info = self.load_device_file(file)
                device_type = device_info.get("device_type", "physical")
                self.devices_by_type.setdefault(device_type, []).append(device_info)
                logger.debug(f"Loaded device from file: {file.name}")
            except Exception as e:
                logger.warning(f"Skipping {file}: {e}")

        logger.info(
            f"Total devices loaded from files - physical: {len(self.devices_by_type.get('physical', []))}, "
            f"weather_api: {len(self.devices_by_type.get('weather_api', []))}"
        )

    # -------------------------
    # Load and validate JSON device files
    # -------------------------
    def load_device_file(self, path: Path) -> dict:
        if not path.exists():
            raise FileNotFoundError(f"{path} not found. Register device first.")
        try:
            data = json.loads(path.read_text())
            for key in self.ESSENTIAL_KEYS:
                if key not in data:
                    raise ValueError(f"Essential key '{key}' missing in {path}")
            return data
        except json.JSONDecodeError as e:
            raise ValueError(f"Invalid JSON in {path}") from e

    # -------------------------
    # Main loop remains unchanged
    # -------------------------
    def run_forever(self, interval: float = 60.0):
        while True:
            for device in self.devices_by_type.get("physical", []):
                logger.info(f"device info {device['sensor_map']}")
                readings = self.read(device['sensor_map'])
                if readings:
                    self.send_to_api(device, readings)

            weather_readings = self._read_weather_api_for_city(self.city)
            if weather_readings:
                for device in self.devices_by_type.get("weather_api", []):
                    self.send_to_api_weather(device, weather_readings)

            time.sleep(interval)


    # -------------------------
    # Read sensor values
    # -------------------------
    def read(self, sensor_map: dict[str, str]) -> dict[str, float]:
        logger.debug(f"Reading sensors: {sensor_map}")
        readings = {}
        for sensor_name in sensor_map:
            if self.use_simulated:
                readings[sensor_name] = self._generate_simulated_reading(sensor_name)
            else:
                real_value = self._get_real_sensor_reading(sensor_name)
                readings[sensor_name] = real_value if real_value is not None else self._generate_simulated_reading(sensor_name)
        logger.debug(f"Sensor readings complete: {readings}")
        return readings

    # -------------------------
    # Real sensor reading (stub)
    # -------------------------
    def _get_real_sensor_reading(self, sensor_name: str) -> float | None:
        """
        Replace with actual sensor reading code:
        e.g., read_temp_from_dht22(), read_humidity(), etc.
        """
        return None

    # -------------------------
    # Simulated sensor readings
    # -------------------------
    def _generate_simulated_reading(self, sensor_name: str) -> float:
        if sensor_name == "temperature":
            return round(random.uniform(20, 30), 2)
        elif sensor_name == "humidity":
            return round(random.uniform(40, 70), 2)
        elif sensor_name == "soil_moisture":
            return round(random.uniform(10, 60), 2)
        elif sensor_name == "soil_ph":
            return round(random.uniform(5.5, 7.5), 2)
        elif sensor_name == "light":
            return round(random.uniform(0, 100), 2)
        
        elif sensor_name == "camera":
            # Create random image
            arr = np.random.randint(0, 256, (480, 640, 3), dtype=np.uint8)
            img = Image.fromarray(arr)

            buffer = io.BytesIO()
            img.save(buffer, format="JPEG")
            buffer.seek(0)

            return buffer  # return bytes buffer


    # -------------------------
    # Weather API reading
    # -------------------------
    def _read_weather_api_for_city(self, city: str) -> dict[str, float]:
        logger.debug(f"Reading weather API data for city: {city}")
        cached = self.weather_cache.get_cached_weather(city)
        if cached:
            logger.info(f"Using cached weather data for {city}")
            return cached
        try:
            # Example placeholder for real weather API request
            # Replace self.api_key with actual URL + key
            logger.debug(f"Fetching fresh weather data from API for {city}")
            params = {"latitude": 0, "longitude": 0, "hourly": ["temperature_2m", "relative_humidity_2m"], "timezone": "auto"}
            data = requests.get(self.api_key, params=params).json()
            readings = {
                "temperature": float(np.mean(data["hourly"]["temperature_2m"])),
                "humidity": float(np.mean(data["hourly"]["relative_humidity_2m"])),
            }
            logger.info(f"Successfully fetched weather data for {city}: {readings}")
            self.weather_cache.cache_weather_data(city, readings)
            return readings
        except Exception as e:
            logger.error(f"Error fetching weather API data for {city}: {e}. Using offline data.")
            return self.weather_cache.get_offline_weather(city)

    # -------------------------
    # Send readings to backend
    # -------------------------
    def send_to_api(self, device: dict, readings: dict[str, float]):
        logger.debug(f"Sending readings to API for device: {device.get('device_id')}")


        headers = {"Authorization": f"Bearer {device['device_key']}"}
        sensor_map = device["sensor_map"]

        for sensor_name, value in readings.items():

            if sensor_name not in sensor_map:
                continue

            sensor_name = sensor_map[sensor_name]
            

            # 📷 CAMERA SENSOR
            if sensor_name == "camera":
                try:
                    image_buffer = value  # this is BytesIO

                    files = {
                        "file": ("camera.jpg", image_buffer, "image/jpeg")
                    }

                    r = requests.post(
                        f"{FASTAPI_URL}/camera/upload/{sensor_name}",
                        headers=headers,
                        files=files,
                        timeout=10
                    )

                    logger.info(
                        f"[{device['device_id']}] CAMERA uploaded | status: {r.status_code}"
                    )

                except Exception as e:
                    logger.error(
                        f"[{device['device_id']}] Failed to send camera image: {e}"
                    )

            # 🌡️ NORMAL NUMERIC SENSOR
            else:
                logging.info(sensor_map)
                payload = {
                    "sensor_id": sensor_name,
                    "value": value,
                    "source": "physical"
                }

                try:
                    r = requests.post(
                        f"{FASTAPI_URL}/sensor_readings",
                        json=payload,
                        headers=headers,
                        timeout=3
                    )

                    logger.info(
                        f"[{device['device_id']}] {sensor_map} -> {value} | status: {r.status_code}"
                    )

                except Exception as e:
                    logger.error(
                        f"[{device['device_id']}] Failed to send {sensor_name}: {e}"
                    )


    def send_to_api_weather(self, device: dict, readings: dict[str, float]):
        logger.debug(f"Sending weather readings to API for device: {device.get('device_id')}")
        headers = {"Authorization": f"Bearer {device['device_key']}"}
        sensor_map = device["sensor_map"]
        for sensor_name, value in readings.items():
            if sensor_name not in sensor_map:
                continue
            payload = {"sensor_id": sensor_map[sensor_name], "value": value, "source": "weather api"}
            try:
                r = requests.post(f"{FASTAPI_URL}/sensor_readings", json=payload, headers=headers, timeout=3)
                logger.info(f"[{device['device_id']}] {sensor_name} -> {value} | status: {r.status_code}")
            except Exception as e:
                logger.error(f"[{device['device_id']}] Failed to send {sensor_name}: {e}")
