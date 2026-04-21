from __future__ import annotations

import json
import uuid
from datetime import datetime, timedelta, timezone
from typing import Any

from fastapi import Depends, FastAPI, HTTPException  # type: ignore
from fastapi.security import OAuth2PasswordBearer  # type: ignore
from jose import JWTError, jwt  # type: ignore
from pydantic import BaseModel  # type: ignore

from balconygreen.db_implementation.db_general import Database
from balconygreen.settings import DB_PATH, JWT_SECRET_KEY
from balconygreen.user_service import UserService


ALGORITHM = "HS256"
ACCESS_TOKEN_EXPIRE_MINUTES = 60 * 24 * 30
app = FastAPI(title="Balcony Green Auth API")


class SignupRequest(BaseModel):
    username: str | None = None
    email: str | None = None
    password: str
    name: str | None = None


class LoginRequest(BaseModel):
    username: str | None = None
    email: str | None = None
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
    device_id: str | None = None


class SensorReadingBatch(BaseModel):
    readings: list[SensorReading]


class Sensor(BaseModel):
    sensor_name: str
    sensor_source: str
    device_info: str
    timestamp: datetime | None = None


class ImageUploadEvent(BaseModel):
    file_path: str
    file_type: str = "image/jpeg"
    source: str = "camera"


class WaterNowCommandRequest(BaseModel):
    device_id: str
    pump_ms: int
    plant_type: str = "unknown"
    reason: str = "manual_dashboard_trigger"


class CommandAcknowledgeRequest(BaseModel):
    command_id: str
    status: str = "executed"
    message: str | None = None


class CalibrationRequest(BaseModel):
    device_id: str
    plant_type: str
    soil_raw_dry: int
    soil_raw_wet: int
    moisture_target_pct: float = 70.0
    pump_flow_ml_per_sec: float | None = None
    failure_min_rise_pct: float = 2.0
    failure_window_minutes: int = 45
    notes: str | None = None


class WateringFeedbackRequest(BaseModel):
    plant_type: str
    feedback_label: str
    device_id: str | None = None
    command_id: str | None = None
    notes: str | None = None


user_service = UserService(DB_PATH)
database = Database(DB_PATH)
oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")


class JWTService:
    @staticmethod
    def create_token(user_id: str):
        payload = {
            "sub": user_id,
            "exp": datetime.now(tz=timezone.utc) + timedelta(minutes=ACCESS_TOKEN_EXPIRE_MINUTES),
        }
        return jwt.encode(payload, JWT_SECRET_KEY, algorithm=ALGORITHM)

    @staticmethod
    def verify_token(token: str):
        try:
            payload = jwt.decode(token, JWT_SECRET_KEY, algorithms=[ALGORITHM])
            return payload["sub"]
        except JWTError as exc:
            raise HTTPException(401, "Invalid or expired token") from exc


def get_current_user(token: str = Depends(oauth2_scheme)):
    user_id = JWTService.verify_token(token)
    user = user_service.get_user_by_id(user_id)
    if not user:
        raise HTTPException(status_code=401, detail="User not found")
    return {"id": user_id, "username": user[1], "email": user[1], "name": user[2]}


def _auth_identifier(username: str | None = None, email: str | None = None) -> str:
    identifier = (username or email or "").strip()
    if not identifier:
        raise HTTPException(400, "Username is required")
    return identifier


def _parse_db_datetime(value: Any) -> datetime | None:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value
    text = str(value).replace("Z", "+00:00")
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        return parsed.replace(tzinfo=timezone.utc)
    return parsed


def _serialize_command(row: dict) -> dict:
    payload = json.loads(row["payload_json"])
    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "command_type": row["command_type"],
        "payload": payload,
        "status": row["status"],
        "device_message": row.get("device_message"),
        "created_at": row["created_at"],
        "delivered_at": row.get("delivered_at"),
        "acknowledged_at": row.get("acknowledged_at"),
    }


def _normalize_plant_type(value: str) -> str:
    normalized = value.strip().lower().replace(" ", "_")
    aliases = {
        "basil": "basilikum",
        "tomato": "tomato_indoor",
        "houseplant": "houseplant_generic",
        "succulent": "succulent_cactus",
        "mint": "houseplant_generic",
        "potato": "houseplant_generic",
    }
    return aliases.get(normalized, normalized or "houseplant_generic")


