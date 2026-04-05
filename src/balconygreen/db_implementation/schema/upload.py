from datetime import datetime, timezone
from sqlalchemy import Column, Integer, String, DateTime, ForeignKey # type: ignore
from sqlalchemy.orm import relationship # type: ignore
from balconygreen.db_implementation.schema.init import Base # type: ignore

class Upload(Base):
    __tablename__ = "uploads"

    id = Column(Integer, primary_key=True, autoincrement=True)
    user_id = Column(String(36), ForeignKey("users.id"), nullable=False)
    file_path = Column(String(255), nullable=False)
    file_type = Column(String(50))
    timestamp = Column(DateTime, default=datetime.now(timezone.utc))

    user = relationship("User", backref="uploads")
