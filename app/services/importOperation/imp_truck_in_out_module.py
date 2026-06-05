from datetime import datetime, date, time, timedelta, timezone
import os
from zoneinfo import ZoneInfo
import pytz
from typing import Any, Dict, List, Optional
from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import cast, Date, exists, func, or_, update
from sqlalchemy.future import select
from app.api.routes.domesticOperation.domestic_xray_report import (
    convert_ist_day_to_utc_range,
)
from app.db.models.importOperation.import_release_report import IrrReport
from app.db.models.importOperation.imp_truck_in_out_module import (
    ImportGatePass,
    ImportGatePassAssignment,
    ImportGatePassLoading,
    ImportTruckInStaging,
    ImportTruckVisit,
)
from app.db.models.importOperation.worker_assignment import (
    WorkerAssignmentHeader,
    WorkerAssignmentShipment,
)
from app.db.models.user import User
from app.schemas.importOperation.imp_truck_in_out_module import (
    GatePassCheckRequest,
    GatePassCheckResponse,
    TruckStagingRequest,
    TruckStagingResponse,
)
from app.services.app_config.app_config_service import AppConfigService
from app.services.export_manual_slot_service import generate_token_number

# from dotenv import load_dotenv
import logging

from app.services.importOperation.Imp_truck_in_out_activity_log import (
    log_activity_of_imp_truck_in_out,
)

# from app.utils.common.helperFunction import save_to_dial_ftp


logger = logging.getLogger(__name__)

# Load environment variables
# load_dotenv(dotenv_path=os.path.join(os.path.dirname(__file__), '..', '.env'))

# ============================= ✌️Utils for generating queue number ===================

# async def generate_queue_number(db: AsyncSession) -> str:
#     now_ist = datetime.now(ZoneInfo('Asia/Kolkata'))
#     today_prefix = f"{now_ist.strftime('%d%m%y%H%M')}"
#     count_result = await db.execute(
#         select(ImportTruckVisit.queue_no).where(
#             ImportTruckVisit.queue_no.like(f"{today_prefix}%")
#         )
#     )
#     db_count = len(count_result.scalars().all())
#     seq = str(db_count + 1).zfill(3)
#     return f"{today_prefix}{seq}"


def _fmt_duration(hours: float) -> str:
    """0.5 → '30 min', 1.33 → '1 hr 20 min', 2 → '2 hr'."""
    total_min = round(abs(hours) * 60)
    if total_min < 1:
        return f"{max(1, round(abs(hours) * 3600))} sec"
    h, m = divmod(total_min, 60)
    if h == 0:
        return f"{m} min"
    if m == 0:
        return f"{h} hr"
    return f"{h} hr {m} min"

def _visit_label(visit: ImportTruckVisit | None) -> str:
            if not visit:
                return "another visit"
            if getattr(visit, "visit_type", "TRUCK") == "BY_HAND":
                who = visit.driver_name or "someone"
                return f"a by-hand pickup ({who})"
            return f"truck {visit.truck_number or 'unknown'}"


async def generate_queue_number(db: AsyncSession) -> str:
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))
    full_prefix = f"{now_ist.strftime('%d%m%y%H%M')}"  # DDMMYYHHMM — used in the number
    date_prefix = f"{now_ist.strftime('%d%m%y')}"  # DDMMYY — used only for counting

    count_result = await db.execute(
        select(ImportTruckVisit.queue_no).where(
            ImportTruckVisit.queue_no.like(
                f"{date_prefix}%"
            )  # ← count all queues for today
        )
    )
    db_count = len(count_result.scalars().all())
    seq = str(db_count + 1).zfill(3)
    return f"{full_prefix}{seq}"  # ← DDMMYYHHMM + daily sequences


# ==============================================


def get_env_variable(name: str, cast_type: type = str) -> any:
    """Get environment variable or raise error if missing, with type casting."""
    value = os.getenv(name)
    if value is None:
        raise EnvironmentError(f"Missing environment variable: {name}")
    try:
        return cast_type(value)
    except ValueError:
        raise EnvironmentError(
            f"Invalid value for {name}: expected {cast_type.__name__}"
        )


def convert_to_ist_datetime(dt, ist_timezone) -> str:
    """
    Convert datetime to IST and format as DDMMYYYYHHMM.

    Args:
        dt: datetime object (can be naive or aware)
        ist_timezone: pytz timezone object

    Returns:
        str: Formatted datetime string (DDMMYYYYHHMM)
    """
    if not dt:
        return ""

    try:
        # Handle naive datetime (assume UTC)
        if dt.tzinfo is None:
            dt_utc = pytz.utc.localize(dt)
        else:
            dt_utc = dt.astimezone(pytz.utc)

        # Convert to IST
        dt_ist = dt_utc.astimezone(ist_timezone)
        return dt_ist.strftime("%d%m%Y%H%M")

    except Exception as e:
        print(f"⚠️ Error converting datetime: {e}")
        return ""


def convert_to_ist_date(dt, ist_timezone) -> str:
    """
    Convert datetime to IST and format as DD-MMM-YY.

    Args:
        dt: datetime object
        ist_timezone: pytz timezone object

    Returns:
        str: Formatted date string (DD-MMM-YY)
    """
    if not dt:
        return ""

    try:
        # Handle naive datetime (assume UTC)
        if dt.tzinfo is None:
            dt_utc = pytz.utc.localize(dt)
        else:
            dt_utc = dt.astimezone(pytz.utc)

        # Convert to IST
        dt_ist = dt_utc.astimezone(ist_timezone)
        return dt_ist.strftime("%d-%b-%y").upper()

    except Exception as e:
        print(f"⚠️ Error converting date: {e}")
        return ""


class ImportTruckInOutService:


    @staticmethod
    async def check_gate_pass_validity(
        db: AsyncSession, request: GatePassCheckRequest
    ) -> GatePassCheckResponse:
        """
        Validate if a gate pass exists and can be assigned.
        Rules:
        1. New GP: Always allow if exists in IRR
        2. Existing GP with pcs_remaining > 0: Allow reassignment
        3. Existing GP with pcs_remaining = 0: Block
        4. Prevent duplicate in staging
        5. Prevent reassignment if active assignment exists but not yet loaded/unloaded
        """
        print(f"🔍 Validating gate pass: {request}")
        # 1️⃣ Check staging duplicate
        staging_stmt = select(ImportTruckInStaging).where(
            ImportTruckInStaging.gate_pass_no == request.gate_pass_no
        )
        staging_result = await db.execute(staging_stmt)
        staging_record = staging_result.scalar_one_or_none()

        if staging_record:
            raise HTTPException(
                status_code=400,
                detail=f"Gate pass {request.gate_pass_no} already exists in staging. Preventing duplicate assignment.",
            )

        # 2️⃣ Check if gate pass exists in system
        gp_stmt = select(ImportGatePass).where(
            ImportGatePass.gate_pass_no == request.gate_pass_no
        )
        gp_result = await db.execute(gp_stmt)
        existing_gate_pass = gp_result.scalar_one_or_none()

        if existing_gate_pass:

            # ═══════════════════════════════════════════════════════════════════
            # ⬇️ ADD HERE — same-truck check (only when truck_visit_id provided)
            # ═══════════════════════════════════════════════════════════════════
            if request.current_truck_visit_id is not None:
                prior_stmt = select(ImportGatePassAssignment).where(
                    ImportGatePassAssignment.gate_pass_id == existing_gate_pass.id,
                    ImportGatePassAssignment.truck_visit_id
                    == request.current_truck_visit_id,
                )
                prior = (await db.execute(prior_stmt)).scalars().first()

                if prior:
                    load_count_stmt = (
                        select(func.count())
                        .select_from(ImportGatePassLoading)
                        .where(
                            ImportGatePassLoading.gate_pass_id == existing_gate_pass.id,
                            ImportGatePassLoading.truck_visit_id
                            == request.current_truck_visit_id,
                        )
                    )
                    load_count = (await db.execute(load_count_stmt)).scalar() or 0

                    if load_count > 0:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Gate pass {request.gate_pass_no} already loaded on this truck. Remaining pcs must go to a different truck.",
                        )
                    else:
                        raise HTTPException(
                            status_code=400,
                            detail=f"Gate pass {request.gate_pass_no} already assigned to this truck.",
                        )
            # ═══════════════════════════════════════════════════════════════════
            # ⬆️ END of new block
            # ═══════════════════════════════════════════════════════════════════

            # Block if fully consumed
            if existing_gate_pass.pcs_remaining <= 0:
                raise HTTPException(
                    status_code=400,
                    detail=f"Gate pass {request.gate_pass_no} fully consumed (0 pcs remaining)",
                )

            # Check active assignment
            active_assign_stmt = select(ImportGatePassAssignment).where(
                ImportGatePassAssignment.gate_pass_id == existing_gate_pass.id,
                ImportGatePassAssignment.is_active == True,
            )
            active_assign_result = await db.execute(active_assign_stmt)
            active_assignment = active_assign_result.scalar_one_or_none()

            if active_assignment:
                # Check loading records for this assignment
                load_stmt = select(ImportGatePassLoading).where(
                    ImportGatePassLoading.gate_pass_id == existing_gate_pass.id,
                    ImportGatePassLoading.truck_visit_id
                    == active_assignment.truck_visit_id,
                )
                load_result = await db.execute(load_stmt)
                loading_record = load_result.scalar_one_or_none()

                if loading_record:
                    if existing_gate_pass.pcs_remaining < existing_gate_pass.pcs_total:
                        # ✅ Partial loading already done → allow reassignment of remaining pcs
                        pass
                    else:
                        # ❌ Loading started but nothing consumed yet → block reassignment
                        truck_stmt = select(ImportTruckVisit).where(
                            ImportTruckVisit.id == active_assignment.truck_visit_id
                        )
                        truck_result = await db.execute(truck_stmt)
                        truck = truck_result.scalar_one_or_none()

                        # raise HTTPException(
                        #     status_code=400,
                        #     detail=f"Gate pass {request.gate_pass_no} loading in progress on truck "
                        #     f"{truck.truck_number if truck else 'unknown'}. Complete or cancel current loading first.",
                        # )

                        raise HTTPException(
                            status_code=400,
                            detail=(
                                f"Gate pass {request.gate_pass_no} loading in progress on "
                                f"{_visit_label(truck)}. Complete or cancel current loading first."
                            ),
                        )
                else:
                    # ❌ Assigned but no loading record yet → block reassignment until unloaded or GP Out
                    truck_stmt = select(ImportTruckVisit).where(
                        ImportTruckVisit.id == active_assignment.truck_visit_id
                    )
                    truck_result = await db.execute(truck_stmt)
                    truck = truck_result.scalar_one_or_none()

                    # raise HTTPException(
                    #     status_code=400,
                    #     detail=f"Gate pass {request.gate_pass_no} already assigned on truck "
                    #     f"{truck.truck_number if truck else 'unknown'}. Reassignment not allowed until GP Out.",
                    # )
                    raise HTTPException(
                        status_code=400,
                        detail=(
                            f"Gate pass {request.gate_pass_no} is already assigned to "
                            f"{_visit_label(truck)}. Reassignment is not allowed until it is GP out."
                        ),
                    )

        # 3️⃣ Validate against IRR Report (new GP case)
        # NEW
        was_stmt = (
            select(WorkerAssignmentShipment, WorkerAssignmentHeader)
            .join(
                WorkerAssignmentHeader,
                WorkerAssignmentShipment.assignment_header_id
                == WorkerAssignmentHeader.id,
            )
            .where(WorkerAssignmentShipment.gate_pass_no == request.gate_pass_no)
        )
        was_result = await db.execute(was_stmt)
        was_row = was_result.first()

        if not was_row:
            return GatePassCheckResponse(
                valid=False,
                message="Invalid gate pass - not found in system",
                gate_pass_no=request.gate_pass_no,
            )

        shipment, header = was_row

        # 4️⃣ Build message
        message = "Gate pass is valid"
        if (
            existing_gate_pass
            and existing_gate_pass.pcs_remaining < existing_gate_pass.pcs_total
        ):
            loaded_pcs = existing_gate_pass.pcs_total - existing_gate_pass.pcs_remaining
            message = f"Gate pass partially loaded ({loaded_pcs}/{existing_gate_pass.pcs_total} pcs). {existing_gate_pass.pcs_remaining} pcs available for assignment."

        # return GatePassCheckResponse(
        #     valid=True,
        #     message=message,
        #     gate_pass_no=shipment.gate_pass_no,
        #     agent=shipment.agent_name,
        #     consignee=shipment.customer_name,
        #     pcs=existing_gate_pass.pcs_remaining if existing_gate_pass else shipment.no_of_pc,
        #     grg_wt=shipment.weight_in_kgs,
        #     issued_date=shipment.gate_pass_issued_date_time_combo,
        #     gate_pass_released_by=shipment.verified_by
        # )

        return GatePassCheckResponse(
            valid=True,
            message=message,
            gate_pass_no=shipment.gate_pass_no,
            agent=shipment.agent_name,
            consignee=shipment.customer_name,
            pcs=(
                existing_gate_pass.pcs_remaining
                if existing_gate_pass
                else shipment.no_of_pc
            ),
            grg_wt=shipment.weight_in_kgs,
            issued_date=shipment.gate_pass_issued_date_time_combo,
            gate_pass_released_by=shipment.verified_by,
            # NEW
            final_delivery_datetime=shipment.final_delivery_datetime,
            final_delivery_by_person=shipment.final_delivery_by_person,
            gate_pass_end_datetime=shipment.gate_pass_end_datetime,
            drop_dlv_zone=shipment.drop_dlv_zone,
           lift_out_zone=shipment.unloading_from_lift_zone, 
              dlv_zone_from_irr=shipment.dlv_zone_from_irr,    
        )

    @staticmethod
    async def list_trucks_by_date(db: AsyncSession, target_date: date = None):
        """List all trucks for a given date with their gate passes ordered:
        - Not GP Out on top
        - Then the rest
        - Descending by assignment time inside each group
        - Trucks with any not-out gate pass appear first
        """
        if target_date is None:
            target_date = date.today()

        start_utc, end_utc = convert_ist_day_to_utc_range(target_date)

        # Fetch truck visits for the day where truck is in
        stmt = select(ImportTruckVisit).where(
            ImportTruckVisit.truck_slot_from >= start_utc,
            ImportTruckVisit.truck_slot_from <= end_utc,
            ImportTruckVisit.is_truck_in == True,
        )
        result = await db.execute(stmt)
        truck_visits = result.scalars().all()

        if not truck_visits:
            return {
                "success": True,
                "count": 0,
                "date": str(target_date),
                "trucks": [],
                "message": f"No trucks found for {target_date}",
            }

        trucks_data = []

        for visit in truck_visits:
            # Fetch ALL assignments (active and inactive) for history
            assign_stmt = select(ImportGatePassAssignment).where(
                ImportGatePassAssignment.truck_visit_id == visit.id
            )
            assign_result = await db.execute(assign_stmt)
            assignments = assign_result.scalars().all()

            gate_passes = []
            latest_assigned_time = None
            has_any_not_gp_out = False

            for assignment in assignments:
                gp_stmt = select(ImportGatePass).where(
                    ImportGatePass.id == assignment.gate_pass_id
                )
                gp_result = await db.execute(gp_stmt)
                gate_pass = gp_result.scalar_one_or_none()

                if not gate_pass:
                    continue

                # Track latest assignment time per truck for truck-level ordering
                if assignment.assigned_time and (
                    latest_assigned_time is None
                    or assignment.assigned_time > latest_assigned_time
                ):
                    latest_assigned_time = assignment.assigned_time

                # Determine gp_out state for ordering
                gp_out_done = gate_pass.gate_pass_out_date_time is not None
                if not gp_out_done:
                    has_any_not_gp_out = True

                # 🔎 Fetch loading record for this gate pass + truck
                load_stmt = select(ImportGatePassLoading).where(
                    ImportGatePassLoading.gate_pass_id == gate_pass.id,
                    ImportGatePassLoading.truck_visit_id == assignment.truck_visit_id,
                )
                load_result = await db.execute(load_stmt)
                loading_record = load_result.scalar_one_or_none()

                gate_passes.append(
                    {
                        "gate_pass_no": gate_pass.gate_pass_no,
                        "awb": getattr(gate_pass, "awb_no", None),
                        "hawb": getattr(gate_pass, "hawb_no", None),
                        "pcs": gate_pass.pcs_total,
                        "pcs_remaining": gate_pass.pcs_remaining,
                        "assigned_time": assignment.assigned_time,
                        "assigned_by": assignment.assigned_by,
                        # "gate_pass_out_time": gate_pass.gate_pass_out_date_time,
                        "gate_pass_out_time": (
                            loading_record.loaded_time if loading_record else None
                        ),
                        "pcs_loaded": (
                            loading_record.loaded_pcs if loading_record else 0
                        ),
                        "gate_pass_out_by": (
                            loading_record.loaded_by if loading_record else None
                        ),
                        "assigned_truck_visit_id": assignment.truck_visit_id,
                        "is_active_assignment": assignment.is_active,
                    }
                )

            # Order gate passes:
            # 1) Not GP Out first
            # 2) Then by assigned_time descending
            gate_passes = sorted(
                gate_passes,
                key=lambda gp: (
                    (
                        1 if gp["gate_pass_out_time"] is not None else 0
                    ),  # 0 = not out -> first
                    (
                        gp["assigned_time"]
                        if gp["assigned_time"] is not None
                        else datetime.min
                    ),
                ),
                reverse=False,  # because first key ascending (0 before 1), second key we’ll invert below
            )
            # For the second key (assigned_time) we want descending; achieve by reverse on a stable sort:
            gate_passes = sorted(
                gate_passes,
                key=lambda gp: (
                    gp["assigned_time"]
                    if gp["assigned_time"] is not None
                    else datetime.min
                ),
                reverse=True,
            )

            trucks_data.append(
                {
                    "truck_visit_id": visit.id,
                    "truck_number": visit.truck_number,
                    "driver_name": visit.driver_name,
                    "driver_contact": visit.driver_contact,
                    "token_no": visit.token_no,
                    "status": visit.status,
                    "queue_no": visit.queue_no,
                    "gate_passes": gate_passes,
                    "truck_in_date_time": visit.truck_in_date_time,
                    "truck_out_date_time": visit.truck_out_date_time,
                    # For top-level ordering
                    "_has_any_not_gp_out": has_any_not_gp_out,
                    "_latest_assigned_time": latest_assigned_time or datetime.min,
                }
            )

        # Order trucks:
        # 1) Trucks with any not-out gate pass first
        # 2) Then by latest_assigned_time descending
        trucks_data = sorted(
            trucks_data,
            key=lambda t: (
                0 if t["_has_any_not_gp_out"] else 1,  # 0 first if has not-out
                t["_latest_assigned_time"],
            ),
            reverse=False,
        )
        trucks_data = sorted(
            trucks_data, key=lambda t: t["_latest_assigned_time"], reverse=True
        )

        # Strip internal ordering keys from the final response
        for t in trucks_data:
            t.pop("_has_any_not_gp_out", None)
            t.pop("_latest_assigned_time", None)

        return {
            "success": True,
            "count": len(trucks_data),
            "date": str(target_date),
            "trucks": trucks_data,
            "message": f"Found {len(trucks_data)} trucks for {target_date}",
        }

    @staticmethod
    async def list_queued_trucks_by_date(db: AsyncSession, target_date: date = None):
        """
        List all QUEUED trucks for a given IST date.
        Ordered by queued_at ascending (earliest queued first).
        """
        if target_date is None:
            target_date = date.today()

        # Convert IST date to UTC range
        IST = ZoneInfo("Asia/Kolkata")
        UTC = ZoneInfo("UTC")
        start_ist = datetime.combine(target_date, time.min, tzinfo=IST)
        end_ist = datetime.combine(target_date, time.max, tzinfo=IST)
        day_start_utc = start_ist.astimezone(UTC)
        day_end_utc = end_ist.astimezone(UTC)

        stmt = (
            select(ImportTruckVisit)
            .where(
                ImportTruckVisit.status == "QUEUED",
                ImportTruckVisit.queued_at >= day_start_utc,
                ImportTruckVisit.queued_at <= day_end_utc,
            )
            .order_by(ImportTruckVisit.queued_at.asc())
        )

        result = await db.execute(stmt)
        truck_visits = result.scalars().all()

        if not truck_visits:
            return {
                "success": True,
                "count": 0,
                "date": str(target_date),
                "trucks": [],
                "message": f"No queued trucks found for {target_date}",
            }

        trucks_data = []

        for visit in truck_visits:
            assign_stmt = select(ImportGatePassAssignment).where(
                ImportGatePassAssignment.truck_visit_id == visit.id,
                ImportGatePassAssignment.is_active == True,
            )
            assign_result = await db.execute(assign_stmt)
            assignments = assign_result.scalars().all()

            gate_passes = []
            for assignment in assignments:
                gp_stmt = select(ImportGatePass).where(
                    ImportGatePass.id == assignment.gate_pass_id
                )
                gp_result = await db.execute(gp_stmt)
                gate_pass = gp_result.scalar_one_or_none()

                if not gate_pass:
                    continue

                gate_passes.append(
                    {
                        "gate_pass_no": gate_pass.gate_pass_no,
                        "awb": gate_pass.awb_no,
                        "hawb": gate_pass.hawb_no,
                        "pcs": gate_pass.pcs_total,
                        "pcs_loaded": 0,
                        "pcs_remaining": gate_pass.pcs_remaining,
                        "assigned_time": assignment.assigned_time,
                        "assigned_by": assignment.assigned_by,
                        "assigned_truck_visit_id": assignment.truck_visit_id,
                        "is_active_assignment": assignment.is_active,
                    }
                )

            trucks_data.append(
                {
                    "truck_visit_id": visit.id,
                    "truck_number": visit.truck_number,
                    "driver_name": visit.driver_name,
                    "driver_contact": visit.driver_contact,
                    "token_no": visit.token_no,
                    "status": visit.status,
                    "queue_no": visit.queue_no,
                    "queued_at": visit.queued_at,
                    "queued_by": visit.queued_by,
                    "gate_passes": gate_passes,
                }
            )

        return {
            "success": True,
            "count": len(trucks_data),
            "date": str(target_date),
            "trucks": trucks_data,
            "message": f"Found {len(trucks_data)} queued trucks for {target_date}",
        }

    @staticmethod
    async def list_trucks_by_list_type_and_date(
        db: AsyncSession,
        list_type: str,
        target_date: date = None,
    ):
        """
        Returns full data for the requested list_type,
        plus lightweight counts for both truck_in and truck_out for the date.
        """
        if target_date is None:
            target_date = date.today()

        list_type = (list_type or "").strip().lower()
        if list_type not in ("truck_in", "truck_out"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid list_type '{list_type}'. Must be 'truck_in' or 'truck_out'.",
            )

        start_utc, end_utc = convert_ist_day_to_utc_range(target_date)

        # ── 1. Lightweight counts for BOTH tabs (cheap aggregate queries) ─────────
        # Count of trucks that checked IN on this date AND still inside (pending)
        pending_count_stmt = (
            select(func.count())
            .select_from(ImportTruckVisit)
            .where(
                ImportTruckVisit.is_truck_in == True,
                ImportTruckVisit.is_truck_out == False,
                ImportTruckVisit.truck_in_date_time >= start_utc,
                ImportTruckVisit.truck_in_date_time <= end_utc,
            )
        )
        pending_count = (await db.execute(pending_count_stmt)).scalar() or 0

        # Count of trucks that checked OUT on this date
        out_count_stmt = (
            select(func.count())
            .select_from(ImportTruckVisit)
            .where(
                ImportTruckVisit.is_truck_out == True,
                ImportTruckVisit.truck_out_date_time >= start_utc,
                ImportTruckVisit.truck_out_date_time <= end_utc,
            )
        )
        out_count = (await db.execute(out_count_stmt)).scalar() or 0

        # ── 2. Full data ONLY for the requested list_type ─────────────────────────
        if list_type == "truck_out":
            stmt = (
                select(ImportTruckVisit)
                .where(
                    ImportTruckVisit.is_truck_out == True,
                    ImportTruckVisit.truck_out_date_time >= start_utc,
                    ImportTruckVisit.truck_out_date_time <= end_utc,
                )
                .order_by(ImportTruckVisit.truck_out_date_time.desc())
            )
        else:
            # truck_in → trucks that checked in on this date, still inside
            # (Filter out already-out trucks since they'll appear in truck_out list)
            stmt = (
                select(ImportTruckVisit)
                .where(
                    ImportTruckVisit.is_truck_in == True,
                    ImportTruckVisit.is_truck_out == False,  # ← only pending
                    ImportTruckVisit.truck_in_date_time >= start_utc,
                    ImportTruckVisit.truck_in_date_time <= end_utc,
                )
                .order_by(ImportTruckVisit.truck_in_date_time.desc())
            )

        result = await db.execute(stmt)
        truck_visits = result.scalars().all()

        # ── 3. Build truck data ────────────────────────────────────────────────────
        trucks_data = []

        for visit in truck_visits:
            assign_stmt = select(ImportGatePassAssignment).where(
                ImportGatePassAssignment.truck_visit_id == visit.id
            )
            assignments = (await db.execute(assign_stmt)).scalars().all()

            gate_passes = []

            for assignment in assignments:
                gp_stmt = select(ImportGatePass).where(
                    ImportGatePass.id == assignment.gate_pass_id
                )
                gate_pass = (await db.execute(gp_stmt)).scalar_one_or_none()
                if not gate_pass:
                    continue

                load_stmt = select(
                    func.coalesce(func.sum(ImportGatePassLoading.loaded_pcs), 0).label(
                        "total_loaded"
                    ),
                    func.max(ImportGatePassLoading.loaded_time).label("latest_time"),
                    func.max(ImportGatePassLoading.loaded_by).label("latest_by"),
                ).where(
                    ImportGatePassLoading.gate_pass_id == gate_pass.id,
                    ImportGatePassLoading.truck_visit_id == assignment.truck_visit_id,
                )
                load_row = (await db.execute(load_stmt)).first()
                total_loaded = int(load_row.total_loaded) if load_row else 0
                latest_time = load_row.latest_time if load_row else None
                latest_by = load_row.latest_by if load_row else None

                gate_passes.append(
                    {
                        "gate_pass_no": gate_pass.gate_pass_no,
                        "awb": getattr(gate_pass, "awb_no", None),
                        "hawb": getattr(gate_pass, "hawb_no", None),
                        "pcs": gate_pass.pcs_total,
                        "pcs_remaining": gate_pass.pcs_remaining,
                        "assigned_time": assignment.assigned_time,
                        "assigned_by": assignment.assigned_by,
                        "gate_pass_out_time": latest_time,
                        "pcs_loaded": total_loaded,
                        "gate_pass_out_by": latest_by,
                        "assigned_truck_visit_id": assignment.truck_visit_id,
                        "is_active_assignment": assignment.is_active,
                    }
                )

            gate_passes.sort(
                key=lambda gp: (
                    gp["assigned_time"]
                    if gp["assigned_time"] is not None
                    else datetime.min
                ),
                reverse=True,
            )

            trucks_data.append(
                {
                    "truck_visit_id": visit.id,
                    "truck_number": visit.truck_number,
                    "driver_name": visit.driver_name,
                    "driver_contact": visit.driver_contact,
                    "token_no": visit.token_no,
                    "status": visit.status,
                    "queue_no": visit.queue_no,
                    "gate_passes": gate_passes,
                    "truck_in_date_time": visit.truck_in_date_time,
                    "truck_out_date_time": visit.truck_out_date_time,
                    "visit_type": getattr(visit, "visit_type", "TRUCK"),
                }
            )

        return {
            "success": True,
            "date": str(target_date),
            "list_type": list_type,
            "count": len(trucks_data),
            "counts": {  # ← counts for BOTH tabs
                "pending": pending_count,
                "out": out_count,
            },
            "trucks": trucks_data,
            "message": f"Found {len(trucks_data)} {list_type} trucks for {target_date}",
        }


