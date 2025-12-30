

from datetime import datetime, time,date , timedelta
import io
import xlsxwriter
from typing import Any, Dict, Generator, Optional, AsyncGenerator
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from numpy import ceil
import pytz
from sqlalchemy import and_, case, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.user import User
from app.services.importOperation.audit_log_worker_assignment import log_worker_assignment_audit
from app.utils.common.helperFunction import get_utc_now
from sqlalchemy.orm import aliased


from app.db.models.importOperation.oc_merge_gatepass import OcMergeGatePass
from app.db.models.importOperation.import_release_report import IrrReport
from app.db.models.importOperation.worker_assignment import WorkerAssignment
from app.schemas.importOperation.worker_assignment import WorkerAssignmentRequest, WorkerAssignmentResponseForWorker, WorkerAssignmentResponseForWorkerLists




IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")



# ---------------------------------------------------------
# COMMON FILTER CLASS (Inside the same file)
# ---------------------------------------------------------

class WorkerAssignmentFilters:
    def __init__(self, model, status: str, startDate: str = None, endDate: str = None):
        self.model = model
        self.status = status
        self.startDate = startDate
        self.endDate = endDate

    @staticmethod
    def convert_ist_day_to_utc_range(date_str: str):
        if not date_str:
            return None, None

        ist = pytz.timezone("Asia/Kolkata")
        d = datetime.strptime(date_str, "%Y-%m-%d")

        start_ist = ist.localize(d.replace(hour=0, minute=0, second=0))
        end_ist = ist.localize(d.replace(hour=23, minute=59, second=59, microsecond=999999))

        return start_ist.astimezone(pytz.UTC), end_ist.astimezone(pytz.UTC)

    def apply_dlv_zone_filter(self, query):
        model = self.model
        status = self.status

        if status == "dlv_added":
            return query.where(
                model.drop_dlv_zone.isnot(None),
                func.trim(model.drop_dlv_zone) != ""
            )

        if status == "assigned_but_not_delivered":
            return query.where(
                or_(
                    model.drop_dlv_zone.is_(None),
                    func.trim(model.drop_dlv_zone) == ""
                )
            )

        return query

    def apply_status_filter(self, query):
        model = self.model
        status = self.status

        if status == "assigned":
            return query.where(model.assigned_person.isnot(None))

        if status == "unassigned":
            return query.where(model.assigned_person.is_(None))

        if status == "assigned_but_not_delivered":
            return query.where(
                and_(
                    model.assigned_person.isnot(None),
                    or_(
                        model.drop_dlv_zone.is_(None),
                        func.trim(model.drop_dlv_zone) == ""
                    )
                )
            )

        return query

    def apply_date_filter(self, query):
        model = self.model
        start = self.startDate
        end = self.endDate

        if not (start and end):
            return query

        utc_start, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start)
        _, utc_end = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end)

        return query.where(
            or_(
                model.integrate_date_time.between(utc_start, utc_end),
                model.gate_pass_issued_date_time_combo.between(utc_start, utc_end)
            )
        )


    def apply_all(self, query):
        query = self.apply_dlv_zone_filter(query)
        query = self.apply_status_filter(query)
        query = self.apply_date_filter(query)
        return query

# ==========================




def ist_day_to_utc_range(date_obj: date):
    """
    Returns a tuple (utc_start, utc_exclusive_end):

    utc_start  = IST midnight (00:00:00) of date_obj converted to UTC
    utc_end    = IST midnight (00:00:00) of next day converted to UTC

    Use this range as:
        timestamp >= utc_start AND timestamp < utc_end
    """
    if isinstance(date_obj, datetime):
        date_obj = date_obj.date()  # normalize to date only

    # Start of that day in IST (00:00:00)
    start_ist = datetime.combine(date_obj, time(0, 0, 0)).replace(tzinfo=IST)

    # Start of next day in IST (exclusive end)
    next_day_ist = start_ist + timedelta(days=1)

    # Convert both to UTC
    utc_start = start_ist.astimezone(UTC)
    utc_exclusive_end = next_day_ist.astimezone(UTC)

    return utc_start, utc_exclusive_end



def combine_gate_pass_date_with_time_and_return_utc_datetime(
    gate_pass_issued_date: Optional[datetime], 
    gate_pass_issued_time: Optional[str]
) -> Optional[datetime]:
    """
    Combines gate_pass_issued_date (UTC in DB) with gate_pass_issued_time (IST string in db)
    to produce a single UTC datetime.
    
    Args:
        gate_pass_issued_date: DateTime with timezone (UTC) from database
        gate_pass_issued_time: Time string in IST format like "12:42:00" or "09:30:15"
    
    Returns:
        Combined datetime in UTC timezone, or None if either input is None
    
    Example:
        Input:  gate_pass_issued_date = 2024-12-16 18:30:00+00:00 (UTC)
                gate_pass_issued_time = "12:42:00" (IST time string)
        
        Process:
        1. Convert UTC date to IST: 2024-12-17 00:00:00+05:30
        2. Extract IST date part: 2024-12-17
        3. Parse IST time: 12:42:00
        4. Combine: 2024-12-17 12:42:00+05:30 (IST)
        5. Convert back to UTC: 2024-12-17 07:12:00+00:00
        
        Output: 2024-12-17 07:12:00+00:00 (UTC)
    """
    
    # If either is missing, return None
    if not gate_pass_issued_date or not gate_pass_issued_time:
        return None
    
    try:
        ist_zone = ZoneInfo("Asia/Kolkata")
        utc_zone = ZoneInfo("UTC")
        
        # Step 1: Convert the UTC date to IST to get the correct IST date
        # (because the time string is in IST, we need the IST date)
        ist_date = gate_pass_issued_date.astimezone(ist_zone)
        
        # Step 2: Parse the time string (format: "HH:MM:SS" or "HH:MM")
        time_str = gate_pass_issued_time.strip()
        
        # Handle both "HH:MM:SS" and "HH:MM" formats
        if len(time_str.split(':')) == 2:
            time_obj = datetime.strptime(time_str, "%H:%M").time()
        else:
            time_obj = datetime.strptime(time_str, "%H:%M:%S").time()
        
        # Step 3: Combine the IST date with the IST time
        combined_ist = datetime.combine(
            ist_date.date(),  # Use IST date part
            time_obj          # Use IST time part
        ).replace(tzinfo=ist_zone)
        # print(combined_ist,"combined_ist")
        # Step 4: Convert the combined IST datetime back to UTC
        combined_utc = combined_ist.astimezone(utc_zone)
        
        return combined_utc
        
    except (ValueError, AttributeError) as e:
        print(f"Error combining datetime: {e}")
        return None




