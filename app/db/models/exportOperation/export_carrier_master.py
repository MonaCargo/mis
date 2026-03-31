
from sqlalchemy import Boolean, Column, DateTime, ForeignKey, Index, Integer, String, UniqueConstraint

from app.db.base import Base
from sqlalchemy.orm import relationship

class ExportCarrierMaster(Base):
    __tablename__ = "export_carrier_master"

    __table_args__ = (
        UniqueConstraint("carrier_code", name="uq_carrier_code"),
        Index("idx_carrier_code", "carrier_code"),
    )

    id = Column(Integer, primary_key=True)
    carrier_code = Column(String(10), nullable=False)   # e.g. "AI", "EK", "3G"
    name = Column(String(200), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(String(20), nullable=True)

    pfx_list = relationship("ExportCarrierPfx", backref="carrier")




class ExportCarrierPfx(Base):
    __tablename__ = "export_carrier_pfx"

    __table_args__ = (
        UniqueConstraint("carrier_master_id", "pfx", name="uq_carrier_pfx"),
        Index("idx_carrier_pfx", "pfx"),
    )

    id = Column(Integer, primary_key=True)

    carrier_master_id = Column(          # ✅ integer FK to id
        Integer,
        ForeignKey("export_carrier_master.id"),
        nullable=False,
    )

    pfx = Column(String(10), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)