class ImportTruckStagingService:
    """
    Service layer for staging truck + gate pass entries.
    """

    @staticmethod
    async def add_to_staging(
        db: AsyncSession,
        request: TruckStagingRequest,
        emp_id: str = None,
        # session_id: str
    ) -> TruckStagingResponse:
        """
        Add a truck + gate pass entry into staging table.
        """
        staging_entry = ImportTruckInStaging(
            session_id="default-session",  # Placeholder; replace with session_id
            truck_number=request.truck_number,
            driver_name=request.driver_name,
            driver_contact=request.driver_contact,
            gate_pass_no=request.gate_pass_no,
        )

        db.add(staging_entry)
        await log_activity_of_imp_truck_in_out(
            db,
            event_type="GP_STAGED",
            entity_type="staging",
            entity_id=staging_entry.id,
            truck_number=staging_entry.truck_number,
            gate_pass_no=staging_entry.gate_pass_no,
            description=f"GP {staging_entry.gate_pass_no} staged for truck {staging_entry.truck_number}",
            snapshot_after={
                "truck_number": staging_entry.truck_number,
                "gate_pass_no": staging_entry.gate_pass_no,
                "driver_name": staging_entry.driver_name,
                "driver_contact": staging_entry.driver_contact,
            },
            performed_by=emp_id,  
        )
        await db.commit()
        await db.refresh(staging_entry)

        return TruckStagingResponse(
            success=True,
            message="Truck + gate pass staged successfully",
            id=staging_entry.id,
            truck_number=staging_entry.truck_number,
            gate_pass_no=staging_entry.gate_pass_no,
            driver_name=staging_entry.driver_name,
            driver_contact=staging_entry.driver_contact,
        )

    # @staticmethod
    # async def list_staging_entries(
    #     db: AsyncSession, truck_number: str
    # ) -> Dict[str, Any]:
    #     """
    #     List all staging entries for a given session.
    #     """
    #     print(f"Fetching staging entries for Truck: {truck_number}")
    #     stmt = select(ImportTruckInStaging).where(
    #         ImportTruckInStaging.truck_number == truck_number
    #     )
    #     result = await db.execute(stmt)
    #     entries = result.scalars().all()
    #     print(entries)

    #     return {
    #         "success": True,
    #         "count": len(entries),
    #         "entries": [
    #             {
    #                 "id": e.id,
    #                 "truck_number": e.truck_number,
    #                 "driver_name": e.driver_name,
    #                 "driver_contact": e.driver_contact,
    #                 "gate_pass_no": e.gate_pass_no,
    #                 "added_time": e.added_time,
    #             }
    #             for e in entries
    #         ],
    #     }

    @staticmethod
    async def list_staging_entries(
        db: AsyncSession, truck_number: str
    ) -> Dict[str, Any]:
        """
        List all staging entries for a given session,
        with each GP's final_delivery_datetime (for overstay preview).
        """
        print(f"Fetching staging entries for Truck: {truck_number}")

        stmt = select(ImportTruckInStaging).where(
            ImportTruckInStaging.truck_number == truck_number
        )
        result = await db.execute(stmt)
        entries = result.scalars().all()

        # Batch-fetch final_delivery_datetime for all staged GPs in one query
        gp_nos = [e.gate_pass_no for e in entries if e.gate_pass_no]
        ship_map: dict[str, object] = {}
        if gp_nos:
            ship_rows = (await db.execute(
                select(
                    WorkerAssignmentShipment.gate_pass_no,
                    WorkerAssignmentShipment.final_delivery_datetime,
                     WorkerAssignmentShipment.no_of_pc,
                    WorkerAssignmentShipment.agent_name,
                    WorkerAssignmentShipment.customer_name,
                ).where(WorkerAssignmentShipment.gate_pass_no.in_(gp_nos))
            )).all()
            # one GP → one shipment row (gate_pass_no is the link); keep first non-null
            # for gp_no, fd in ship_rows:
            #     if gp_no not in ship_map or (fd is not None and ship_map[gp_no] is None):
            #         ship_map[gp_no] = fd

             # one GP → one shipment row; store the full row, keep first per GP
            for r in ship_rows:
                if r.gate_pass_no not in ship_map:
                    ship_map[r.gate_pass_no] = r

        return {
            "success": True,
            "count": len(entries),
            "entries": [
                {
                    "id": e.id,
                    "truck_number": e.truck_number,
                    "driver_name": e.driver_name,
                    "driver_contact": e.driver_contact,
                    "gate_pass_no": e.gate_pass_no,
                    "added_time": e.added_time,
                  "final_delivery_datetime": (
                        ship_map[e.gate_pass_no].final_delivery_datetime
                        if e.gate_pass_no in ship_map else None
                    ),
                      "pcs": (
                        ship_map[e.gate_pass_no].no_of_pc
                        if e.gate_pass_no in ship_map else None
                    ),
                    "agent": (
                        ship_map[e.gate_pass_no].agent_name
                        if e.gate_pass_no in ship_map else None
                    ),
                    "consignee": (
                        ship_map[e.gate_pass_no].customer_name
                        if e.gate_pass_no in ship_map else None
                    ),
                }
                for e in entries
            ],
        }

    @staticmethod
    async def remove_from_staging(
        db: AsyncSession, entry_id: int, truck_number: str, emp_id: str = None
    ) -> Dict[str, Any]:
        """
        Remove a staging entry by ID for a given session.
        """
        stmt = select(ImportTruckInStaging).where(
            ImportTruckInStaging.id == entry_id,
            ImportTruckInStaging.truck_number == truck_number,
        )
        result = await db.execute(stmt)
        staging_entry = result.scalar_one_or_none()

        if not staging_entry:
            raise HTTPException(status_code=404, detail="Staging entry not found")

        # Snapshot before deletion
        snapshot_before = {
            "id": staging_entry.id,
            "truck_number": staging_entry.truck_number,
            "gate_pass_no": staging_entry.gate_pass_no,
            "driver_name": staging_entry.driver_name,
        }

        await db.delete(staging_entry)

        await log_activity_of_imp_truck_in_out(
            db,
            event_type="GP_STAGING_REMOVED",
            entity_type="staging",
            entity_id=entry_id,
            truck_number=staging_entry.truck_number,
            gate_pass_no=staging_entry.gate_pass_no,
            description=f"GP {staging_entry.gate_pass_no} removed from staging for truck {truck_number}",
            snapshot_before=snapshot_before,
            performed_by=emp_id,
        )
        await db.commit()

        return {
            "success": True,
            "message": f"Staging entry {entry_id} removed successfully",
        }


