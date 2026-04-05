from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey, Index, Text # type: ignore
from sqlalchemy.orm import relationship # type: ignore
from balconygreen.db_implementation.schema.init import Base

class Image(Base):
    __tablename__ = "images"

    id = Column(Integer, primary_key=True, autoincrement=True)

    device_id = Column(
        String(36),
        ForeignKey("devices.id", ondelete="CASCADE"),
        nullable=False
    )

    sensor_id = Column(
        String(36),
        ForeignKey("sensors.id", ondelete="CASCADE"),
        nullable=False
    )

    image_path = Column(String(255), nullable=False)
    source = Column(String(50))
    timestamp = Column(DateTime(timezone=True), default=datetime.now(timezone.utc))
    prediction = Column(Text, nullable=True)

    device = relationship("Device", back_populates="images")
    sensor = relationship("Sensor", back_populates="images")


# Indexes (same philosophy as Reading)
Index("idx_images_device", Image.device_id)
Index("idx_images_sensor", Image.sensor_id)
Index("idx_images_timestamp", Image.timestamp)