async def process_worker_assignment(db: AsyncSession, req):
    """
    ======================================================
    WORKER ASSIGNMENT PROCESS (SAFE + IDEMPOTENT)
    ======================================================

    Identity rule:
    - Shipment identity = (awb_no, hawb)
    - oc_no is mutable
    - temp_irm_oc_no is history only

    This function:
    - Syncs oc_merge_gatepass → worker_assignment
    - Syncs irr_report → worker_assignment
    - Never creates duplicate rows

     INSERT  → snapshot from oc_merge_gatepass
     UPDATE  → propagate only allowed changes
    """

    utc_start, utc_end = ist_day_to_utc_range(req.date)
    now = get_utc_now()

    # ─────────────────────────────────────────────
    # 1️⃣ Fetch source data (BATCHED)
    # ─────────────────────────────────────────────
    merge_rows = (await db.execute(
        select(OcMergeGatePass).where(
            and_(
                OcMergeGatePass.integrate_date_time >= utc_start,
                OcMergeGatePass.integrate_date_time < utc_end
            )
        )
    )).scalars().all()

    irr_rows = (await db.execute(
        select(IrrReport).where(
            IrrReport.gate_pass_issued_date.between(utc_start, utc_end)
        )
    )).scalars().all()

    # ─────────────────────────────────────────────
    # 2️⃣ Build IRR map by AWB+HAWB
    # ─────────────────────────────────────────────
    irr_map = {
        (i.awb, i.hwb or ""): i
        for i in irr_rows
    }

    inserted = 0
    updated = 0

    # ─────────────────────────────────────────────
    # 3️⃣ PROCESS OC MERGE DATA
    # ─────────────────────────────────────────────
    for oc in merge_rows:
        key_awb = oc.awb_no
        key_hawb = oc.hawb or ""

        stmt = (
            insert(WorkerAssignment)
            .values(
                # awb_no=key_awb,
                # hawb=oc.hawb,
                # oc_no=oc.oc_no,                         # real or temp
                # temp_irm_oc_no=oc.temp_irm_oc_no,
                # igp_no=oc.igp_no,
                # integrate_date_time=oc.integrate_date_time,
                # from_irr_table=False,
                # created_at=now,
                # updated_at=now
                # ------------------------------
                 # 🔑 Identity
                awb_no=oc.awb_no,
                hawb=oc.hawb,

                # 🔁 Mutable identifiers
                oc_no=oc.oc_no,
                temp_irm_oc_no=oc.temp_irm_oc_no,
                is_temp_irm_oc=oc.is_temp_irm_oc,
                igp_no=oc.igp_no,

                # 📦 Snapshot fields (READ-ONLY later)
                flight_no=oc.flight_no,
                igp_print_date_time=oc.igp_print_date_time,
                flight_date=oc.flight_date,
                no_of_pc=oc.no_of_pc,
                weight_in_kgs=oc.weight_in_kgs,
                chg_wgt_in_kg=oc.chg_wgt_in_kg,
                location=oc.location,
                shc=oc.shc,
                irr_codes=oc.irr_codes,
                customer_name=oc.customer_name,
                agent_name=oc.agent_name,
                irregularity_remarks=oc.irregularity_remarks,
                integrate_date_time=oc.integrate_date_time,

                from_irr_table=False,
                created_at=get_utc_now(),
                updated_at=get_utc_now()

            )
            .on_conflict_do_update(
                index_elements=[
                    WorkerAssignment.awb_no,
                    text("COALESCE(hawb, '')")
                ],
                set_={
                    # 🔥 CRITICAL: propagate OC change
                    "oc_no": insert(WorkerAssignment).excluded.oc_no,
                    "temp_irm_oc_no": case(
                        (
                            WorkerAssignment.temp_irm_oc_no.is_(None),
                            insert(WorkerAssignment).excluded.temp_irm_oc_no
                        ),
                        else_=WorkerAssignment.temp_irm_oc_no
                    ),

                        # ✅ UPDATE weight ONLY IF NULL
                    "weight_in_kgs": case(
                        (
                            WorkerAssignment.weight_in_kgs.is_(None),
                            insert(WorkerAssignment).excluded.weight_in_kgs
                        ),
                        else_=WorkerAssignment.weight_in_kgs
                    ),

                    # ✅ UPDATE chargeable weight ONLY IF NULL
                    "chg_wgt_in_kg": case(
                        (
                            WorkerAssignment.chg_wgt_in_kg.is_(None),
                            insert(WorkerAssignment).excluded.chg_wgt_in_kg
                        ),
                        else_=WorkerAssignment.chg_wgt_in_kg
                    ),
                    "igp_no": insert(WorkerAssignment).excluded.igp_no,
                    "updated_at": get_utc_now()
                }
            )
            .returning(
                text("CASE WHEN xmax = 0 THEN 1 ELSE 0 END")
            )
        )

        res = (await db.execute(stmt)).all()
        inserted += sum(1 for r in res if r[0] == 1)
        updated += sum(1 for r in res if r[0] == 0)

    # ─────────────────────────────────────────────
    # 4️⃣ PROCESS IRR DATA (REAL OC ALWAYS)
    # ─────────────────────────────────────────────
    for irr in irr_rows:
        key_awb = irr.awb
        key_hawb = irr.hwb or ""

        # 🆕 Combine gate_pass_issued_date (UTC) + gate_pass_issued_time (IST string)
        gate_pass_combo = combine_gate_pass_date_with_time_and_return_utc_datetime(
            irr.gate_pass_issued_date,
            irr.gate_pass_issued_time
        )
        stmt = (
            insert(WorkerAssignment)
            .values(
                # awb_no=key_awb,
                # hawb=irr.hwb,
                # oc_no=irr.oc_num,              # REAL OC
                # igp_no=None,
                # integrate_date_time=None,
                # from_irr_table=True,
                # created_at=now,
                # updated_at=now

                igp_no=None,
                igp_print_date_time=None,
                flight_no=irr.flight_no,
                awb_no=irr.awb,
                hawb=irr.hwb,
                flight_date=irr.flight_date,
                no_of_pc=irr.pcs,
                weight_in_kgs=irr.grg_wt,
                chg_wgt_in_kg=irr.chg_wt,
                location=irr.location_pcs,
                oc_no=irr.oc_num,
                irregularity_remarks=None,
                pd_in_time=None,
                no_of_pc_recd=irr.pcs,
                verified_by=None,
                agent_name=irr.agent,
                customer_name=irr.consignee,
                release_zone=irr.dlv_zone,
                is_printed=False,
                shc=irr.shc,
                irr_codes=None,
                integrate_date_time=None,

                # gate_pass_issued_date=irr.gate_pass_issued_date, # OLD and removed it now 
                gate_pass_issued_date_time_combo=gate_pass_combo,  # 🆕 Combined datetime new
                gate_pass_end_datetime=irr.gate_pass_end_date_time,
                gate_pass_no=irr.gate_pass_no,

                from_irr_table=True,
                created_at=get_utc_now(),
                updated_at=get_utc_now()
            )
            .on_conflict_do_update(
                index_elements=[
                    WorkerAssignment.awb_no,
                    text("COALESCE(hawb, '')")
                ],
             set_={
                    # 🔥 REAL OC overrides TEMP
                    "oc_no": insert(WorkerAssignment).excluded.oc_no,
                    
                    "gate_pass_end_datetime": case(
                        (
                            WorkerAssignment.gate_pass_end_datetime.is_(None),
                            insert(WorkerAssignment).excluded.gate_pass_end_datetime
                        ),
                        else_=WorkerAssignment.gate_pass_end_datetime
                    ),
                    "gate_pass_no": case(
                        (
                            or_(
                                WorkerAssignment.gate_pass_no.is_(None),
                                WorkerAssignment.gate_pass_no == ""
                            ),
                            insert(WorkerAssignment).excluded.gate_pass_no
                        ),
                        else_=WorkerAssignment.gate_pass_no
                    ),
                    "gate_pass_issued_date_time_combo": case(
                        (
                            WorkerAssignment.gate_pass_issued_date_time_combo.is_(None),
                            insert(WorkerAssignment).excluded.gate_pass_issued_date_time_combo
                        ),
                        else_=WorkerAssignment.gate_pass_issued_date_time_combo
                    ),
                    
                    "updated_at": now
                }
            )
            .returning(
                text("CASE WHEN xmax = 0 THEN 1 ELSE 0 END")
            )
        )

        res = (await db.execute(stmt)).all()
        inserted += sum(1 for r in res if r[0] == 1)
        updated += sum(1 for r in res if r[0] == 0)

    await db.commit()

    return {
        "success": True,
        "merge_rows_processed": len(merge_rows),
        "irr_rows_processed": len(irr_rows),
        "inserted_rows": inserted,
        "updated_rows": updated
    }












