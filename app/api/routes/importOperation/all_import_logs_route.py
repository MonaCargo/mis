


from fastapi import APIRouter, Depends
from numpy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.importOperation.audit_log_worker_assignment import WorkerAssignmentAuditLog
from app.db.models.importOperation.worker_assignment import WorkerAssignmentHeader, WorkerAssignmentShipment
from app.db.session import get_db


from app.db.models.user import User
from app.services.importOperation.audit_log_worker_assignment import search_in_worker_assignments_for_history_timeline

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












# ===================== SHIPMENT TIME LINE API 😊😊 =====================================

# @router.get("/history/timeline/search")
# async def search_shipments(
#     type: str,
#     value: str,
#     db: AsyncSession = Depends(get_db),
# ):

#     query = select(
#         WorkerAssignmentHeader,
#         WorkerAssignmentShipment
#     ).join(
#         WorkerAssignmentShipment,
#         WorkerAssignmentShipment.assignment_header_id
#         == WorkerAssignmentHeader.id
#     )

#     if type == "oc":
#         query = query.where(WorkerAssignmentHeader.oc_no == value)

#     elif type == "awb":
#         query = query.where(WorkerAssignmentHeader.awb_no == value)

#     elif type == "hawb":
#         query = query.where(WorkerAssignmentHeader.hawb == value)

#     elif type == "gp":
#         query = query.where(
#             WorkerAssignmentShipment.gate_pass_no == value
#         )

#     else:
#         raise HTTPException(400, "Invalid search type")

#     result = await db.execute(query)

#     rows = result.all()

#     if not rows:
#         return {"data": []}

#     data = []

#     for header, ship in rows:

#         data.append({
#             "header_id": header.id,
#             "shipment_id": ship.id,

#             "oc_no": header.oc_no,
#             "awb": header.awb_no,
#             "hawb": header.hawb,

#             "gate_pass": ship.gate_pass_no,

#             "assigned_person": ship.assigned_person,
#             "drop_dlv_zone":ship.drop_dlv_zone,
#             "is_final_delivered": ship.is_final_delivered,
#         })

#     return {"data": data}


@router.get(
    "/history/timeline/search",
    # response_model=WorkerAssignmentResponseForWorkerLists,
    description="Search worker assignments by oc_no, gp_no, temp_oc, awb, hawb",
)
async def search_worker_assignment(
    type: str = Query(..., description="oc_no | gp_no | temp_oc | awb | hawb"),
    term: str = Query(..., description="Search value"),
    db: AsyncSession = Depends(get_db),
):

    data = await search_in_worker_assignments_for_history_timeline(db, search_type=type, search_value=term)

    return {
        "status": "success",
        "success": True,
        "message": "Search completed",
        "data": data,
        "total": len(data),
        "your_search_type": type,
        "your_search_value": term,
    }

