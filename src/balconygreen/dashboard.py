from __future__ import annotations

import datetime
import logging
import tempfile
from pathlib import Path
from typing import Any, Optional

import pandas as pd
import requests  # type: ignore
import streamlit as st  # type: ignore
from PIL import Image  # type: ignore

try:
    from balconygreen.camera_sensor import ExternalCameraSensor, ImageInput
    from balconygreen.sensor_reading import SensorReader
    from balconygreen.settings import API_BASE_URL, DEFAULT_CAMERA_URL, OPEN_METEO_URL
    from balconygreen.watering_ai import WateringAIService
except ModuleNotFoundError:
    from camera_sensor import ExternalCameraSensor, ImageInput  # type: ignore
    from sensor_reading import SensorReader  # type: ignore
    from settings import API_BASE_URL, DEFAULT_CAMERA_URL, OPEN_METEO_URL  # type: ignore
    from watering_ai import WateringAIService  # type: ignore

try:
    from streamlit_js_eval import get_geolocation as _get_browser_location
    _GPS_AVAILABLE = True
except ImportError:
    _GPS_AVAILABLE = False


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CKPT_PATH_TOMATO_11 = PROJECT_ROOT / "disease-detection" / "Tomatoes" / "Models" / "efficientnet_best_multiple_sources.pth"
CKPT_PATH_TOMATO_2 = PROJECT_ROOT / "disease-detection" / "Tomatoes" / "Models" / "efficientnet_binary_best_multiple_sources.pth"
LOGGER = logging.getLogger(__name__)
LIVE_REFRESH_INTERVAL_SECONDS = 30
LIVE_REFRESH_TABS = {"Overview"}
LIVE_SENSOR_MAX_AGE_MINUTES = 10


class StreamController:
    def __init__(self) -> None:
        if "streaming" not in st.session_state:
            st.session_state.streaming = False

    def controls(self) -> None:
        st.session_state.streaming = st.checkbox(
            "Auto refresh live data",
            value=bool(st.session_state.get("streaming", False)),
            key="streaming_toggle",
        )
        if st.button("Refresh now", use_container_width=True):
            st.session_state.force_single_read = True

    def is_streaming(self) -> bool:
        return bool(st.session_state.streaming)


