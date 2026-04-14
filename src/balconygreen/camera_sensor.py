import logging
from io import BytesIO
import requests  # type: ignore
import streamlit as st  # type: ignore
from PIL import Image  # type: ignore
from balconygreen.backend.register_device import DeviceRegister
import os

FASTAPI_URL = os.getenv("FASTAPI_URL", "https://balconygreen-production.up.railway.app")

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# =========================
# IMAGE INPUT HANDLER
# =========================
class ImageInput:
    def __init__(self, user_id: str | None):
        self.user_id = user_id

        if "page_func" not in st.session_state:
            st.session_state["page_func"] = "home"
        if "upload_device_registered" not in st.session_state:
            st.session_state["upload_device_registered"] = False
        if "current_upload_plant" not in st.session_state:
            st.session_state["current_upload_plant"] = ""

    def render(self, payload, headers, plant) -> Image.Image | None:

        st.subheader("📸 Plant Image Input")

        if not plant:
            st.warning("Please select a plant first")
            return None

        source = st.selectbox(
            "Select image source:",
            ["", "Upload from Phone / PC"]
        )

        if source == "Upload from Phone / PC":

            # Reset if plant changed
            if st.session_state.get("current_upload_plant", "") != plant:
                self.reset_upload_session()
                st.session_state["current_upload_plant"] = plant

            # ✅ Register device once
            if not st.session_state.get("upload_device_registered", False):
                logger.info(f"Registering upload device for plant: {plant}")

                response = DeviceRegister(
                    device_payload=payload,
                    headers=headers
                ).register()

                if response.status_code != 200:
                    st.error("Device registration failed")
                    return None

                device_key = response.json().get("device_key")
                if not device_key:
                    st.error("No device key received")
                    return None

                st.session_state["upload_device_key"] = device_key
                st.session_state["upload_device_registered"] = True

                sensor_headers = {
                    "Authorization": f"Bearer {device_key}"
                }

                # ✅ Sync sensor safely
                sensor = requests.post(
                    f"{FASTAPI_URL}/device/sync_sensors",
                    json={"sensors": ["camera_upload"]},
                    headers=sensor_headers,
                    timeout=5
                )

                if sensor.status_code != 200:
                    st.error("Sensor sync failed")
                    return None

                sensor_json = sensor.json()
                sensor_id = sensor_json.get("camera_upload")

                if not sensor_id:
                    st.error("Sensor ID not returned")
                    return None

                logger.info(f"Camera sensor synced for device: {device_key}")

                st.session_state["upload_sensor_id"] = sensor_id

            device_key = st.session_state.get("upload_device_key", "")
            return self._upload_image(device_key, plant)

        return None

    # =========================
    # UPLOAD IMAGE
    # =========================
    def _upload_image(self, device_key, plant) -> Image.Image | None:
        uploaded = st.file_uploader("Upload plant image", type=["jpg", "jpeg", "png"])

        if uploaded:
            logger.info(f"Image uploaded: {uploaded.name}")

            img = Image.open(uploaded).convert("RGB")
            st.image(img, caption="Uploaded Image", width=300)

            sensor_id = st.session_state.get("upload_sensor_id", "")

            if not sensor_id or not device_key:
                st.error("Upload setup failed. Please try again.")
                return None

            # ✅ Mode selection (instead of duplicate API calls)
            mode = st.radio("Select prediction mode:", ["binary", "not binary"])

            # Optional button to prevent auto-trigger
            if st.button("Analyze"):
                self._send_to_api(img, sensor_id, device_key, plant, mode)

            return img

    def reset_upload_session(self):
        """Reset upload session state when starting a new upload"""
        st.session_state["upload_device_registered"] = False
        st.session_state.pop("upload_device_key", None)
        st.session_state.pop("upload_sensor_id", None)

    # =========================
    # SEND TO API
    # =========================
    def _send_to_api(self, image: Image.Image, sensor_id: str, device_key: str, plant: str, mode: str):
        """Send image to FastAPI backend"""
        try:
            # ✅ Convert image ONCE
            buffer = BytesIO()
            image.save(buffer, format="JPEG")
            buffer.seek(0)

            files = {
                "file": ("image.jpg", buffer, "image/jpeg")
            }

            data = {
                "plant": plant,
                "mode": mode
            }

            headers = {
                "Authorization": f"Bearer {device_key}"
            }

            url = f"{FASTAPI_URL}/camera/upload/{sensor_id}"

            with st.spinner("Analyzing image..."):
                response = requests.post(
                    url,
                    files=files,
                    data=data,
                    headers=headers,
                    timeout=10
                )

            if response.status_code != 200:
                logger.error(f"Upload failed: {response.text}")
                st.error(response.text)
                return

            result = response.json()
            logger.info(f"Upload + prediction success: {result}")

            # ✅ Clean output handling
            if mode == "binary":
                if "prediction" in result:
                    st.success(f"🌿 {result['prediction']} ({result['confidence']}%)")
                else:
                    st.write(result)
            else:
                if "predictions" in result:
                    for disease in result['predictions']:
                        st.success(f"🌿 {disease['disease']} ({disease['confidence']}%)")
                else:
                    st.write(result)

        except requests.exceptions.RequestException as e:
            logger.error(f"Network error: {e}")
            st.error("Network error while sending image")

        except Exception as e:
            logger.error(f"Failed to send image: {e}")
            st.error("Failed to send image to backend")