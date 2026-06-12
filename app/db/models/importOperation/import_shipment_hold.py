
from sqlalchemy import (
    Column, Integer, String, DateTime, Boolean, Text,
    ForeignKey, Index
)
from app.db.base import Base


class ImportShipmentHold(Base):
    __tablename__ = "import_shipment_hold"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ===============================
    # HOLD IDENTITY (how the user placed it)
    # ===============================
    # one of: AWB_HAWB / OC / BOE / GP
    hold_type = Column(String(20), nullable=False, index=True)

    # filled according to hold_type (others stay NULL)
    awb_no = Column(String(30), nullable=True, index=True)
    hawb = Column(String(50), nullable=True)            # may be NULL even for AWB_HAWB
    oc_no = Column(String(50), nullable=True, index=True)
    boe_no = Column(String(100), nullable=True, index=True)
    gate_pass_no = Column(String(200), nullable=True, index=True)

    # ===============================
    # RESOLVED LINK (cached if shipment already exists)
    # ===============================
    # nullable: hold may be placed before the pipeline creates the row it mainly used in case of GP no.
    assignment_header_id = Column(
        Integer,
        ForeignKey("import_worker_assignment_header.id", ondelete="SET NULL"),
        nullable=True,
        index=True
    )

    # ===============================
    # HOLD STATE
    # ===============================
    is_active = Column(Boolean, default=True, nullable=False, index=True)
    reason = Column(Text, nullable=True)

    held_by = Column(String(20), nullable=True)          # emp_id
    held_datetime = Column(DateTime(timezone=True), nullable=True)

    released_by = Column(String(20), nullable=True)      # emp_id (release audit)
    released_datetime = Column(DateTime(timezone=True), nullable=True)
    release_reason = Column(Text, nullable=True)

    # ===============================
    # AUDIT
    # ===============================
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # fast "any active hold matching this identifier?" lookups
        Index("idx_hold_active_awb", "is_active", "awb_no"),
        Index("idx_hold_active_oc", "is_active", "oc_no"),
        Index("idx_hold_active_boe", "is_active", "boe_no"),
        Index("idx_hold_active_gp", "is_active", "gate_pass_no"),
        Index("idx_hold_active_header", "is_active", "assignment_header_id"),
    )