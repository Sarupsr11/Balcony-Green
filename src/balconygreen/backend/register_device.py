import json
import logging
import os
from pathlib import Path

import requests  # type: ignore

FASTAPI_URL = "http://127.0.0.1:8000"

DEVICE_DIR = Path("device_data/devices")
DEVICE_DIR.mkdir(parents=True, exist_ok=True)

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)


class DeviceRegister:
    def __init__(self, device_payload: dict, headers: dict):
        self.device_payload = device_payload
        self.headers = headers
        logger.info(f"DeviceRegister initialized for device: {device_payload.get('device_name')}")

    def register(self) -> dict:
        logger.info(f"Registering device: {self.device_payload.get('device_name')}")
        try:
            response = requests.post(
                f"{FASTAPI_URL}/register_device",
                json=self.device_payload,
                headers=self.headers,
                timeout=10,
            )

            if response.status_code != 200:
                logger.error(f"Device registration failed: {response.status_code} {response.text}")
                raise RuntimeError(f"Device registration failed: {response.status_code} {response.text}")

            data = response.json()

            device_id = data["device_id"]
            device_file = DEVICE_DIR / f"{device_id}.json"

            # atomic write
            tmp_file = device_file.with_suffix(".tmp")
            with open(tmp_file, "w") as f:
                json.dump(data, f, indent=2)

            tmp_file.replace(device_file)
            logger.info(f"Device registered successfully: {device_id}")

            return response
        except Exception as e:
            logger.error(f"Device registration error: {e}")
            raise


def remove_device(device_id):
    logger.info(f"Attempting to remove device: {device_id}")

    file_path = DEVICE_DIR / f"{device_id}.json"

    if os.path.exists(file_path):
        try:
            os.remove(file_path)  # deletes the file
            logger.info(f"Successfully deleted device file: {file_path}")
        except Exception as e:
            logger.error(f"Error deleting device file {file_path}: {e}")
    else:
        logger.warning(f"Device file does not exist: {file_path}")
