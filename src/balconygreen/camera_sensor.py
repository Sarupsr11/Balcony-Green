import logging
import tempfile

import requests  # type: ignore
import streamlit as st  # type: ignore
from PIL import Image  # type: ignore

FASTAPI_URL = "http://127.0.0.1:8000"

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


# # =========================
# # EXTERNAL CAMERA SENSOR
# # =========================
# class ExternalCameraSensor:
#     def __init__(self, snapshot_url: str):
#         self.snapshot_url = snapshot_url
#         logger.info(f"ExternalCameraSensor initialized with URL: {snapshot_url}")

#     def get_image(self) -> Image.Image | None:
#         try:
#             logger.debug(f"Attempting to capture image from {self.snapshot_url}")
#             response = requests.get(self.snapshot_url, timeout=3)
#             response.raise_for_status()
#             logger.info("Image captured successfully from external camera")
#             return Image.open(BytesIO(response.content)).convert("RGB")
#         except Exception as e:
#             logger.error(f"Camera error: {e}")
#             st.warning(f"Camera error: {e}")
#             return None


# =========================
# IMAGE INPUT HANDLER
# =========================
class ImageInput:
    def __init__(self, user_id: str | None):
        self.user_id = user_id
        logger.info(f"ImageInput initialized for user: {user_id}")

    def render(self) -> Image.Image | None:
        st.subheader("📸 Plant Image Input")
        source = st.radio("Select image source:", ["Upload from Phone / PC"], index=None)
        logger.debug(f"Image source selected: {source}")

        return self._upload_image()

    def _upload_image(self) -> Image.Image | None:
        uploaded = st.file_uploader("Upload plant image", type=["jpg", "jpeg", "png"])
        if uploaded:
            logger.info(f"Image uploaded: {uploaded.name}")
            img = Image.open(uploaded).convert("RGB")
            st.image(img, caption="Uploaded Image", width=300)
            self._send_to_api(img, "User Upload")
            return img
        return None

    def _send_to_api(self, image: Image.Image, source: str):
        """Save image to temp file and send metadata to FastAPI"""
        try:
            with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
                image.save(tmp.name)
                logger.debug(f"Image saved to temp file: {tmp.name}")
                payload = {"user_id": self.user_id, "sensor_name": "camera", "value": tmp.name, "extra_info": {"source": source}}
                logger.debug(f"Sending image metadata to API from source: {source}")
                requests.post(f"{FASTAPI_URL}/reading", json=payload, timeout=3)
                logger.info(f"Image metadata sent successfully from {source}")
        except Exception as e:
            logger.error(f"Failed to send image metadata to FastAPI: {e}")
            st.warning("Failed to send image metadata to FastAPI")
