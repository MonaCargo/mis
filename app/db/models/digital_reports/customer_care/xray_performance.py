from sqlalchemy import (
    Column, Integer, String, Numeric, Date, DateTime,
    func, UniqueConstraint, Index
)
from sqlalchemy.dialects.postgresql import JSONB
from app.db.base import Base


class DigitalReportXRayPerformance(Base):
    __tablename__ = 'dr_xray_performance'

    id = Column(Integer, primary_key=True, autoincrement=True)
    report_month = Column(String(50), nullable=True)  # Format: YYYY-MM
    report_daily = Column(Date, nullable=True)  # Format: YYYY-MM-DD  (In IST format not utc)
    period_type = Column(String(20), nullable=False, default='monthly')  # e.g., 'monthly', 'daily'
    machine_code = Column(String(50), nullable=False)
    machine_name = Column(String(100), nullable=False, default='')
    pcs_count = Column(Integer, nullable=False, default=0)
    grs_weight = Column(Numeric(12, 2), nullable=False, default=0.00)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    __table_args__ = (
        Index('ix_dr_xray_report_month', 'report_month'),
        Index('ix_dr_xray_machine_code', 'machine_code'),
    )