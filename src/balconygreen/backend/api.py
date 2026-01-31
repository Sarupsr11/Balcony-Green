# ruff: noqa: B008

import logging
import uuid
from datetime import datetime, timedelta, timezone

from fastapi import Depends, FastAPI, HTTPException  # type: ignore
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer, OAuth2PasswordBearer  # type: ignore
from jose import JWTError, jwt  # type: ignore
from pydantic import BaseModel  # type: ignore

from balconygreen.db_implementation.db_general import Database
from balconygreen.user_service import UserService

logger = logging.getLogger(__name__)
logger.setLevel(logging.DEBUG)

# ============================================================
# CONFIG
# ============================================================

SECRET_KEY = "CHANGE_ME_TO_ENV_SECRET"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
DB_PATH = "balcony.db"

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
device_scheme = HTTPBearer(auto_error=False)

app = FastAPI(title="Balcony Green API")

database = Database(DB_PATH)
user_service = UserService(DB_PATH)

# ============================================================
# MODELS
# ============================================================


class SignupRequest(BaseModel):
    email: str
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    email: str
    password: str


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "Bearer"


class DeviceRegistration(BaseModel):
    device_name: str
    device_ip: str | None = None
    sensor_types: list[str]
    device_type: str = "physical"
    city: str | None = None


class SensorReading(BaseModel):
    sensor_id: str
    value: float
    unit: str | None = None
    source: str = "sensor"
    timestamp: datetime | None = None


# ============================================================
# JWT SERVICE (USERS ONLY)
# ============================================================


class JWTService:
    @staticmethod
    def create_token(user_id: str):
        payload = {
            "sub": user_id,
            "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def verify_token(token: str):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload["sub"]
        except JWTError:
            raise HTTPException(status_code=401, detail="Invalid or expired token") from None


# ============================================================
# AUTH DEPENDENCIES
# ============================================================


def get_current_user(token: str = Depends(oauth2_scheme)):
    user_id = JWTService.verify_token(token)
    user = user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {
        "id": user_id,
        "email": user[1],
        "name": user[2],
        "type": "user",
    }


def get_current_device(
    creds: HTTPAuthorizationCredentials = Depends(device_scheme),
):
    if not creds:
        raise HTTPException(status_code=401, detail="Device token required")

    device_key = creds.credentials
    device = database.fetch_one(
        "SELECT id, is_active FROM devices WHERE device_key = ?",
        (device_key,),
    )
    if not device or not device["is_active"]:
        raise HTTPException(status_code=401, detail="Invalid or inactive device")

    # heartbeat: update last_seen
    database.execute(
        "UPDATE devices SET last_seen = CURRENT_TIMESTAMP WHERE id = ?",
        (device["id"],),
    )

    return {"id": device["id"], "type": "device"}


# ============================================================
# USER AUTH ENDPOINTS
# ============================================================


@app.post("/auth/signup")
def signup(data: SignupRequest):
    user_service.create_user(data.email, data.password, data.name)
    return {"message": "User created"}


@app.post("/auth/login", response_model=TokenResponse)
def login(data: LoginRequest):
    user = user_service.get_user(data.email)
    if not user:
        raise HTTPException(401, "Invalid credentials")

    user_id, _, hashed_pw = user
    if not user_service.verify_password(data.password, hashed_pw):
        raise HTTPException(401, "Invalid credentials")

    token = JWTService.create_token(user_id)
    return {"access_token": token}


# ============================================================
# DEVICE MANAGEMENT (USER ONLY)
# ============================================================


@app.post("/register_device")
async def register_device(
    device: DeviceRegistration,
    user=Depends(get_current_user),
):
    device_id = str(uuid.uuid4())
    device_key = str(uuid.uuid4())

    database.execute(
        """
        INSERT INTO devices
        (id, user_id, device_name, device_ip, device_key, device_type, city, is_active)
        VALUES (?, ?, ?, ?, ?, ?, ?, 1)
        """,
        (device_id, user["id"], device.device_name, device.device_ip, device_key, device.device_type, device.city),
    )

    # Generate sensor IDs and return sensor map
    sensor_map: dict[str, str] = {}
    for sensor_name in device.sensor_types:
        sensor_id = str(uuid.uuid4())
        sensor_map[sensor_name] = sensor_id
        database.execute(
            "INSERT INTO sensors (id, device_id, sensor_name, sensor_type) VALUES (?, ?, ?, ?)",
            (sensor_id, device_id, sensor_name, sensor_name),
        )

    return {
        "status": "success",
        "device_id": device_id,
        "device_key": device_key,  # store locally on device
        "sensor_map": sensor_map,  # store locally on device
        "device_type": device.device_type,
    }


@app.get("/devices")
async def get_devices(user=Depends(get_current_user)):
    rows = database.fetch_all(
        """
        SELECT d.id, d.device_name, d.device_ip, d.is_active,
               d.device_type, d.city,
               GROUP_CONCAT(s.sensor_name) AS sensors
        FROM devices d
        LEFT JOIN sensors s ON d.id = s.device_id
        WHERE d.user_id = ?
        GROUP BY d.id
        """,
        (user["id"],),
    )

    return [
        {
            "id": r["id"],
            "name": r["device_name"],
            "ip": r["device_ip"],
            "active": bool(r["is_active"]),
            "type": r["device_type"],
            "city": r["city"],
            "sensors": r["sensors"].split(",") if r["sensors"] else [],
        }
        for r in rows
    ]


@app.delete("/devices/{device_id}")
async def remove_device(device_id: str, user=Depends(get_current_user)):
    database.execute("DELETE FROM sensors WHERE device_id = ?", (device_id,))
    database.execute("DELETE FROM devices WHERE id = ? AND user_id = ?", (device_id, user["id"]))
    return {"status": "success"}


# ============================================================
# SENSOR INGESTION (DEVICE ONLY)
# ============================================================


@app.post("/sensor_readings")
async def save_sensor_reading(
    reading: SensorReading,
    device=Depends(get_current_device),
):
    timestamp = reading.timestamp or datetime.now(timezone.utc)

    database.execute(
        """
        INSERT INTO readings
        (device_id, sensor_id, value, source, timestamp)
        VALUES (?, ?, ?, ?, ?)
        """,
        (device["id"], reading.sensor_id, reading.value, reading.source, timestamp),
    )

    return {
        "status": "success",
        "device_id": device["id"],
        "timestamp": timestamp,
    }


# ============================================================
# READINGS (USER ONLY)
# ============================================================


@app.get("/readings")
async def get_readings(user=Depends(get_current_user)):
    rows = database.fetch_all(
        """
        SELECT s.sensor_name, r.value, r.timestamp, r.source
        FROM readings r
        JOIN sensors s ON r.sensor_id = s.id
        JOIN devices d ON r.device_id = d.id
        WHERE d.user_id = ?
        ORDER BY r.timestamp DESC
        """,
        (user["id"],),
    )

    return [
        {
            "sensor_name": r["sensor_name"],
            "value": r["value"],
            "timestamp": r["timestamp"],
            "source": r["source"],
        }
        for r in rows
    ]