class ImportTruckVisitService:

    @staticmethod
    async def commit_staging_to_truck_visit(
        db: AsyncSession,
        truck_number: str,
        emp_id: str,
        device_id: str = None,
        is_queued: bool = False,  # ← ADD THIS
    ):
        """
        Commit staged rows for a truck into main tables.
        Adds truck_in_date_time, token_number, and company_name = DCSC.
        """
        # 1. Fetch staging rows
        stmt = select(ImportTruckInStaging).where(
            ImportTruckInStaging.truck_number == truck_number
        )
        result = await db.execute(stmt)
        staging_rows = result.scalars().all()

        if not staging_rows:
            raise HTTPException(
                status_code=404, detail="No staging rows found for this truck"
            )

        # ← ADD HERE, after staging check, before token generation
        if is_queued:
            existing_queue_stmt = select(ImportTruckVisit).where(
                ImportTruckVisit.truck_number == truck_number,
                ImportTruckVisit.status == "QUEUED",
            )
            existing_queue_result = await db.execute(existing_queue_stmt)
            existing_queue = existing_queue_result.scalar_one_or_none()

            if existing_queue:
                raise HTTPException(
                    status_code=400,
                    detail=f"Truck {truck_number} is already in queue (Queue No: {existing_queue.queue_no}). Cancel or promote the existing queue first.",
                )
        ## ← Block if truck already has an active BOOKED (truck IN, not out) visit { Block truck IN if already inside}
        existing_booked_stmt = select(ImportTruckVisit).where(
            ImportTruckVisit.truck_number == truck_number,
            ImportTruckVisit.status == "BOOKED",
            ImportTruckVisit.is_truck_out == False,
        )
        existing_booked = (await db.execute(existing_booked_stmt)).scalar_one_or_none()

        if existing_booked and not is_queued:
            raise HTTPException(
                status_code=400,
                detail=f"Truck {truck_number} is already inside (Token: {existing_booked.token_no}). Truck out must be done first.",
            )

        # ← ADD HERE
        # Block truck IN if already in queue
        if not is_queued:
            existing_queue_stmt = select(ImportTruckVisit).where(
                ImportTruckVisit.truck_number == truck_number,
                ImportTruckVisit.status == "QUEUED",
            )
            existing_queue = (
                await db.execute(existing_queue_stmt)
            ).scalar_one_or_none()
            if existing_queue:
                raise HTTPException(
                    status_code=400,
                    detail=f"Truck {truck_number} is already in queue (Queue No: {existing_queue.queue_no}). Use 'Promote queue' to check it in instead of creating a new truck IN.",
                )

        # 2. Count existing tokens for today
        # today_prefix = f"M{datetime.utcnow().strftime('%Y%m%d')}"
        today_prefix = f"M{datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y%m%d')}"
        count_result = await db.execute(
            select(ImportTruckVisit.token_no).where(
                ImportTruckVisit.token_no.like(f"{today_prefix}%")
            )
        )
        db_count = len(count_result.scalars().all())

        # 3. Create ImportTruckVisit
        utc_now = datetime.now(timezone.utc)
        token_number = generate_token_number(db_count, prefix="M")

        # truck_visit = ImportTruckVisit(
        #     company_name="DCSC",  # ✅ fixed company name
        #     warehouse="IMP-I",
        #     zone="ZONE-I",
        #     truck_number=truck_number,
        #     driver_name=staging_rows[0].driver_name,
        #     driver_contact=staging_rows[0].driver_contact,
        #     status = "BOOKED",
        #     remarks = "Truck IN",
        #     truck_slot_from=staging_rows[0].added_time,
        #     is_truck_in=True,
        #     truck_in_by=emp_id,
        #     truck_in_device=device_id,
        #     truck_in_date_time=utc_now,   # ✅ explicit truck in timestamp
        #     token_no=token_number,    # ✅ generated token
        #     created_at=utc_now,
        #     updated_at=utc_now
        # )

        # Queue number — only generate if queuing
        queue_no = None
        queued_at = None
        if is_queued:
            queue_no = await generate_queue_number(db)
            queued_at = utc_now

        truck_visit = ImportTruckVisit(
            company_name="DCSC",
            warehouse="IMP-I",
            zone="ZONE-I",
            truck_number=truck_number,
            driver_name=staging_rows[0].driver_name,
            driver_contact=staging_rows[0].driver_contact,
            status="QUEUED" if is_queued else "BOOKED",
            remarks="Truck QUEUED" if is_queued else "Truck IN",
            truck_slot_from=staging_rows[0].added_time,
            is_truck_in=not is_queued,
            truck_in_by=emp_id if not is_queued else None,
            truck_in_device=device_id if not is_queued else None,
            truck_in_date_time=utc_now if not is_queued else None,
            token_no=token_number,
            queue_no=queue_no,
            queued_at=queued_at,
            queued_by=emp_id if is_queued else None,
            queued_device=device_id if is_queued else None,
            created_at=utc_now,
            updated_at=utc_now,
        )
        db.add(truck_visit)
        await db.flush()  # get truck_visit.id

        assigned_gate_passes = []
        # 4. Validate gate passes + create assignments
        for row in staging_rows:
            gp_stmt = select(ImportGatePass).where(
                ImportGatePass.gate_pass_no == row.gate_pass_no
            )
            gp_result = await db.execute(gp_stmt)
            gate_pass = gp_result.scalar_one_or_none()

            if not gate_pass:
                # NEW
                was_stmt = (
                    select(WorkerAssignmentShipment, WorkerAssignmentHeader)
                    .join(
                        WorkerAssignmentHeader,
                        WorkerAssignmentShipment.assignment_header_id
                        == WorkerAssignmentHeader.id,
                    )
                    .where(WorkerAssignmentShipment.gate_pass_no == row.gate_pass_no)
                )
                was_result = await db.execute(was_stmt)
                was_row = was_result.first()

                if not was_row:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Gate pass not found in system: {row.gate_pass_no}",
                    )

                shipment, header = was_row

                gate_pass = ImportGatePass(
                    gate_pass_no=shipment.gate_pass_no,
                    issued_date=shipment.gate_pass_issued_date_time_combo,
                    agent=shipment.agent_name,
                    consignee=shipment.customer_name,
                    gate_pass_release_by=shipment.verified_by or None,
                    gate_pass_released_time=shipment.gate_pass_issued_date_time_combo,
                    awb_no=header.awb_no,
                    hawb_no=header.hawb,
                    pcs_total=shipment.no_of_pc,
                    pcs_remaining=shipment.no_of_pc,
                    gross_wt_total=shipment.weight_in_kgs or 0,
                    status="A",
                    worker_assignment_shipment_id=shipment.id,  # ← ADD
                    drop_dlv_zone=shipment.drop_dlv_zone,  # ← ADD
                )
                db.add(gate_pass)
                await db.flush()

            # Deactivate any prior active assignments for this GP (defensive)
            await db.execute(
                update(ImportGatePassAssignment)
                .where(ImportGatePassAssignment.gate_pass_id == gate_pass.id)
                .values(is_active=False)
            )

            assignment = ImportGatePassAssignment(
                gate_pass_id=gate_pass.id,
                truck_visit_id=truck_visit.id,
                assigned_by=emp_id,
                is_active=True,  # ✅ IMPORTANT
                remarks="Committed from staging",
            )
            db.add(assignment)
            await db.flush()  # ← get assignment.id
            # assigned_gate_passes.append(row.gate_pass_no)
            assigned_gate_passes.append(
                {
                    "gate_pass_no": row.gate_pass_no,
                    "gate_pass_id": gate_pass.id,
                    "assignment_id": assignment.id,
                }
            )

        # 5. Clear staging
        for row in staging_rows:
            await db.delete(row)

        # 6. Log everything BEFORE commit (atomic)

        # ── 6a. Truck-level log ──────────────────────────────────────
        gate_pass_nos_list = [g["gate_pass_no"] for g in assigned_gate_passes]

        await log_activity_of_imp_truck_in_out(
            db,
            event_type="TRUCK_QUEUED" if is_queued else "TRUCK_IN",
            entity_type="truck_visit",
            entity_id=truck_visit.id,
            truck_visit_id=truck_visit.id,
            truck_number=truck_visit.truck_number,
            queue_no=truck_visit.queue_no,
            token_no=truck_visit.token_no,
            description=(
                f"Truck {truck_visit.truck_number} (visit #{truck_visit.id}) "
                f"{'queued' if is_queued else 'checked in'}. "
                f"Token: {truck_visit.token_no}. "
                f"{'Queue No: ' + truck_visit.queue_no + '. ' if truck_visit.queue_no else ''}"
                f"GPs assigned: {', '.join(gate_pass_nos_list)}."
            ),
            snapshot_after={
                "truck_number": truck_visit.truck_number,
                "status": truck_visit.status,
                "is_truck_in": truck_visit.is_truck_in,
                "token_no": truck_visit.token_no,
                "queue_no": truck_visit.queue_no,
                "driver_name": truck_visit.driver_name,
                "driver_contact": truck_visit.driver_contact,
                "gate_passes_count": len(gate_pass_nos_list),
                "gate_pass_nos": gate_pass_nos_list,
            },
            performed_by=emp_id,
            device_id=device_id,
        )

        # ── 6b. Per-GP assignment logs ───────────────────────────────
        for gp_info in assigned_gate_passes:
            await log_activity_of_imp_truck_in_out(
                db,
                event_type="GP_ASSIGNED",
                entity_type="gp_assignment",
                entity_id=gp_info["assignment_id"],
                truck_visit_id=truck_visit.id,
                truck_number=truck_visit.truck_number,
                gate_pass_no=gp_info["gate_pass_no"],
                token_no=truck_visit.token_no,
                queue_no=truck_visit.queue_no,
                description=(
                    f"GP {gp_info['gate_pass_no']} assigned to truck {truck_visit.truck_number} "
                    f"(visit #{truck_visit.id}) during {'queue' if is_queued else 'truck in'}"
                ),
                snapshot_after={
                    "gate_pass_id": gp_info["gate_pass_id"],
                    "assignment_id": gp_info["assignment_id"],
                    "is_active": True,
                },
                performed_by=emp_id,
                device_id=device_id,
            )

        # 7. Commit (existing line)
        await db.commit()
        await db.refresh(truck_visit)

        return {
            "success": True,
            "truck_visit_id": truck_visit.id,
            "truck_number": truck_visit.truck_number,
            "token_number": truck_visit.token_no,
            "queue_no": truck_visit.queue_no,  # ← new
            "is_queued": is_queued,  # ← new
            "assigned_gate_passes": [
                g["gate_pass_no"] for g in assigned_gate_passes
            ],  # ← extract strings
            "message": f"Truck {'QUEUED' if is_queued else 'IN'} successfully",
        }

    @staticmethod
    async def create_by_hand_pickup(
        db: AsyncSession,
        person_name: str,
        person_contact: Optional[str],
        gate_pass_nos: List[str],
        emp_id: str,
        device_id: Optional[str] = None,
        remarks: Optional[str] = None,
    ):
        """
        Create a BY_HAND visit (no truck, no queue, no staging).
        Single-shot: validates GPs, creates visit, creates assignments, all atomic.
        truck_number is NULL — by-hand visits have no truck.
        """
        # Clean input
        gp_nos_clean = list({gp.strip() for gp in gate_pass_nos if gp and gp.strip()})
        if not gp_nos_clean:
            raise HTTPException(
                status_code=400, detail="At least one gate pass required"
            )

        person_name = person_name.strip()
        if not person_name:
            raise HTTPException(status_code=400, detail="Person name is required")

        utc_now = datetime.now(timezone.utc)

        # Generate token with M prefix
        today_prefix = f"M{datetime.now(ZoneInfo('Asia/Kolkata')).strftime('%Y%m%d')}"
        count_result = await db.execute(
            select(ImportTruckVisit.token_no).where(
                ImportTruckVisit.token_no.like(f"{today_prefix}%")
            )
        )
        db_count = len(count_result.scalars().all())
        token_number = generate_token_number(db_count, prefix="M")

        # Validate all GPs FIRST (atomic)
        validated_gps = (
            []
        )  # list of (gp_no, existing_gp_or_None, shipment_or_None, header_or_None)

        for gp_no in gp_nos_clean:
            # Check existing
            gp_stmt = select(ImportGatePass).where(ImportGatePass.gate_pass_no == gp_no)
            existing_gp = (await db.execute(gp_stmt)).scalar_one_or_none()

            if existing_gp:
                if existing_gp.pcs_remaining <= 0:
                    raise HTTPException(
                        status_code=400,
                        detail=f"Gate pass {gp_no} fully consumed (0 pcs remaining)",
                    )

                # Active assignment elsewhere?
                active_stmt = select(ImportGatePassAssignment).where(
                    ImportGatePassAssignment.gate_pass_id == existing_gp.id,
                    ImportGatePassAssignment.is_active == True,
                )
                active = (await db.execute(active_stmt)).scalar_one_or_none()
                if active:
                    other_visit = (
                        await db.execute(
                            select(ImportTruckVisit).where(
                                ImportTruckVisit.id == active.truck_visit_id
                            )
                        )
                    ).scalar_one_or_none()
                    # Build a sensible label whether it's a truck or by-hand entry
                    if other_visit:
                        if other_visit.visit_type == "BY_HAND":
                            other_label = f"by-hand pickup by {other_visit.driver_name or 'unknown'}"
                        else:
                            other_label = (
                                f"truck {other_visit.truck_number or 'unknown'}"
                            )
                    else:
                        other_label = "another visit"
                    raise HTTPException(
                        status_code=400,
                        detail=f"Gate pass {gp_no} active on {other_label}. Reassign first.",
                    )

                validated_gps.append((gp_no, existing_gp, None, None))
                continue

            # GP doesn't exist → check IRR
            was_stmt = (
                select(WorkerAssignmentShipment, WorkerAssignmentHeader)
                .join(
                    WorkerAssignmentHeader,
                    WorkerAssignmentShipment.assignment_header_id
                    == WorkerAssignmentHeader.id,
                )
                .where(WorkerAssignmentShipment.gate_pass_no == gp_no)
            )
            was_row = (await db.execute(was_stmt)).first()
            if not was_row:
                raise HTTPException(
                    status_code=400, detail=f"Gate pass not found in system: {gp_no}"
                )
            shipment, header = was_row

            if not shipment.no_of_pc or shipment.no_of_pc <= 0:
                raise HTTPException(
                    status_code=400, detail=f"Invalid pcs count for GP {gp_no}"
                )

            validated_gps.append((gp_no, None, shipment, header))

        # ── All validation passed — create visit + assignments atomically ─────────
        try:
            truck_visit = ImportTruckVisit(
                company_name="DCSC",
                warehouse="IMP-I",
                zone="ZONE-I",
                visit_type="BY_HAND",
                truck_number=None,  # ← NULL — by-hand has no truck
                driver_name=person_name,  # person name stored here
                driver_contact=person_contact,  # person contact stored here
                status="BOOKED",
                remarks=remarks or "By-hand pickup",
                truck_slot_from=utc_now,
                is_truck_in=True,
                truck_in_by=emp_id,
                truck_in_device=device_id,
                truck_in_date_time=utc_now,
                token_no=token_number,
                created_at=utc_now,
                updated_at=utc_now,
            )
            db.add(truck_visit)
            await db.flush()

            assigned_gate_passes = []

            for gp_no, existing_gp, shipment, header in validated_gps:
                if existing_gp:
                    gp = existing_gp
                else:
                    gp = ImportGatePass(
                        gate_pass_no=shipment.gate_pass_no,
                        issued_date=shipment.gate_pass_issued_date_time_combo,
                        agent=shipment.agent_name,
                        consignee=shipment.customer_name,
                        gate_pass_release_by=shipment.verified_by or None,
                        gate_pass_released_time=shipment.gate_pass_issued_date_time_combo,
                        awb_no=header.awb_no,
                        hawb_no=header.hawb,
                        pcs_total=shipment.no_of_pc,
                        pcs_remaining=shipment.no_of_pc,
                        gross_wt_total=shipment.weight_in_kgs or 0,
                        status="A",
                        worker_assignment_shipment_id=shipment.id,
                        drop_dlv_zone=shipment.drop_dlv_zone,
                    )
                    db.add(gp)
                    await db.flush()

                # Defensive deactivation of any active assignment for this GP
                await db.execute(
                    update(ImportGatePassAssignment)
                    .where(ImportGatePassAssignment.gate_pass_id == gp.id)
                    .values(is_active=False)
                )

                assignment = ImportGatePassAssignment(
                    gate_pass_id=gp.id,
                    truck_visit_id=truck_visit.id,
                    assigned_by=emp_id,
                    is_active=True,
                    remarks=f"By-hand pickup by {person_name}",
                )
                db.add(assignment)
                await db.flush()

                assigned_gate_passes.append(
                    {
                        "gate_pass_no": gp_no,
                        "gate_pass_id": gp.id,
                        "assignment_id": assignment.id,
                    }
                )

            # ── Activity logs ──────────────────────────────────────────────────────
            gp_nos_list = [g["gate_pass_no"] for g in assigned_gate_passes]

            await log_activity_of_imp_truck_in_out(
                db,
                event_type="TRUCK_IN",
                entity_type="truck_visit",
                entity_id=truck_visit.id,
                truck_visit_id=truck_visit.id,
                truck_number=None,  # ← NULL for by-hand
                token_no=truck_visit.token_no,
                description=(
                    f"BY-HAND pickup checked in by {person_name} "
                    f"(visit #{truck_visit.id}). "
                    f"Token: {truck_visit.token_no}. "
                    f"GPs assigned: {', '.join(gp_nos_list)}."
                ),
                snapshot_after={
                    "visit_type": "BY_HAND",
                    "person_name": person_name,
                    "person_contact": person_contact,
                    "token_no": truck_visit.token_no,
                    "truck_number": None,
                    "status": truck_visit.status,
                    "is_truck_in": True,
                    "gate_passes_count": len(gp_nos_list),
                    "gate_pass_nos": gp_nos_list,
                },
                performed_by=emp_id,
                device_id=device_id,
            )

            for gp_info in assigned_gate_passes:
                await log_activity_of_imp_truck_in_out(
                    db,
                    event_type="GP_ASSIGNED",
                    entity_type="gp_assignment",
                    entity_id=gp_info["assignment_id"],
                    truck_visit_id=truck_visit.id,
                    truck_number=None,  # ← NULL for by-hand
                    gate_pass_no=gp_info["gate_pass_no"],
                    token_no=truck_visit.token_no,
                    description=(
                        f"GP {gp_info['gate_pass_no']} assigned to BY-HAND pickup by {person_name} "
                        f"(visit #{truck_visit.id})"
                    ),
                    snapshot_after={
                        "visit_type": "BY_HAND",
                        "gate_pass_id": gp_info["gate_pass_id"],
                        "assignment_id": gp_info["assignment_id"],
                        "is_active": True,
                    },
                    performed_by=emp_id,
                    device_id=device_id,
                )

            await db.commit()
            await db.refresh(truck_visit)

            return {
                "success": True,
                "truck_visit_id": truck_visit.id,
                "token_no": truck_visit.token_no,
                "person_name": person_name,
                "visit_type": "BY_HAND",
                "assigned_gate_passes": gp_nos_list,
                "message": f"By-hand pickup created for {person_name} with {len(gp_nos_list)} GP(s)",
            }

        except HTTPException:
            await db.rollback()
            raise
        except Exception as e:
            await db.rollback()
            logger.error(f"By-hand pickup failed: {e}")
            raise HTTPException(
                status_code=500, detail=f"Failed to create by-hand pickup: {str(e)}"
            )


class ImportGatePassOutService:

    @staticmethod
    async def gate_pass_out(
        db: AsyncSession,
        truck_visit_id: int,
        gate_pass_no: str,
        loaded_pcs: int,
        emp_id: str,
        device_id: str = None,
    ):
        """
        Record gate pass out (loading).
        Can be called multiple times for same GP on different trucks.
        """
        utc_now = datetime.now(timezone.utc)

        # Validate truck visit
        truck_stmt = select(ImportTruckVisit).where(
            ImportTruckVisit.id == truck_visit_id
        )
        truck_result = await db.execute(truck_stmt)
        truck_visit = truck_result.scalar_one_or_none()

        if not truck_visit:
            raise HTTPException(status_code=404, detail="Truck visit not found")

        # Validate gate pass
        gp_stmt = select(ImportGatePass).where(
            ImportGatePass.gate_pass_no == gate_pass_no
        )
        gp_result = await db.execute(gp_stmt)
        gate_pass = gp_result.scalar_one_or_none()

        if not gate_pass:
            raise HTTPException(
                status_code=400, detail=f"Gate pass not found: {gate_pass_no}"
            )

        if gate_pass.status == "C":
            raise HTTPException(
                status_code=400, detail=f"Gate pass already closed: {gate_pass_no}"
            )

        if loaded_pcs > gate_pass.pcs_remaining:
            raise HTTPException(
                status_code=400,
                detail=f"Loaded pcs ({loaded_pcs}) exceed remaining ({gate_pass.pcs_remaining}) for {gate_pass_no}",
            )

        # Verify active assignment to this truck
        active_assign_stmt = select(ImportGatePassAssignment).where(
            ImportGatePassAssignment.gate_pass_id == gate_pass.id,
            ImportGatePassAssignment.truck_visit_id == truck_visit_id,
            ImportGatePassAssignment.is_active == True,
        )
        active_assign_result = await db.execute(active_assign_stmt)
        active_assignment = active_assign_result.scalar_one_or_none()

        # ═══ CAPTURE SNAPSHOT BEFORE ANY CHANGES ═══
        snapshot_before = {
            "pcs_remaining": gate_pass.pcs_remaining,
            "status": gate_pass.status,
            "gate_pass_out_date_time": (
                gate_pass.gate_pass_out_date_time.isoformat()
                if gate_pass.gate_pass_out_date_time
                else None
            ),
        }

        if not active_assignment:
            raise HTTPException(
                status_code=400,
                detail=f"Gate pass {gate_pass_no} not actively assigned to this truck",
            )

        # Insert loading record
        gp_loading = ImportGatePassLoading(
            gate_pass_id=gate_pass.id,
            truck_visit_id=truck_visit.id,
            loaded_pcs=loaded_pcs,
            loaded_by=emp_id,
            remarks=f"Loaded {loaded_pcs} pcs on truck {truck_visit.truck_number}",
        )
        db.add(gp_loading)
        await db.flush()  # ← get gp_loading.id for the log

        # Update gate pass
        gate_pass.pcs_remaining -= loaded_pcs
        gate_pass.gate_pass_out_by = emp_id
        gate_pass.gate_pass_out_date_time = utc_now
        gate_pass.gate_pass_Out_device = device_id

        # If fully loaded, mark as closed and deactivate assignment
        if gate_pass.pcs_remaining == 0:
            gate_pass.status = "C"

        await db.execute(
            update(ImportGatePassAssignment)
            .where(
                ImportGatePassAssignment.gate_pass_id == gate_pass.id,
                ImportGatePassAssignment.truck_visit_id == truck_visit_id,
                ImportGatePassAssignment.is_active == True,
            )
            .values(is_active=False)
        )

        # (The actual update is already done before this)
        # ═══ CAPTURE SNAPSHOT AFTER ═══
        snapshot_after = {
            "pcs_remaining": gate_pass.pcs_remaining,
            "status": gate_pass.status,
            "gate_pass_out_date_time": gate_pass.gate_pass_out_date_time.isoformat(),
            "loaded_pcs_this_event": loaded_pcs,
            "loaded_by": emp_id,
            "assignment_deactivated": True,
        }

        await log_activity_of_imp_truck_in_out(
            db,
            event_type="GP_LOADED",
            entity_type="gp_loading",
            entity_id=gp_loading.id,
            truck_visit_id=truck_visit.id,
            truck_number=truck_visit.truck_number,
            gate_pass_no=gate_pass.gate_pass_no,
            token_no=truck_visit.token_no,
            description=(
                f"GP {gate_pass.gate_pass_no} loaded — {loaded_pcs} pcs on truck {truck_visit.truck_number} "
                f"(visit_id #{truck_visit.id}). Remaining: {gate_pass.pcs_remaining}. Status: {gate_pass.status}."
            ),
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
            performed_by=emp_id,
            device_id=device_id,
        )

        await db.commit()
        await db.refresh(gate_pass)

        return {
            "success": True,
            "truck_visit_id": truck_visit.id,
            "gate_pass_no": gate_pass.gate_pass_no,
            "loaded_pcs": loaded_pcs,
            "remaining_pcs": gate_pass.pcs_remaining,
            "status": gate_pass.status,
            "message": f"{'Fully' if gate_pass.pcs_remaining == 0 else 'Partially'} loaded: {loaded_pcs} pcs",
        }


