# services/export_car_message_awb_service.py

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import and_, func, select
from sqlalchemy.dialects.postgresql import insert
from app.db.models.exportOperation.car_message import (
    ExportAwbSkidItemSequence,
    ExportAwbSkidMapping,
    ExportCarMessageAwbMaster,
    ExportFlightBookingDetail,
    ExportFlightBookingHeader,
    ExportSequenceItemUldLoading,
    ExportSkidBaseMapping,
    ExportSkidLocationMapping,
    ExportUldAssignment,
    ExportUldAssignmentDetail
)
from app.db.models.exportOperation.export_base_master import ExportBaseMaster
from app.db.models.exportOperation.export_location_master import ExportLocationsMaster
from app.db.models.exportOperation.export_skid_master import ExportSkidMaster
from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.schemas.exportOperation.car_message import AvailableAwbForFlightBookingResponse, AwbLoadingStatusItem, CreateFlightBookingRequest, CreateFlightBookingResponse, CreateUldAssignmentRequest, EditFlightBookingRequest, EditFlightBookingResponse, EditUldAssignmentRequest, FlightBookingByFlightResponse, FlightBookingDetailResponse, FlightBookingDetailWithAwbResponse, FlightUldLoadingStatusResponse, ScanItemIntoUldRequest, ScanItemIntoUldResponse, ScanItemResult, UldAssignmentDataResponse, UldAssignmentDetailResponse, UldAssignmentResponse, UldLoadingStatusItem, UldMasterResponse, UldVerifyForLoadingResponse
from app.services.exportOperation.car_message_flow_audit_log import write_car_message_flow_audit
from app.utils.common.car_message_flow_audit_utils import CarMessageFlowModule, CarMessageFlowStep
from app.utils.common.helperFunction import get_utc_now


# ── 😎 reusable booked_pcs subquery }───────────────────────────────
def _booked_pcs_subquery():
    return (
        select(
            ExportFlightBookingDetail.awb_master_id,
            func.sum(ExportFlightBookingDetail.booked_pcs).label("booked_pcs"),
        )
        .join(
            ExportFlightBookingHeader,
            and_(
                ExportFlightBookingDetail.flight_header_id == ExportFlightBookingHeader.id,
                ExportFlightBookingHeader.is_active == True,
            ),
        )
        .group_by(ExportFlightBookingDetail.awb_master_id)
        .subquery()
    )


def to_utc(dt: datetime) -> datetime:
    if dt.tzinfo is not None:
        return dt.astimezone(timezone.utc)
    ist_offset = timedelta(hours=5, minutes=30)
    return (dt - ist_offset).replace(tzinfo=timezone.utc)


def _build_skid_activity_log(
    skid: dict,
    mapping_row,
    location_history: list,
    base_drop: dict | None = None, 
) -> list[dict]:

    activity = []

    # ── 1. Skid assigned to AWB ────────────────────────────────
    activity.append({
        "action": "SKID_ASSIGNED",
        "label": "Skid assigned to AWB",
        "performed_by": skid.get("mapped_by"),
        "timestamp": mapping_row.mapping_created_at,
        "detail": {
            "skid_no": skid.get("skid_no"),
            "virtual_skid_no": skid.get("virtual_skid_no"),
            "is_virtual": skid.get("is_virtual"),
        },
    })

    # ── 2. Retrieved — most recent is_current=False + picked_at set ──
    retrieved = [
        loc for loc in location_history
        if not loc.is_current and
        loc.picked_at and loc.picked_by
         and not loc.is_relocation
      
    ]

    if retrieved:
        # ✅ most recent retrieval only
        most_recent = max(retrieved, key=lambda x: x.picked_at)
        activity.append({
            "action": "RETRIEVED_FROM_LOCATION",
            "label": f"Retrieved from {most_recent.area_code} — {most_recent.loc}",
            "performed_by": most_recent.picked_by,
            "timestamp": most_recent.picked_at,
            "detail": {
                "location_code": most_recent.area_code,
                "location_name": most_recent.loc,
            },
        })

       # ── 3. Dropped at base ─────────────────────────────────────
    if base_drop:
        activity.append({
            "action": "DROPPED_AT_BASE",
            "label": f"Dropped at base — {base_drop['base_name']}",
            "performed_by": base_drop["dropped_by"],
            "timestamp": base_drop["dropped_at"],
            "detail": {
                "base_id": base_drop["base_id"],
                "base_name": base_drop["base_name"],
            },
        })


    # ── sort by timestamp ──────────────────────────────────────
    activity.sort(
        key=lambda x: x["timestamp"] if x["timestamp"]
        else datetime.min.replace(tzinfo=timezone.utc)
    )

    return activity


def _get_skid_retrieval_status(
    location_history: list,
    base_drop: dict | None,
) -> str:
    if base_drop:
        return "AT_BASE"
    if location_history:
        most_recent = max(location_history, key=lambda x: x.assigned_at)
        if not most_recent.is_current and most_recent.picked_at:
            return "RETRIEVED"
    return "PENDING"


# COMMON PRIVATE FUN END ---------------------------------------------------




async def save_export_car_message_awbs(db: AsyncSession, df, uploaded_by: str = None, ):

    if df.empty:
        return {
            "total_received": 0,
            "inserted": 0,
            "already_present": 0,
        }

    records = df.to_dict(orient="records")

    # 🔥 Add timestamps
    now = get_utc_now()

    for record in records:
        record["created_at"] = now
        record["updated_at"] = now
        record["uploaded_by"] = uploaded_by 

    stmt = insert(ExportCarMessageAwbMaster).values(records)

    stmt = stmt.on_conflict_do_nothing(
        constraint="uq_awb_car_msg"
    )

    result = await db.execute(stmt)
    await db.commit()

    inserted_count = result.rowcount or 0
    total_received = len(records)
    already_present = total_received - inserted_count

    return {
        "total_received": total_received,
        "inserted": inserted_count,
        "already_present": already_present,
    }



# ✌️======== Extract awb data from give export wh_inventry pdf for car message =================================
async def enrich_awb_from_wh_inventory(db: AsyncSession, df) -> dict:
    """
    Match extracted PDF rows against ExportCarMessageAwbMaster by awb_no
    and update: status, rcs_datetime, agent, vol_mc.

    Rules:
        - If master.status is already RCS → skip status, rcs_datetime, vol_mc
        - If not RCS yet → always update status, rcs_datetime, vol_mc
        - agent → update if currently NULL (always, regardless of status)
    """
    if df.empty:
        return {
            "total_in_pdf": 0,
            "matched": 0,
            "not_found": [],
            "not_found_count": 0,
        }

    # ── 1. Deduplicate — one row per AWB (latest datetime wins) ──────────────
    df = df.copy()
    df_unique = (
        df.sort_values("DATETIME")
          .drop_duplicates(subset="AWB", keep="last")
          .set_index("AWB")
    )
    pdf_awb_set = set(df_unique.index.tolist())

    # ── 2. Fetch matching master rows — single query ───────────────────────── 
    stmt = select(ExportCarMessageAwbMaster).where(
        ExportCarMessageAwbMaster.awb_no.in_(pdf_awb_set)
    )
    result  = await db.execute(stmt)
    masters = result.scalars().all()

    # ── 3. Update fields ──────────────────────────────────────────────────────
    matched: set[str] = set()
    now = get_utc_now()

    for master in masters:
        if master.awb_no not in df_unique.index:
            continue

        row = df_unique.loc[master.awb_no]

        # agent — always update if currently NULL
        if master.agent is None:
            master.agent = _val(row.get("AGENT"))

        # If already RCS — final status, don't touch anything else
        if master.status == "RCS":
            pass

        else:
            # Not yet RCS — update status, datetime, vol_mc
            master.status       = _val(row.get("STATUS"))
            master.rcs_datetime = _to_datetime(row.get("DATETIME"))
            master.vol_mc       = _to_float(row.get("VOL_MC"))

        master.updated_at = now
        matched.add(master.awb_no)

    # ── 4. Commit ─────────────────────────────────────────────────────────────
    await db.commit()

    not_found = sorted(pdf_awb_set - matched)

    return {
        "total_in_pdf":    len(df_unique),
        "matched":         len(matched),
        "not_found":       not_found,
        "not_found_count": len(not_found),
    }
# ── Small helpers (private) ───────────────────────────────────────────────────
 
def _val(val):
    """pandas NA / empty string → None, else stripped string."""
    import pandas as pd
    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass
    s = str(val).strip()
    return s or None
 
 
def _to_datetime(val):
    """Convert PDF datetime (IST naive) → UTC aware datetime for DB."""
    import pandas as pd
    import pytz
    from datetime import datetime

    IST = pytz.timezone("Asia/Kolkata")
    UTC = pytz.utc

    if val is None:
        return None
    try:
        if pd.isna(val):
            return None
    except (TypeError, ValueError):
        pass

    if isinstance(val, pd.Timestamp):
        dt = val.to_pydatetime().replace(tzinfo=None)
    elif isinstance(val, datetime):
        dt = val.replace(tzinfo=None)
    else:
        return None

    # Treat as IST → convert to UTC
    return IST.localize(dt).astimezone(UTC)

 
 
def _to_float(val):
    """Safe float conversion, None on failure."""
    try:
        return float(val)
    except (TypeError, ValueError):
        return None
    
#  =====------------ End of extract and save awb data from pdf whexport-inventry -------------------   


#✌️=======Get allowed awb for fligh booking screen dropdown =======================
# async def get_available_awbs_for_flight_booking_dropdown(
#     db: AsyncSession,
#     origin: Optional[str] = None,
#     destination: Optional[str] = None,
# ) -> list[AvailableAwbForFlightBookingResponse]:

#     # ── Subquery: sum booked_pcs per AWB across active flights only ──
#     booked_subq = _booked_pcs_subquery()

#     # ── Main query ──
#     remaining_pcs_expr = (
#         ExportCarMessageAwbMaster.pcs
#         - func.coalesce(booked_subq.c.booked_pcs, 0)
#     )

#     stmt = (
#         select(
#             ExportCarMessageAwbMaster.id.label("awb_master_id"),
#             ExportCarMessageAwbMaster.awb_no,
#             ExportCarMessageAwbMaster.origin,
#             ExportCarMessageAwbMaster.destination,
#             ExportCarMessageAwbMaster.pcs.label("total_pcs"),
#             func.coalesce(booked_subq.c.booked_pcs, 0).label("booked_pcs"),
#             remaining_pcs_expr.label("remaining_pcs"),
#             ExportCarMessageAwbMaster.agent,
#             ExportCarMessageAwbMaster.rcs_datetime,
#         )
#         .outerjoin(
#             booked_subq,
#             ExportCarMessageAwbMaster.id == booked_subq.c.awb_master_id,
#         )
#         .where(
#             ExportCarMessageAwbMaster.status == "RCS",          # hits partial index
#             ExportCarMessageAwbMaster.pcs.isnot(None),
#             remaining_pcs_expr > 0,                             # only with pcs left
#         )
#         .order_by(ExportCarMessageAwbMaster.rcs_datetime.desc())
#     )

#     if origin:
#         stmt = stmt.where(
#             ExportCarMessageAwbMaster.origin == origin.strip().upper()
#         )
#     if destination:
#         stmt = stmt.where(
#             ExportCarMessageAwbMaster.destination == destination.strip().upper()
#         )

#     result = await db.execute(stmt)
#     rows = result.mappings().all()

#     return [AvailableAwbForFlightBookingResponse(**row) for row in rows]

# async def get_available_awbs_for_flight_booking_dropdown(
#     db: AsyncSession,
#     origin: Optional[str] = None,
#     destination: Optional[str] = None,
# ) -> list[AvailableAwbForFlightBookingResponse]:

#     # ── Subquery 1: sum booked_pcs per AWB across active flights ──
#     booked_subq = _booked_pcs_subquery()

#     # ── Subquery 2: total scanned pcs per AWB ─────────────────
#     scanned_subq = (
#         select(
#             ExportAwbSkidItemSequence.awb_master_id,
#             func.count(ExportAwbSkidItemSequence.id).label("scanned_pcs"),
#         )
#         .group_by(ExportAwbSkidItemSequence.awb_master_id)
#         .subquery()
#     )

#     # ── Subquery 3: total skids count per AWB ─────────────────
#     total_skids_subq = (
#         select(
#             ExportAwbSkidMapping.awb_master_id,
#             func.count(ExportAwbSkidMapping.id).label("total_skids"),
#         )
#         .group_by(ExportAwbSkidMapping.awb_master_id)
#         .subquery()
#     )

