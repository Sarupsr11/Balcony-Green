import os
import uuid
import logging
import subprocess
import shutil
import socket
import json

from datetime import datetime, timedelta, timezone
from typing import List, Optional
from pathlib import Path

from fastapi import ( # type: ignore
    FastAPI,
    Depends,
    HTTPException,
    File,
    UploadFile,
    BackgroundTasks
)

from fastapi.responses import FileResponse # type: ignore
from fastapi.security import OAuth2PasswordBearer, HTTPAuthorizationCredentials, HTTPBearer # type: ignore
from fastapi.middleware.cors import CORSMiddleware # type: ignore

from jose import JWTError, jwt # type: ignore
from pydantic import BaseModel # type: ignore
from sqlalchemy.orm import Session # type: ignore

from balconygreen.db_implementation.db_general import SessionLocal
from balconygreen.db_implementation.schema.users import User
from balconygreen.db_implementation.schema.devices import Device
from balconygreen.db_implementation.schema.sensor import Sensor
from balconygreen.db_implementation.schema.reading import Reading
from balconygreen.db_implementation.schema.image import Image

from balconygreen.utils import hash_password, verify_password


# ======================
# Logging
# ======================

logging.basicConfig(level=logging.INFO)
logger = logging.getLogger("balconygreen")


# ======================
# Configuration
# ======================

SECRET_KEY = os.getenv("SECRET_KEY")
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60


# Use the LAN IP for your backend URL
BASE_URL = "http://10.66.165.182:8000"

logger.info(f"LAN: {BASE_URL}")


# ======================
# FastAPI
# ======================

app = FastAPI(title="BalconyGreen API")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
device_scheme = HTTPBearer(auto_error=False)


@app.get("/favicon.ico")
def favicon():
    return {}

# ======================
# Storage
# ======================



FIRMWARE_DIR = Path("firmware_bins")
IMAGE_DIR = Path("images")

FIRMWARE_DIR.mkdir(exist_ok=True, parents=True)
IMAGE_DIR.mkdir(exist_ok=True, parents=True)


# ======================
# Database
# ======================

def get_db():
    logging.info("Initializing the Database ")
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()



# ======================
# Models
# ======================

class SignupRequest(BaseModel):
    email: str
    password: str
    name: Optional[str]


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"


class DeviceRegistration(BaseModel):
    device_name: str
    device_type: str = "physical"
    city: Optional[str] = None
    device_ip: Optional[str] = None
    wifi_ssid: Optional[str] = None
    wifi_password: Optional[str] = None


class SensorReading(BaseModel):
    sensor_id: str
    value: float
    unit: Optional[str] = None
    sensor_name: str = "sensor"
    timestamp: Optional[datetime] = None


class DeviceActivation(BaseModel):
    device_key: str


# ======================
# JWT Service
# ======================

