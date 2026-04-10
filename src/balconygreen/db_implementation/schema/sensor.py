import uuid
from datetime import datetime, timezone
from sqlalchemy import Column, String, ForeignKey, DateTime # type: ignore
from sqlalchemy.orm import relationship # type: ignore
from balconygreen.db_implementation.schema.init import Base # type: ignore

class Sensor(Base):
    __tablename__ = "sensors"

    id = Column(String(36), primary_key=True, default=lambda: str(uuid.uuid4()))
    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    sensor_name = Column(String(100), nullable=False)
    unit = Column(String(20))
    created_at = Column(DateTime(timezone=True))

    device = relationship("Device", back_populates="sensors")

    readings = relationship(
        "Reading",
        back_populates="sensor",
        cascade="all, delete-orphan",
        passive_deletes=True
    )
    images = relationship("Image", back_populates="sensor", cascade="all, delete-orphan", passive_deletes = True)

