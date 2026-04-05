# balconygreen/db_implementation/db_general.py
import os
import time
from urllib.parse import urlparse
from sqlalchemy import create_engine # type: ignore
from sqlalchemy.orm import sessionmaker, declarative_base # type: ignore

# Import your Base for table creation
from balconygreen.db_implementation.schema.init import Base

from dotenv import load_dotenv # type: ignore
import os


DATABASE_URL = os.getenv("DATABASE_URL")

if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set!")

# ----------------------
# Step 1: Ensure Postgres DB exists (if using Postgres)
# ----------------------
if DATABASE_URL.startswith("postgresql"):
    import psycopg2 # type: ignore
    from psycopg2.extensions import ISOLATION_LEVEL_AUTOCOMMIT # type: ignore

    url = urlparse(DATABASE_URL)
    POSTGRES_USER = url.username
    POSTGRES_PASSWORD = url.password
    POSTGRES_DB = url.path[1:]  # strip leading '/'
    POSTGRES_HOST = url.hostname
    POSTGRES_PORT = url.port or 5432

    # Try connecting to Postgres and create DB if missing
    for attempt in range(3):
        try:
            conn = psycopg2.connect(
                dbname="postgres",
                user=POSTGRES_USER,
                password=POSTGRES_PASSWORD,
                host=POSTGRES_HOST,
                port=POSTGRES_PORT,
            )
            conn.set_isolation_level(ISOLATION_LEVEL_AUTOCOMMIT)
            cur = conn.cursor()
            cur.execute(f"SELECT 1 FROM pg_database WHERE datname='{POSTGRES_DB}'")
            if not cur.fetchone():
                print(f"Database '{POSTGRES_DB}' not found. Creating...")
                cur.execute(f"CREATE DATABASE {POSTGRES_DB}")
                print(f"Database '{POSTGRES_DB}' created successfully.")
            cur.close()
            conn.close()
            break
        except psycopg2.OperationalError as e:
            print(f"Attempt {attempt + 1}: Could not connect to Postgres. Retrying in 3s...")
            time.sleep(3)
        except Exception as e:
            print("Error ensuring database exists:", e)
            raise

# ----------------------
# Step 2: SQLAlchemy Engine
# ----------------------
connect_args = {"check_same_thread": False} if DATABASE_URL.startswith("sqlite") else {}
engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)

# ----------------------
# Step 3: Session Factory
# ----------------------
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# ----------------------
# Step 4: Auto-create tables
# ----------------------
def init_db():
    """Call this once to ensure all tables exist."""
    Base.metadata.create_all(bind=engine)
    print("All tables are created and ready.")

# Optional: automatically initialize tables on import
init_db()