class BalconyGreenApp:
    def __init__(self, access_token: str | None):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
        defaults = {
            "predicted_plant": "Tomato",
            "latest_readings": None,
            "latest_snapshot_device_id": "",
            "latest_backend_snapshot_meta": None,
            "sensor_history": [],
            "uploaded_image": None,
            "latest_disease_prediction": {"label": "healthy", "confidence": 0.0, "top_results": []},
            "force_single_read": False,
            "camera_url": DEFAULT_CAMERA_URL,
            "active_device_id": "",
            "last_queued_command_id": None,
            "last_saved_at": None,
            "sensor_mode": "ESP32 + Weather API",
            "session_expired": False,
            "weather_city": "London",
            "latest_weather_context": None,
            "latest_weather_context_at": None,
            "latest_weather_context_city": None,
            "_gps_requested": False,
            "_gps_error": None,
            "_gps_request_nonce": 0,
            "active_dashboard_tab": "Overview",
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

        self.camera = ExternalCameraSensor(st.session_state["camera_url"])
        self.image_input = ImageInput(self.camera, self.access_token)
        self.sensor_reader: Optional[SensorReader] = None
        self.weather_reader: Optional[SensorReader] = None
        self.stream_controller = StreamController()
        self.watering_ai = WateringAIService()
        self.classifier_all = BalconyGreenApp.load_classifier_all()
        self.classifier_binary = BalconyGreenApp.load_classifier_binary()

    @staticmethod
    @st.cache_resource
    def load_classifier_all():
        try:
            try:
                from balconygreen.inference import EfficientNetClassifier
            except ModuleNotFoundError:
                from inference import EfficientNetClassifier  # type: ignore
            return EfficientNetClassifier(model_path=CKPT_PATH_TOMATO_11, num_classes=11)
        except Exception as exc:
            LOGGER.warning("Failed to load multiclass disease model: %s", exc)
            return None

    @staticmethod
    @st.cache_resource
    def load_classifier_binary():
        try:
            try:
                from balconygreen.inference import EfficientNetClassifier
            except ModuleNotFoundError:
                from inference import EfficientNetClassifier  # type: ignore
            return EfficientNetClassifier(model_path=CKPT_PATH_TOMATO_2, num_classes=2)
        except Exception as exc:
            LOGGER.warning("Failed to load binary disease model: %s", exc)
            return None

    def _inject_styles(self) -> None:
        st.markdown(
            """
            <style>
            [data-testid="stAppViewContainer"] {background:
                radial-gradient(circle at top left, rgba(41,98,61,0.18), transparent 26%),
                linear-gradient(180deg, #0b0d12 0%, #0d1118 100%);}
            [data-testid="stSidebar"] {background: linear-gradient(180deg, #10141d 0%, #0f131b 100%);}
            .block-container {max-width: 1320px; padding-top: 0.85rem; padding-bottom: 1.4rem; padding-left: 1.1rem; padding-right: 1.1rem;}
            div[data-testid="stHorizontalBlock"] {gap: 0.8rem;}
            .hero-card {border:1px solid rgba(255,255,255,0.08); background:linear-gradient(180deg, rgba(13,16,23,0.98), rgba(17,21,30,0.94)); padding:1.05rem 1.2rem; border-radius:24px; box-shadow:0 14px 30px rgba(0,0,0,0.22);}
            .hero-title {font-size:2.45rem; font-weight:820; color:#f7f8fb; margin-bottom:0.2rem; line-height:1.03;}
            .hero-subtitle {color:#b9bfcb; line-height:1.5; margin:0;}
            .section-heading {font-size:1.65rem; font-weight:780; color:#f5f7fb; margin:0.8rem 0 0.2rem;}
            .section-subheading {font-size:1.18rem; font-weight:760; color:#f7f8fb; margin:0.15rem 0 0.6rem;}
            .pill {display:inline-flex; padding:0.28rem 0.62rem; border-radius:999px; font-size:0.8rem; margin:0.4rem 0.35rem 0 0; border:1px solid rgba(255,255,255,0.06);}
            .good {background:rgba(92,187,132,0.14); color:#d7f6e1;}
            .warn {background:rgba(224,179,62,0.14); color:#ffe6a5;}
            .bad {background:rgba(230,96,96,0.15); color:#ffd4d4;}
            .panel-card {border:1px solid rgba(255,255,255,0.08); background:#151922; border-radius:20px; padding:0.8rem 0.95rem; margin-bottom:0.75rem;}
            .panel-title {font-size:1.03rem; font-weight:680; color:#f5f9f6; margin-bottom:0.25rem;}
            .panel-muted {color:#aeb5c0; font-size:0.9rem; line-height:1.45;}
            .device-detail-card {border:1px solid rgba(69,143,233,0.18); background:#1a3552; border-radius:18px; padding:0.85rem 1rem; margin:0.65rem 0 0.8rem;}
            .device-detail-title {color:#4ea0ff; font-size:1.2rem; font-weight:760; margin-bottom:0.55rem;}
            .device-detail-line {color:#d9ecff; font-size:1rem; margin:0;}
            [data-testid="stMetric"] {background:linear-gradient(180deg, rgba(21,25,34,0.98), rgba(18,22,30,0.92)); border:1px solid rgba(255,255,255,0.06); padding:0.72rem 0.82rem; border-radius:18px;}
            [data-baseweb="tab"] {background:rgba(255,255,255,0.04); border-radius:14px; padding:0.46rem 0.78rem; height:auto;}
            div[data-baseweb="select"] > div,
            div[data-baseweb="input"] > div {
                background: #232632;
                border-color: rgba(232, 77, 77, 0.9);
                border-radius: 16px;
                min-height: 2.95rem;
            }
            .stButton > button {
                border-radius: 12px;
                border: 0;
                background: #21a9f5;
                color: white;
                font-weight: 700;
            }
            [data-testid="stExpander"] {
                border: 1px solid rgba(255,255,255,0.08);
                border-radius: 18px;
                background: #171b24;
            }
            [data-testid="stSuccess"] {
                background: rgba(22, 82, 46, 0.92);
                border: 1px solid rgba(102, 224, 145, 0.22);
                border-radius: 16px;
            }
            [data-testid="stInfo"] {
                background: rgba(26, 53, 82, 0.92);
                border: 1px solid rgba(98, 166, 255, 0.18);
                border-radius: 16px;
            }
            .hs-card {
                border-radius: 22px; padding: 0.95rem 1.15rem;
                margin-bottom: 0.8rem; border: 1px solid rgba(255,255,255,0.09);
                background: linear-gradient(160deg, rgba(17,21,30,0.98), rgba(13,16,23,0.94));
            }
            .hs-label { font-size:0.82rem; font-weight:600; letter-spacing:0.07em; text-transform:uppercase; color:#8891a0; margin-bottom:0.3rem; }
            .hs-score-good  { font-size:3.6rem; font-weight:900; color:#5cbb84; line-height:1; }
            .hs-score-warn  { font-size:3.6rem; font-weight:900; color:#e0b33e; line-height:1; }
            .hs-score-bad   { font-size:3.6rem; font-weight:900; color:#e66060; line-height:1; }
            .hs-trend-up    { font-size:1rem; color:#5cbb84; margin-left:0.5rem; }
            .hs-trend-down  { font-size:1rem; color:#e66060; margin-left:0.5rem; }
            .hs-trend-flat  { font-size:1rem; color:#8891a0; margin-left:0.5rem; }
            .hs-bar-wrap    { background:rgba(255,255,255,0.07); border-radius:999px; height:7px; margin:0.6rem 0 0.9rem; overflow:hidden; }
            .hs-bar-fill    { height:7px; border-radius:999px; transition:width 0.4s ease; }
            .hs-breakdown   { display:flex; gap:1.1rem; flex-wrap:wrap; margin-top:0.5rem; }
            .hs-component   { font-size:0.83rem; color:#aeb5c0; }
            .hs-component b { color:#d8dde6; }
            .hs-inline-good { color:#5cbb84; font-weight:700; }
            .hs-inline-warn { color:#e0b33e; font-weight:700; }
            .hs-inline-bad  { color:#e66060; font-weight:700; }
            .compact-grid {display:grid; grid-template-columns:repeat(2, minmax(0, 1fr)); gap:0.75rem 1rem; margin-top:0.15rem;}
            .compact-item {padding:0.05rem 0;}
            .compact-label {display:block; font-size:0.78rem; text-transform:uppercase; letter-spacing:0.05em; color:#7d8796; margin-bottom:0.15rem;}
            .compact-value {display:block; font-size:1rem; font-weight:680; color:#eef2f8; line-height:1.25;}
            .compact-grid.single-column {grid-template-columns:1fr;}
            </style>
            """,
            unsafe_allow_html=True,
        )

    def _api_get(self, path: str, params: dict[str, Any] | None = None) -> Any | None:
        if not self.headers:
            return None
        try:
            response = requests.get(f"{API_BASE_URL}{path}", params=params, headers=self.headers, timeout=5)
            if response.status_code == 401:
                st.session_state["session_expired"] = True
            response.raise_for_status()
            st.session_state["session_expired"] = False
            return response.json()
        except requests.exceptions.RequestException as exc:
            LOGGER.warning("GET %s failed: %s", path, exc)
            return None
        except ValueError as exc:
            LOGGER.warning("GET %s returned non-JSON response: %s", path, exc)
            return None

    def _api_post(self, path: str, payload: dict[str, Any]) -> Any | None:
        if not self.headers:
            return None
        try:
            response = requests.post(f"{API_BASE_URL}{path}", json=payload, headers=self.headers, timeout=5)
            if response.status_code == 401:
                st.session_state["session_expired"] = True
            response.raise_for_status()
            st.session_state["session_expired"] = False
            return response.json()
        except requests.exceptions.RequestException as exc:
            LOGGER.warning("POST %s failed: %s", path, exc)
            return None
        except ValueError as exc:
            LOGGER.warning("POST %s returned non-JSON response: %s", path, exc)
            return None

    def _safe_float(self, value: Any) -> float | None:
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

    def _snapshot_age_seconds(self, snapshot: dict[str, Any] | None) -> float | None:
        if not isinstance(snapshot, dict):
            return None
        parsed = self._parse_timestamp(snapshot.get("timestamp"))
        if parsed is None:
            return None
        return max(0.0, (datetime.datetime.now(tz=datetime.timezone.utc) - parsed).total_seconds())

    def _snapshot_is_stale(self, snapshot: dict[str, Any] | None) -> bool:
        age_seconds = self._snapshot_age_seconds(snapshot)
        return age_seconds is not None and age_seconds > LIVE_SENSOR_MAX_AGE_MINUTES * 60

    def _format_snapshot_age(self, snapshot: dict[str, Any] | None) -> str:
        age_seconds = self._snapshot_age_seconds(snapshot)
        if age_seconds is None:
            return "unknown"
        if age_seconds < 90:
            return f"{int(age_seconds)}s ago"
        if age_seconds < 90 * 60:
            return f"{int(round(age_seconds / 60.0))}m ago"
        if age_seconds < 48 * 60 * 60:
            return f"{age_seconds / 3600.0:.1f}h ago"
        return f"{age_seconds / 86400.0:.1f}d ago"

    def _reading_value(self, readings: dict[str, Any] | None, *keys: str) -> float | None:
        if not readings:
            return None
        for key in keys:
            value = self._safe_float(readings.get(key))
            if value is not None:
                return value
        return None

    def _calibration_review_message(
        self,
        readings: dict[str, Any] | None,
        calibration: dict[str, Any] | None,
        plant_name: str,
    ) -> str | None:
        if not readings or not calibration:
            return None

        soil = self._reading_value(readings, "soil_moisture_pct", "soil_moisture")
        raw = self._reading_value(readings, "soil_raw")
        if soil is None:
            return None

        raw_wet = self._safe_float(calibration.get("soil_raw_wet"))
        target = self._safe_float(calibration.get("moisture_target_pct"))
        notes = str(calibration.get("notes", "") or "").strip().lower()

        key = self._PLANT_ALIASES.get(plant_name.strip().lower(), "houseplant_generic")
        profile = self.watering_ai.profiles.get(key, self.watering_ai.profiles["houseplant_generic"])
        profile_threshold = float(profile["moisture_threshold_pct"])

        reasons: list[str] = []
        if soil >= 99.5:
            if raw is not None and raw_wet is not None and raw <= raw_wet + 25:
                reasons.append("soil is pegged at saturation and the raw value is at or below the saved wet point")
            else:
                reasons.append("soil is pegged at saturation")
        if target is not None and abs(target - profile_threshold) >= 5:
            reasons.append(
                f"saved target {target:.0f}% differs from the {plant_name} profile baseline of {profile_threshold:.0f}%"
            )
        if "copied from" in notes:
            reasons.append("this calibration was copied from another setup")

        if not reasons:
            return None
        return "Calibration review suggested because " + "; ".join(reasons) + "."

    @staticmethod
    def _format_missing_inputs(missing_inputs: list[str]) -> str:
        labels = {
            "light_lux": "light sensor",
            "soil_moisture_pct": "soil moisture",
            "temperature_c": "temperature",
            "humidity_pct": "humidity",
        }
        formatted = [labels.get(item, item.replace("_", " ")) for item in missing_inputs]
        return ", ".join(formatted)

    def _history_delta(self, *keys: str) -> float | None:
        history = st.session_state.get("sensor_history", [])
        if len(history) < 2:
            return None
        current = self._reading_value(history[-1], *keys)
        previous = self._reading_value(history[-2], *keys)
        if current is None or previous is None:
            return None
        return round(current - previous, 2)

    def _backend_online(self) -> bool:
        try:
            return requests.get(f"{API_BASE_URL}/health", timeout=3).status_code == 200
        except requests.exceptions.RequestException as exc:
            LOGGER.warning("Backend health check failed: %s", exc)
            return False

    _PLANT_RANGES: dict[str, dict] = {
        "tomato_indoor":      {"temp": (20, 30), "humidity": (50, 70), "light_ref": 18000},
        "basilikum":          {"temp": (18, 30), "humidity": (50, 70), "light_ref": 12000},
        "houseplant_generic": {"temp": (16, 28), "humidity": (40, 70), "light_ref":  8000},
        "succulent_cactus":   {"temp": (18, 32), "humidity": (20, 50), "light_ref": 14000},
    }
    _PLANT_ALIASES: dict[str, str] = {
        "tomato": "tomato_indoor", "basil": "basilikum",
        "mint": "houseplant_generic", "potato": "houseplant_generic",
        "houseplant": "houseplant_generic", "succulent": "succulent_cactus",
    }

    def _compute_health_score(
        self,
        readings: dict[str, Any] | None,
        plant_type: str,
        disease_prediction: dict[str, Any],
        calibration: dict[str, Any] | None,
    ) -> tuple[float | None, dict[str, float], int]:
        if not readings:
            return None, {}, 0

        key = self._PLANT_ALIASES.get(plant_type.strip().lower(), "houseplant_generic")
        profile = self.watering_ai.profiles.get(key, self.watering_ai.profiles["houseplant_generic"])
        ranges = self._PLANT_RANGES.get(key, self._PLANT_RANGES["houseplant_generic"])

        soil = self._reading_value(readings, "soil_moisture_pct", "soil_moisture")
        threshold = float((calibration or {}).get("moisture_target_pct", profile["moisture_threshold_pct"]))
        target = float(profile["target_moisture_pct"])
        stop = float(profile["stop_watering_pct"])
        if soil is None:
            moisture_score = 50.0
        elif soil < threshold * 0.5:
            moisture_score = max(0.0, (soil / max(threshold * 0.5, 1)) * 35.0)
        elif soil < threshold:
            moisture_score = 35.0 + ((soil - threshold * 0.5) / max(threshold * 0.5, 1)) * 45.0
        elif soil <= target:
            moisture_score = 80.0 + ((soil - threshold) / max(target - threshold, 1)) * 20.0
        elif soil <= stop:
            moisture_score = 100.0
        else:
            moisture_score = max(55.0, 100.0 - (soil - stop) * 2.5)

        temp = self._reading_value(readings, "temperature_c", "temperature")
        t_min, t_max = ranges["temp"]
        if temp is None:
            temp_score = 50.0
        elif t_min <= temp <= t_max:
            temp_score = 100.0
        elif temp < t_min:
            temp_score = max(0.0, 100.0 - (t_min - temp) * 9.0)
        else:
            temp_score = max(0.0, 100.0 - (temp - t_max) * 9.0)

        light = self._reading_value(readings, "light_lux", "light")
        light_ref = float(ranges["light_ref"])
        if light is None:
            light_score = 50.0
        else:
            ratio = light / light_ref
            if ratio >= 0.9:
                light_score = min(100.0, 85.0 + ratio * 15.0)
            elif ratio >= 0.4:
                light_score = 55.0 + ratio * 75.0
            else:
                light_score = max(5.0, ratio * 137.5)
        light_score = min(100.0, light_score)

        label = str(disease_prediction.get("label", "healthy")).lower()
        conf = float(disease_prediction.get("confidence", 0.0))
        if label in {"healthy", "unknown", "unknown_non_target", "other_plant", ""}:
            disease_score = 100.0
        else:
            disease_score = max(0.0, 100.0 - conf * 95.0)

        total = round(
            moisture_score * 0.35 + temp_score * 0.25 +
            light_score * 0.20 + disease_score * 0.20,
            1,
        )
        total = max(0.0, min(100.0, total))

        breakdown = {
            "Moisture": round(moisture_score, 1),
            "Temperature": round(temp_score, 1),
            "Light": round(light_score, 1),
            "Disease": round(disease_score, 1),
        }

        score_history = st.session_state.get("_health_score_history", [])
        score_history.append(total)
        st.session_state["_health_score_history"] = score_history[-60:]
        trend = 0
        if len(score_history) >= 2:
            delta = score_history[-1] - score_history[-2]
            trend = 1 if delta > 0.5 else (-1 if delta < -0.5 else 0)

        return total, breakdown, trend

    @staticmethod
    def _health_score_color(score: float, trend: int) -> str:
        if score >= 75 and trend >= 0:
            return "good"
        if score < 50 or trend < 0:
            return "bad"
        return "warn"

    def _render_health_score_card(
        self,
        score: float | None,
        breakdown: dict[str, float],
        trend: int,
    ) -> None:
        if score is None:
            st.info("Connect a sensor to calculate the Plant Health Score.")
            return
        cls = self._health_score_color(score, trend)
        color_map = {"good": "#5cbb84", "warn": "#e0b33e", "bad": "#e66060"}
        color = color_map[cls]
        trend_html = (
            "<span class='hs-trend-up'>▲ Improving</span>" if trend > 0
            else "<span class='hs-trend-down'>▼ Declining</span>" if trend < 0
            else "<span class='hs-trend-flat'>● Stable</span>"
        )
        bar_color = color
        def _hs_cls(v: float) -> str:
            return "good" if v >= 75 else ("warn" if v >= 50 else "bad")
        components_html = "".join(
            f"<div class='hs-component'><b>{k}</b> "
            f"<span class='hs-inline-{_hs_cls(v)}'>"
            f"{v:.0f}</span></div>"
            for k, v in breakdown.items()
        )
        st.markdown(
            f"""
            <div class="hs-card">
              <div class="hs-label">Plant Health Score</div>
              <div style="display:flex;align-items:baseline;gap:0.4rem">
                <div class="hs-score-{cls}">{score:.0f}<span style="font-size:1.4rem;font-weight:600;color:{color}">/100</span></div>
                {trend_html}
              </div>
              <div class="hs-bar-wrap">
                <div class="hs-bar-fill" style="width:{score:.0f}%;background:{bar_color};"></div>
              </div>
              <div class="hs-breakdown">{components_html}</div>
              <div style="margin-top:0.55rem;font-size:0.78rem;color:#636b78;">
                Health&nbsp;=&nbsp;f(moisture&nbsp;35%&nbsp;·&nbsp;temperature&nbsp;25%&nbsp;·&nbsp;light&nbsp;20%&nbsp;·&nbsp;disease&nbsp;20%)
              </div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def predict_tomato_image(self, image: Image.Image):
        if self.classifier_all is None or self.classifier_binary is None:
            return [], []
        temp_path: Path | None = None
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                temp_path = Path(tmp.name)
                image.save(tmp.name)
            return (
                self.classifier_all.predict(str(temp_path), top_k=3, confidence_threshold=0.0),
                self.classifier_binary.predict(str(temp_path)),
            )
        except Exception as exc:
            LOGGER.warning("Tomato image prediction failed: %s", exc)
            return [], []
        finally:
            if temp_path is not None:
                try:
                    temp_path.unlink(missing_ok=True)
                except Exception as exc:
                    LOGGER.warning("Failed to delete temp prediction file %s: %s", temp_path, exc)

    def _register_selected_sensors(self, sensor_names: list[str], device_info: str) -> None:
        if not self.access_token:
            st.warning("Login is required to register sensors.")
            return
        if not device_info:
            st.info("Add a device ID or endpoint before registering local sensors.")
            return
        successes: list[str] = []
        failures: list[str] = []
        for sensor_name in sensor_names:
            result = self._api_post(
                "/register_sensors",
                {"sensor_name": sensor_name, "sensor_source": "Environment Sensors", "device_info": device_info},
            )
            if result:
                successes.append(sensor_name)
            else:
                failures.append(sensor_name)
        if successes and not failures:
            st.session_state["last_device_registration"] = {"device_id": device_info, "sensors": successes}
            st.success("Device Registered Successfully!")
        elif successes:
            st.warning("Registered: " + ", ".join(successes))
            st.error("Failed: " + ", ".join(failures))
        elif failures:
            st.error("Failed: " + ", ".join(failures))

    def _register_weather_params(self, sensor_names: list[str]) -> None:
        if not self.access_token:
            st.warning("Login is required to register Weather API sensors.")
            return
        for sensor_name in sensor_names:
            result = self._api_post(
                "/register_sensors",
                {"sensor_name": sensor_name, "sensor_source": "Weather API", "device_info": OPEN_METEO_URL},
            )
            st.success(f"{sensor_name} weather input registered.") if result else st.error(f"Failed to register {sensor_name}.")

    def _fetch_registered_devices(self) -> list[str]:
        sensors = self._api_get("/sensors") or []
        device_ids: list[str] = []
        for sensor in sensors:
            device_info = str(sensor.get("device_info", "")).strip()
            if device_info and device_info != OPEN_METEO_URL and device_info not in device_ids:
                device_ids.append(device_info)
        readings = self._api_get("/readings", params={"limit": 200}) or []
        for reading in readings:
            device_info = str(reading.get("device_id", "") or "").strip()
            if device_info and device_info not in device_ids:
                device_ids.append(device_info)
        return device_ids

    def _fetch_latest_calibration(self, device_id: str, plant_name: str) -> dict[str, Any] | None:
        if not device_id:
            return None
        result = self._api_get("/calibrations/latest", params={"device_id": device_id, "plant_type": plant_name})
        return None if not result or result.get("status") != "ok" else result.get("calibration")

    def _fetch_recent_commands(self, device_id: str | None = None) -> list[dict]:
        params = {"limit": 6}
        if device_id:
            params["device_id"] = device_id
        rows = self._api_get("/commands/recent", params=params)
        return rows if isinstance(rows, list) else []

    def _fetch_recent_feedback(self, device_id: str | None = None, limit: int = 6) -> list[dict]:
        params = {"limit": limit}
        if device_id:
            params["device_id"] = device_id
        rows = self._api_get("/watering_feedback/recent", params=params)
        return rows if isinstance(rows, list) else []

    def _fetch_water_usage_analytics(self, device_id: str | None = None) -> dict[str, Any]:
        params = {"device_id": device_id} if device_id else None
        analytics = self._api_get("/analytics/water_usage", params=params)
        return analytics if isinstance(analytics, dict) else {}

    def _fetch_pump_failures(self, device_id: str | None = None) -> list[dict]:
        params = {"limit": 6}
        if device_id:
            params["device_id"] = device_id
        rows = self._api_get("/analytics/pump_failures", params=params)
        return rows if isinstance(rows, list) else []

    def _fetch_recent_readings(self, device_id: str | None = None, limit: int = 100, hours: int | None = None) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if device_id:
            params["device_id"] = device_id
        if hours is not None:
            params["hours"] = hours
        rows = self._api_get("/readings", params=params)
        return rows if isinstance(rows, list) else []

    def _save_feedback(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._api_post("/watering_feedback", payload)

    def _save_calibration(self, payload: dict[str, Any]) -> dict[str, Any] | None:
        return self._api_post("/calibrations", payload)

    def _queue_water_command(self, device_id: str, pump_ms: int, plant_name: str, reasons: list[str]) -> None:
        result = self._api_post(
            "/commands/water_now",
            {
                "device_id": device_id,
                "pump_ms": max(0, int(pump_ms)),
                "plant_type": plant_name,
                "reason": " | ".join(reasons[:2]) if reasons else "dashboard relay trigger",
            },
        )
        if result:
            command_id = result.get("command_id")
            payload = result.get("payload") if isinstance(result.get("payload"), dict) else {}
            queued_device = str(result.get("device_id") or device_id)
            queued_pump_ms = int(payload.get("pump_ms", pump_ms))
            st.session_state["last_queued_command_id"] = command_id
            st.success(f"Queued watering for {queued_device} with {queued_pump_ms} ms.")
        else:
            st.error("Failed to queue relay command.")

    def _append_sensor_history(self, readings: dict[str, float], source: str) -> None:
        if not readings:
            return
        stamped = {
            key: value
            for key, value in readings.items()
            if key not in {"source", "timestamp", "device_id"}
        }
        if not stamped:
            return
        stamped["source"] = str(readings.get("source", "") or source)
        stamped["timestamp"] = str(readings.get("timestamp", "") or datetime.datetime.utcnow().isoformat(timespec="seconds"))
        stamped["device_id"] = str(readings.get("device_id", "") or st.session_state.get("active_device_id", ""))
        st.session_state["latest_readings"] = stamped
        st.session_state["latest_backend_snapshot_meta"] = {
            "timestamp": stamped["timestamp"],
            "source": stamped["source"],
            "device_id": stamped["device_id"],
        }
        st.session_state["latest_snapshot_device_id"] = st.session_state.get("active_device_id", "")
        history = st.session_state["sensor_history"]
        history.append(stamped)
        st.session_state["sensor_history"] = history[-36:]

    def _build_backend_snapshot(self, rows: list[dict]) -> dict[str, Any] | None:
        if not rows:
            return None

        snapshot: dict[str, Any] = {}
        latest_timestamp: str | None = None
        latest_source: str | None = None
        latest_device_id: str | None = None
        seen_sensors: set[str] = set()

        for row in rows:
            sensor_name = str(row.get("sensor_name", "")).strip()
            if not sensor_name or sensor_name in seen_sensors:
                continue

            value = self._safe_float(row.get("value"))
            if value is None:
                continue

            snapshot[sensor_name] = value
            seen_sensors.add(sensor_name)

            if latest_timestamp is None:
                latest_timestamp = str(row.get("timestamp", ""))
                latest_source = str(row.get("source", "Backend Telemetry"))
                latest_device_id = str(row.get("device_id", "") or "")

        if not snapshot:
            return None

        snapshot["timestamp"] = latest_timestamp or datetime.datetime.utcnow().isoformat(timespec="seconds")
        snapshot["source"] = latest_source or "Backend Telemetry"
        snapshot["device_id"] = latest_device_id or ""
        return snapshot

    def _build_prediction_history(self, active_device: str) -> list[dict[str, Any]]:
        session_history = list(st.session_state.get("sensor_history", []))
        if not self.access_token or not active_device:
            return session_history

        rows = self._fetch_recent_readings(active_device, limit=5000, hours=24)
        if not rows:
            return session_history

        backend = pd.DataFrame(rows)
        backend["timestamp"] = pd.to_datetime(backend["timestamp"], errors="coerce")
        backend = backend.dropna(subset=["timestamp"])
        if backend.empty:
            return session_history

        backend["time_bucket"] = backend["timestamp"].dt.floor("30s")
        pivot = (
            backend.pivot_table(index="time_bucket", columns="sensor_name", values="value", aggfunc="last")
            .sort_index()
            .ffill()
        )
        snapshots: list[dict[str, Any]] = []
        for timestamp, values in pivot.tail(24 * 60 * 2).iterrows():
            snapshot = {str(key): float(value) for key, value in values.items() if pd.notna(value)}
            if not snapshot:
                continue
            snapshot["timestamp"] = timestamp.isoformat()
            snapshot["source"] = "Backend Telemetry"
            snapshot["device_id"] = active_device
            snapshots.append(snapshot)

        return snapshots or session_history

    def _hydrate_latest_snapshot(self, active_device: str) -> None:
        if not self.access_token or not active_device:
            st.session_state["latest_backend_snapshot_meta"] = None
            return

        current_device = st.session_state.get("latest_snapshot_device_id", "")
        current_snapshot = st.session_state.get("latest_readings")
        if current_snapshot is not None and current_device == active_device and not self._snapshot_is_stale(current_snapshot):
            return

        rows = self._fetch_recent_readings(active_device, limit=20)
        snapshot = self._build_backend_snapshot(rows)
        st.session_state["latest_snapshot_device_id"] = active_device
        if snapshot is None:
            st.session_state["latest_readings"] = None
            st.session_state["latest_backend_snapshot_meta"] = None
            return
        st.session_state["latest_backend_snapshot_meta"] = {
            "timestamp": str(snapshot.get("timestamp", "") or ""),
            "source": str(snapshot.get("source", "") or "Backend Telemetry"),
            "device_id": str(snapshot.get("device_id", "") or active_device),
        }
        if self._snapshot_is_stale(snapshot):
            st.session_state["latest_readings"] = None
            return

        st.session_state["latest_readings"] = snapshot

    def _ingest_sensor_data(self, sensor_source: str) -> None:
        last_saved_at = st.session_state.get("last_saved_at")
        data_source = self.sensor_reader.source if self.sensor_reader else sensor_source
        if st.session_state.get("force_single_read"):
            readings = self.sensor_reader.read() if self.sensor_reader else {}
            self._append_sensor_history(readings, data_source)
            st.session_state["force_single_read"] = False
        elif self.stream_controller.is_streaming():
            readings = self.sensor_reader.read() if self.sensor_reader else {}
            self._append_sensor_history(readings, data_source)
            now = datetime.datetime.utcnow()
            if self.sensor_reader and (
                last_saved_at is None
                or (now - datetime.datetime.fromisoformat(str(last_saved_at))).total_seconds() >= 30 * 60
            ):
                self.sensor_reader.send_to_api(readings, data_source)
                st.session_state["last_saved_at"] = now.isoformat()

    def _get_weather_context(self, city: str) -> dict[str, float]:
        cached = st.session_state.get("latest_weather_context")
        fetched_at_raw = st.session_state.get("latest_weather_context_at")
        cached_city = st.session_state.get("latest_weather_context_city")
        fetched_at = None
        if fetched_at_raw:
            try:
                fetched_at = datetime.datetime.fromisoformat(str(fetched_at_raw))
            except ValueError:
                fetched_at = None

        if (
            isinstance(cached, dict)
            and cached_city == city
            and fetched_at is not None
            and (datetime.datetime.utcnow() - fetched_at).total_seconds() < 15 * 60
        ):
            return cached

        weather_context = self.weather_reader.read() if self.weather_reader else {}
        st.session_state["latest_weather_context"] = weather_context
        st.session_state["latest_weather_context_at"] = datetime.datetime.utcnow().isoformat()
        st.session_state["latest_weather_context_city"] = city
        return weather_context

    @staticmethod
    def _format_geolocation_error(error_payload: Any) -> str:
        if not isinstance(error_payload, dict):
            return "Location detection failed. Check browser permissions and try again."

        code = error_payload.get("code")
        raw_message = str(error_payload.get("message", "") or "").strip()
        if raw_message:
            if code == 1:
                return f"Geolocation was denied in the current page context. Browser message: {raw_message}"
            return raw_message
        if code == 1:
            return "Geolocation was denied in the current page context."
        if code == 2:
            return "The browser could not determine your location. Try again in a few seconds."
        if code == 3:
            return "Location lookup timed out. Try again."
        return "Location detection failed. Check browser permissions and try again."

    @staticmethod
    def _extract_reverse_geocode_city(reverse_payload: dict[str, Any]) -> str | None:
        address = reverse_payload.get("address", {})
        if isinstance(address, dict):
            for field in ("city", "town", "village", "municipality", "county", "state_district", "suburb"):
                candidate = str(address.get(field, "") or "").strip()
                if candidate:
                    return candidate

        name = str(reverse_payload.get("name", "") or "").strip()
        if name:
            return name

        display_name = str(reverse_payload.get("display_name", "") or "").strip()
        if display_name:
            return display_name.split(",")[0].strip()
        return None

    def _detect_weather_city_from_browser(self, browser_location: dict[str, Any] | None) -> tuple[str | None, str | None]:
        if not browser_location:
            return None, None

        if browser_location.get("error"):
            return None, self._format_geolocation_error(browser_location["error"])

        coords = browser_location.get("coords")
        if not isinstance(coords, dict):
            return None, "The browser returned an invalid location payload."

        latitude = coords.get("latitude")
        longitude = coords.get("longitude")
        if latitude is None or longitude is None:
            return None, "The browser returned incomplete coordinates."

        try:
            reverse_response = requests.get(
                "https://nominatim.openstreetmap.org/reverse",
                params={"lat": latitude, "lon": longitude, "format": "json"},
                headers={"User-Agent": "BalconyGreen/1.0"},
                timeout=5,
            )
            reverse_response.raise_for_status()
            reverse_payload = reverse_response.json()
        except Exception as exc:
            return None, f"Reverse geocoding failed: {exc}"

        detected_city = self._extract_reverse_geocode_city(reverse_payload)
        if not detected_city:
            return None, "The location lookup succeeded, but no city name was returned."
        return detected_city, None

    @staticmethod
    def _weather_summary_line(weather_context: dict[str, Any]) -> str | None:
        if not isinstance(weather_context, dict) or not weather_context:
            return None

        temp = weather_context.get("current_temp_c", weather_context.get("weather_temp_c", weather_context.get("temperature")))
        wind = weather_context.get("current_wind_speed_kmh")
        rain_chance = weather_context.get("rain_chance_pct")
        parts: list[str] = []
        if temp is not None:
            parts.append(f"{float(temp):.1f} C")
        if wind is not None:
            parts.append(f"{float(wind):.0f} km/h wind")
        if rain_chance is not None:
            parts.append(f"{float(rain_chance):.0f}% rain chance")
        return " | ".join(parts) if parts else None

    def _merge_prediction_inputs(self, base_readings: dict[str, Any], sensor_mode: str, city: str | None) -> dict[str, Any]:
        merged = dict(base_readings)
        if "Weather" not in sensor_mode or not city:
            return merged

        weather_context = self._get_weather_context(city)
        if not weather_context:
            return merged

        merged["weather_temp_c"] = float(weather_context.get("weather_temp_c", weather_context.get("temperature", 0.0)) or 0.0)
        merged["weather_humidity_pct"] = float(weather_context.get("weather_humidity_pct", weather_context.get("humidity", 0.0)) or 0.0)
        merged["forecast_rain_mm"] = float(weather_context.get("forecast_rain_mm", 0.0) or 0.0)

        if self._reading_value(merged, "temperature_c", "temperature") is None and "temperature" in weather_context:
            merged["temperature"] = weather_context["temperature"]
        if self._reading_value(merged, "humidity_pct", "humidity") is None and "humidity" in weather_context:
            merged["humidity"] = weather_context["humidity"]
        if self._reading_value(merged, "light_lux", "light") is None and "light" in weather_context:
            merged["light"] = weather_context["light"]

        return merged

    def _render_sidebar(self) -> tuple[str, str, str | None]:
        with st.sidebar:
            st.markdown("## Configuration")
            if st.session_state.get("session_expired"):
                st.warning("Session expired. Log out and log back in.")
            options = ["Tomato", "Basil", "Houseplant", "Succulent", "Mint", "Potato"]
            plant_name = st.selectbox("Plant profile", options, index=options.index(st.session_state.get("predicted_plant", "Tomato")))
            st.session_state["predicted_plant"] = plant_name
            devices = self._fetch_registered_devices() if self.access_token else []
            if devices:
                remembered = st.session_state.get("active_device_id", "")
                index = devices.index(remembered) if remembered in devices else 0
                active_device = st.selectbox("Active ESP32 device", devices, index=index)
            else:
                active_device = st.text_input("Active ESP32 device", value=st.session_state.get("active_device_id", ""), placeholder="esp32-balcony-1")
            active_device = active_device.strip()
            previous_device = str(st.session_state.get("active_device_id", "") or "")
            if active_device != previous_device:
                st.session_state["sensor_history"] = []
                st.session_state["latest_readings"] = None
                st.session_state["latest_snapshot_device_id"] = ""
                st.session_state["latest_backend_snapshot_meta"] = None
            st.session_state["active_device_id"] = active_device
            sensor_modes = ["ESP32 Sensors", "ESP32 + Weather API"]
            sensor_source = st.radio(
                "Data mode",
                sensor_modes,
                index=sensor_modes.index(
                    st.session_state.get("sensor_mode", "ESP32 + Weather API")
                    if st.session_state.get("sensor_mode", "ESP32 + Weather API") in sensor_modes
                    else "ESP32 + Weather API"
                ),
            )
            st.session_state["sensor_mode"] = sensor_source
            if "weather_city_input" not in st.session_state:
                st.session_state["weather_city_input"] = st.session_state.get("weather_city", "London")

            gps_component_key = f"gps_loc_fetch_{st.session_state.get('_gps_request_nonce', 0)}"
            if st.session_state.get("_gps_requested"):
                if not _GPS_AVAILABLE:
                    st.session_state["_gps_requested"] = False
                    st.session_state["_gps_error"] = "GPS detection is unavailable in this environment."
                else:
                    detected_city, gps_error = self._detect_weather_city_from_browser(
                        _get_browser_location(component_key=gps_component_key)
                    )
                    if detected_city:
                        st.session_state["weather_city"] = detected_city
                        st.session_state["weather_city_input"] = detected_city
                        st.session_state["_gps_requested"] = False
                        st.session_state["_gps_error"] = None
                        st.rerun()
                    if gps_error:
                        st.session_state["_gps_requested"] = False
                        st.session_state["_gps_error"] = gps_error

            st.markdown(
                """
                <style>
                [data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
                  [data-testid="stColumn"]:last-child .stButton button {
                    width: 100%; height: 2.95rem; margin-top: 1.55rem;
                    padding: 0; font-size: 1.1rem; line-height: 1;
                }
                [data-testid="stSidebar"] [data-testid="stHorizontalBlock"]
                  [data-testid="stColumn"]:first-child [data-baseweb="input"] > div {
                    min-height: 2.95rem;
                }
                </style>
                """,
                unsafe_allow_html=True,
            )
            city_col, gps_col = st.columns([5, 1])
            previous_city = str(st.session_state.get("weather_city", "London") or "London").strip() or "London"
            with city_col:
                city_input = st.text_input(
                    "Weather location",
                    key="weather_city_input",
                    placeholder="City name",
                )
            with gps_col:
                if st.button(
                    "📍",
                    key="gps_detect_btn",
                    help="Auto-detect from device GPS",
                    disabled=not _GPS_AVAILABLE,
                ):
                    st.session_state["_gps_requested"] = True
                    st.session_state["_gps_error"] = None
                    st.session_state["_gps_request_nonce"] = int(st.session_state.get("_gps_request_nonce", 0)) + 1
                    st.rerun()
            st.session_state["weather_city"] = (city_input or "").strip() or "London"
            city = st.session_state["weather_city"]
            if city != previous_city and not st.session_state.get("_gps_requested"):
                st.session_state["_gps_error"] = None
            self.weather_reader = SensorReader(
                access_token=self.access_token,
                source="Weather API",
                city=city or st.session_state.get("weather_city", "London"),
                api_key=OPEN_METEO_URL,
            )
            weather_context = self._get_weather_context(city) if "Weather" in sensor_source and city else {}
            matched_location = str(weather_context.get("matched_location_label", "") or "").strip()
            match_type = str(weather_context.get("matched_location_type", "") or "").strip()
            if matched_location and match_type == "closest" and matched_location.lower() != city.lower():
                st.caption(f'Using weather for: {matched_location} (closest match for "{city}")')
            else:
                st.caption(f"Using weather for: {matched_location or city}")
            weather_summary = self._weather_summary_line(weather_context)
            if weather_summary:
                st.caption(weather_summary)
            if st.session_state.get("_gps_requested"):
                st.caption("Detecting your current city. Allow browser location access if prompted.")
            elif st.session_state.get("_gps_error"):
                st.caption(f"Location detection failed: {st.session_state['_gps_error']}")
            elif not _GPS_AVAILABLE:
                st.caption("GPS detection is unavailable in this environment.")
            st.caption("Register sensors under Device Management on the main page.")
            with st.expander("Advanced", expanded=False):
                camera_url = st.text_input("External camera URL", value=st.session_state.get("camera_url", DEFAULT_CAMERA_URL))
                st.session_state["camera_url"] = camera_url.strip() or DEFAULT_CAMERA_URL
            self.camera.snapshot_url = st.session_state["camera_url"]
            st.markdown("### Live data")
            self.stream_controller.controls()
            active_tab = str(st.session_state.get("active_dashboard_tab", "Overview") or "Overview")
            st.caption(
                (
                    "Auto refresh is on. Overview updates every 30 seconds to match ESP32 telemetry."
                    if self.stream_controller.is_streaming() and active_tab in LIVE_REFRESH_TABS
                    else f"Auto refresh is paused while you are on {active_tab}. Use Refresh now or switch back to Overview."
                    if self.stream_controller.is_streaming()
                    else "Auto refresh is off."
                )
            )
        self.sensor_reader = SensorReader(
            access_token=self.access_token,
            source="Environment Sensors",
            city=city or st.session_state.get("weather_city", "London"),
            api_key=OPEN_METEO_URL,
            device_id=st.session_state.get("active_device_id", "") or None,
        )
        self.weather_reader = SensorReader(
            access_token=self.access_token,
            source="Weather API",
            city=city or st.session_state.get("weather_city", "London"),
            api_key=OPEN_METEO_URL,
        )
        return sensor_source, st.session_state.get("active_device_id", ""), city

    def _update_disease_prediction(self, uploaded_image: Image.Image | None, plant_name: str) -> None:
        if uploaded_image is None:
            return
        if plant_name.lower() != "tomato":
            st.session_state["latest_disease_prediction"] = {"label": "unknown_non_target", "confidence": 0.0, "top_results": []}
            return
        results_all, results_binary = self.predict_tomato_image(uploaded_image)
        if not results_all:
            st.session_state["latest_disease_prediction"] = {"label": "healthy", "confidence": 0.0, "top_results": [], "binary": []}
            return
        top_result = results_all[0]
        st.session_state["latest_disease_prediction"] = {
            "label": top_result["class_name"],
            "confidence": float(top_result["confidence"]),
            "top_results": results_all,
            "binary": results_binary,
        }

    def _build_prediction(self, plant_name: str, active_device: str, sensor_mode: str, city: str | None) -> tuple[Any | None, dict[str, Any] | None]:
        readings = st.session_state.get("latest_readings")
        if not readings:
            st.session_state["_active_calibration"] = None
            return None, None
        readings = self._merge_prediction_inputs(readings, sensor_mode, city)
        calibration = self._fetch_latest_calibration(active_device, plant_name) if self.access_token and active_device else None
        st.session_state["_active_calibration"] = calibration
        disease_prediction = st.session_state.get("latest_disease_prediction", {})
        prediction_history = self._build_prediction_history(active_device)
        feedback_rows = self._fetch_recent_feedback(active_device or None, limit=24) if self.access_token else []
        prediction = self.watering_ai.predict(
            sensor_readings=readings,
            plant_type=plant_name,
            disease_label=disease_prediction.get("label", "healthy"),
            disease_confidence=float(disease_prediction.get("confidence", 0.0)),
            history=prediction_history,
            feedback_rows=feedback_rows,
            calibration=calibration,
        )
        return prediction, calibration

    def _render_panel_header(self, title: str, subtitle: str) -> None:
        st.markdown(f"<div class='panel-card'><div class='panel-title'>{title}</div><div class='panel-muted'>{subtitle}</div></div>", unsafe_allow_html=True)

    def _render_hero(self, backend_ok: bool, active_device: str, prediction, health_score: float | None = None, hs_trend: int = 0) -> None:
        disease_ready = self.classifier_all is not None and self.classifier_binary is not None
        latest_snapshot = st.session_state.get("latest_readings")
        backend_snapshot = st.session_state.get("latest_backend_snapshot_meta")
        if latest_snapshot and not self._snapshot_is_stale(latest_snapshot):
            telemetry_pill = (f"ESP32 Live · {self._format_snapshot_age(latest_snapshot)}", "good")
        elif isinstance(backend_snapshot, dict) and backend_snapshot.get("timestamp"):
            telemetry_pill = (f"Telemetry stale · {self._format_snapshot_age(backend_snapshot)}", "warn")
        else:
            telemetry_pill = ("No ESP32 telemetry", "bad")
        pills = [
            ("API Online" if backend_ok else "API Offline", "good" if backend_ok else "bad"),
            telemetry_pill,
            ("Watering AI Ready", "good"),
            ("Disease Model Ready" if disease_ready else "Disease Model Unavailable", "good" if disease_ready else "warn"),
            (f"ESP32: {active_device}" if active_device else "No Device Linked", "good" if active_device else "warn"),
        ]
        if prediction is not None:
            pills.append((f"Next watering in {prediction.probable_next_watering_hours}h", "warn" if prediction.should_water else "good"))
        if health_score is not None:
            hs_cls = self._health_score_color(health_score, hs_trend)
            pills.append((f"Health {health_score:.0f}/100", hs_cls))
        pill_html = "".join(f"<span class='pill {kind}'>{label}</span>" for label, kind in pills)
        st.markdown(
            f"""
            <div class="hero-card">
                <div class="hero-title">🌱 Balcony Green</div>
                <p class="hero-subtitle">ESP32 telemetry · Predictive irrigation · Plant disease detection · Relay control</p>
                <div>{pill_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def _render_device_management_panel(self, active_device: str) -> None:
        st.markdown("<div class='section-heading'>🔌 Device Management</div>", unsafe_allow_html=True)

        options = ["Tomato", "Basil", "Houseplant", "Succulent", "Mint", "Potato"]
        expanded = bool(st.session_state.get("open_device_setup", False)) or not bool(active_device)
        with st.expander("Register ESP32 Device", expanded=expanded):
            selected_plant = st.selectbox(
                "Plant profile",
                options,
                index=options.index(st.session_state.get("predicted_plant", "Tomato")),
                key="device_management_plant",
            )
            st.session_state["predicted_plant"] = selected_plant

            device_value = st.text_input(
                "Device ID",
                value=active_device or st.session_state.get("active_device_id", ""),
                placeholder="esp32-balcony-1",
                key="device_management_device_id",
            ).strip()
            if device_value:
                st.session_state["active_device_id"] = device_value
                active_device = device_value

            sensor_names = st.multiselect(
                "Sensors to register",
                ["temperature", "humidity", "soil_moisture", "soil_raw", "soil_ph", "light", "camera", "pump_relay"],
                default=["temperature", "humidity", "soil_moisture", "soil_raw", "light"],
                key="device_management_sensor_names",
            )
            if st.button("Register Device", key="device_management_register"):
                self._register_selected_sensors(sensor_names, device_value)

        registration = st.session_state.get("last_device_registration")
        if isinstance(registration, dict) and registration.get("device_id"):
            registered_device = str(registration.get("device_id"))
            st.markdown(
                f"""
                <div class="device-detail-card">
                    <div class="device-detail-title">Registered Device</div>
                    <p class="device-detail-line">Device ID: <code>{registered_device}</code></p>
                </div>
                """,
                unsafe_allow_html=True,
            )

        with st.expander("Flash Firmware", expanded=False):
            st.caption("Firmware sketch with pin mapping for your hardware configuration.")
            st.code("examples/esp32_water_now_demo/esp32_water_now_demo.ino", language="text")
            st.write("Capacitive soil sensor `AOUT → GPIO34` · DHT22 `DATA → GPIO4`")
            st.write("OLED `SDA → GPIO21` · `SCL → GPIO22`")
            st.write("BH1750 `SDA → GPIO18` · `SCL → GPIO19`")
            st.warning("ESP32 Wi-Fi is 2.4 GHz only. A 5 GHz-only hotspot will cause Wi-Fi timeouts.")
            st.info("Run `flash_esp32.bat` to auto-patch credentials and flash the firmware to your device.")

    def _render_kpis(self, prediction, disease_prediction: dict[str, Any], health_score: float | None = None, hs_trend: int = 0) -> None:
        readings = st.session_state.get("latest_readings")
        calibration = st.session_state.get("_active_calibration")
        plant_name = st.session_state.get("predicted_plant", "Tomato")
        calibration_review = self._calibration_review_message(readings, calibration, plant_name)
        soil = self._reading_value(readings, "soil_moisture_pct", "soil_moisture")
        temp = self._reading_value(readings, "temperature_c", "temperature")
        light = self._reading_value(readings, "light_lux", "light")
        humidity = self._reading_value(readings, "humidity_pct", "humidity")
        c1, c2, c3, c4, c5 = st.columns(5)
        with c1:
            st.metric("Soil Moisture", f"{soil:.1f}%" if soil is not None else "--", None if self._history_delta("soil_moisture_pct", "soil_moisture") is None else f"{self._history_delta('soil_moisture_pct', 'soil_moisture'):+.1f}%")
        with c2:
            st.metric("Temperature", f"{temp:.1f} C" if temp is not None else "--", None if self._history_delta("temperature_c", "temperature") is None else f"{self._history_delta('temperature_c', 'temperature'):+.1f} C")
        with c3:
            light_delta = "Sensor offline" if light is None else (None if self._history_delta("light_lux", "light") is None else f"{self._history_delta('light_lux', 'light'):+.0f}")
            st.metric("Light", f"{int(light)} lux" if light is not None else "--", light_delta, delta_color="off" if light is None else "normal")
        with c4:
            if prediction is not None:
                urgency = "Review calibration" if calibration_review else ("Recommend watering" if prediction.should_water else "Low urgency")
                st.metric("Next Watering", f"{prediction.probable_next_watering_hours} h", urgency, delta_color="off")
            else:
                st.metric("Health Signal", disease_prediction.get("label", "healthy").replace("_", " "), f"{float(disease_prediction.get('confidence', 0.0)) * 100:.0f}% confidence")
        with c5:
            if health_score is not None:
                delta_str = "▲ Improving" if hs_trend > 0 else ("▼ Declining" if hs_trend < 0 else "● Stable")
                st.metric("Plant Health", f"{health_score:.0f}/100", delta_str)
            else:
                st.metric("Plant Health", "--")
        if humidity is not None:
            st.caption(f"Ambient humidity: {humidity:.1f}%")
        if calibration_review:
            st.caption(calibration_review)

    def _render_alerts(self, prediction, disease_prediction: dict[str, Any], failures: list[dict], health_score: float | None = None, hs_trend: int = 0) -> None:
        alerts: list[tuple[str, str, str]] = []
        latest_snapshot = st.session_state.get("latest_readings")
        backend_snapshot = st.session_state.get("latest_backend_snapshot_meta")
        calibration = st.session_state.get("_active_calibration")
        plant_name = st.session_state.get("predicted_plant", "Tomato")
        calibration_review = self._calibration_review_message(latest_snapshot, calibration, plant_name)
        if latest_snapshot is None:
            if isinstance(backend_snapshot, dict) and backend_snapshot.get("timestamp"):
                source = str(backend_snapshot.get("source", "Backend Telemetry") or "Backend Telemetry")
                age_label = self._format_snapshot_age(backend_snapshot)
                alerts.append(("warn", "Telemetry stale", f"No fresh ESP32 data has arrived for {age_label}. Last backend reading was from {source}."))
            else:
                alerts.append(("warn", "No live snapshot", "Use Refresh now or enable auto refresh to populate the dashboard."))
        if health_score is not None and (health_score < 50 or hs_trend < 0):
            trend_word = "and declining" if hs_trend < 0 else "(low)"
            alerts.append(("bad", "Plant health alert", f"Health score is {health_score:.0f}/100 {trend_word}. Check soil moisture, temperature, light, and disease status."))
        if prediction is not None and prediction.should_water:
            alerts.append(("warn", "Watering recommended", f"Model confidence is {prediction.watering_probability * 100:.1f}% with {prediction.recommended_pump_ms} ms suggested pump time."))
        label = str(disease_prediction.get("label", "healthy")).lower()
        if label not in {"healthy", "unknown", "unknown_non_target", "other_plant", ""}:
            alerts.append(("bad", "Disease signal detected", f"Leaf analysis reported {label} with {float(disease_prediction.get('confidence', 0.0)) * 100:.1f}% confidence."))
        if prediction is not None and prediction.missing_inputs:
            alerts.append(("warn", "Fallback inputs", "Model is using fallback values for the " + self._format_missing_inputs(prediction.missing_inputs) + "."))
        if latest_snapshot is not None and self._reading_value(latest_snapshot, "light_lux", "light") is None:
            alerts.append(("warn", "Light sensor offline", "No BH1750 light reading is arriving from the ESP32, so light-dependent scores use a fallback estimate."))
        if calibration_review:
            alerts.append(("warn", "Calibration review", calibration_review))
        if any(row.get("status") == "warning" for row in failures):
            alerts.append(("bad", "Pump response issue", "Soil moisture did not rise enough after a recent watering command."))
        if not alerts:
            alerts.append(("good", "System stable", "No critical health or irrigation alerts right now."))
        st.markdown("### Alert Feed")
        for kind, title, body in alerts:
            st.markdown(f"<div class='panel-card'><span class='pill {kind}'>{title}</span><div class='panel-muted' style='margin-top:0.6rem'>{body}</div></div>", unsafe_allow_html=True)

    def _render_system_status(self, backend_ok: bool, active_device: str) -> None:
        disease_ready = self.classifier_all is not None and self.classifier_binary is not None
        self._render_panel_header("System Status", "Live readiness of the stack, models, and active device.")
        latest_snapshot = st.session_state.get("latest_readings")
        backend_snapshot = st.session_state.get("latest_backend_snapshot_meta")
        if latest_snapshot:
            latest_value = f"{self._format_snapshot_age(latest_snapshot)} from {latest_snapshot.get('source', 'Backend Telemetry')}"
        elif isinstance(backend_snapshot, dict) and backend_snapshot.get("timestamp"):
            latest_value = f"stale, last seen {self._format_snapshot_age(backend_snapshot)} from {backend_snapshot.get('source', 'Backend Telemetry')}"
        else:
            latest_value = "none yet"
        rows = [
            ("Backend API", "Online" if backend_ok else "Offline"),
            ("Watering model", "Ready"),
            ("Disease model", "Ready" if disease_ready else "Fallback mode"),
            ("Session mode", "Authenticated" if self.access_token else "Guest"),
            ("Linked device", active_device or "Not linked"),
            ("Latest telemetry", latest_value),
        ]
        if "Weather" in st.session_state.get("sensor_mode", "ESP32 Sensors"):
            rows.append(("Weather context", st.session_state.get("weather_city", "London")))
        status_html = "".join(
            f'<div class="compact-item"><span class="compact-label">{label}</span><span class="compact-value">{value}</span></div>'
            for label, value in rows
        )
        st.markdown(
            f"<div class='panel-card'><div class='compact-grid single-column'>{status_html}</div></div>",
            unsafe_allow_html=True,
        )

    def _render_compact_overview_details(
        self,
        plant_name: str,
        active_device: str,
        disease_prediction: dict[str, Any],
        readings: dict[str, Any] | None,
    ) -> None:
        if not readings:
            st.info("No live sensor snapshot yet.")
            return

        soil = self._reading_value(readings, "soil_moisture_pct", "soil_moisture")
        temp = self._reading_value(readings, "temperature_c", "temperature")
        humidity = self._reading_value(readings, "humidity_pct", "humidity")
        light = self._reading_value(readings, "light_lux", "light")
        details = [
            ("Plant profile", plant_name),
            ("Active device", active_device or "Not linked"),
            ("Disease status", disease_prediction.get("label", "healthy").replace("_", " ")),
            ("Soil moisture", f"{soil:.1f}%" if soil is not None else "--"),
            ("Temperature", f"{temp:.1f} C" if temp is not None else "--"),
            ("Humidity", f"{humidity:.1f}%" if humidity is not None else "--"),
            ("Light", f"{int(light)} lux" if light is not None else "--"),
        ]
        cards = "".join(
            f'<div class="compact-item"><span class="compact-label">{label}</span><span class="compact-value">{value}</span></div>'
            for label, value in details
        )
        st.markdown(f"<div class='panel-card'><div class='compact-grid'>{cards}</div></div>", unsafe_allow_html=True)

    def _render_sensor_trends(self, active_device: str) -> None:
        self._render_panel_header("Sensor Trends", "Recent backend telemetry for the selected device.")
        history = st.session_state.get("sensor_history", [])
        rows = self._fetch_recent_readings(active_device or None, limit=20000, hours=24)
        if rows:
            backend = pd.DataFrame(rows)
            backend["timestamp"] = pd.to_datetime(backend["timestamp"], errors="coerce")
            backend = backend.dropna(subset=["timestamp"])
            if not backend.empty:
                backend["time_bucket"] = backend["timestamp"].dt.floor("30s")
                pivot = (
                    backend.pivot_table(index="time_bucket", columns="sensor_name", values="value", aggfunc="last")
                    .sort_index()
                    .ffill()
                )
                trend_window = pivot.tail(24 * 60 * 2)
                st.caption("These charts show up to the last 24 hours of saved ESP32 readings from the backend.")
                moisture_cols = [c for c in ["soil_moisture", "soil_moisture_pct"] if c in pivot.columns]
                raw_cols = [c for c in ["soil_raw"] if c in pivot.columns]
                env_cols = [c for c in ["temperature", "humidity"] if c in pivot.columns]
                light_cols = [c for c in ["light"] if c in pivot.columns]
                if moisture_cols:
                    st.caption("Soil moisture over time")
                    st.line_chart(trend_window[moisture_cols], height=180)
                if raw_cols:
                    st.caption("Soil sensor raw value")
                    st.line_chart(trend_window[raw_cols], height=140)
                if env_cols:
                    st.caption("Temperature and humidity")
                    st.line_chart(trend_window[env_cols], height=180)
                if light_cols:
                    st.caption("Light sensor")
                    st.line_chart(trend_window[light_cols], height=140)
        else:
            st.info("No backend telemetry history yet.")

        if history:
            with st.expander("Browser session buffer", expanded=False):
                st.caption("These temporary charts only show readings collected in this browser tab since the last reload.")
                frame = pd.DataFrame(history)
                frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
                frame = frame.dropna(subset=["timestamp"])
                frame["time_bucket"] = frame["timestamp"].dt.floor("30s")
                value_columns = [c for c in ["soil_moisture", "soil_moisture_pct", "soil_raw", "temperature", "temperature_c", "humidity", "humidity_pct", "light", "light_lux"] if c in frame.columns]
                frame = frame.groupby("time_bucket")[value_columns].last().sort_index().ffill()
                moisture_cols = [c for c in ["soil_moisture", "soil_moisture_pct"] if c in frame.columns]
                raw_cols = [c for c in ["soil_raw"] if c in frame.columns]
                env_cols = [c for c in ["temperature", "temperature_c", "humidity", "humidity_pct"] if c in frame.columns]
                light_cols = [c for c in ["light", "light_lux"] if c in frame.columns]
                if moisture_cols:
                    st.caption("Session moisture")
                    st.line_chart(frame[moisture_cols], height=160)
                if raw_cols:
                    st.caption("Session raw sensor")
                    st.line_chart(frame[raw_cols], height=130)
                if env_cols:
                    st.caption("Session temperature and humidity")
                    st.line_chart(frame[env_cols], height=160)
                if light_cols:
                    st.caption("Session light")
                    st.line_chart(frame[light_cols], height=130)

    def _render_recent_activity(self, active_device: str) -> None:
        self._render_panel_header("Recent Activity", "Recent relay commands and human feedback labels.")
        commands = self._fetch_recent_commands(active_device or None)
        feedback = self._fetch_recent_feedback(active_device or None)
        if not commands and not feedback:
            st.caption("No recent commands or feedback yet.")
            return
        for command in commands[:4]:
            status = str(command.get("status", "unknown"))
            device = str(command.get("device_id", "unknown-device"))
            created_at = str(command.get("created_at", "unknown time"))
            st.write(f"- Command `{status}` for `{device}` at {created_at}")
        for row in feedback[:4]:
            label = str(row.get("feedback_label", "unknown"))
            plant = str(row.get("plant_type", "unknown plant"))
            created_at = str(row.get("created_at", "unknown time"))
            st.write(f"- Feedback `{label}` for `{plant}` at {created_at}")

    def _render_plant_health_tab(self, plant_name: str) -> None:
        self._render_panel_header("Plant Health Input", "Use your phone camera, upload a saved leaf image, or pull from an external camera URL. The result feeds the health panel and watering logic.")
        image = self.image_input.render()
        if image:
            st.session_state["uploaded_image"] = image
        uploaded_image = st.session_state.get("uploaded_image")
        self._update_disease_prediction(uploaded_image, plant_name)
        disease_prediction = st.session_state.get("latest_disease_prediction", {})

        left, right = st.columns([1.05, 0.95])
        with left:
            if uploaded_image:
                st.image(uploaded_image, caption=f"{plant_name} image", use_container_width=True)
            else:
                st.info("Add a plant image to run the health model.")
            if plant_name.lower() != "tomato":
                st.caption("Disease detection is currently trained on Tomato leaves. Set the plant profile to `Tomato` in the sidebar to run the full inference pipeline.")
        with right:
            self._render_panel_header("Health Summary", "Live disease classification, confidence, and top alternative matches.")
            st.metric("Detected class", disease_prediction.get("label", "unknown").replace("_", " "))
            st.metric("Confidence", f"{float(disease_prediction.get('confidence', 0.0)) * 100:.1f}%")
            top_results = disease_prediction.get("top_results") or []
            if top_results:
                st.markdown("#### Top matches")
                for result in top_results[:4]:
                    st.write(f"- {result['class_name']} — {result['confidence'] * 100:.1f}%")
            elif plant_name.lower() != "tomato":
                st.info("Disease inference is currently tomato-focused. Other plants still use the watering model.")
            else:
                st.info("The disease model is currently in fallback mode on this machine.")

    def _render_automation_tab(self, plant_name: str, active_device: str, prediction, calibration: dict[str, Any] | None) -> None:
        readings = st.session_state.get("latest_readings")
        if not readings:
            st.info("Take a sensor reading first so the irrigation model has live inputs.")
            return
        calibration_review = self._calibration_review_message(readings, calibration, plant_name)
        left, right = st.columns([1.2, 0.8])
        with left:
            self._render_panel_header("Watering Recommendation", "Predictive irrigation output using soil, weather, light, and plant-health context.")
            if prediction is None:
                st.warning("The watering model needs soil moisture or soil raw input.")
            else:
                c1, c2, c3 = st.columns(3)
                with c1:
                    st.metric("Water Now", "Yes" if prediction.should_water else "No")
                with c2:
                    st.metric("Probability", f"{prediction.watering_probability * 100:.1f}%")
                with c3:
                    st.metric("Pump Duration", f"{prediction.recommended_pump_ms} ms")
                st.progress(min(int(prediction.watering_probability * 100), 100))
                st.caption(f"Probable next watering: {prediction.probable_next_watering_hours} h | threshold {prediction.decision_threshold:.2f}")
                if calibration_review:
                    st.warning(calibration_review)
                st.markdown("#### Decision drivers")
                for reason in prediction.reasons:
                    st.write(f"- {reason}")
                with st.expander("Model inputs used"):
                    st.json(prediction.normalized_inputs)
                if prediction.missing_inputs:
                    st.warning("Model is using fallback values for the " + self._format_missing_inputs(prediction.missing_inputs) + ".")
        with right:
            self._render_panel_header("Action Center", "Queue relay commands, inspect command history, and review calibration state.")
            if not self.access_token:
                st.info("Login is required to send relay commands and save calibration.")
                return
            relay_pump_ms = int(st.number_input("Relay pump duration (ms)", min_value=0, max_value=30000, value=max(1000, int(prediction.recommended_pump_ms if prediction else 1000)), step=250))
            if st.button("Send Water Now Command", disabled=not bool(active_device) or relay_pump_ms <= 0):
                self._queue_water_command(active_device, relay_pump_ms, plant_name, prediction.reasons if prediction else [])
            if calibration:
                st.caption(f"Calibration active: target {calibration['moisture_target_pct']}%, failure threshold {calibration['failure_min_rise_pct']}%.")
                if calibration_review:
                    st.info("The current next-watering estimate should be treated cautiously until calibration is reviewed.")
            else:
                st.caption("No calibration saved for this device yet.")
                soil = self._reading_value(readings, "soil_moisture_pct", "soil_moisture")
                if soil is not None and (soil >= 98.0 or soil <= 2.0):
                    st.info("The moisture value is near the limit. Save a calibration if this percentage does not look realistic.")
            commands = self._fetch_recent_commands(active_device or None)
            if commands:
                st.markdown("#### Recent commands")
                for command in commands[:5]:
                    payload = command.get("payload") if isinstance(command.get("payload"), dict) else {}
                    pump_ms = payload.get("pump_ms", 0)
                    status = str(command.get("status", "unknown"))
                    created_at = str(command.get("created_at", "unknown time"))
                    st.write(f"- {status} | {pump_ms} ms | {created_at}")

    def _render_analytics_tab(self, active_device: str) -> None:
        left, right = st.columns([1.1, 0.9])
        with left:
            self._render_panel_header("Water Usage Analytics", "Daily and weekly pump activity with estimated water volume when flow calibration is available.")
            analytics = self._fetch_water_usage_analytics(active_device or None)
            if analytics:
                today = analytics.get("today", {})
                week = analytics.get("last_7_days", {})
                c1, c2 = st.columns(2)
                with c1:
                    st.metric("Today pump time", f"{int(today.get('pump_ms', 0))} ms")
                    if today.get("estimated_ml") is not None:
                        st.metric("Today water", f"{float(today['estimated_ml']):.1f} ml")
                with c2:
                    st.metric("7-day pump time", f"{int(week.get('pump_ms', 0))} ms")
                    if week.get("estimated_ml") is not None:
                        st.metric("7-day water", f"{float(week['estimated_ml']):.1f} ml")
                series = analytics.get("daily_series", [])
                if series:
                    frame = pd.DataFrame(series).set_index("date")
                    st.bar_chart(frame[["pump_ms"]], height=220)
                    if frame["estimated_ml"].notna().any():
                        st.line_chart(frame[["estimated_ml"]], height=220)
            else:
                st.info("No executed watering history yet.")
            self._render_sensor_trends(active_device)
        with right:
            self._render_panel_header("Failure Diagnostics", "Validate that watering commands actually raised soil moisture within the configured time window.")
            diagnostics = self._fetch_pump_failures(active_device or None)
            if diagnostics:
                for row in diagnostics:
                    status = str(row.get("status", "unknown"))
                    device_id = str(row.get("device_id", "unknown-device"))
                    if status == "warning":
                        delta = row.get("moisture_delta", "?")
                        expected = row.get("min_expected_rise_pct", "?")
                        st.error(f"{device_id} | delta {delta}% is below the expected {expected}%.")
                    elif status == "insufficient_data":
                        message = str(row.get("message", "Insufficient diagnostic data."))
                        st.warning(f"{device_id} | {message}")
                    else:
                        delta = row.get("moisture_delta", "?")
                        window = row.get("window_minutes", "?")
                        st.success(f"{device_id} | moisture rose by {delta}% in {window} minutes.")
            else:
                st.info("No pump diagnostics available yet.")
            readings = st.session_state.get("latest_readings")
            if readings:
                with st.expander("Latest raw snapshot"):
                    st.json(readings)

    def _render_learning_tab(self, plant_name: str, active_device: str, calibration: dict[str, Any] | None) -> None:
        left, right = st.columns([0.95, 1.05])
        with left:
            self._render_panel_header("Learning From Feedback", "Save watering outcomes here. These labels now adapt future watering timing and pump suggestions for this plant/device.")
            recent_commands = self._fetch_recent_commands(active_device or None)
            first_command = recent_commands[0] if recent_commands else {}
            recent_command_id = first_command.get("id") if isinstance(first_command, dict) else st.session_state.get("last_queued_command_id")
            st.markdown(
                """
                <div style="display:grid;grid-template-columns:1fr 1fr;gap:0.6rem;margin-bottom:0.9rem">
                  <div style="background:rgba(92,187,132,0.08);border:1px solid rgba(92,187,132,0.2);border-radius:14px;padding:0.7rem 0.85rem">
                    <div style="font-size:0.78rem;font-weight:700;color:#5cbb84;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.4rem">Plant looks better</div>
                    <div style="font-size:0.8rem;color:#aeb5c0;line-height:1.5">Leaves are firm and upright · Colour is vivid green · Soil feels right</div>
                  </div>
                  <div style="background:rgba(230,96,96,0.08);border:1px solid rgba(230,96,96,0.2);border-radius:14px;padding:0.7rem 0.85rem">
                    <div style="font-size:0.78rem;font-weight:700;color:#e66060;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.4rem">Plant looks worse</div>
                    <div style="font-size:0.8rem;color:#aeb5c0;line-height:1.5">Wilting or drooping · Yellowing or browning · Mushy or bone-dry stem</div>
                  </div>
                  <div style="background:rgba(78,160,255,0.08);border:1px solid rgba(78,160,255,0.2);border-radius:14px;padding:0.7rem 0.85rem">
                    <div style="font-size:0.78rem;font-weight:700;color:#4ea0ff;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.4rem">Overwatered</div>
                    <div style="font-size:0.8rem;color:#aeb5c0;line-height:1.5">Soil is soggy · Leaves yellowing or dropping · Stem base feels soft or smells</div>
                  </div>
                  <div style="background:rgba(224,179,62,0.08);border:1px solid rgba(224,179,62,0.25);border-radius:14px;padding:0.7rem 0.85rem">
                    <div style="font-size:0.78rem;font-weight:700;color:#e0b33e;text-transform:uppercase;letter-spacing:0.05em;margin-bottom:0.4rem">Underwatered</div>
                    <div style="font-size:0.8rem;color:#aeb5c0;line-height:1.5">Soil dry and pulling from pot edges · Leaves crispy or curled inward · Drooping despite light</div>
                  </div>
                </div>
                """,
                unsafe_allow_html=True,
            )
            feedback_note = st.text_input("Feedback note", placeholder="Example: plant perked up after 30 minutes")
            c1, c2 = st.columns(2)
            with c1:
                if st.button("Plant looks better"):
                    result = self._save_feedback({"plant_type": plant_name, "feedback_label": "better", "device_id": active_device or None, "command_id": recent_command_id, "notes": feedback_note or None})
                    st.success("Saved positive feedback.") if result else st.error("Failed to save feedback.")
                if st.button("Overwatered"):
                    result = self._save_feedback({"plant_type": plant_name, "feedback_label": "overwatered", "device_id": active_device or None, "command_id": recent_command_id, "notes": feedback_note or None})
                    st.success("Saved overwatering feedback.") if result else st.error("Failed to save feedback.")
            with c2:
                if st.button("Plant looks worse"):
                    result = self._save_feedback({"plant_type": plant_name, "feedback_label": "worse", "device_id": active_device or None, "command_id": recent_command_id, "notes": feedback_note or None})
                    st.success("Saved negative feedback.") if result else st.error("Failed to save feedback.")
                if st.button("Underwatered"):
                    result = self._save_feedback({"plant_type": plant_name, "feedback_label": "underwatered", "device_id": active_device or None, "command_id": recent_command_id, "notes": feedback_note or None})
                    st.success("Saved underwatering feedback.") if result else st.error("Failed to save feedback.")
            feedback_rows = self._fetch_recent_feedback(active_device or None)
            if feedback_rows:
                st.markdown("#### Recent labels")
                for row in feedback_rows[:5]:
                    label = str(row.get("feedback_label", "unknown"))
                    plant = str(row.get("plant_type", "unknown plant"))
                    created_at = str(row.get("created_at", "unknown time"))
                    st.write(f"- {label} | {plant} | {created_at}")
        with right:
            self._render_panel_header("Calibration Wizard", "Tune dry/wet raw values, target moisture, pump flow, and failure thresholds for each plant and sensor.")
            if not active_device:
                st.info("Choose an active ESP32 device in the sidebar first.")
                return
            defaults = calibration or {}
            with st.form("calibration_form"):
                col1, col2 = st.columns(2)
                with col1:
                    soil_raw_dry = int(st.number_input("Dry raw value", min_value=0, max_value=4095, value=int(defaults.get("soil_raw_dry", 3200))))
                    target_moisture = float(st.slider("Target moisture %", min_value=10, max_value=95, value=int(defaults.get("moisture_target_pct", 70))))
                    flow_ml = float(st.number_input("Pump flow (ml/s)", min_value=0.0, max_value=1000.0, value=float(defaults.get("pump_flow_ml_per_sec") or 0.0), step=0.5))
                with col2:
                    soil_raw_wet = int(st.number_input("Wet raw value", min_value=0, max_value=4095, value=int(defaults.get("soil_raw_wet", 1200))))
                    failure_rise = float(st.number_input("Min moisture rise after watering (%)", min_value=0.5, max_value=30.0, value=float(defaults.get("failure_min_rise_pct", 2.0)), step=0.5))
                    failure_window = int(st.number_input("Check window (minutes)", min_value=5, max_value=240, value=int(defaults.get("failure_window_minutes", 45)), step=5))
                notes = st.text_input("Calibration note", value=str(defaults.get("notes") or ""))
                submitted = st.form_submit_button("Save Calibration")
            if submitted:
                result = self._save_calibration({"device_id": active_device, "plant_type": plant_name, "soil_raw_dry": soil_raw_dry, "soil_raw_wet": soil_raw_wet, "moisture_target_pct": target_moisture, "pump_flow_ml_per_sec": flow_ml or None, "failure_min_rise_pct": failure_rise, "failure_window_minutes": failure_window, "notes": notes or None})
                if result and result.get("calibration"):
                    st.success("Calibration saved.")
                    calibration = result["calibration"]
                else:
                    st.error("Failed to save calibration.")
            if calibration:
                st.markdown("#### Active calibration")
                st.write(f"- Dry raw: {calibration.get('soil_raw_dry', '--')}")
                st.write(f"- Wet raw: {calibration.get('soil_raw_wet', '--')}")
                st.write(f"- Target moisture: {calibration.get('moisture_target_pct', '--')}%")
                st.write(
                    f"- Failure threshold: {calibration.get('failure_min_rise_pct', '--')}% in {calibration.get('failure_window_minutes', '--')} min"
                )

    def _render_reports_tab(self, active_device: str) -> None:
        self._render_panel_header("Reports", "Full sensor history, logs, and downloads for all connected sensors.")

        col_lim, col_dl = st.columns([3, 1])
        with col_lim:
            limit = st.select_slider(
                "How many readings to load",
                options=[50, 100, 200, 500],
                value=200,
                key="reports_limit",
            )

        rows = self._fetch_recent_readings(active_device or None, limit=limit)

        if not rows:
            st.info("No sensor data found. Connect an ESP32 and make sure it is sending readings.")
            return

        df = pd.DataFrame(rows)
        df["timestamp"] = pd.to_datetime(df["timestamp"], errors="coerce")
        df = df.dropna(subset=["timestamp"]).sort_values("timestamp")
        df["value"] = pd.to_numeric(df["value"], errors="coerce")

        with col_dl:
            st.markdown("<div style='padding-top:0.65rem'>", unsafe_allow_html=True)
            csv = df.to_csv(index=False).encode("utf-8")
            st.download_button(
                "Download CSV",
                data=csv,
                file_name="balcony_green_sensor_log.csv",
                mime="text/csv",
                use_container_width=True,
            )
            st.markdown("</div>", unsafe_allow_html=True)

        sensor_meta = {
            "soil_moisture":     {"label": "Soil Moisture (%)",      "unit": "%"},
            "soil_raw":          {"label": "Soil Raw ADC",            "unit": "raw"},
            "temperature":       {"label": "Temperature (°C)",        "unit": "°C"},
            "humidity":          {"label": "Humidity (%)",            "unit": "%"},
            "light":             {"label": "Light (lux)",             "unit": "lux"},
            "soil_ph":           {"label": "Soil pH",                 "unit": "pH"},
            "weather_temp_c":    {"label": "Weather Temp (°C)",       "unit": "°C"},
            "weather_humidity_pct": {"label": "Weather Humidity (%)", "unit": "%"},
            "forecast_rain_mm":  {"label": "Forecast Rain (mm)",      "unit": "mm"},
        }

        present_sensors = sorted(df["sensor_name"].dropna().unique().tolist())

        st.markdown("### Sensor Charts")
        for sensor in present_sensors:
            meta = sensor_meta.get(sensor, {"label": sensor.replace("_", " ").title(), "unit": ""})
            sensor_df = df[df["sensor_name"] == sensor][["timestamp", "value"]].set_index("timestamp")
            if sensor_df.empty:
                continue
            sensor_df.columns = [meta["label"]]
            with st.expander(f"{meta['label']}  —  {len(sensor_df)} readings", expanded=True):
                latest = sensor_df.iloc[-1, 0]
                mn = sensor_df.iloc[:, 0].min()
                mx = sensor_df.iloc[:, 0].max()
                avg = sensor_df.iloc[:, 0].mean()
                m1, m2, m3, m4 = st.columns(4)
                m1.metric("Latest",  f"{latest:.2f} {meta['unit']}")
                m2.metric("Min",     f"{mn:.2f} {meta['unit']}")
                m3.metric("Max",     f"{mx:.2f} {meta['unit']}")
                m4.metric("Average", f"{avg:.2f} {meta['unit']}")
                st.line_chart(sensor_df, height=180)

        st.markdown("### Full Data Log")
        sensor_filter = st.multiselect(
            "Filter by sensor",
            options=present_sensors,
            default=present_sensors,
            key="reports_sensor_filter",
        )
        filtered = df[df["sensor_name"].isin(sensor_filter)][
            ["timestamp", "sensor_name", "value", "source", "device_id"]
        ].sort_values("timestamp", ascending=False)
        filtered["timestamp"] = filtered["timestamp"].dt.strftime("%Y-%m-%d %H:%M:%S")
        st.dataframe(filtered, use_container_width=True, height=400)

        st.markdown("### Watering Log")
        commands = self._fetch_recent_commands(active_device or None)
        if commands:
            cmd_rows = []
            for c in commands:
                payload = c.get("payload") or {}
                cmd_rows.append({
                    "Time":        str(c.get("created_at", ""))[:19],
                    "Device":      str(c.get("device_id", "")),
                    "Status":      str(c.get("status", "")),
                    "Pump (ms)":   payload.get("pump_ms", "--"),
                    "Plant":       str(payload.get("plant_type", "")),
                    "Reason":      str(payload.get("reason", "")),
                    "Ack time":    str(c.get("acknowledged_at") or "")[:19],
                    "Note":        str(c.get("device_message") or ""),
                })
            st.dataframe(pd.DataFrame(cmd_rows), use_container_width=True)
        else:
            st.info("No watering commands recorded yet.")

        score_history = st.session_state.get("_health_score_history", [])
        if len(score_history) >= 2:
            st.markdown("### Plant Health Score Trend")
            hs_df = pd.DataFrame({"Health Score": score_history})
            st.line_chart(hs_df, height=180)

    def _render_main_content(self, sensor_source: str, active_device: str, weather_city: str | None) -> None:
        self._ingest_sensor_data(sensor_source)
        self._hydrate_latest_snapshot(active_device)
        plant_name = st.session_state.get("predicted_plant", "Tomato")
        self._update_disease_prediction(st.session_state.get("uploaded_image"), plant_name)
        disease_prediction = st.session_state.get("latest_disease_prediction", {})
        prediction, calibration = self._build_prediction(plant_name, active_device, sensor_source, weather_city)
        health_score, hs_breakdown, hs_trend = self._compute_health_score(
            st.session_state.get("latest_readings"), plant_name, disease_prediction, calibration
        )
        failures = self._fetch_pump_failures(active_device or None) if self.access_token else []
        backend_ok = self._backend_online()
        self._render_hero(backend_ok, active_device, prediction, health_score, hs_trend)
        if st.session_state.get("open_health_upload"):
            st.info("Go to the `Plant Health` tab to upload a leaf photo from your phone or computer.")
        self._render_device_management_panel(active_device)
        self._render_kpis(prediction, disease_prediction, health_score, hs_trend)
        tab_options = ["Overview", "Plant Health", "Automation", "Analytics", "Learning", "Reports"]
        active_tab = st.segmented_control(
            "Section",
            options=tab_options,
            default=str(st.session_state.get("active_dashboard_tab", "Overview") or "Overview"),
            key="active_dashboard_tab",
            selection_mode="single",
        )
        active_tab = str(active_tab or st.session_state.get("active_dashboard_tab", "Overview") or "Overview")
        if active_tab == "Overview":
            left, right = st.columns([1.05, 0.95])
            with left:
                self._render_panel_header("Overview", "Live operational status for the active plant profile and connected device.")
                self._render_health_score_card(health_score, hs_breakdown, hs_trend)
                self._render_compact_overview_details(
                    plant_name,
                    active_device,
                    disease_prediction,
                    st.session_state.get("latest_readings"),
                )
                self._render_sensor_trends(active_device)
            with right:
                self._render_alerts(prediction, disease_prediction, failures, health_score, hs_trend)
                self._render_system_status(backend_ok, active_device)
                self._render_recent_activity(active_device)
                if st.session_state.get("latest_readings"):
                    with st.expander("Latest sensor snapshot"):
                        st.json(st.session_state["latest_readings"])
        elif active_tab == "Plant Health":
            self._render_plant_health_tab(plant_name)
        elif active_tab == "Automation":
            self._render_automation_tab(plant_name, active_device, prediction, calibration)
        elif active_tab == "Analytics":
            self._render_analytics_tab(active_device)
        elif active_tab == "Learning":
            self._render_learning_tab(plant_name, active_device, calibration)
        else:
            self._render_reports_tab(active_device)

    def run(self) -> None:
        self._inject_styles()
        if not self.access_token:
            st.info("You are browsing as a guest. Log in to unlock relay control, calibration, watering history, and persistent analytics.")
        sensor_source, active_device, weather_city = self._render_sidebar()
        active_tab = str(st.session_state.get("active_dashboard_tab", "Overview") or "Overview")
        refresh_interval = (
            LIVE_REFRESH_INTERVAL_SECONDS
            if self.stream_controller.is_streaming() and active_tab in LIVE_REFRESH_TABS
            else None
        )

        @st.fragment(run_every=refresh_interval)
        def render_main_content_fragment() -> None:
            self._render_main_content(sensor_source, active_device, weather_city)

        render_main_content_fragment()


def main_page(access: str | None = None) -> None:
    BalconyGreenApp(access_token=access).run()


if __name__ == "__main__":
    main_page()
