from __future__ import annotations

import os
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[2]

API_BASE_URL = os.getenv("BALCONYGREEN_API_URL", "http://127.0.0.1:8000")
OPEN_METEO_URL = os.getenv("BALCONYGREEN_WEATHER_URL", "https://api.open-meteo.com/v1/forecast")
DEFAULT_CAMERA_URL = os.getenv("BALCONYGREEN_CAMERA_URL", "http://192.168.1.100/capture")

JWT_SECRET_KEY = os.getenv("BALCONYGREEN_JWT_SECRET", "balconygreen-demo-secret")
COOKIE_PASSWORD = os.getenv("BALCONYGREEN_COOKIE_PASSWORD", JWT_SECRET_KEY)
DB_PATH = os.getenv("BALCONYGREEN_DB_PATH", str(PROJECT_ROOT / "balcony.db"))
