# utils/audit.py

from app.db.models.exportOperation.car_message_flow_audit_log import ExportOperationCarMessageFlowAuditLog
from app.utils.common.helperFunction import get_utc_now
from sqlalchemy.ext.asyncio import AsyncSession

async def write_car_message_flow_audit(
    db: AsyncSession,
    awb_reference_id: int,
    module: str,
    flow_step: str,                      # ← string now
    record_id: int,
    action: str,
    performed_by: str,
    flight_reference_id: int | None = None,
    changes: dict | None = None,
    note: str | None = None,
):
    log = ExportOperationCarMessageFlowAuditLog(
        awb_reference_id=awb_reference_id,
        flight_reference_id=flight_reference_id,
        module=module,
        flow_step=flow_step,             # ← stored as "STEP_FLIGHT_BOOKING"
        record_id=record_id,
        action=action,
        changes=changes,
        performed_by=performed_by,
        created_at=get_utc_now(),
        note=note,
    )
    db.add(log)



      # commits header + details + logs together