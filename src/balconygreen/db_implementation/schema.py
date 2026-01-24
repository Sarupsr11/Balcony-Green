# schema.py
SCHEMA_SQL = [
    """
    CREATE TABLE IF NOT EXISTS users (
    id TEXT PRIMARY KEY,              -- UUID
    email TEXT UNIQUE NOT NULL,
    name TEXT,
    password_hash TEXT NOT NULL,
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )

    """,

    """
    CREATE TABLE IF NOT EXISTS sensors (
    id TEXT PRIMARY KEY,               -- UUID
    user_id TEXT NOT NULL,
    sensor_name TEXT NOT NULL,          -- "Temperature", "Humidity"
    sensor_type TEXT NOT NULL,          -- "environment", "camera", "weather_api"
    created_at DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
    )

    """,

    """
    CREATE TABLE IF NOT EXISTS readings (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_name TEXT NOT NULL,
    value REAL NOT NULL,
    unit TEXT,                          -- °C, %, hPa
    source TEXT,                        -- sensor | weather_api
    timestamp DATETIME NOT NULL
    )

    """,

    """
    CREATE TABLE IF NOT EXISTS images (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    sensor_id TEXT,
    image_path TEXT NOT NULL,
    source TEXT,                        -- camera | upload | api
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (sensor_id) REFERENCES sensors(id)
    )

    """,

    """
    CREATE TABLE IF NOT EXISTS uploads (
    id INTEGER PRIMARY KEY AUTOINCREMENT,
    user_id TEXT NOT NULL,
    file_path TEXT NOT NULL,
    file_type TEXT,                     -- image/jpeg, image/png
    timestamp DATETIME DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (user_id) REFERENCES users(id)
    )
    """
]
