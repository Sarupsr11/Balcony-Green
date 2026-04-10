from datetime import datetime
from sqlalchemy import Column, Integer, String, Float, DateTime, ForeignKey, Index # type: ignore
from sqlalchemy.orm import relationship # type: ignore
from balconygreen.db_implementation.schema.init import Base

class Reading(Base):
    __tablename__ = "readings"

    id = Column(Integer, primary_key=True, autoincrement=True)
    device_id = Column(String(36), ForeignKey("devices.id", ondelete="CASCADE"), nullable=False)
    sensor_id = Column(String(36), ForeignKey("sensors.id", ondelete="CASCADE"), nullable=False)
    value = Column(Float, nullable=False)
    sensor_name = Column(String(50))
    timestamp = Column(DateTime(timezone=True))

    device = relationship("Device", back_populates="readings")
    sensor = relationship("Sensor", back_populates="readings")


# Indexes
Index("idx_readings_device", Reading.device_id)
Index("idx_readings_sensor", Reading.sensor_id)
Index("idx_readings_timestamp", Reading.timestamp)
