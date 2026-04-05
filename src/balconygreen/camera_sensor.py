import logging
from io import BytesIO
import requests # type: ignore
import streamlit as st # type: ignore
from PIL import Image # type: ignore
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

    def render(self, payload, headers, plant) -> Image.Image | None:
        st.subheader("📸 Plant Image Input")

        source = st.radio("Select image source:", ["Upload from Phone / PC"], index=None)

        if source:
            # ✅ Register device (should ideally be once, but keeping your structure)
            response = DeviceRegister(device_payload=payload, headers=headers).register()

            device_key = response.json().get("device_key", "")

            sensor_headers = {
                "Authorization": f"Bearer {device_key}"
            }

            # ✅ Create / sync camera sensor
            sensor = requests.post(
                f"{FASTAPI_URL}/device/sync_sensors",
                json={"sensors": ["camera_upload"]},
                headers=sensor_headers,
                timeout=5
            )

            return self._upload_image(sensor, device_key, plant)

        return None

    # =========================
    # UPLOAD IMAGE
    # =========================
    def _upload_image(self, sensor, device_key, plant) -> Image.Image | None:
        uploaded = st.file_uploader("Upload plant image", type=["jpg", "jpeg", "png"])

        if uploaded:
            logger.info(f"Image uploaded: {uploaded.name}")

            img = Image.open(uploaded).convert("RGB")
            st.image(img, caption="Uploaded Image", width=300)

            # ✅ Extract correct sensor_id
            sensor_id = sensor.json().get("sensor_id", "")

            if not sensor_id:
                st.error("Sensor creation failed")
                return None

           

            self._send_to_api(img, sensor_id, device_key, plant)

            return img

        return None

    # =========================
    # SEND TO BACKEND
    # =========================
    def _send_to_api(self, image: Image.Image, sensor_id: str, device_key: str, plant: str):
        """Send image to FastAPI backend"""
        try:
            # Convert image → bytes
            buffer = BytesIO()
            image.save(buffer, format="JPEG")
            buffer.seek(0)

            files = {
                "file": ("image.jpg", buffer, "image/jpeg")
            }

            data = {
                "plant": plant,
                "mode": "binary"
            }

            headers = {
                "Authorization": f"Bearer {device_key}"
            }

            url = f"{FASTAPI_URL}/camera/upload/{sensor_id}"

            response = requests.post(
                url,
                files=files,   # ✅ REQUIRED
                data=data,     # ✅ REQUIRED
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Upload + prediction success: {result}")

                if "prediction" in result:
                    st.success(f"🌿 {result['prediction']} ({result['confidence']}%)")
                else:
                    st.write(result)

            else:
                logger.error(f"Upload failed: {response.text}")
                st.error(response.text)


            buffer = BytesIO()
            image.save(buffer, format="JPEG")
            buffer.seek(0)

            files = {
                "file": ("image.jpg", buffer, "image/jpeg")
            }

            data = {
                "plant": plant,
                "mode": "not binary"
            }

            headers = {
                "Authorization": f"Bearer {device_key}"
            }

            url = f"{FASTAPI_URL}/camera/upload/{sensor_id}"

            response = requests.post(
                url,
                files=files,   # ✅ REQUIRED
                data=data,     # ✅ REQUIRED
                headers=headers,
                timeout=10
            )

            if response.status_code == 200:
                result = response.json()
                logger.info(f"Upload + prediction success: {result}")

                if "predictions" in result:
                    for disease in result['predictions']:
                        st.success(f"🌿 {disease['disease']} ({disease['confidence']}%)")
                else:
                    st.write(result)

            else:
                logger.error(f"Upload failed: {response.text}")
                st.error(response.text)

        except Exception as e:
            logger.error(f"Failed to send image: {e}")
            st.error("Failed to send image to backend")