class ImportTruckOutService:

    # local_import_dir = get_env_variable('LOCAL_IMPORT_DIR')
    # ftp_host = get_env_variable('FTP_HOST')
    # ftp_user = get_env_variable('FTP_USER')
    # ftp_pass = get_env_variable('FTP_PASS')
    # ftp_dir = get_env_variable('FTP_DIR')
    # ftp_port = get_env_variable('FTP_PORT',int)
    # ftp_time_out = get_env_variable('FTP_TIMEOUT',int)

    @staticmethod
    def build_import_lines(
        truck_visit: ImportTruckVisit,
        gate_passes_data: List[dict],
        user_id: str,
        parking_in_user: str = None,
        release_user: str = None,
    ) -> str:
        """
        Build import lines for FTP file.

        Args:
            truck_visit: ImportTruckVisit instance
            gate_passes_data: List of dicts with gate pass and loading info
                [
                    {
                        'gate_pass': ImportGatePass instance,
                        'loaded_pcs': int,
                        'parking_in_time': datetime,
                        'release_time': datetime,
                        'parking_in_by': str,
                        'release_by': str
                    }
                ]
            user_id: str (system user/operator)
            parking_in_user: str (who did truck in)
            release_user: str (who did gate pass out)

        Returns:
            str: Formatted FTP message
        """

        lines = []
        ist_timezone = pytz.timezone("Asia/Kolkata")
        GS = chr(29)  # Group Separator (ASCII 29)

        # Debug logging
        print(f"\n🔍 DEBUG - Building Import FTP Message:")
        print(f"   Truck Visit ID: {truck_visit.id}")
        print(f"   Truck Number: {truck_visit.truck_number}")
        print(f"   Token: {truck_visit.token_no}")
        print(f"   Gate Passes: {len(gate_passes_data)}")

        # Determine truck status: M=Manual, B=Booked
        truck_status = (
            "R"
            if truck_visit.token_no and truck_visit.token_no.startswith("M")
            else "B"
        )

        for gp_data in gate_passes_data:
            gate_pass = gp_data["gate_pass"]
            loaded_pcs = gp_data.get(
                "loaded_pcs", gate_pass.pcs_total - gate_pass.pcs_remaining
            )

            print(f"\n   Processing GP: {gate_pass.gate_pass_no}")
            print(f"   - AWB: {gate_pass.awb_no or 'N/A'}")
            print(f"   - HAWB: {gate_pass.hawb_no or 'N/A'}")
            print(f"   - Loaded PCS: {loaded_pcs}")

            # Convert times to IST
            parking_in_ist = convert_to_ist_datetime(
                gp_data.get("parking_in_time") or truck_visit.truck_in_date_time,
                ist_timezone,
            )

            release_ist = convert_to_ist_datetime(
                # gp_data.get('release_time') or gate_pass.gate_pass_out_date_time,
                truck_visit.truck_out_date_time,
                ist_timezone,
            )

            # # Slot times (from truck visit)
            # slot_from_ist = convert_to_ist_date(
            #     truck_visit.truck_slot_from,
            #     ist_timezone
            # )

            # # Slot TO = Slot FROM (same day for import)
            # slot_to_ist = slot_from_ist

            # Slot times (fixed logic)
            slot_date = truck_visit.truck_slot_from.date()  # take the date part
            slot_from_dt = datetime.combine(slot_date, time(11, 0))  # 11:00 IST
            slot_to_dt = slot_from_dt + timedelta(hours=1)  # add 1 hour → 12:00 IST

            # Convert to IST formatted strings
            slot_to_ist = convert_to_ist_datetime(slot_to_dt, ist_timezone)
            slot_from_ist = convert_to_ist_datetime(slot_from_dt, ist_timezone)

            # Build field list according to format
            fields = [
                truck_visit.warehouse or "IMP-I",  # 1. WAREHOUSE
                truck_visit.zone or "ZONE-I",  # 2. ZONE
                str(11),  # 3. HOURS (standard import hours)
                "DCSC",  # 4. ORGNTR (originator)
                truck_visit.token_no or "",  # 5. VCT_NO (vehicle control token)
                gate_pass.gate_pass_no or "",  # 6. GP_NO (gate pass number)
                gate_pass.awb_no or "",  # 7. AWB_NO
                gate_pass.hawb_no or "",  # 8. HAWB_NO
                truck_visit.truck_number or "",  # 9. TRUCK_NO
                str(loaded_pcs),  # 10. LOAD_PKGS
                "NORMAL",  # 11. BOOKING_TYPE
                truck_status,  # 12. TRUCK_STATUS (M/B)
                slot_from_ist,  # 13. SLOT_FROM (DD-MMM-YY)
                slot_to_ist,  # 14. SLOT_TO (DD-MMM-YY)
                truck_visit.remarks or gate_pass.consignee or "",  # 15. REMARKS
                # user_id or "CTO",                           # 16. USER_ID
                "DCSC",
                datetime.now(ist_timezone).strftime("%d-%b-%y").upper(),  # 17. TM_STMP
                # gp_data.get('parking_in_by') or parking_in_user or truck_visit.truck_in_by or "",  # 18. PARKING_IN_USER
                "DCSC",
                parking_in_ist,  # 19. PARKING_IN_TM_STMP (DDMMYYYYHHMM)
                # gp_data.get('release_by') or release_user or gate_pass.gate_pass_out_by or "",     # 20. RELEASE_USER
                "DCSC",
                release_ist,  # 21. RELEASE_TM_STMP (DDMMYYYYHHMM)
                truck_visit.driver_name or "DRIVER",  # 22. DRIVER_NAME
                truck_visit.driver_contact or "0000000000",  # 23. MOBILE_NUMBER
            ]

            # Join fields with Group Separator
            line = GS.join(fields)
            lines.append(line)

            print(f"   ✅ Line created: {len(line)} chars")

        # Wrap message with header and footer
        message = "<IMPORT-SLOT-CTO>\n" + "\n".join(lines) + "\n<END-IMPORT-SLOT-CTO>"

        print(f"\n✅ FTP Message built: {len(lines)} lines")
        return message

    @staticmethod
    async def truck_out(
        db: AsyncSession,
        truck_visit_id: int,
        emp_id: str,
        device_id: str,
        send_ftp: bool = True,  # ✅ Control FTP sending
    ):
        """
        Mark truck as OUT.
        Validates that all ACTIVE gate pass assignments have been processed.
        """
        utc_now = datetime.now(timezone.utc)

        truck_stmt = select(ImportTruckVisit).where(
            ImportTruckVisit.id == truck_visit_id
        )
        truck_result = await db.execute(truck_stmt)
        truck_visit = truck_result.scalar_one_or_none()

        if not truck_visit:
            raise HTTPException(status_code=404, detail="Truck visit not found")

        logger.info(
            f"📦 Processing Truck OUT for: {truck_visit.truck_number} (Token: {truck_visit.token_no})"
        )

        # Check only ACTIVE assignments
        active_assign_stmt = select(ImportGatePassAssignment).where(
            ImportGatePassAssignment.truck_visit_id == truck_visit_id,
            ImportGatePassAssignment.is_active == True,
        )
        active_assign_result = await db.execute(active_assign_stmt)
        active_assignments = active_assign_result.scalars().all()

        unprocessed_gps = []
        for assignment in active_assignments:
            # Check if this assignment has loading records
            load_stmt = select(ImportGatePassLoading).where(
                ImportGatePassLoading.gate_pass_id == assignment.gate_pass_id,
                ImportGatePassLoading.truck_visit_id == truck_visit_id,
            )
            load_result = await db.execute(load_stmt)
            loadings = load_result.scalars().all()

            if not loadings:
                gp_stmt = select(ImportGatePass).where(
                    ImportGatePass.id == assignment.gate_pass_id
                )
                gp_result = await db.execute(gp_stmt)
                gp = gp_result.scalar_one_or_none()
                if gp:
                    unprocessed_gps.append(gp.gate_pass_no)

        if unprocessed_gps:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot truck out: {len(unprocessed_gps)} active gate pass(es) not processed: {', '.join(unprocessed_gps)}",
            )

        # ═══ CHARGE GATE — re-verify live, don't trust the flag alone ═══
        any_needed, missing = await ImportTruckOutService._visit_charge_status(
            db, truck_visit
        )
        if any_needed:
            # Some GP is charge-eligible → require BOTH: CC cleared AND no GP missing a charge
            if any_needed and missing:
                raise HTTPException(
                    status_code=400,
                    detail=(
                        f"Cannot truck out — storage charges not entered for GP: {', '.join(missing)}. "
                        f"Complete charge collection (Customer Care) first."
                    ),
                )
            # if not truck_visit.charges_cleared:
            #     raise HTTPException(
            #         status_code=400,
            #         detail=(
            #             "Storage charges are applicable but not yet cleared by Customer Care. "
            #             "Clear charges before truck out."
            #         ),
            #     )
        # If no GP needs charges → auto-cleared, gate passes.

        # ═══ CAPTURE SNAPSHOT BEFORE CHANGE ═══
        snapshot_before = {
            "status": truck_visit.status,
            "is_truck_out": truck_visit.is_truck_out,
            "truck_out_date_time": (
                truck_visit.truck_out_date_time.isoformat()
                if truck_visit.truck_out_date_time
                else None
            ),
            "truck_out_by": truck_visit.truck_out_by,
        }

        # Mark truck OUT
        truck_visit.is_truck_out = True
        truck_visit.truck_out_by = emp_id
        truck_visit.truck_out_device = device_id
        truck_visit.truck_out_date_time = utc_now

        snapshot_after = {
            "status": truck_visit.status,
            "is_truck_out": True,
            "truck_out_date_time": truck_visit.truck_out_date_time.isoformat(),
            "truck_out_by": emp_id,
            "total_gps_processed": len(active_assignments),
        }

        await log_activity_of_imp_truck_in_out(
            db,
            event_type="TRUCK_OUT",
            entity_type="truck_visit",
            entity_id=truck_visit.id,
            truck_visit_id=truck_visit.id,
            truck_number=truck_visit.truck_number,
            token_no=truck_visit.token_no,
            description=(
                f"Truck {truck_visit.truck_number} (visit_id #{truck_visit.id}) checked OUT. "
                f"Token: {truck_visit.token_no}. "
                f"Total GPs processed: {len(active_assignments)}."
            ),
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
            performed_by=emp_id,
            device_id=device_id,
        )

        await db.commit()
        await db.refresh(truck_visit)

        logger.info(f"✅ Truck marked OUT: {truck_visit.truck_number}")
        # ========== 4. BUILD FTP MESSAGE ==========
        ftp_result = None

        # if send_ftp:
        #     try:
        #         logger.info(f"📤 Generating FTP message for truck {truck_visit.truck_number}")

        #         # Fetch ALL assignments (not just active ones) to include in FTP
        #         all_assign_stmt = select(ImportGatePassAssignment).where(
        #             ImportGatePassAssignment.truck_visit_id == truck_visit_id
        #         )
        #         all_assign_result = await db.execute(all_assign_stmt)
        #         all_assignments = all_assign_result.scalars().all()

        #         # Build gate passes data for FTP
        #         gate_passes_data = []

        #         for assignment in all_assignments:
        #             # Fetch gate pass
        #             gp_stmt = select(ImportGatePass).where(
        #                 ImportGatePass.id == assignment.gate_pass_id
        #             )
        #             gp_result = await db.execute(gp_stmt)
        #             gate_pass = gp_result.scalar_one_or_none()

        #             if not gate_pass:
        #                 continue

        #             # Fetch loading records for this truck
        #             load_stmt = select(ImportGatePassLoading).where(
        #                 ImportGatePassLoading.gate_pass_id == gate_pass.id,
        #                 ImportGatePassLoading.truck_visit_id == truck_visit_id
        #             )
        #             load_result = await db.execute(load_stmt)
        #             loadings = load_result.scalars().all()

        #             # Calculate total loaded pieces
        #             total_loaded = sum(loading.loaded_pcs for loading in loadings)

        #             if total_loaded == 0:
        #                 # Skip gate passes with no loading for this truck
        #                 continue

        #             # Get the latest loading time
        #             latest_loading = max(loadings, key=lambda l: l.loaded_time) if loadings else None

        #             gate_passes_data.append({
        #                 'gate_pass': gate_pass,
        #                 'loaded_pcs': total_loaded,
        #                 'parking_in_time': truck_visit.truck_in_date_time,
        #                 'release_time': latest_loading.loaded_time if latest_loading else gate_pass.gate_pass_out_date_time,
        #                 'parking_in_by': truck_visit.truck_in_by,
        #                 'release_by': latest_loading.loaded_by if latest_loading else gate_pass.gate_pass_out_by
        #             })

        #         if not gate_passes_data:
        #             logger.warning(f"⚠️ No gate passes with loading found for truck {truck_visit.truck_number}")
        #         else:
        #             # Build FTP message
        #             # message = ImportTruckOutService.build_import_lines(
        #             #     truck_visit=truck_visit,
        #             #     gate_passes_data=gate_passes_data,
        #             #     user_id=emp_id,
        #             #     parking_in_user=truck_visit.truck_in_by,
        #             #     release_user=truck_visit.truck_out_by
        #             # )

        #             # # Save to FTP
        #             # logger.info(f"💾 Saving FTP message to local and uploading...")

        #             # ftp_result = save_to_dial_ftp(
        #             #     message=message,
        #             #     local_dir=ImportTruckOutService.local_import_dir,
        #             #     ftp_host=ImportTruckOutService.ftp_host,
        #             #     ftp_user=ImportTruckOutService.ftp_user,
        #             #     ftp_pass=ImportTruckOutService.ftp_pass,
        #             #     ftp_port=ImportTruckOutService.ftp_port,
        #             #     ftp_time_out=ImportTruckOutService.ftp_time_out,
        #             #     ftp_dir=ImportTruckOutService.ftp_dir
        #             # )

        #             # if ftp_result.get('ftp_upload_success'):
        #             #     logger.info(f"✅ FTP message sent successfully: {ftp_result.get('filename')}")
        #             # else:
        #             #     logger.warning(f"⚠️ FTP upload failed but file saved locally: {ftp_result.get('local_path')}")
        #             print("Ftp process is commentout ")

        #     except Exception as e:
        #         logger.error(f"❌ Error generating/sending FTP message: {str(e)}")
        #         # Don't fail the truck out operation if FTP fails
        #         ftp_result = {
        #             "error": str(e),
        #             "ftp_upload_success": False
        #         }

        # ========== 5. RETURN RESPONSE ==========
        response = {
            "success": True,
            "truck_visit_id": truck_visit.id,
            "truck_number": truck_visit.truck_number,
            "token_no": truck_visit.token_no,
            "truck_out_time": (
                truck_visit.truck_out_date_time.isoformat()
                if truck_visit.truck_out_date_time
                else None
            ),
            "message": "Truck OUT recorded successfully",
        }

        # # Include FTP info if available
        # if ftp_result:
        #     response["ftp"] = {
        #         "sent": ftp_result.get('ftp_upload_success', False),
        #         "filename": ftp_result.get('filename'),
        #         "local_path": ftp_result.get('local_path'),
        #         "error": ftp_result.get('error')
        #     }

        return response

    # @staticmethod
    # async def search_truck_for_out(
    #     db: AsyncSession,
    #     truck_number: str
    # ):
    #     truck_no = truck_number.strip().upper()

    #     if not truck_no:
    #         raise HTTPException(status_code=400, detail="Truck number is required")

    #     stmt = (
    #         select(ImportTruckVisit)
    #         .where(
    #             ImportTruckVisit.truck_number == truck_no,
    #             ImportTruckVisit.status == "BOOKED",
    #             ImportTruckVisit.is_truck_in == True,
    #         )
    #         .order_by(ImportTruckVisit.truck_in_date_time.desc())
    #     )
    #     result = await db.execute(stmt)
    #     visit = result.scalars().first()

    #     if not visit:
    #         queued_stmt = select(ImportTruckVisit).where(
    #             ImportTruckVisit.truck_number == truck_no,
    #             ImportTruckVisit.status == "QUEUED",
    #         ).order_by(ImportTruckVisit.queued_at.desc())
    #         queued_visit = (await db.execute(queued_stmt)).scalars().first()

    #         if queued_visit:
    #             raise HTTPException(
    #                 status_code=409,
    #                 detail=(
    #                     f"Truck {truck_no} is in QUEUE (Queue No: {queued_visit.queue_no}). "
    #                     f"Promote to Truck IN first before processing Truck OUT."
    #                 )
    #             )

    #         any_stmt = select(ImportTruckVisit).where(
    #             ImportTruckVisit.truck_number == truck_no
    #         ).order_by(ImportTruckVisit.created_at.desc())
    #         any_visit = (await db.execute(any_stmt)).scalars().first()

    #         if any_visit and any_visit.is_truck_out:
    #             raise HTTPException(
    #                 status_code=404,
    #                 detail=(
    #                     f"No active visit for truck {truck_no}. "
    #                     f"Last visit checked out at "
    #                     f"{ImportTruckQueueService._to_ist(any_visit.truck_out_date_time)}."
    #                 )
    #             )

    #         raise HTTPException(
    #             status_code=404,
    #             detail=f"No active truck visit found for '{truck_no}'. Truck has not been checked in."
    #         )

    #     assign_stmt = select(ImportGatePassAssignment).where(
    #         ImportGatePassAssignment.truck_visit_id == visit.id
    #     )
    #     assignments = (await db.execute(assign_stmt)).scalars().all()

    #     # ── Collect all emp_ids we need to resolve to names ─────────────────────
    #     emp_ids = set()
    #     for a in assignments:
    #         if a.assigned_by:
    #             emp_ids.add(a.assigned_by)

    #     # truck in/out users
    #     if visit.truck_in_by:
    #         emp_ids.add(visit.truck_in_by)
    #     if visit.truck_out_by:
    #         emp_ids.add(visit.truck_out_by)

    #     gate_passes = []
    #     pending_count = 0
    #     completed_count = 0

    #     # Pre-fetch loadings + collect their emp_ids too (gather first, then resolve)
    #     loadings_by_gp = {}
    #     gps_by_id = {}
    #     for assignment in assignments:
    #         gp = (await db.execute(
    #             select(ImportGatePass).where(ImportGatePass.id == assignment.gate_pass_id)
    #         )).scalar_one_or_none()
    #         if not gp:
    #             continue
    #         gps_by_id[assignment.id] = gp

    #         loading = (await db.execute(
    #             select(ImportGatePassLoading).where(
    #                 ImportGatePassLoading.gate_pass_id == gp.id,
    #                 ImportGatePassLoading.truck_visit_id == visit.id,
    #             )
    #         )).scalar_one_or_none()
    #         loadings_by_gp[assignment.id] = loading
    #         if loading and loading.loaded_by:
    #             emp_ids.add(loading.loaded_by)

    #     # ── Resolve emp_id → name in one query ──────────────────────────────────
    #     name_map = {}
    #     if emp_ids:
    #         users = (await db.execute(
    #             select(User.emp_id, User.name).where(User.emp_id.in_(emp_ids))
    #         )).all()
    #         name_map = {u.emp_id: u.name for u in users}

    #     for assignment in assignments:
    #         gp = gps_by_id.get(assignment.id)
    #         if not gp:
    #             continue
    #         loading = loadings_by_gp.get(assignment.id)

    #         pcs_loaded = loading.loaded_pcs if loading else 0
    #         pcs_remaining_for_truck = gp.pcs_remaining if assignment.is_active else 0

    #         is_done = (not assignment.is_active) or pcs_remaining_for_truck == 0
    #         if is_done:
    #             completed_count += 1
    #         else:
    #             pending_count += 1

    #         gate_passes.append({
    #             "gate_pass_no": gp.gate_pass_no,
    #             "awb": gp.awb_no,
    #             "hawb": gp.hawb_no,
    #             "pcs": gp.pcs_total,
    #             "pcs_loaded": pcs_loaded,
    #             "pcs_remaining": pcs_remaining_for_truck,
    #             "agent": gp.agent,
    #             "consignee": gp.consignee,
    #             "assigned_time": assignment.assigned_time,
    #             "assigned_by": assignment.assigned_by,
    #             "assigned_by_name": name_map.get(assignment.assigned_by),
    #             "gate_pass_out_time": loading.loaded_time if loading else None,

    #             "gate_pass_out_by": loading.loaded_by if loading else None,
    #             "gate_pass_out_by_name": name_map.get(loading.loaded_by) if loading else None,
    #             "is_active_assignment": assignment.is_active,
    #         })

    #     gate_passes.sort(
    #         key=lambda g: (
    #             0 if (g["is_active_assignment"] and g["pcs_remaining"] > 0) else 1,
    #             g["assigned_time"] or datetime.min
    #         )
    #     )

    #     if visit.is_truck_out:
    #         workflow_status = "TRUCK_OUT_DONE"
    #         message = f"Truck {truck_no} already checked out."
    #     elif pending_count == 0 and len(gate_passes) > 0:
    #         workflow_status = "READY_FOR_TRUCK_OUT"
    #         message = f"All {completed_count} gate pass(es) loaded. Ready for truck out."
    #     else:
    #         workflow_status = "READY_FOR_GP_OUT"
    #         message = f"{pending_count} gate pass(es) pending loading."

    #     return {
    #         "success": True,
    #         "truck_visit_id": visit.id,
    #         "truck_number": visit.truck_number,
    #         "driver_name": visit.driver_name,
    #         "driver_contact": visit.driver_contact,
    #         "token_no": visit.token_no,
    #         "status": visit.status,
    #         "truck_in_date_time": visit.truck_in_date_time,
    #         "truck_out_date_time": visit.truck_out_date_time,
    #           "truck_in_by": visit.truck_in_by,                          # ✅ new
    #             "truck_in_by_name": name_map.get(visit.truck_in_by),       # ✅ new
    #             "truck_out_by": visit.truck_out_by,                        # ✅ new
    #             "truck_out_by_name": name_map.get(visit.truck_out_by),     # ✅ new
    #         "workflow_status": workflow_status,
    #         "pending_gp_count": pending_count,
    #         "completed_gp_count": completed_count,
    #         "gate_passes": gate_passes,
    #         "message": message,
    #     }

    @staticmethod
    async def search_truck_for_out(
        db: AsyncSession,
        search_term: str,
        search_by: str = "truck_no",  # ← NEW: "truck_no" | "gp_no"
    ):
        """
        Find the active (BOOKED + truck_in + not truck_out) visit for the truck out screen.

        search_by:
        - "truck_no" → finds by truck_number (works for both TRUCK and BY_HAND visits)
        - "gp_no"    → finds active visit that has this GP currently assigned & pending
                    (typical use case: BY_HAND pickups where operator has only the GP slip)
        """
        term = (search_term or "").strip().upper()
        search_by = (search_by or "truck_no").strip().lower()

        if not term:
            raise HTTPException(status_code=400, detail="Search term is required")

        if search_by not in ("truck_no", "gp_no", "visit_id"):
            raise HTTPException(
                status_code=400,
                detail="search_by must be 'truck_no', 'gp_no', or 'visit_id'",
            )

        visit = None
        # ═══════════════════════════════════════════════════════════════════════════
        # BRANCH 0: Search by visit ID (used for refresh after any operation)
        # ═══════════════════════════════════════════════════════════════════════════
        if search_by == "visit_id":
            try:
                visit_id_int = int(term)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"Invalid visit_id: {term}")

            visit = (
                (
                    await db.execute(
                        select(ImportTruckVisit).where(
                            ImportTruckVisit.id == visit_id_int
                        )
                    )
                )
                .scalars()
                .first()
            )

            if not visit:
                raise HTTPException(
                    status_code=404, detail=f"Visit #{visit_id_int} not found."
                )

        # ═══════════════════════════════════════════════════════════════════════════
        # BRANCH 1: Search by GP number
        # ═══════════════════════════════════════════════════════════════════════════
        elif search_by == "gp_no":
            # Find the GP first
            gp_stmt = select(ImportGatePass).where(ImportGatePass.gate_pass_no == term)
            gp = (await db.execute(gp_stmt)).scalar_one_or_none()

            if not gp:
                raise HTTPException(
                    status_code=404, detail=f"Gate pass '{term}' not found in system."
                )

            # Find an ACTIVE assignment for this GP on a visit that's IN but not yet OUT
            # active_assign_stmt = (
            #     select(ImportGatePassAssignment, ImportTruckVisit)
            #     .join(
            #         ImportTruckVisit,
            #         ImportTruckVisit.id == ImportGatePassAssignment.truck_visit_id,
            #     )
            #     .where(
            #         ImportGatePassAssignment.gate_pass_id == gp.id,
            #         ImportGatePassAssignment.is_active == True,
            #         ImportTruckVisit.status == "BOOKED",
            #         ImportTruckVisit.is_truck_in == True,
            #         ImportTruckVisit.is_truck_out == False,
            #     )
            #     .order_by(ImportGatePassAssignment.assigned_time.desc())
            # )

            active_assign_stmt = (
                select(ImportGatePassAssignment, ImportTruckVisit)
                .join(
                    ImportTruckVisit,
                    ImportTruckVisit.id == ImportGatePassAssignment.truck_visit_id,
                )
                .where(
                    ImportGatePassAssignment.gate_pass_id == gp.id,
                    ImportTruckVisit.status == "BOOKED",
                    ImportTruckVisit.is_truck_in == True,
                    ImportTruckVisit.is_truck_out == False,
                    or_(
                        ImportGatePassAssignment.is_active == True,
                        exists().where(
                            ImportGatePassLoading.gate_pass_id == gp.id,
                            ImportGatePassLoading.truck_visit_id == ImportTruckVisit.id,
                        ),
                    ),
                )
                .order_by(ImportTruckVisit.truck_in_date_time.desc())
            )

            row = (await db.execute(active_assign_stmt)).first()

            # if not row:
            #     # Helpful error — check what state the GP is actually in
            #     any_assign_stmt = (
            #         select(ImportGatePassAssignment, ImportTruckVisit)
            #         .join(ImportTruckVisit, ImportTruckVisit.id == ImportGatePassAssignment.truck_visit_id)
            #         .where(ImportGatePassAssignment.gate_pass_id == gp.id)
            #         .order_by(ImportGatePassAssignment.assigned_time.desc())
            #     )
            #     any_row = (await db.execute(any_assign_stmt)).first()

            #     if any_row:
            #         _, any_visit = any_row
            #         if any_visit.is_truck_out:
            #             raise HTTPException(
            #                 status_code=404,
            #                 detail=(
            #                     f"Gate pass {term} was last on '{any_visit.truck_number}' "
            #                     f"which already checked out at "
            #                     f"{ImportTruckQueueService._to_ist(any_visit.truck_out_date_time)}."
            #                 )
            #             )
            #         raise HTTPException(
            #             status_code=404,
            #             detail=f"Gate pass {term} has no active pickup pending."
            #         )
            #     raise HTTPException(
            #         status_code=404,
            #         detail=f"Gate pass {term} not assigned to any visit yet."
            #     )

            if not row:
                # No active visit — build a friendly message from the GP's full history
                history_stmt = (
                    select(ImportGatePassAssignment, ImportTruckVisit)
                    .join(
                        ImportTruckVisit,
                        ImportTruckVisit.id == ImportGatePassAssignment.truck_visit_id,
                    )
                    .where(ImportGatePassAssignment.gate_pass_id == gp.id)
                    .order_by(ImportTruckVisit.truck_out_date_time.desc().nullslast())
                )
                history = (await db.execute(history_stmt)).all()

                if not history:
                    raise HTTPException(
                        status_code=404,
                        detail=f"Gate pass {term} is not assigned to any visit yet.",
                    )

                out_visits = [v for (_, v) in history if v.is_truck_out]

                if out_visits:

                    def carrier_label(v):
                        if getattr(v, "visit_type", "TRUCK") == "BY_HAND":
                            return f"{v.driver_name or 'by-hand pickup'} (by hand)"
                        return v.truck_number or "unknown truck"

                    # Deduplicate, keep most-recent-first order
                    seen = set()
                    labels = []
                    for v in out_visits:
                        lbl = carrier_label(v)
                        if lbl not in seen:
                            seen.add(lbl)
                            labels.append(lbl)

                    last_out = ImportTruckQueueService._to_ist(
                        out_visits[0].truck_out_date_time
                    )

                    if len(labels) == 1:
                        detail = (
                            f"Gate pass {term} already shipped on {labels[0]} "
                            f"(checked out {last_out}). No active pickup pending."
                        )
                    else:
                        joined = ", ".join(labels)
                        detail = (
                            f"Gate pass {term} already shipped on {len(labels)} visits: {joined} "
                            f"(last checkout {last_out}). No active pickup pending."
                        )

                    raise HTTPException(status_code=404, detail=detail)

                raise HTTPException(
                    status_code=404,
                    detail=f"Gate pass {term} has no active pickup pending.",
                )

            _, visit = row

        # ═══════════════════════════════════════════════════════════════════════════
        # BRANCH 2: Search by truck number (existing behavior)
        # ═══════════════════════════════════════════════════════════════════════════
        else:
            stmt = (
                select(ImportTruckVisit)
                .where(
                    ImportTruckVisit.truck_number == term,
                    ImportTruckVisit.status == "BOOKED",
                    ImportTruckVisit.is_truck_in == True,
                )
                .order_by(ImportTruckVisit.truck_in_date_time.desc())
            )
            visit = (await db.execute(stmt)).scalars().first()

            if not visit:
                queued_stmt = (
                    select(ImportTruckVisit)
                    .where(
                        ImportTruckVisit.truck_number == term,
                        ImportTruckVisit.status == "QUEUED",
                    )
                    .order_by(ImportTruckVisit.queued_at.desc())
                )
                queued_visit = (await db.execute(queued_stmt)).scalars().first()

                if queued_visit:
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Truck {term} is in QUEUE (Queue No: {queued_visit.queue_no}). "
                            f"Promote to Truck IN first before processing Truck OUT."
                        ),
                    )

                any_stmt = (
                    select(ImportTruckVisit)
                    .where(ImportTruckVisit.truck_number == term)
                    .order_by(ImportTruckVisit.created_at.desc())
                )
                any_visit = (await db.execute(any_stmt)).scalars().first()

                if any_visit and any_visit.is_truck_out:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            f"No active visit for truck {term}. "
                            f"Last visit checked out at "
                            f"{ImportTruckQueueService._to_ist(any_visit.truck_out_date_time)}."
                        ),
                    )

                raise HTTPException(
                    status_code=404,
                    detail=f"No active truck visit found for '{term}'. Truck has not been checked in.",
                )

        # ═══════════════════════════════════════════════════════════════════════════
        # COMMON: Build response (same for both branches)
        # ═══════════════════════════════════════════════════════════════════════════
        assign_stmt = select(ImportGatePassAssignment).where(
            ImportGatePassAssignment.truck_visit_id == visit.id
        )
        assignments = (await db.execute(assign_stmt)).scalars().all()

        # Collect all emp_ids we need to resolve to names
        emp_ids = set()
        for a in assignments:
            if a.assigned_by:
                emp_ids.add(a.assigned_by)

        if visit.truck_in_by:
            emp_ids.add(visit.truck_in_by)
        if visit.truck_out_by:
            emp_ids.add(visit.truck_out_by)

        gate_passes = []
        pending_count = 0
        completed_count = 0

        # Pre-fetch loadings + collect their emp_ids
        loadings_by_assign = {}
        gps_by_assign = {}
        for assignment in assignments:
            gp = (
                await db.execute(
                    select(ImportGatePass).where(
                        ImportGatePass.id == assignment.gate_pass_id
                    )
                )
            ).scalar_one_or_none()
            if not gp:
                continue
            gps_by_assign[assignment.id] = gp

            loading = (
                await db.execute(
                    select(ImportGatePassLoading).where(
                        ImportGatePassLoading.gate_pass_id == gp.id,
                        ImportGatePassLoading.truck_visit_id == visit.id,
                    )
                )
            ).scalar_one_or_none()
            loadings_by_assign[assignment.id] = loading
            if loading and loading.loaded_by:
                emp_ids.add(loading.loaded_by)

        # Resolve emp_id → name in one query
        name_map = {}
        if emp_ids:
            users = (
                await db.execute(
                    select(User.emp_id, User.name).where(User.emp_id.in_(emp_ids))
                )
            ).all()
            name_map = {u.emp_id: u.name for u in users}

        for assignment in assignments:
            gp = gps_by_assign.get(assignment.id)
            if not gp:
                continue
            loading = loadings_by_assign.get(assignment.id)

            pcs_loaded = loading.loaded_pcs if loading else 0
            pcs_remaining_for_truck = gp.pcs_remaining if assignment.is_active else 0

            is_done = (not assignment.is_active) or pcs_remaining_for_truck == 0
            if is_done:
                completed_count += 1
            else:
                pending_count += 1

             # final delivery for charge eligibility (frontend computes)
            final_delivery = None
            if gp.worker_assignment_shipment_id:
                final_delivery = (await db.execute(
                    select(WorkerAssignmentShipment.final_delivery_datetime).where(
                        WorkerAssignmentShipment.id == gp.worker_assignment_shipment_id
                    )
                )).scalar_one_or_none()

            gate_passes.append(
                {
                    "gate_pass_no": gp.gate_pass_no,
                    "awb": gp.awb_no,
                    "hawb": gp.hawb_no,
                    "pcs": gp.pcs_total,
                    "pcs_loaded": pcs_loaded,
                    "pcs_remaining": pcs_remaining_for_truck,
                    "agent": gp.agent,
                    "consignee": gp.consignee,
                    "assigned_time": assignment.assigned_time,
                    "assigned_by": assignment.assigned_by,
                    "assigned_by_name": name_map.get(assignment.assigned_by),
                    "gate_pass_out_time": loading.loaded_time if loading else None,
                    "gate_pass_out_by": loading.loaded_by if loading else None,
                    "gate_pass_out_by_name": (
                        name_map.get(loading.loaded_by) if loading else None
                    ),
                    "is_active_assignment": assignment.is_active,
                        # ── charge fields (read-only for truck-out page) ──
                    "final_delivery_datetime": final_delivery,
                    "storage_charge": float(assignment.storage_charge) if assignment.storage_charge is not None else None,
                    "challan_no": assignment.challan_no,
                }
            )

        gate_passes.sort(
            key=lambda g: (
                0 if (g["is_active_assignment"] and g["pcs_remaining"] > 0) else 1,
                g["assigned_time"] or datetime.min,
            )
        )

        # Workflow status with by-hand-aware messages
        is_by_hand = getattr(visit, "visit_type", "TRUCK") == "BY_HAND"
        label = visit.driver_name if is_by_hand else visit.truck_number

        if visit.is_truck_out:
            workflow_status = "TRUCK_OUT_DONE"
            message = (
                f"Pickup by {label} already completed."
                if is_by_hand
                else f"Truck {label} already checked out."
            )
        elif pending_count == 0 and len(gate_passes) > 0:
            workflow_status = "READY_FOR_TRUCK_OUT"
            message = (
                f"All {completed_count} gate pass(es) loaded. Ready to mark pickup complete."
                if is_by_hand
                else f"All {completed_count} gate pass(es) loaded. Ready for truck out."
            )
        else:
            workflow_status = "READY_FOR_GP_OUT"
            message = f"{pending_count} gate pass(es) pending loading."

        return {
            "success": True,
            "truck_visit_id": visit.id,
            "truck_number": visit.truck_number,
            "visit_type": getattr(visit, "visit_type", "TRUCK"),  # ← NEW
            "driver_name": visit.driver_name,
            "driver_contact": visit.driver_contact,
            "token_no": visit.token_no,
            "status": visit.status,
            "truck_in_date_time": visit.truck_in_date_time,
            "truck_out_date_time": visit.truck_out_date_time,
            "truck_in_by": visit.truck_in_by,
            "truck_in_by_name": name_map.get(visit.truck_in_by),
            "truck_out_by": visit.truck_out_by,
            "truck_out_by_name": name_map.get(visit.truck_out_by),
            "workflow_status": workflow_status,
            "pending_gp_count": pending_count,
            "completed_gp_count": completed_count,
            "gate_passes": gate_passes,
            "message": message,
            "queued_at": visit.queued_at,
            "charges_cleared": visit.charges_cleared,
        }

    @staticmethod
    async def search_for_customer_care(
        db: AsyncSession,
        search_term: str,
        search_by: str = "truck_no",  # "truck_no" | "gp_no"
    ):
        """
        Customer-care dashboard search.
        Finds the ACTIVE visit (BOOKED + truck_in + not truck_out) for a truck or GP.
        Works for both TRUCK and BY_HAND visits.
        Returns visit + its gate passes with shipment timing data for SLA review.
        """
        term = (search_term or "").strip().upper()
        search_by = (search_by or "truck_no").strip().lower()

        if not term:
            raise HTTPException(status_code=400, detail="Search term is required")
        if search_by not in ("truck_no", "gp_no"):
            raise HTTPException(
                status_code=400, detail="search_by must be 'truck_no' or 'gp_no'"
            )

        visit = None

        # ── BRANCH A: by GP number ──────────────────────────────────────────────
        # if search_by == "gp_no":
        #     gp = (await db.execute(
        #         select(ImportGatePass).where(ImportGatePass.gate_pass_no == term)
        #     )).scalar_one_or_none()

        #     if not gp:
        #         raise HTTPException(
        #             status_code=404,
        #             detail=f"Gate pass {term} not found in the system."
        #         )

        #     # Active assignment on an active visit
        #     active_row = (await db.execute(
        #         select(ImportGatePassAssignment, ImportTruckVisit)
        #         .join(ImportTruckVisit, ImportTruckVisit.id == ImportGatePassAssignment.truck_visit_id)
        #         .where(
        #             ImportGatePassAssignment.gate_pass_id == gp.id,
        #             ImportGatePassAssignment.is_active == True,
        #             ImportTruckVisit.status == "BOOKED",
        #             ImportTruckVisit.is_truck_in == True,
        #             ImportTruckVisit.is_truck_out == False,
        #         )
        #         .order_by(ImportGatePassAssignment.assigned_time.desc())
        #     )).first()

        #     if not active_row:
        #         # Build a friendly "no active visit" message from history
        #         history = (await db.execute(
        #             select(ImportGatePassAssignment, ImportTruckVisit)
        #             .join(ImportTruckVisit, ImportTruckVisit.id == ImportGatePassAssignment.truck_visit_id)
        #             .where(ImportGatePassAssignment.gate_pass_id == gp.id)
        #             .order_by(ImportTruckVisit.truck_out_date_time.desc().nullslast())
        #         )).all()

        #         out_visits = [v for (_, v) in history if v.is_truck_out]
        #         if out_visits:
        #             def carrier(v):
        #                 if getattr(v, "visit_type", "TRUCK") == "BY_HAND":
        #                     return f"{v.driver_name or 'by-hand pickup'} (by hand)"
        #                 return v.truck_number or "unknown truck"

        #             seen, labels = set(), []
        #             for v in out_visits:
        #                 lbl = carrier(v)
        #                 if lbl not in seen:
        #                     seen.add(lbl); labels.append(lbl)

        #             last_out = ImportTruckQueueService._to_ist(out_visits[0].truck_out_date_time)
        #             if len(labels) == 1:
        #                 detail = (
        #                     f"No active visit for gate pass {term}. "
        #                     f"It already shipped on {labels[0]} (checked out {last_out})."
        #                 )
        #             else:
        #                 detail = (
        #                     f"No active visit for gate pass {term}. "
        #                     f"It already shipped on {len(labels)} visits: {', '.join(labels)} "
        #                     f"(last checkout {last_out})."
        #                 )
        #             raise HTTPException(status_code=404, detail=detail)

        #         raise HTTPException(
        #             status_code=404,
        #             detail=f"No active visit for gate pass {term}. It is not currently on any truck or pickup."
        #         )

        #     _, visit = active_row

        # ── BRANCH A: by GP number ──────────────────────────────────────────────
        if search_by == "gp_no":
            gp = (
                await db.execute(
                    select(ImportGatePass).where(ImportGatePass.gate_pass_no == term)
                )
            ).scalar_one_or_none()

            # if not gp:
            #     raise HTTPException(
            #         status_code=404, detail=f"Gate pass {term} not found in the system."
            #     )

            if not gp:
                src = (await db.execute(
                    select(WorkerAssignmentShipment.gate_pass_no)
                    .where(WorkerAssignmentShipment.gate_pass_no == term)
                    .limit(1)
                )).first()
                if src:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            f"Gate pass {term} exists in system but has not entered the truck-in-out flow yet. "
                            f"It hasn't been staged or assigned to any truck/pickup."
                        ),
                    )
                raise HTTPException(
                    status_code=404,
                    detail=f"Gate pass {term} not found anywhere in the system.",
                )

            # Active assignment on an active visit
            # active_row = (
            #     await db.execute(
            #         select(ImportGatePassAssignment, ImportTruckVisit)
            #         .join(
            #             ImportTruckVisit,
            #             ImportTruckVisit.id == ImportGatePassAssignment.truck_visit_id,
            #         )
            #         .where(
            #             ImportGatePassAssignment.gate_pass_id == gp.id,
            #             ImportGatePassAssignment.is_active == True,  # ← KEEP this
            #             ImportTruckVisit.status == "BOOKED",
            #             ImportTruckVisit.is_truck_in == True,
            #             ImportTruckVisit.is_truck_out == False,
            #         )
            #         .order_by(ImportGatePassAssignment.assigned_time.desc())
            #     )
            # ).first()

            active_row = (
                await db.execute(
                    select(ImportGatePassAssignment, ImportTruckVisit)
                    .join(
                        ImportTruckVisit,
                        ImportTruckVisit.id == ImportGatePassAssignment.truck_visit_id,
                    )
                    .where(
                        ImportGatePassAssignment.gate_pass_id == gp.id,
                        ImportTruckVisit.status == "BOOKED",
                        ImportTruckVisit.is_truck_in == True,
                        ImportTruckVisit.is_truck_out == False,
                        or_(
                            ImportGatePassAssignment.is_active == True,
                            exists().where(
                                ImportGatePassLoading.gate_pass_id == gp.id,
                                ImportGatePassLoading.truck_visit_id == ImportTruckVisit.id,
                            ),
                        ),
                    )
                    .order_by(ImportTruckVisit.truck_in_date_time.desc())
                )
            ).first()

            if not active_row:
                # No ACTIVE assignment. Figure out the most useful reason.
                # Pull full history, newest visit first.
                history = (
                    await db.execute(
                        select(ImportGatePassAssignment, ImportTruckVisit)
                        .join(
                            ImportTruckVisit,
                            ImportTruckVisit.id
                            == ImportGatePassAssignment.truck_visit_id,
                        )
                        .where(ImportGatePassAssignment.gate_pass_id == gp.id)
                        .order_by(ImportTruckVisit.created_at.desc())
                    )
                ).all()

                def carrier_label(v):
                    if getattr(v, "visit_type", "TRUCK") == "BY_HAND":
                        return f"by-hand pickup by {v.driver_name or 'unknown'}"
                    return f"truck {v.truck_number or 'unknown'}"

                # CASE 1: GP is loaded but sitting on a visit that is STILL INSIDE (not out).
                #         This is the case you asked about — tell the operator clearly.
                inside_visits = [
                    v
                    for (_, v) in history
                    if v.status == "BOOKED" and v.is_truck_in and not v.is_truck_out
                ]
                if inside_visits:
                    v = inside_visits[0]  # newest still-inside visit
                    label = carrier_label(v)
                    raise HTTPException(
                        status_code=409,
                        detail=(
                            f"Gate pass {term} is already loaded on {label}, "
                            f"which is still inside (not checked out yet). "
                            f"Nothing pending for this gate pass."
                        ),
                    )

                # CASE 2: GP's visits have all checked out — tell where it shipped.
                out_visits = [v for (_, v) in history if v.is_truck_out]
                if out_visits:
                    # newest checkout first
                    out_visits.sort(
                        key=lambda x: x.truck_out_date_time or datetime.min,
                        reverse=True,
                    )
                    seen, labels = set(), []
                    for v in out_visits:
                        lbl = carrier_label(v)
                        if lbl not in seen:
                            seen.add(lbl)
                            labels.append(lbl)

                    last_out = ImportTruckQueueService._to_ist(
                        out_visits[0].truck_out_date_time
                    )
                    if len(labels) == 1:
                        detail = (
                            f"No active visit for gate pass {term}. "
                            f"It already shipped on {labels[0]} (checked out {last_out})."
                        )
                    else:
                        detail = (
                            f"No active visit for gate pass {term}. "
                            f"It already shipped on {len(labels)} visits: {', '.join(labels)} "
                            f"(last checkout {last_out})."
                        )
                    raise HTTPException(status_code=404, detail=detail)

                # CASE 3: GP exists but never assigned to any visit.
                raise HTTPException(
                    status_code=404,
                    detail=(
                        f"No active visit for gate pass {term}. "
                        f"It is not currently assigned to any truck or pickup."
                    ),
                )

            _, visit = active_row

        # ── BRANCH B: by truck number ───────────────────────────────────────────
        else:
            visit = (
                (
                    await db.execute(
                        select(ImportTruckVisit)
                        .where(
                            ImportTruckVisit.truck_number == term,
                            ImportTruckVisit.status == "BOOKED",
                            ImportTruckVisit.is_truck_in == True,
                            ImportTruckVisit.is_truck_out == False,
                        )
                        .order_by(ImportTruckVisit.truck_in_date_time.desc())
                    )
                )
                .scalars()
                .first()
            )

            if not visit:
                # Queued? checked out? give a useful reason
                queued = (
                    (
                        await db.execute(
                            select(ImportTruckVisit)
                            .where(
                                ImportTruckVisit.truck_number == term,
                                ImportTruckVisit.status == "QUEUED",
                            )
                            .order_by(ImportTruckVisit.queued_at.desc())
                        )
                    )
                    .scalars()
                    .first()
                )
                if queued:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            f"No active visit for truck {term}. "
                            f"It is currently in QUEUE (Queue No: {queued.queue_no}), not yet checked in."
                        ),
                    )

                last = (
                    (
                        await db.execute(
                            select(ImportTruckVisit)
                            .where(ImportTruckVisit.truck_number == term)
                            .order_by(ImportTruckVisit.created_at.desc())
                        )
                    )
                    .scalars()
                    .first()
                )
                if last and last.is_truck_out:
                    raise HTTPException(
                        status_code=404,
                        detail=(
                            f"No active visit for truck {term}. "
                            f"Its last visit already checked out at "
                            f"{ImportTruckQueueService._to_ist(last.truck_out_date_time)}."
                        ),
                    )

                raise HTTPException(
                    status_code=404,
                    detail=f"No active visit for truck {term}. It has not been checked in.",
                )

        # ── COMMON: build gate-pass rows with shipment timing data ──────────────
        assignments = (
            (
                await db.execute(
                    select(ImportGatePassAssignment).where(
                        ImportGatePassAssignment.truck_visit_id == visit.id
                    )
                )
            )
            .scalars()
            .all()
        )

        gate_passes = []
        for assignment in assignments:
            gp = (
                await db.execute(
                    select(ImportGatePass).where(
                        ImportGatePass.id == assignment.gate_pass_id
                    )
                )
            ).scalar_one_or_none()
            if not gp:
                continue

            # Shipment row holds the timing/SLA fields the dashboard shows
            shipment = None
            if gp.worker_assignment_shipment_id:
                shipment = (
                    await db.execute(
                        select(WorkerAssignmentShipment).where(
                            WorkerAssignmentShipment.id
                            == gp.worker_assignment_shipment_id
                        )
                    )
                ).scalar_one_or_none()

            # Loading on THIS visit → gate-out time + loaded pcs
            loading = (
                await db.execute(
                    select(
                        func.coalesce(
                            func.sum(ImportGatePassLoading.loaded_pcs), 0
                        ).label("loaded"),
                        func.max(ImportGatePassLoading.loaded_time).label("out_time"),
                    ).where(
                        ImportGatePassLoading.gate_pass_id == gp.id,
                        ImportGatePassLoading.truck_visit_id == visit.id,
                    )
                )
            ).first()
            loaded_pcs = int(loading.loaded) if loading else 0
            gate_out_time = loading.out_time if loading else None

            gate_passes.append(
                {
                    "gp_no": gp.gate_pass_no,
                    "pcs": shipment.no_of_pc if shipment else gp.pcs_total,
                    "pcs_loaded": loaded_pcs,
                    "pcs_remaining": gp.pcs_remaining,
                    "weight_kgs": (
                        shipment.weight_in_kgs if shipment else gp.gross_wt_total
                    ),
                    "agent": gp.agent,
                    "consignee": gp.consignee,
                    "awb": gp.awb_no,
                    "hawb": gp.hawb_no,
                    "gp_issued_datetime": (
                        shipment.gate_pass_issued_date_time_combo
                        if shipment
                        else gp.issued_date
                    ),
                    "gp_end_datetime": (
                        shipment.gate_pass_end_datetime if shipment else None
                    ),
                    "final_delivery_datetime": (
                        shipment.final_delivery_datetime if shipment else None
                    ),
                    "gate_out_time": gate_out_time,  # this visit's loading time
                    "is_active_assignment": assignment.is_active,

                     # ── NEW: per-GP charge data (from the assignment row) ──
                    "storage_charge": float(assignment.storage_charge) if assignment.storage_charge is not None else None,
                    "challan_no": assignment.challan_no,
                    "charge_remarks": assignment.charge_remarks,
                }
            )

        is_by_hand = getattr(visit, "visit_type", "TRUCK") == "BY_HAND"

        return {
            "success": True,
            "truck_visit_id": visit.id,
            "truck_no": visit.truck_number,  # None for by-hand
            "visit_type": getattr(visit, "visit_type", "TRUCK"),
            "receiver_name": visit.driver_name,  # person / driver
            "driver_contact": visit.driver_contact,
            "token_no": visit.token_no,
            "queue_no": visit.queue_no,
            "queued_at": visit.queued_at,  # SLA entry time (if queued)
            "charges_cleared": visit.charges_cleared,
            "truck_in": visit.truck_in_date_time,  # SLA entry time (if direct in)
            "truck_out": visit.truck_out_date_time,  # always null here (active only)
            "status": visit.status,
            "gate_passes": gate_passes,
            "message": (
                f"Active {'by-hand pickup' if is_by_hand else 'truck'} found "
                f"with {len(gate_passes)} gate pass(es)."
            ),
        }

    @staticmethod
    async def save_gp_storage_charge_from_customer(
        db, truck_visit_id, gate_pass_no, storage_charge, challan_no, remarks, emp_id
    ):
        visit = (
            await db.execute(
                select(ImportTruckVisit).where(ImportTruckVisit.id == truck_visit_id)
            )
        ).scalar_one_or_none()
        if not visit:
            raise HTTPException(404, "Truck visit not found")
        if visit.is_truck_out:
            raise HTTPException(400, "Visit already checked out — charges locked")

        gp = (
            await db.execute(
                select(ImportGatePass).where(
                    ImportGatePass.gate_pass_no == gate_pass_no
                )
            )
        ).scalar_one_or_none()
        if not gp:
            raise HTTPException(404, f"Gate pass {gate_pass_no} not found")

        if storage_charge is None or storage_charge < 0:
            raise HTTPException(400, "Storage charge must be 0 or more")
        if not challan_no or not challan_no.strip():
            raise HTTPException(400, "Challan number is required")

        # The assignment row IS the per-GP-per-visit record
        assignment = (
            await db.execute(
                select(ImportGatePassAssignment).where(
                    ImportGatePassAssignment.gate_pass_id == gp.id,
                    ImportGatePassAssignment.truck_visit_id == truck_visit_id,
                )
            )
        ).scalar_one_or_none()
        if not assignment:
            raise HTTPException(404, f"GP {gate_pass_no} is not assigned to this visit")

        assignment.storage_charge = storage_charge
        assignment.challan_no = challan_no.strip()
        assignment.charge_remarks = remarks
        assignment.charge_by = emp_id
        assignment.charge_at = datetime.now(timezone.utc)

        await db.commit()
        return {
            "success": True,
            "gate_pass_no": gp.gate_pass_no,
            "storage_charge": float(storage_charge),
            "challan_no": challan_no.strip(),
            "remarks": remarks,
            "message": f"Charge saved for GP {gp.gate_pass_no}",
        }

    # @staticmethod
    # async def _visit_charge_status(db: AsyncSession, visit: ImportTruckVisit):
    #     """Returns (any_charge_needed: bool, missing_gp_nos: list)."""
    #     try:
    #         free_hours = float(
    #             await AppConfigService.get_value(
    #                 db, "IMPORT", "free_hours_for_truck_in"
    #             )
    #         )
    #     except Exception:
    #         free_hours = 4.0

    #     anchor = visit.queued_at or visit.truck_in_date_time
    #     if anchor and anchor.tzinfo is None:
    #         anchor = anchor.replace(tzinfo=timezone.utc)

    #     assignments = (
    #         (
    #             await db.execute(
    #                 select(ImportGatePassAssignment).where(
    #                     ImportGatePassAssignment.truck_visit_id == visit.id,
    #                     ImportGatePassAssignment.is_active == True,
    #                 )
    #             )
    #         )
    #         .scalars()
    #         .all()
    #     )

    #     any_needed = False
    #     missing = []
    #     for a in assignments:
    #         gp = (
    #             await db.execute(
    #                 select(ImportGatePass).where(ImportGatePass.id == a.gate_pass_id)
    #             )
    #         ).scalar_one_or_none()
    #         if not gp:
    #             continue

    #         final_delivery = None
    #         if gp.worker_assignment_shipment_id:
    #             final_delivery = (
    #                 await db.execute(
    #                     select(WorkerAssignmentShipment.final_delivery_datetime).where(
    #                         WorkerAssignmentShipment.id
    #                         == gp.worker_assignment_shipment_id
    #                     )
    #                 )
    #             ).scalar_one_or_none()

    #         eligible = False
    #         if anchor and final_delivery:
    #             fd = (
    #                 final_delivery
    #                 if final_delivery.tzinfo
    #                 else final_delivery.replace(tzinfo=timezone.utc)
    #             )
    #             waited_h = (anchor - fd).total_seconds() / 3600.0
    #             eligible = waited_h > free_hours

    #         if eligible:
    #             any_needed = True
    #             if a.storage_charge is None or not a.challan_no:
    #                 missing.append(gp.gate_pass_no)

    #     return any_needed, missing

    @staticmethod
    async def _visit_charge_status(db: AsyncSession, visit: ImportTruckVisit):
        """Returns (any_charge_needed: bool, missing_gp_nos: list).
        Considers a GP if it's still active (pending) OR was loaded on THIS visit."""
        try:
            free_hours = float(await AppConfigService.get_value(db, "IMPORT", "free_hours_for_truck_in"))
        except Exception:
            free_hours = 4.0

        anchor = visit.queued_at or visit.truck_in_date_time
        if anchor and anchor.tzinfo is None:
            anchor = anchor.replace(tzinfo=timezone.utc)

        # ALL assignments on this visit (active AND inactive) — loaded GPs are inactive
        assignments = (await db.execute(
            select(ImportGatePassAssignment).where(
                ImportGatePassAssignment.truck_visit_id == visit.id,
            )
        )).scalars().all()

        any_needed = False
        missing = []
        for a in assignments:
            gp = (await db.execute(
                select(ImportGatePass).where(ImportGatePass.id == a.gate_pass_id)
            )).scalar_one_or_none()
            if not gp:
                continue

            # Was this GP loaded on THIS visit?
            loaded_here = (await db.execute(
                select(func.count()).select_from(ImportGatePassLoading).where(
                    ImportGatePassLoading.gate_pass_id == gp.id,
                    ImportGatePassLoading.truck_visit_id == visit.id,
                )
            )).scalar() or 0

            # Skip only if inactive AND never loaded here (passed through / moved on)
            if not a.is_active and loaded_here == 0:
                continue

            final_delivery = None
            if gp.worker_assignment_shipment_id:
                final_delivery = (await db.execute(
                    select(WorkerAssignmentShipment.final_delivery_datetime).where(
                        WorkerAssignmentShipment.id == gp.worker_assignment_shipment_id
                    )
                )).scalar_one_or_none()

            eligible = False
            if anchor and final_delivery:
                fd = final_delivery if final_delivery.tzinfo else final_delivery.replace(tzinfo=timezone.utc)
                waited_h = (anchor - fd).total_seconds() / 3600.0
                eligible = waited_h > free_hours

            if eligible:
                any_needed = True
                if a.storage_charge is None or not a.challan_no:
                    missing.append(gp.gate_pass_no)

        return any_needed, missing