def _serialize_calibration(row: dict) -> dict:
    return {
        "id": row["id"],
        "device_id": row["device_id"],
        "plant_type": row["plant_type"],
        "soil_raw_dry": row["soil_raw_dry"],
        "soil_raw_wet": row["soil_raw_wet"],
        "moisture_target_pct": row["moisture_target_pct"],
        "pump_flow_ml_per_sec": row.get("pump_flow_ml_per_sec"),
        "failure_min_rise_pct": row["failure_min_rise_pct"],
        "failure_window_minutes": row["failure_window_minutes"],
        "notes": row.get("notes"),
        "created_at": row["created_at"],
    }


def _get_latest_calibration(user_id: str, device_id: str, plant_type: str | None = None) -> dict | None:
    if plant_type:
        return database.fetch_one(
            """
            SELECT *
            FROM soil_sensor_calibrations
            WHERE user_id = ? AND device_id = ? AND plant_type = ?
            ORDER BY created_at DESC
            LIMIT 1
            """,
            (user_id, device_id, _normalize_plant_type(plant_type)),
        )
    return database.fetch_one(
        """
        SELECT *
        FROM soil_sensor_calibrations
        WHERE user_id = ? AND device_id = ?
        ORDER BY created_at DESC
        LIMIT 1
        """,
        (user_id, device_id),
    )


def _raw_to_moisture_pct(raw_value: float, calibration: dict | None) -> float | None:
    if calibration is None:
        return None
    raw_dry = float(calibration["soil_raw_dry"])
    raw_wet = float(calibration["soil_raw_wet"])
    span = raw_dry - raw_wet
    if abs(span) < 1e-6:
        return None
    moisture = ((raw_dry - float(raw_value)) * 100.0) / span
    return max(0.0, min(100.0, moisture))


def _query_sensor_series(
    user_id: str,
    sensor_name: str,
    start_time: datetime | None = None,
    end_time: datetime | None = None,
    device_id: str | None = None,
    limit: int = 200,
) -> list[dict]:
    clauses = ["user_id = ?", "sensor_name = ?"]
    params: list[Any] = [user_id, sensor_name]
    if device_id:
        clauses.append("device_id = ?")
        params.append(device_id)
    if start_time:
        clauses.append("timestamp >= ?")
        params.append(start_time)
    if end_time:
        clauses.append("timestamp <= ?")
        params.append(end_time)
    params.append(max(1, min(limit, 5000)))
    return database.fetch_all(
        f"""
        SELECT sensor_name, value, timestamp, source, device_id
        FROM readings
        WHERE {' AND '.join(clauses)}
        ORDER BY timestamp ASC
        LIMIT ?
        """,
        tuple(params),
    )


def _get_nearest_before(readings: list[dict], event_time: datetime) -> dict | None:
    eligible = [row for row in readings if (_parse_db_datetime(row["timestamp"]) or event_time) <= event_time]
    return eligible[-1] if eligible else None


def _get_max_after(readings: list[dict], event_time: datetime) -> dict | None:
    eligible = [row for row in readings if (_parse_db_datetime(row["timestamp"]) or event_time) >= event_time]
    if not eligible:
        return None
    return max(eligible, key=lambda row: float(row["value"]))


def _estimate_command_water_ml(command_row: dict, calibration: dict | None) -> float | None:
    pump_ms = float(json.loads(command_row["payload_json"]).get("pump_ms", 0.0))
    if pump_ms <= 0:
        return 0.0
    if calibration is None or calibration.get("pump_flow_ml_per_sec") is None:
        return None
    flow_rate = float(calibration["pump_flow_ml_per_sec"])
    return round((pump_ms / 1000.0) * flow_rate, 2)


