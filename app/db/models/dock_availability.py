from sqlalchemy import Column, Integer, String, Boolean, TIMESTAMP, text
from sqlalchemy.dialects.postgresql import TIMESTAMP as PG_TIMESTAMP
from sqlalchemy.sql import func
from sqlalchemy.orm import declarative_base
from app.db.base import Base

class DockAvailability(Base):
    __tablename__ = "export_dock_availability"

    id = Column(Integer, primary_key=True, index=True)
    dock_no = Column(String(50), unique=True, nullable=False, index=True)
    dock_in_time = Column(PG_TIMESTAMP(timezone=True), nullable=True)
    is_dock_occupied = Column(Boolean, nullable=False, server_default="false")
    created_at = Column(
        TIMESTAMP(timezone=True), 
        server_default=func.now(), 
        nullable=False
    )
    updated_at = Column(
        TIMESTAMP(timezone=True), 
        server_default=func.now(), 
        onupdate=func.now(), 
        nullable=False
    )

    