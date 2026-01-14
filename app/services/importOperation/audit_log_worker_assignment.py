# # app/services/worker_assignment_audit_service.py

# from app.db.models.importOperation.audit_log_worker_assignment import WorkerAssignmentAuditLog
# from app.utils.common.helperFunction import get_utc_now

# async def log_worker_assignment_audit(
#     db,
#     *,
#     assignment,
#     field_name: str,
#     old_value,
#     new_value,
#     changed_by: str,
#     changed_by_role: str,          # ✅
#     ip_address: str | None,
#     user_agent:str | None,
#     device_id:str |None,
#     db_action: str,
#     source_action: str,
# ):
#     db.add(
#         WorkerAssignmentAuditLog(
#             worker_assignment_id=assignment.id,
#             oc_no=assignment.oc_no,
#             awb_no=assignment.awb_no,
#             hawb=assignment.hawb,

#             field_name=field_name,
#             old_value=str(old_value) if old_value is not None else None,
#             new_value=str(new_value) if new_value is not None else None,

#             db_action=db_action,
#             source_action=source_action,

#             device_id=device_id,

#             changed_by=changed_by,
#             changed_by_role=changed_by_role,
#             user_agent =user_agent,
#             ip_address=ip_address,
#             changed_at = get_utc_now(),
#             created_at = get_utc_now(),
            
#         )
#     )



# ===================== New structure two level ============================



from app.db.models.importOperation.audit_log_worker_assignment import WorkerAssignmentAuditLog
from app.db.models.importOperation.worker_assignment import WorkerAssignmentHeader, WorkerAssignmentShipment
from app.utils.common.helperFunction import get_utc_now
from sqlalchemy.ext.asyncio import AsyncSession


async def log_worker_assignment_audit(
    db: AsyncSession,
    header: WorkerAssignmentHeader,
    shipment: WorkerAssignmentShipment,
    field_name: str,
    old_value: str | None,
    new_value: str | None,
    changed_by: str,
    changed_by_role: str,
    device_id: str | None,
    user_agent: str | None,
    ip_address: str | None,
    db_action: str,
    source_action: str,
):
    now = get_utc_now()

    audit_entry = WorkerAssignmentAuditLog(
        header_id=header.id,
        shipment_id=shipment.id,

        oc_no=header.oc_no,
        awb_no=header.awb_no,
        hawb=header.hawb,
        gate_pass_no=shipment.gate_pass_no,

        field_name=field_name,
        old_value=str(old_value) if old_value is not None else None,
        new_value=str(new_value) if new_value is not None else None,

        db_action=db_action,
        source_action=source_action,

        changed_by=changed_by,
        changed_by_role=changed_by_role,
        ip_address=ip_address,
        device_id=device_id,
        user_agent=user_agent,

        changed_at=now,
        created_at=now,
    )

    db.add(audit_entry)

