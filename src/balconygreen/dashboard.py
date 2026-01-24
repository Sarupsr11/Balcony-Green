import random
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional
import datetime
import requests  # type: ignore
import streamlit as st  # type: ignore
from inference import EfficientNetClassifier  # type: ignore
from PIL import Image  # type: ignore
from balconygreen.sensor_reading import SensorReader
from camera_sensor import ExternalCameraSensor, ImageInput
import uuid
PROJECT_ROOT = Path(__file__).resolve().parents[2]

CKPT_PATH_TOMATO_11 = PROJECT_ROOT / "disease-detection" / "Tomatoes" / "Models" / "efficientnet_best_multiple_sources.pth"
CKPT_PATH_TOMATO_2 = PROJECT_ROOT / "disease-detection" / "Tomatoes" / "Models" / "efficientnet_binary_best_multiple_sources.pth"

FASTAPI_URL = "http://127.0.0.1:8000"
api_key = "https://api.open-meteo.com/v1/forecast"





# =========================
# STREAM CONTROLLER
# =========================
class StreamController:
    def __init__(self):
        if "streaming" not in st.session_state:
            st.session_state.streaming = False

    def controls(self):
        col1, col2 = st.columns(2)
        with col1:
            if st.button("▶ Start Stream"):
                st.session_state.streaming = True
        with col2:
            if st.button("⏹ Stop Stream"):
                st.session_state.streaming = False

    def is_streaming(self):
        return st.session_state.streaming


