# models/location.py

from sqlalchemy import Boolean, Column, Index, Integer, String, UniqueConstraint, DateTime

from app.db.base import Base

class ExportLocationsMaster(Base):
    __tablename__ = "export_locations_master"

    id = Column(Integer, primary_key=True, index=True)
    ops_type = Column(String(50), nullable=False)
    area_code = Column(String(10), nullable=False)
    loc = Column(String(50), nullable=False)
    is_active = Column(Boolean, nullable=False, default=True)
    created_at = Column(DateTime(timezone=True),nullable=False)
    

    __table_args__ = (
        UniqueConstraint("loc", name="uq_location"),
       Index("ix_export_location", "loc"),
    )