#     # ── Subquery 4: skids that have been located at least once ─
#     ever_located_subq = (
#         select(
#             ExportAwbSkidMapping.awb_master_id,
#             func.count(ExportAwbSkidMapping.id.distinct()).label("ever_located_skids"),
#         )
#         .join(
#             ExportSkidLocationMapping,
#             ExportSkidLocationMapping.skid_id == ExportAwbSkidMapping.skid_id,
#         )
#         .group_by(ExportAwbSkidMapping.awb_master_id)
#         .subquery()
#     )

#     # ── Main query ─────────────────────────────────────────────
#     remaining_pcs_expr = (
#         ExportCarMessageAwbMaster.pcs
#         - func.coalesce(booked_subq.c.booked_pcs, 0)
#     )

#     stmt = (
#         select(
#             ExportCarMessageAwbMaster.id.label("awb_master_id"),
#             ExportCarMessageAwbMaster.awb_no,
#             ExportCarMessageAwbMaster.origin,
#             ExportCarMessageAwbMaster.destination,
#             ExportCarMessageAwbMaster.pcs.label("total_pcs"),
#             func.coalesce(booked_subq.c.booked_pcs, 0).label("booked_pcs"),
#             remaining_pcs_expr.label("remaining_pcs"),
#             ExportCarMessageAwbMaster.agent,
#             ExportCarMessageAwbMaster.rcs_datetime,
#         )
#         .outerjoin(booked_subq, ExportCarMessageAwbMaster.id == booked_subq.c.awb_master_id)
#         # ✅ inner joins — AWB must have scans, skids, and located skids
#         .join(scanned_subq, ExportCarMessageAwbMaster.id == scanned_subq.c.awb_master_id)
#         .join(total_skids_subq, ExportCarMessageAwbMaster.id == total_skids_subq.c.awb_master_id)
#         .join(ever_located_subq, ExportCarMessageAwbMaster.id == ever_located_subq.c.awb_master_id)
#         .where(
#             ExportCarMessageAwbMaster.status == "RCS",
#             ExportCarMessageAwbMaster.pcs.isnot(None),
#             remaining_pcs_expr > 0,
#             # ✅ NEW: all pcs scanned
#             scanned_subq.c.scanned_pcs >= ExportCarMessageAwbMaster.pcs,
#             # ✅ NEW: all skids located at least once
#             ever_located_subq.c.ever_located_skids == total_skids_subq.c.total_skids,
#         )
#         .order_by(ExportCarMessageAwbMaster.rcs_datetime.desc())
#     )

#     if origin:
#         stmt = stmt.where(
#             ExportCarMessageAwbMaster.origin == origin.strip().upper()
#         )
#     if destination:
#         stmt = stmt.where(
#             ExportCarMessageAwbMaster.destination == destination.strip().upper()
#         )

#     result = await db.execute(stmt)
#     rows = result.mappings().all()

#     return [AvailableAwbForFlightBookingResponse(**row) for row in rows]

async def get_available_awbs_for_flight_booking_dropdown(
    db: AsyncSession,
    origin: Optional[str] = None,
    destination: Optional[str] = None,
) -> list[AvailableAwbForFlightBookingResponse]:

    # ── Subquery 1: booked pcs ─────────────────────────────
    booked_subq = _booked_pcs_subquery()

    # ── Subquery 2: scanned pcs per AWB ───────────────────
    scanned_subq = (
        select(
            ExportAwbSkidItemSequence.awb_master_id,
            func.count(ExportAwbSkidItemSequence.id).label("scanned_pcs"),
        )
        .group_by(ExportAwbSkidItemSequence.awb_master_id)
        .subquery()
    )

    # ── Subquery 3: total distinct skids per AWB ───────────
    total_skids_subq = (
        select(
            ExportAwbSkidMapping.awb_master_id,
            func.count(ExportAwbSkidMapping.skid_id.distinct()).label("total_skids"),
        )
        .group_by(ExportAwbSkidMapping.awb_master_id)
        .subquery()
    )

    # ── Subquery 4: located skids scoped to same AWB session
    ever_located_subq = (
        select(
            ExportAwbSkidMapping.awb_master_id,
            func.count(ExportAwbSkidMapping.skid_id.distinct()).label("ever_located_skids"),
        )
        .join(
            ExportSkidLocationMapping,
            and_(
                ExportSkidLocationMapping.skid_id == ExportAwbSkidMapping.skid_id,
                ExportSkidLocationMapping.awb_master_id == ExportAwbSkidMapping.awb_master_id,  # ✅ scope
            ),
        )
        .group_by(ExportAwbSkidMapping.awb_master_id)
        .subquery()
    )

    # ── Main query ─────────────────────────────────────────
    remaining_pcs_expr = (
        ExportCarMessageAwbMaster.pcs
        - func.coalesce(booked_subq.c.booked_pcs, 0)
    )

    stmt = (
        select(
            ExportCarMessageAwbMaster.id.label("awb_master_id"),
            ExportCarMessageAwbMaster.awb_no,
            ExportCarMessageAwbMaster.origin,
            ExportCarMessageAwbMaster.destination,
            ExportCarMessageAwbMaster.pcs.label("total_pcs"),
            func.coalesce(booked_subq.c.booked_pcs, 0).label("booked_pcs"),
            remaining_pcs_expr.label("remaining_pcs"),
            ExportCarMessageAwbMaster.agent,
            ExportCarMessageAwbMaster.rcs_datetime,
        )
        .outerjoin(booked_subq, ExportCarMessageAwbMaster.id == booked_subq.c.awb_master_id)
        .join(scanned_subq, ExportCarMessageAwbMaster.id == scanned_subq.c.awb_master_id)
        .join(total_skids_subq, ExportCarMessageAwbMaster.id == total_skids_subq.c.awb_master_id)
        .join(ever_located_subq, ExportCarMessageAwbMaster.id == ever_located_subq.c.awb_master_id)
        .where(
            ExportCarMessageAwbMaster.status == "RCS",
            ExportCarMessageAwbMaster.pcs.isnot(None),
            remaining_pcs_expr > 0,
            # ✅ all pcs scanned
            scanned_subq.c.scanned_pcs >= ExportCarMessageAwbMaster.pcs,
            # ✅ ALL skids located at least once in this AWB session
            ever_located_subq.c.ever_located_skids == total_skids_subq.c.total_skids,
        )
        .order_by(ExportCarMessageAwbMaster.rcs_datetime.desc())
    )

    if origin:
        stmt = stmt.where(
            ExportCarMessageAwbMaster.origin == origin.strip().upper()
        )
    if destination:
        stmt = stmt.where(
            ExportCarMessageAwbMaster.destination == destination.strip().upper()
        )

    result = await db.execute(stmt)
    rows = result.mappings().all()

    return [AvailableAwbForFlightBookingResponse(**row) for row in rows]