async def get_all_worker_assignments_list(db: AsyncSession):
    query = select(WorkerAssignment).order_by(WorkerAssignment.id.desc())
    result = await db.execute(query)
    rows = result.scalars().all()
    return rows







async def get_all_allowed_users_as_worker(db: AsyncSession) -> list[User]:
    allowed_roles_for_become_worker = ['imp_gp_user']  # Define the allowed role
    
    query = select(User).filter(User.role.in_(allowed_roles_for_become_worker), User.is_active == True)
    
    result = await db.execute(query)
    users = result.scalars().all()

    if not users:
        raise HTTPException(status_code=404, detail="No users found for assignment")
    
    return users


async def get_worker_assignment_lists_by_emp_id(db: AsyncSession, emp_id: str) -> list[WorkerAssignment]:
    # Query the User table to check the role of the user
    user_query = select(User).filter(User.emp_id == emp_id)
    result = await db.execute(user_query)
    user = result.scalars().first()

    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    # Check if the user has the 'imp_gp_user' role
    if user.role != 'imp_gp_user':
        raise HTTPException(status_code=403, detail="User is not authorized for this action")

    # If the user is authorized, fetch the worker assignments assigned to the user
     # Fetch only unfilled drop_dlv_zone assignments
    assignment_query = (
        select(WorkerAssignment)
        .filter(WorkerAssignment.assigned_person == emp_id)
        .filter(
            or_(
                WorkerAssignment.drop_dlv_zone.is_(None),   # NULL
                WorkerAssignment.drop_dlv_zone == ""        # empty string (optional)
            )
        )
    )

    result = await db.execute(assignment_query)
    worker_assignments = result.scalars().all()

    return worker_assignments



