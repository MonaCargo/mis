# app/services/worker_assignment_audit_service.py

from app.db.models.importOperation.audit_log_worker_assignment import WorkerAssignmentAuditLog
from app.utils.common.helperFunction import get_utc_now

async def log_worker_assignment_audit(
    db,
    *,
    assignment,
    field_name: str,
    old_value,
    new_value,
    changed_by: str,
    changed_by_role: str,          # ✅
    ip_address: str | None,
    user_agent:str | None,
    device_id:str |None,
    db_action: str,
    source_action: str,
):
    db.add(
        WorkerAssignmentAuditLog(
            worker_assignment_id=assignment.id,
            oc_no=assignment.oc_no,
            awb_no=assignment.awb_no,
            hawb=assignment.hawb,

            field_name=field_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,

            db_action=db_action,
            source_action=source_action,

            device_id=device_id,

            changed_by=changed_by,
            changed_by_role=changed_by_role,
            user_agent =user_agent,
            ip_address=ip_address,
            changed_at = get_utc_now(),
            created_at = get_utc_now(),
            
        )
    )
