


from fastapi import APIRouter, Depends
from numpy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.importOperation.audit_log_worker_assignment import WorkerAssignmentAuditLog
from app.db.session import get_db


from app.db.models.user import User

router = APIRouter(prefix="/logs", tags=[""])





def get_event_title(field_name: str, source_action: str) -> str:
    mapping = {
        "drop_dlv_zone": "Delivery Zone Updated",
        "assign_worker": "Worker Assigned",
        "release_zone": "Release Zone Updated"
    }
    return mapping.get(field_name, source_action.replace("_", " ").title())

from fastapi import Query, HTTPException
from sqlalchemy import select, and_

@router.get(
    "/worker-assignments/history",
    summary="Get worker assignment audit timeline"
)
async def get_worker_assignment_history(
    worker_assignment_id: int | None = Query(None),
    oc_no: str | None = Query(None),
    awb_no: str | None = Query(None),
    hawb: str | None = Query(None),
    db: AsyncSession = Depends(get_db)
):
    # -----------------------------
    # 1️⃣ Validate input
    # -----------------------------
    identifiers_used = sum([
        worker_assignment_id is not None,
        oc_no is not None,
        awb_no is not None or hawb is not None
    ])

    if identifiers_used != 1:
        raise HTTPException(
            status_code=400,
            detail="Provide exactly one of: worker_assignment_id OR oc_no OR (awb_no + hawb)"
        )

    if (awb_no and not hawb) or (hawb and not awb_no):
        raise HTTPException(
            status_code=400,
            detail="Both awb_no and hawb are required together"
        )

    # -----------------------------
    # 2️⃣ Build query condition
    # -----------------------------
    if worker_assignment_id:
        condition = WorkerAssignmentAuditLog.worker_assignment_id == worker_assignment_id

    elif oc_no:
        condition = WorkerAssignmentAuditLog.oc_no == oc_no

    else:  # awb_no + hawb
        condition = and_(
            WorkerAssignmentAuditLog.awb_no == awb_no,
            WorkerAssignmentAuditLog.hawb == hawb
        )

    # -----------------------------
    # 3️⃣ Fetch logs
    # -----------------------------
    result = await db.execute(
        select(WorkerAssignmentAuditLog)
        .where(condition)
        .order_by(WorkerAssignmentAuditLog.changed_at.asc())
    )

    logs = result.scalars().all()

    if not logs:
        return {
            "timeline": []
        }

    # -----------------------------
    # 4️⃣ Build timeline
    # -----------------------------
    timeline = []
    for index, log in enumerate(logs, start=1):
        timeline.append({
            "step": index,
            "event": get_event_title(log.field_name, log.source_action),
            "field": log.field_name,
            "from": log.old_value,
            "to": log.new_value,
            "performed_by": {
                "emp_id": log.changed_by,
                "role": log.changed_by_role
            },
            "source": log.source_action,
            "ip_address": log.ip_address,
            "device_id": log.device_id,
            "user_agent": log.user_agent,
            "timestamp": log.changed_at
        })

    first = logs[0]

    return {
        "worker_assignment_id": first.worker_assignment_id,
        "oc_no": first.oc_no,
        "awb_no": first.awb_no,
        "hawb": first.hawb,
        "timeline": timeline
    }