# ==========Assign a user to the worker assignment table row data =============================

async def assign_user_to_worker_assignment(db: AsyncSession,
            oc_no: str, 
            emp_id: str,  # worker being assigned
            current_user_role:str,
            changed_by  : str,      # actor which perform this operation
            *,
            ip_address: str | None,
            user_agent:str |None,
            device_id:str |None,
            
            ) -> bool:
    # Step 1: Check if the worker assignment with the given `oc_no` exists
    result = await db.execute(select(WorkerAssignment).filter(WorkerAssignment.oc_no == oc_no))
    worker_assignment = result.scalars().first()

    if not worker_assignment:
        raise HTTPException(status_code=404, detail=f"Worker assignment with OC No {oc_no} not found.")
    
    # Step 2: Check if the employee exists and has the proper role (imp_gp_user)
    user_result = await db.execute(select(User).filter(User.emp_id == emp_id, User.role == "imp_gp_user"))
    user = user_result.scalars().first()

    if not user:
        raise HTTPException(status_code=400, detail=f"User with emp_id {emp_id} not found or invalid role.")
    
        # NEW: Check if user is active
    if hasattr(user, "is_active") and not user.is_active:
        raise HTTPException(
            status_code=400,
            detail=f"User with emp_id {emp_id} is Inactive."
        )
    
    # 🔒 Capture old value BEFORE change
    old_assigned_person = worker_assignment.assigned_person

    # Step 3: Update the worker assignment with the employee's ID
    worker_assignment.assigned_person = emp_id
    worker_assignment.assigned_person_datetime = get_utc_now()  # Set the timestamp of assignment
    worker_assignment.updated_at=get_utc_now()

       # 🧾 AUDIT LOG
    await log_worker_assignment_audit(
        db=db,
        assignment=worker_assignment,
        field_name="assigned_person",
        old_value=old_assigned_person,
        new_value=emp_id,
        changed_by=changed_by,
        changed_by_role=current_user_role,
        device_id=device_id,
        user_agent = user_agent,
        ip_address=ip_address,
        db_action="UPDATE",
        source_action="assign_user",
    )

    # Step 4: Commit the transaction
    db.add(worker_assignment)
    await db.commit()
    
    return True




# add drop_dlv_zone by assigned user or worker ===============================
async def add_drop_dlv_zone_by_assigned_worker(
    db: AsyncSession, 
    oc_no: str, 
    emp_id: str, 
    current_user_role:str,
    drop_dlv_zone: str,
    ip_address: str = None,
    device_id:str = None,
    user_agent:str = None
) -> dict:
    try:
        # Step 1: Fetch worker assignment by oc_no
        stmt = select(WorkerAssignment).filter(WorkerAssignment.oc_no == oc_no)
        result = await db.execute(stmt)
        worker_assignment = result.scalars().first()

        # If worker assignment does not exist
        if not worker_assignment:
            # return {"status": "error", "message": "Record not found for the given OC No."}
            raise HTTPException(status_code=404, detail=f"Record not found for the given OC No: {oc_no}")
        
        if not worker_assignment.assigned_person:
            raise HTTPException(
                status_code=400,
                detail="No worker has been assigned to this OC yet."
            )

        # Step 2: Cross-check if the emp_id matches the assigned person
        if worker_assignment.assigned_person != emp_id:
            return {"status": "error", "message": "This OC No. is assigned to someone else."}

        # Step 3: Check if drop_dlv_zone is already set
        if worker_assignment.drop_dlv_zone:
            return {"status": "error", "message": "Delivery zone has already been filled.."}
        # Store old value for audit log (before update)
        old_drop_dlv_zone = worker_assignment.drop_dlv_zone

        # Step 4: Update drop_dlv_zone and set drop_dlv_zone_datetime
        print("role--------------------",current_user_role)
        stmt = (
            update(WorkerAssignment)
            .where(WorkerAssignment.oc_no == oc_no)
            .values(
                drop_dlv_zone=drop_dlv_zone,
                drop_dlv_zone_datetime=get_utc_now(),  
                updated_at=get_utc_now()
            )
        )
        await db.execute(stmt)
        # 🧾 5️⃣ AUDIT LOG (after update, before commit)
        await log_worker_assignment_audit(
            db=db,
            assignment=worker_assignment,  # Fixed: use worker_assignment
            field_name="drop_dlv_zone",
            old_value=old_drop_dlv_zone,
            new_value=drop_dlv_zone,
            changed_by=emp_id,
            changed_by_role=current_user_role,
            user_agent = user_agent,
            ip_address=ip_address,
            device_id = device_id,
            db_action="UPDATE",
            source_action="dlv_zone_update",
        )

        await db.commit()

        return {"status": "success", "message": f"Drop delivery zone successfully updated by {emp_id}."}
    except HTTPException:
        # ❌ Rollback on known errors (404, 403, 400)
        await db.rollback()
        raise  # Re-raise HTTPException to be handled by FastAPI
    
    except Exception as e:
        # ❌ Rollback on any unexpected errors
        await db.rollback()
        # logger.error(f"Unexpected error in add_drop_dlv_zone_by_assigned_worker: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="An unexpected error occurred. Please try again later."
        )





