# app/db/models/importOperation/gp_mismatch_log.py
from sqlalchemy import (
    Boolean, Column, Integer, String, DateTime, ForeignKey, UniqueConstraint, Index
)
from app.db.base import Base


class ImportGpMismatchLog(Base):
    __tablename__ = "import_gp_mismatch_log"

    id = Column(Integer, primary_key=True, autoincrement=True)

    assignment_header_id = Column(
        Integer,
        ForeignKey("import_worker_assignment_header.id", ondelete="CASCADE"),
        nullable=True,
        index=True
    )

    awb_no = Column(String(30), nullable=False)
    hawb = Column(String(50), nullable=True)

    existing_gate_pass = Column(String(200), nullable=True)
    incoming_gate_pass = Column(String(200), nullable=True)

    # dates if available
    gp_issued_datetime  = Column(DateTime(timezone=True), nullable=True)  # gp_combo
    integrate_date_time = Column(DateTime(timezone=True), nullable=True)  # OC integrate time

    created_at = Column(DateTime(timezone=True), nullable=False)

        # 🆕 COMPLETION TRACKING
    is_complete   = Column(Boolean, nullable=False, server_default="false")
    # completed_by  = Column(
    #     Integer,
    #     ForeignKey("users.id", ondelete="SET NULL"),  # adjust table name to your users table
    #     nullable=True
    # )

    completed_by = Column(String(20),nullable=True)
    completed_at  = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        UniqueConstraint(
            "awb_no",
            "existing_gate_pass",
            "incoming_gate_pass",
            name="uq_gp_mismatch_awb_existing_incoming"
        ),
        Index("idx_gp_mismatch_awb", "awb_no"),
    )