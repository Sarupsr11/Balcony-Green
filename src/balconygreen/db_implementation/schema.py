# schema.py

SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
        id TEXT PRIMARY KEY,              -- UUID
        email TEXT UNIQUE NOT NULL,
        name TEXT,
        password_hash TEXT NOT NULL,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS devices (
        id TEXT PRIMARY KEY,              -- UUID
        user_id TEXT NOT NULL,             -- owner user
        device_name TEXT NOT NULL,
        device_ip TEXT,
        device_key TEXT UNIQUE NOT NULL,   -- device authentication secret
        device_type TEXT DEFAULT 'physical',  -- physical | weather_api
        city TEXT,                         -- for weather API devices
        is_active BOOLEAN DEFAULT 1,
        last_seen DATETIME,
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS sensors (
        id TEXT PRIMARY KEY,               -- UUID
        device_id TEXT NOT NULL,
        sensor_name TEXT NOT NULL,          -- temperature, humidity, camera
        sensor_type TEXT NOT NULL,          -- environment | camera | weather_api
        unit TEXT,                          -- °C, %, hPa
        created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (device_id) REFERENCES devices(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS readings (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        device_id TEXT NOT NULL,
        sensor_id TEXT NOT NULL,
        value REAL NOT NULL,
        source TEXT,                        -- sensor | weather_api
        timestamp DATETIME NOT NULL,
        FOREIGN KEY (device_id) REFERENCES devices(id) ON DELETE CASCADE,
        FOREIGN KEY (sensor_id) REFERENCES sensors(id) ON DELETE CASCADE
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS images (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        sensor_id TEXT NOT NULL,
        image_path TEXT NOT NULL,
        source TEXT,                        -- camera | upload | api
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (sensor_id) REFERENCES sensors(id)
    );
    """,
    """
    CREATE TABLE IF NOT EXISTS uploads (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        user_id TEXT NOT NULL,
        file_path TEXT NOT NULL,
        file_type TEXT,                     -- image/jpeg, image/png
        timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
        FOREIGN KEY (user_id) REFERENCES users(id)
    );
    """,
    # =========================
    # INDEXES (IMPORTANT)
    # =========================
    """
    CREATE INDEX IF NOT EXISTS idx_readings_device
    ON readings(device_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_readings_sensor
    ON readings(sensor_id);
    """,
    """
    CREATE INDEX IF NOT EXISTS idx_readings_timestamp
    ON readings(timestamp);
    """,
]