# PAGINATED WORKER ASSIGNMENT DATA WITH FILTERS AND MATRIX COUNTS (NEW)

async def get_paginated_worker_assignments_data_list(
    db: AsyncSession,
    model,
    status: str = "all",
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    page: int = 1,
    page_size: int = 10
) -> Dict[str, Any]:
    """
    One single static method that contains ALL logic using inner functions.
    """

    # -----------------------------------------------------
    # INTERNAL HELPERS
    # -----------------------------------------------------

    def convert_ist_day_to_utc_range(date_str: str):
        ist = pytz.timezone("Asia/Kolkata")
        d = datetime.strptime(date_str, "%Y-%m-%d")

        start_ist = ist.localize(d.replace(hour=0, minute=0, second=0))
        end_ist = ist.localize(d.replace(hour=23, minute=59, second=59, microsecond=999999))

        return start_ist.astimezone(pytz.UTC), end_ist.astimezone(pytz.UTC)

    # def apply_dlv_zone_filter(query):
    #     if status == "dlv_added":
    #         return query.where(
    #             model.drop_dlv_zone.isnot(None),
    #             func.trim(model.drop_dlv_zone) != ""
    #         )
    #     return query.where(
    #         or_(
    #             model.drop_dlv_zone.is_(None),
    #             func.trim(model.drop_dlv_zone) == ""
    #         )
    #     )

    def apply_dlv_zone_filter(query):
        # 1️⃣ Show ONLY delivered rows
        if status == "dlv_added":
            return query.where(
                model.drop_dlv_zone.isnot(None),
                func.trim(model.drop_dlv_zone) != ""
            )

        # 2️⃣ Show assigned but NOT delivered
        if status == "assigned_but_not_delivered":
            return query.where(
                or_(
                    model.drop_dlv_zone.is_(None),
                    func.trim(model.drop_dlv_zone) == ""
                )
            )

        # 3️⃣ For all, assigned, unassigned → DO NOT FILTER BY DELIVERY
        return query


    def apply_status_filter(query):
        if status == "assigned":
            return query.where(model.assigned_person.isnot(None))
        if status == "unassigned":
            return query.where(model.assigned_person.is_(None))
        if status == "assigned_but_not_delivered":
            return query.where(
                and_(
                    model.assigned_person.isnot(None),
                    or_(
                        model.drop_dlv_zone.is_(None),
                        func.trim(model.drop_dlv_zone) == ""
                    )
                )
            )

        return query

    def apply_date_filter(query):
        if not (startDate and endDate):
            return query

        utc_start, _ = convert_ist_day_to_utc_range(startDate)
        _, utc_end = convert_ist_day_to_utc_range(endDate)

        return query.where(
            or_(
                model.integrate_date_time.between(utc_start, utc_end),
                model.gate_pass_issued_date_time_combo.between(utc_start, utc_end)
            )
        )

    async def calculate_matrix(base_query):
        # 1. PURE OC COUNT
        pure = base_query.where(
            and_(
                model.from_irr_table == False,
                or_(
                    model.temp_irm_oc_no.is_(None),
                    func.trim(model.temp_irm_oc_no) == ""
                )
            )
        )
        pure_count = (await db.execute(
            select(func.count()).select_from(pure.subquery())
        )).scalar() or 0

        # 2. TEMP IRM COUNT
        temp_irm = base_query.where(
            and_(
                model.from_irr_table == False,
                model.temp_irm_oc_no.isnot(None),
                func.trim(model.temp_irm_oc_no) != ""
            )
        )
        temp_irm_count = (await db.execute(
            select(func.count()).select_from(temp_irm.subquery())
        )).scalar() or 0

        # 3. GP COUNT
        gp = base_query.where(
            and_(
                model.gate_pass_no.isnot(None),
                func.trim(model.gate_pass_no) != ""
            )
        )
        gp_count = (await db.execute(
            select(func.count()).select_from(gp.subquery())
        )).scalar() or 0

        return {
            "pure_oc_merge_count": pure_count,
            "temp_irm_count": temp_irm_count,
            "gp_alloted_count": gp_count
        }

    # -----------------------------------------------------
    # STEP 1 – BUILD BASE QUERY
    # -----------------------------------------------------
    base_query = select(model)
    base_query = apply_dlv_zone_filter(base_query)
    base_query = apply_status_filter(base_query)
    base_query = apply_date_filter(base_query)

    # -----------------------------------------------------
    # STEP 2 – TOTAL RECORDS
    # -----------------------------------------------------
    total_records = (await db.execute(
        select(func.count()).select_from(base_query.subquery())
    )).scalar() or 0

    total_pages = ceil(total_records / page_size) if page_size > 0 else 0

    if page < 1:
        page = 1
    if total_pages > 0 and page > total_pages:
        page = total_pages

    offset = (page - 1) * page_size

    # -----------------------------------------------------
    # STEP 3 – PAGINATED DATA
    # -----------------------------------------------------
    paginated_query = (
        base_query
        # .order_by(model.id.desc())
         .order_by(
        model.gate_pass_no.is_(None),   # NULL GP go last
        model.gate_pass_no.asc(),       # GP numbers ascending
        model.oc_no.asc()               # OC ascending
    )
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(paginated_query)
    records = result.scalars().all()

    # -----------------------------------------------------
    # STEP 4 – MATRIX COUNTS
    # -----------------------------------------------------
    matrix_counts = await calculate_matrix(base_query)

    # -----------------------------------------------------
    # STEP 5 – RETURN RESPONSE
    # -----------------------------------------------------
    return {
        # "data": records,
        "success": True,
    "message": "Worker assignments fetched successfully",
        "data": [WorkerAssignmentResponseForWorker.model_validate(r) for r in records],

        "pagination": {
            "current_page": page,
            "page_size": page_size,
            "total_records": total_records,
            "total_pages": total_pages,
            "has_previous": page > 1,
            "has_next": page < total_pages,
            "previous_page": page - 1 if page > 1 else None,
            "next_page": page + 1 if page < total_pages else None
        },
        "matrix_counts": matrix_counts,
        "filters_applied": {
            "status": status,
            "start_date": startDate,
            "end_date": endDate
        }
    }

#-----this is used for sear ch in worker assignment page where I can search by awb hawb gp_no, oc_no, temp_oc -------
async def search_in_worker_assignments(
    db: AsyncSession,
    search_type: str,
    search_value: str
) ->WorkerAssignmentResponseForWorkerLists:

    field_map = {
        "oc_no": WorkerAssignment.oc_no,
        "gp_no": WorkerAssignment.gate_pass_no,
        "temp_oc": WorkerAssignment.temp_irm_oc_no,
        "awb": WorkerAssignment.awb_no,
        "hawb": WorkerAssignment.hawb,
    }

    print(search_type,search_value,"search_type,search_value")


    if search_type not in field_map:
        return []  # invalid search type

    column = field_map[search_type]

    if search_type == "gp_no":
        stmt = select(WorkerAssignment).where(
            func.lower(WorkerAssignment.gate_pass_no)
            .contains(search_value.lower())
        )
    else:
        stmt = select(WorkerAssignment).where(column == search_value)

    # stmt = select(WorkerAssignment).where(column == search_value)



    result = await db.execute(stmt)
    return result.scalars().all()





#============= IT IS USED TO EXPORT EXCEL STREAMING FOR WORKER ASSIGNMENT DATA WITH FILTERS ================
async def generate_excel_stream_export_worker_assignment(
    db: AsyncSession,
    assignment_status: str,
    start_date: str,
    end_date: str,
    chunk_size: int = 1000
) -> AsyncGenerator[bytes, None]:
    """
    Async generator that streams Excel file in chunks
    Processes records in batches to avoid memory issues
    """

    # Create in-memory buffer
    output = io.BytesIO()
    
    # Create workbook and worksheet
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('Worker Assignments')
    
    # Define formats
    header_format = workbook.add_format({
        'bold': True,
        # 'bg_color': '#4472C4',
        # 'font_color': 'white',
        'border': 1,
        'align': 'center',
        'valign': 'vcenter',
        'text_wrap': False
    })
    
    date_format = workbook.add_format({
        'num_format': 'dd/mm/yyyy hh:mm',
        'align': 'left'
    })
    
    number_format = workbook.add_format({
        'num_format': '0.00',
        'align': 'right'
    })

    integer_format = workbook.add_format({
    'num_format': '0',
    'align': 'right'
})

    
    text_format = workbook.add_format({
        'align': 'left',
        'valign': 'top',
        'text_wrap': True
    })
    
    text_center = workbook.add_format({
        'align': 'center',
        'valign': 'vcenter'
    })
    
    # Define headers
    
    headers = [
        'S.No', 'IGP No', 'OC No', 'Temp IRM OC',
        'AWB No', 'HAWB', 'Flight No', 'Flight Date',
        'No of Pieces', 'Weight (KG)', 'Chargeable Weight (KG)',
        'Location', 'Agent Name', 'Customer Name', 
        # 'Release Zone',
        'SHC', 'IRR Codes', 'Irregularity Remarks',
        'Gate Pass No', 'GP Issue Date', 'GP End Date',
        'Assigned Person', 'Assigned Person Name','Assigned DateTime',
        'Drop Delivery Zone', 'Drop DLV DateTime',
        'From Source', 'Integrate Date', 'Created At'
    ]
    
    # Write headers
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header, header_format)
    
    # # Set column widths
    # column_widths = {
    #     0: 8,   # S.No
    #     1: 15,  # IGP No
    #     2: 15,  # OC No
    #     3: 15,  # Temp IRM OC
    #     4: 12,  # Is Temp OC
    #     5: 18,  # AWB No
    #     6: 18,  # HAWB
    #     7: 12,  # Flight No
    #     8: 18,  # Flight Date
    #     9: 12,  # No of Pieces
    #     10: 12, # Weight
    #     11: 18, # Chargeable Weight
    #     12: 25, # Location
    #     13: 30, # Agent Name
    #     14: 30, # Customer Name
    #     # 15: 15, # Release Zone
    #     15: 15,  # SHC
    #     16: 20,  # IRR Codes
    #     17: 35,  # Irregularity Remarks
    #     18: 18,  # Gate Pass No
    #     19: 18,  # GP Issue Date
    #     20: 18,  # GP End Date
    #     21: 20,  # Assigned Person
    #     22: 18,  # Assigned DateTime
    #     23: 20,  # Drop Delivery Zone
    #     24: 18,  # Drop DLV DateTime
    #     25: 15,  # From IRR Table
    #     26: 18,  # Integrate Date
    #     27: 18   # Created At

    # }

    column_widths = {
    0: 8,   # S.No
    1: 15,  # IGP No
    2: 15,  # OC No
    3: 15,  # Temp IRM OC

    # ❌ Removed: Is Temp OC (was index 4)

    4: 18,  # AWB No
    5: 18,  # HAWB
    6: 12,  # Flight No
    7: 18,  # Flight Date
    8: 12,  # No of Pieces
    9: 12,  # Weight
    10: 18, # Chargeable Weight
    11: 25, # Location
    12: 30, # Agent Name
    13: 30, # Customer Name

    14: 15,  # SHC
    15: 20,  # IRR Codes
    16: 35,  # Irregularity Remarks
    17: 18,  # Gate Pass No
    18: 18,  # GP Issue Date
    19: 18,  # GP End Date
    20: 20,  # Assigned Person
    21: 25,  # Assigned Person Name
    22: 18,  # Assigned DateTime
    23: 20,  # Drop Delivery Zone
    24: 18,  # Drop DLV DateTime
    25: 15,  # From IRR Table
    26: 18,  # Integrate Date
    27: 18   # Created At
}

    
    for col, width in column_widths.items():
        worksheet.set_column(col, col, width)
    
    # Freeze header row
    worksheet.freeze_panes(1, 0)
    
    # Parse dates
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    # Build base query---------------
    
    # USE COMMON FILTER LOGIC
    # ----------------------------------------
    filters = WorkerAssignmentFilters(
        model=WorkerAssignment,
        status=assignment_status,
        startDate=start_date,
        endDate=end_date
    )

    # base_query = filters.apply_all(select(WorkerAssignment))
    UserAlias = aliased(User)

    base_query = (
        filters.apply_all(
            select(
                WorkerAssignment,
                UserAlias.name.label("assigned_person_name")
            )
            .outerjoin(
                UserAlias,
                UserAlias.emp_id == WorkerAssignment.assigned_person
            )
        )
    )

    # SAME ORDERING AS TABLE VIEW
    base_query = base_query.order_by(
        WorkerAssignment.gate_pass_no.is_(None),
        WorkerAssignment.gate_pass_no.asc(),
        WorkerAssignment.oc_no.asc()
    )

    
    def to_ist_no_tz(dt):
        """
        Convert UTC datetime → IST datetime (naive)
        Excel requires timezone removed.
        """
        IST = pytz.timezone("Asia/Kolkata")
        if not dt:
            return None

        # If timezone-aware: convert to IST
        if dt.tzinfo:
            dt = dt.astimezone(IST)
        # Make timezone-naive for Excel
        return dt.replace(tzinfo=None)
    
    # helper function to get source value that from where it data originated in assignment table (it get from source header value)
    def get_source_label(assignment):
        if assignment.from_irr_table and not assignment.temp_irm_oc_no:
            return "IRR"
        if assignment.temp_irm_oc_no and not assignment.from_irr_table:
            return "IRM"
        if not assignment.temp_irm_oc_no and not assignment.from_irr_table:
            return "OC MERGE"
        return ""


    # Process in chunks
    row_num = 1
    offset = 0
    
    while True:
        # Fetch chunk asynchronously
        chunk_query = base_query.offset(offset).limit(chunk_size)
        result = await db.execute(chunk_query)
        # chunk = result.scalars().all()
        chunk = result.all()

        
        if not chunk:
            break
        
        # Write chunk to Excel
        # for assignment in chunk:
        for assignment, assigned_person_name in chunk:

            # S.No
            worksheet.write(row_num, 0, row_num, text_center)
            
            # IGP No
            worksheet.write(row_num, 1, assignment.igp_no or '', text_format)
            
            # OC No
            worksheet.write(row_num, 2, assignment.oc_no or '', text_format)
            
            # Temp IRM OC
            worksheet.write(row_num, 3, assignment.temp_irm_oc_no or '', text_format)
            
            # # Is Temp OC
            # worksheet.write(row_num, 4, 'Yes' if assignment.is_temp_irm_oc else 'No', text_center)
            
            # AWB No
            worksheet.write(row_num, 4, assignment.awb_no or '', text_format)
            
            # HAWB
            worksheet.write(row_num, 5, assignment.hawb or '', text_format)
            
            # Flight No
            worksheet.write(row_num, 6, assignment.flight_no or '', text_format)
            
            # Flight Date
            if assignment.flight_date:
                worksheet.write_datetime(row_num, 7, to_ist_no_tz(assignment.flight_date), date_format)
            else:
                worksheet.write(row_num, 7, '', text_format)
            
            # No of Pieces
            # worksheet.write(row_num, 9, assignment.no_of_pc or '', integer_format)

            # No of Pieces
            if assignment.no_of_pc is not None:
                worksheet.write_number(row_num, 8, assignment.no_of_pc, integer_format)
            else:
                worksheet.write_blank(row_num, 8, None)

            
            # Weight (KG)
            # worksheet.write(row_num, 10, assignment.weight_in_kgs or 0.0, number_format)
            
            # Chargeable Weight (KG)
            # worksheet.write(row_num, 11, assignment.chg_wgt_in_kg or 0.0, number_format)

            # Weight (KG)
            if assignment.weight_in_kgs is not None:
                worksheet.write_number(row_num, 9, assignment.weight_in_kgs, number_format)
            else:
                worksheet.write_blank(row_num, 9, None)

            # Chargeable Weight (KG)
            if assignment.chg_wgt_in_kg is not None:
                worksheet.write_number(row_num, 10, assignment.chg_wgt_in_kg, number_format)
            else:
                worksheet.write_blank(row_num, 10, None)

            
            # Location
            worksheet.write(row_num, 11, assignment.location or '', text_format)
            
            # Agent Name
            worksheet.write(row_num, 12, assignment.agent_name or '', text_format)
            
            # Customer Name
            worksheet.write(row_num, 13, assignment.customer_name or '', text_format)
            
            # Release Zone
            # worksheet.write(row_num, 15, assignment.release_zone or '', text_format)
            
            # SHC
            worksheet.write(row_num, 14, assignment.shc or '', text_format)
            
            # IRR Codes
            worksheet.write(row_num, 15, assignment.irr_codes or '', text_format)
            
            # Irregularity Remarks
            worksheet.write(row_num, 16, assignment.irregularity_remarks or '', text_format)
            
            # Gate Pass No
            worksheet.write(row_num, 17, assignment.gate_pass_no or '', text_format)
            
            # GP Issue Date
            if assignment.gate_pass_issued_date_time_combo:
                worksheet.write_datetime(row_num, 18, to_ist_no_tz(assignment.gate_pass_issued_date_time_combo), date_format)
            else:
                worksheet.write(row_num, 18, '', text_format)
            
            # GP End Date
            if assignment.gate_pass_end_datetime:
                worksheet.write_datetime(row_num, 19, to_ist_no_tz(assignment.gate_pass_end_datetime), date_format)
            else:
                worksheet.write(row_num, 19, '', text_format)
            
            # Assigned Person
            worksheet.write(row_num, 20, assignment.assigned_person or '', text_format)

            # Assigned Person Name (from users table)
            worksheet.write(
                row_num,
                21,
                assigned_person_name or '',
                text_format
            )
                        
            # Assigned DateTime
            if assignment.assigned_person_datetime:
                worksheet.write_datetime(row_num, 22, to_ist_no_tz(assignment.assigned_person_datetime), date_format)
            else:
                worksheet.write(row_num, 22, '', text_format)
            
            # Drop Delivery Zone
            worksheet.write(row_num, 23, assignment.drop_dlv_zone or '', text_format)
            
            # Drop DLV DateTime
            if assignment.drop_dlv_zone_datetime:
                worksheet.write_datetime(row_num, 24, to_ist_no_tz(assignment.drop_dlv_zone_datetime), date_format)
            else:
                worksheet.write(row_num, 24, '', text_format)
            
            # From IRR Table
            # worksheet.write(row_num, 26, 'Yes' if assignment.from_irr_table else 'No', text_center)
            worksheet.write(
                row_num,
                25,  # Source column index
                get_source_label(assignment),
                text_center
            )

            
            # Integrate Date
            if assignment.integrate_date_time:
                worksheet.write_datetime(row_num, 26, to_ist_no_tz(assignment.integrate_date_time), date_format)
            else:
                worksheet.write(row_num, 26, '', text_format)
            
            # Created At
            if assignment.created_at:
                worksheet.write_datetime(row_num, 27, to_ist_no_tz(assignment.created_at), date_format)
            else:
                worksheet.write(row_num, 27, '', text_format)
            
            row_num += 1
        
        offset += chunk_size
    
    # Close workbook to finalize
    workbook.close()
    
    # Seek to beginning
    output.seek(0)
    
    # Yield the complete file
    yield output.read()



