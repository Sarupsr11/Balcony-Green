from __future__ import annotations

import tempfile
from io import BytesIO
from typing import Optional

import requests  # type: ignore
import streamlit as st  # type: ignore
from PIL import Image  # type: ignore

try:
    from balconygreen.settings import API_BASE_URL
except ModuleNotFoundError:
    from settings import API_BASE_URL  # type: ignore


class ExternalCameraSensor:
    def __init__(self, snapshot_url: str):
        self.snapshot_url = snapshot_url

    def get_image(self) -> Optional[Image.Image]:
        try:
            response = requests.get(self.snapshot_url, timeout=3)
            response.raise_for_status()
            return Image.open(BytesIO(response.content)).convert("RGB")
        except Exception as exc:
            st.warning(f"Camera error: {exc}")
            return None


class ImageInput:
    def __init__(self, camera: ExternalCameraSensor, access_token: str | None):
        self.camera = camera
        self.access_token = access_token

    def render(self) -> Optional[Image.Image]:
        st.subheader("Plant Image Input")
        st.caption("Use your phone browser camera for a live demo, upload any saved leaf image, or fetch a frame from an external camera URL.")
        source = st.radio(
            "Select image source:",
            ["Phone Camera", "Upload from Phone / PC", "External Camera Sensor"],
        )

        if source == "Phone Camera":
            return self._phone_camera()
        if source == "External Camera Sensor":
            return self._external_camera()
        return self._upload_image()

    def _phone_camera(self) -> Optional[Image.Image]:
        captured = st.camera_input("Take a leaf photo with this device")
        if captured:
            image = Image.open(captured).convert("RGB")
            st.image(image, caption="Phone Camera Image", use_container_width=True)
            self._send_to_api(image, "Phone Camera")
            return image
        return None

    def _external_camera(self) -> Optional[Image.Image]:
        if st.button("Capture from Sensor"):
            image = self.camera.get_image()
            if image:
                st.image(image, caption="External Camera Image", use_container_width=True)
                self._send_to_api(image, "External Camera Sensor")
                return image
        return None

    def _upload_image(self) -> Optional[Image.Image]:
        uploaded = st.file_uploader("Upload plant image", type=["jpg", "jpeg", "png"])
        if uploaded:
            image = Image.open(uploaded).convert("RGB")
            st.image(image, caption="Uploaded Image", width=300)
            self._send_to_api(image, "User Upload")
            return image
        return None

    def _send_to_api(self, image: Image.Image, source: str):
        if not self.access_token:
            return

        with tempfile.NamedTemporaryFile(suffix=".jpg", delete=False) as tmp:
            image.save(tmp.name)
            payload = {
                "file_path": tmp.name,
                "file_type": "image/jpeg",
                "source": source,
            }
            headers = {"Authorization": f"Bearer {self.access_token}"}
            try:
                response = requests.post(
                    f"{API_BASE_URL}/image_uploads",
                    json=payload,
                    headers=headers,
                    timeout=3,
                )
                response.raise_for_status()
            except Exception:
                st.warning("Failed to send image metadata to FastAPI")
