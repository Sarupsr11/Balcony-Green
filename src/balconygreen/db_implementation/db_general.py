# balconygreen/db_implementation/db_general.py
import os
from sqlalchemy import create_engine # type: ignore
from sqlalchemy.orm import sessionmaker # type: ignore
from balconygreen.db_implementation.schema.init import Base

# ----------------------
# 1️⃣ Get DATABASE_URL from Railway env
# ----------------------
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise RuntimeError("DATABASE_URL is not set! Make sure you added the PostgreSQL plugin on Railway.")

# ----------------------
# 2️⃣ Create SQLAlchemy Engine
# ----------------------
# For PostgreSQL on Railway, SSL is required
connect_args = {"sslmode": "require"} if DATABASE_URL.startswith("postgresql") else {}

engine = create_engine(DATABASE_URL, pool_pre_ping=True, connect_args=connect_args)

# ----------------------
# 3️⃣ Create Session Factory
# ----------------------
SessionLocal = sessionmaker(bind=engine, autocommit=False, autoflush=False)

# ----------------------
# 4️⃣ Auto-create tables
# ----------------------
def init_db():
    """Call once to ensure all tables exist."""
    Base.metadata.create_all(bind=engine)
    print("✅ All tables are created and ready.")

# Optional: automatically initialize tables on import
init_db()