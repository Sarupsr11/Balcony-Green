# schema.py
SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )

    """,
    """
    CREATE TABLE IF NOT EXISTS sensors (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    sensor_name TEXT NOT NULL,
    sensor_type TEXT NOT NULL,
    device_info TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
    )

    """,
    """
    CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    device_id TEXT,
    sensor_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,
    source TEXT,
    timestamp DATETIME NOT NULL,
    FOREIGN KEY (user_id) REFERENCES users(id)
    )

    """,
    """
    CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT,
    image_path TEXT NOT NULL,
    source TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sensor_id) REFERENCES sensors(id)
    )

    """,
    """
    CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT,
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS device_commands (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    command_type TEXT NOT NULL,
    payload_json TEXT NOT NULL,
    status TEXT NOT NULL DEFAULT 'queued',
    device_message TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    delivered_at DATETIME,
    acknowledged_at DATETIME,
    FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS soil_sensor_calibrations (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_id TEXT NOT NULL,
    plant_type TEXT NOT NULL,
    soil_raw_dry INTEGER NOT NULL,
    soil_raw_wet INTEGER NOT NULL,
    moisture_target_pct REAL NOT NULL,
    pump_flow_ml_per_sec REAL,
    failure_min_rise_pct REAL NOT NULL DEFAULT 2.0,
    failure_window_minutes INTEGER NOT NULL DEFAULT 45,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS watering_feedback (
    id TEXT PRIMARY KEY,
    user_id TEXT NOT NULL,
    device_id TEXT,
    plant_type TEXT NOT NULL,
    command_id TEXT,
    feedback_label TEXT NOT NULL,
    notes TEXT,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """,
]