@router.get("/shipments/{shipment_id}/flow")
async def get_shipment_flow(
    shipment_id: int,
    header_id: int,
    db: AsyncSession = Depends(get_db)
):

    # --------------------------------------------------
    # 1️⃣ Fetch Header
    # --------------------------------------------------
    header = (
        await db.execute(
            select(WorkerAssignmentHeader)
            .where(WorkerAssignmentHeader.id == header_id)
        )
    ).scalars().first()

    if not header:
        raise HTTPException(404, "Header not found")


    # --------------------------------------------------
    # 2️⃣ Fetch Shipment
    # --------------------------------------------------
    shipment = (
        await db.execute(
            select(WorkerAssignmentShipment)
            .where(
                WorkerAssignmentShipment.id == shipment_id,
                WorkerAssignmentShipment.assignment_header_id == header_id
            )
        )
    ).scalars().first()

    if not shipment:
        raise HTTPException(404, "Shipment not found")


    # --------------------------------------------------
    # 3️⃣ Fetch Audit Logs
    # --------------------------------------------------
    logs = (
        await db.execute(
            select(WorkerAssignmentAuditLog)
            .where(
                WorkerAssignmentAuditLog.shipment_id == shipment_id,
                WorkerAssignmentAuditLog.header_id == header_id
            )
            .order_by(WorkerAssignmentAuditLog.changed_at)
        )
    ).scalars().all()


    # --------------------------------------------------
    # 4️⃣ Timeline Builder
    # --------------------------------------------------
    STEP_MAP = {
        "assigned_person": "Assigned",
        "drop_dlv_zone": "Drop Zone",
        "loading_in_lift_zone": "Lift Loading",
        "unloading_from_lift_zone": "Lift Unloading",
        "is_final_delivered": "Delivered",
    }

    timeline = []

    for log in logs:

        if log.field_name not in STEP_MAP:
            continue

        timeline.append({
            "step": STEP_MAP[log.field_name],

            "field": log.field_name,

            "from": log.old_value,
            "to": log.new_value,

            "changed_by": log.changed_by,
            "role": log.changed_by_role,

            "time": log.changed_at,

            "action": log.source_action,
            "origin": log.origin_source_type,
        })


    # --------------------------------------------------
    # 5️⃣ Current Status Resolver
    # --------------------------------------------------
    if shipment.is_final_delivered:
        current_status = "Delivered"

    elif shipment.unloading_from_lift_zone:
        current_status = "Lift Unloaded"

    elif shipment.loading_in_lift_zone:
        current_status = "Lift Loaded"

    elif shipment.drop_dlv_zone:
        current_status = "Drop Zone"

    elif shipment.assigned_person:
        current_status = "Assigned"

    else:
        current_status = "Created"


    # --------------------------------------------------
    # 6️⃣ Identity Section (HEADER)
    # --------------------------------------------------
    identity = {
        "header_id": header.id,

        "oc_no": header.oc_no,
        "awb_no": header.awb_no,
        "hawb": header.hawb,

        "igp_no": header.igp_no,
        "igp_print_time": header.igp_print_date_time,

        "is_temp_irm": header.is_temp_irm_oc,
        "temp_irm_oc": header.temp_irm_oc_no,

        "is_printed": header.is_printed,

        "created_at": header.created_at,
        "updated_at": header.updated_at,
    }


    # --------------------------------------------------
    # 7️⃣ Full Shipment Snapshot
    # --------------------------------------------------
    shipment_info = {
        "shipment_id": shipment.id,

        # Package Info
        "no_of_pc": shipment.no_of_pc,
        "no_of_pc_recd": shipment.no_of_pc_recd,

        "weight_in_kgs": shipment.weight_in_kgs,
        "chargeable_weight": shipment.chg_wgt_in_kg,

        # Flight
        "flight_no": shipment.flight_no,
        "flight_date": shipment.flight_date,

        # Location
        "location": shipment.location,
        "shc": shipment.shc,

        "irr_codes": shipment.irr_codes,
        "irregularity_remarks": shipment.irregularity_remarks,

        # Parties
        "agent_name": shipment.agent_name,
        "customer_name": shipment.customer_name,

        # Gate Pass
        "gate_pass_no": shipment.gate_pass_no,
        "gate_pass_start": shipment.gate_pass_issued_date_time_combo,
        "gate_pass_end": shipment.gate_pass_end_datetime,

        # Assignment
        "assigned_person": shipment.assigned_person,
        "assigned_at": shipment.assigned_person_datetime,

        # Drop
        "drop_dlv_zone": shipment.drop_dlv_zone,
        "drop_dlv_zone_time": shipment.drop_dlv_zone_datetime,

        # Lift Loading
        "lift_loading_zone": shipment.loading_in_lift_zone,
        "lift_loading_person": shipment.loading_in_lift_person,
        "lift_loading_time": shipment.loading_in_lift_zone_datetime,

        # Lift Unloading
        "lift_unloading_zone": shipment.unloading_from_lift_zone,
        "lift_unloading_person": shipment.unloading_from_lift_person,
        "lift_unloading_time": shipment.unloading_from_lift_zone_datetime,

        # Final Delivery
        "final_delivered_by": shipment.final_delivery_by_person,
        "final_delivery_time": shipment.final_delivery_datetime,
        "is_final_delivered": shipment.is_final_delivered,

        # Meta
        "created_at": shipment.created_at,
        "updated_at": shipment.updated_at,
    }


    # --------------------------------------------------
    # 8️⃣ Summary (For Stepper UI)
    # --------------------------------------------------
    summary = {
        "assigned": bool(shipment.assigned_person),
        "drop_zone": bool(shipment.drop_dlv_zone),
        "lift_loaded": bool(shipment.loading_in_lift_zone),
        "lift_unloaded": bool(shipment.unloading_from_lift_zone),
        "delivered": shipment.is_final_delivered,
    }


    # --------------------------------------------------
    # 9️⃣ Final Response
    # --------------------------------------------------
    return {
        "identity": identity,

        "shipment_info": shipment_info,

        "current_status": current_status,

        "summary": summary,

        "timeline": timeline,
    }
