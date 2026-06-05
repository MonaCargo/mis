from typing import Optional

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependency import verify_token_and_get_user
from app.db.session import get_db
from app.schemas.importOperation.imp_truck_in_out_module import (
    AddMoreGpRequest,
    AddMoreGpResponse,
    ByHandPickupRequest,
    ByHandPickupResponse,
    CancelQueueRequest,
    CancelQueueResponse,
    CcClearChargesRequest,
    GatePassCheckRequest,
    GatePassCheckResponse,
    GatePassReassignRequest,
    GatePassReassignResponse,
    PromoteQueueRequest,
    PromoteQueueResponse,
    QueueSearchResponse,
    QueuedTruckListResponse,
    SaveGpChargeRequest,
    SaveStagingToTruckVisitResponse,
    TruckListResponse,
    TruckListResponseforListType,
    TruckOutSearchResponse,
    TruckSearchResponse,
    TruckStagingRequest,
    TruckStagingResponse,
    GatePassOutRequest,
    GatePassOutResponse,
    TruckOutRequest,
    TruckOutResponse,
)
from app.services.importOperation.imp_truck_in_out_module import (
    ImportAddMoreGpService,
    ImportCustomercareService,
    ImportGatePassReassignService,
    ImportTruckInOutService,
    ImportTruckQueueService,
    ImportTruckSearchService,
    ImportTruckStagingService,
    ImportTruckVisitService,
    ImportGatePassOutService,
    ImportTruckOutService,
)
from datetime import date, datetime

from app.db.models.importOperation.imp_truck_in_out_module import (
    ImportTruckInOutActivityLog,
)

router = APIRouter()


@router.post("/check-gate-pass", response_model=GatePassCheckResponse)
async def check_gate_pass(
    request: GatePassCheckRequest, db: AsyncSession = Depends(get_db)
):
    """
    Validate a gate pass against IRR Report table.
    """
    response = await ImportTruckInOutService.check_gate_pass_validity(db, request)

    if not response.valid:
        # Raise HTTP 404 for invalid gate pass
        raise HTTPException(status_code=404, detail=response.message)

    return response


@router.get("/truck-list", response_model=TruckListResponse)
async def list_trucks(target_date: date = None, db: AsyncSession = Depends(get_db)):
    """
    List all trucks for a given date (default = today).
    Includes truck info and assigned gate passes.
    """
    return await ImportTruckInOutService.list_trucks_by_date(db, target_date)


@router.get(
    "/truck-list-by-event-type-and-date", response_model=TruckListResponseforListType
)
async def list_trucks_by_event(
    list_type: str,  # required: "truck_in" or "truck_out"
    target_date: date = None,
    db: AsyncSession = Depends(get_db),
):
    """
    List trucks for a given date filtered by event type.

    Query params:
    - list_type   : "truck_in"  → trucks that checked IN on this date
                    "truck_out" → trucks that checked OUT on this date
    - target_date : IST date (default = today)
    """
    return await ImportTruckInOutService.list_trucks_by_list_type_and_date(
        db, list_type=list_type, target_date=target_date
    )


@router.get("/queued-truck-list", response_model=QueuedTruckListResponse)
async def list_queued_trucks(
    target_date: date = None, db: AsyncSession = Depends(get_db)
):
    """
    List all QUEUED trucks for a given IST date (default = today).
    Ordered by queued_at ascending.
    """
    return await ImportTruckInOutService.list_queued_trucks_by_date(db, target_date)


@router.post("/add-staging", response_model=TruckStagingResponse)
async def add_to_staging(
    request: TruckStagingRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
    # session_id: str = "default-session"  # In real app, derive from user/session context
):
    """
    Add a truck + gate pass entry into staging table.
    """
    return await ImportTruckStagingService.add_to_staging(db, request,current_user.emp_id)


@router.delete("/remove/{entry_id}")
async def remove_from_staging(
    entry_id: int, truck_number: str, db: AsyncSession = Depends(get_db), current_user = Depends(verify_token_and_get_user)
):
    return await ImportTruckStagingService.remove_from_staging(
        db, entry_id, truck_number, current_user.emp_id
    )


@router.get("/staging-list")
async def list_staging_entries(
    db: AsyncSession = Depends(get_db), truck_number: str = "default-truck"
):
    """
    List all staging entries for a given session.
    """

    return await ImportTruckStagingService.list_staging_entries(
        db, truck_number=truck_number
    )


@router.post(
    "/move-staging-to-truck-visit", response_model=SaveStagingToTruckVisitResponse
)
async def commit_truck(
    truck_number: str,
    emp_id: str,
    db: AsyncSession = Depends(get_db),
    device_id: str = None,
    is_queued: bool = False,  # ← NEW query param
):
    return await ImportTruckVisitService.commit_staging_to_truck_visit(
        db, truck_number, emp_id, device_id, is_queued
    )


