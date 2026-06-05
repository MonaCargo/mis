from sqlalchemy import (
    Boolean, Column, ForeignKey, Index, Integer, String, DateTime, Numeric, Text, UniqueConstraint, text
)
from sqlalchemy.orm import relationship
from app.db.base import Base
from sqlalchemy.dialects.postgresql import JSONB


# 0) Staging Table
class ImportTruckInStaging(Base):
    __tablename__ = "import_truck_in_staging"

    id = Column(Integer, primary_key=True, index=True)
    session_id = Column(String, nullable=False)
    truck_number = Column(String, nullable=False)
    driver_name = Column(String, nullable=True)
    driver_contact = Column(String, nullable=True)
    gate_pass_no = Column(String, nullable=False)
    added_time = Column(DateTime(timezone=True), server_default=text("NOW()"))


# 1) Truck Visit
class ImportTruckVisit(Base):
    __tablename__ = "import_truck_visit"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    warehouse = Column(String, nullable=False)
    zone = Column(String, nullable=False)
    visit_type = Column(String(20), nullable=False, default="TRUCK", index=True)
    token_no = Column(String, nullable=True)
    truck_number = Column(String, nullable=True)
    driver_name = Column(String, nullable=True)
    driver_contact = Column(String, nullable=True)
    status = Column(String, nullable=True)  # I=IN, O=OUT, C=Closed
    remarks = Column(String, nullable=True)

    truck_slot_from = Column(DateTime(timezone=True), nullable=False)
    truck_in_date_time = Column(DateTime(timezone=True))
    truck_out_date_time = Column(DateTime(timezone=True))
    is_truck_in = Column(Boolean, default=False)
    is_truck_out = Column(Boolean, default=False)
    truck_in_by = Column(String)
    truck_out_by = Column(String)
    truck_in_device = Column(String, nullable=True, default=None)
    truck_out_device = Column(String, nullable=True, default=None)

    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))


    # In ImportTruckVisit class, after existing columns:
    queue_no        = Column(String, nullable=True,index=True)
    queued_at       = Column(DateTime(timezone=True), nullable=True)
    queued_by       = Column(String, nullable=True)
    queued_device   = Column(String, nullable=True)

    # In ImportTruckVisit, after queued fields:
    charges_cleared     = Column(Boolean, default=False, nullable=False)
    charges_cleared_by  = Column(String, nullable=True)
    charges_cleared_at  = Column(DateTime(timezone=True), nullable=True)

    gate_passes = relationship("ImportGatePassAssignment", back_populates="truck_visit", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_import_token_truckslot_trucknumber', 'token_no', 'truck_slot_from', 'truck_number'),
    )


# 2) Gate Pass Master
class ImportGatePass(Base):
    __tablename__ = "import_gate_pass"

    id = Column(Integer, primary_key=True, index=True)
    worker_assignment_shipment_id = Column(
    Integer,
    ForeignKey("import_worker_assignment_shipment.id", ondelete="SET NULL"),
    nullable=True,
    index=True
)
    Final_delivery_time = Column(DateTime(timezone=True), nullable=True)
    drop_dlv_zone = Column(String, nullable=True)

    
    gate_pass_no = Column(String, unique=True, nullable=False)
    issued_date = Column(DateTime(timezone=True), nullable=False)
    agent = Column(String, nullable=True)
    consignee = Column(String, nullable=True)
    gate_pass_release_by = Column(String, nullable=True)
    gate_pass_released_time = Column(DateTime(timezone=True), nullable=True)
    gate_pass_Out_device = Column(String, nullable=True, default=None)
    gate_pass_out_date_time = Column(DateTime(timezone=True), nullable=True)
    gate_pass_out_by = Column(String, nullable=True)
    awb_no = Column(String, nullable=True)   # Air Waybill number
    hawb_no = Column(String, nullable=True)  # House Air Waybill number
    pcs_total = Column(Integer, nullable=False)
    pcs_remaining = Column(Integer, nullable=False)
    gross_wt_total = Column(Numeric(12,3), nullable=False)
    status = Column(String, default="A")  # A=Active, C=Closed
    remarks = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))

    assignments = relationship("ImportGatePassAssignment", back_populates="gate_pass", cascade="all, delete-orphan")
    loadings = relationship("ImportGatePassLoading", back_populates="gate_pass", cascade="all, delete-orphan")


