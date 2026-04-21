import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, Boolean, DateTime, ForeignKey # type: ignore
from sqlalchemy.orm import relationship # type: ignore
from balconygreen.db_implementation.schema.init import Base # type: ignore

class Device(Base):
    __tablename__ = "devices"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    device_name = Column(String(100), nullable=False)
    device_ip = Column(String(45))
    device_key = Column(String(255), unique=True, nullable=False)
    device_type = Column(String(50), default="physical")
    city = Column(String(100))
    is_active = Column(Boolean, default=True)
    last_seen = Column(DateTime(timezone=True))
    created_at = Column(DateTime(timezone=True))

    owner = relationship("User", backref="devices")

    sensors = relationship(
        "Sensor",
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True
    )

    readings = relationship(
        "Reading",
        back_populates="device",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    
    images = relationship("Image", back_populates="device", cascade="all, delete-orphan",
                          passive_deletes = True)