def _build_water_usage_analytics(user_id: str, device_id: str | None = None) -> dict:
    clauses = ["user_id = ?", "status = 'executed'"]
    params: list[Any] = [user_id]
    if device_id:
        clauses.append("device_id = ?")
        params.append(device_id)

    rows = database.fetch_all(
        f"""
        SELECT id, device_id, payload_json, created_at, acknowledged_at
        FROM device_commands
        WHERE {' AND '.join(clauses)}
        ORDER BY COALESCE(acknowledged_at, created_at) DESC
        """,
        tuple(params),
    )

    today = datetime.now(tz=timezone.utc).date()
    daily_totals: dict[str, dict[str, float | int | None]] = {}
    today_pump_ms = 0
    week_pump_ms = 0
    today_ml = 0.0
    week_ml = 0.0
    has_today_ml = False
    has_week_ml = False

    for row in rows:
        event_time = _parse_db_datetime(row.get("acknowledged_at") or row.get("created_at"))
        if event_time is None:
            continue
        payload = json.loads(row["payload_json"])
        pump_ms = int(payload.get("pump_ms", 0) or 0)
        calibration = _get_latest_calibration(user_id, row["device_id"], payload.get("plant_type"))
        estimated_ml = _estimate_command_water_ml(row, calibration)

        day_key = event_time.date().isoformat()
        if day_key not in daily_totals:
            daily_totals[day_key] = {"pump_ms": 0, "estimated_ml": 0.0, "commands": 0, "has_ml": False}
        daily_totals[day_key]["pump_ms"] = int(daily_totals[day_key]["pump_ms"]) + pump_ms
        daily_totals[day_key]["commands"] = int(daily_totals[day_key]["commands"]) + 1
        if estimated_ml is not None:
            daily_totals[day_key]["estimated_ml"] = float(daily_totals[day_key]["estimated_ml"]) + estimated_ml
            daily_totals[day_key]["has_ml"] = True

        if event_time.date() == today:
            today_pump_ms += pump_ms
            if estimated_ml is not None:
                today_ml += estimated_ml
                has_today_ml = True
        if event_time.date() >= today - timedelta(days=6):
            week_pump_ms += pump_ms
            if estimated_ml is not None:
                week_ml += estimated_ml
                has_week_ml = True

    last_seven = []
    for offset in range(6, -1, -1):
        day = today - timedelta(days=offset)
        key = day.isoformat()
        bucket = daily_totals.get(key, {"pump_ms": 0, "estimated_ml": 0.0, "commands": 0, "has_ml": False})
        last_seven.append(
            {
                "date": key,
                "pump_ms": int(bucket["pump_ms"]),
                "estimated_ml": round(float(bucket["estimated_ml"]), 2) if bucket["has_ml"] else None,
                "commands": int(bucket["commands"]),
            }
        )

    return {
        "today": {
            "pump_ms": today_pump_ms,
            "estimated_ml": round(today_ml, 2) if has_today_ml else None,
        },
        "last_7_days": {
            "pump_ms": week_pump_ms,
            "estimated_ml": round(week_ml, 2) if has_week_ml else None,
        },
        "daily_series": last_seven,
    }


def _build_pump_failure_analytics(user_id: str, device_id: str | None = None, limit: int = 5) -> list[dict]:
    clauses = ["user_id = ?", "status = 'executed'"]
    params: list[Any] = [user_id]
    if device_id:
        clauses.append("device_id = ?")
        params.append(device_id)
    params.append(max(1, min(limit, 20)))

    commands = database.fetch_all(
        f"""
        SELECT id, device_id, payload_json, created_at, acknowledged_at, status
        FROM device_commands
        WHERE {' AND '.join(clauses)}
        ORDER BY COALESCE(acknowledged_at, created_at) DESC
        LIMIT ?
        """,
        tuple(params),
    )

    diagnostics: list[dict] = []
    for command in commands:
        payload = json.loads(command["payload_json"])
        event_time = _parse_db_datetime(command.get("acknowledged_at") or command.get("created_at"))
        if event_time is None:
            continue
        calibration = _get_latest_calibration(user_id, command["device_id"], payload.get("plant_type"))
        failure_window = int((calibration or {}).get("failure_window_minutes", 45))
        min_rise_pct = float((calibration or {}).get("failure_min_rise_pct", 2.0))
        window_start = event_time - timedelta(hours=2)
        window_end = event_time + timedelta(minutes=failure_window)

        moisture_rows = _query_sensor_series(
            user_id=user_id,
            sensor_name="soil_moisture",
            start_time=window_start,
            end_time=window_end,
            device_id=command["device_id"],
        )
        raw_rows = _query_sensor_series(
            user_id=user_id,
            sensor_name="soil_raw",
            start_time=window_start,
            end_time=window_end,
            device_id=command["device_id"],
        )

        before = _get_nearest_before(moisture_rows, event_time)
        after = _get_max_after(moisture_rows, event_time)
        moisture_before = float(before["value"]) if before else None
        moisture_after = float(after["value"]) if after else None

        if moisture_before is None or moisture_after is None:
            raw_before = _get_nearest_before(raw_rows, event_time)
            raw_after = _get_max_after(
                [
                    {
                        **row,
                        "value": _raw_to_moisture_pct(float(row["value"]), calibration)
                        if _raw_to_moisture_pct(float(row["value"]), calibration) is not None
                        else row["value"],
                    }
                    for row in raw_rows
                    if _raw_to_moisture_pct(float(row["value"]), calibration) is not None
                ],
                event_time,
            )
            if moisture_before is None and raw_before is not None:
                moisture_before = _raw_to_moisture_pct(float(raw_before["value"]), calibration)
            if moisture_after is None and raw_after is not None:
                moisture_after = float(raw_after["value"])

        if moisture_before is None or moisture_after is None:
            diagnostics.append(
                {
                    "command_id": command["id"],
                    "device_id": command["device_id"],
                    "status": "insufficient_data",
                    "message": "Not enough soil-moisture telemetry after watering to verify pump response.",
                    "created_at": command["created_at"],
                    "moisture_before": moisture_before,
                    "moisture_after": moisture_after,
                    "moisture_delta": None,
                    "min_expected_rise_pct": min_rise_pct,
                    "window_minutes": failure_window,
                }
            )
            continue

        delta = round(float(moisture_after) - float(moisture_before), 2)
        diagnostics.append(
            {
                "command_id": command["id"],
                "device_id": command["device_id"],
                "status": "warning" if delta < min_rise_pct else "ok",
                "message": (
                    "Soil moisture did not rise enough after watering."
                    if delta < min_rise_pct
                    else "Pump response looks normal."
                ),
                "created_at": command["created_at"],
                "moisture_before": round(float(moisture_before), 2),
                "moisture_after": round(float(moisture_after), 2),
                "moisture_delta": delta,
                "min_expected_rise_pct": min_rise_pct,
                "window_minutes": failure_window,
            }
        )

    return diagnostics