class ImportGatePassReassignService:

    @staticmethod
    async def reassign_gate_pass(
        db: AsyncSession,
        gate_pass_no: str,
        from_truck_visit_id: int,
        to_truck_visit_id: int,
        operator: str,
        remarks: str = None,
    ):
        """
        Reassign remaining pieces of gate pass to another truck.
        Works for both unloaded and partially loaded gate passes.
        """

        # Validate trucks
        from_truck_stmt = select(ImportTruckVisit).where(
            ImportTruckVisit.id == from_truck_visit_id
        )
        from_result = await db.execute(from_truck_stmt)
        from_visit = from_result.scalar_one_or_none()

        if not from_visit:
            raise HTTPException(status_code=404, detail="Source truck visit not found")

        to_truck_stmt = select(ImportTruckVisit).where(
            ImportTruckVisit.id == to_truck_visit_id
        )
        to_result = await db.execute(to_truck_stmt)
        to_visit = to_result.scalar_one_or_none()

        if not to_visit:
            raise HTTPException(
                status_code=404, detail="Destination truck visit not found"
            )

        # Validate gate pass
        gp_stmt = select(ImportGatePass).where(
            ImportGatePass.gate_pass_no == gate_pass_no
        )
        gp_result = await db.execute(gp_stmt)
        gate_pass = gp_result.scalar_one_or_none()

        if not gate_pass:
            raise HTTPException(
                status_code=404, detail=f"Gate pass not found: {gate_pass_no}"
            )

        if gate_pass.status == "C":
            raise HTTPException(
                status_code=400, detail=f"Gate pass already closed: {gate_pass_no}"
            )

        if gate_pass.pcs_remaining <= 0:
            raise HTTPException(
                status_code=400,
                detail=f"No pieces remaining to reassign for {gate_pass_no}",
            )

        # Verify current active assignment is to source truck
        current_assign_stmt = select(ImportGatePassAssignment).where(
            ImportGatePassAssignment.gate_pass_id == gate_pass.id,
            ImportGatePassAssignment.is_active == True,
        )
        current_assign_result = await db.execute(current_assign_stmt)
        current_assignment = current_assign_result.scalar_one_or_none()

        if not current_assignment:
            raise HTTPException(
                status_code=400,
                detail=f"Gate pass {gate_pass_no} has no active assignment",
            )

        if current_assignment.truck_visit_id != from_truck_visit_id:
            raise HTTPException(
                status_code=400,
                detail=f"Gate pass {gate_pass_no} not currently assigned to specified source truck",
            )

        # Deactivate current assignment
        await db.execute(
            update(ImportGatePassAssignment)
            .where(ImportGatePassAssignment.id == current_assignment.id)
            .values(is_active=False)
        )

        # Create new assignment
        new_assignment = ImportGatePassAssignment(
            gate_pass_id=gate_pass.id,
            truck_visit_id=to_visit.id,
            assigned_by=operator,
            assigned_time=datetime.now(timezone.utc),
            is_active=True,
            remarks=remarks
            or f"Reassigned from truck {from_visit.truck_number} ({gate_pass.pcs_remaining} pcs remaining)",
        )
        db.add(new_assignment)
        await db.flush()

        await log_activity_of_imp_truck_in_out(
            db,
            event_type="GP_REASSIGNED",
            entity_type="gp_assignment",
            entity_id=new_assignment.id,  # ← now valid
            truck_visit_id=to_visit.id,
            truck_number=to_visit.truck_number,
            gate_pass_no=gate_pass.gate_pass_no,
            description=(
                f"GP {gate_pass.gate_pass_no} reassigned from truck {from_visit.truck_number} (visit #{from_visit.id}) "
                f"to truck {to_visit.truck_number} (visit #{to_visit.id}). {gate_pass.pcs_remaining} pcs remaining."
            ),
            reason=remarks,
            snapshot_before={
                "from_truck_visit_id": from_truck_visit_id,
                "from_truck_number": from_visit.truck_number,
                "old_assignment_id": current_assignment.id,
                "old_assignment_is_active": True,
                "pcs_remaining": gate_pass.pcs_remaining,
            },
            snapshot_after={
                "to_truck_visit_id": to_visit.id,
                "to_truck_number": to_visit.truck_number,
                "new_assignment_id": new_assignment.id,
                "new_assignment_is_active": True,
                "pcs_remaining": gate_pass.pcs_remaining,  # same — reassign doesn't load
            },
            performed_by=operator,
        )
        await db.commit()
        await db.refresh(new_assignment)

        return {
            "success": True,
            "gate_pass_no": gate_pass.gate_pass_no,
            "from_truck": from_visit.truck_number,
            "to_truck": to_visit.truck_number,
            "remaining_pcs": gate_pass.pcs_remaining,
            "message": f"Gate pass reassigned: {gate_pass.pcs_remaining} pcs remaining",
        }


