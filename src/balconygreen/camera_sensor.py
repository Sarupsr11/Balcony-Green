
import random
import tempfile
import time
from io import BytesIO
from pathlib import Path
from typing import Any, Dict, Optional

import requests  # type: ignore
import streamlit as st  # type: ignore
from PIL import Image  # type: ignore
FASTAPI_URL = "http://127.0.0.1:8000"


# =========================
# EXTERNAL CAMERA SENSOR
# =========================
class ExternalCameraSensor:
    def __init__(self, snapshot_url: str):
        self.snapshot_url = snapshot_url

    def get_image(self) -> Optional[Image.Image]:
        try:
            response = requests.get(self.snapshot_url, timeout=3)
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGB")
        except Exception as e:
            st.warning(f"Camera error: {e}")
            return None


# =========================
# IMAGE INPUT HANDLER
# =========================
class ImageInput:
    def __init__(self, camera: ExternalCameraSensor, user_id: str):
        self.camera = camera
        self.user_id = user_id

    def render(self) -> Optional[Image.Image]:
        st.subheader("📸 Plant Image Input")
        source = st.radio("Select image source:", ["External Camera Sensor", "Upload from Phone / PC"])

        if source == "External Camera Sensor":
            return self._external_camera()
        else:
            return self._upload_image()

    def _external_camera(self) -> Optional[Image.Image]:
        if st.button("📡 Capture from Sensor"):
            img = self.camera.get_image()
            if img:
                st.image(img, caption="External Camera Image", use_container_width=True)
                self._send_to_api(img, "External Camera Sensor")
                return img
        return None

    def _upload_image(self) -> Optional[Image.Image]:
        uploaded = st.file_uploader("Upload plant image", type=["jpg", "jpeg", "png"])
        if uploaded:
            img = Image.open(uploaded).convert("RGB")
            st.image(img, caption="Uploaded Image", width=300)
            self._send_to_api(img, "User Upload")
            return img
        return None

    def _send_to_api(self, image: Image.Image, source: str):
        """Save image to temp file and send metadata to FastAPI"""
        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            image.save(tmp.name)
            payload = {"user_id": self.user_id, "sensor_name": "camera", "value": tmp.name, "extra_info": {"source": source}}
            try:
                requests.post(f"{FASTAPI_URL}/reading", json=payload, timeout=3)
            except:
                st.warning("Failed to send image metadata to FastAPI")