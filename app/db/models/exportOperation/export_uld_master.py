# models/export_uld_master.py

from sqlalchemy import (
    Column,
    Integer,
    String,
    Boolean,
    DateTime,
    Index
)
from app.db.base import Base


class ExportUldMaster(Base):
    __tablename__ = "export_uld_master"

    __table_args__ = (
        Index("idx_export_uld_no", "uld_no"),
        Index("idx_export_carrier", "carrier"),
    )

    id = Column(Integer, primary_key=True)

    # 🔹 ULD number (e.g., AKE12345AI)
    uld_no = Column(String(25), unique=True, nullable=False)

    # 🔹 Airline / Carrier code (AI, LH, EK, etc.)
    carrier = Column(String(20), nullable=False)

    # 🔹 Active / inactive ULD
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    created_by = Column(String(20), nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False
    )