class ImportTruckQueueService:

    @staticmethod
    def _to_ist(dt: datetime | None) -> str:
        IST = pytz.timezone("Asia/Kolkata")
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(IST).strftime("%d-%b-%Y %H:%M:%S")

    @staticmethod
    async def search_queue(
        db: AsyncSession, queue_no: str = None, truck_number: str = None
    ):
        if not queue_no and not truck_number:
            raise HTTPException(
                status_code=400, detail="Provide queue_no or truck_number"
            )

        # ── Search WITHOUT status filter first ───────────────────────────────────
        stmt = select(ImportTruckVisit)

        if queue_no:
            stmt = stmt.where(ImportTruckVisit.queue_no == queue_no)
        elif truck_number:
            # Get the most recent visit for this truck
            stmt = stmt.where(
                ImportTruckVisit.truck_number == truck_number.upper()
            ).order_by(ImportTruckVisit.created_at.desc())

        result = await db.execute(stmt)
        visit = result.scalars().first()

        # ── Not found at all ─────────────────────────────────────────────────────
        if not visit:
            if queue_no:
                raise HTTPException(
                    status_code=404,
                    detail=f"Queue number '{queue_no}' does not exist in the system.",
                )
            else:
                raise HTTPException(
                    status_code=404,
                    detail=f"No records found for truck '{truck_number}'. Truck has never been queued or checked in.",
                )

        # ── Found — check status ──────────────────────────────────────────────────
        if visit.status == "BOOKED" and visit.is_truck_in and not visit.is_truck_out:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{'Queue ' + visit.queue_no + ' was' if visit.queue_no else 'Truck was'} already promoted to truck IN. "
                    f"Truck: {visit.truck_number} | "
                    f"Truck IN at: {ImportTruckQueueService._to_ist(visit.truck_in_date_time) if visit.truck_in_date_time else 'N/A'}. "
                    f"Search by truck number in the truck list to view details."
                ),
            )

        if visit.status == "BOOKED" and visit.is_truck_out:
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{'Queue ' + visit.queue_no + ' was' if visit.queue_no else 'Truck was'} promoted to truck IN and has already checked OUT. "
                    f"Truck: {visit.truck_number} | "
                    f"Truck OUT at: {ImportTruckQueueService._to_ist(visit.truck_out_date_time) if visit.truck_out_date_time else 'N/A'}. "
                    f"This visit is fully completed."
                ),
            )

        if visit.status == "CANCELLED":
            raise HTTPException(
                status_code=409,
                detail=(
                    f"{'Queue ' + visit.queue_no if visit.queue_no else 'This queue'} was cancelled. "
                    f"Truck: {visit.truck_number} | "
                    f"Remarks: {visit.remarks or 'No remarks'}. "
                    f"A new queue must be created for this truck."
                ),
            )

        # ── Still QUEUED — normal flow ────────────────────────────────────────────
        if visit.status != "QUEUED":
            raise HTTPException(
                status_code=400,
                detail=f"Unexpected status '{visit.status}' for truck {visit.truck_number}. Please contact support.",
            )

        # Fetch gate passes
        assign_stmt = select(ImportGatePassAssignment).where(
            ImportGatePassAssignment.truck_visit_id == visit.id,
            ImportGatePassAssignment.is_active == True,
        )
        assign_result = await db.execute(assign_stmt)
        assignments = assign_result.scalars().all()

        gate_passes = []
        for assignment in assignments:
            gp_stmt = select(ImportGatePass).where(
                ImportGatePass.id == assignment.gate_pass_id
            )
            gp_result = await db.execute(gp_stmt)
            gp = gp_result.scalar_one_or_none()
            if gp:
                gate_passes.append(
                    {
                        "gate_pass_no": gp.gate_pass_no,
                        "awb": gp.awb_no,
                        "hawb": gp.hawb_no,
                        "pcs": gp.pcs_total,
                        "pcs_remaining": gp.pcs_remaining,
                        "agent": gp.agent,
                        "consignee": gp.consignee,
                    }
                )

        return {
            "success": True,
            "truck_visit_id": visit.id,
            "queue_no": visit.queue_no,
            "truck_number": visit.truck_number,
            "driver_name": visit.driver_name,
            "driver_contact": visit.driver_contact,
            "token_no": visit.token_no,
            "queued_at": visit.queued_at,
            "queued_by": visit.queued_by,
            "status": visit.status,
            "gate_passes": gate_passes,
        }

    @staticmethod
    async def promote_queue_to_truck_in(
        db: AsyncSession, truck_visit_id: int, emp_id: str, device_id: str = None
    ):
        """
        Promote a QUEUED truck visit to TRUCKED IN.
        Just flips status + sets truck_in fields. Gate passes already assigned.
        """
        stmt = select(ImportTruckVisit).where(
            ImportTruckVisit.id == truck_visit_id, ImportTruckVisit.status == "QUEUED"
        )
        result = await db.execute(stmt)
        visit = result.scalar_one_or_none()

        if not visit:
            raise HTTPException(status_code=404, detail="Queued truck visit not found")

        # ═══ CAPTURE SNAPSHOT BEFORE CHANGE ═══
        snapshot_before = {
            "status": visit.status,
            "is_truck_in": visit.is_truck_in,
            "truck_in_date_time": (
                visit.truck_in_date_time.isoformat()
                if visit.truck_in_date_time
                else None
            ),
            "remarks": visit.remarks,
        }

        utc_now = datetime.now(timezone.utc)

        visit.is_truck_in = True
        visit.truck_in_by = emp_id
        visit.truck_in_device = device_id
        visit.truck_in_date_time = utc_now
        visit.status = "BOOKED"
        visit.remarks = "Promoted from queue"
        visit.updated_at = utc_now

        snapshot_after = {
            "status": visit.status,
            "is_truck_in": True,
            "truck_in_date_time": visit.truck_in_date_time.isoformat(),
            "remarks": visit.remarks,
            "truck_in_by": emp_id,
        }

        await log_activity_of_imp_truck_in_out(
            db,
            event_type="QUEUE_PROMOTED",
            entity_type="truck_visit",
            entity_id=visit.id,
            truck_visit_id=visit.id,
            truck_number=visit.truck_number,
            queue_no=visit.queue_no,
            token_no=visit.token_no,
            description=(
                f"Queue {visit.queue_no} promoted to truck IN. "
                f"Truck: {visit.truck_number} (visit_id #{visit.id}), Token: {visit.token_no}."
            ),
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
            performed_by=emp_id,
            device_id=device_id,
        )

        await db.commit()
        await db.refresh(visit)

        return {
            "success": True,
            "truck_visit_id": visit.id,
            "queue_no": visit.queue_no,
            "truck_number": visit.truck_number,
            "token_no": visit.token_no,
            "truck_in_date_time": visit.truck_in_date_time.isoformat(),
            "message": f"Truck {visit.truck_number} promoted from queue to IN",
        }

    @staticmethod
    async def cancel_queue(
        db: AsyncSession, truck_visit_id: int, emp_id: str, remarks: str = None
    ):
        """
        Cancel a queued truck. Deactivates assignments, marks CANCELLED.
        Does NOT delete — keeps audit trail.
        """
        stmt = select(ImportTruckVisit).where(
            ImportTruckVisit.id == truck_visit_id, ImportTruckVisit.status == "QUEUED"
        )
        result = await db.execute(stmt)
        visit = result.scalar_one_or_none()

        if not visit:
            raise HTTPException(status_code=404, detail="Queued truck visit not found")

        # ═══ CAPTURE SNAPSHOT BEFORE CHANGE ═══
        snapshot_before = {
            "status": visit.status,
            "remarks": visit.remarks,
        }

        # Get list of GPs that will be deactivated (for richer description)
        active_gps_stmt = (
            select(ImportGatePassAssignment, ImportGatePass)
            .join(
                ImportGatePass,
                ImportGatePass.id == ImportGatePassAssignment.gate_pass_id,
            )
            .where(
                ImportGatePassAssignment.truck_visit_id == truck_visit_id,
                ImportGatePassAssignment.is_active == True,
            )
        )
        active_gp_rows = (await db.execute(active_gps_stmt)).all()
        deactivated_gp_nos = [gp.gate_pass_no for (_, gp) in active_gp_rows]

        # Deactivate all active assignments
        await db.execute(
            update(ImportGatePassAssignment)
            .where(
                ImportGatePassAssignment.truck_visit_id == truck_visit_id,
                ImportGatePassAssignment.is_active == True,
            )
            .values(is_active=False)
        )

        visit.status = "CANCELLED"
        visit.remarks = remarks or f"Queue cancelled by {emp_id}"
        visit.updated_at = datetime.now(timezone.utc)

        snapshot_after = {
            "status": "CANCELLED",
            "remarks": visit.remarks,
            "deactivated_gp_nos": deactivated_gp_nos,
            "deactivated_count": len(deactivated_gp_nos),
        }

        await log_activity_of_imp_truck_in_out(
            db,
            event_type="QUEUE_CANCELLED",
            entity_type="truck_visit",
            entity_id=visit.id,
            truck_visit_id=visit.id,
            truck_number=visit.truck_number,
            queue_no=visit.queue_no,
            token_no=visit.token_no,
            description=(
                f"Queue {visit.queue_no} cancelled for truck {visit.truck_number} (visit #{visit.id}). "
                f"Deactivated {len(deactivated_gp_nos)} GP assignment(s)."
            ),
            reason=remarks,
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
            performed_by=emp_id,
        )
        await db.commit()

        return {
            "success": True,
            "truck_visit_id": visit.id,
            "queue_no": visit.queue_no,
            "truck_number": visit.truck_number,
            "message": f"Queue {visit.queue_no} cancelled",
        }