def _store_sensor_readings(user_id: str, readings: list[SensorReading]) -> list[datetime]:
    timestamps: list[datetime] = []
    with database.get_conn() as conn:
        for reading in readings:
            timestamp = reading.timestamp or datetime.now(tz=timezone.utc)
            conn.execute(
                """
                INSERT INTO readings (user_id, device_id, sensor_name, value, timestamp, source)
                VALUES (?, ?, ?, ?, ?, ?)
                """,
                (user_id, reading.device_id, reading.sensor_name, reading.value, timestamp, reading.source),
            )
            timestamps.append(timestamp)
    return timestamps


@app.get("/health")
async def health_check():
    return {"status": "ok", "service": "balconygreen-auth-api"}


@app.post("/user_sensors")
async def add_reading(reading: SensorReading, user=Depends(get_current_user)):
    timestamp = _store_sensor_readings(user["id"], [reading])[0]
    return {"status": "success", "timestamp": timestamp, "user_id": user["id"], "device_id": reading.device_id}


@app.post("/user_sensors/bulk")
async def add_readings_batch(batch: SensorReadingBatch, user=Depends(get_current_user)):
    if not batch.readings:
        raise HTTPException(400, "At least one reading is required")
    timestamps = _store_sensor_readings(user["id"], batch.readings)
    return {
        "status": "success",
        "count": len(batch.readings),
        "first_timestamp": timestamps[0],
        "last_timestamp": timestamps[-1],
        "user_id": user["id"],
        "device_id": batch.readings[0].device_id,
    }


@app.post("/register_sensors")
async def add_sensor(reading: Sensor, user=Depends(get_current_user)):
    sensor_id = str(uuid.uuid4())
    database.execute(
        "INSERT INTO sensors (id, user_id, sensor_name, sensor_type, device_info) VALUES (?, ?, ?, ?, ?)",
        (sensor_id, user["id"], reading.sensor_name, reading.sensor_source, reading.device_info),
    )
    return {"status": "success", "user_id": user["id"], "sensor_id": sensor_id}


@app.post("/image_uploads")
async def add_image_upload(upload: ImageUploadEvent, user=Depends(get_current_user)):
    database.execute(
        "INSERT INTO uploads (user_id, file_path, file_type) VALUES (?, ?, ?)",
        (user["id"], upload.file_path, upload.file_type),
    )
    return {"status": "success", "user_id": user["id"], "source": upload.source}


@app.get("/sensors")
async def get_sensors(user=Depends(get_current_user)):
    return database.fetch_all(
        """
        SELECT sensor_name, sensor_type, device_info, created_at
        FROM sensors
        WHERE user_id = ?
        ORDER BY created_at DESC
        """,
        (user["id"],),
    )


