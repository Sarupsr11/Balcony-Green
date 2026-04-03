from __future__ import annotations

import datetime
import tempfile
import time
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


PROJECT_ROOT = Path(__file__).resolve().parents[2]
CKPT_PATH_TOMATO_11 = PROJECT_ROOT / "disease-detection" / "Tomatoes" / "Models" / "efficientnet_best_multiple_sources.pth"
CKPT_PATH_TOMATO_2 = PROJECT_ROOT / "disease-detection" / "Tomatoes" / "Models" / "efficientnet_binary_best_multiple_sources.pth"


class StreamController:
    def __init__(self) -> None:
        if "streaming" not in st.session_state:
            st.session_state.streaming = False

    def controls(self) -> None:
        c1, c2, c3 = st.columns(3)
        with c1:
            if st.button("Start"):
                st.session_state.streaming = True
        with c2:
            if st.button("Stop"):
                st.session_state.streaming = False
        with c3:
            if st.button("Read Once"):
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
            "sensor_history": [],
            "uploaded_image": None,
            "latest_disease_prediction": {"label": "healthy", "confidence": 0.0, "top_results": []},
            "force_single_read": False,
            "camera_url": DEFAULT_CAMERA_URL,
            "active_device_id": "",
            "last_queued_command_id": None,
            "last_saved_at": None,
        }
        for key, value in defaults.items():
            if key not in st.session_state:
                st.session_state[key] = value

        self.camera = ExternalCameraSensor(st.session_state["camera_url"])
        self.image_input = ImageInput(self.camera, self.access_token)
        self.sensor_reader: Optional[SensorReader] = None
        self.stream_controller = StreamController()
        self.watering_ai = WateringAIService()
        self.classifier_all = self.load_classifier_all()
        self.classifier_binary = self.load_classifier_binary()

    @st.cache_resource
    def load_classifier_all(_self):
        try:
            try:
                from balconygreen.inference import EfficientNetClassifier
            except ModuleNotFoundError:
                from inference import EfficientNetClassifier  # type: ignore
            return EfficientNetClassifier(model_path=CKPT_PATH_TOMATO_11, num_classes=11)
        except Exception:
            return None

    @st.cache_resource
    def load_classifier_binary(_self):
        try:
            try:
                from balconygreen.inference import EfficientNetClassifier
            except ModuleNotFoundError:
                from inference import EfficientNetClassifier  # type: ignore
            return EfficientNetClassifier(model_path=CKPT_PATH_TOMATO_2, num_classes=2)
        except Exception:
            return None

    def _inject_styles(self) -> None:
        st.markdown(
            """
            <style>
            [data-testid="stAppViewContainer"] {background:
                radial-gradient(circle at top left, rgba(54,118,80,0.30), transparent 24%),
                radial-gradient(circle at top right, rgba(208,154,44,0.14), transparent 20%),
                linear-gradient(180deg, #08110f 0%, #0b1418 55%, #091117 100%);}
            [data-testid="stSidebar"] {background: linear-gradient(180deg, #0d1d19 0%, #0a1216 100%);}
            .block-container {max-width: 1380px; padding-top: 1.2rem; padding-bottom: 2rem;}
            .hero-card {border:1px solid rgba(146,214,177,0.16); background:linear-gradient(135deg, rgba(20,55,41,0.92), rgba(12,18,24,0.94)); padding:1.5rem 1.7rem; border-radius:26px; box-shadow:0 18px 40px rgba(0,0,0,0.24);}
            .hero-title {font-size:2.08rem; font-weight:760; color:#f6faf7; margin-bottom:0.35rem;}
            .hero-subtitle {color:#b5c5bc; line-height:1.5; margin:0;}
            .pill {display:inline-flex; padding:0.35rem 0.7rem; border-radius:999px; font-size:0.84rem; margin:0.55rem 0.45rem 0 0; border:1px solid rgba(255,255,255,0.06);}
            .good {background:rgba(92,187,132,0.14); color:#d7f6e1;}
            .warn {background:rgba(224,179,62,0.14); color:#ffe6a5;}
            .bad {background:rgba(230,96,96,0.15); color:#ffd4d4;}
            .panel-card {border:1px solid rgba(255,255,255,0.07); background:rgba(9,15,20,0.78); border-radius:22px; padding:1rem 1.1rem; margin-bottom:1rem;}
            .panel-title {font-size:1.03rem; font-weight:680; color:#f5f9f6; margin-bottom:0.25rem;}
            .panel-muted {color:#9fb0a7; font-size:0.9rem; line-height:1.45;}
            [data-testid="stMetric"] {background:linear-gradient(180deg, rgba(15,22,28,0.92), rgba(10,15,19,0.88)); border:1px solid rgba(255,255,255,0.06); padding:0.9rem 1rem; border-radius:20px;}
            [data-baseweb="tab"] {background:rgba(255,255,255,0.04); border-radius:14px; padding:0.55rem 0.9rem; height:auto;}
            </style>
            """,
            unsafe_allow_html=True,
        )

    def _api_get(self, path: str, params: dict[str, Any] | None = None) -> Any | None:
        if not self.headers:
            return None
        try:
            response = requests.get(f"{API_BASE_URL}{path}", params=params, headers=self.headers, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def _api_post(self, path: str, payload: dict[str, Any]) -> Any | None:
        if not self.headers:
            return None
        try:
            response = requests.post(f"{API_BASE_URL}{path}", json=payload, headers=self.headers, timeout=5)
            response.raise_for_status()
            return response.json()
        except Exception:
            return None

    def _safe_float(self, value: Any) -> float | None:
        try:
            return None if value in (None, "") else float(value)
        except Exception:
            return None

    def _reading_value(self, readings: dict[str, Any] | None, *keys: str) -> float | None:
        if not readings:
            return None
        for key in keys:
            value = self._safe_float(readings.get(key))
            if value is not None:
                return value
        return None

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
        except Exception:
            return False

    def predict_tomato_image(self, image: Image.Image):
        if self.classifier_all is None or self.classifier_binary is None:
            return [], []
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            image.save(tmp.name)
            return (
                self.classifier_all.predict(tmp.name, top_k=3, confidence_threshold=0.0),
                self.classifier_binary.predict(tmp.name),
            )

    def _register_selected_sensors(self, sensor_names: list[str], device_info: str) -> None:
        if not self.access_token:
            st.warning("Login is required to register sensors.")
            return
        if not device_info:
            st.info("Add a device ID or endpoint before registering local sensors.")
            return
        for sensor_name in sensor_names:
            result = self._api_post(
                "/register_sensors",
                {"sensor_name": sensor_name, "sensor_source": "Environment Sensors", "device_info": device_info},
            )
            st.success(f"{sensor_name} registered.") if result else st.error(f"Failed to register {sensor_name}.")

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
        return self._api_get("/commands/recent", params=params) or []

    def _fetch_recent_feedback(self, device_id: str | None = None) -> list[dict]:
        params = {"limit": 6}
        if device_id:
            params["device_id"] = device_id
        return self._api_get("/watering_feedback/recent", params=params) or []

    def _fetch_water_usage_analytics(self, device_id: str | None = None) -> dict[str, Any]:
        params = {"device_id": device_id} if device_id else None
        return self._api_get("/analytics/water_usage", params=params) or {}

    def _fetch_pump_failures(self, device_id: str | None = None) -> list[dict]:
        params = {"limit": 6}
        if device_id:
            params["device_id"] = device_id
        return self._api_get("/analytics/pump_failures", params=params) or []

    def _fetch_recent_readings(self, device_id: str | None = None, limit: int = 100) -> list[dict]:
        params: dict[str, Any] = {"limit": limit}
        if device_id:
            params["device_id"] = device_id
        return self._api_get("/readings", params=params) or []

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
            st.session_state["last_queued_command_id"] = result.get("command_id")
            st.success(f"Queued watering for {result['device_id']} with {result['payload']['pump_ms']} ms.")
        else:
            st.error("Failed to queue relay command.")

    def _append_sensor_history(self, readings: dict[str, float], source: str) -> None:
        if not readings:
            return
        stamped = dict(readings)
        stamped["source"] = source
        stamped["timestamp"] = datetime.datetime.utcnow().isoformat(timespec="seconds")
        st.session_state["latest_readings"] = stamped
        history = st.session_state["sensor_history"]
        history.append(stamped)
        st.session_state["sensor_history"] = history[-36:]

    def _ingest_sensor_data(self, sensor_source: str) -> None:
        last_saved_at = st.session_state.get("last_saved_at")
        if st.session_state.get("force_single_read"):
            readings = self.sensor_reader.read() if self.sensor_reader else {}
            self._append_sensor_history(readings, sensor_source)
            st.session_state["force_single_read"] = False
        elif self.stream_controller.is_streaming():
            readings = self.sensor_reader.read() if self.sensor_reader else {}
            self._append_sensor_history(readings, sensor_source)
            now = datetime.datetime.utcnow()
            if self.sensor_reader and (
                last_saved_at is None
                or (now - datetime.datetime.fromisoformat(str(last_saved_at))).total_seconds() >= 30 * 60
            ):
                self.sensor_reader.send_to_api(readings, sensor_source)
                st.session_state["last_saved_at"] = now.isoformat()
            time.sleep(1)
            st.rerun()

    def _render_sidebar(self) -> tuple[str, str]:
        with st.sidebar:
            st.markdown("## Control Center")
            st.caption("Live plant profile, linked device, and sensor controls.")
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
            st.session_state["active_device_id"] = active_device.strip()
            camera_url = st.text_input("Camera capture URL", value=st.session_state.get("camera_url", DEFAULT_CAMERA_URL))
            st.session_state["camera_url"] = camera_url.strip() or DEFAULT_CAMERA_URL
            self.camera.snapshot_url = st.session_state["camera_url"]
            sensor_source = st.radio("Reading source", ["Environment Sensors", "Weather API"])
            city = st.text_input("Weather city", "London") if sensor_source == "Weather API" else None
            with st.expander("Register sensors", expanded=False):
                sensor_names = st.multiselect("Sensor types", ["temperature", "humidity", "soil_moisture", "soil_raw", "soil_ph", "light", "camera", "pump_relay"])
                register_device = st.text_input("Device ID / endpoint", value=st.session_state.get("active_device_id", ""), key="register_device_info")
                if st.button("Register selected sensors"):
                    self._register_selected_sensors(sensor_names, register_device)
            if sensor_source == "Weather API":
                with st.expander("Weather inputs", expanded=False):
                    weather_params = st.multiselect("Weather parameters", ["temperature", "humidity", "light"])
                    if st.button("Register weather parameters"):
                        self._register_weather_params(weather_params)
            st.markdown("### Live controls")
            self.stream_controller.controls()
            st.caption("Streaming active." if self.stream_controller.is_streaming() else "Streaming paused.")
        self.sensor_reader = SensorReader(access_token=self.access_token, source=sensor_source, city=city, api_key=OPEN_METEO_URL)
        return sensor_source, st.session_state.get("active_device_id", "")

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

    def _build_prediction(self, plant_name: str, active_device: str) -> tuple[Any | None, dict[str, Any] | None]:
        readings = st.session_state.get("latest_readings")
        if not readings:
            return None, None
        calibration = self._fetch_latest_calibration(active_device, plant_name) if self.access_token and active_device else None
        disease_prediction = st.session_state.get("latest_disease_prediction", {})
        prediction = self.watering_ai.predict(
            sensor_readings=readings,
            plant_type=plant_name,
            disease_label=disease_prediction.get("label", "healthy"),
            disease_confidence=float(disease_prediction.get("confidence", 0.0)),
            history=st.session_state.get("sensor_history", []),
            calibration=calibration,
        )
        return prediction, calibration

    def _render_panel_header(self, title: str, subtitle: str) -> None:
        st.markdown(f"<div class='panel-card'><div class='panel-title'>{title}</div><div class='panel-muted'>{subtitle}</div></div>", unsafe_allow_html=True)

    def _render_hero(self, backend_ok: bool, active_device: str, prediction) -> None:
        disease_ready = self.classifier_all is not None and self.classifier_binary is not None
        pills = [
            ("Backend Online" if backend_ok else "Backend Offline", "good" if backend_ok else "bad"),
            ("Watering AI Ready", "good"),
            ("Disease Model Ready" if disease_ready else "Disease Fallback", "good" if disease_ready else "warn"),
            (f"Device {active_device or 'Not linked'}", "warn" if not active_device else "good"),
        ]
        if prediction is not None:
            pills.append((f"Next watering {prediction.probable_next_watering_hours}h", "warn" if prediction.should_water else "good"))
        pill_html = "".join(f"<span class='pill {kind}'>{label}</span>" for label, kind in pills)
        st.markdown(
            f"""
            <div class="hero-card">
                <div class="hero-title">Balcony Green Control Center</div>
                <p class="hero-subtitle">A real-time plant dashboard for disease detection, predictive irrigation, relay control, calibration, and post-watering diagnostics.</p>
                <div>{pill_html}</div>
            </div>
            """,
            unsafe_allow_html=True,
        )

    def _render_kpis(self, prediction, disease_prediction: dict[str, Any]) -> None:
        readings = st.session_state.get("latest_readings")
        soil = self._reading_value(readings, "soil_moisture_pct", "soil_moisture")
        temp = self._reading_value(readings, "temperature_c", "temperature")
        light = self._reading_value(readings, "light_lux", "light")
        humidity = self._reading_value(readings, "humidity_pct", "humidity")
        c1, c2, c3, c4 = st.columns(4)
        with c1:
            st.metric("Soil Moisture", f"{soil:.1f}%" if soil is not None else "--", None if self._history_delta("soil_moisture_pct", "soil_moisture") is None else f"{self._history_delta('soil_moisture_pct', 'soil_moisture'):+.1f}%")
        with c2:
            st.metric("Temperature", f"{temp:.1f} C" if temp is not None else "--", None if self._history_delta("temperature_c", "temperature") is None else f"{self._history_delta('temperature_c', 'temperature'):+.1f} C")
        with c3:
            st.metric("Light", f"{int(light)} lux" if light is not None else "--", None if self._history_delta("light_lux", "light") is None else f"{self._history_delta('light_lux', 'light'):+.0f}")
        with c4:
            if prediction is not None:
                st.metric("Watering Forecast", f"{prediction.probable_next_watering_hours} h", f"{prediction.watering_probability * 100:.0f}% confidence")
            else:
                st.metric("Health Signal", disease_prediction.get("label", "healthy").replace("_", " "), f"{float(disease_prediction.get('confidence', 0.0)) * 100:.0f}% confidence")
        if humidity is not None:
            st.caption(f"Ambient humidity: {humidity:.1f}%")

    def _render_alerts(self, prediction, disease_prediction: dict[str, Any], failures: list[dict]) -> None:
        alerts: list[tuple[str, str, str]] = []
        if st.session_state.get("latest_readings") is None:
            alerts.append(("warn", "No live snapshot", "Use Read Once or start streaming to populate the dashboard."))
        if prediction is not None and prediction.should_water:
            alerts.append(("warn", "Watering recommended", f"Model confidence is {prediction.watering_probability * 100:.1f}% with {prediction.recommended_pump_ms} ms suggested pump time."))
        label = str(disease_prediction.get("label", "healthy")).lower()
        if label not in {"healthy", "unknown", "unknown_non_target", "other_plant", ""}:
            alerts.append(("bad", "Disease signal detected", f"Leaf analysis reported {label} with {float(disease_prediction.get('confidence', 0.0)) * 100:.1f}% confidence."))
        if prediction is not None and prediction.missing_inputs:
            alerts.append(("warn", "Defaulted inputs", "Model filled missing values for: " + ", ".join(prediction.missing_inputs)))
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
        st.write(f"**Backend API:** {'Online' if backend_ok else 'Offline'}")
        st.write("**Watering model:** Ready")
        st.write(f"**Disease model:** {'Ready' if disease_ready else 'Fallback mode'}")
        st.write(f"**Session mode:** {'Authenticated' if self.access_token else 'Guest'}")
        st.write(f"**Linked device:** {active_device or 'Not linked'}")

    def _render_sensor_trends(self, active_device: str) -> None:
        self._render_panel_header("Sensor Trends", "Session trends and recent backend telemetry for the selected device.")
        history = st.session_state.get("sensor_history", [])
        if history:
            frame = pd.DataFrame(history)
            frame["timestamp"] = pd.to_datetime(frame["timestamp"], errors="coerce")
            frame = frame.dropna(subset=["timestamp"]).set_index("timestamp")
            soil_cols = [c for c in ["soil_moisture", "soil_moisture_pct", "soil_raw"] if c in frame.columns]
            env_cols = [c for c in ["temperature", "temperature_c", "humidity", "humidity_pct", "light", "light_lux"] if c in frame.columns]
            if soil_cols:
                st.line_chart(frame[soil_cols], height=200)
            if env_cols:
                st.line_chart(frame[env_cols], height=200)
        else:
            st.info("No session history yet.")
        rows = self._fetch_recent_readings(active_device or None, limit=80)
        if rows:
            backend = pd.DataFrame(rows)
            backend["timestamp"] = pd.to_datetime(backend["timestamp"], errors="coerce")
            backend = backend.dropna(subset=["timestamp"])
            if not backend.empty:
                pivot = backend.pivot_table(index="timestamp", columns="sensor_name", values="value", aggfunc="last").sort_index()
                st.caption("Backend telemetry history")
                st.line_chart(pivot.tail(40), height=220)

    def _render_recent_activity(self, active_device: str) -> None:
        self._render_panel_header("Recent Activity", "Recent relay commands and human feedback labels.")
        commands = self._fetch_recent_commands(active_device or None)
        feedback = self._fetch_recent_feedback(active_device or None)
        if not commands and not feedback:
            st.caption("No recent commands or feedback yet.")
            return
        for command in commands[:4]:
            st.write(f"- Command `{command['status']}` for `{command['device_id']}` at {command['created_at']}")
        for row in feedback[:4]:
            st.write(f"- Feedback `{row['feedback_label']}` for `{row['plant_type']}` at {row['created_at']}")

    def _render_plant_health_tab(self, plant_name: str) -> None:
        left, right = st.columns([1.1, 0.9])
        with left:
            self._render_panel_header("Plant Health Input", "Capture or upload a leaf image. The result is fused into watering decisions.")
            image = self.image_input.render()
            if image:
                st.session_state["uploaded_image"] = image
            uploaded_image = st.session_state.get("uploaded_image")
            if uploaded_image:
                st.image(uploaded_image, caption=f"{plant_name} image", use_container_width=True)
            else:
                st.info("Add a plant image to run the health model.")
        with right:
            self._render_panel_header("Health Summary", "Live disease classification, confidence, and top alternative matches.")
            self._update_disease_prediction(st.session_state.get("uploaded_image"), plant_name)
            disease_prediction = st.session_state.get("latest_disease_prediction", {})
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
                st.markdown("#### Decision drivers")
                for reason in prediction.reasons:
                    st.write(f"- {reason}")
                with st.expander("Model inputs used"):
                    st.json(prediction.normalized_inputs)
                if prediction.missing_inputs:
                    st.warning("Model defaulted: " + ", ".join(prediction.missing_inputs))
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
            else:
                st.caption("No calibration saved for this device yet.")
            commands = self._fetch_recent_commands(active_device or None)
            if commands:
                st.markdown("#### Recent commands")
                for command in commands[:5]:
                    pump_ms = command.get("payload", {}).get("pump_ms", 0)
                    st.write(f"- {command['status']} | {pump_ms} ms | {command['created_at']}")

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
                    if row["status"] == "warning":
                        st.error(f"{row['device_id']} | delta {row['moisture_delta']}% is below the expected {row['min_expected_rise_pct']}%.")
                    elif row["status"] == "insufficient_data":
                        st.warning(f"{row['device_id']} | {row['message']}")
                    else:
                        st.success(f"{row['device_id']} | moisture rose by {row['moisture_delta']}% in {row['window_minutes']} minutes.")
            else:
                st.info("No pump diagnostics available yet.")
            readings = st.session_state.get("latest_readings")
            if readings:
                with st.expander("Latest raw snapshot"):
                    st.json(readings)

    def _render_learning_tab(self, plant_name: str, active_device: str, calibration: dict[str, Any] | None) -> None:
        left, right = st.columns([0.95, 1.05])
        with left:
            self._render_panel_header("Learning From Feedback", "Capture whether the plant improved after watering so the next training cycle has human labels.")
            recent_commands = self._fetch_recent_commands(active_device or None)
            recent_command_id = recent_commands[0]["id"] if recent_commands else st.session_state.get("last_queued_command_id")
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
                    st.write(f"- {row['feedback_label']} | {row['plant_type']} | {row['created_at']}")
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
                st.write(f"- Dry raw: {calibration['soil_raw_dry']}")
                st.write(f"- Wet raw: {calibration['soil_raw_wet']}")
                st.write(f"- Target moisture: {calibration['moisture_target_pct']}%")
                st.write(f"- Failure threshold: {calibration['failure_min_rise_pct']}% in {calibration['failure_window_minutes']} min")

    def run(self) -> None:
        self._inject_styles()
        if not self.access_token:
            st.info("Guest mode is active. Login enables relay control, saved calibration, feedback, and analytics persistence.")
        sensor_source, active_device = self._render_sidebar()
        self._ingest_sensor_data(sensor_source)
        plant_name = st.session_state.get("predicted_plant", "Tomato")
        self._update_disease_prediction(st.session_state.get("uploaded_image"), plant_name)
        disease_prediction = st.session_state.get("latest_disease_prediction", {})
        prediction, calibration = self._build_prediction(plant_name, active_device)
        failures = self._fetch_pump_failures(active_device or None) if self.access_token else []
        backend_ok = self._backend_online()
        self._render_hero(backend_ok, active_device, prediction)
        self._render_kpis(prediction, disease_prediction)
        top_left, top_right = st.columns([1.2, 0.8])
        with top_left:
            self._render_panel_header("Overview", "Live operational status for the active plant profile and connected device.")
            readings = st.session_state.get("latest_readings")
            if readings:
                soil = self._reading_value(readings, "soil_moisture_pct", "soil_moisture")
                temp = self._reading_value(readings, "temperature_c", "temperature")
                humidity = self._reading_value(readings, "humidity_pct", "humidity")
                light = self._reading_value(readings, "light_lux", "light")
                l, r = st.columns(2)
                with l:
                    st.write(f"**Plant profile:** {plant_name}")
                    st.write(f"**Active device:** {active_device or 'Not linked'}")
                    st.write(f"**Disease status:** {disease_prediction.get('label', 'healthy').replace('_', ' ')}")
                with r:
                    st.write(f"**Soil moisture:** {soil:.1f}%" if soil is not None else "**Soil moisture:** --")
                    st.write(f"**Temperature:** {temp:.1f} C" if temp is not None else "**Temperature:** --")
                    st.write(f"**Humidity:** {humidity:.1f}%" if humidity is not None else "**Humidity:** --")
                    st.write(f"**Light:** {int(light)} lux" if light is not None else "**Light:** --")
            else:
                st.info("No live sensor snapshot yet.")
        with top_right:
            self._render_alerts(prediction, disease_prediction, failures)
            self._render_system_status(backend_ok, active_device)
        tabs = st.tabs(["Overview", "Plant Health", "Automation", "Analytics", "Learning"])
        with tabs[0]:
            left, right = st.columns([1.15, 0.85])
            with left:
                self._render_sensor_trends(active_device)
            with right:
                self._render_recent_activity(active_device)
                if st.session_state.get("latest_readings"):
                    with st.expander("Latest sensor snapshot"):
                        st.json(st.session_state["latest_readings"])
        with tabs[1]:
            self._render_plant_health_tab(plant_name)
        with tabs[2]:
            self._render_automation_tab(plant_name, active_device, prediction, calibration)
        with tabs[3]:
            self._render_analytics_tab(active_device)
        with tabs[4]:
            self._render_learning_tab(plant_name, active_device, calibration)


def main_page(access: str | None) -> None:
    BalconyGreenApp(access_token=access).run()
