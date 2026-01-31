import datetime
import logging
import random
import tempfile
from pathlib import Path

import requests  # type: ignore
import streamlit as st  # type: ignore
from PIL import Image  # type: ignore

from balconygreen.backend.register_device import DeviceRegister, remove_device
from balconygreen.camera_sensor import ImageInput
from balconygreen.inference import EfficientNetClassifier  # type: ignore
from balconygreen.sensor_reading import SensorReader

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)
DEVICE_FILE = Path("device_data/device_info.json")
WEATHER_FILE = Path("device_data/weather_info.json")
PROJECT_ROOT = Path(__file__).resolve().parents[3]

CKPT_PATH_TOMATO_11 = PROJECT_ROOT / "disease-detection" / "Tomatoes" / "Models" / "efficientnet_best_multiple_sources.pth"
CKPT_PATH_TOMATO_2 = PROJECT_ROOT / "disease-detection" / "Tomatoes" / "Models" / "efficientnet_binary_best_multiple_sources.pth"

FASTAPI_URL = "http://127.0.0.1:8000"
api_key = "https://api.open-meteo.com/v1/forecast"


# =========================
# MAIN APP
# =========================
class BalconyGreenApp:
    def __init__(self, access_token: str | None):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
        self.simulated = False
        self.city = None

        logger.info(f"BalconyGreenApp initialized - authenticated: {access_token is not None}")

        if not access_token:
            st.info("You are using Balcony Green as a guest. Sensor data will not be saved.")
            logger.info("Guest mode enabled")

        st.set_page_config("Balcony Green", layout="centered")
        st.title("🌱 Balcony Green – Smart Plant Monitor")

        # Initialize session state
        if "page_func" not in st.session_state:
            st.session_state["page_func"] = "Home"
        if "predicted_plant" not in st.session_state:
            st.session_state["predicted_plant"] = None

        # CAMERA_SNAPSHOT_URL = "http://192.168.1.100/capture"
        
        self.image_input = ImageInput(self.access_token)

        self.sensor_reader: SensorReader | None = None

        self.classifier_all = self.load_classifier_all()
        self.classifier_binary = self.load_classifier_binary()
        self.api_key = api_key

    @st.cache_resource
    def load_classifier_all(_self):
        return EfficientNetClassifier(model_path=CKPT_PATH_TOMATO_11, num_classes=11)

    @st.cache_resource
    def load_classifier_binary(_self):
        return EfficientNetClassifier(model_path=CKPT_PATH_TOMATO_2, num_classes=2)

    def predict_tomato_image(self, image: Image.Image):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            image.save(tmp.name)
            return self.classifier_all.predict(tmp.name, top_k=3, confidence_threshold=0.0), self.classifier_binary.predict(tmp.name)

    def predict_plant(self, image: Image.Image):
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            image.save(tmp.name)
            return random.choice(["Tomato", "Potato", "Mint"])

    def test_device_connection(self, device_ip: str | None) -> bool:
        """Test if a device is reachable via ping or HTTP request"""
        if not device_ip:
            logger.debug("No device IP provided for connection test")
            return False

        logger.debug(f"Testing device connection to: {device_ip}")
        try:
            # Try HTTP request first (for web-enabled devices)
            response = requests.get(f"http://{device_ip}", timeout=5)
            logger.info(f"Device connection test successful: {device_ip}")
            return response.status_code < 400
        except Exception as e:
            logger.warning(f"Device connection test failed for {device_ip}: {e}")
            return False
        except requests.RequestException:
            try:
                # Fallback to ping
                import subprocess

                result = subprocess.run(["ping", "-n", "1", "-w", "2000", device_ip], capture_output=True, text=True)
                return result.returncode == 0
            except requests.RequestException:
                return False

    def test_weather_api(self, city: str) -> bool:
        """Test if weather API is working for a given city"""
        try:
            # Test geocoding API
            params = {"name": city, "count": 1, "language": "en", "format": "json"}
            response = requests.get("https://geocoding-api.open-meteo.com/v1/search", params=params, timeout=5)
            return response.status_code == 200 and "results" in response.json()
        except requests.RequestException:
            return False

    def display_sensor_readings(self):
        """Display beautiful sensor readings automatically"""
        # Add custom CSS for beautiful styling
        st.markdown(
            """
        <style>
        .sensor-card {
            background: linear-gradient(135deg, rgba(255,255,255,0.1), rgba(255,255,255,0.05));
            border: 1px solid rgba(255,255,255,0.2);
            border-radius: 20px;
            padding: 25px;
            text-align: center;
            box-shadow: 0 8px 32px rgba(0,0,0,0.1);
            backdrop-filter: blur(10px);
            margin: 15px 0;
            transition: transform 0.3s ease, box-shadow 0.3s ease;
        }
        .sensor-card:hover {
            transform: translateY(-5px);
            box-shadow: 0 12px 40px rgba(0,0,0,0.2);
        }
        .sensor-icon {
            font-size: 3em;
            margin-bottom: 15px;
            filter: drop-shadow(0 2px 4px rgba(0,0,0,0.2));
        }
        .sensor-name {
            font-size: 1em;
            color: #888;
            margin-bottom: 10px;
            font-weight: 500;
        }
        .sensor-value {
            font-size: 2.2em;
            font-weight: 700;
            margin: 0;
            text-shadow: 0 2px 4px rgba(0,0,0,0.1);
        }
        .status-indicator {
            display: inline-block;
            width: 12px;
            height: 12px;
            border-radius: 50%;
            margin-right: 8px;
        }
        .status-online {
            background: #4CAF50;
            box-shadow: 0 0 10px rgba(76, 175, 80, 0.5);
        }
        .status-offline {
            background: #f44336;
            box-shadow: 0 0 10px rgba(244, 67, 54, 0.5);
        }
        </style>
        """,
            unsafe_allow_html=True,
        )
        # Create placeholders for real-time updates
        if "sensor_placeholders" not in st.session_state:
            st.session_state.sensor_placeholders = {}

        # Get devices for sensor reader
        is_guest = not self.access_token
        sensor_devices = []
        sensor_weather_config = None

        if is_guest:
            sensor_devices = st.session_state.get("guest_devices", [])
            sensor_weather_config = st.session_state.get("guest_weather_config")
        else:
            try:
                devices_response = requests.get(f"{FASTAPI_URL}/devices", headers=self.headers, timeout=3)
                sensor_devices = devices_response.json() if devices_response.status_code == 200 else []
            except requests.RequestException:
                sensor_devices = []

        # Separate physical devices and weather API devices
        # physical_devices = [d for d in sensor_devices if d.get('type') != 'weather_api']
        weather_devices = [d for d in sensor_devices if d.get("type") == "weather_api"]
        if sensor_weather_config:
            weather_devices.append(sensor_weather_config)

        # Initialize filter preferences in session state
        if "show_physical_sensors" not in st.session_state:
            st.session_state["show_physical_sensors"] = True
        if "show_weather_sensors" not in st.session_state:
            st.session_state["show_weather_sensors"] = True

        # Add sensor type filter controls
        filter_col1, filter_col2 = st.columns(2)
        with filter_col1:
            st.session_state["show_physical_sensors"] = st.checkbox(
                "📡 Physical Sensors", value=st.session_state["show_physical_sensors"], key="physical_filter"
            )
        with filter_col2:
            st.session_state["show_weather_sensors"] = st.checkbox(
                "🌤️ Weather API", value=st.session_state["show_weather_sensors"], key="weather_filter"
            )

        st.divider()

        # Create sensor reader
        # Add two functions later on that display real time sensor readings
        self.sensor_reader = SensorReader(
            use_simulated=self.simulated,
            city=self.city,
            api_key=self.api_key,
        )

        # Auto-refresh every 5 seconds
        if "last_refresh" not in st.session_state:
            st.session_state.last_refresh = datetime.datetime.now()

        # Check if 5 seconds have passed
        now = datetime.datetime.now()
        if (now - st.session_state.last_refresh).total_seconds() >= 5:
            st.session_state.last_refresh = now
            st.rerun()

        if st.button("🔄 Refresh Now", key="refresh_sensors"):
            st.session_state.last_refresh = datetime.datetime.now()
            st.rerun()

        # For logged-in users, fetch stored readings from database
        db_readings_physical = {}
        db_readings_weather = {}
        if self.access_token:
            try:
                db_response = requests.get(f"{FASTAPI_URL}/readings", headers=self.headers, timeout=3)
                if db_response.status_code == 200:
                    db_readings_list = db_response.json()
                    # Get latest reading for each sensor
                    for reading in db_readings_list:
                        sensor_name = reading["sensor_name"]
                        sensor_source = reading["source"]
                        if sensor_name not in db_readings_weather and sensor_source == "weather api":
                            db_readings_weather[sensor_name] = reading["value"]
                        elif sensor_name not in db_readings_physical:
                            db_readings_physical[sensor_name] = reading["value"]
            except Exception as e:
                print(f"Failed to fetch database readings: {e}")

        # Use database readings if available, otherwise use real-time readings
        # current only retrieving data from the database, add functions to retrieve real time sensor value
        readings_to_display_physical = db_readings_physical if db_readings_physical else None
        readings_to_display_weather = db_readings_weather if db_readings_weather else None

        # Define sensor display info
        sensor_info_physical = {
            "temperature": {"icon": "🌡️", "unit": "°C", "name": "Temperature", "color": "#FF6B6B"},
            "humidity": {"icon": "💧", "unit": "%", "name": "Humidity", "color": "#4ECDC4"},
            "soil_moisture": {"icon": "🌱", "unit": "%", "name": "Soil Moisture", "color": "#45B7D1"},
            "soil_ph": {"icon": "🧪", "unit": "", "name": "Soil pH", "color": "#96CEB4"},
            "light": {"icon": "☀️", "unit": "%", "name": "Light Level", "color": "#FFEAA7"},
            "camera": {"icon": "📷", "unit": "", "name": "Camera", "color": "#DDA0DD"},
        }

        # Display each sensor reading

        if readings_to_display_physical:
            # Display readings in a beautiful layout
            st.subheader("Physical Sensor Readings")
            col1, col2, col3, col4, col5 = st.columns(5)
            columns = [col1, col2, col3, col4, col5]
            sensor_index = 0
            for sensor_name, value in readings_to_display_physical.items():
                if sensor_name in sensor_info_physical and sensor_index < len(columns):
                    info = sensor_info_physical[sensor_name]
                    with columns[sensor_index]:
                        # Beautiful sensor card
                        st.markdown(
                            f"""
                        <div class="sensor-card" style="border-left: 5px solid {info["color"]};">
                            <div class="sensor-icon">{info["icon"]}</div>
                            <div class="sensor-name">{info["name"]}</div>
                            <div class="sensor-value" style="color: {info["color"]};">
                                {value:.1f}<span style="font-size: 0.6em; font-weight: 400;">{info["unit"]}</span>
                            </div>
                        </div>
                        """,
                            unsafe_allow_html=True,
                        )
                    sensor_index += 1

        if readings_to_display_weather:
            st.subheader("Weather Sensor Readings")
            col1, col2 = st.columns(2)
            columns = [col1, col2]
            sensor_info_weather_api = {
                "temperature": {"icon": "🌡️", "unit": "°C", "name": "Temperature", "color": "#FF6B6B"},
                "humidity": {"icon": "💧", "unit": "%", "name": "Humidity", "color": "#4ECDC4"},
            }

            sensor_index = 0

            for sensor_name, value in readings_to_display_weather.items():
                if sensor_name in sensor_info_weather_api and sensor_index < len(columns):
                    info = sensor_info_weather_api[sensor_name]
                    with columns[sensor_index]:
                        # Beautiful sensor card
                        st.markdown(
                            f"""
                        <div class="sensor-card" style="border-left: 5px solid {info["color"]};">
                            <div class="sensor-icon">{info["icon"]}</div>
                            <div class="sensor-name">{info["name"]}</div>
                            <div class="sensor-value" style="color: {info["color"]};">
                                {value:.1f}<span style="font-size: 0.6em; font-weight: 400;">{info["unit"]}</span>
                            </div>
                        </div>
                        """,
                            unsafe_allow_html=True,
                        )
                    sensor_index += 1
            # Display last updated time
            current_time = datetime.datetime.now().strftime("%H:%M:%S")
            st.caption(f"📅 Last updated: {current_time} | Auto-refreshes every 5 seconds")
            st.markdown("---")

        # # Display device status based on filter selections
        # devices_to_display = []
        # if st.session_state["show_physical_sensors"]:
        #     devices_to_display.extend(physical_devices)
        # if st.session_state["show_weather_sensors"]:
        #     devices_to_display.extend(weather_devices)

        # if devices_to_display:
        #     st.subheader("📊 Connected Devices")
        #     status_cols = st.columns(len(devices_to_display))
        #     for i, device in enumerate(devices_to_display):
        #         with status_cols[i]:
        #             device_type_icon = "🌤️" if device.get('type') == 'weather_api' else "📡"
        #             status_class = "status-online" if device['active'] else "status-offline"
        #             location = f" ({device['city']})" if device.get('type') == 'weather_api' and device.get('city') else ""

        #             st.markdown(f"""
        #             <div style="text-align: center; padding: 15px; background: rgba(255,255,255,0.05);
        #              border-radius: 15px; border: 1px solid rgba(255,255,255,0.1);">
        #                 <div style="font-size: 1.5em; margin-bottom: 8px;">{device_type_icon}</div>
        #                 <div style="font-size: 0.9em; font-weight: 500; margin-bottom: 8px;">{device['name']}{location}</div>
        #                 <div style="display: flex; align-items: center; justify-content: center;">
        #                     <span class="status-indicator {status_class}"></span>
        #                     <span style="font-size: 0.8em; color: #ccc;">{'Online' if device['active'] else 'Offline'}</span>
        #                 </div>
        #             </div>
        #             """, unsafe_allow_html=True)
        # else:
        #     st.info("📡 No sensors selected. Enable Physical Sensors or Weather API above to view device status.")

    def run(self):
        st.subheader("Home Page")

        # -----------------------
        # DEVICE MANAGEMENT
        # -----------------------
        is_guest = not self.access_token

        if is_guest:
            st.info("🌟 **Guest Mode**: You can connect sensors and use weather API, but data won't be saved to your account.")

        # Initialize guest devices in session state
        if "guest_devices" not in st.session_state:
            st.session_state.guest_devices = []
        if "guest_weather_config" not in st.session_state:
            st.session_state.guest_weather_config = None
        st.subheader("🔌 Device Management")

        # Device registration section
        with st.expander("➕ Add New Device"):
            device_name = st.text_input("Device Name", placeholder="e.g., Balcony Sensor Hub or dummy for simulated readings", key="device_name")
            device_ip = st.text_input("Device IP/Endpoint (optional)", placeholder="192.168.1.100 or dummy for simulated readings", key="device_ip")

            # Available sensors for this device
            available_sensors = ["temperature", "humidity", "soil_moisture", "soil_ph", "light", "camera"]
            selected_sensors = st.multiselect("Sensors on this device", available_sensors, key="selected_sensors")

            if st.button("Register Device", disabled=not device_name or not selected_sensors, key="register_device"):
                if is_guest:
                    # For guest users, store in session state
                    guest_device = {
                        "id": f"guest_{len(st.session_state.guest_devices)}",
                        "device_name": device_name,
                        "ip": device_ip if device_ip else None,
                        "is_active": True,
                        "device_type": "physical",
                        "device_city": self.city,
                        "sensor_types": selected_sensors,
                    }
                    st.session_state.guest_devices.append(guest_device)
                    st.success(f"✅ Device '{device_name}' connected! Sensor readings will appear below.")
                    st.rerun()
                else:
                    # For logged-in users, register on server
                    device_payload = {
                        "device_name": device_name,
                        "device_ip": device_ip if device_ip else None,
                        "device_type": "physical",
                        "device_city": self.city,
                        "sensor_types": selected_sensors,
                    }

                    try:
                        response = DeviceRegister(device_payload=device_payload, headers=self.headers).register()
                        if response.status_code == 200:
                            st.success(f"✅ Device '{device_name}' registered! Sensor readings will appear below.")
                            st.rerun()  # Refresh to show new device
                        else:
                            st.error(f"Failed to register device: {response.text}")
                    except Exception as e:
                        st.error(f"Failed to register device: {e}")

        # Weather API as virtual device
        with st.expander("🌤️ Add Weather API Sensors"):
            self.city = st.text_input("City", "London", key="weather_city")
            weather_sensors = st.multiselect("Weather Parameters", ["temperature", "humidity"], key="weather_sensors")

            if st.button("Register Weather API", disabled=not weather_sensors, key="register_weather"):
                if is_guest:
                    # For guest users, store weather config in session state
                    st.session_state.guest_weather_config = {
                        "id": "guest_weather",
                        "name": f"Weather API - {self.city}",
                        "city": self.city,
                        "active": True,
                        "type": "weather_api",
                        "sensors": weather_sensors,
                    }
                    st.success(f"✅ Weather API configured for {self.city}! Weather data will appear below.")
                    st.rerun()
                else:
                    # For logged-in users, register on server
                    device_payload = {
                        "device_name": f"Weather API - {self.city}",
                        "device_ip": None,  # No IP for weather API
                        "sensor_types": weather_sensors,
                        "device_type": "weather_api",
                        "city": self.city,
                    }

                    try:
                        response = DeviceRegister(device_payload=device_payload, headers=self.headers).register()
                        type(response)

                        if response.status_code == 200:
                            st.success(f"✅ Weather API registered for {self.city}! Weather data will appear below.")
                            st.rerun()
                        else:
                            st.error(f"Failed to register weather sensors: {response.text}")
                    except Exception as e:
                        st.error(f"Failed to register weather sensors: {e}")

        # Display registered devices
        st.subheader("📱 Your Devices")

        # Combine devices from server and session state
        all_devices = []

        if is_guest:
            # For guest users, use session state devices
            all_devices = st.session_state.guest_devices.copy()
            if st.session_state.guest_weather_config:
                all_devices.append(st.session_state.guest_weather_config)
        else:
            # For logged-in users, get from server
            try:
                devices_response = requests.get(f"{FASTAPI_URL}/devices", headers=self.headers)
                if devices_response.status_code == 200:
                    all_devices = devices_response.json()
            except Exception as e:
                st.error(f"Failed to load devices: {e}")
                all_devices = []

        for device in all_devices:
            if device["name"] == "dummy" and device["active"]:
                self.simulated = True
        if not all_devices:
            st.info("No devices connected yet. Add a device or weather API above to start monitoring!")
        else:
            for device in all_devices:
                device_type_icon = "🌤️" if device.get("type") == "weather_api" else "📡"
                location_info = (
                    f" ({device['city']})"
                    if device.get("type") == "weather_api" and device.get("city")
                    else f" ({device['ip']})"
                    if device["ip"]
                    else ""
                )
                with st.expander(f"{device_type_icon} {device['name']}{location_info}"):
                    status_icon = "🟢" if device["active"] else "🔴"
                    device_type_display = "Weather API" if device.get("type") == "weather_api" else "Physical Device"
                    st.write(f"**Status:** {status_icon} {'Connected' if device['active'] else 'Disconnected'}")
                    st.write(f"**Type:** {device_type_display}")
                    st.write(f"**Sensors:** {', '.join(device['sensors'])}")

                    col1, col2 = st.columns(2)
                    with col1:
                        if device.get("type") == "physical" and device.get("ip"):
                            if st.button("Test Connection", key=f"test_{device['id']}"):
                                # Test device connectivity
                                test_result = self.test_device_connection(device.get("ip"))
                                if test_result:
                                    st.success("Device is reachable!")
                                else:
                                    st.error("Device is not reachable. Check network connection.")
                        elif device.get("type") == "weather_api" and st.button("Test API", key=f"test_{device['id']}"):
                            # Test weather API connectivity
                            try:
                                test_result = self.test_weather_api(device.get("city", "London"))
                                if test_result:
                                    st.success("Weather API is working!")
                                else:
                                    st.error("Weather API is not responding.")
                            except Exception as e:
                                st.error(f"Weather API test failed: {e}")

                    with col2:
                        if st.button("Remove Device", key=f"remove_{device['id']}"):
                            if is_guest:
                                # For guest users, remove from session state
                                if device.get("type") == "weather_api":
                                    st.session_state.guest_weather_config = None
                                else:
                                    st.session_state.guest_devices = [d for d in st.session_state.guest_devices if d["id"] != device["id"]]
                                st.success(f"Device '{device['name']}' removed!")
                                st.rerun()
                            else:
                                # For logged-in users, remove from server
                                try:
                                    delete_response = requests.delete(f"{FASTAPI_URL}/devices/{device['id']}", headers=self.headers)
                                    remove_device(device["id"])
                                    if delete_response.status_code == 200:
                                        st.success(f"Device '{device['name']}' removed successfully!")
                                        st.rerun()
                                    else:
                                        st.error(f"Failed to remove device: {delete_response.text}")
                                except Exception as e:
                                    st.error(f"Failed to remove device: {e}")

        # -----------------------
        # LIVE SENSOR READINGS
        # -----------------------
        # Check if user has registered devices or weather API
        has_devices = False
        has_weather_api = False

        if is_guest:
            # For guest users, check session state
            has_devices = len(st.session_state.guest_devices) > 0
            has_weather_api = st.session_state.guest_weather_config is not None
        else:
            # For logged-in users, check server
            try:
                devices_response = requests.get(f"{FASTAPI_URL}/devices", headers=self.headers, timeout=3)
                if devices_response.status_code == 200:
                    devices = devices_response.json()
                    has_devices = len(devices) > 0
                    # Check if any device is weather API
                    has_weather_api = any(device.get("type") == "weather_api" for device in devices)
            except requests.RequestException:
                pass

        if has_devices or has_weather_api:
            st.subheader("🌡️ Live Sensor Readings")
            self.display_sensor_readings()
        else:
            st.info("📡 No devices or weather API configured yet. Add a device or configure weather API above to start monitoring!")

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
                            st.success(f"{r['class_name']} — {r['confidence'] * 100:.6f}%")

            st.divider()
            st.subheader("📊 Live Sensor Data")

            # Display beautiful sensor readings
            self.display_sensor_readings()

            if st.button("⬅ Back to Home"):
                st.session_state["page_func"] = "Home"
                st.session_state["predicted_plant"] = None


# =========================
# ENTRY POINT
# =========================
def main_page(access: str):
    BalconyGreenApp(access_token=access).run()