# =========================
# MAIN APP
# =========================
class BalconyGreenApp:
    def __init__(self, access_token: str | None):

        self.access_token = access_token
        self.headers = (
            {"Authorization": f"Bearer {access_token}"}
            if access_token else None
        )

        if not access_token:
            st.info("You are using Balcony Green as a guest. Sensor data will not be saved.")

        st.set_page_config("Balcony Green", layout="centered")
        st.title("🌱 Balcony Green – Smart Plant Monitor")


        # Initialize session state
        if "page_func" not in st.session_state:
            st.session_state["page_func"] = "Home"
        if "predicted_plant" not in st.session_state:
            st.session_state["predicted_plant"] = None

        CAMERA_SNAPSHOT_URL = "http://192.168.1.100/capture"
        self.camera = ExternalCameraSensor(CAMERA_SNAPSHOT_URL)
        self.image_input = ImageInput(self.camera, self.access_token)

        self.sensor_reader: Optional[SensorReader] = None
        self.stream_controller = StreamController()

        self.classifier_all = self.load_classifier_all()
        self.classifier_binary = self.load_classifier_binary()

    @st.cache_resource
    def load_classifier_all(_self):
        return EfficientNetClassifier(
            model_path=CKPT_PATH_TOMATO_11,
            num_classes=11
        )

    @st.cache_resource
    def load_classifier_binary(_self):
        return EfficientNetClassifier(
            model_path=CKPT_PATH_TOMATO_2,
            num_classes=2
        )

    def predict_tomato_image(self, image: Image.Image):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            image.save(tmp.name)
            return self.classifier_all.predict(tmp.name, top_k=3, confidence_threshold=0.0), \
                   self.classifier_binary.predict(tmp.name)

    def predict_plant(self, image: Image.Image):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            image.save(tmp.name)
            return random.choice(["Tomato", "Potato", "Mint"])

    def run(self):

        st.subheader("Home Page")

        # -----------------------
        # SENSOR REGISTRATION
        # -----------------------
        st.subheader("🔌 Connect Your Sensors")
        sensor_type = st.multiselect("Sensor Type", ["temperature", "humidity", "soil_moisture", "soil_ph", "camera"])
        device_info = st.text_input("Device IP / ID / Endpoint (leave blank if using Weather API)")

        if st.button("Register Sensor"):
            if device_info:
                for sensors in sensor_type:
                    payload = {"sensor_name": sensors, "sensor_source"           : "Environment Sensors",
                                "device_info": device_info}
                    headers={
                        "Authorization": f"Bearer {self.access_token}"
                    }
                    try:
                        requests.post(f"{FASTAPI_URL}/register_sensors", json=payload, headers=headers, timeout=3)
                        st.success(f"{sensor_type} sensor registered!")
                    except:
                        st.error(f"Failed to register sensor {sensors}")
            else:
                st.info("Leave blank if using Weather API instead")

        # -----------------------
        # SENSOR SOURCE SELECTION
        # -----------------------
        st.subheader("📊 Numerical Sensor Data")
        sensor_source = st.radio("Select source for numerical readings:", ["Environment Sensors", "Weather API"])
        city = st.text_input("City (Weather API only)", "London") if sensor_source == "Weather API" else None
        if sensor_source == "Weather API":
            sensor_type = st.multiselect("Choose Parameters", ["temperature", "humidity"])
            headers = {
                "Authorization": f"Bearer {self.access_token}"
            }

            for sensor in sensor_type:  
                payload = {
                    "sensor_name": sensor,
                    "sensor_source": "Weather API",
                    "device_info": api_key
                }

                try:
                    r = requests.post(
                        f"{FASTAPI_URL}/register_sensors",
                        json=payload,
                        headers=headers,
                        timeout=3
                    )

                    print(r.status_code, r.text)

                    if r.status_code == 200:
                        data = r.json()
                        if data.get("status") == "success":
                            st.success(f"{sensor} sensor registered!")
                    else:
                        st.error(f"Failed to register {sensor}: {r.text}")

                except Exception as e:
                    st.error(f"Request failed for {sensor}: {e}")



        self.sensor_reader = SensorReader(access_token=self.access_token, source=sensor_source, city=city, api_key=api_key)

        # Start streaming continuously
        self.stream_controller.controls()  

        last_saved = datetime.datetime.now()
        placeholder = st.empty()
        while self.stream_controller.is_streaming():
            readings = self.sensor_reader.read()
            
            # Show in Streamlit
            placeholder.json(readings)
            
            # Send to FastAPI periodically (30 minutues)
            now = datetime.datetime.now()
            if (now-last_saved).total_seconds() >= 30*60:
                self.sensor_reader.send_to_api(readings, sensor_source)
                last_saved = now
    
            time.sleep(1)  # adjust the interval as needed


        # -----------------------
        # IMAGE INPUT
        # -----------------------
        image = self.image_input.render()

        if image and st.session_state["page_func"] == "Home":
            st.session_state["uploaded_image"] = image
            predicted_plant = self.predict_plant(image)
            st.session_state["predicted_plant"] = predicted_plant
            if st.button("Predict & Go to Plant Page"):
                st.session_state["page_func"] = "PlantPage"

        # -----------------------
        # PLANT PAGE
        # -----------------------
        elif st.session_state.get("page_func") == "PlantPage":
            plant_name = st.session_state.get("predicted_plant", "Unknown")
            uploaded_image = st.session_state.get("uploaded_image", None)

            st.header(f"🧠 {plant_name} Health & Analytics")

            col1, col2 = st.columns([1, 1])
            with col1:
                st.subheader("🌱 Plant Image")
                if uploaded_image:
                    st.image(uploaded_image, width=300)
                else:
                    st.write("No image available")

            with col2:
                st.subheader("Prediction")
                st.write(f"Predicted Plant: **{plant_name}**")
                st.write("Confidence: 92%")  # placeholder
                st.subheader("🧠 Health Prediction")
                if uploaded_image:
                    health_status = False
                    results_1, results_2 = self.predict_tomato_image(uploaded_image)
                    for r in results_2:
                        if r["confidence"] * 100 > 80:
                            health_status = True
                            st.success(f"{r['class_name']}")
                    if health_status and st.button("Possible Disease Type"):
                        for r in results_1:
                            st.success(f"{r['class_name']} — {r['confidence']*100:.6f}%")

            st.divider()
            st.subheader("📊 Live Sensor Data")
            self.stream_controller.controls()
            placeholder = st.empty()

            # while self.stream_controller.is_streaming():
            #     readings = self.sensor_reader.read()
            #     placeholder.json(readings)
            #     self.sensor_reader.send_to_api(readings, sensor_source)
            #     time.sleep(1)

            if st.button("⬅ Back to Home"):
                st.session_state["page_func"] = "Home"
                st.session_state["predicted_plant"] = None


# =========================
# ENTRY POINT
# =========================
def main_page(access: str):
    BalconyGreenApp(access_token = access).run()
