

from sqlalchemy import Column, DateTime, Index, Integer, String, UniqueConstraint

from app.db.base import Base


class ExportBaseMaster(Base):
    __tablename__ = "export_base_master"

    __table_args__ = (
        UniqueConstraint("base_name", name="uq_uld_base_name"),
        Index("idx_uld_base_name", "base_name"),
    )

    id = Column(Integer, primary_key=True)
    base_name = Column(String(50), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
    created_by = Column(String(20), nullable=True)