@router.post(
    "/by-hand-pickup-in",
    response_model=ByHandPickupResponse,
    description="Create a by-hand pickup entry directly. No truck number, no queue, no staging — direct check-in for cargo carried by hand.",
)
async def by_hand_pickup_in(
    request: ByHandPickupRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Create a by-hand pickup entry. No truck, no queue, direct check-in.
    """
    return await ImportTruckVisitService.create_by_hand_pickup(
        db=db,
        person_name=request.person_name,
        person_contact=request.person_contact,
        gate_pass_nos=request.gate_pass_nos,
        emp_id=request.emp_id,
        device_id=request.device_id,
        remarks=request.remarks,
    )


@router.post("/gatepass-out", response_model=GatePassOutResponse)
async def gate_pass_out(
    request: GatePassOutRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Record pcs loaded for a specific gate pass (Gate Pass OUT).
    """
    return await ImportGatePassOutService.gate_pass_out(
        db=db,
        truck_visit_id=request.truck_visit_id,
        gate_pass_no=request.gate_pass_no,
        loaded_pcs=request.loaded_pcs,
        emp_id=request.emp_id,
    )


@router.post("/truck-out", response_model=TruckOutResponse)
async def truck_out(
    request: TruckOutRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Mark a truck visit as OUT.
    Only allowed once all gate passes have been processed.
    """
    return await ImportTruckOutService.truck_out(
        db=db,
        truck_visit_id=request.truck_visit_id,
        emp_id=request.emp_id,
        device_id=request.device_id,
    )


@router.post("/reassign-gatepass", response_model=GatePassReassignResponse)
async def reassign_gate_pass(
    request: GatePassReassignRequest, db: AsyncSession = Depends(get_db),current_user = Depends(verify_token_and_get_user)
):
    return await ImportGatePassReassignService.reassign_gate_pass(
        db=db,
        gate_pass_no=request.gate_pass_no,
        from_truck_visit_id=request.from_truck_visit_id,
        to_truck_visit_id=request.to_truck_visit_id,
        operator=current_user.emp_id if current_user else request.operator,
        remarks=request.remarks,
    )


# New endpoints:
@router.get("/queue-search", response_model=QueueSearchResponse)
async def search_queue(
    queue_no: str = None, truck_number: str = None, db: AsyncSession = Depends(get_db)
):
    return await ImportTruckQueueService.search_queue(db, queue_no, truck_number)


@router.post("/promote-queue", response_model=PromoteQueueResponse)
async def promote_queue(
    request: PromoteQueueRequest, db: AsyncSession = Depends(get_db)
):
    return await ImportTruckQueueService.promote_queue_to_truck_in(
        db, request.truck_visit_id, request.emp_id, request.device_id
    )


@router.post("/cancel-queue", response_model=CancelQueueResponse)
async def cancel_queue(request: CancelQueueRequest, db: AsyncSession = Depends(get_db)):
    return await ImportTruckQueueService.cancel_queue(
        db, request.truck_visit_id, request.emp_id, request.remarks
    )


@router.get("/search-truck-in-out-module", response_model=TruckSearchResponse)
async def search_trucks(
    search_type: str,  # gp_no | truck_no | queue_no
    term: str,
    target_date: date = None,  # only for truck_no; defaults to today in service
    db: AsyncSession = Depends(get_db),
):
    """
    Unified search across gate passes, truck numbers, and queue numbers.
    Single optimized JOIN query per search type.
    """
    return await ImportTruckSearchService.search(
        db=db, search_type=search_type, term=term, target_date=target_date
    )


# @router.get("/truck-out-search", response_model=TruckOutSearchResponse)
# async def truck_out_search(
#     truck_no: str,
#     db: AsyncSession = Depends(get_db)
# ):
#     """
#     Search a truck for truck-out workflow.
#     No date filter — finds the active (BOOKED + truck_in) visit.
#     Returns workflow_status to drive UI (READY_FOR_GP_OUT | READY_FOR_TRUCK_OUT | TRUCK_OUT_DONE).
#     """
#     return await ImportTruckOutService.search_truck_for_out(db, truck_no)


@router.get("/truck-out-search", response_model=TruckOutSearchResponse)
async def truck_out_search(
    search_term: str,  # ← renamed from truck_no
    search_by: str = "truck_no",  # ← NEW: "truck_no" | "gp_no"
    db: AsyncSession = Depends(get_db),
):
    """
    Search a visit (truck or by-hand) for the truck-out workflow.

    Query params:
    - search_term : the value to search for
    - search_by   : "truck_no" → search by truck number (default)
                    "gp_no"    → search by gate pass number, finds active visit
    """
    return await ImportTruckOutService.search_truck_for_out(
        db,
        search_term=search_term,
        search_by=search_by,
    )


@router.post("/add-more-gp", response_model=AddMoreGpResponse)
async def add_more_gp(
    request: AddMoreGpRequest,
    db: AsyncSession = Depends(get_db),
):
    """
    Add more gate passes to an already-checked-in truck (before truck out).
    Multiple GPs in one request. Per-GP results returned for transparency.
    """
    return await ImportAddMoreGpService.add_more_gp_to_truck(
        db=db,
        truck_visit_id=request.truck_visit_id,
        gate_pass_nos=[item.gate_pass_no for item in request.gate_passes],
        emp_id=request.emp_id,
        remarks=request.remarks,
    )


@router.get("/customer-care-search")
async def customer_care_search(
    search_term: str,
    search_by: str = "truck_no",  # "truck_no" | "gp_no"
    db: AsyncSession = Depends(get_db),
):
    """
    Customer-care dashboard search.
    Finds the ACTIVE visit (truck or by-hand) by truck number or GP number.
    No date filter. Returns friendly message if no active visit exists.
    """
    return await ImportTruckOutService.search_for_customer_care(
        db,
        search_term=search_term,
        search_by=search_by,
    )


@router.post("/save-gp-storage-charge")
async def save_gp_storage_charge(
    request: SaveGpChargeRequest, db: AsyncSession = Depends(get_db)
):
    return await ImportTruckOutService.save_gp_storage_charge_from_customer(
        db,
        truck_visit_id=request.truck_visit_id,
        gate_pass_no=request.gate_pass_no,
        storage_charge=request.storage_charge,
        challan_no=request.challan_no,
        remarks=request.remarks,
        emp_id=request.emp_id,
    )


@router.post("/customer-care-clear-charges")
async def customer_care_clear_charges(
    request: CcClearChargesRequest, db: AsyncSession = Depends(get_db)
):
    return await ImportCustomercareService.customer_care_clear_charges(
        db, 
        truck_visit_id=request.truck_visit_id,
        emp_id=request.emp_id
    )


# =========== Get All activity log based on filters (truck , gatepass no , event_type etc)
@router.get("/get-all-activity-log-of-truck-in-out-module")
async def get_activity_log(
    truck_visit_id: Optional[int] = None,
    truck_number: Optional[str] = None,
    gate_pass_no: Optional[str] = None,
    queue_no: Optional[str] = None,
    token_no: Optional[str] = None,
    event_type: Optional[str] = None,
    entity_type: Optional[str] = None,
    performed_by: Optional[str] = None,
    from_date: Optional[datetime] = None,
    to_date: Optional[datetime] = None,
    limit: int = 200,
    offset: int = 0,
    db: AsyncSession = Depends(get_db),
):
    """
    Get activity logs for the import truck-in-out module.

    Filters (all optional, combine freely):
    - truck_visit_id  : exact visit ID
    - truck_number    : truck number (case-insensitive)
    - gate_pass_no    : gate pass number
    - queue_no        : queue number
    - token_no        : token number
    - event_type      : TRUCK_IN | TRUCK_OUT | GP_ASSIGNED | GP_LOADED | QUEUE_PROMOTED | QUEUE_CANCELLED | GP_REASSIGNED | MORE_GP_ADDED | GP_STAGED | GP_STAGING_REMOVED
    - entity_type     : truck_visit | gate_pass | gp_assignment | gp_loading | staging
    - performed_by    : emp_id
    - from_date       : ISO datetime (e.g., 2026-06-01T00:00:00)
    - to_date         : ISO datetime
    - limit           : default 200 (max 1000)
    - offset          : for pagination

    Returns latest events first.
    """
    if limit > 1000:
        limit = 1000

    stmt = select(ImportTruckInOutActivityLog).order_by(
        ImportTruckInOutActivityLog.created_at.desc()
    )

    if truck_visit_id is not None:
        stmt = stmt.where(ImportTruckInOutActivityLog.truck_visit_id == truck_visit_id)
    if truck_number:
        stmt = stmt.where(
            ImportTruckInOutActivityLog.truck_number == truck_number.strip().upper()
        )
    if gate_pass_no:
        stmt = stmt.where(
            ImportTruckInOutActivityLog.gate_pass_no == gate_pass_no.strip()
        )
    if queue_no:
        stmt = stmt.where(ImportTruckInOutActivityLog.queue_no == queue_no.strip())
    if token_no:
        stmt = stmt.where(ImportTruckInOutActivityLog.token_no == token_no.strip())
    if event_type:
        stmt = stmt.where(
            ImportTruckInOutActivityLog.event_type == event_type.strip().upper()
        )
    if entity_type:
        stmt = stmt.where(
            ImportTruckInOutActivityLog.entity_type == entity_type.strip().lower()
        )
    if performed_by:
        stmt = stmt.where(
            ImportTruckInOutActivityLog.performed_by == performed_by.strip()
        )
    if from_date:
        stmt = stmt.where(ImportTruckInOutActivityLog.created_at >= from_date)
    if to_date:
        stmt = stmt.where(ImportTruckInOutActivityLog.created_at <= to_date)

    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    logs = result.scalars().all()

    # ── Reference for what entity_id means in each event ────────────────────
    entity_id_reference = {
        "GP_STAGED": {
            "entity_type": "staging",
            "refers_to": "ImportTruckInStaging.id",
            "table": "import_truck_in_staging",
            "description": "The staging row created when operator scanned a GP before truck IN. truck_visit_id is null at this stage (truck visit not yet created).",
        },
        "GP_STAGING_REMOVED": {
            "entity_type": "staging",
            "refers_to": "ImportTruckInStaging.id (now deleted)",
            "table": "import_truck_in_staging",
            "description": "The staging row that was removed before truck IN was committed. Row no longer exists in DB.",
        },
        "TRUCK_QUEUED": {
            "entity_type": "truck_visit",
            "refers_to": "ImportTruckVisit.id",
            "table": "import_truck_visit",
            "description": "The truck visit row created with status=QUEUED. Has queue_no but no truck_in_date_time yet.",
        },
        "TRUCK_IN": {
            "entity_type": "truck_visit",
            "refers_to": "ImportTruckVisit.id",
            "table": "import_truck_visit",
            "description": "The truck visit row created with status=BOOKED and is_truck_in=True. Direct truck IN (no queue).",
        },
        "QUEUE_PROMOTED": {
            "entity_type": "truck_visit",
            "refers_to": "ImportTruckVisit.id",
            "table": "import_truck_visit",
            "description": "The truck visit row that flipped from QUEUED to BOOKED (is_truck_in set to True).",
        },
        "QUEUE_CANCELLED": {
            "entity_type": "truck_visit",
            "refers_to": "ImportTruckVisit.id",
            "table": "import_truck_visit",
            "description": "The truck visit row that was set to CANCELLED. All its assignments were deactivated.",
        },
        "GP_ASSIGNED": {
            "entity_type": "gp_assignment",
            "refers_to": "ImportGatePassAssignment.id",
            "table": "import_gate_pass_assignment",
            "description": "The assignment row created linking GP to truck_visit during initial truck IN/queue. is_active=True.",
        },
        "MORE_GP_ADDED": {
            "entity_type": "gp_assignment",
            "refers_to": "ImportGatePassAssignment.id",
            "table": "import_gate_pass_assignment",
            "description": "The assignment row created when GP was added to an already-checked-in truck.",
        },
        "GP_REASSIGNED": {
            "entity_type": "gp_assignment",
            "refers_to": "ImportGatePassAssignment.id (the NEW assignment)",
            "table": "import_gate_pass_assignment",
            "description": "The NEW active assignment created on the destination truck. Old assignment ID is in snapshot_before.old_assignment_id.",
        },
        "GP_LOADED": {
            "entity_type": "gp_loading",
            "refers_to": "ImportGatePassLoading.id",
            "table": "import_gate_pass_loading",
            "description": "The loading event row recording pcs loaded. After this, the assignment is deactivated (is_active=False).",
        },
        "TRUCK_OUT": {
            "entity_type": "truck_visit",
            "refers_to": "ImportTruckVisit.id",
            "table": "import_truck_visit",
            "description": "The truck visit row that was marked is_truck_out=True. All active GPs verified as loaded before this.",
        },
    }

    return {
        "success": True,
        "count": len(logs),
        "limit": limit,
        "offset": offset,
        "entity_id_reference": entity_id_reference,
        "logs": [
            {
                "id": l.id,
                "created_at": l.created_at.isoformat() if l.created_at else None,
                "event_type": l.event_type,
                "entity_type": l.entity_type,
                "entity_id": l.entity_id,
                "truck_visit_id": l.truck_visit_id,
                "truck_number": l.truck_number,
                "gate_pass_no": l.gate_pass_no,
                "queue_no": l.queue_no,
                "token_no": l.token_no,
                "description": l.description,
                "reason": l.reason,
                "changes": l.changes,
                "snapshot_before": l.snapshot_before,
                "snapshot_after": l.snapshot_after,
                "performed_by": l.performed_by,
                "performed_by_role": l.performed_by_role,
                "device_id": l.device_id,
                "ip_address": l.ip_address,
                "request_id": l.request_id,
            }
            for l in logs
        ],
    }