class ImportTruckSearchService:

    @staticmethod
    def _to_ist(dt: datetime | None) -> str:
        IST = pytz.timezone("Asia/Kolkata")
        if dt is None:
            return ""
        if dt.tzinfo is None:
            dt = pytz.utc.localize(dt)
        return dt.astimezone(IST).strftime("%d-%b-%Y %H:%M:%S")

    @staticmethod
    async def search(
        db: AsyncSession,
        search_type: str,  # "gp_no" | "truck_no" | "queue_no"
        term: str,
        target_date: date = None,  # only used for truck_no
    ):
        """
        Single optimized query per search type.
        Returns flat list of results — one row per gate pass assignment.
        """

        IST = ZoneInfo("Asia/Kolkata")
        UTC = ZoneInfo("UTC")

        def ist_to_utc_range(d: date):
            # IST midnight = UTC 18:30 of PREVIOUS day
            start_ist = datetime.combine(d, time.min, tzinfo=IST)  # May 26 00:00:00 IST
            end_ist = datetime.combine(d, time.max, tzinfo=IST)  # May 26 23:59:59 IST
            return start_ist.astimezone(UTC), end_ist.astimezone(UTC)

        # ── 1. GP NO ──────────────────────────────────────────────
        # ImportGatePass → ImportGatePassAssignment (active) → ImportTruckVisit
        if search_type == "gp_no":
            stmt = (
                select(
                    ImportGatePass,
                    ImportGatePassAssignment,
                    ImportTruckVisit,
                    WorkerAssignmentShipment,
                    WorkerAssignmentHeader,
                )
                .select_from(ImportGatePass)
                .join(
                    ImportGatePassAssignment,
                    ImportGatePassAssignment.gate_pass_id == ImportGatePass.id,
                )
                .join(
                    ImportTruckVisit,
                    ImportTruckVisit.id == ImportGatePassAssignment.truck_visit_id,
                )
                .outerjoin(
                    WorkerAssignmentShipment,
                    WorkerAssignmentShipment.id
                    == ImportGatePass.worker_assignment_shipment_id,
                )
                .outerjoin(
                    WorkerAssignmentHeader,
                    WorkerAssignmentHeader.id
                    == WorkerAssignmentShipment.assignment_header_id,
                )
                .where(ImportGatePass.gate_pass_no == term.strip())
                .order_by(ImportGatePassAssignment.assigned_time.desc())
            )

            result = await db.execute(stmt)
            rows = result.all()

            if not rows:
                return {
                    "success": True,
                    "count": 0,
                    "results": [],
                    "queue_status_message": None,
                }

            return {
                "success": True,
                "count": len(rows),
                "queue_status_message": None,
                "results": [
                    _build_search_result(gp, assign, visit, shipment, header)
                    for gp, assign, visit, shipment, header in rows
                ],
            }

        # ── 2. TRUCK NO ───────────────────────────────────────────
        # ImportTruckVisit (date filter) → ImportGatePassAssignment → ImportGatePass
        elif search_type == "truck_no":
            if target_date is None:
                raise HTTPException(
                    status_code=400, detail="date is required for truck_no search"
                )

            day_start_utc, day_end_utc = ist_to_utc_range(target_date)

            print(f"Searching truck: '{term.strip().upper()}'")
            print(f"UTC range: {day_start_utc} → {day_end_utc}")

            stmt = (
                select(
                    ImportGatePass,
                    ImportGatePassAssignment,
                    ImportTruckVisit,
                    WorkerAssignmentShipment,
                    WorkerAssignmentHeader,
                )
                .select_from(ImportTruckVisit)
                .join(
                    ImportGatePassAssignment,
                    ImportGatePassAssignment.truck_visit_id == ImportTruckVisit.id,
                )
                .join(
                    ImportGatePass,
                    ImportGatePass.id == ImportGatePassAssignment.gate_pass_id,
                )
                .outerjoin(
                    WorkerAssignmentShipment,
                    WorkerAssignmentShipment.id
                    == ImportGatePass.worker_assignment_shipment_id,
                )
                .outerjoin(
                    WorkerAssignmentHeader,
                    WorkerAssignmentHeader.id
                    == WorkerAssignmentShipment.assignment_header_id,
                )
                .where(
                    ImportTruckVisit.truck_number == term.strip().upper(),
                    ImportTruckVisit.truck_slot_from >= day_start_utc,
                    ImportTruckVisit.truck_slot_from <= day_end_utc,
                )
                .order_by(ImportGatePassAssignment.assigned_time.desc())
            )

            result = await db.execute(stmt)
            rows = result.all()

            if not rows:
                return {
                    "success": True,
                    "count": 0,
                    "results": [],
                    "queue_status_message": None,
                }

            return {
                "success": True,
                "count": len(rows),
                "queue_status_message": None,
                "results": [
                    _build_search_result(gp, assign, visit, shipment, header)
                    for gp, assign, visit, shipment, header in rows
                ],
            }
        # ── 3. QUEUE NO ───────────────────────────────────────────
        # ImportTruckVisit (queue_no) → ImportGatePassAssignment → ImportGatePass
        # elif search_type == "queue_no":
        #     stmt = (
        #         select(
        #             ImportGatePass,
        #             ImportGatePassAssignment,
        #             ImportTruckVisit
        #         )
        #         .join(
        #             ImportGatePassAssignment,
        #             ImportGatePassAssignment.truck_visit_id == ImportTruckVisit.id
        #         )
        #         .join(
        #             ImportGatePass,
        #             ImportGatePass.id == ImportGatePassAssignment.gate_pass_id
        #         )
        #         .where(ImportTruckVisit.queue_no == term.strip().upper(), ImportTruckVisit.status == "QUEUED")
        #         .order_by(ImportGatePassAssignment.assigned_time.desc())
        #     )

        #     result = await db.execute(stmt)
        #     rows = result.all()

        #     if not rows:
        #         return {"success": True, "count": 0, "results": []}

        #     return {
        #         "success": True,
        #         "count": len(rows),
        #         "results": [
        #             _build_search_result(gp, assign, visit)
        #             for gp, assign, visit in rows
        #         ]
        #     }

        elif search_type == "queue_no":
            stmt = (
                select(
                    ImportGatePass,
                    ImportGatePassAssignment,
                    ImportTruckVisit,
                    WorkerAssignmentShipment,
                    WorkerAssignmentHeader,
                )
                .select_from(ImportTruckVisit)
                .join(
                    ImportGatePassAssignment,
                    ImportGatePassAssignment.truck_visit_id == ImportTruckVisit.id,
                )
                .join(
                    ImportGatePass,
                    ImportGatePass.id == ImportGatePassAssignment.gate_pass_id,
                )
                .outerjoin(
                    WorkerAssignmentShipment,
                    WorkerAssignmentShipment.id
                    == ImportGatePass.worker_assignment_shipment_id,
                )
                .outerjoin(
                    WorkerAssignmentHeader,
                    WorkerAssignmentHeader.id
                    == WorkerAssignmentShipment.assignment_header_id,
                )
                .where(ImportTruckVisit.queue_no == term.strip().upper())
                .order_by(ImportGatePassAssignment.assigned_time.desc())
            )

            result = await db.execute(stmt)
            rows = result.all()

            if not rows:
                return {
                    "success": True,
                    "count": 0,
                    "results": [],
                    "queue_status_message": None,
                }

            _, _, first_visit, _, _ = rows[0]  # ← unpack 5 now
            queue_status_message = None

            if first_visit.status == "BOOKED":
                queue_status_message = {
                    "type": "trucked_in",
                    "title": "This truck is already IN from queue",
                    "detail": f"Queue {first_visit.queue_no} was promoted to truck IN. Truck No: {first_visit.truck_number} (Truck In: {ImportTruckSearchService._to_ist(first_visit.truck_in_date_time)}). Search by truck number '{first_visit.truck_number}' in Truck No. tab or by gate pass in GP No. tab.",
                }
            elif first_visit.status == "CANCELLED":
                queue_status_message = {
                    "type": "cancelled",
                    "title": "This queue was cancelled",
                    "detail": f"Queue {first_visit.queue_no} for truck {first_visit.truck_number} was cancelled. Remarks: {first_visit.remarks or 'No remarks'}.",
                }

            return {
                "success": True,
                "count": len(rows),
                "queue_status_message": queue_status_message,
                "results": [
                    _build_search_result(gp, assign, visit, shipment, header)
                    for gp, assign, visit, shipment, header in rows
                ],
            }

        else:
            raise HTTPException(
                status_code=400, detail=f"Invalid search_type: {search_type}"
            )


