import datetime
import logging
from pathlib import Path
import requests # type: ignore
import streamlit as st # type: ignore
from PIL import Image # type: ignore
import pandas as pd # type: ignore
import json
from io import BytesIO

from balconygreen.backend.register_device import DeviceRegister, remove_device
from balconygreen.camera_sensor import ImageInput
from balconygreen.sensor_reading import SensorReader

import os
import time
logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

FASTAPI_URL = os.getenv("FASTAPI_URL", "https://balconygreen-production.up.railway.app")

import streamlit.components.v1 as components # type: ignore


def esp32_flasher(manifest_url):
    html_code = f"""
    <!DOCTYPE html>
    <html>
    <head>
        <script type="module"
        src="https://unpkg.com/esp-web-tools@8/dist/web/install-button.js?module">
        </script>
    </head>

    <body>
    <h3>Flash your ESP32</h3>
    <esp-web-install-button
        manifest="{manifest_url}">
    </esp-web-install-button>
    <p>Click connect and choose your ESP32 serial port.</p>
    </body>
    </html>
    """
    components.html(html_code, height=300)


class BalconyGreenApp:


    def __init__(self, access_token: str | None):
        self.access_token = access_token
        self.headers = {"Authorization": f"Bearer {access_token}"} if access_token else None
        self.simulated = False
        self.city = None
        self.plant_list = ["Tomato"]

        st.set_page_config("Balcony Green", layout="centered")
        st.title("🌱 Balcony Green – Smart Plant Monitor")

        # Initialize session state
        if "page_func" not in st.session_state:
            st.session_state["page_func"] = "home"
        

        self.image_input = ImageInput(self.access_token)
        self.sensor_reader: SensorReader | None = None
        self.api_key = "https://api.open-meteo.com/v1/forecast"

    # ------------------------
    # Sensor Readings
    # ------------------------
    def display_sensor_readings(self):
        st.session_state["page_func"] = "esp_device"
        st.subheader("🌡️ Live Sensor Readings")

        # st.info("Sensor readings display is under development.")
        

   

        try:
            response = requests.get(
                f"{FASTAPI_URL}/readings",
                headers={"Authorization": f"Bearer {self.access_token}"}
            )
            
            if response.status_code != 200:
                st.error("Failed to fetch sensor readings")
                return

            data = response.json()

            if not data:
                st.info("No sensor readings available yet.")
                return

            df = pd.DataFrame(data)
            df["timestamp"] = pd.to_datetime(df["timestamp"])
            df = df.sort_values(by="timestamp", ascending=False)

            # ------------------------
            # Helper: color + icon
            # ------------------------
            def sensor_style(sensor, value):
                sensor = sensor.lower()

                if "temperature" in sensor:
                    if value > 35:
                        return "🔥", "red"
                    elif value < 10:
                        return "❄️", "blue"
                    return "🌡️", "green"

                if "humidity" in sensor:
                    if value > 80:
                        return "💧", "blue"
                    elif value < 30:
                        return "🏜️", "orange"
                    return "💧", "green"

                if "soil" in sensor:
                    if value < 300:
                        return "🌱", "red"
                    return "🌿", "green"

                if "light" in sensor:
                    return "☀️", "yellow"

                return "📟", "gray"

            # ------------------------
            # Group by sensor
            # ------------------------
            sensors = df["sensor_name"].unique()

            cols = st.columns(2)  # grid layout

            for i, sensor in enumerate(sensors):
                sensor_df = df[df["sensor_name"] == sensor]
                latest = sensor_df.iloc[0]

                icon, color = sensor_style(sensor, latest["value"])

                with cols[i % 2]:
                    with st.container():
                        st.markdown(f"### {icon} {sensor.capitalize()}")

                        # Styled metric
                        st.metric(
                            label="Current",
                            value=f"{latest['value']}",
                            delta=None
                        )

                        st.caption(
                            f"Last updated: {latest['timestamp'].strftime('%Y-%m-%d %H:%M:%S')}"
                        )

                        # Alert messages
                        if color == "red":
                            st.error("⚠️ Critical value detected!")
                        elif color == "orange":
                            st.warning("⚠️ Warning level")
                        elif color == "blue":
                            st.info("ℹ️ High moisture / humidity")

                        # Mini chart
                        st.line_chart(
                            sensor_df.set_index("timestamp")["value"],
                            height=150
                        )

        except Exception as e:
            st.error(f"Error loading sensor readings: {e}")

    # ------------------------
    # Device Management
    # ------------------------
    def device_management_section(self):
        st.session_state["page_func"] = "esp_device"
        st.subheader("🔌 Device Management")
        is_guest = not self.access_token

        if is_guest:
            st.info("🌟 Guest Mode: Sensor data won't be saved.")

        # Session state
        if "guest_devices" not in st.session_state:
            st.session_state.guest_devices = []
        if "guest_weather_config" not in st.session_state:
            st.session_state.guest_weather_config = None

       

        with st.expander("➕ Add New Device (ESP32 Device)"):
            device_name = st.selectbox(
                "🌿 Select the plant connected to the device",
                self.plant_list,
                key="device_name"
            )
        

            if st.button("Register Device", disabled=not device_name):
                payload = {
                    "device_name": device_name,
                    "device_type": "physical",
                }

                if is_guest:
                    guest_device = {
                        "id": f"guest_{len(st.session_state.guest_devices)}",
                        "device_name": device_name,
                        "device_type": "physical"
                    }
                    st.session_state.guest_devices.append(guest_device)
                    st.success(f"✅ Device '{device_name}' added in Guest Mode.")
                    st.rerun()
                else:
                    try:
                        response = DeviceRegister(device_payload=payload, headers=self.headers).register()
                        if response.status_code == 200:
                            data = response.json()
                            st.success("✅ Device Registered Successfully!")
                            
                            # Display device credentials from backend
                            st.info(f"""
                            **Device Details:**
                            - Device Key: `{data['device_key']}`
                            """)

                            # Firmware flashing section
                            st.info("🔧 **Step 1: Flash Firmware to your ESP32**")
                            manifest_url  = data['firmware']['manifest_url']
                            esp32_flasher(manifest_url)
                            
                            st.markdown("---")

                            

                            st.success("📱 **Step 2: ESP32 Setup Instructions:**")
                            st.markdown("""
                            1. **Power on your ESP32** (after flashing) - It will create a WiFi hotspot
                            2. **Connect your phone/tablet** to the hotspot (password: setup1234)
                            3. **Open browser** and go to `http://192.168.4.1`
                            4. **Enter the device key, wifi name and password
                            6. **ESP32 will connect** to your WiFi and start sending sensor data!
                            """)

                        else:
                            st.error(f"Failed to register device: {response.text}")
                    except Exception as e:
                        st.error(f"Error registering device: {e}")
            
                # ------------------------
                # Weather API Device
                # ------------------------
                with st.expander("🌤️ Add Weather API Sensors"):
                    self.city = st.text_input("City", "London", key="weather_city")
                    weather_sensors = st.multiselect("Weather Sensors", ["temperature", "humidity"], key="weather_sensors")

                    if st.button("Register Weather API", disabled=not weather_sensors):
                        payload = {
                            "device_name": f"Weather API - {self.city}",
                            "sensor_types": weather_sensors,
                            "device_type": "weather_api",
                            "device_ip": None,
                            "city": self.city,
                        }
                        if is_guest:
                            st.session_state.guest_weather_config = {
                                "id": "guest_weather",
                                "name": f"Weather API - {self.city}",
                                "type": "weather_api",
                                "active": True,
                                "sensors": weather_sensors,
                                "city": self.city,
                            }
                            st.success(f"✅ Weather API configured for {self.city}.")
                            st.rerun()
                        else:
                            try:
                                response = DeviceRegister(device_payload=payload, headers=self.headers).register()
                                if response.status_code == 200:
                                    st.success(f"✅ Weather API registered for {self.city}.")
                                    st.rerun()
                                else:
                                    st.error(f"Failed to register weather API: {response.text}")
                            except Exception as e:
                                st.error(f"Error registering weather API: {e}")

        # ------------------------
        # Show Connected Devices
        # ------------------------
        st.subheader("📱 Connected Devices")
        all_devices = []
        if is_guest:
            all_devices = st.session_state.guest_devices.copy()
            if st.session_state.guest_weather_config:
                all_devices.append(st.session_state.guest_weather_config)
        else:
            try:
                resp = requests.get(f"{FASTAPI_URL}/devices", headers=self.headers, timeout=3)
                if resp.status_code == 200:
                    all_devices = resp.json()
            except Exception as e:
                st.error(f"Failed to load devices: {e}")

        if not all_devices:
            st.info("No devices connected. Add devices above.")
        else:
            for device in all_devices:
                if device.get("type") != "upload":
                    device_type_icon = "🌤️" if device.get("type") == "weather_api" else "📡"
                    location_info = f" ({device.get('city')})" if device.get("type") == "weather_api" else f" ({device.get('ip')})" if device.get("ip") else ""
                    with st.expander(f"{device_type_icon} {device.get('device_name', device.get('name'))}{location_info}"):
                        status_icon = "🟢" if device.get("active") else "🔴"
                        st.write(f"**Status:** {status_icon} {'Connected' if device.get('active') else 'Disconnected'}")
                        st.write(f"**Type:** {'Weather API' if device.get('type') == 'weather_api' else 'Physical Device'}")

                        col1, col2 = st.columns(2)
                        with col1:
                            if device.get("type") == "physical" and device.get("ip"):
                                if st.button("Test Connection", key=f"test_{device['id']}"):
                                    from subprocess import run, PIPE
                                    result = run(["ping", "-n" if os.name=="nt" else "-c", "1", device.get("ip")], stdout=PIPE)
                                    if result.returncode == 0:
                                        st.success("Device reachable!")
                                    else:
                                        st.error("Device unreachable.")
                            elif device.get("type") == "weather_api":
                                if st.button("Test API", key=f"test_{device['id']}"):
                                    try:
                                        r = requests.get(f"https://geocoding-api.open-meteo.com/v1/search?name={device.get('city')}", timeout=3)
                                        if r.status_code == 200 and "results" in r.json():
                                            st.success("Weather API working!")
                                        else:
                                            st.error("Weather API failed.")
                                    except Exception as e:
                                        st.error(f"Weather API test failed: {e}")

                        with col2:

                        # Remove device
                            if st.button("Remove Device", key=f"remove_{device['id']}"):
                                if is_guest:
                                    if device.get("type") == "weather_api":
                                        st.session_state.guest_weather_config = None
                                    else:
                                        st.session_state.guest_devices = [d for d in st.session_state.guest_devices if d["id"] != device["id"]]
                                    st.success(f"Device '{device.get('device_name', device.get('name'))}' removed!")
                                    st.rerun()
                                else:
                                    try:
                                        requests.delete(f"{FASTAPI_URL}/devices/{device['id']}", headers=self.headers, timeout=3)
                                        remove_device(device["id"])
                                        st.success(f"Device removed from backend!")
                                        st.rerun()
                                    except Exception as e:
                                        st.error(f"Failed to remove device: {e}")


    def sensor_health_status(self):
        

        st.set_page_config(page_title="🌿 Plant Health Monitor", layout="wide")

        st.title("🌿 Basil Plant Health Dashboard")

        try:
            response = requests.get(f"{FASTAPI_URL}/predict/latest", headers=self.headers, timeout=5)
            
            if response.status_code != 200:
                st.write("No readings for prediction ")
                
            # -----------------------------
            # Extract values
            # -----------------------------
            data = response.json()

            if "error" not in data:

                status = data["status"]
                trend = data["trend"]
                health = data["prediction"]["health_score"]   # already %
                risk = data["prediction"]["risk"]
                alert = data["alert"]["level"]

                # -----------------------------
                # Normalize risk for UI (0–100)
                # -----------------------------
                risk_ui = int((risk + 1) / 2 * 100)

                # -----------------------------
                # Trend icon
                # -----------------------------
                trend_icon = {
                    "improving": "📈",
                    "declining": "📉",
                    "stable": "➖"
                }.get(trend, "")

                # -----------------------------
                # Top Metrics
                # -----------------------------
                col1, col2, col3 = st.columns(3)

                col1.metric("🌱 Health Score", f"{health:.1f}%")
                col2.metric("📉 Risk Score", f"{risk_ui}%")
                col3.metric("📊 Trend", f"{trend_icon} {trend}")

                # -----------------------------
                # Status Indicator
                # -----------------------------
                if status == "critical":
                    st.error("🚨 Plant is in CRITICAL condition!")
                elif status == "warning":
                    st.warning("⚠️ Plant health declining")
                else:
                    st.success("✅ Plant is healthy")

                # -----------------------------
                # Alert Level
                # -----------------------------
                st.subheader("🚨 Alert Level")
                st.markdown(f"### **{alert.upper()}**")

                # -----------------------------
                # Health Gauge
                # -----------------------------
                st.subheader("🌿 Health Visualization")
                st.progress(int(health))

                # -----------------------------
                # Risk Gauge
                # -----------------------------
                st.subheader("⚠️ Risk Visualization")
                st.progress(risk_ui)

                # -----------------------------
                # Smart Insights (🔥 NEW)
                # -----------------------------
                st.subheader("🧠 Insights")

                if alert == "high_risk":
                    st.error("Immediate attention needed! Check soil moisture & environment.")
                elif alert == "moderate_risk":
                    st.warning("Plant may become unstable soon.")
                else:
                    st.success("Plant conditions are stable.")

                # Trend-based insight
                if trend == "declining":
                    st.warning("Health is trending downward. Consider intervention.")
                elif trend == "improving":
                    st.success("Plant is recovering well.")

                # -----------------------------
                # Auto Refresh (NON-BLOCKING)
                # -----------------------------
                st.caption("Auto-refresh every 15 seconds")
                time.sleep(15)
                st.rerun()

            else:
                st.error(data["error"])
            
        except Exception as e:
                st.error(f"Failed to predict: {e}")
    

    def live_sensor_dashboard(self):
        st.session_state["page_func"] = "esp_device"
        st.subheader("📡 Live Sensor Dashboard")

        if "run_live" not in st.session_state:
            st.session_state.run_live = False

        col1, col2 = st.columns(2)

        if col1.button("▶ Start Live"):
            st.session_state.run_live = True

        if col2.button("⏹ Stop"):
            st.session_state.run_live = False

        placeholder = st.empty()

        if st.session_state.run_live:
            while st.session_state.run_live:
                with placeholder.container():
                    self.display_sensor_readings()

                time.sleep(5)

        self.sensor_health_status()
                
    # ------------------------
    # Page Methods
    # ------------------------
    def show_home_page(self):
        st.subheader("🏠 Welcome to Balcony Green")

        options = st.selectbox(
            "What would you like to do?",
            ["", "Add ESP32 Device", "Upload Image from Phone / PC"],
            index=0
        )

        if options == "Add ESP32 Device":
            st.session_state["page_func"] = "esp_device"
            st.rerun()
        elif options == "Upload Image from Phone / PC":
            st.session_state["page_func"] = "upload_from_device"
            st.rerun()

    def show_esp_device_page(self):
        st.subheader("🔌 ESP32 Device Management")
        self.device_management_section()
        self.live_sensor_dashboard()

        if st.button("⬅ Back to Home", key="back_to_home_from_esp"):
            st.session_state["page_func"] = "home"
            st.rerun()

    def show_upload_page(self):
        st.subheader("📸 Plant Image Upload")

        device_name = st.selectbox(
            "🌿 Select the plant that is being uploaded",
            self.plant_list,
            key="plant_name"
        )

        payload = {
            "device_name": device_name,
            "device_type": "upload",
        }
        image = self.image_input.render(payload, self.headers, device_name)

        if image:
            st.session_state["uploaded_image"] = image

        if st.button("⬅ Back to Home", key="back_to_home_from_upload"):
            st.session_state["page_func"] = "home"
            st.rerun()

    # ------------------------
    # Run Main Page
    # ------------------------
    def run(self):
        # Page routing based on session state
        if st.session_state.get("page_func") == "home":
            self.show_home_page()
        elif st.session_state.get("page_func") == "esp_device":
            self.show_esp_device_page()
        elif st.session_state.get("page_func") == "upload_from_device":
            self.show_upload_page()
        else:
            # Default to home
            st.session_state["page_func"] = "home"
            self.show_home_page()
                    
        
       
            
                

        


# =========================
# Entry Point
# =========================
def main_page(access: str | None):
    BalconyGreenApp(access_token=access).run()