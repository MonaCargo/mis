from sqlalchemy import JSON, Column, DateTime, Index, Integer, String, Text

from app.db.base import Base


class ExportOperationCarMessageFlowAuditLog(Base):
    __tablename__ = "export_operation_car_message_flow_audit_log"

    __table_args__ = (
        Index("idx_car_flow_audit_module", "module"),
        Index("idx_car_flow_audit_record", "module", "record_id"),
        Index("idx_car_flow_audit_emp", "performed_by"),
        Index("idx_car_flow_audit_created", "created_at"),
        Index("idx_car_flow_audit_awb", "awb_reference_id", "flow_step"),
        Index("idx_car_flow_audit_flight", "flight_reference_id", "flow_step"),
        Index("idx_car_flow_audit_action", "module", "action"),
    )

    id = Column(Integer, primary_key=True)

    awb_reference_id = Column(Integer, nullable=False)
    flight_reference_id = Column(Integer, nullable=True)

    module = Column(String(50), nullable=False)
    # e.g. "FLIGHT_BOOKING"

    record_id = Column(Integer, nullable=False)

    action = Column(String(20), nullable=False)
    # "CREATE" | "UPDATE" | "DELETE"

    # ✅ fixed string code — never integer, never reorderable
    flow_step = Column(String(30), nullable=False)
    # e.g. "STEP_FLIGHT_BOOKING" — permanent, immutable

    changes = Column(JSON, nullable=True)
    performed_by = Column(String(20), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)
    note = Column(Text, nullable=True)