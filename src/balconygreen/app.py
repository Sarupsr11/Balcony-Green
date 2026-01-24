import random
import tempfile
import time
from io import BytesIO
from pathlib import Path

import requests
import streamlit as st
from inference import EfficientNetClassifier  # type: ignore
from PIL import Image
from weather_service import WeatherService

PROJECT_ROOT = Path(__file__).resolve().parents[2]

CKPT_PATH_TOMATO_11  = PROJECT_ROOT / "disease-detection"/"Tomatoes" /"Models"/"efficientnet_best_multiple_sources.pth"
CKPT_PATH_TOMATO_2  = PROJECT_ROOT / "disease-detection"/"Tomatoes" /"Models"/"efficientnet_binary_best_multiple_sources.pth"

# =========================
# EXTERNAL CAMERA SENSOR
# =========================
class ExternalCameraSensor:
    def __init__(self, snapshot_url: str):
        self.snapshot_url = snapshot_url

    def get_image(self):
        try:
            response = requests.get(self.snapshot_url, timeout=3)
            response.raise_for_status()
            return Image.open(BytesIO(response.content))
        except Exception as e:
            st.warning(f"Camera error: {e}")
            return None


# =========================
# WEATHER DATA (API)
# =========================
class WeatherReader:
    def __init__(self, lat=52.52, lon=13.41):
        self.service = WeatherService(lat, lon)

    def read(self):
        data = self.service.get_current_weather()
        if "error" in data:
            return None
        return data

# =========================
# LOCAL SENSOR (MOCK)
# =========================
class HardwareSensorReader:
    @staticmethod
    def read():
        # Simulated hardware values
        return {
            "pot_moisture": round(random.uniform(20, 80), 1),
            "light_lux": int(random.uniform(100, 5000)),
            "battery_level": int(random.uniform(80, 100))
        }


# =========================
# IMAGE INPUT HANDLER
# =========================
class ImageInput:
    def __init__(self, camera):
        self.camera = camera

    def render(self):
        st.subheader("📸 Plant Image Input")

        source = st.radio(
            "Select image source:",
            ["External Camera Sensor", "Upload Image"]
        )

        if source == "External Camera Sensor":
            return self._external_camera()
        else:
            return self._upload_image()

    def _external_camera(self):
        if st.button("📡 Capture from Sensor"):
            img = self.camera.get_image()
            if img:
                st.image(img, caption="External Camera Image", use_container_width=True)
                return img
        return None

    def _upload_image(self):
        uploaded = st.file_uploader(
            "Upload plant image",
            type=["jpg", "jpeg", "png"]
        )
        if uploaded:
            img = Image.open(uploaded).convert("RGB")
            st.image(img, caption="Uploaded Image", use_container_width=True)
            return img
        return None


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
    def __init__(self):
        st.set_page_config("Balcony Green", layout="centered")
        st.title("🌱 Balcony Green – Smart Plant Monitor")

        # Sidebar for Location
        with st.sidebar:
            st.header("📍 Location Settings")
            st.info("Coordinates for Weather Data")
            lat = st.number_input("Latitude", value=52.52, format="%.4f")
            lon = st.number_input("Longitude", value=13.41, format="%.4f")

        CAMERA_SNAPSHOT_URL = "http://192.168.1.100/capture"

        self.camera = ExternalCameraSensor(CAMERA_SNAPSHOT_URL)
        self.image_input = ImageInput(self.camera)
        self.weather_reader = WeatherReader(lat, lon)
        self.hardware_reader = HardwareSensorReader()
        self.stream_controller = StreamController()

        self.classifier_all = self.load_classifier_all()
        self.classifier_binary = self.load_classifier_binary()

    @st.cache_resource
    def load_classifier_all(_self):

    
        return EfficientNetClassifier(
            model_path= CKPT_PATH_TOMATO_11,
            num_classes= 11
            
        )
    
    @st.cache_resource
    def load_classifier_binary(_self):

    
        return EfficientNetClassifier(
            model_path= CKPT_PATH_TOMATO_2,
            num_classes= 2
            
        )

    def predict_image(self, image: Image.Image):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            image.save(tmp.name)
            return self.classifier_all.predict(
                tmp.name,
                top_k=3,
                confidence_threshold=0.0
            ), self.classifier_binary.predict(tmp.name)

    def run(self):
        image = self.image_input.render()

        if image:
            st.subheader("🧠 Health Prediction")
            health_status = False
            results_1 , results_2  = self.predict_image(image)
            for r in results_2:
                if r['confidence']*100 > 80:
                    health_status = True
                    st.success(f"{r['class_name']}")
            if health_status and st.button("Possible Disease Type"):
                for r in results_1:
                    st.success(f"{r['class_name']} — {r['confidence']*100:.6f}%")
            

        st.divider()
        st.subheader("� Live Monitoring")
        
        self.stream_controller.controls()
        
        # Create placeholders for two columns
        weather_col, sensor_col = st.columns(2)
        
        with weather_col:
            st.markdown("### ☁️ Ambient Weather")
            st.caption(f"Source: Open-Meteo (Lat: {self.weather_reader.service.lat}, Lon: {self.weather_reader.service.lon})")
            weather_placeholder = st.empty()
            
        with sensor_col:
            st.markdown("### 🪴 Plant Sensors")
            st.caption("Heatlh Status (Hardware Simulation)")
            sensor_placeholder = st.empty()

        while self.stream_controller.is_streaming():
            # Update Weather
            weather_data = self.weather_reader.read()
            if weather_data:
                with weather_placeholder.container():
                    col1, col2 = st.columns(2)
                    col1.metric("Temp", f"{weather_data['temperature (°C)']} °C")
                    col2.metric("Humidity", f"{weather_data['humidity (%)']} %")
                    col3, col4 = st.columns(2)
                    col3.metric("Rain", f"{weather_data['rain (mm)']} mm")
                    # Display soil moisture from API as "Ground Moisture" to distinguish from pot
                    col4.metric("Ground M.", f"{weather_data['soil_moisture']:.2f}")

            # Update Hardware Sensors (simulated)
            sensor_data = self.hardware_reader.read()
            with sensor_placeholder.container():
                 s_col1, s_col2 = st.columns(2)
                 s_col1.metric("Pot Moisture", f"{sensor_data['pot_moisture']} %")
                 s_col2.metric("Light", f"{sensor_data['light_lux']} lux")
                 st.progress(sensor_data['battery_level'] / 100, text=f"Battery: {sensor_data['battery_level']}%")

            time.sleep(1)


# =========================
# ENTRY POINT
# =========================
if __name__ == "__main__":
    BalconyGreenApp().run()