@app.get("/readings")
async def get_readings(
    device_id: str | None = None,
    sensor_name: str | None = None,
    hours: int | None = None,
    limit: int = 100,
    user=Depends(get_current_user),
):
    clauses = ["user_id = ?"]
    params: list[Any] = [user["id"]]
    if device_id:
        clauses.append("device_id = ?")
        params.append(device_id)
    if sensor_name:
        clauses.append("sensor_name = ?")
        params.append(sensor_name)
    if hours is not None:
        safe_hours = max(1, min(hours, 24 * 14))
        clauses.append("timestamp >= ?")
        params.append(datetime.now(tz=timezone.utc) - timedelta(hours=safe_hours))
    params.append(max(1, min(limit, 20000)))
    rows = database.fetch_all(
        f"""
        SELECT sensor_name, value, timestamp, source, device_id
        FROM readings
        WHERE {' AND '.join(clauses)}
        ORDER BY timestamp DESC
        LIMIT ?
        """,
        tuple(params),
    )
    return [
        {
            "sensor_name": row["sensor_name"],
            "value": row["value"],
            "timestamp": row["timestamp"],
            "source": row["source"],
            "device_id": row.get("device_id"),
        }
        for row in rows
    ]


@app.post("/calibrations")
async def save_calibration(calibration: CalibrationRequest, user=Depends(get_current_user)):
    calibration_id = str(uuid.uuid4())
    database.execute(
        """
        INSERT INTO soil_sensor_calibrations
        (
            id, user_id, device_id, plant_type, soil_raw_dry, soil_raw_wet,
            moisture_target_pct, pump_flow_ml_per_sec, failure_min_rise_pct,
            failure_window_minutes, notes
        )
        VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
        """,
        (
            calibration_id,
            user["id"],
            calibration.device_id,
            _normalize_plant_type(calibration.plant_type),
            calibration.soil_raw_dry,
            calibration.soil_raw_wet,
            calibration.moisture_target_pct,
            calibration.pump_flow_ml_per_sec,
            calibration.failure_min_rise_pct,
            calibration.failure_window_minutes,
            calibration.notes,
        ),
    )
    row = _get_latest_calibration(user["id"], calibration.device_id, calibration.plant_type)
    return {"status": "saved", "calibration": _serialize_calibration(row) if row else None}


@app.get("/calibrations/latest")
async def get_latest_calibration(device_id: str, plant_type: str | None = None, user=Depends(get_current_user)):
    row = _get_latest_calibration(user["id"], device_id, plant_type)
    if not row:
        return {"status": "empty", "device_id": device_id}
    return {"status": "ok", "calibration": _serialize_calibration(row)}


@app.get("/calibrations/recent")
async def get_recent_calibrations(device_id: str | None = None, limit: int = 10, user=Depends(get_current_user)):
    safe_limit = max(1, min(limit, 20))
    if device_id:
        rows = database.fetch_all(
            """
            SELECT *
            FROM soil_sensor_calibrations
            WHERE user_id = ? AND device_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user["id"], device_id, safe_limit),
        )
    else:
        rows = database.fetch_all(
            """
            SELECT *
            FROM soil_sensor_calibrations
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user["id"], safe_limit),
        )
    return [_serialize_calibration(row) for row in rows]


@app.post("/watering_feedback")
async def save_watering_feedback(feedback: WateringFeedbackRequest, user=Depends(get_current_user)):
    feedback_id = str(uuid.uuid4())
    database.execute(
        """
        INSERT INTO watering_feedback
        (id, user_id, device_id, plant_type, command_id, feedback_label, notes)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            feedback_id,
            user["id"],
            feedback.device_id,
            _normalize_plant_type(feedback.plant_type),
            feedback.command_id,
            feedback.feedback_label.strip().lower(),
            feedback.notes,
        ),
    )
    return {"status": "saved", "feedback_id": feedback_id}


@app.get("/watering_feedback/recent")
async def get_recent_feedback(device_id: str | None = None, limit: int = 10, user=Depends(get_current_user)):
    safe_limit = max(1, min(limit, 20))
    if device_id:
        rows = database.fetch_all(
            """
            SELECT *
            FROM watering_feedback
            WHERE user_id = ? AND device_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user["id"], device_id, safe_limit),
        )
    else:
        rows = database.fetch_all(
            """
            SELECT *
            FROM watering_feedback
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user["id"], safe_limit),
        )
    return rows


@app.post("/commands/water_now")
async def queue_water_now(command: WaterNowCommandRequest, user=Depends(get_current_user)):
    command_id = str(uuid.uuid4())
    created_at = datetime.now(tz=timezone.utc)
    payload = {
        "pump_ms": max(0, int(command.pump_ms)),
        "plant_type": _normalize_plant_type(command.plant_type),
        "reason": command.reason,
    }
    database.execute(
        """
        INSERT INTO device_commands
        (id, user_id, device_id, command_type, payload_json, status, created_at)
        VALUES (?, ?, ?, ?, ?, ?, ?)
        """,
        (
            command_id,
            user["id"],
            command.device_id,
            "water_now",
            json.dumps(payload),
            "queued",
            created_at,
        ),
    )
    return {
        "status": "queued",
        "command_id": command_id,
        "device_id": command.device_id,
        "payload": payload,
        "created_at": created_at,
    }


@app.get("/commands/recent")
async def get_recent_commands(device_id: str | None = None, limit: int = 10, user=Depends(get_current_user)):
    safe_limit = max(1, min(int(limit), 20))
    if device_id:
        rows = database.fetch_all(
            """
            SELECT id, device_id, command_type, payload_json, status, device_message, created_at, delivered_at, acknowledged_at
            FROM device_commands
            WHERE user_id = ? AND device_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user["id"], device_id, safe_limit),
        )
    else:
        rows = database.fetch_all(
            """
            SELECT id, device_id, command_type, payload_json, status, device_message, created_at, delivered_at, acknowledged_at
            FROM device_commands
            WHERE user_id = ?
            ORDER BY created_at DESC
            LIMIT ?
            """,
            (user["id"], safe_limit),
        )
    return [_serialize_command(row) for row in rows]


