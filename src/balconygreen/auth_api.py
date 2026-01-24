# auth_api.py
from fastapi import FastAPI, HTTPException, Depends, status  # type: ignore
from fastapi.security import OAuth2PasswordBearer # type: ignore
from pydantic import BaseModel  # type: ignore
from passlib.context import CryptContext  # type: ignore
from jose import jwt, JWTError  # type: ignore
from datetime import datetime, timedelta, timezone
import uuid
from balconygreen.db_implementation.db_general import Database
from balconygreen.user_service import UserService

# -------------------------
# Config
# -------------------------
SECRET_KEY = "CHANGE_ME_TO_ENV_SECRET"
ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60
DB_PATH = "balcony.db"

pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")
app = FastAPI(title="Balcony Green Auth API")

# -------------------------
# Models
# -------------------------
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


class SensorReading(BaseModel):
    sensor_name: str
    value: float
    source: str = "Environment Sensors"
    unit: str | None = None
    timestamp: datetime | None = None

class Sensor(BaseModel):
    sensor_name: str          
    sensor_source: str 
    device_info: str
    timestamp: datetime | None = None
     



# -------------------------
# Services
# -------------------------
user_service = UserService(DB_PATH)

# -------------------------
# JWT Utilities
# -------------------------
class JWTService:
    @staticmethod
    def create_token(user_id: str):
        payload = {
            "sub": user_id,
            "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES)
        }
        return jwt.encode(payload, SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def verify_token(token: str):
        try:
            payload = jwt.decode(token, SECRET_KEY, algorithms=[ALGORITHM])
            return payload["sub"]
        except JWTError:
            raise HTTPException(401, "Invalid or expired token")


# -------------------------
# OAuth2 scheme for access token
# -------------------------
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


def get_current_user(token: str = Depends(oauth2_scheme)):
    print("TOKEN RECEIVED:", token)
    try:
        user_id = JWTService.verify_token(token)
        user = user_service.get_user_by_id(user_id)
        if not user:
            raise HTTPException(status_code=401, detail="User not found")
        return {"id": user_id, "email": user[1], "name": user[2]}
    except Exception as e:
        print("JWT ERROR:", e)
        raise HTTPException(status_code=401, detail="Invalid or expired token")


database = Database(DB_PATH)



# -------------------------
# Sensor Endpoints
# -------------------------
@app.post("/user_sensors")
async def add_reading(reading: SensorReading, user=Depends(get_current_user)):
    """
    Save a reading for the authenticated user.

    """
    
    timestamp = datetime.now(tz=timezone.utc)
    database.execute(
        "INSERT INTO readings ( sensor_name, value, timestamp, source) VALUES (?, ?, ?,  ?)",
        ( reading.sensor_name, reading.value, timestamp, reading.source)
    )
    return {"status": "success", "timestamp": timestamp, "user_id": user["id"]}


@app.post("/register_sensors")
async def add_sensor(reading: Sensor, user=Depends(get_current_user)):
    """
    Save a reading for the authenticated user.

    """
    sensor_id = str(uuid.uuid4())
    print(user["id"], reading, user)
    database.execute(
        "INSERT INTO sensors ( id,  user_id , sensor_name, sensor_type ) VALUES (?, ?, ?, ?)",
        (sensor_id, user["id"], reading.sensor_name, reading.sensor_source)
    )
    
    return {"status": "success", "user_id": user["id"]}



@app.get("/readings")
async def get_readings(user=Depends(get_current_user)):
    """
    Fetch all readings for the authenticated user.
    """
    database.execute(
        "SELECT sensor_name, value, timestamp, source FROM readings WHERE user_id = ? ORDER BY timestamp DESC",
        (user["id"],)
    )
    rows = database.fetchall()
    return [
        {"sensor_name": r[0], "value": r[1], "timestamp": r[2], "source": r[3]}
        for r in rows
    ]


# -------------------------
# Auth Endpoints (UNCHANGED)
# -------------------------
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