# =========== Get summary data of allocations and IRM related ==========================
async def get_assignment_summary(db, start_utc, end_utc):
    """
    Dashboard summary for:
    - OC_MERGE
    - IRM
    - IRR
    Always returns all 3 categories (missing ones filled with zero values).
    """

    ALL_CATEGORIES = ["OC_MERGE", "IRM", "IRR"]

    # Category mapping (NO SPACES)
    category_case = case(
        (WorkerAssignment.from_irr_table.is_(True), "IRR"),
        (
            and_(
                WorkerAssignment.temp_irm_oc_no.isnot(None),
                WorkerAssignment.temp_irm_oc_no != ""
            ),
            "IRM"
        ),
        else_="OC_MERGE"
    ).label("category")

    # Fallback date logic
    date_field = func.coalesce(
        WorkerAssignment.integrate_date_time,
        WorkerAssignment.gate_pass_issued_date_time_combo
    )

    # Main query
    stmt = (
        select(
            category_case,
            func.count(WorkerAssignment.id).label("count"),

            func.count(
                case((WorkerAssignment.gate_pass_no.isnot(None), 1))
            ).label("converted_to_gp"),

            func.count(
                case((WorkerAssignment.drop_dlv_zone.isnot(None), 1))
            ).label("delivered"),

            func.count(
                case(
                    (
                        and_(
                            WorkerAssignment.assigned_person.isnot(None),
                            WorkerAssignment.assigned_person_datetime.isnot(None)
                        ),
                        1
                    )
                )
            ).label("assigned"),
        )
        .where(
            date_field >= start_utc,
            date_field < end_utc
        )
        .group_by(category_case)
    )

    result = await db.execute(stmt)
    rows = result.all()

    # Convert rows → map by category
    data_map = {row.category: row for row in rows}

    # Ensure ALL categories exist in output
    summary = []
    for cat in ALL_CATEGORIES:
        if cat in data_map:
            row = data_map[cat]
            summary.append({
                "category": cat,
                "count": row.count,
                "converted_to_gp": row.converted_to_gp,
                "delivered": row.delivered,
                "assigned": row.assigned,
                "balance_for_delivered": row.count - row.delivered,
            })
        else:
            # Default zero values
            summary.append({
                "category": cat,
                "count": 0,
                "converted_to_gp": 0,
                "delivered": 0,
                "assigned": 0,
                "balance_for_delivered": 0,
            })

    return summary