@app.get("/devices/{device_id}/next_command")
async def get_next_command(device_id: str, user=Depends(get_current_user)):
    row = database.fetch_one(
        """
        SELECT id, device_id, command_type, payload_json, status, device_message, created_at, delivered_at, acknowledged_at
        FROM device_commands
        WHERE user_id = ? AND device_id = ? AND status IN ('queued', 'delivered')
        ORDER BY created_at ASC
        LIMIT 1
        """,
        (user["id"], device_id),
    )
    if not row:
        return {"status": "empty", "device_id": device_id}

    if row["status"] == "queued":
        delivered_at = datetime.now(tz=timezone.utc)
        database.execute(
            "UPDATE device_commands SET status = ?, delivered_at = ? WHERE id = ?",
            ("delivered", delivered_at, row["id"]),
        )
        row["status"] = "delivered"
        row["delivered_at"] = delivered_at

    return {"status": "ok", "command": _serialize_command(row)}


@app.post("/devices/{device_id}/ack_command")
async def acknowledge_command(device_id: str, ack: CommandAcknowledgeRequest, user=Depends(get_current_user)):
    command = database.fetch_one(
        """
        SELECT id, status
        FROM device_commands
        WHERE id = ? AND user_id = ? AND device_id = ?
        """,
        (ack.command_id, user["id"], device_id),
    )
    if not command:
        raise HTTPException(status_code=404, detail="Command not found for device")

    next_status = ack.status if ack.status in {"executed", "failed"} else "executed"
    acknowledged_at = datetime.now(tz=timezone.utc)
    database.execute(
        """
        UPDATE device_commands
        SET status = ?, acknowledged_at = ?, device_message = ?
        WHERE id = ? AND user_id = ? AND device_id = ?
        """,
        (next_status, acknowledged_at, ack.message, ack.command_id, user["id"], device_id),
    )
    return {
        "status": next_status,
        "command_id": ack.command_id,
        "device_id": device_id,
        "acknowledged_at": acknowledged_at,
    }


@app.get("/analytics/water_usage")
async def get_water_usage_analytics(device_id: str | None = None, user=Depends(get_current_user)):
    return _build_water_usage_analytics(user["id"], device_id)


@app.get("/analytics/pump_failures")
async def get_pump_failure_analytics(device_id: str | None = None, limit: int = 5, user=Depends(get_current_user)):
    return _build_pump_failure_analytics(user["id"], device_id, limit)


@app.post("/auth/signup")
def signup(data: SignupRequest):
    user_service.create_user(_auth_identifier(data.username, data.email), data.password, data.name)
    return {"message": "User created"}


@app.post("/auth/login", response_model=TokenResponse)
def login(data: LoginRequest):
    user = user_service.get_user(_auth_identifier(data.username, data.email))
    if not user:
        raise HTTPException(401, "Invalid credentials")

    user_id, _, hashed_pw = user
    if not user_service.verify_password(data.password, hashed_pw):
        raise HTTPException(401, "Invalid credentials")

    token = JWTService.create_token(user_id)
    return {"access_token": token}
