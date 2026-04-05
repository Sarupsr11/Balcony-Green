import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, DateTime # type: ignore
from balconygreen.db_implementation.schema.init import Base # type: ignore
from sqlalchemy.dialects.postgresql import UUID  # type: ignore # Postgres-specific

class User(Base):
    __tablename__ = "users"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    email = Column(String(120), unique=True, nullable=False)
    name = Column(String(100))
    password_hash = Column(String(255), nullable=False)
    created_at = Column(DateTime, default=datetime.now(timezone.utc))