# 3) Gate Pass Assignment
class ImportGatePassAssignment(Base):
    __tablename__ = "import_gate_pass_assignment"

    id = Column(Integer, primary_key=True, index=True)
    gate_pass_id = Column(Integer, ForeignKey("import_gate_pass.id", ondelete="CASCADE"))
    truck_visit_id = Column(Integer, ForeignKey("import_truck_visit.id", ondelete="CASCADE"))
    assigned_by = Column(String, nullable=False)
    assigned_time = Column(DateTime(timezone=True), server_default=text("NOW()"))
    is_active = Column(Boolean, default=True)  # ✅ ADD THIS
    remarks = Column(String, nullable=True)

    gate_pass = relationship("ImportGatePass", back_populates="assignments")
    truck_visit = relationship("ImportTruckVisit", back_populates="gate_passes")

    # ── NEW: storage charge fields (per GP per visit) ──
    storage_charge  = Column(Numeric(12, 2), nullable=True)   # ₹, up to 2 decimals
    challan_no      = Column(String(100), nullable=True)
    charge_remarks  = Column(Text, nullable=True)
    charge_by       = Column(String(20), nullable=True)       # who entered it
    charge_at       = Column(DateTime(timezone=True), nullable=True)

    __table_args__ = (
        Index('idx_gatepass_assignment', 'gate_pass_id', 'truck_visit_id'),
         UniqueConstraint(
            "gate_pass_id", "truck_visit_id",
            name="uq_gp_assignment_per_visit"
        ),
    )


# 4) Gate Pass Loading
class ImportGatePassLoading(Base):
    __tablename__ = "import_gate_pass_loading"

    id = Column(Integer, primary_key=True, index=True)
    gate_pass_id = Column(Integer, ForeignKey("import_gate_pass.id", ondelete="CASCADE"))
    truck_visit_id = Column(Integer, ForeignKey("import_truck_visit.id", ondelete="CASCADE"))
    loaded_pcs = Column(Integer, nullable=False)
    loaded_by = Column(String, nullable=False)
    loaded_time = Column(DateTime(timezone=True), server_default=text("NOW()"))
    remarks = Column(String, nullable=True)

    gate_pass = relationship("ImportGatePass", back_populates="loadings")
    truck_visit = relationship("ImportTruckVisit")




class ImportTruckInOutActivityLog(Base):
    __tablename__ = "import_truck_in_out_activity_log"

    id              = Column(Integer, primary_key=True, index=True)

    # ── What happened ────────────────────────────────────────────────────────
    event_type      = Column(String(50), nullable=False, index=True)
    # Examples:
    # TRUCK_QUEUED, QUEUE_CANCELLED, QUEUE_PROMOTED,
    # TRUCK_IN, TRUCK_OUT,
    # GP_STAGED, GP_STAGING_REMOVED, GP_ASSIGNED, GP_REASSIGNED,
    # GP_LOADED, GP_LOADING_CORRECTED, GP_VOIDED,
    # MORE_GP_ADDED, GP_ASSIGNMENT_DEACTIVATED,
    # CONFIG_CHANGED, ...

    # ── What was affected ────────────────────────────────────────────────────
    entity_type     = Column(String(50), nullable=False, index=True)
    # truck_visit | gate_pass | gp_assignment | gp_loading | staging | queue
    entity_id       = Column(Integer, nullable=True, index=True)
    # Primary key of the affected row (truck_visit.id, gate_pass.id, etc.)

    # ── Cross-references for fast tracing ────────────────────────────────────
    truck_visit_id  = Column(Integer, nullable=True, index=True)
    gate_pass_no    = Column(String(100), nullable=True, index=True)
    truck_number    = Column(String(50), nullable=True, index=True)
    queue_no        = Column(String(50), nullable=True, index=True)
    token_no        = Column(String(50), nullable=True)

    # ── What changed ─────────────────────────────────────────────────────────
    changes         = Column(JSONB, nullable=True)
    # Example: {"pcs_remaining": {"old": 10, "new": 4}, "status": {"old": "A", "new": "C"}}
    snapshot_before = Column(JSONB, nullable=True)
    # Full state of the entity before the change
    snapshot_after  = Column(JSONB, nullable=True)
    # Full state of the entity after the change

    # ── Context ──────────────────────────────────────────────────────────────
    description     = Column(Text, nullable=True)
    # Human-readable: "Truck DL01AB1234 promoted from queue Q123456001 to truck IN. Token: M2026053001."
    reason          = Column(Text, nullable=True)
    # Optional user-supplied reason for correction/cancellation/etc.

    # ── Who & when & where ───────────────────────────────────────────────────
    performed_by    = Column(String(100), nullable=False)
    # emp_id of the operator
    performed_by_role = Column(String(50), nullable=True)
    # "OPERATOR" | "ADMIN" | "SYSTEM"
    device_id       = Column(String(100), nullable=True)
    ip_address      = Column(String(50), nullable=True)
    request_id      = Column(String(50), nullable=True)
    # Optional: correlation ID for tracing related events from one request

    created_at      = Column(DateTime(timezone=True), server_default=text("NOW()"), index=True)

    __table_args__ = (
        Index("idx_activity_truck_event", "truck_visit_id", "event_type"),
        Index("idx_activity_gp_event",    "gate_pass_no", "event_type"),
        Index("idx_activity_created_desc", "created_at"),
    )