class ImportAddMoreGpService:

    @staticmethod
    async def add_more_gp_to_truck(
        db: AsyncSession,
        truck_visit_id: int,
        gate_pass_nos: List[str],
        emp_id: str,
        remarks: str = None,
    ):
        """
        Add additional gate passes to an already-checked-in truck.
        All-or-nothing: validates ALL GPs first, then commits in single transaction.
        Reuses existing ImportGatePass rows or creates from WorkerAssignmentShipment.
        """
        # ── 1. Validate truck visit ────────────────────────────────────────────
        visit_stmt = select(ImportTruckVisit).where(
            ImportTruckVisit.id == truck_visit_id
        )
        visit = (await db.execute(visit_stmt)).scalar_one_or_none()

        if not visit:
            raise HTTPException(status_code=404, detail="Truck visit not found")

        if visit.status != "BOOKED":
            raise HTTPException(
                status_code=400,
                detail=f"Cannot add GPs to truck with status '{visit.status}'. Truck must be BOOKED.",
            )

        if not visit.is_truck_in:
            raise HTTPException(
                status_code=400,
                detail="Truck has not been checked in yet. Cannot add gate passes.",
            )

        if visit.is_truck_out:
            raise HTTPException(
                status_code=400,
                detail=f"Truck {visit.truck_number} has already been checked out. Cannot add gate passes.",
            )

        # ── 2. Deduplicate and clean input ─────────────────────────────────────
        gp_nos_clean = list({gp.strip() for gp in gate_pass_nos if gp and gp.strip()})
        if not gp_nos_clean:
            raise HTTPException(status_code=400, detail="No gate pass numbers provided")

        # # ── 3. Validate EACH gate pass (collect, don't commit yet) ─────────────
        # # We do all validation first, then all writes — atomic.
        # to_create: list[dict] = []   # entries to be added to DB
        # results: list[dict] = []

        # for gp_no in gp_nos_clean: =============>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>> NEW
        # ── 3. Validate EACH gate pass (collect, don't commit yet) ─────────────
        # We do all validation first, then all writes — atomic.
        to_create: list[dict] = []  # entries to be added to DB
        results: list[dict] = []

        # ── Time-window setup: max allowed wait between final delivery and truck in ──
        try:
            allow_hours = float(
                await AppConfigService.get_value(
                    db, "IMPORT", "free_hour_for_more_gp_add"
                )
            )
        except Exception:
            print(
                "⚠️⚠️⚠️⚠️ Error fetching config 'free_hour_for_more_gp_add', using fallback of 2.0 hours. ⚠️⚠️⚠️⚠️"
            )
            allow_hours = 2.0  # fallback if config missing/inactive

        anchor_in = visit.truck_in_date_time or visit.queued_at
        if anchor_in and anchor_in.tzinfo is None:
            anchor_in = anchor_in.replace(tzinfo=timezone.utc)

        def _check_window(final_delivery):
            """Return an error message if (truck_in − final_delivery) exceeds the limit, else None."""
            if not anchor_in or not final_delivery:
                return None  # can't compute → don't block
            fd = final_delivery
            if fd.tzinfo is None:
                fd = fd.replace(tzinfo=timezone.utc)
            waited_hours = (anchor_in - fd).total_seconds() / 3600.0
            if waited_hours > allow_hours:
                return (
                    f"Final delivery was {_fmt_duration(waited_hours)} before truck in "
                    f"— beyond the {_fmt_duration(allow_hours)} limit."
                )
            return None

        for gp_no in gp_nos_clean:
            try:
                # 3a. Check existing ImportGatePass
                gp_stmt = select(ImportGatePass).where(
                    ImportGatePass.gate_pass_no == gp_no
                )
                existing_gp = (await db.execute(gp_stmt)).scalar_one_or_none()

                if existing_gp:
                    # Fully consumed?
                    if existing_gp.pcs_remaining <= 0:
                        results.append(
                            {
                                "gate_pass_no": gp_no,
                                "success": False,
                                "message": "Fully consumed — 0 pcs remaining",
                            }
                        )
                        continue

                    # Active assignment anywhere?
                    active_stmt = select(ImportGatePassAssignment).where(
                        ImportGatePassAssignment.gate_pass_id == existing_gp.id,
                        ImportGatePassAssignment.is_active == True,
                    )
                    active = (await db.execute(active_stmt)).scalar_one_or_none()

                    if active:
                        if active.truck_visit_id == truck_visit_id:
                            results.append(
                                {
                                    "gate_pass_no": gp_no,
                                    "success": False,
                                    "message": "Already assigned to this truck",
                                }
                            )
                        else:
                            # Get other truck name for message
                            other_visit_stmt = select(ImportTruckVisit).where(
                                ImportTruckVisit.id == active.truck_visit_id
                            )
                            other_visit = (
                                await db.execute(other_visit_stmt)
                            ).scalar_one_or_none()
                            other_name = (
                                other_visit.truck_number if other_visit else "unknown"
                            )
                            results.append(
                                {
                                    "gate_pass_no": gp_no,
                                    "success": False,
                                    "message": f"Active assignment on truck {other_name}. Reassign or complete it first.",
                                }
                            )
                        continue

                    # # GP exists, has pcs_remaining, no active assignment → reusable
                    # to_create.append({
                    #     "gp_no": gp_no,
                    #     "existing_gp": existing_gp,
                    #     "shipment": None,
                    #     "header": None,
                    #     "pcs_to_assign": existing_gp.pcs_remaining,
                    # })
                    # continue

                    # GP exists, has pcs_remaining, no active assignment → reusable
                    # Window check needs final_delivery from the source shipment
                    existing_final_delivery = None
                    if existing_gp.worker_assignment_shipment_id:
                        existing_final_delivery = (
                            await db.execute(
                                select(
                                    WorkerAssignmentShipment.final_delivery_datetime
                                ).where(
                                    WorkerAssignmentShipment.id
                                    == existing_gp.worker_assignment_shipment_id
                                )
                            )
                        ).scalar_one_or_none()

                    # Final delivery must be completed or present
                    if not existing_final_delivery:
                        results.append(
                            {
                                "gate_pass_no": gp_no,
                                "success": False,
                                "message": "Final delivery not completed yet for this gate pass.",
                            }
                        )
                        continue

                    win_err = _check_window(existing_final_delivery)
                    if win_err:
                        results.append(
                            {
                                "gate_pass_no": gp_no,
                                "success": False,
                                "message": win_err,
                            }
                        )
                        continue

                    to_create.append(
                        {
                            "gp_no": gp_no,
                            "existing_gp": existing_gp,
                            "shipment": None,
                            "header": None,
                            "pcs_to_assign": existing_gp.pcs_remaining,
                        }
                    )
                    continue

                # 3b. GP doesn't exist in ImportGatePass — check WorkerAssignmentShipment
                was_stmt = (
                    select(WorkerAssignmentShipment, WorkerAssignmentHeader)
                    .join(
                        WorkerAssignmentHeader,
                        WorkerAssignmentShipment.assignment_header_id
                        == WorkerAssignmentHeader.id,
                    )
                    .where(WorkerAssignmentShipment.gate_pass_no == gp_no)
                )
                was_row = (await db.execute(was_stmt)).first()

                if not was_row:
                    results.append(
                        {
                            "gate_pass_no": gp_no,
                            "success": False,
                            "message": "Not found in system",
                        }
                    )
                    continue

                shipment, header = was_row

                # if not shipment.no_of_pc or shipment.no_of_pc <= 0:
                #     results.append({
                #         "gate_pass_no": gp_no,
                #         "success": False,
                #         "message": "Invalid pcs count in source data"
                #     })
                #     continue

                # to_create.append({
                #     "gp_no": gp_no,
                #     "existing_gp": None,
                #     "shipment": shipment,
                #     "header": header,
                #     "pcs_to_assign": shipment.no_of_pc,
                # })

                if not shipment.no_of_pc or shipment.no_of_pc <= 0:
                    results.append(
                        {
                            "gate_pass_no": gp_no,
                            "success": False,
                            "message": "Invalid pcs count in source data",
                        }
                    )
                    continue

                # Final delivery must be completed or present
                if not shipment.final_delivery_datetime:
                    results.append(
                        {
                            "gate_pass_no": gp_no,
                            "success": False,
                            "message": "Final delivery not completed yet for this gate pass.",
                        }
                    )
                    continue

                # Window check using this shipment's final delivery
                win_err = _check_window(shipment.final_delivery_datetime)
                if win_err:
                    results.append(
                        {
                            "gate_pass_no": gp_no,
                            "success": False,
                            "message": win_err,
                        }
                    )
                    continue

                to_create.append(
                    {
                        "gp_no": gp_no,
                        "existing_gp": None,
                        "shipment": shipment,
                        "header": header,
                        "pcs_to_assign": shipment.no_of_pc,
                    }
                )

            except Exception as e:
                logger.error(f"Validation failed for GP {gp_no}: {e}")
                results.append(
                    {
                        "gate_pass_no": gp_no,
                        "success": False,
                        "message": f"Validation error: {str(e)}",
                    }
                )

        # ── 4. If nothing valid → return early (no writes needed) ──────────────
        if not to_create:
            return {
                "success": False,
                "truck_visit_id": visit.id,
                "truck_number": visit.truck_number,
                "added_count": 0,
                "skipped_count": len(results),
                "results": results,
                "message": "No gate passes could be added. See per-GP details.",
            }

        # ── 5. Perform all writes inside single transaction ────────────────────
        truck_no_for_log = visit.truck_number  # ← capture BEFORE try (survives rollback
        try:
            utc_now = datetime.now(timezone.utc)

            for item in to_create:
                if item["existing_gp"]:
                    # Reuse existing GP row
                    gp = item["existing_gp"]
                else:
                    # Create new GP from shipment
                    shipment = item["shipment"]
                    header = item["header"]
                    gp = ImportGatePass(
                        gate_pass_no=shipment.gate_pass_no,
                        issued_date=shipment.gate_pass_issued_date_time_combo,
                        agent=shipment.agent_name,
                        consignee=shipment.customer_name,
                        gate_pass_release_by=shipment.verified_by or None,
                        gate_pass_released_time=shipment.gate_pass_issued_date_time_combo,
                        awb_no=header.awb_no,
                        hawb_no=header.hawb,
                        pcs_total=shipment.no_of_pc,
                        pcs_remaining=shipment.no_of_pc,
                        gross_wt_total=shipment.weight_in_kgs or 0,
                        status="A",
                        worker_assignment_shipment_id=shipment.id,
                        drop_dlv_zone=shipment.drop_dlv_zone,
                    )
                    db.add(gp)
                    await db.flush()  # get gp.id

                # Defensive — if any active assignment slipped through, deactivate
                await db.execute(
                    update(ImportGatePassAssignment)
                    .where(
                        ImportGatePassAssignment.gate_pass_id == gp.id,
                        ImportGatePassAssignment.is_active == True,
                    )
                    .values(is_active=False)
                )

                # Create new active assignment for this truck
                assignment = ImportGatePassAssignment(
                    gate_pass_id=gp.id,
                    truck_visit_id=visit.id,
                    assigned_by=emp_id,
                    assigned_time=utc_now,
                    is_active=True,
                    remarks=remarks
                    or f"Added to truck {visit.truck_number} after truck in",
                )
                db.add(assignment)
                await db.flush()

                await log_activity_of_imp_truck_in_out(
                    db,
                    event_type="MORE_GP_ADDED",
                    entity_type="gp_assignment",
                    entity_id=assignment.id,  # ← actual ID
                    truck_visit_id=visit.id,
                    truck_number=visit.truck_number,
                    gate_pass_no=item["gp_no"],
                    token_no=visit.token_no,
                    description=(
                        f"GP {item['gp_no']} added to truck {visit.truck_number} (visit #{visit.id}) "
                        f"after truck IN. {item['pcs_to_assign']} pcs assigned."
                    ),
                    reason=remarks,
                    snapshot_after={
                        "truck_visit_id": visit.id,
                        "gate_pass_id": gp.id,
                        "assignment_id": assignment.id,
                        "pcs_to_assign": item["pcs_to_assign"],
                        "is_active": True,
                    },
                    performed_by=emp_id,
                )

                results.append(
                    {
                        "gate_pass_no": item["gp_no"],
                        "success": True,
                        "message": f"Added — {item['pcs_to_assign']} pcs assigned",
                        "pcs_assigned": item["pcs_to_assign"],
                    }
                )

            visit.updated_at = utc_now
            if visit.charges_cleared:
                any_needed, missing = await ImportTruckOutService._visit_charge_status(db, visit)
                if any_needed and missing:
                    visit.charges_cleared = False
                    visit.charges_cleared_by = None
                    visit.charges_cleared_at = None
            await db.commit()

        except Exception as e:
            await db.rollback()
            logger.error(
                f"Failed to add GPs to truck {truck_no_for_log}: {e}"
            )  # ✅ plain string
            raise HTTPException(
                status_code=500, detail=f"Failed to add gate passes: {str(e)}"
            )

        # ── 6. Build response ───────────────────────────────────────────────────
        added_count = sum(1 for r in results if r["success"])
        skipped_count = sum(1 for r in results if not r["success"])

        return {
            "success": added_count > 0,
            "truck_visit_id": visit.id,
            "truck_number": visit.truck_number,
            "added_count": added_count,
            "skipped_count": skipped_count,
            "results": results,
            "message": (
                f"{added_count} added"
                + (f", {skipped_count} skipped" if skipped_count else "")
            ),
        }


class ImportCustomercareService:

    @staticmethod
    async def customer_care_clear_charges(db, truck_visit_id, emp_id):
        visit = (
            await db.execute(
                select(ImportTruckVisit).where(ImportTruckVisit.id == truck_visit_id)
            )
        ).scalar_one_or_none()
        if not visit:
            raise HTTPException(404, "Truck visit not found")
        if visit.is_truck_out:
            raise HTTPException(400, "Visit already checked out")

        any_needed, missing = await ImportTruckOutService._visit_charge_status(
            db, visit
        )

        if not any_needed:
            # No GP needs charges → nothing to clear (auto-cleared)
            return {
                "success": True,
                "charges_cleared": True,
                "message": "No charges applicable — already cleared for truck out.",
            }

        if missing:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot clear — charges not entered for: {', '.join(missing)}.",
            )

        visit.charges_cleared = True
        visit.charges_cleared_by = emp_id
        visit.charges_cleared_at = datetime.now(timezone.utc)
        await db.commit()
        return {
            "success": True,
            "charges_cleared": True,
            "message": "Charges cleared. Visit is ready for truck out.",
        }


def _build_search_result(
    gp: ImportGatePass,
    assign: ImportGatePassAssignment,
    visit: ImportTruckVisit,
    shipment: WorkerAssignmentShipment = None,  # ← ADD
    header: WorkerAssignmentHeader = None,  # ← ADD
) -> dict:
    print(
        f"GP: {gp.gate_pass_no} | shipment id: {shipment.id if shipment else None} | weight: {shipment.weight_in_kgs if shipment else 'NONE'}"
    )
    return {
        "gp_no": gp.gate_pass_no,
        "gp_status": gp.status,
        "pcs": shipment.no_of_pc if shipment else gp.pcs_total,
        "pcs_remaining": gp.pcs_remaining,
        "pcs_loaded": gp.pcs_total - gp.pcs_remaining,
        "weight_kgs": shipment.weight_in_kgs if shipment else None,
        "chg_weight_kgs": shipment.chg_wgt_in_kg if shipment else None,
        "agent": shipment.agent_name if shipment else gp.agent,
        "consignee": shipment.customer_name if shipment else gp.consignee,
        # AWB / HAWB — from header (most accurate source)
        "awb": header.awb_no if header else gp.awb_no,
        "hawb": header.hawb if header else gp.hawb_no,
        # Gate pass datetimes
        "gp_issued_datetime": (
            shipment.gate_pass_issued_date_time_combo if shipment else gp.issued_date
        ),
        "gp_end_datetime": shipment.gate_pass_end_datetime if shipment else None,
        "drop_dlv_zone": shipment.drop_dlv_zone if shipment else gp.drop_dlv_zone,
        "dlv_zone_from_irr": shipment.dlv_zone_from_irr if shipment else None,  # ← ADD
        "final_delivery_datetime": (
            shipment.final_delivery_datetime if shipment else None
        ),
        # truck visit
        "truck_visit_id": visit.id,
        "truck_no": visit.truck_number,
        "token": visit.token_no,
        "queue_no": visit.queue_no,
        "queued_at": visit.queued_at,
        "driver": visit.driver_name,
        "driver_contact": visit.driver_contact,
        "truck_status": visit.status,
        "truck_in": visit.truck_in_date_time,
        "truck_out": visit.truck_out_date_time,
        # assignment
        "assigned_time": assign.assigned_time,
        "assigned_by": assign.assigned_by,
        "is_active": assign.is_active,
    }