# ========= ✌️✌️  CREATE new flight booking ──────────────────────────────────────=========
async def create_flight_booking(
    db: AsyncSession,
    payload: CreateFlightBookingRequest,
    booked_by: str,  # emp_id from auth
) -> CreateFlightBookingResponse:

    now = get_utc_now()
    awb_ids = [item.awb_master_id for item in payload.awbs]

   
    # ── Check 1: duplicate flight on same date ─────────────────
    existing_header = await db.execute(
        select(ExportFlightBookingHeader.id).where(
            ExportFlightBookingHeader.flight_no == payload.flight_no,
            ExportFlightBookingHeader.flight_date == payload.flight_date,
            ExportFlightBookingHeader.is_active == True,
        )
    )
    if existing_header.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Flight {payload.flight_no} already booked on {payload.flight_date}"
        )

    # ── Check 2: fetch all AWBs in one query ───────────────────
    awb_result = await db.execute(
        select(
            ExportCarMessageAwbMaster.id,
            ExportCarMessageAwbMaster.awb_no,
            ExportCarMessageAwbMaster.pcs,
            ExportCarMessageAwbMaster.status,
        ).where(ExportCarMessageAwbMaster.id.in_(awb_ids))
    )
    awb_map = {row.id: row for row in awb_result.mappings().all()}

    # ── Check 3: fetch already booked pcs for these AWBs in one query ──
    booked_result = await db.execute(
        select(
            ExportFlightBookingDetail.awb_master_id,
            func.sum(ExportFlightBookingDetail.booked_pcs).label("booked_pcs"),
        )
        .join(
            ExportFlightBookingHeader,
            and_(
                ExportFlightBookingDetail.flight_header_id == ExportFlightBookingHeader.id,
                ExportFlightBookingHeader.is_active == True,
            ),
        )
        .where(ExportFlightBookingDetail.awb_master_id.in_(awb_ids))
        .group_by(ExportFlightBookingDetail.awb_master_id)
    )
    booked_map = {row.awb_master_id: row.booked_pcs for row in booked_result.mappings().all()}

    # ── Check 4: validate each AWB ─────────────────────────────
    errors = []
    for item in payload.awbs:
        awb = awb_map.get(item.awb_master_id)

        if not awb:
            errors.append(f"AWB id {item.awb_master_id} not found")
            continue

        if awb.status != "RCS":
            errors.append(f"AWB {awb.awb_no} is not in RCS status")
            continue

        already_booked = booked_map.get(item.awb_master_id, 0)
        remaining = awb.pcs - already_booked

        if remaining <= 0:
            errors.append(f"AWB {awb.awb_no} is fully booked — no pcs remaining")
            continue

        if item.booked_pcs > remaining:
            errors.append(
                f"AWB {awb.awb_no}: requested {item.booked_pcs} pcs "
                f"but only {remaining} remaining"
            )

    if errors:
        raise HTTPException(status_code=400, detail=errors)

    # ── All checks passed — insert header + details ────────────
    header = ExportFlightBookingHeader(
        flight_no=payload.flight_no,
        flight_date=payload.flight_date,
        flight_dpt_datetime=to_utc(payload.flight_dpt_datetime),
        booked_by=booked_by,
        booked_at=now,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(header)
    await db.flush()  # get header.id without committing

    details = [
        ExportFlightBookingDetail(
             flight_header_id=header.id,
            awb_master_id=item.awb_master_id,
            booked_pcs=item.booked_pcs,
        )
        for item in payload.awbs
    ]
    db.add_all(details)

    await db.flush()  # get detail ids


     # ── Audit log — one entry per AWB ─────────────────────────
    for item in payload.awbs:
        await write_car_message_flow_audit(
            db=db,
            awb_reference_id=item.awb_master_id,
            flight_reference_id=header.id,
            module=CarMessageFlowModule.FLIGHT_BOOKING,
            flow_step=CarMessageFlowStep.FLIGHT_BOOKING,
            record_id=header.id,
            action="CREATE",
            performed_by=booked_by,
            changes={
                "event": "FLIGHT_BOOKING_CREATED",
                "flight_no": header.flight_no,
                "flight_date": str(header.flight_date),
                "flight_dpt_datetime": str(header.flight_dpt_datetime),
                "booked_pcs": item.booked_pcs,
            },
        )
        
    await db.commit()   # commits header + details + logs together
    await db.refresh(header)

    # ── Build response ─────────────────────────────────────────
    return CreateFlightBookingResponse(
        success=True,
        message="Successfully Created flight booking.",
        header_id=header.id,
        flight_no=header.flight_no,
        flight_date=header.flight_date,
        flight_dpt_datetime=header.flight_dpt_datetime,
        total_awbs=len(details),
        total_pcs=sum(item.booked_pcs for item in payload.awbs),
        details=[
            FlightBookingDetailResponse(
                awb_master_id=item.awb_master_id,
                awb_no=awb_map[item.awb_master_id].awb_no,
                booked_pcs=item.booked_pcs,
                total_pcs=awb_map[item.awb_master_id].pcs,  # ✅ add this
            )
            for item in payload.awbs
        ],
    )







async def get_flight_booking_by_flight_no_and_date(
    db: AsyncSession,
    flight_no: str,
    flight_date: date,
) -> FlightBookingByFlightResponse:

    # ── Fetch header ───────────────────────────────────────────
    header_result = await db.execute(
        select(ExportFlightBookingHeader).where(
            ExportFlightBookingHeader.flight_no == flight_no.strip().upper(),
            ExportFlightBookingHeader.flight_date == flight_date,
            ExportFlightBookingHeader.is_active == True,
        )
    )
    header = header_result.scalar_one_or_none()
    if not header:
        raise HTTPException(
            status_code=404,
            detail=f"No active booking found for flight {flight_no} on {flight_date}",
        )

    # ── Fetch details with AWB info ────────────────────────────
    details_result = await db.execute(
        select(
            ExportFlightBookingDetail.id.label("detail_id"),
            ExportFlightBookingDetail.awb_master_id,
            ExportFlightBookingDetail.booked_pcs,
            ExportCarMessageAwbMaster.awb_no,
            ExportCarMessageAwbMaster.origin,
            ExportCarMessageAwbMaster.destination,
            ExportCarMessageAwbMaster.pcs.label("total_pcs"),
            ExportCarMessageAwbMaster.agent,
            ExportCarMessageAwbMaster.rcs_datetime,
        )
        .join(
            ExportCarMessageAwbMaster,
            ExportFlightBookingDetail.awb_master_id == ExportCarMessageAwbMaster.id,
        )
      
        .where(ExportFlightBookingDetail.flight_header_id == header.id)
    )
    details = details_result.mappings().all()

    if not details:
        raise HTTPException(
            status_code=404,
            detail="Flight booking has no AWB details",
        )

    awb_ids = [d.awb_master_id for d in details]

    # ── Booked in OTHER flights for these AWBs (single query) ──
    booked_elsewhere_result = await db.execute(
        select(
            ExportFlightBookingDetail.awb_master_id,
            func.sum(ExportFlightBookingDetail.booked_pcs).label("booked_pcs"),
        )
        .join(
            ExportFlightBookingHeader,
            and_(
              
                ExportFlightBookingDetail.flight_header_id == ExportFlightBookingHeader.id,
                ExportFlightBookingHeader.is_active == True,
                ExportFlightBookingHeader.id != header.id,   # exclude current
            ),
        )
        .where(ExportFlightBookingDetail.awb_master_id.in_(awb_ids))
        .group_by(ExportFlightBookingDetail.awb_master_id)
    )
    booked_elsewhere = {
        row.awb_master_id: row.booked_pcs
        for row in booked_elsewhere_result.mappings().all()
    }

    # ── Build detail response ──────────────────────────────────
    detail_list = []
    for d in details:
        booked_in_others = booked_elsewhere.get(d.awb_master_id, 0)
        remaining = d.total_pcs - booked_in_others - d.booked_pcs

        detail_list.append(
            FlightBookingDetailWithAwbResponse(
                detail_id=d.detail_id,
                awb_master_id=d.awb_master_id,
                awb_no=d.awb_no,
                origin=d.origin,
                destination=d.destination,
                total_pcs=d.total_pcs,
                booked_pcs=d.booked_pcs,
                booked_in_other_flights=booked_in_others,
                remaining_pcs=remaining,
                agent=d.agent,
                rcs_datetime=d.rcs_datetime,
            )
        )

    return FlightBookingByFlightResponse(
        header_id=header.id,
        flight_no=header.flight_no,
        flight_date=header.flight_date,
        flight_dpt_datetime=header.flight_dpt_datetime,
        booked_by=header.booked_by,
        booked_at=header.booked_at,
        total_awbs=len(detail_list),
        total_pcs=sum(d.booked_pcs for d in detail_list),
        details=detail_list,
    )



async def edit_flight_booking(
    db: AsyncSession,
    header_id: int,
    payload: EditFlightBookingRequest,
    edited_by: str,
) -> EditFlightBookingResponse:

    now = get_utc_now()

    # ── Fetch header ───────────────────────────────────────────
    header = await db.get(ExportFlightBookingHeader, header_id)
    if not header or not header.is_active:
        raise HTTPException(
            status_code=404,
            detail="Flight booking not found"
        )

    if header.flight_dpt_datetime <= now:
        raise HTTPException(
            status_code=400,
            detail=f"Flight {header.flight_no} has already departed — editing is not allowed"
        )

    # ── Fetch existing details for this header ─────────────────
    existing_result = await db.execute(
        select(ExportFlightBookingDetail).where(
            ExportFlightBookingDetail.flight_header_id == header_id
        )
    )
    existing_details = {
        d.id: d for d in existing_result.scalars().all()
    }

    # ✅ ADD THIS — snapshot before any mutation {which used in log}
    old_pcs_map = {
        d_id: d.booked_pcs
        for d_id, d in existing_details.items()
    }

        # ✅ ADD HERE — block AWB removal + pcs reduction if items already loaded
    # fetch loaded counts per AWB on this flight in one query
    loaded_per_awb_result = await db.execute(
        select(
            ExportSequenceItemUldLoading.awb_master_id,
            func.count(ExportSequenceItemUldLoading.id).label("loaded_count"),
            ExportCarMessageAwbMaster.awb_no,
        )
        .join(
            ExportCarMessageAwbMaster,
            ExportSequenceItemUldLoading.awb_master_id == ExportCarMessageAwbMaster.id,
        )
        .where(
            ExportSequenceItemUldLoading.flight_header_id == header_id,
        )
        .group_by(
            ExportSequenceItemUldLoading.awb_master_id,
            ExportCarMessageAwbMaster.awb_no,
        )
    )
    loaded_per_awb = {
        row.awb_master_id: row
        for row in loaded_per_awb_result.mappings().all()
    }

    block_errors = []

    # block removal of AWBs that have loaded items
    for did in payload.removed_detail_ids:
        detail = existing_details.get(did)
        if not detail:
            continue
        loaded = loaded_per_awb.get(detail.awb_master_id)
        if loaded and loaded.loaded_count > 0:
            block_errors.append(
                f"AWB {loaded.awb_no} cannot be removed — "
                f"{loaded.loaded_count} item(s) already loaded into ULD on this flight"
            )

    # block pcs reduction below already loaded count
    for item in payload.awbs:
        if not item.detail_id or item.detail_id not in existing_details:
            continue
        loaded = loaded_per_awb.get(item.awb_master_id)
        if loaded and loaded.loaded_count > 0:
            if item.booked_pcs < loaded.loaded_count:
                awb = awb_map.get(item.awb_master_id) if 'awb_map' in dir() else None
                # awb_map not built yet at this point — fetch awb_no from loaded row
                block_errors.append(
                    f"AWB {loaded.awb_no}: cannot reduce pcs to {item.booked_pcs} — "
                    f"{loaded.loaded_count} item(s) already loaded into ULD"
                )

    if block_errors:
        raise HTTPException(status_code=400, detail=block_errors)
    
    # ── All AWB ids in payload ─────────────────────────────────
    awb_ids = [item.awb_master_id for item in payload.awbs]

    # ── Fetch AWB master data in one query ─────────────────────
    awb_result = await db.execute(
        select(
            ExportCarMessageAwbMaster.id,
            ExportCarMessageAwbMaster.awb_no,
            ExportCarMessageAwbMaster.pcs,
            ExportCarMessageAwbMaster.status,
        ).where(ExportCarMessageAwbMaster.id.in_(awb_ids))
    )
    awb_map = {row.id: row for row in awb_result.mappings().all()}

    # ── Booked pcs in OTHER active flights (exclude current) ───
    booked_elsewhere_result = await db.execute(
        select(
            ExportFlightBookingDetail.awb_master_id,
            func.sum(ExportFlightBookingDetail.booked_pcs).label("booked_pcs"),
        )
        .join(
            ExportFlightBookingHeader,
            and_(
                ExportFlightBookingDetail.flight_header_id == ExportFlightBookingHeader.id,
                ExportFlightBookingHeader.is_active == True,
                ExportFlightBookingHeader.id != header_id,  # ← exclude current flight
            ),
        )
        .where(ExportFlightBookingDetail.awb_master_id.in_(awb_ids))
        .group_by(ExportFlightBookingDetail.awb_master_id)
    )
    booked_elsewhere = {
        row.awb_master_id: row.booked_pcs
        for row in booked_elsewhere_result.mappings().all()
    }

    # ── Validate each AWB ──────────────────────────────────────
    errors = []
    for item in payload.awbs:
        awb = awb_map.get(item.awb_master_id)

        if not awb:
            errors.append(f"AWB id {item.awb_master_id} not found")
            continue

        if awb.status != "RCS":
            errors.append(f"AWB {awb.awb_no} is not in RCS status")
            continue

        booked_in_others = booked_elsewhere.get(item.awb_master_id, 0)
        available = awb.pcs - booked_in_others  # excludes current flight

        if item.booked_pcs > available:
            errors.append(
                f"AWB {awb.awb_no}: max {available} pcs available "
                f"({awb.pcs} total − {booked_in_others} in other flights)"
            )

    if errors:
        raise HTTPException(status_code=400, detail=errors)

    # ── Delete removed AWBs ────────────────────────────────────
    for detail_id in payload.removed_detail_ids:
        detail = existing_details.get(detail_id)
        if detail:
            await db.delete(detail)

    # ── Update existing / insert new ───────────────────────────
    for item in payload.awbs:
        if item.detail_id and item.detail_id in existing_details:
            # ✅ update existing row
            existing_details[item.detail_id].booked_pcs = item.booked_pcs
        else:
            # ✅ new AWB — insert
            db.add(
                ExportFlightBookingDetail(
                    flight_header_id=header_id,
                    awb_master_id=item.awb_master_id,
                    booked_pcs=item.booked_pcs,
                )
            )

    # ── Update header timestamp ────────────────────────────────
    header.updated_at = now



    # ── 😎 Audit log — track what actually changed ────────────────
    added_awbs = [
        item for item in payload.awbs
        if not item.detail_id or item.detail_id not in existing_details
    ]
    updated_awbs = [
        item for item in payload.awbs
        if item.detail_id and item.detail_id in existing_details
        and old_pcs_map[item.detail_id] != item.booked_pcs  # ✅ uses snapshot
    ]

    # log for newly added AWBs
    for item in added_awbs:
        awb = awb_map.get(item.awb_master_id)  # ✅ ADD THIS
        if not awb:
            continue
        await write_car_message_flow_audit(
            db=db,
            awb_reference_id=item.awb_master_id,
            flight_reference_id=header_id,
            module=CarMessageFlowModule.FLIGHT_BOOKING,
            flow_step=CarMessageFlowStep.FLIGHT_BOOKING,
            record_id=header_id,
            action="UPDATE",
            performed_by=edited_by,
            changes={
                "event": "AWB_ADDED",
                "flight_no": header.flight_no,
                "awb_no": awb.awb_no,
                "booked_pcs": item.booked_pcs,
                "summary": (
                f"AWB {awb.awb_no} added to flight {header.flight_no} "
                f"with {item.booked_pcs} pcs"
            ),
            },
        )

    # log for pcs changed AWBs
    for item in updated_awbs:
        awb = awb_map.get(item.awb_master_id)  # ✅ ADD THIS
        if not awb:
            continue
        old_pcs = old_pcs_map[item.detail_id]
        await write_car_message_flow_audit(
            db=db,
            awb_reference_id=item.awb_master_id,
            flight_reference_id=header_id,
            module=CarMessageFlowModule.FLIGHT_BOOKING,
            flow_step=CarMessageFlowStep.FLIGHT_BOOKING,
            record_id=header_id,
            action="UPDATE",
            performed_by=edited_by,
            changes={
                "event": "PCS_UPDATED",
                "flight_no": header.flight_no,
                "booked_pcs_before": old_pcs,
                "awb_no": awb.awb_no,
                "booked_pcs_after": item.booked_pcs,
                "summary": (
                f"AWB {awb.awb_no} pcs updated from {old_pcs} "
                f"to {item.booked_pcs} on flight {header.flight_no} and "
                f"flight date {str(header.flight_date)}"
            ),
            },
        )

    # log for removed AWBs — need awb_master_id from existing details
    # if payload.removed_detail_ids:
    #     removed_awb_ids = {
    #         existing_details[did].awb_master_id
    #         for did in payload.removed_detail_ids
    #         if did in existing_details
    #     }
    #     for awb_id in removed_awb_ids:
    #         await write_car_message_flow_audit(
    #             db=db,
    #             awb_reference_id=awb_id,
    #             flight_reference_id=header_id,
    #             module=CarMessageFlowModule.FLIGHT_BOOKING,
    #             flow_step=CarMessageFlowStep.FLIGHT_BOOKING,
    #             record_id=header_id,
    #             action="UPDATE",
    #             performed_by=edited_by,
    #             changes={
    #                 "event": "AWB_REMOVED",
    #                 "flight_no": header.flight_no,
    #                 "awb_no": awb.awb_no if awb else "UNKNOWN",
    #                 "summary": (
    #             f"AWB {awb.awb_no if awb else 'UNKNOWN'} removed from "
    #             f"flight {header.flight_no}"
    #             f"flight date {str(header.flight_date)}"
    #             f"({detail.booked_pcs} pcs freed)"
    #         ),
    #             },
    #         )

    for did in payload.removed_detail_ids:
        detail = existing_details.get(did)
        if not detail:
            continue
        awb = awb_map.get(detail.awb_master_id)  # ✅ now awb is defined
        await write_car_message_flow_audit(
            db=db,
            awb_reference_id=detail.awb_master_id,
            flight_reference_id=header_id,
            module=CarMessageFlowModule.FLIGHT_BOOKING,
            flow_step=CarMessageFlowStep.FLIGHT_BOOKING,
            record_id=header_id,
            action="UPDATE",
            performed_by=edited_by,
            changes={
                "event": "AWB_REMOVED",
                "flight_no": header.flight_no,
                "flight_date": str(header.flight_date),
                "awb_no": awb.awb_no if awb else "UNKNOWN",
                "booked_pcs_removed": old_pcs_map.get(did),  # ✅ from snapshot
                "summary": (
                    f"AWB {awb.awb_no if awb else 'UNKNOWN'} removed from "
                    f"flight {header.flight_no} ({header.flight_date}) — "
                    f"{old_pcs_map.get(did)} pcs freed"
                ),
            },
        )
# ------
    await db.commit()

    await db.refresh(header)

    # ── Return updated booking ─────────────────────────────────
    updated = await get_flight_booking_by_flight_no_and_date(
        db=db,
        flight_no=header.flight_no,
        flight_date=header.flight_date,
    )

    return EditFlightBookingResponse(
        success=True,
        message=f"Flight {header.flight_no} booking updated successfully",
        data=updated,
    )


# ======================== ✌️ ULD ASSIGNMENT CREATE AND  EDIT GET ...✌️ ======================================
# ============================-----------------------------------==============================================



# ── Helper: build assignment data response ─────────────────────
async def _build_assignment_response(
    db: AsyncSession,
    assignment: ExportUldAssignment,
    header: ExportFlightBookingHeader,
) -> UldAssignmentDataResponse:

    details_result = await db.execute(
        select(
            ExportUldAssignmentDetail.id.label("detail_id"),
            ExportUldAssignmentDetail.uld_id,
            ExportUldMaster.uld_no,
            ExportUldMaster.carrier,
        )
        .join(ExportUldMaster, ExportUldAssignmentDetail.uld_id == ExportUldMaster.id)
        .where(ExportUldAssignmentDetail.assignment_id == assignment.id)
        .order_by(ExportUldMaster.uld_no)
    )
    details = details_result.mappings().all()

    return UldAssignmentDataResponse(
        assignment_id=assignment.id,
        flight_header_id=header.id,
        flight_no=header.flight_no,
        flight_date=str(header.flight_date),
        flight_dpt_datetime=header.flight_dpt_datetime,
        total_ulds=len(details),
        assigned_by=assignment.assigned_by,
        assigned_at=assignment.assigned_at,
        ulds=[UldAssignmentDetailResponse(**d) for d in details],
    )


# ── Helper: departure check ────────────────────────────────────
def _check_not_departed(header: ExportFlightBookingHeader, flight_no: str):
    if header.flight_dpt_datetime <= datetime.now(timezone.utc):
        raise HTTPException(
            status_code=400,
            detail=f"Flight {flight_no} has already departed — operation not allowed",
        )

# ── reusable helper ────────────────────────────────────────────
# this help to check that already assignd uld not reused utilf that flight departure
async def _check_ulds_not_active_on_another_flight(
    db: AsyncSession,
    uld_ids: list[int],
    exclude_assignment_id: int | None = None,  # for edit — exclude current
) -> list[str]:
    """
    Returns list of error messages for ULDs already assigned
    to a flight that has not yet departed.
    """
    now = datetime.now(timezone.utc)

    # Find ULDs already assigned to another active non-departed flight
    stmt = (
        select(
            ExportUldMaster.uld_no,
            ExportFlightBookingHeader.flight_no,
            ExportFlightBookingHeader.flight_dpt_datetime,
        )
        .join(
            ExportUldAssignmentDetail,
            ExportUldAssignmentDetail.uld_id == ExportUldMaster.id,
        )
        .join(
            ExportUldAssignment,
            and_(
                ExportUldAssignmentDetail.assignment_id == ExportUldAssignment.id,
                ExportUldAssignment.is_active == True,
            ),
        )
        .join(
            ExportFlightBookingHeader,
            and_(
                ExportUldAssignment.flight_header_id == ExportFlightBookingHeader.id,
                ExportFlightBookingHeader.is_active == True,
                ExportFlightBookingHeader.flight_dpt_datetime > now,  # not yet departed
            ),
        )
        .where(ExportUldMaster.id.in_(uld_ids))
    )

    # exclude current assignment in edit mode
    if exclude_assignment_id:
        stmt = stmt.where(
            ExportUldAssignment.id != exclude_assignment_id
        )

    result = await db.execute(stmt)
    rows = result.mappings().all()

    return [
        f"ULD {row.uld_no} is already assigned to flight {row.flight_no} "
        f"which departs at {row.flight_dpt_datetime.strftime('%d %b %Y %H:%M')} UTC — "
        f"cannot assign until that flight departs"
        for row in rows
    ]


# ── GET all active ULDs ────────────────────────────────────────
async def get_uld_master_list(db: AsyncSession) -> list[UldMasterResponse]:
    result = await db.execute(
        select(
            ExportUldMaster.id.label("uld_id"),
            ExportUldMaster.uld_no,
            ExportUldMaster.carrier,
        )
        .where(ExportUldMaster.is_active == True)
        .order_by(ExportUldMaster.uld_no)
    )

    return [UldMasterResponse(**row) for row in result.mappings().all()]

# ── Get ULD which is assign to a flight and that flight  depart. If flighrt not depart now then those are not include 
async def get_uld_master_list_eligeble_for_assignment(db: AsyncSession) -> list[UldMasterResponse]:

    now = get_utc_now()

    # ── Subquery: ULD ids already assigned to non-departed active flights ──
    assigned_uld_subq = (
        select(ExportUldAssignmentDetail.uld_id)
        .join(
            ExportUldAssignment,
            ExportUldAssignmentDetail.assignment_id == ExportUldAssignment.id,
        )
        .join(
            ExportFlightBookingHeader,
            ExportUldAssignment.flight_header_id == ExportFlightBookingHeader.id,
        )
        .where(
            ExportUldAssignment.is_active == True,
            ExportFlightBookingHeader.is_active == True,
            ExportFlightBookingHeader.flight_dpt_datetime > now,  # ✅ not yet departed
        )
        .subquery()
    )

    result = await db.execute(
        select(
            ExportUldMaster.id.label("uld_id"),
            ExportUldMaster.uld_no,
            ExportUldMaster.carrier,
        )
        .where(
            ExportUldMaster.is_active == True,
            ExportUldMaster.id.notin_(select(assigned_uld_subq)),  # ✅ exclude assigned
        )
        .order_by(ExportUldMaster.uld_no)
    )
    rows = result.mappings().all()
    print(len(rows))

    return [UldMasterResponse(**row) for row in rows]

# ── GET assignment by flight ───────────────────────────────────
async def get_uld_assignment_by_flight(
    db: AsyncSession,
    flight_no: str,
    flight_date: date,
) -> UldAssignmentDataResponse | None:

    # fetch flight header
    header_result = await db.execute(
        select(ExportFlightBookingHeader).where(
            ExportFlightBookingHeader.flight_no == flight_no.strip().upper(),
            ExportFlightBookingHeader.flight_date == flight_date,
            ExportFlightBookingHeader.is_active == True,
        )
    )
    header = header_result.scalar_one_or_none()
    if not header:
        raise HTTPException(
            status_code=404,
            detail=f"No active flight booking found for {flight_no} on {flight_date}",
        )

    # fetch assignment
    assignment_result = await db.execute(
        select(ExportUldAssignment).where(
            ExportUldAssignment.flight_header_id == header.id,
            ExportUldAssignment.is_active == True,
        )
    )
    assignment = assignment_result.scalar_one_or_none()

    if not assignment:
        return None  # no assignment yet — frontend shows create form

    return await _build_assignment_response(db, assignment, header)


# ── CREATE assignment ──────────────────────────────────────────
async def create_uld_assignment(
    db: AsyncSession,
    payload: CreateUldAssignmentRequest,
    assigned_by: str,
) -> UldAssignmentResponse:

    now = get_utc_now()

    # fetch header
    header = await db.get(ExportFlightBookingHeader, payload.flight_header_id)
    if not header or not header.is_active:
        raise HTTPException(status_code=404, detail="Flight booking not found")

    # departure check
    _check_not_departed(header, header.flight_no)

    # check no existing assignment
    existing = await db.execute(
        select(ExportUldAssignment.id).where(
            ExportUldAssignment.flight_header_id == payload.flight_header_id,
            ExportUldAssignment.is_active == True,
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"ULD assignment already exists for flight {header.flight_no} — use edit instead",
        )

    # validate ULDs exist and are active — one query
    uld_result = await db.execute(
        select(ExportUldMaster.id).where(
            ExportUldMaster.id.in_(payload.uld_ids),
            ExportUldMaster.is_active == True,
        )
    )
    valid_uld_ids = {row.id for row in uld_result.all()}
    invalid = set(payload.uld_ids) - valid_uld_ids
    if invalid:
        raise HTTPException(
            status_code=400,
            detail=f"ULD ids not found or inactive: {sorted(invalid)}",
        )
    
    # ── Check ULDs not active on another non-departed flight ───
    conflicts = await _check_ulds_not_active_on_another_flight(
        db=db,
        uld_ids=payload.uld_ids,
    )
    if conflicts:
        raise HTTPException(status_code=400, detail=conflicts)

    # insert assignment
    assignment = ExportUldAssignment(
        flight_header_id=payload.flight_header_id,
        assigned_by=assigned_by,
        assigned_at=now,
        is_active=True,
        created_at=now,
        updated_at=now,
    )
    db.add(assignment)
    await db.flush()



    # insert details
    db.add_all([
        ExportUldAssignmentDetail(
            assignment_id=assignment.id,
            uld_id=uld_id,
            created_at=now,
        )
        for uld_id in payload.uld_ids
    ])

    # ✅ fetch ULD info for readable 😎 Log
    uld_info_result = await db.execute(
        select(
            ExportUldMaster.id,
            ExportUldMaster.uld_no,
            ExportUldMaster.carrier,
        ).where(ExportUldMaster.id.in_(payload.uld_ids))
    )
    uld_info_map = {row.id: row for row in uld_info_result.mappings().all()}

    # ✅ fetch all AWBs on this flight for per-AWB logging
    awb_ids_result = await db.execute(
        select(ExportFlightBookingDetail.awb_master_id).where(
            ExportFlightBookingDetail.flight_header_id == payload.flight_header_id
        )
    )
    awb_ids_on_flight = [row.awb_master_id for row in awb_ids_result.all()]

    # ✅ audit log — one entry per AWB
    for awb_id in awb_ids_on_flight:
        await write_car_message_flow_audit(
            db=db,
            awb_reference_id=awb_id,
            flight_reference_id=payload.flight_header_id,
            module=CarMessageFlowModule.ULD_ASSIGNMENT,
            flow_step=CarMessageFlowStep.ULD_ASSIGNMENT,
            record_id=assignment.id,
            action="CREATE",
            performed_by=assigned_by,
            changes={
                "event": "ULD_ASSIGNMENT_CREATED",
                "flight_no": header.flight_no,
                "flight_date": str(header.flight_date),
                "uld_count": len(payload.uld_ids),
                "ulds": [
                    {
                        "uld_id": uid,
                        "uld_no": uld_info_map[uid].uld_no,
                        "carrier": uld_info_map[uid].carrier,
                    }
                    for uid in payload.uld_ids
                    if uid in uld_info_map
                ],
                "summary": (
                    f"{len(payload.uld_ids)} ULD(s) assigned to flight "
                    f"{header.flight_no} ({header.flight_date}): "
                    f"{', '.join(uld_info_map[uid].uld_no for uid in payload.uld_ids if uid in uld_info_map)}"
                ),
            },
        )


# ------
    await db.commit()
    await db.refresh(assignment)

    data = await _build_assignment_response(db, assignment, header)
    return UldAssignmentResponse(
        success=True,
        message=f"ULD assignment created for flight {header.flight_no} — {len(payload.uld_ids)} ULDs assigned",
        data=data,
    )


# ── EDIT assignment ────────────────────────────────────────────
async def edit_uld_assignment(
    db: AsyncSession,
    assignment_id: int,
    payload: EditUldAssignmentRequest,
    edited_by: str,
) -> UldAssignmentResponse:

    now = get_utc_now()

    # fetch assignment
    assignment = await db.get(ExportUldAssignment, assignment_id)
    if not assignment or not assignment.is_active:
        raise HTTPException(status_code=404, detail="ULD assignment not found")

    # fetch header for departure check
    header = await db.get(ExportFlightBookingHeader, assignment.flight_header_id)
    _check_not_departed(header, header.flight_no)

    # fetch existing details
    existing_result = await db.execute(
        select(ExportUldAssignmentDetail).where(
            ExportUldAssignmentDetail.assignment_id == assignment_id
        )
    )
    existing_details = {d.id: d for d in existing_result.scalars().all()}
    existing_uld_ids = {d.uld_id for d in existing_details.values()}

    errors = []

    # ✅ ADD HERE — block ULD removal if items already loaded
    if payload.uld_detail_ids_to_remove:
        loaded_result = await db.execute(
            select(
                ExportSequenceItemUldLoading.uld_assignment_detail_id,
                func.count(ExportSequenceItemUldLoading.id).label("loaded_count"),
                ExportUldMaster.uld_no,
            )
            .join(
                ExportUldAssignmentDetail,
                ExportSequenceItemUldLoading.uld_assignment_detail_id == ExportUldAssignmentDetail.id,
            )
            .join(
                ExportUldMaster,
                ExportUldAssignmentDetail.uld_id == ExportUldMaster.id,
            )
            .where(
                ExportSequenceItemUldLoading.uld_assignment_detail_id.in_(
                    payload.uld_detail_ids_to_remove
                )
            )
            .group_by(
                ExportSequenceItemUldLoading.uld_assignment_detail_id,
                ExportUldMaster.uld_no,
            )
        )
        loaded_rows = loaded_result.mappings().all()

        block_errors = [
            f"ULD {row.uld_no} cannot be removed — "
            f"{row.loaded_count} item(s) already loaded into it"
            for row in loaded_rows
            if row.loaded_count > 0
        ]

        if block_errors:
            raise HTTPException(status_code=400, detail=block_errors)

    # ── validate new ULDs to add ───────────────────────────────
    if payload.uld_ids_to_add:
        # check duplicates against already assigned
        already_assigned = set(payload.uld_ids_to_add) & existing_uld_ids
        if already_assigned:
            # get uld_nos for readable error
            dup_result = await db.execute(
                select(ExportUldMaster.uld_no).where(
                    ExportUldMaster.id.in_(already_assigned)
                )
            )
            dup_nos = [r.uld_no for r in dup_result.all()]
            errors.append(f"ULDs already assigned to this flight: {', '.join(dup_nos)}")

        # check active in master
        uld_result = await db.execute(
            select(ExportUldMaster.id).where(
                ExportUldMaster.id.in_(payload.uld_ids_to_add),
                ExportUldMaster.is_active == True,
            )
        )
        valid_ids = {row.id for row in uld_result.all()}
        invalid = set(payload.uld_ids_to_add) - valid_ids
        if invalid:
            errors.append(f"ULD ids not found or inactive: {sorted(invalid)}")

        # ✅ only check flight conflicts if ULDs are valid so far
        # no point querying flight conflicts for invalid/inactive ULDs
        if not errors:
            conflicts = await _check_ulds_not_active_on_another_flight(
                db=db,
                uld_ids=payload.uld_ids_to_add,
                exclude_assignment_id=assignment_id,
            )
            if conflicts:
                errors.extend(conflicts)


    # ── validate remove ids belong to this assignment ──────────
    if payload.uld_detail_ids_to_remove:
        invalid_removes = set(payload.uld_detail_ids_to_remove) - set(existing_details.keys())
        if invalid_removes:
            errors.append(f"Detail ids do not belong to this assignment: {sorted(invalid_removes)}")

        # block if removing all and not adding any
        remaining_after_remove = len(existing_details) - len(payload.uld_detail_ids_to_remove)
        net_adds = len(payload.uld_ids_to_add)
        if remaining_after_remove + net_adds < 1:
            errors.append("At least one ULD must remain in the assignment")

    if errors:
        raise HTTPException(status_code=400, detail=errors)

    # ── delete removed details ─────────────────────────────────
    for detail_id in payload.uld_detail_ids_to_remove:
        await db.delete(existing_details[detail_id])

    # ── insert new ULDs ────────────────────────────────────────
    db.add_all([
        ExportUldAssignmentDetail(
            assignment_id=assignment_id,
            uld_id=uld_id,
            created_at=now,
        )
        for uld_id in payload.uld_ids_to_add
    ])

    assignment.updated_at = now
    
# ====== Log related used 😎
    # ✅ snapshot existing uld_id per detail_id before any delete
    existing_uld_id_map = {
        d_id: d.uld_id
        for d_id, d in existing_details.items()
    }

    # ✅ fetch ULD info for both added and removed ULDs
    all_relevant_uld_ids = list(
        set(payload.uld_ids_to_add) |
        {existing_uld_id_map[did] for did in payload.uld_detail_ids_to_remove if did in existing_uld_id_map}
    )

    uld_info_map = {}
    if all_relevant_uld_ids:
        uld_info_result = await db.execute(
            select(
                ExportUldMaster.id,
                ExportUldMaster.uld_no,
                ExportUldMaster.carrier,
            ).where(ExportUldMaster.id.in_(all_relevant_uld_ids))
        )
        uld_info_map = {row.id: row for row in uld_info_result.mappings().all()}

    # ✅ fetch AWBs on this flight
    awb_ids_result = await db.execute(
        select(ExportFlightBookingDetail.awb_master_id).where(
            ExportFlightBookingDetail.flight_header_id == assignment.flight_header_id
        )
    )
    awb_ids_on_flight = [row.awb_master_id for row in awb_ids_result.all()]

    # ✅ build readable added/removed uld lists
    added_ulds = [
        {
            "uld_id": uid,
            "uld_no": uld_info_map[uid].uld_no,
            "carrier": uld_info_map[uid].carrier,
        }
        for uid in payload.uld_ids_to_add
        if uid in uld_info_map
    ]

    removed_ulds = [
        {
            "uld_id": existing_uld_id_map[did],
            "uld_no": uld_info_map[existing_uld_id_map[did]].uld_no,
        }
        for did in payload.uld_detail_ids_to_remove
        if did in existing_uld_id_map
        and existing_uld_id_map[did] in uld_info_map
    ]

    added_uld_nos = [u["uld_no"] for u in added_ulds]
    removed_uld_nos = [u["uld_no"] for u in removed_ulds]

    # ✅ audit log — one entry per AWB
    for awb_id in awb_ids_on_flight:
        await write_car_message_flow_audit(
            db=db,
            awb_reference_id=awb_id,
            flight_reference_id=assignment.flight_header_id,
            module=CarMessageFlowModule.ULD_ASSIGNMENT,
            flow_step=CarMessageFlowStep.ULD_ASSIGNMENT,
            record_id=assignment_id,
            action="UPDATE",
            performed_by=edited_by,
            changes={
                "event": "ULD_ASSIGNMENT_UPDATED",
                "flight_no": header.flight_no,
                "flight_date": str(header.flight_date),
                "added_ulds": added_ulds,
                "removed_ulds": removed_ulds,
                "summary": (
                    f"Flight {header.flight_no} ({header.flight_date}) "
                    "ULD assignment updated — "
                    + (f"Added: {', '.join(added_uld_nos)}. " if added_uld_nos else "No ULDs added. ")
                    + (f"Removed: {', '.join(removed_uld_nos)}." if removed_uld_nos else "No ULDs removed.")
                ),
            },
        )

    # --------------
    await db.commit()
    await db.refresh(assignment)

    data = await _build_assignment_response(db, assignment, header)
    return UldAssignmentResponse(
        success=True,
        message=f"ULD assignment updated for flight {header.flight_no}",
        data=data,
    )

# ============ END ULD =========================


# ======================✌️Skid Retrival from location ===================
async def get_flights_by_date(
    db: AsyncSession,
    flight_date: date,
) -> list[dict]:

    now = get_utc_now()
    result = await db.execute(
        select(
            ExportFlightBookingHeader.id.label("header_id"),
            ExportFlightBookingHeader.flight_no,
            ExportFlightBookingHeader.flight_date,
            ExportFlightBookingHeader.flight_dpt_datetime,
            ExportFlightBookingHeader.booked_by,
            ExportFlightBookingHeader.booked_at,
            func.count(ExportFlightBookingDetail.id).label("total_awbs"),
            func.sum(ExportFlightBookingDetail.booked_pcs).label("total_pcs"),
        )
        .join(
            ExportFlightBookingDetail,
            ExportFlightBookingDetail.flight_header_id == ExportFlightBookingHeader.id,
        )
        .where(
            ExportFlightBookingHeader.flight_date == flight_date,
            ExportFlightBookingHeader.is_active == True,
            ExportFlightBookingHeader.flight_dpt_datetime > now,  # ✅ not yet departed
        )
        .group_by(ExportFlightBookingHeader.id)
        .order_by(ExportFlightBookingHeader.flight_dpt_datetime.asc())
    )
    rows = result.mappings().all()

    return [dict(row) for row in rows]


async def get_flight_full_detail(
    db: AsyncSession,
    header_id: int,
) -> dict:

    # ── Fetch header ───────────────────────────────────────────
    header = await db.get(ExportFlightBookingHeader, header_id)
    if not header or not header.is_active:
        raise HTTPException(status_code=404, detail="Flight booking not found")

    # ── Fetch AWBs booked on this flight ───────────────────────
    awb_result = await db.execute(
        select(
            ExportFlightBookingDetail.id.label("detail_id"),
            ExportFlightBookingDetail.booked_pcs,
            ExportCarMessageAwbMaster.id.label("awb_master_id"),
            ExportCarMessageAwbMaster.awb_no,
            ExportCarMessageAwbMaster.origin,
            ExportCarMessageAwbMaster.destination,
            ExportCarMessageAwbMaster.pcs.label("total_pcs"),
            ExportCarMessageAwbMaster.gross_wt,
            ExportCarMessageAwbMaster.chg_wt,
            ExportCarMessageAwbMaster.nog,
            ExportCarMessageAwbMaster.shc,
            ExportCarMessageAwbMaster.agent,
            ExportCarMessageAwbMaster.status,
            ExportCarMessageAwbMaster.rcs_datetime,
        )
        .join(
            ExportCarMessageAwbMaster,
            ExportFlightBookingDetail.awb_master_id == ExportCarMessageAwbMaster.id,
        )
        .where(ExportFlightBookingDetail.flight_header_id == header_id)
        .order_by(ExportCarMessageAwbMaster.awb_no)
    )
    awb_rows = awb_result.mappings().all()

    if not awb_rows:
        raise HTTPException(status_code=404, detail="No AWBs found for this flight")

    awb_master_ids = [row.awb_master_id for row in awb_rows]

    # ── Fetch skid mappings for all AWBs in one query ──────────
    skid_result = await db.execute(
        select(
            ExportAwbSkidMapping.id.label("mapping_id"),
            ExportAwbSkidMapping.awb_master_id,
            ExportAwbSkidMapping.skid_id,
            ExportAwbSkidMapping.virtual_skid_no,
            ExportAwbSkidMapping.is_virtual,
            ExportAwbSkidMapping.mapped_by,
            ExportAwbSkidMapping.mapped_at,
            ExportAwbSkidMapping.is_skid_used_complete,
             ExportAwbSkidMapping.created_at.label("mapping_created_at"),
            ExportSkidMaster.skid_no,
        )
        .outerjoin(
            ExportSkidMaster,
            ExportAwbSkidMapping.skid_id == ExportSkidMaster.id,
        )
        .where(ExportAwbSkidMapping.awb_master_id.in_(awb_master_ids))
        .order_by(ExportAwbSkidMapping.awb_master_id)
    )
    skid_rows = skid_result.mappings().all()

    mapping_ids = [row.mapping_id for row in skid_rows]

    # ── Fetch sequences for all mappings in one query ──────────
    seq_result = await db.execute(
        select(
            ExportAwbSkidItemSequence.id.label("sequence_id"),
            ExportAwbSkidItemSequence.mapping_id,
            ExportAwbSkidItemSequence.awb_master_id,
            ExportAwbSkidItemSequence.sequence_no,
            ExportAwbSkidItemSequence.sequence_date_time,
            ExportAwbSkidItemSequence.scanned_by,
            ExportAwbSkidItemSequence.scan_by_device,
        )
        .where(ExportAwbSkidItemSequence.mapping_id.in_(mapping_ids))
        .order_by(
            ExportAwbSkidItemSequence.mapping_id,
            ExportAwbSkidItemSequence.sequence_date_time.asc(),
        )
    ) if mapping_ids else None

    seq_rows = seq_result.mappings().all() if seq_result else []

    # ── Fetch current locations for all skids in one query ────
    location_result = await db.execute(
        select(
            ExportSkidLocationMapping.skid_id,
            ExportSkidLocationMapping.assigned_at,
            ExportSkidLocationMapping.assigned_by,
            ExportSkidLocationMapping.picked_at,
            ExportSkidLocationMapping.picked_by,
            ExportSkidLocationMapping.is_relocation,
            ExportLocationsMaster.id.label("location_id"),
            ExportLocationsMaster.loc,
            ExportLocationsMaster.area_code,
        )
        .join(
            ExportLocationsMaster,
            ExportSkidLocationMapping.location_id == ExportLocationsMaster.id,
        )
        .where(
            ExportSkidLocationMapping.skid_id.in_(
                [row.skid_id for row in skid_rows if row.skid_id]
            ),
            ExportSkidLocationMapping.mapping_id.in_(mapping_ids),# 😂😂
            ExportSkidLocationMapping.is_current == True,   # only current location
        )
    ) if any(row.skid_id for row in skid_rows) else None

    location_rows = location_result.mappings().all() if location_result else []
# =========== activity log releted ---
    # ── Fetch full location history for all skids ──────────────
    location_history_result = await db.execute(
        select(
            ExportSkidLocationMapping.skid_id,
            ExportSkidLocationMapping.assigned_at,
             ExportSkidLocationMapping.mapping_id,
            ExportSkidLocationMapping.assigned_by,
            ExportSkidLocationMapping.picked_at,
            ExportSkidLocationMapping.picked_by,
            ExportSkidLocationMapping.is_relocation,
            ExportSkidLocationMapping.is_current,
            ExportLocationsMaster.loc,
            ExportLocationsMaster.area_code,
        )
        .join(
            ExportLocationsMaster,
            ExportSkidLocationMapping.location_id == ExportLocationsMaster.id,
        )
        .where(
            ExportSkidLocationMapping.skid_id.in_(
                [row.skid_id for row in skid_rows if row.skid_id]
            ),
            ExportSkidLocationMapping.mapping_id.in_(mapping_ids),  
        )
        .order_by(
            ExportSkidLocationMapping.skid_id,
            ExportSkidLocationMapping.assigned_at.asc(),  # asc for activity timeline
        )
    ) if any(row.skid_id for row in skid_rows) else None

    location_history_rows = location_history_result.mappings().all() if location_history_result else []

    location_history_by_skid: dict[int, list] = {}
    for loc in location_history_rows:
        location_history_by_skid.setdefault(loc.skid_id, []).append(loc)
# ==========-------------------

#===================✌️  GET THE DATA DROPED AT BASE 
    base_drop_result = await db.execute(
        select(
            ExportSkidBaseMapping.mapping_id,
            ExportSkidBaseMapping.skid_id,
            ExportSkidBaseMapping.dropped_by,
            ExportSkidBaseMapping.dropped_at,
            ExportBaseMaster.base_name,
            ExportBaseMaster.id.label("base_id"),
        )
        .join(ExportBaseMaster, ExportSkidBaseMapping.base_id == ExportBaseMaster.id)
        .where(ExportSkidBaseMapping.mapping_id.in_(mapping_ids))
    ) if mapping_ids else None

    base_drop_rows = base_drop_result.mappings().all() if base_drop_result else []

    # keyed by mapping_id
    base_drop_by_mapping: dict[int, dict] = {
        row.mapping_id: dict(row)
        for row in base_drop_rows
    }
# ------------

    # location keyed by skid_id — one current location per skid
    location_by_skid: dict[int, dict] = {
        row.skid_id: {
            "location_id": row.location_id,
            "location_name": row.loc,
            "location_code": row.area_code,
            "assigned_at": row.assigned_at,
            "assigned_by": row.assigned_by,
            "picked_at": row.picked_at,
            "picked_by": row.picked_by,
            "is_relocation": row.is_relocation,
        }
        for row in location_rows
    }


    # ── ULD assignment for this flight ─────────────────────────
    uld_result = await db.execute(
        select(
            ExportUldAssignment.id.label("assignment_id"),
            ExportUldMaster.uld_no,
            ExportUldMaster.carrier,
            ExportUldAssignmentDetail.uld_id,
        )
        .join(
            ExportUldAssignmentDetail,
            ExportUldAssignmentDetail.assignment_id == ExportUldAssignment.id,
        )
        .join(
            ExportUldMaster,
            ExportUldAssignmentDetail.uld_id == ExportUldMaster.id,
        )
        .where(
            ExportUldAssignment.flight_header_id == header_id,
            ExportUldAssignment.is_active == True,
        )
        .order_by(ExportUldMaster.uld_no)
    )
    uld_rows = uld_result.mappings().all()

    # ── Build nested structure in memory ───────────────────────

    # sequences grouped by mapping_id
    seq_by_mapping: dict[int, list] = {}
    for seq in seq_rows:
        seq_by_mapping.setdefault(seq.mapping_id, []).append({
            "sequence_id": seq.sequence_id,
            "sequence_no": seq.sequence_no,
            "sequence_date_time": seq.sequence_date_time,
            "scanned_by": seq.scanned_by,
            "scan_by_device": seq.scan_by_device,
        })

    # skids grouped by awb_master_id
    skids_by_awb: dict[int, list] = {}
    for skid in skid_rows:

        location_history = location_history_by_skid.get(skid.skid_id, []) if skid.skid_id else []  # ← ADD
        base_drop = base_drop_by_mapping.get(skid.mapping_id) 
        
        skids_by_awb.setdefault(skid.awb_master_id, []).append({
            "mapping_id": skid.mapping_id,
            "skid_id": skid.skid_id,
            "skid_no": skid.skid_no,
            "virtual_skid_no": skid.virtual_skid_no,
            "is_virtual": skid.is_virtual,
            "is_skid_used_complete": skid.is_skid_used_complete,
            "sequences": seq_by_mapping.get(skid.mapping_id, []),
            "scanned_pcs": len(seq_by_mapping.get(skid.mapping_id, [])),
            "current_location": location_by_skid.get(skid.skid_id),
            # ✅ only 3 events now
            "activity_log": _build_skid_activity_log(
                skid=dict(skid),
                mapping_row=skid,
                location_history=location_history_by_skid.get(skid.skid_id, []) if skid.skid_id else [],
                base_drop=base_drop,        
            ),
           
             "retrieval_status": _get_skid_retrieval_status(    # ← ADD
                location_history=location_history,
                base_drop=base_drop,
    ),
        })

    # assemble AWBs
    awbs = []
    for awb in awb_rows:
        skids = skids_by_awb.get(awb.awb_master_id, [])
        total_scanned = sum(s["scanned_pcs"] for s in skids)
        awbs.append({
            "detail_id": awb.detail_id,
            "awb_master_id": awb.awb_master_id,
            "awb_no": awb.awb_no,
            "origin": awb.origin,
            "destination": awb.destination,
            "total_pcs": awb.total_pcs,
            "booked_pcs": awb.booked_pcs,
            "gross_wt": awb.gross_wt,
            "chg_wt": awb.chg_wt,
            "nog": awb.nog,
            "shc": awb.shc,
            "agent": awb.agent,
            "status": awb.status,
            "rcs_datetime": awb.rcs_datetime,
            "total_scanned_pcs": total_scanned,
            "skids": skids,
        })

    return {
        "header_id": header.id,
        "flight_no": header.flight_no,
        "flight_date": str(header.flight_date),
        "flight_dpt_datetime": header.flight_dpt_datetime,
        "booked_by": header.booked_by,
        "booked_at": header.booked_at,
        "total_awbs": len(awbs),
        "total_pcs": sum(a["booked_pcs"] for a in awbs),
        "total_scanned_pcs": sum(a["total_scanned_pcs"] for a in awbs),
        "ulds": [dict(u) for u in uld_rows],
        "awbs": awbs,
    }



async def retrieve_skid_from_location(
    db: AsyncSession,
    mapping_id: int,
    retrieved_by: str,
) -> dict:

    now = get_utc_now()

    # ── Fetch mapping with skid info ───────────────────────────
    mapping_result = await db.execute(
        select(
            ExportAwbSkidMapping.id.label("mapping_id"),
            ExportAwbSkidMapping.skid_id,
            ExportAwbSkidMapping.awb_master_id,
            ExportAwbSkidMapping.is_virtual,
            ExportAwbSkidMapping.virtual_skid_no,
            ExportSkidMaster.skid_no,
        )
        .join(
            ExportSkidMaster,
            ExportAwbSkidMapping.skid_id == ExportSkidMaster.id,
        )
        .where(ExportAwbSkidMapping.id == mapping_id)
    )
    mapping = mapping_result.mappings().one_or_none()

    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=f"Mapping id {mapping_id} not found",
        )

    # ── Fetch most recent active location for this skid ────────
    location_result = await db.execute(
        select(ExportSkidLocationMapping)
        .where(
            ExportSkidLocationMapping.skid_id == mapping.skid_id,
            ExportSkidLocationMapping.is_current == True,
        )
        .order_by(ExportSkidLocationMapping.assigned_at.desc())
        .limit(1)
    )
    location = location_result.scalar_one_or_none()

    if not location:
        raise HTTPException(
            status_code=404,
            detail=(
                f"Skid {mapping.skid_no} has no active location — "
                "already retrieved or never placed at a location"
            ),
        )

    # ── Fetch location master for readable info ────────────────
    location_master_result = await db.execute(
        select(ExportLocationsMaster).where(
            ExportLocationsMaster.id == location.location_id
        )
    )
    location_master = location_master_result.scalar_one_or_none()

    # ── Mark as retrieved ──────────────────────────────────────
    location.is_current = False
    location.picked_at = now
    location.picked_by = retrieved_by

    # ── Audit log ──────────────────────────────────────────────
    await write_car_message_flow_audit(
        db=db,
        awb_reference_id=location.awb_master_id,
        flight_reference_id=None,
        module=CarMessageFlowModule.SKID_RETRIEVAL,      # ← was LOCATION_MAPPING
        flow_step=CarMessageFlowStep.SKID_RETRIEVAL,     # ← was STEP_LOCATION_MAPPING
        record_id=location.id,
        action="UPDATE",
        performed_by=retrieved_by,
        changes={
            "event": "SKID_RETRIEVED",
            "mapping_id": mapping_id,
            "skid_id": mapping.skid_id,
            "skid_no": mapping.skid_no,
            "is_virtual": mapping.is_virtual,
            "virtual_skid_no": mapping.virtual_skid_no,
            "location_id": location.location_id,
            "location_code": location_master.area_code if location_master else None,
            "location_name": location_master.loc if location_master else None,
            "summary": (
                f"Skid {mapping.skid_no} retrieved from "
                f"{location_master.area_code if location_master else location.location_id} "
                f"by {retrieved_by}"
            ),
        },
    )

    await db.commit()

    return {
        "success": True,
        "message": (
            f"Skid {mapping.skid_no} successfully retrieved from "
            f"{location_master.area_code if location_master else 'location'}"
        ),
        "data": {
            "mapping_id": mapping_id,
            "skid_id": mapping.skid_id,
            "skid_no": mapping.skid_no,
            "is_virtual": mapping.is_virtual,
            "virtual_skid_no": mapping.virtual_skid_no,
            "awb_master_id": mapping.awb_master_id,
            "location_id": location.location_id,
            "location_code": location_master.area_code if location_master else None,
            "location_name": location_master.loc if location_master else None,
            "retrieved_by": retrieved_by,
            "retrieved_at": now,
        },
    }



# ================== 👌👌✌️ EXPORT ULD/PALLET LOADING BY SCANNING SEQUENCE [LAST STEP OF PROCESS]================= 


# ── 1. Verify ULD belongs to flight ───────────────────────
async def verify_uld_for_loading(
    db: AsyncSession,
    flight_header_id: int,
    uld_no: str,
) -> UldVerifyForLoadingResponse:

    uld_no = uld_no.strip().upper()

    # verify ULD exists and belongs to this flight
    result = await db.execute(
        select(
            ExportUldAssignmentDetail.id.label("uld_assignment_detail_id"),
            ExportUldMaster.id.label("uld_id"),
            ExportUldMaster.uld_no,
            ExportUldMaster.carrier,
        )
        .join(ExportUldAssignment,
              ExportUldAssignmentDetail.assignment_id == ExportUldAssignment.id)
        .join(ExportUldMaster,
              ExportUldAssignmentDetail.uld_id == ExportUldMaster.id)
        .where(
            ExportUldAssignment.flight_header_id == flight_header_id,
            ExportUldAssignment.is_active == True,
            ExportUldMaster.uld_no == uld_no,
        )
    )
    row = result.mappings().first()

    if not row:
        raise HTTPException(
            status_code=404,
            detail=f"ULD '{uld_no}' is not assigned to this flight",
        )

    # count already loaded items for this ULD
    loaded_result = await db.execute(
        select(func.count(ExportSequenceItemUldLoading.id)).where(
            ExportSequenceItemUldLoading.uld_assignment_detail_id == row.uld_assignment_detail_id,
        )
    )
    already_loaded = loaded_result.scalar() or 0

    return UldVerifyForLoadingResponse(
        success=True,
        message=f"ULD '{uld_no}' verified — {already_loaded} items already loaded",
        uld_assignment_detail_id=row.uld_assignment_detail_id,
        uld_id=row.uld_id,
        uld_no=row.uld_no,
        carrier=row.carrier,
        already_loaded=already_loaded,
    )


# ── 2. Scan item into ULD ──────────────────────────────────
# async def scan_item_into_uld(
#     db: AsyncSession,
#     flight_header_id: int,
#     payload: ScanItemIntoUldRequest,
#     loaded_by: str,
# ) -> ScanItemIntoUldResponse:

#     now = get_utc_now()

#     # ── verify flight ──────────────────────────────────────
#     flight = await db.get(ExportFlightBookingHeader, flight_header_id)
#     if not flight or not flight.is_active:
#         raise HTTPException(status_code=404, detail="Flight not found")

#     if flight.flight_dpt_datetime <= now:
#         raise HTTPException(status_code=400, detail="Flight has already departed")

#     # ── verify ULD belongs to this flight ─────────────────
#     uld_detail_result = await db.execute(
#         select(
#             ExportUldAssignmentDetail.id,
#             ExportUldMaster.uld_no,
#         )
#         .join(ExportUldAssignment,
#               ExportUldAssignmentDetail.assignment_id == ExportUldAssignment.id)
#         .join(ExportUldMaster,
#               ExportUldAssignmentDetail.uld_id == ExportUldMaster.id)
#         .where(
#             ExportUldAssignmentDetail.id == payload.uld_assignment_detail_id,
#             ExportUldAssignment.flight_header_id == flight_header_id,
#             ExportUldAssignment.is_active == True,
#         )
#     )
#     uld_detail = uld_detail_result.mappings().first()
#     if not uld_detail:
#         raise HTTPException(status_code=400, detail="ULD does not belong to this flight")

#     # ── fetch all sequences in one query ───────────────────
#     seq_result = await db.execute(
#         select(
#             ExportAwbSkidItemSequence.id.label("sequence_id"),
#             ExportAwbSkidItemSequence.mapping_id,
#             ExportAwbSkidItemSequence.awb_master_id,
#             ExportAwbSkidItemSequence.sequence_no,
#         )
#         .where(ExportAwbSkidItemSequence.sequence_no.in_(payload.sequence_nos))
#     )
#     seq_map = {row.sequence_no: row for row in seq_result.mappings().all()}

#     # ── fetch flight AWB ids in one query ──────────────────
#     flight_awb_result = await db.execute(
#         select(
#             ExportFlightBookingDetail.awb_master_id,
#             ExportCarMessageAwbMaster.awb_no,
#         )
#         .join(ExportCarMessageAwbMaster,
#               ExportFlightBookingDetail.awb_master_id == ExportCarMessageAwbMaster.id)
#         .where(ExportFlightBookingDetail.flight_header_id == flight_header_id)
#     )
#     flight_awb_map = {
#         row.awb_master_id: row.awb_no
#         for row in flight_awb_result.mappings().all()
#     }

#     # ── fetch already loaded sequences in one query ────────
#     already_loaded_result = await db.execute(
#         select(
#             ExportSequenceItemUldLoading.sequence_id,
#             ExportUldMaster.uld_no.label("loaded_uld_no"),
#         )
#         .join(ExportUldAssignmentDetail,
#               ExportSequenceItemUldLoading.uld_assignment_detail_id == ExportUldAssignmentDetail.id)
#         .join(ExportUldMaster,
#               ExportUldAssignmentDetail.uld_id == ExportUldMaster.id)
#         .where(
#             ExportSequenceItemUldLoading.sequence_id.in_(
#                 [s.sequence_id for s in seq_map.values()]
#             )
#         )
#     )
#     already_loaded_map = {
#         row.sequence_id: row.loaded_uld_no
#         for row in already_loaded_result.mappings().all()
#     }

#     # ── process each sequence_no ───────────────────────────
#     to_insert = []
#     results = []

#     for seq_no in payload.sequence_nos:
#         seq = seq_map.get(seq_no)

#         # ── not found in system
#         if not seq:
#             results.append(ScanItemResult(
#                 sequence_no=seq_no,
#                 awb_no="—",
#                 success=False,
#                 message=f"Item '{seq_no}' not found in system",
#             ))
#             continue

#         # ── not part of this flight
#         awb_no = flight_awb_map.get(seq.awb_master_id)
#         if not awb_no:
#             results.append(ScanItemResult(
#                 sequence_no=seq_no,
#                 awb_no="—",
#                 success=False,
#                 message=f"Item '{seq_no}' does not belong to any AWB on this flight",
#             ))
#             continue

#         # ── already loaded in a ULD
#         loaded_uld = already_loaded_map.get(seq.sequence_id)
#         if loaded_uld:
#             results.append(ScanItemResult(
#                 sequence_no=seq_no,
#                 awb_no=awb_no,
#                 success=False,
#                 message=f"Already loaded into ULD {loaded_uld}",
#             ))
#             continue

#         # ── all good — add to insert list
#         to_insert.append(
#             ExportSequenceItemUldLoading(
#                 flight_header_id=flight_header_id,
#                 uld_assignment_detail_id=payload.uld_assignment_detail_id,
#                 sequence_id=seq.sequence_id,
#                 awb_master_id=seq.awb_master_id,
#                 mapping_id=seq.mapping_id,
#                 loaded_by=loaded_by,
#                 loaded_at=now,
#                 created_at=now,
#             )
#         )
#         results.append(ScanItemResult(
#             sequence_no=seq_no,
#             awb_no=awb_no,
#             success=True,
#             message=f"Loaded into ULD {uld_detail.uld_no}",
#         ))

#     # ── bulk insert all valid items ────────────────────────
#     if to_insert:
#         db.add_all(to_insert)
#         await db.commit()

#     total_loaded = sum(1 for r in results if r.success)
#     total_failed = sum(1 for r in results if not r.success)

#     return ScanItemIntoUldResponse(
#         success=True,
#         message=f"{total_loaded} loaded, {total_failed} failed",
#         uld_no=uld_detail.uld_no,
#         total_submitted=len(payload.sequence_nos),
#         total_loaded=total_loaded,
#         total_failed=total_failed,
#         results=results,
#     )

async def scan_item_into_uld(
    db: AsyncSession,
    flight_header_id: int,
    payload: ScanItemIntoUldRequest,
    loaded_by: str,
) -> ScanItemIntoUldResponse:

    now = get_utc_now()

    # ── verify flight ──────────────────────────────────────
    flight = await db.get(ExportFlightBookingHeader, flight_header_id)
    if not flight or not flight.is_active:
        raise HTTPException(status_code=404, detail="Flight not found")

    if flight.flight_dpt_datetime <= now:
        raise HTTPException(status_code=400, detail="Flight has already departed")

    # ── verify ULD belongs to this flight ─────────────────
    uld_detail_result = await db.execute(
        select(
            ExportUldAssignmentDetail.id,
            ExportUldMaster.uld_no,
        )
        .join(ExportUldAssignment,
              ExportUldAssignmentDetail.assignment_id == ExportUldAssignment.id)
        .join(ExportUldMaster,
              ExportUldAssignmentDetail.uld_id == ExportUldMaster.id)
        .where(
            ExportUldAssignmentDetail.id == payload.uld_assignment_detail_id,
            ExportUldAssignment.flight_header_id == flight_header_id,
            ExportUldAssignment.is_active == True,
        )
    )
    uld_detail = uld_detail_result.mappings().first()
    if not uld_detail:
        raise HTTPException(status_code=400, detail="ULD does not belong to this flight")

    # ── fetch all sequences in one query ───────────────────
    seq_result = await db.execute(
        select(
            ExportAwbSkidItemSequence.id.label("sequence_id"),
            ExportAwbSkidItemSequence.mapping_id,
            ExportAwbSkidItemSequence.awb_master_id,
            ExportAwbSkidItemSequence.sequence_no,
        )
        .where(ExportAwbSkidItemSequence.sequence_no.in_(payload.sequence_nos))
    )
    seq_map = {row.sequence_no: row for row in seq_result.mappings().all()}

    # ── fetch flight AWB ids in one query ──────────────────
    flight_awb_result = await db.execute(
        select(
            ExportFlightBookingDetail.awb_master_id,
            ExportCarMessageAwbMaster.awb_no,
        )
        .join(ExportCarMessageAwbMaster,
              ExportFlightBookingDetail.awb_master_id == ExportCarMessageAwbMaster.id)
        .where(ExportFlightBookingDetail.flight_header_id == flight_header_id)
    )
    flight_awb_map = {
        row.awb_master_id: row.awb_no
        for row in flight_awb_result.mappings().all()
    }

    # ── fetch already loaded sequences in one query ────────
    already_loaded_result = await db.execute(
        select(
            ExportSequenceItemUldLoading.sequence_id,
            ExportUldMaster.uld_no.label("loaded_uld_no"),
        )
        .join(ExportUldAssignmentDetail,
              ExportSequenceItemUldLoading.uld_assignment_detail_id == ExportUldAssignmentDetail.id)
        .join(ExportUldMaster,
              ExportUldAssignmentDetail.uld_id == ExportUldMaster.id)
        .where(
            ExportSequenceItemUldLoading.sequence_id.in_(
                [s.sequence_id for s in seq_map.values()]
            )
        )
    )
    already_loaded_map = {
        row.sequence_id: row.loaded_uld_no
        for row in already_loaded_result.mappings().all()
    }

    # ✅ NEW — fetch base drop status for all mappings in one query
    mapping_ids_in_seq = list({s.mapping_id for s in seq_map.values()})

    base_drop_result = await db.execute(
        select(ExportSkidBaseMapping.mapping_id).where(
            ExportSkidBaseMapping.mapping_id.in_(mapping_ids_in_seq)
        )
    ) if mapping_ids_in_seq else None

    base_dropped_mapping_ids = {
        row.mapping_id
        for row in (base_drop_result.all() if base_drop_result else [])
    }

    # ── process each sequence_no ───────────────────────────
    to_insert = []
    results = []

    for seq_no in payload.sequence_nos:
        seq = seq_map.get(seq_no)

        # ── not found in system
        if not seq:
            results.append(ScanItemResult(
                sequence_no=seq_no,
                awb_no="—",
                success=False,
                message=f"Item '{seq_no}' not found in system",
            ))
            continue

        # ── not part of this flight
        awb_no = flight_awb_map.get(seq.awb_master_id)
        if not awb_no:
            results.append(ScanItemResult(
                sequence_no=seq_no,
                awb_no="—",
                success=False,
                message=f"Item '{seq_no}' does not belong to any AWB on this flight",
            ))
            continue

        # ✅ NEW — skid not dropped at base yet
        if seq.mapping_id not in base_dropped_mapping_ids:
            results.append(ScanItemResult(
                sequence_no=seq_no,
                awb_no=awb_no,
                success=False,
                message=f"Item '{seq_no}' cannot be loaded — skid has not been dropped at base yet",
            ))
            continue

        # ── already loaded in a ULD
        loaded_uld = already_loaded_map.get(seq.sequence_id)
        if loaded_uld:
            results.append(ScanItemResult(
                sequence_no=seq_no,
                awb_no=awb_no,
                success=False,
                message=f"Already loaded into ULD {loaded_uld}",
            ))
            continue

        # ── all good — add to insert list
        to_insert.append(
            ExportSequenceItemUldLoading(
                flight_header_id=flight_header_id,
                uld_assignment_detail_id=payload.uld_assignment_detail_id,
                sequence_id=seq.sequence_id,
                awb_master_id=seq.awb_master_id,
                mapping_id=seq.mapping_id,
                loaded_by=loaded_by,
                loaded_at=now,
                created_at=now,
            )
        )
        results.append(ScanItemResult(
            sequence_no=seq_no,
            awb_no=awb_no,
            success=True,
            message=f"Loaded into ULD {uld_detail.uld_no}",
        ))

    # ── bulk insert all valid items ────────────────────────
    if to_insert:
        db.add_all(to_insert)
        await db.commit()

    total_loaded = sum(1 for r in results if r.success)
    total_failed = sum(1 for r in results if not r.success)

    return ScanItemIntoUldResponse(
        success=True,
        message=f"{total_loaded} loaded, {total_failed} failed",
        uld_no=uld_detail.uld_no,
        total_submitted=len(payload.sequence_nos),
        total_loaded=total_loaded,
        total_failed=total_failed,
        results=results,
    )


# ── 3. Get loading status ──────────────────────────────────
async def get_flight_uld_loading_status(
    db: AsyncSession,
    flight_header_id: int,
) -> FlightUldLoadingStatusResponse:

    # ── fetch flight ───────────────────────────────────────
    flight = await db.get(ExportFlightBookingHeader, flight_header_id)
    if not flight or not flight.is_active:
        raise HTTPException(status_code=404, detail="Flight not found")

    # ── fetch all AWBs with booked pcs ─────────────────────
    awb_result = await db.execute(
        select(
            ExportFlightBookingDetail.awb_master_id,
            ExportFlightBookingDetail.booked_pcs,
            ExportCarMessageAwbMaster.awb_no,
        )
        .join(ExportCarMessageAwbMaster,
              ExportFlightBookingDetail.awb_master_id == ExportCarMessageAwbMaster.id)
        .where(ExportFlightBookingDetail.flight_header_id == flight_header_id)
    )
    awb_rows = awb_result.mappings().all()

    awb_ids = [r.awb_master_id for r in awb_rows]
    total_to_load = sum(r.booked_pcs for r in awb_rows)

    # ✅ ADD HERE — after awb_ids, before loaded_per_awb query
    # ── fetch all mapping_ids for AWBs on this flight ──────────
    mapping_ids_result = await db.execute(
        select(ExportAwbSkidMapping.id.label("mapping_id")).where(
            ExportAwbSkidMapping.awb_master_id.in_(awb_ids)
        )
    ) if awb_ids else None

    all_mapping_ids = [
        row.mapping_id
        for row in (mapping_ids_result.all() if mapping_ids_result else [])
    ]

    # ── which of those mappings have been dropped at base ──────
    base_drop_result = await db.execute(
        select(ExportSkidBaseMapping.mapping_id).where(
            ExportSkidBaseMapping.mapping_id.in_(all_mapping_ids)
        )
    ) if all_mapping_ids else None

    base_dropped_mapping_ids = {
        row.mapping_id
        for row in (base_drop_result.all() if base_drop_result else [])
    }

    # ── loaded pcs per AWB ─────────────────────────────────
    loaded_per_awb_result = await db.execute(
        select(
            ExportSequenceItemUldLoading.awb_master_id,
            func.count(ExportSequenceItemUldLoading.id).label("loaded_pcs"),
        )
        .where(
            ExportSequenceItemUldLoading.flight_header_id == flight_header_id,
            ExportSequenceItemUldLoading.awb_master_id.in_(awb_ids),
        )
        .group_by(ExportSequenceItemUldLoading.awb_master_id)
    )
    loaded_per_awb = {
        r.awb_master_id: r.loaded_pcs
        for r in loaded_per_awb_result.mappings().all()
    }

    # ── loaded pcs per ULD ─────────────────────────────────
    uld_result = await db.execute(
        select(
            ExportUldAssignmentDetail.id.label("uld_assignment_detail_id"),
            ExportUldMaster.id.label("uld_id"),
            ExportUldMaster.uld_no,
            ExportUldMaster.carrier,
            func.count(ExportSequenceItemUldLoading.id).label("loaded_count"),
        )
        .join(ExportUldAssignment,
              ExportUldAssignmentDetail.assignment_id == ExportUldAssignment.id)
        .join(ExportUldMaster,
              ExportUldAssignmentDetail.uld_id == ExportUldMaster.id)
        .outerjoin(ExportSequenceItemUldLoading,
              ExportSequenceItemUldLoading.uld_assignment_detail_id == ExportUldAssignmentDetail.id)
        .where(
            ExportUldAssignment.flight_header_id == flight_header_id,
            ExportUldAssignment.is_active == True,
        )
        .group_by(
            ExportUldAssignmentDetail.id,
            ExportUldMaster.id,
            ExportUldMaster.uld_no,
            ExportUldMaster.carrier,
        )
    )
    uld_rows = uld_result.mappings().all()

    total_loaded = sum(r.loaded_count for r in uld_rows)


    # ── fetch all loaded sequences per ULD to show in screen which are scanned already ────────────────────
    uld_detail_ids = [r.uld_assignment_detail_id for r in uld_rows]

    sequences_result = await db.execute(
        select(
            ExportSequenceItemUldLoading.uld_assignment_detail_id,
            ExportSequenceItemUldLoading.sequence_id,
            ExportSequenceItemUldLoading.awb_master_id,
            ExportSequenceItemUldLoading.loaded_by,
            ExportSequenceItemUldLoading.loaded_at,
            ExportAwbSkidItemSequence.sequence_no,
            ExportCarMessageAwbMaster.awb_no,
        )
        .join(
            ExportAwbSkidItemSequence,
            ExportSequenceItemUldLoading.sequence_id == ExportAwbSkidItemSequence.id,
        )
        .join(
            ExportCarMessageAwbMaster,
            ExportSequenceItemUldLoading.awb_master_id == ExportCarMessageAwbMaster.id,
        )
        .where(
            ExportSequenceItemUldLoading.flight_header_id == flight_header_id,
            ExportSequenceItemUldLoading.uld_assignment_detail_id.in_(uld_detail_ids),
        )
        .order_by(ExportSequenceItemUldLoading.loaded_at.asc())
    ) if uld_detail_ids else None

    sequences_rows = sequences_result.mappings().all() if sequences_result else []

    # group sequences by uld_assignment_detail_id
    sequences_by_uld: dict[int, list] = {}
    for seq in sequences_rows:
        sequences_by_uld.setdefault(seq.uld_assignment_detail_id, []).append({
            "sequence_id": seq.sequence_id,
            "sequence_no": seq.sequence_no,
            "awb_master_id": seq.awb_master_id,
            "awb_no": seq.awb_no,
            "loaded_by": seq.loaded_by,
            "loaded_at": seq.loaded_at,
        })


    # ── fetch ALL scanned sequences for this flight ────────────
    # all sequences belonging to AWBs booked on this flight
    # regardless of ULD loading status
    all_sequences_result = await db.execute(
        select(
            ExportAwbSkidItemSequence.id.label("sequence_id"),
            ExportAwbSkidItemSequence.sequence_no,
            ExportAwbSkidItemSequence.awb_master_id,
            ExportAwbSkidItemSequence.mapping_id,
            ExportAwbSkidItemSequence.sequence_date_time,
            ExportAwbSkidItemSequence.scanned_by,
            ExportAwbSkidItemSequence.scan_by_device,
            ExportCarMessageAwbMaster.awb_no,
            # ✅ is it loaded into ULD or not
            ExportSequenceItemUldLoading.id.label("loading_id"),
            ExportSequenceItemUldLoading.uld_assignment_detail_id,
            ExportSequenceItemUldLoading.loaded_by,
            ExportSequenceItemUldLoading.loaded_at,
        )
        .join(
            ExportCarMessageAwbMaster,
            ExportAwbSkidItemSequence.awb_master_id == ExportCarMessageAwbMaster.id,
        )
        .outerjoin(                                      # ← outerjoin — include unloaded too
            ExportSequenceItemUldLoading,
            and_(
                ExportSequenceItemUldLoading.sequence_id == ExportAwbSkidItemSequence.id,
                ExportSequenceItemUldLoading.flight_header_id == flight_header_id,
            ),
        )
        .where(
            ExportAwbSkidItemSequence.awb_master_id.in_(awb_ids),  # scoped to flight AWBs
        )
        .order_by(ExportAwbSkidItemSequence.sequence_date_time.asc())
    ) if awb_ids else None

    all_sequences_rows = all_sequences_result.mappings().all() if all_sequences_result else []

    # build flat list with loading status per sequence
    all_sequences = [
        {
            "sequence_id": row.sequence_id,
            "sequence_no": row.sequence_no,
            "awb_master_id": row.awb_master_id,
            "awb_no": row.awb_no,
            "mapping_id": row.mapping_id,
            "sequence_date_time": row.sequence_date_time,
            "scanned_by": row.scanned_by,
            "scan_by_device": row.scan_by_device,
            "is_loaded": row.loading_id is not None,                          # ← True/False
            "uld_assignment_detail_id": row.uld_assignment_detail_id,         # ← None if not loaded
            "loaded_by": row.loaded_by,
            "loaded_at": row.loaded_at,
            # ✅ ADD — frontend uses this to block scan attempt
           "is_eligible_to_load": (
    row.loading_id is None
    and row.mapping_id in base_dropped_mapping_ids
),
"ineligible_reason": (
    "Already loaded into ULD"
    if row.loading_id is not None
    else "Skid not dropped at base yet"
    if row.mapping_id not in base_dropped_mapping_ids
    else None    # ← eligible — no reason needed
),
        }
        for row in all_sequences_rows
    ]

    total_scanned = len(all_sequences)
    total_loaded_sequences = sum(1 for s in all_sequences if s["is_loaded"])
    total_pending_sequences = total_scanned - total_loaded_sequences

    # ── build response ─────────────────────────────────────
    awb_status = [
        AwbLoadingStatusItem(
            awb_master_id=r.awb_master_id,
            awb_no=r.awb_no,
            booked_pcs=r.booked_pcs,
            loaded_pcs=loaded_per_awb.get(r.awb_master_id, 0),
            pending_pcs=r.booked_pcs - loaded_per_awb.get(r.awb_master_id, 0),
        )
        for r in awb_rows
    ]

    uld_status = [
        UldLoadingStatusItem(
            uld_assignment_detail_id=r.uld_assignment_detail_id,
            uld_id=r.uld_id,
            uld_no=r.uld_no,
            carrier=r.carrier,
            loaded_count=r.loaded_count,
            sequences=sequences_by_uld.get(r.uld_assignment_detail_id, []),  # ← ADD
        )
        for r in uld_rows
    ]

    return FlightUldLoadingStatusResponse(
        success=True,
        message=f"{total_loaded}/{total_to_load} items loaded",
        flight_header_id=flight.id,
        flight_no=flight.flight_no,
        flight_date=flight.flight_date,
        flight_dpt_datetime=flight.flight_dpt_datetime,
        total_to_load=total_to_load,
        total_loaded=total_loaded,
        total_pending=total_to_load - total_loaded,

         total_scanned=total_scanned,                        # ← ADD
        total_loaded_sequences=total_loaded_sequences,      # ← ADD
        total_pending_sequences=total_pending_sequences,    # ← ADD

        is_fully_loaded=total_loaded >= total_to_load,
        ulds=uld_status,
        awbs=awb_status,
        all_sequences=all_sequences,                        # ← ADD
    )