class JWTService:

    @staticmethod
    def create_token(user_id: str):
        payload = {
            "sub": user_id,
            "exp": datetime.now(timezone.utc)
            + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def verify_token(token: str):

        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload["sub"]

        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid token")


# ======================
# Auth Dependencies
# ======================

def get_current_user(
    db: Session = Depends(get_db),
    token: str = Depends(oauth2_scheme)
):

    user_id = JWTService.verify_token(token)

    user = db.query(User).filter(User.id == user_id).first()

    if not user:
        raise HTTPException(status_code=401, detail="User not found")

    return user


def get_current_device(
    db: Session = Depends(get_db),
    creds: HTTPAuthorizationCredentials = Depends(device_scheme)
):

    if not creds:
        raise HTTPException(status_code=401, detail="Device token required")

    device_key = creds.credentials

    device = db.query(Device).filter(Device.device_key == device_key).first()

    if not device or not device.is_active:
        raise HTTPException(status_code=401, detail="Invalid device")

    device.last_seen = datetime.now(timezone.utc)
    db.commit()

    return device


# ======================
# Auth Endpoints
# ======================

@app.post("/auth/signup")
def signup(data: SignupRequest, db: Session = Depends(get_db)):

    if db.query(User).filter(User.email == data.email).first():
        raise HTTPException(400, "Email already exists")

    user = User(
        email=data.email,
        name=data.name,
        password_hash=hash_password(data.password)
    )

    db.add(user)
    db.commit()
    db.refresh(user)

    return {"user_id": user.id}


@app.post("/auth/login", response_model=TokenResponse)
def login(data: LoginRequest, db: Session = Depends(get_db)):

    user = db.query(User).filter(User.email == data.email).first()

    if not user or not verify_password(data.password, user.password_hash):
        raise HTTPException(401, "Invalid credentials")

    token = JWTService.create_token(user.id)

    return {"access_token": token}





# ======================
# Device Registration
# ======================

@app.post("/register_device")
def register_device(
    device: DeviceRegistration,
    background_tasks: BackgroundTasks,
    user: User = Depends(get_current_user),
    db: Session = Depends(get_db)
):
    # Generate unique device ID and key
    device_id = str(uuid.uuid4())
    device_key = str(uuid.uuid4())

    # Create device record in DB (no sensors yet)
    db_device = Device(
        id=device_id,
        user_id=user.id,
        device_type = device.device_type,
        device_name=device.device_name,
        device_key=device_key,
        city=device.city,
        is_active=True
    )
    db.add(db_device)
    db.commit()

    if device.device_type != "upload":
        return {
            "device_id": device_id,
            "device_key": device_key,
            "firmware": {
                "bin_url": f"{BASE_URL}/firmware/generic/firmware.bin",
                "manifest_url": f"{BASE_URL}/firmware/generic/manifest.json"
            },
            "wifi_ssid": device.wifi_ssid,
            "wifi_password": device.wifi_password
        }
    else:
        return {
            "device_id": device_id,
            "device_key": device_key
        }




@app.get("/firmware/generic/firmware.bin")
def get_generic_firmware():
    firmware_bins = Path("/app/ESP_module/.pio/build/esp32dev")
    file_path =  firmware_bins / "firmware.bin"
    if not file_path.exists():
        raise HTTPException(404, "Firmware not found")
    return FileResponse(file_path)

@app.get("/firmware/generic/bootloader.bin")
def get_generic_firmware():
    firmware_bins = Path("/app/ESP_module/.pio/build/esp32dev")
    file_path =  firmware_bins / "bootloader.bin"
    if not file_path.exists():
        raise HTTPException(404, "Firmware not found")
    return FileResponse(file_path)

@app.get("/firmware/generic/partitions.bin")
def get_generic_firmware():
    firmware_bins = Path("/app/ESP_module/.pio/build/esp32dev")
    file_path =  firmware_bins / "partitions.bin"
    if not file_path.exists():
        raise HTTPException(404, "Firmware not found")
    return FileResponse(file_path)


@app.get("/firmware/generic/manifest.json")
def get_generic_manifest():
    return {
        "name": "BalconyGreen Sensor Device",
        "builds": [
            {
                "chipFamily": "ESP32",
                "parts": [
                    {"path": f"{BASE_URL}/firmware/generic/bootloader.bin", "offset": 4096},
                    {"path": f"{BASE_URL}/firmware/generic/partitions.bin", "offset": 32768},
                    {"path": f"{BASE_URL}/firmware/generic/firmware.bin", "offset": 65536}
                ]
            }
        ]
    }


# @app.get("/firmware/{device_id}/manifest.json")
# def firmware_manifest(device_id: str):

#     device_dir = FIRMWARE_DIR / device_id

#     if not device_dir.exists():
#         raise HTTPException(404, "Firmware not ready")

#     return {
#         "name": "BalconyGreen Sensor Device",
#         "builds": [
#             {
#                 "chipFamily": "ESP32",
#                 "parts": [
#                     {"path": f"{BASE_URL}/firmware/{device_id}/bootloader.bin", "offset": 4096},
#                     {"path": f"{BASE_URL}/firmware/{device_id}/partitions.bin", "offset": 32768},
#                     {"path": f"{BASE_URL}/firmware/{device_id}/firmware.bin", "offset": 65536}
#                 ]
#             }
#         ]
#     }


# # ======================
# # Firmware Endpoints
# # ======================



# @app.get("/firmware_status/{device_id}")
# def firmware_status(device_id: str):

#     firmware = FIRMWARE_DIR / device_id / "firmware.bin"

#     if firmware.exists():
#         return {"status": "ready"}

#     return {"status": "building"}


# @app.get("/firmware/{device_id}/{filename}")
# def get_firmware_file(device_id: str, filename: str):

#     file_path = FIRMWARE_DIR / device_id / filename

#     if not file_path.exists():
#         raise HTTPException(404, "Firmware file not found")

#     return FileResponse(file_path)



# ======================
# Firmware Build
# ======================

# def escape_for_macro(s):
#     return f'\\"{s}\\"'  # escape inner quotes

# def generate_firmware(
#     device_id,
#     device_key,
#     wifi_ssid,
#     wifi_password,
#     backend_url
# ):

#     try:

#         logger.info(f"Building firmware for {device_id}")


#         # Build flags for PlatformIO
#         build_flags = [
#             f'-DWIFI_SSID="{escape_for_macro(wifi_ssid)}"',
#             f'-DWIFI_PASSWORD="{escape_for_macro(wifi_password)}"',
#             f'-DDEVICE_KEY="{escape_for_macro(device_key)}"',
#             f'-DDEVICE_ID="{escape_for_macro(device_id)}"',
#             f'-DBACKEND_URL="{escape_for_macro(backend_url)}"'
#         ]
#         env = os.environ.copy()
#         env["PLATFORMIO_BUILD_FLAGS"] = " ".join(build_flags)

#         esp_module_path = Path("/app/balconygreen/ESP_module")
#         subprocess.run(
#             ["pio", "run"],
#             cwd=esp_module_path,
#             env=env,
#             check=True
#         )

#         device_dir = FIRMWARE_DIR / device_id
#         device_dir.mkdir(exist_ok=True, parents=True)

#         shutil.copy(esp_module_path/".pio"/"build"/"esp32dev"/"bootloader.bin", device_dir / "bootloader.bin")
#         shutil.copy(esp_module_path/".pio"/"build"/"esp32dev"/"partitions.bin", device_dir / "partitions.bin")
#         shutil.copy(esp_module_path/".pio"/"build"/"esp32dev"/"firmware.bin", device_dir / "firmware.bin")

#         logger.info(f"Firmware built for {device_id}")

#     except Exception as e:
#         logger.error(f"Firmware build failed: {e}")

# ======================
# Devices
# ======================

@app.get("/devices")
def get_devices(user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    devices = db.query(Device).filter(Device.user_id == user.id).all()

    results = []

    for d in devices:

        sensors = db.query(Sensor).filter(Sensor.device_id == d.id).all()

        results.append({
            "id": d.id,
            "name": d.device_name,
            "ip": d.device_ip,
            "type": d.device_type,
            "active": d.is_active,
            "type": d.device_type,
            "city": d.city,
            "sensors": [
                {
                    "id": s.id,
                    "name": s.sensor_name
                }
                for s in sensors
            ]
        })

    return results


@app.delete("/devices/{device_id}")
def remove_device(device_id: str, user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    device = db.query(Device).filter(
        Device.id == device_id,
        Device.user_id == user.id
    ).first()

    if device:
        db.delete(device)
        db.commit()

    return {"status": "success"}


# ======================
# Sensor Readings
# ======================


@app.post("/device/sync_sensors")
def sync_sensors(
    payload: dict,
    device: Device = Depends(get_current_device),  # 🔐 secure auth
    db: Session = Depends(get_db)
):
    try:
        sensors = payload.get("sensors", [])

        if not sensors:
            raise HTTPException(status_code=400, detail="No sensors provided")

        result = {}

        for sensor_name in sensors:
            timestamp = datetime.now(timezone.utc)
            # Normalize sensor type
            sensor_name = sensor_name.strip().lower()

            dev = db.query(Device).filter(
                Device.device_key == device.device_key
            ).first()

            # Check if sensor already exists for this device
            existing = db.query(Sensor).filter(
                Sensor.device_id == dev.id,
                Sensor.sensor_name == sensor_name
            ).first()

            if existing:
                sensor_id = existing.id
            else:
                sensor_id = str(uuid.uuid4())

                new_sensor = Sensor(
                    id=sensor_id,
                    device_id=device.id,
                    sensor_name=sensor_name,
                    created_at = timestamp
                )

                db.add(new_sensor)
                db.commit()

            result[sensor_name] = sensor_id
            

        return result

    except Exception as e:
        print("SYNC ERROR:", str(e))
        raise HTTPException(status_code=500, detail="Sensor sync failed")
    


@app.post("/sensor_readings")
def save_sensor_reading(
    reading: SensorReading,
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):

    timestamp = reading.timestamp or datetime.now(timezone.utc)

    db_reading = Reading(
        device_id=device.id,
        sensor_id=reading.sensor_id,
        value=reading.value,
        sensor_name=reading.sensor_name,
        timestamp=timestamp
    )

    db.add(db_reading)
    db.commit()

    return {"status": "success"}


@app.get("/readings")
def get_readings(user: User = Depends(get_current_user), db: Session = Depends(get_db)):

    readings = (
        db.query(Reading, Sensor)
        .join(Sensor, Reading.sensor_id == Sensor.id)
        .join(Device, Reading.device_id == Device.id)
        .filter(Device.user_id == user.id)
        .order_by(Reading.timestamp.desc())
        .all()
    )

    return [
        {
            "sensor_name": sensor.sensor_name,
            "value": reading.value,
            "timestamp": reading.timestamp,
            "sensor_name": reading.sensor_name
        }
        for reading, sensor in readings
    ]


# ======================
# Camera Upload
# ======================

from fastapi import UploadFile, File, Form, HTTPException # type: ignore
import tempfile
import shutil
from balconygreen.model_prediction.models import get_model

@app.post("/camera/upload/{sensor_id}")
async def upload_camera_image(
    sensor_id: str,
    file: UploadFile = File(...),
    plant: str = Form(...),                  # ✅ REQUIRED
    mode: str = Form("binary"),              # ✅ binary or disease
    device: Device = Depends(get_current_device),
    db: Session = Depends(get_db)
):
    try:
        # ---------------------------
        # Validate sensor
        # ---------------------------
        sensor = db.query(Sensor).filter(
            Sensor.id == sensor_id,
            Sensor.device_id == device.id
        ).first()

        if not sensor:
            raise HTTPException(404, "Sensor not found")

        # ---------------------------
        # Validate file
        # ---------------------------
        if not file.content_type.startswith("image/"):
            raise HTTPException(400, "File must be an image")

        # ---------------------------
        # Save image
        # ---------------------------
        sensor_folder = IMAGE_DIR / f"sensor_{sensor_id}"
        sensor_folder.mkdir(exist_ok=True, parents=True)

        timestamp = datetime.now(timezone.utc)
        filename = timestamp.strftime("%Y-%m-%d_%H-%M-%S") + ".jpg"
        file_path = sensor_folder / filename

        
        with open(file_path, "wb") as buffer:
            shutil.copyfileobj(file.file, buffer)

        # ---------------------------
        # Run prediction
        # ---------------------------
        model = get_model(plant, mode)

        results = model.predict(
            str(file_path),
            top_k=3,
            confidence_threshold=0.1
        )

        # ---------------------------
        # Format prediction
        # ---------------------------
        if mode == "binary":
            best = results[0]
            prediction = best["class_name"]
            confidence = round(best["confidence"] * 100, 2)
            prediction_data = {
                "prediction": prediction,
                "confidence": confidence
            }

        else:
            prediction_data = {
                "predictions": [
                    {
                        "disease": r["class_name"],
                        "confidence": round(r["confidence"] * 100, 2)
                    }
                    for r in results
                ]
            }

        # ---------------------------
        # Save to DB
        # ---------------------------
        db_image = Image(
            device_id=device.id,
            sensor_id=sensor_id,
            image_path=str(file_path),
            source="camera",
            timestamp=timestamp,
            prediction=json.dumps(prediction_data)  # ✅ store prediction
        )

        db.add(db_image)
        db.commit()

        # ---------------------------
        # Return response
        # ---------------------------
        return {
            "status": "success",
            "plant": plant,
            **prediction_data
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


@app.get("/")
def root():
    return {"status": "ok", "message": "BalconyGreen API is running"}