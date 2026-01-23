

# from datetime import datetime, time,date , timedelta
# import io
# import xlsxwriter
# from typing import Any, Dict, Generator, Optional, AsyncGenerator
# from zoneinfo import ZoneInfo
# from fastapi import HTTPException
# from numpy import ceil
# import pytz
# from sqlalchemy import and_, case, func, or_, select, text, update
# from sqlalchemy.dialects.postgresql import insert
# from sqlalchemy.ext.asyncio import AsyncSession
# from app.db.models.user import User
# from app.services.importOperation.audit_log_worker_assignment import log_worker_assignment_audit
# from app.utils.common.helperFunction import get_utc_now
# from sqlalchemy.orm import aliased


# from app.db.models.importOperation.oc_merge_gatepass import OcMergeGatePass
# from app.db.models.importOperation.import_release_report import IrrReport
# from app.db.models.importOperation.worker_assignment import WorkerAssignment
# from app.schemas.importOperation.worker_assignment import WorkerAssignmentRequest, WorkerAssignmentResponseForWorker, WorkerAssignmentResponseForWorkerLists




# IST = ZoneInfo("Asia/Kolkata")
# UTC = ZoneInfo("UTC")



# # ---------------------------------------------------------
# # COMMON FILTER CLASS (Inside the same file)
# # ---------------------------------------------------------

# class WorkerAssignmentFilters:
#     def __init__(self, model, status: str, startDate: str = None, endDate: str = None):
#         self.model = model
#         self.status = status
#         self.startDate = startDate
#         self.endDate = endDate

#     @staticmethod
#     def convert_ist_day_to_utc_range(date_str: str):
#         if not date_str:
#             return None, None

#         ist = pytz.timezone("Asia/Kolkata")
#         d = datetime.strptime(date_str, "%Y-%m-%d")

#         start_ist = ist.localize(d.replace(hour=0, minute=0, second=0))
#         end_ist = ist.localize(d.replace(hour=23, minute=59, second=59, microsecond=999999))

#         return start_ist.astimezone(pytz.UTC), end_ist.astimezone(pytz.UTC)

#     def apply_dlv_zone_filter(self, query):
#         model = self.model
#         status = self.status

#         if status == "dlv_added":
#             return query.where(
#                 model.drop_dlv_zone.isnot(None),
#                 func.trim(model.drop_dlv_zone) != ""
#             )

#         if status == "assigned_but_not_delivered":
#             return query.where(
#                 or_(
#                     model.drop_dlv_zone.is_(None),
#                     func.trim(model.drop_dlv_zone) == ""
#                 )
#             )

#         return query
# # old status filter up to 31-dec-2025 01:17 pm
#     # def apply_status_filter(self, query):
#     #     model = self.model
#     #     status = self.status

#     #     if status == "assigned":
#     #         return query.where(model.assigned_person.isnot(None))

#     #     if status == "unassigned":
#     #         return query.where(model.assigned_person.is_(None))

#     #     if status == "assigned_but_not_delivered":
#     #         return query.where(
#     #             and_(
#     #                 model.assigned_person.isnot(None),
#     #                 or_(
#     #                     model.drop_dlv_zone.is_(None),
#     #                     func.trim(model.drop_dlv_zone) == ""
#     #                 )
#     #             )
#     #         )

#     #     return query
#     def apply_status_filter(self, query):
#         model = self.model
#         status = self.status

#         # -----------------------------
#         # 1️⃣ GP DELIVERED (ONLY delivered)
#         # -----------------------------
#         if status == "gp_delivered":
#             return query.where(
#                 model.gate_pass_end_datetime.isnot(None)
#             )

#         # -----------------------------
#         # 2️⃣ EXCLUDE delivered from ALL other statuses
#         # -----------------------------
#         if status != "all":
#             query = query.where(
#                 model.gate_pass_end_datetime.is_(None)
#             )

#         # -----------------------------
#         # 3️⃣ STATUS-SPECIFIC FILTERS
#         # -----------------------------
#         if status == "assigned":
#             return query.where(model.assigned_person.isnot(None))

#         if status == "unassigned":
#             return query.where(model.assigned_person.is_(None))

#         if status == "assigned_but_not_delivered":
#             return query.where(
#                 and_(
#                     model.assigned_person.isnot(None),
#                     or_(
#                         model.drop_dlv_zone.is_(None),
#                         func.trim(model.drop_dlv_zone) == ""
#                     )
#                 )
#             )

#         # -----------------------------
#         # 4️⃣ DEFAULT → ALL
#         # -----------------------------
#         return query



#     def apply_date_filter(self, query):
#         model = self.model
#         start = self.startDate
#         end = self.endDate

#         if not (start and end):
#             return query

#         utc_start, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start)
#         _, utc_end = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end)

#         return query.where(
#             or_(
#                 model.integrate_date_time.between(utc_start, utc_end),
#                 model.gate_pass_issued_date_time_combo.between(utc_start, utc_end)
#             )
#         )


#     def apply_all(self, query):
#         query = self.apply_dlv_zone_filter(query)
#         query = self.apply_status_filter(query)
#         query = self.apply_date_filter(query)
#         return query

# # ==========================




# def ist_day_to_utc_range(date_obj: date):
#     """
#     Returns a tuple (utc_start, utc_exclusive_end):

#     utc_start  = IST midnight (00:00:00) of date_obj converted to UTC
#     utc_end    = IST midnight (00:00:00) of next day converted to UTC

#     Use this range as:
#         timestamp >= utc_start AND timestamp < utc_end
#     """
#     if isinstance(date_obj, datetime):
#         date_obj = date_obj.date()  # normalize to date only

#     # Start of that day in IST (00:00:00)
#     start_ist = datetime.combine(date_obj, time(0, 0, 0)).replace(tzinfo=IST)

#     # Start of next day in IST (exclusive end)
#     next_day_ist = start_ist + timedelta(days=1)

#     # Convert both to UTC
#     utc_start = start_ist.astimezone(UTC)
#     utc_exclusive_end = next_day_ist.astimezone(UTC)

#     return utc_start, utc_exclusive_end



# def combine_gate_pass_date_with_time_and_return_utc_datetime(
#     gate_pass_issued_date: Optional[datetime], 
#     gate_pass_issued_time: Optional[str]
# ) -> Optional[datetime]:
#     """
#     Combines gate_pass_issued_date (UTC in DB) with gate_pass_issued_time (IST string in db)
#     to produce a single UTC datetime.
    
#     Args:
#         gate_pass_issued_date: DateTime with timezone (UTC) from database
#         gate_pass_issued_time: Time string in IST format like "12:42:00" or "09:30:15"
    
#     Returns:
#         Combined datetime in UTC timezone, or None if either input is None
    
#     Example:
#         Input:  gate_pass_issued_date = 2024-12-16 18:30:00+00:00 (UTC)
#                 gate_pass_issued_time = "12:42:00" (IST time string)
        
#         Process:
#         1. Convert UTC date to IST: 2024-12-17 00:00:00+05:30
#         2. Extract IST date part: 2024-12-17
#         3. Parse IST time: 12:42:00
#         4. Combine: 2024-12-17 12:42:00+05:30 (IST)
#         5. Convert back to UTC: 2024-12-17 07:12:00+00:00
        
#         Output: 2024-12-17 07:12:00+00:00 (UTC)
#     """
    
#     # If either is missing, return None
#     if not gate_pass_issued_date or not gate_pass_issued_time:
#         return None
    
#     try:
#         ist_zone = ZoneInfo("Asia/Kolkata")
#         utc_zone = ZoneInfo("UTC")
        
#         # Step 1: Convert the UTC date to IST to get the correct IST date
#         # (because the time string is in IST, we need the IST date)
#         ist_date = gate_pass_issued_date.astimezone(ist_zone)
        
#         # Step 2: Parse the time string (format: "HH:MM:SS" or "HH:MM")
#         time_str = gate_pass_issued_time.strip()
        
#         # Handle both "HH:MM:SS" and "HH:MM" formats
#         if len(time_str.split(':')) == 2:
#             time_obj = datetime.strptime(time_str, "%H:%M").time()
#         else:
#             time_obj = datetime.strptime(time_str, "%H:%M:%S").time()
        
#         # Step 3: Combine the IST date with the IST time
#         combined_ist = datetime.combine(
#             ist_date.date(),  # Use IST date part
#             time_obj          # Use IST time part
#         ).replace(tzinfo=ist_zone)
#         # print(combined_ist,"combined_ist")
#         # Step 4: Convert the combined IST datetime back to UTC
#         combined_utc = combined_ist.astimezone(utc_zone)
        
#         return combined_utc
        
#     except (ValueError, AttributeError) as e:
#         print(f"Error combining datetime: {e}")
#         return None




# async def process_worker_assignment(db: AsyncSession, req):
#     """
#     ======================================================
#     WORKER ASSIGNMENT PROCESS (SAFE + IDEMPOTENT)
#     ======================================================

#     Identity rule:
#     - Shipment identity = (awb_no, hawb)
#     - oc_no is mutable
#     - temp_irm_oc_no is history only

#     This function:
#     - Syncs oc_merge_gatepass → worker_assignment
#     - Syncs irr_report → worker_assignment
#     - Never creates duplicate rows

#      INSERT  → snapshot from oc_merge_gatepass
#      UPDATE  → propagate only allowed changes
#     """

#     utc_start, utc_end = ist_day_to_utc_range(req.date)
#     now = get_utc_now()

#     # ─────────────────────────────────────────────
#     # 1️⃣ Fetch source data (BATCHED)
#     # ─────────────────────────────────────────────
#     merge_rows = (await db.execute(
#         select(OcMergeGatePass).where(
#             and_(
#                 OcMergeGatePass.integrate_date_time >= utc_start,
#                 OcMergeGatePass.integrate_date_time < utc_end
#             )
#         )
#     )).scalars().all()

#     irr_rows = (await db.execute(
#         select(IrrReport).where(
#             IrrReport.gate_pass_issued_date.between(utc_start, utc_end)
#         )
#     )).scalars().all()

#     # ─────────────────────────────────────────────
#     # 2️⃣ Build IRR map by AWB+HAWB
#     # ─────────────────────────────────────────────
#     irr_map = {
#         (i.awb, i.hwb or ""): i
#         for i in irr_rows
#     }

#     inserted = 0
#     updated = 0

#     # ─────────────────────────────────────────────
#     # 3️⃣ PROCESS OC MERGE DATA
#     # ─────────────────────────────────────────────
#     for oc in merge_rows:
#         key_awb = oc.awb_no
#         key_hawb = oc.hawb or ""

#         stmt = (
#             insert(WorkerAssignment)
#             .values(
#                 # awb_no=key_awb,
#                 # hawb=oc.hawb,
#                 # oc_no=oc.oc_no,                         # real or temp
#                 # temp_irm_oc_no=oc.temp_irm_oc_no,
#                 # igp_no=oc.igp_no,
#                 # integrate_date_time=oc.integrate_date_time,
#                 # from_irr_table=False,
#                 # created_at=now,
#                 # updated_at=now
#                 # ------------------------------
#                  # 🔑 Identity
#                 awb_no=oc.awb_no,
#                 hawb=oc.hawb,

#                 # 🔁 Mutable identifiers
#                 oc_no=oc.oc_no,
#                 temp_irm_oc_no=oc.temp_irm_oc_no,
#                 is_temp_irm_oc=oc.is_temp_irm_oc,
#                 igp_no=oc.igp_no,

#                 # 📦 Snapshot fields (READ-ONLY later)
#                 flight_no=oc.flight_no,
#                 igp_print_date_time=oc.igp_print_date_time,
#                 flight_date=oc.flight_date,
#                 no_of_pc=oc.no_of_pc,
#                 weight_in_kgs=oc.weight_in_kgs,
#                 chg_wgt_in_kg=oc.chg_wgt_in_kg,
#                 location=oc.location,
#                 shc=oc.shc,
#                 irr_codes=oc.irr_codes,
#                 customer_name=oc.customer_name,
#                 agent_name=oc.agent_name,
#                 irregularity_remarks=oc.irregularity_remarks,
#                 integrate_date_time=oc.integrate_date_time,

#                 from_irr_table=False,
#                 created_at=get_utc_now(),
#                 updated_at=get_utc_now()

#             )
#             .on_conflict_do_update(
#                 index_elements=[
#                     WorkerAssignment.awb_no,
#                     text("COALESCE(hawb, '')")
#                 ],
#                 set_={
#                     # 🔥 CRITICAL: propagate OC change
#                     "oc_no": insert(WorkerAssignment).excluded.oc_no,
#                     "temp_irm_oc_no": case(
#                         (
#                             WorkerAssignment.temp_irm_oc_no.is_(None),
#                             insert(WorkerAssignment).excluded.temp_irm_oc_no
#                         ),
#                         else_=WorkerAssignment.temp_irm_oc_no
#                     ),

#                         # ✅ UPDATE weight ONLY IF NULL
#                     "weight_in_kgs": case(
#                         (
#                             WorkerAssignment.weight_in_kgs.is_(None),
#                             insert(WorkerAssignment).excluded.weight_in_kgs
#                         ),
#                         else_=WorkerAssignment.weight_in_kgs
#                     ),

#                     # ✅ UPDATE chargeable weight ONLY IF NULL
#                     "chg_wgt_in_kg": case(
#                         (
#                             WorkerAssignment.chg_wgt_in_kg.is_(None),
#                             insert(WorkerAssignment).excluded.chg_wgt_in_kg
#                         ),
#                         else_=WorkerAssignment.chg_wgt_in_kg
#                     ),
#                      # 🔥 ADD THIS
#     "location": case(
#         (
#             or_(
#                 WorkerAssignment.location.is_(None),
#                 WorkerAssignment.location == ""
#             ),
#             insert(WorkerAssignment).excluded.location
#         ),
#         else_=WorkerAssignment.location
#     ),
#                     "igp_no": insert(WorkerAssignment).excluded.igp_no,
#                     "updated_at": get_utc_now()
#                 }
#             )
#             .returning(
#                 text("CASE WHEN xmax = 0 THEN 1 ELSE 0 END")
#             )
#         )

#         res = (await db.execute(stmt)).all()
#         inserted += sum(1 for r in res if r[0] == 1)
#         updated += sum(1 for r in res if r[0] == 0)

#     # ─────────────────────────────────────────────
#     # 4️⃣ PROCESS IRR DATA (REAL OC ALWAYS)
#     # ─────────────────────────────────────────────
#     for irr in irr_rows:
#         key_awb = irr.awb
#         key_hawb = irr.hwb or ""

#         # 🆕 Combine gate_pass_issued_date (UTC) + gate_pass_issued_time (IST string)
#         gate_pass_combo = combine_gate_pass_date_with_time_and_return_utc_datetime(
#             irr.gate_pass_issued_date,
#             irr.gate_pass_issued_time
#         )
#         stmt = (
#             insert(WorkerAssignment)
#             .values(
#                 # awb_no=key_awb,
#                 # hawb=irr.hwb,
#                 # oc_no=irr.oc_num,              # REAL OC
#                 # igp_no=None,
#                 # integrate_date_time=None,
#                 # from_irr_table=True,
#                 # created_at=now,
#                 # updated_at=now

#                 igp_no=None,
#                 igp_print_date_time=None,
#                 flight_no=irr.flight_no,
#                 awb_no=irr.awb,
#                 hawb=irr.hwb,
#                 flight_date=irr.flight_date,
#                 no_of_pc=irr.pcs,
#                 weight_in_kgs=irr.grg_wt,
#                 chg_wgt_in_kg=irr.chg_wt,
#                 location=irr.location_pcs,
#                 oc_no=irr.oc_num,
#                 irregularity_remarks=None,
#                 pd_in_time=None,
#                 no_of_pc_recd=irr.pcs,
#                 verified_by=None,
#                 agent_name=irr.agent,
#                 customer_name=irr.consignee,
#                 release_zone=irr.dlv_zone,
#                 is_printed=False,
#                 shc=irr.shc,
#                 irr_codes=None,
#                 integrate_date_time=None,

#                 # gate_pass_issued_date=irr.gate_pass_issued_date, # OLD and removed it now 
#                 gate_pass_issued_date_time_combo=gate_pass_combo,  # 🆕 Combined datetime new
#                 gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                 gate_pass_no=irr.gate_pass_no,

#                 from_irr_table=True,
#                 created_at=get_utc_now(),
#                 updated_at=get_utc_now()
#             )
#             .on_conflict_do_update(
#                 index_elements=[
#                     WorkerAssignment.awb_no,
#                     text("COALESCE(hawb, '')")
#                 ],
#              set_={
#                     # 🔥 REAL OC overrides TEMP
#                     "oc_no": insert(WorkerAssignment).excluded.oc_no,
                    
#                     "gate_pass_end_datetime": case(
#                         (
#                             WorkerAssignment.gate_pass_end_datetime.is_(None),
#                             insert(WorkerAssignment).excluded.gate_pass_end_datetime
#                         ),
#                         else_=WorkerAssignment.gate_pass_end_datetime
#                     ),
#                     "gate_pass_no": case(
#                         (
#                             or_(
#                                 WorkerAssignment.gate_pass_no.is_(None),
#                                 WorkerAssignment.gate_pass_no == ""
#                             ),
#                             insert(WorkerAssignment).excluded.gate_pass_no
#                         ),
#                         else_=WorkerAssignment.gate_pass_no
#                     ),
#                     "gate_pass_issued_date_time_combo": case(
#                         (
#                             WorkerAssignment.gate_pass_issued_date_time_combo.is_(None),
#                             insert(WorkerAssignment).excluded.gate_pass_issued_date_time_combo
#                         ),
#                         else_=WorkerAssignment.gate_pass_issued_date_time_combo
#                     ),
#                     # :white_check_mark: BACKFILL location if missing
#                         "location": case(
#                             (
#                                 or_(
#                                     WorkerAssignment.location.is_(None),
#                                     WorkerAssignment.location == ""
#                                 ),
#                                 insert(WorkerAssignment).excluded.location
#                             ),
#                             else_=WorkerAssignment.location
#                         ),
#                         # :white_check_mark: BACKFILL weight if missing
#                         "weight_in_kgs": case(
#                             (
#                                 WorkerAssignment.weight_in_kgs.is_(None),
#                                 insert(WorkerAssignment).excluded.weight_in_kgs
#                             ),
#                             else_=WorkerAssignment.weight_in_kgs
#                         ),
#                         # :white_check_mark: BACKFILL chargeable weight
#                         "chg_wgt_in_kg": case(
#                             (
#                                 WorkerAssignment.chg_wgt_in_kg.is_(None),
#                                 insert(WorkerAssignment).excluded.chg_wgt_in_kg
#                             ),
#                             else_=WorkerAssignment.chg_wgt_in_kg
#                         ),
#                         # :white_check_mark: BACKFILL pcs
#                         "no_of_pc": case(
#                             (
#                                 WorkerAssignment.no_of_pc.is_(None),
#                                 insert(WorkerAssignment).excluded.no_of_pc
#                             ),
#                             else_=WorkerAssignment.no_of_pc
#                         ),
                    
#                     "updated_at": now
#                 }
#             )
#             .returning(
#                 text("CASE WHEN xmax = 0 THEN 1 ELSE 0 END")
#             )
#         )

#         res = (await db.execute(stmt)).all()
#         inserted += sum(1 for r in res if r[0] == 1)
#         updated += sum(1 for r in res if r[0] == 0)

#     await db.commit()

#     return {
#         "success": True,
#         "merge_rows_processed": len(merge_rows),
#         "irr_rows_processed": len(irr_rows),
#         "inserted_rows": inserted,
#         "updated_rows": updated
#     }












# async def get_all_worker_assignments_list(db: AsyncSession):
#     query = select(WorkerAssignment).order_by(WorkerAssignment.id.desc())
#     result = await db.execute(query)
#     rows = result.scalars().all()
#     return rows







# async def get_all_allowed_users_as_worker(db: AsyncSession) -> list[User]:
#     allowed_roles_for_become_worker = ['imp_gp_user']  # Define the allowed role
    
#     query = select(User).filter(User.role.in_(allowed_roles_for_become_worker), User.is_active == True)
    
#     result = await db.execute(query)
#     users = result.scalars().all()

#     if not users:
#         raise HTTPException(status_code=404, detail="No users found for assignment")
    
#     return users


# async def get_worker_assignment_lists_by_emp_id(db: AsyncSession, emp_id: str) -> list[WorkerAssignment]:
#     # Query the User table to check the role of the user
#     user_query = select(User).filter(User.emp_id == emp_id)
#     result = await db.execute(user_query)
#     user = result.scalars().first()

#     if not user:
#         raise HTTPException(status_code=404, detail="User not found")

#     # Check if the user has the 'imp_gp_user' role
#     if user.role != 'imp_gp_user':
#         raise HTTPException(status_code=403, detail="User is not authorized for this action")

#     # If the user is authorized, fetch the worker assignments assigned to the user
#      # Fetch only unfilled drop_dlv_zone assignments
#     assignment_query = (
#         select(WorkerAssignment)
#         .filter(WorkerAssignment.assigned_person == emp_id)
#         .filter(
#             or_(
#                 WorkerAssignment.drop_dlv_zone.is_(None),   # NULL
#                 WorkerAssignment.drop_dlv_zone == ""        # empty string (optional)
#             )
#         )
#     )

#     result = await db.execute(assignment_query)
#     worker_assignments = result.scalars().all()

#     return worker_assignments



# # ==========Assign a user to the worker assignment table row data =============================

# async def assign_user_to_worker_assignment(db: AsyncSession,
#             oc_no: str, 
#             emp_id: str | None,  # worker being assigned
#             current_user_role:str,
#             changed_by  : str,      # actor which perform this operation
#             *,
#             ip_address: str | None,
#             user_agent:str |None,
#             device_id:str |None,
            
#             ) -> bool:
#     # Step 1: Check if the worker assignment with the given `oc_no` exists
#     result = await db.execute(select(WorkerAssignment).filter(WorkerAssignment.oc_no == oc_no))
#     worker_assignment = result.scalars().first()

#     if not worker_assignment:
#         raise HTTPException(status_code=404, detail=f"Worker assignment with OC No {oc_no} not found.")
    
    
#     # 🔒 Capture old value BEFORE change
#     old_assigned_person = worker_assignment.assigned_person

#     if emp_id == worker_assignment.assigned_person:
#         return True  # no change, skip update & audit


#     # -----------------------------
#     # ✅ UNASSIGN CASE
#     # -----------------------------
#     if emp_id is None:
#         worker_assignment.assigned_person = None
#         worker_assignment.assigned_person_datetime = None
#         worker_assignment.updated_at = get_utc_now()

#         await log_worker_assignment_audit(
#             db=db,
#             assignment=worker_assignment,
#             field_name="assigned_person",
#             old_value=old_assigned_person,
#             new_value=None,
#             changed_by=changed_by,
#             changed_by_role=current_user_role,
#             device_id=device_id,
#             user_agent=user_agent,
#             ip_address=ip_address,
#             db_action="UPDATE",
#             source_action="unassign_user",
#         )

#         db.add(worker_assignment)
#         await db.commit()
#         return True
    
#     # -----------------------------
#     # ✅ ASSIGN CASE
#     # -----------------------------
#     user_result = await db.execute(
#         select(User).filter(
#             User.emp_id == emp_id,
#             User.role == "imp_gp_user",
#             User.is_active.is_(True)
#         )
#     )
#     user = user_result.scalars().first()

#     if not user:
#         raise HTTPException(
#             status_code=400,
#             detail=f"User with emp_id {emp_id} not found, inactive, or invalid role."
#         )

#     worker_assignment.assigned_person = emp_id
#     worker_assignment.assigned_person_datetime = get_utc_now()
#     worker_assignment.updated_at = get_utc_now()

#     await log_worker_assignment_audit(
#         db=db,
#         assignment=worker_assignment,
#         field_name="assigned_person",
#         old_value=old_assigned_person,
#         new_value=emp_id,
#         changed_by=changed_by,
#         changed_by_role=current_user_role,
#         device_id=device_id,
#         user_agent=user_agent,
#         ip_address=ip_address,
#         db_action="UPDATE",
#         source_action="assign_user",
#     )

#     db.add(worker_assignment)
#     await db.commit()
#     return True
    
#     # ----




# # add drop_dlv_zone by assigned user or worker ===============================
# async def add_drop_dlv_zone_by_assigned_worker(
#     db: AsyncSession, 
#     oc_no: str, 
#     emp_id: str, 
#     current_user_role:str,
#     drop_dlv_zone: str,
#     ip_address: str = None,
#     device_id:str = None,
#     user_agent:str = None
# ) -> dict:
#     try:
#         # Step 1: Fetch worker assignment by oc_no
#         stmt = select(WorkerAssignment).filter(WorkerAssignment.oc_no == oc_no)
#         result = await db.execute(stmt)
#         worker_assignment = result.scalars().first()

#         # If worker assignment does not exist
#         if not worker_assignment:
#             # return {"status": "error", "message": "Record not found for the given OC No."}
#             raise HTTPException(status_code=404, detail=f"Record not found for the given OC No: {oc_no}")
        
#         if not worker_assignment.assigned_person:
#             raise HTTPException(
#                 status_code=400,
#                 detail="No worker has been assigned to this OC yet."
#             )

#         # Step 2: Cross-check if the emp_id matches the assigned person
#         if worker_assignment.assigned_person != emp_id:
#             return {"status": "error", "message": "This OC No. is assigned to someone else."}

#         # Step 3: Check if drop_dlv_zone is already set
#         if worker_assignment.drop_dlv_zone:
#             return {"status": "error", "message": "Delivery zone has already been filled.."}
#         # Store old value for audit log (before update)
#         old_drop_dlv_zone = worker_assignment.drop_dlv_zone

#         # Step 4: Update drop_dlv_zone and set drop_dlv_zone_datetime
#         print("role--------------------",current_user_role)
#         stmt = (
#             update(WorkerAssignment)
#             .where(WorkerAssignment.oc_no == oc_no)
#             .values(
#                 drop_dlv_zone=drop_dlv_zone,
#                 drop_dlv_zone_datetime=get_utc_now(),  
#                 updated_at=get_utc_now()
#             )
#         )
#         await db.execute(stmt)
#         # 🧾 5️⃣ AUDIT LOG (after update, before commit)
#         await log_worker_assignment_audit(
#             db=db,
#             assignment=worker_assignment,  # Fixed: use worker_assignment
#             field_name="drop_dlv_zone",
#             old_value=old_drop_dlv_zone,
#             new_value=drop_dlv_zone,
#             changed_by=emp_id,
#             changed_by_role=current_user_role,
#             user_agent = user_agent,
#             ip_address=ip_address,
#             device_id = device_id,
#             db_action="UPDATE",
#             source_action="dlv_zone_update",
#         )

#         await db.commit()

#         return {"status": "success", "message": f"Drop delivery zone successfully updated by {emp_id}."}
#     except HTTPException:
#         # ❌ Rollback on known errors (404, 403, 400)
#         await db.rollback()
#         raise  # Re-raise HTTPException to be handled by FastAPI
    
#     except Exception as e:
#         # ❌ Rollback on any unexpected errors
#         await db.rollback()
#         # logger.error(f"Unexpected error in add_drop_dlv_zone_by_assigned_worker: {str(e)}")
#         raise HTTPException(
#             status_code=500,
#             detail="An unexpected error occurred. Please try again later."
#         )





# #=========== PAGINATED WORKER ASSIGNMENT DATA WITH FILTERS AND MATRIX COUNTS (NEW)

# async def get_paginated_worker_assignments_data_list(
#     db: AsyncSession,
#     model,
#     status: str = "all",
#     startDate: Optional[str] = None,
#     endDate: Optional[str] = None,
#     page: int = 1,
#     page_size: int = 10
# ) -> Dict[str, Any]:
#     """
#     One single static method that contains ALL logic using inner functions.
#     """

#     # -----------------------------------------------------
#     # INTERNAL HELPERS
#     # -----------------------------------------------------

#     def convert_ist_day_to_utc_range(date_str: str):
#         ist = pytz.timezone("Asia/Kolkata")
#         d = datetime.strptime(date_str, "%Y-%m-%d")

#         start_ist = ist.localize(d.replace(hour=0, minute=0, second=0))
#         end_ist = ist.localize(d.replace(hour=23, minute=59, second=59, microsecond=999999))

#         return start_ist.astimezone(pytz.UTC), end_ist.astimezone(pytz.UTC)



 
#     async def calculate_matrix(base_query):
#         # 1. PURE OC COUNT
#         pure = base_query.where(
#             and_(
#                 model.from_irr_table == False,
#                 or_(
#                     model.temp_irm_oc_no.is_(None),
#                     func.trim(model.temp_irm_oc_no) == ""
#                 )
#             )
#         )
#         pure_count = (await db.execute(
#             select(func.count()).select_from(pure.subquery())
#         )).scalar() or 0

#         # 2. TEMP IRM COUNT
#         temp_irm = base_query.where(
#             and_(
#                 model.from_irr_table == False,
#                 model.temp_irm_oc_no.isnot(None),
#                 func.trim(model.temp_irm_oc_no) != ""
#             )
#         )
#         temp_irm_count = (await db.execute(
#             select(func.count()).select_from(temp_irm.subquery())
#         )).scalar() or 0

#         # 3. GP COUNT
#         gp = base_query.where(
#             and_(
#                 model.gate_pass_no.isnot(None),
#                 func.trim(model.gate_pass_no) != ""
#             )
#         )
#         gp_count = (await db.execute(
#             select(func.count()).select_from(gp.subquery())
#         )).scalar() or 0

#         return {
#             "pure_oc_merge_count": pure_count,
#             "temp_irm_count": temp_irm_count,
#             "gp_alloted_count": gp_count
#         }

#     # -----------------------------------------------------
#     # STEP 1 – BUILD BASE QUERY (class based)
#     # -----------------------------------------------------
#     # -----------------------------------------------------
# # STEP 1 – BUILD BASE QUERY (CLASS BASED)
# # -----------------------------------------------------
#     filters = WorkerAssignmentFilters(
#         model=model,
#         status=status,
#         startDate=startDate,
#         endDate=endDate
#     )

#     base_query = filters.apply_all(select(model))


#     # -----------------------------------------------------
#     # STEP 2 – TOTAL RECORDS
#     # -----------------------------------------------------
#     total_records = (await db.execute(
#         select(func.count()).select_from(base_query.subquery())
#     )).scalar() or 0

#     total_pages = ceil(total_records / page_size) if page_size > 0 else 0

#     if page < 1:
#         page = 1
#     if total_pages > 0 and page > total_pages:
#         page = total_pages

#     offset = (page - 1) * page_size

#     # -----------------------------------------------------
#     # STEP 3 – PAGINATED DATA
#     # -----------------------------------------------------
#     paginated_query = (
#         base_query
#         # .order_by(model.id.desc())
#          .order_by(
#         model.gate_pass_no.is_(None),   # NULL GP go last
#         model.gate_pass_no.asc(),       # GP numbers ascending
#         model.oc_no.asc()               # OC ascending
#     )
#         .offset(offset)
#         .limit(page_size)
#     )

#     result = await db.execute(paginated_query)
#     records = result.scalars().all()

#     # -----------------------------------------------------
#     # STEP 4 – MATRIX COUNTS
#     # -----------------------------------------------------
#     matrix_counts = await calculate_matrix(base_query)

#     # -----------------------------------------------------
#     # STEP 5 – RETURN RESPONSE
#     # -----------------------------------------------------
#     return {
#         # "data": records,
#         "success": True,
#     "message": "Worker assignments fetched successfully",
#         "data": [WorkerAssignmentResponseForWorker.model_validate(r) for r in records],

#         "pagination": {
#             "current_page": page,
#             "page_size": page_size,
#             "total_records": total_records,
#             "total_pages": total_pages,
#             "has_previous": page > 1,
#             "has_next": page < total_pages,
#             "previous_page": page - 1 if page > 1 else None,
#             "next_page": page + 1 if page < total_pages else None
#         },
#         "matrix_counts": matrix_counts,
#         "filters_applied": {
#             "status": status,
#             "start_date": startDate,
#             "end_date": endDate
#         }
#     }

# #-----this is used for sear ch in worker assignment page where I can search by awb hawb gp_no, oc_no, temp_oc -------
# async def search_in_worker_assignments(
#     db: AsyncSession,
#     search_type: str,
#     search_value: str
# ) ->WorkerAssignmentResponseForWorkerLists:

#     field_map = {
#         "oc_no": WorkerAssignment.oc_no,
#         "gp_no": WorkerAssignment.gate_pass_no,
#         "temp_oc": WorkerAssignment.temp_irm_oc_no,
#         "awb": WorkerAssignment.awb_no,
#         "hawb": WorkerAssignment.hawb,
#     }

#     print(search_type,search_value,"search_type,search_value")


#     if search_type not in field_map:
#         return []  # invalid search type

#     column = field_map[search_type]

#     if search_type == "gp_no":
#         stmt = select(WorkerAssignment).where(
#             func.lower(WorkerAssignment.gate_pass_no)
#             .contains(search_value.lower())
#         )
#     else:
#         stmt = select(WorkerAssignment).where(column == search_value)

#     # stmt = select(WorkerAssignment).where(column == search_value)



#     result = await db.execute(stmt)
#     return result.scalars().all()





# #============= IT IS USED TO EXPORT EXCEL STREAMING FOR WORKER ASSIGNMENT DATA WITH FILTERS ================
# async def generate_excel_stream_export_worker_assignment(
#     db: AsyncSession,
#     assignment_status: str,
#     start_date: str,
#     end_date: str,
#     chunk_size: int = 1000
# ) -> AsyncGenerator[bytes, None]:
#     """
#     Async generator that streams Excel file in chunks
#     Processes records in batches to avoid memory issues
#     """

#     # Create in-memory buffer
#     output = io.BytesIO()
    
#     # Create workbook and worksheet
#     workbook = xlsxwriter.Workbook(output, {'in_memory': True})
#     worksheet = workbook.add_worksheet('Worker Assignments')
    
#     # Define formats
#     header_format = workbook.add_format({
#         'bold': True,
#         # 'bg_color': '#4472C4',
#         # 'font_color': 'white',
#         'border': 1,
#         'align': 'center',
#         'valign': 'vcenter',
#         'text_wrap': False
#     })
    
#     date_format = workbook.add_format({
#         'num_format': 'dd/mm/yyyy hh:mm',
#         'align': 'left'
#     })
    
#     number_format = workbook.add_format({
#         'num_format': '0.00',
#         'align': 'right'
#     })

#     integer_format = workbook.add_format({
#     'num_format': '0',
#     'align': 'right'
# })

    
#     text_format = workbook.add_format({
#         'align': 'left',
#         'valign': 'top',
#         'text_wrap': True
#     })
    
#     text_center = workbook.add_format({
#         'align': 'center',
#         'valign': 'vcenter'
#     })
    
#     # Define headers
    
#     headers = [
#         'S.No', 'IGP No', 'OC No', 'Temp IRM OC',
#         'AWB No', 'HAWB', 'Flight No', 'Flight Date',
#         'No of Pieces', 'Weight (KG)', 'Chargeable Weight (KG)',
#         'Location', 'Agent Name', 'Customer Name', 
#         # 'Release Zone',
#         'SHC', 'IRR Codes', 'Irregularity Remarks',
#         'Gate Pass No', 'GP Issue Date', 'GP End Date',
#         'Assigned Person', 'Assigned Person Name','Assigned DateTime',
#         'Drop Delivery Zone', 'Drop DLV DateTime',
#         'From Source', 'Integrate Date', 'Created At'
#     ]
    
#     # Write headers
#     for col_num, header in enumerate(headers):
#         worksheet.write(0, col_num, header, header_format)
    
#     # # Set column widths
#     # column_widths = {
#     #     0: 8,   # S.No
#     #     1: 15,  # IGP No
#     #     2: 15,  # OC No
#     #     3: 15,  # Temp IRM OC
#     #     4: 12,  # Is Temp OC
#     #     5: 18,  # AWB No
#     #     6: 18,  # HAWB
#     #     7: 12,  # Flight No
#     #     8: 18,  # Flight Date
#     #     9: 12,  # No of Pieces
#     #     10: 12, # Weight
#     #     11: 18, # Chargeable Weight
#     #     12: 25, # Location
#     #     13: 30, # Agent Name
#     #     14: 30, # Customer Name
#     #     # 15: 15, # Release Zone
#     #     15: 15,  # SHC
#     #     16: 20,  # IRR Codes
#     #     17: 35,  # Irregularity Remarks
#     #     18: 18,  # Gate Pass No
#     #     19: 18,  # GP Issue Date
#     #     20: 18,  # GP End Date
#     #     21: 20,  # Assigned Person
#     #     22: 18,  # Assigned DateTime
#     #     23: 20,  # Drop Delivery Zone
#     #     24: 18,  # Drop DLV DateTime
#     #     25: 15,  # From IRR Table
#     #     26: 18,  # Integrate Date
#     #     27: 18   # Created At

#     # }

#     column_widths = {
#     0: 8,   # S.No
#     1: 15,  # IGP No
#     2: 15,  # OC No
#     3: 15,  # Temp IRM OC

#     # ❌ Removed: Is Temp OC (was index 4)

#     4: 18,  # AWB No
#     5: 18,  # HAWB
#     6: 12,  # Flight No
#     7: 18,  # Flight Date
#     8: 12,  # No of Pieces
#     9: 12,  # Weight
#     10: 18, # Chargeable Weight
#     11: 25, # Location
#     12: 30, # Agent Name
#     13: 30, # Customer Name

#     14: 15,  # SHC
#     15: 20,  # IRR Codes
#     16: 35,  # Irregularity Remarks
#     17: 18,  # Gate Pass No
#     18: 18,  # GP Issue Date
#     19: 18,  # GP End Date
#     20: 20,  # Assigned Person
#     21: 25,  # Assigned Person Name
#     22: 18,  # Assigned DateTime
#     23: 20,  # Drop Delivery Zone
#     24: 18,  # Drop DLV DateTime
#     25: 15,  # From IRR Table
#     26: 18,  # Integrate Date
#     27: 18   # Created At
# }

    
#     for col, width in column_widths.items():
#         worksheet.set_column(col, col, width)
    
#     # Freeze header row
#     worksheet.freeze_panes(1, 0)
    
#     # Parse dates
#     start = datetime.strptime(start_date, "%Y-%m-%d").date()
#     end = datetime.strptime(end_date, "%Y-%m-%d").date()
    
#     # Build base query---------------
    
#     # USE COMMON FILTER LOGIC
#     # ----------------------------------------
#     filters = WorkerAssignmentFilters(
#         model=WorkerAssignment,
#         status=assignment_status,
#         startDate=start_date,
#         endDate=end_date
#     )

#     # base_query = filters.apply_all(select(WorkerAssignment))
#     UserAlias = aliased(User)

#     base_query = (
#         filters.apply_all(
#             select(
#                 WorkerAssignment,
#                 UserAlias.name.label("assigned_person_name")
#             )
#             .outerjoin(
#                 UserAlias,
#                 UserAlias.emp_id == WorkerAssignment.assigned_person
#             )
#         )
#     )

#     # SAME ORDERING AS TABLE VIEW
#     base_query = base_query.order_by(
#         WorkerAssignment.gate_pass_no.is_(None),
#         WorkerAssignment.gate_pass_no.asc(),
#         WorkerAssignment.oc_no.asc()
#     )

    
#     def to_ist_no_tz(dt):
#         """
#         Convert UTC datetime → IST datetime (naive)
#         Excel requires timezone removed.
#         """
#         IST = pytz.timezone("Asia/Kolkata")
#         if not dt:
#             return None

#         # If timezone-aware: convert to IST
#         if dt.tzinfo:
#             dt = dt.astimezone(IST)
#         # Make timezone-naive for Excel
#         return dt.replace(tzinfo=None)
    
#     # helper function to get source value that from where it data originated in assignment table (it get from source header value)
#     def get_source_label(assignment):
#         if assignment.from_irr_table and not assignment.temp_irm_oc_no:
#             return "IRR"
#         if assignment.temp_irm_oc_no and not assignment.from_irr_table:
#             return "IRM"
#         if not assignment.temp_irm_oc_no and not assignment.from_irr_table:
#             return "OC MERGE"
#         return ""


#     # Process in chunks
#     row_num = 1
#     offset = 0
    
#     while True:
#         # Fetch chunk asynchronously
#         chunk_query = base_query.offset(offset).limit(chunk_size)
#         result = await db.execute(chunk_query)
#         # chunk = result.scalars().all()
#         chunk = result.all()

        
#         if not chunk:
#             break
        
#         # Write chunk to Excel
#         # for assignment in chunk:
#         for assignment, assigned_person_name in chunk:

#             # S.No
#             worksheet.write(row_num, 0, row_num, text_center)
            
#             # IGP No
#             worksheet.write(row_num, 1, assignment.igp_no or '', text_format)
            
#             # OC No
#             worksheet.write(row_num, 2, assignment.oc_no or '', text_format)
            
#             # Temp IRM OC
#             worksheet.write(row_num, 3, assignment.temp_irm_oc_no or '', text_format)
            
#             # # Is Temp OC
#             # worksheet.write(row_num, 4, 'Yes' if assignment.is_temp_irm_oc else 'No', text_center)
            
#             # AWB No
#             worksheet.write(row_num, 4, assignment.awb_no or '', text_format)
            
#             # HAWB
#             worksheet.write(row_num, 5, assignment.hawb or '', text_format)
            
#             # Flight No
#             worksheet.write(row_num, 6, assignment.flight_no or '', text_format)
            
#             # Flight Date
#             if assignment.flight_date:
#                 worksheet.write_datetime(row_num, 7, to_ist_no_tz(assignment.flight_date), date_format)
#             else:
#                 worksheet.write(row_num, 7, '', text_format)
            
#             # No of Pieces
#             # worksheet.write(row_num, 9, assignment.no_of_pc or '', integer_format)

#             # No of Pieces
#             if assignment.no_of_pc is not None:
#                 worksheet.write_number(row_num, 8, assignment.no_of_pc, integer_format)
#             else:
#                 worksheet.write_blank(row_num, 8, None)

            
#             # Weight (KG)
#             # worksheet.write(row_num, 10, assignment.weight_in_kgs or 0.0, number_format)
            
#             # Chargeable Weight (KG)
#             # worksheet.write(row_num, 11, assignment.chg_wgt_in_kg or 0.0, number_format)

#             # Weight (KG)
#             if assignment.weight_in_kgs is not None:
#                 worksheet.write_number(row_num, 9, assignment.weight_in_kgs, number_format)
#             else:
#                 worksheet.write_blank(row_num, 9, None)

#             # Chargeable Weight (KG)
#             if assignment.chg_wgt_in_kg is not None:
#                 worksheet.write_number(row_num, 10, assignment.chg_wgt_in_kg, number_format)
#             else:
#                 worksheet.write_blank(row_num, 10, None)

            
#             # Location
#             worksheet.write(row_num, 11, assignment.location or '', text_format)
            
#             # Agent Name
#             worksheet.write(row_num, 12, assignment.agent_name or '', text_format)
            
#             # Customer Name
#             worksheet.write(row_num, 13, assignment.customer_name or '', text_format)
            
#             # Release Zone
#             # worksheet.write(row_num, 15, assignment.release_zone or '', text_format)
            
#             # SHC
#             worksheet.write(row_num, 14, assignment.shc or '', text_format)
            
#             # IRR Codes
#             worksheet.write(row_num, 15, assignment.irr_codes or '', text_format)
            
#             # Irregularity Remarks
#             worksheet.write(row_num, 16, assignment.irregularity_remarks or '', text_format)
            
#             # Gate Pass No
#             worksheet.write(row_num, 17, assignment.gate_pass_no or '', text_format)
            
#             # GP Issue Date
#             if assignment.gate_pass_issued_date_time_combo:
#                 worksheet.write_datetime(row_num, 18, to_ist_no_tz(assignment.gate_pass_issued_date_time_combo), date_format)
#             else:
#                 worksheet.write(row_num, 18, '', text_format)
            
#             # GP End Date
#             if assignment.gate_pass_end_datetime:
#                 worksheet.write_datetime(row_num, 19, to_ist_no_tz(assignment.gate_pass_end_datetime), date_format)
#             else:
#                 worksheet.write(row_num, 19, '', text_format)
            
#             # Assigned Person
#             worksheet.write(row_num, 20, assignment.assigned_person or '', text_format)

#             # Assigned Person Name (from users table)
#             worksheet.write(
#                 row_num,
#                 21,
#                 assigned_person_name or '',
#                 text_format
#             )
                        
#             # Assigned DateTime
#             if assignment.assigned_person_datetime:
#                 worksheet.write_datetime(row_num, 22, to_ist_no_tz(assignment.assigned_person_datetime), date_format)
#             else:
#                 worksheet.write(row_num, 22, '', text_format)
            
#             # Drop Delivery Zone
#             worksheet.write(row_num, 23, assignment.drop_dlv_zone or '', text_format)
            
#             # Drop DLV DateTime
#             if assignment.drop_dlv_zone_datetime:
#                 worksheet.write_datetime(row_num, 24, to_ist_no_tz(assignment.drop_dlv_zone_datetime), date_format)
#             else:
#                 worksheet.write(row_num, 24, '', text_format)
            
#             # From IRR Table
#             # worksheet.write(row_num, 26, 'Yes' if assignment.from_irr_table else 'No', text_center)
#             worksheet.write(
#                 row_num,
#                 25,  # Source column index
#                 get_source_label(assignment),
#                 text_center
#             )

            
#             # Integrate Date
#             if assignment.integrate_date_time:
#                 worksheet.write_datetime(row_num, 26, to_ist_no_tz(assignment.integrate_date_time), date_format)
#             else:
#                 worksheet.write(row_num, 26, '', text_format)
            
#             # Created At
#             if assignment.created_at:
#                 worksheet.write_datetime(row_num, 27, to_ist_no_tz(assignment.created_at), date_format)
#             else:
#                 worksheet.write(row_num, 27, '', text_format)
            
#             row_num += 1
        
#         offset += chunk_size
    
#     # Close workbook to finalize
#     workbook.close()
    
#     # Seek to beginning
#     output.seek(0)
    
#     # Yield the complete file
#     yield output.read()



# # =========== Get summary data of allocations and IRM related ==========================
# async def get_assignment_summary(db, start_utc, end_utc):
#     """
#     Dashboard summary for:
#     - OC_MERGE
#     - IRM
#     - IRR
#     Always returns all 3 categories (missing ones filled with zero values).
#     """

#     ALL_CATEGORIES = ["OC_MERGE", "IRM", "IRR"]

#     # Category mapping (NO SPACES)
#     category_case = case(
#         (WorkerAssignment.from_irr_table.is_(True), "IRR"),
#         (
#             and_(
#                 WorkerAssignment.temp_irm_oc_no.isnot(None),
#                 WorkerAssignment.temp_irm_oc_no != ""
#             ),
#             "IRM"
#         ),
#         else_="OC_MERGE"
#     ).label("category")

#     # Fallback date logic
#     date_field = func.coalesce(
#         WorkerAssignment.integrate_date_time,
#         WorkerAssignment.gate_pass_issued_date_time_combo
#     )

#     # Main query
#     stmt = (
#         select(
#             category_case,
#             func.count(WorkerAssignment.id).label("count"),

#             func.count(
#                 case((WorkerAssignment.gate_pass_no.isnot(None), 1))
#             ).label("converted_to_gp"),

#             func.count(
#                 case((WorkerAssignment.drop_dlv_zone.isnot(None), 1))
#             ).label("delivered"),

#             func.count(
#                 case(
#                     (
#                         and_(
#                             WorkerAssignment.assigned_person.isnot(None),
#                             WorkerAssignment.assigned_person_datetime.isnot(None)
#                         ),
#                         1
#                     )
#                 )
#             ).label("assigned"),
#         )
#         .where(
#             date_field >= start_utc,
#             date_field < end_utc
#         )
#         .group_by(category_case)
#     )

#     result = await db.execute(stmt)
#     rows = result.all()

#     # Convert rows → map by category
#     data_map = {row.category: row for row in rows}

#     # Ensure ALL categories exist in output
#     summary = []
#     for cat in ALL_CATEGORIES:
#         if cat in data_map:
#             row = data_map[cat]
#             summary.append({
#                 "category": cat,
#                 "count": row.count,
#                 "converted_to_gp": row.converted_to_gp,
#                 "delivered": row.delivered,
#                 "assigned": row.assigned,
#                 "balance_for_delivered": row.count - row.delivered,
#             })
#         else:
#             # Default zero values
#             summary.append({
#                 "category": cat,
#                 "count": 0,
#                 "converted_to_gp": 0,
#                 "delivered": 0,
#                 "assigned": 0,
#                 "balance_for_delivered": 0,
#             })

#     return summary



# async def get_assignment_summary_according_to_assigned_person(db, start_utc, end_utc):
#     """
#     Operator-wise assignment dashboard.
#     Date range logic:
#     COALESCE(integrate_date_time, gate_pass_issued_date_time_combo)
#     """

#     # Fallback date logic (same as your category summary)
#     date_field = func.coalesce(
#         WorkerAssignment.integrate_date_time,
#         WorkerAssignment.gate_pass_issued_date_time_combo
#     )

#     # Query grouped by assigned_person
#     stmt = (
#         select(
#             WorkerAssignment.assigned_person.label("operator"),

#             # Count assigned → assigned_person + assigned_person_datetime required
#             func.count(
#                 case((
#                     and_(
#                         WorkerAssignment.assigned_person.isnot(None),
#                         WorkerAssignment.assigned_person_datetime.isnot(None)
#                     ),
#                     1
#                 ))
#             ).label("assigned"),

#             # Count completed → drop_dlv_zone not null
#             func.count(
#                 case((WorkerAssignment.drop_dlv_zone.isnot(None), 1))
#             ).label("completed"),
#         )
#         .where(
#             WorkerAssignment.assigned_person.isnot(None),           # must be assigned
#             WorkerAssignment.assigned_person_datetime.isnot(None), # cannot be blank
#             date_field >= start_utc,
#             date_field < end_utc
#         )
#         .group_by(WorkerAssignment.assigned_person)
#         .order_by(WorkerAssignment.assigned_person)
#     )

#     result = await db.execute(stmt)
#     rows = result.all()

#     summary = []
#     total_assigned = 0
#     total_completed = 0

#     for row in rows:
#         assigned = row.assigned or 0
#         completed = row.completed or 0

#         performance = round((completed / assigned) * 100, 2) if assigned else 0

#         summary.append({
#             "operator": row.operator,  # example: "5234987"
#             "assigned": assigned,
#             "completed": completed,
#             "performance": performance,
#         })

#         total_assigned += assigned
#         total_completed += completed

#     # TOTAL ROW
#     total_performance = round((total_completed / total_assigned) * 100, 2) if total_assigned else 0

#     summary.append({
#         "operator": "TOTAL",
#         "assigned": total_assigned,
#         "completed": total_completed,
#         "performance": total_performance,
#     })

#     return summary




# =========================👌👌👌👌👌👌👌👌👌👌👌👌👌👌👌👌👌=============================
# ===================   NEW TWO LEVEL STRUCTURE BASE SERVICE FUNCTIONS     ======================




from datetime import datetime, time,date , timedelta
import io
import xlsxwriter
from typing import Any, Dict, Generator, List, Optional, AsyncGenerator
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
from app.db.models.importOperation.worker_assignment import WorkerAssignmentHeader, WorkerAssignmentShipment
from app.schemas.importOperation.worker_assignment import WorkerAssignmentRequest, WorkerAssignmentResponseForWorker, WorkerAssignmentResponseForWorkerLists




IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")



# ---------------------------------------------------------
# COMMON FILTER CLASS (Inside the same file)
# ---------------------------------------------------------

class WorkerAssignmentFilters:
    def __init__(self, shipment_model, status: str, startDate: str = None, endDate: str = None):
        self.shipment = shipment_model
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
        shipment = self.shipment   # MUST be WorkerAssignmentShipment
        status = self.status

        if status == "dlv_added":
            return query.where(
                shipment.drop_dlv_zone.isnot(None),
                func.trim(shipment.drop_dlv_zone) != ""
            )

        if status == "assigned_but_not_delivered":
            return query.where(
                or_(
                    shipment.drop_dlv_zone.is_(None),
                    func.trim(shipment.drop_dlv_zone) == ""
                )
            )

        return query


    def apply_status_filter(self, query):
        shipment = self.shipment
        status = self.status

         # ------------------------------------------------
        # 🔥 NEW: GP GENERATED (ignore everything except date)
        # ------------------------------------------------
        if status == "gp_generated":
            return query.where(
                shipment.gate_pass_no.isnot(None),
                func.trim(shipment.gate_pass_no) != ""
            )

        # -----------------------------
        # 1️⃣ GP DELIVERED (ONLY delivered)
        # -----------------------------
        if status == "gp_delivered":
            return query.where(
                shipment.gate_pass_end_datetime.isnot(None)
            )

        # -----------------------------
        # 2️⃣ EXCLUDE delivered from ALL other statuses
        # -----------------------------
        if status != "all":
            query = query.where(
                shipment.gate_pass_end_datetime.is_(None)
            )

        # -----------------------------
        # 3️⃣ STATUS-SPECIFIC FILTERS
        # -----------------------------
        if status == "assigned":
            return query.where(shipment.assigned_person.isnot(None))

        if status == "unassigned":
            return query.where(shipment.assigned_person.is_(None))

        if status == "assigned_but_not_delivered":
            return query.where(
                and_(
                    shipment.assigned_person.isnot(None),
                    or_(
                        shipment.drop_dlv_zone.is_(None),
                        func.trim(shipment.drop_dlv_zone) == ""
                    )
                )
            )

        # -----------------------------
        # 4️⃣ DEFAULT → ALL
        # -----------------------------
        return query


    def apply_date_filter(self, query):
        shipment = self.shipment

        if not (self.startDate and self.endDate):
            return query

        utc_start, _ = self.convert_ist_day_to_utc_range(self.startDate)
        _, utc_end = self.convert_ist_day_to_utc_range(self.endDate)

        return query.where(
            or_(
                shipment.integrate_date_time.between(utc_start, utc_end),
                shipment.gate_pass_issued_date_time_combo.between(utc_start, utc_end)
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




# ========================== 4:58 8 jan ====
#👌 ======================== WORKER ASSIGNMENT PROCESS FUNCTION =========================
async def process_worker_assignment(db: AsyncSession, req):
    """
    ======================================================
    WORKER ASSIGNMENT PROCESS (HYBRID CLEAN + DEBUG LOGGING)
    ======================================================
    """

    print("\n\n================= 🟦 START PROCESS ASSIGNMENT (DEBUG MODE ON) =================")

    utc_start, utc_end = ist_day_to_utc_range(req.date)
    now = get_utc_now()

    # print(f"\n📌 DATE RANGE (IST converted → UTC):")
    # print("  → Start:", utc_start)
    # print("  → End:  ", utc_end)

    headers_inserted = 0
    headers_updated = 0
    events_inserted = 0
    errors = []
    # =====================================================
    # 1️⃣ FETCH SOURCE DATA (OC + IRR)
    # =====================================================
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

    # print("\n================= 🟩 MERGE ROWS FOUND =================")
    # for oc in merge_rows:
    #     print({
    #         "awb_no": oc.awb_no,
    #         "hawb": oc.hawb,
    #         "oc_no": oc.oc_no,
    #         "integration": oc.integrate_date_time
    #     })

    # print("\n================= 🟥 IRR ROWS FOUND =================")
    # for irr in irr_rows:
    #     print({
    #         "awb_no": irr.awb,
    #         "hawb": irr.hwb,
    #         "gp_no": irr.gate_pass_no,
    #         "gp_date": irr.gate_pass_issued_date,
    #     })

    # =====================================================
    # 2️⃣ PROCESS OC-MERGE DATA
    # =====================================================
    for oc in merge_rows:

        # print("\n\n---------------------- 🟦 PROCESSING MERGE ROW ----------------------")

        norm_hawb = (oc.hawb or "").strip()

        # ---- HEADER UPSERT (same as your original, correct)
        header_stmt = (
            insert(WorkerAssignmentHeader)
            .values(
                awb_no=oc.awb_no,
                hawb=norm_hawb,
                oc_no=oc.oc_no,
                temp_irm_oc_no=oc.temp_irm_oc_no,
                is_temp_irm_oc=oc.is_temp_irm_oc,
                igp_no=oc.igp_no,
                igp_print_date_time=oc.igp_print_date_time,
                created_at=now,
                updated_at=now
            )
            .on_conflict_do_update(
                index_elements=[WorkerAssignmentHeader.awb_no, text("COALESCE(hawb, '')")],
                set_={
                    "oc_no": insert(WorkerAssignmentHeader).excluded.oc_no,
                    "temp_irm_oc_no": case(
                        (WorkerAssignmentHeader.temp_irm_oc_no.is_(None),
                         insert(WorkerAssignmentHeader).excluded.temp_irm_oc_no),
                        else_=WorkerAssignmentHeader.temp_irm_oc_no
                    ),
                    "igp_no": insert(WorkerAssignmentHeader).excluded.igp_no,
                    "updated_at": now
                }
            )
            .returning(WorkerAssignmentHeader.id, text("CASE WHEN xmax = 0 THEN 1 ELSE 0 END"))
        )

        row = (await db.execute(header_stmt)).first()
        header_id, is_insert = row

        if is_insert:
            headers_inserted += 1
        else:
            headers_updated += 1
        
         # 🔒 IF IRR shipment already exists for this header → SKIP OC shipment
        irr_exists = (await db.execute(
            select(WorkerAssignmentShipment.id).where(
                WorkerAssignmentShipment.assignment_header_id == header_id,
                WorkerAssignmentShipment.from_irr_table == True
            )
        )).first()

        if irr_exists:
            # OC merge shipment is obsolete once IRR exists
            continue

        # ---- OC EVENT UPSERT
        event_stmt = (
            insert(WorkerAssignmentShipment)
            .values(
                assignment_header_id=header_id,
                flight_no=oc.flight_no,
                flight_date=oc.flight_date,
                no_of_pc=oc.no_of_pc,
                weight_in_kgs=oc.weight_in_kgs,
                chg_wgt_in_kg=oc.chg_wgt_in_kg,
                location=oc.location,
                shc=oc.shc,
                irr_codes=oc.irr_codes,
                irregularity_remarks=oc.irregularity_remarks,
                integrate_date_time=oc.integrate_date_time,
                from_irr_table=False,
                created_at=now,
                updated_at=now
            )
            .on_conflict_do_update(
                index_elements=[WorkerAssignmentShipment.assignment_header_id,
                                WorkerAssignmentShipment.integrate_date_time],
                set_={
                    "weight_in_kgs": case(
                        (WorkerAssignmentShipment.weight_in_kgs.is_(None),
                         insert(WorkerAssignmentShipment).excluded.weight_in_kgs),
                        else_=WorkerAssignmentShipment.weight_in_kgs
                    ),
                    "chg_wgt_in_kg": case(
                        (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None),
                         insert(WorkerAssignmentShipment).excluded.chg_wgt_in_kg),
                        else_=WorkerAssignmentShipment.chg_wgt_in_kg
                    ),
                    "no_of_pc": case(
                        (WorkerAssignmentShipment.no_of_pc.is_(None),
                         insert(WorkerAssignmentShipment).excluded.no_of_pc),
                        else_=WorkerAssignmentShipment.no_of_pc
                    ),
                        "location": case(
                                 (
                            or_(
                                WorkerAssignmentShipment.location.is_(None),
                                func.trim(WorkerAssignmentShipment.location) == "",
                                func.trim(WorkerAssignmentShipment.location) == "-"
                            ),
                            insert(WorkerAssignmentShipment).excluded.location
                        ),
                        else_=WorkerAssignmentShipment.location
                    ),
                    "updated_at": now
                }
            )
        )

        await db.execute(event_stmt)
        events_inserted += 1

    # =====================================================
    # 3️⃣ PROCESS IRR DATA   (THE MOST IMPORTANT PART)
    # =====================================================
    for irr in irr_rows:

        # print("\n\n---------------------- 🟥 PROCESSING IRR ROW ----------------------")

        norm_hawb = (irr.hwb or "").strip()
        gp_combo = combine_gate_pass_date_with_time_and_return_utc_datetime(
            irr.gate_pass_issued_date, irr.gate_pass_issued_time
        )

        # ---- HEADER UPSERT (Same as your logic)
        header_stmt = (
            insert(WorkerAssignmentHeader)
            .values(
                awb_no=irr.awb,
                hawb=norm_hawb,
                oc_no=irr.oc_num,
                is_temp_irm_oc=False,
                created_at=now,
                updated_at=now
            )
            .on_conflict_do_update(
                index_elements=[WorkerAssignmentHeader.awb_no, text("COALESCE(hawb, '')")],
                set_={
                    "oc_no": insert(WorkerAssignmentHeader).excluded.oc_no,
                    "is_temp_irm_oc": False,
                    "updated_at": now
                }
            )
            .returning(WorkerAssignmentHeader.id)
        )

        header_id = (await db.execute(header_stmt)).scalar_one()

        # ============================================================
        # ========== IRR EVENT PROCESSING (FINAL BUSINESS RULES) ======
        # ============================================================

        # STEP 1 — Check OC event
        oc_event = (await db.execute(
            select(WorkerAssignmentShipment).where(
                WorkerAssignmentShipment.assignment_header_id == header_id,
                WorkerAssignmentShipment.from_irr_table == False
            )
        )).scalars().first()


                # ============================================================
        # 🛡️ START — IRR EXISTENCE GUARD (DO NOT MOVE THIS)
        # ============================================================
        existing_irr_event = (await db.execute(
            select(WorkerAssignmentShipment).where(
                WorkerAssignmentShipment.assignment_header_id == header_id,
                WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no,
                WorkerAssignmentShipment.from_irr_table == True
            )
        )).scalars().first()

        if existing_irr_event:
            # print(
            #     f"🟨 IRR already exists → IGNORE OC update | "
            #     f"awb={irr.awb}, hawb={irr.hwb}, gp={irr.gate_pass_no}"
            # )
            continue
        # ============================================================
        # 🛡️ END — IRR EXISTENCE GUARD
        # ============================================================

#------------ ---- CASE A: OC EVENT EXISTS
        if oc_event:
            # print("🟦 OC EVENT FOUND → APPLY OC-FIRST LOGIC")
              # 🛡️ GLOBAL GP DUPLICATE GUARD (MUST BE HERE)
            existing_gp_event = (
                await db.execute(
                    select(WorkerAssignmentShipment).where(
                        WorkerAssignmentShipment.assignment_header_id == header_id,
                        WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no,
                        WorkerAssignmentShipment.id != oc_event.id
                    )
                )
            ).scalars().first()

            if existing_gp_event:
                print(
                    f"⚠️ DUPLICATE GP BLOCKED → "
                    f"header={header_id}, gp={irr.gate_pass_no}, "
                    f"existing_event_id={existing_gp_event.id}"
                )

                errors.append({
                    "type": "DUPLICATE_GP_CONFLICT",
                    "awb": irr.awb,
                    "hawb": irr.hwb,
                    "gate_pass_no": irr.gate_pass_no,
                    "existing_event_id": existing_gp_event.id,
                    "action": "oc_update_skipped"
                })

                continue  # 🔴 DO NOT UPDATE OC EVENT
            
            # CASE A1: OC has no gate pass yet → FIRST IRR ARRIVAL
            if oc_event.gate_pass_no is None:
                # print("🟩 FIRST IRR FOR OC → UPDATE OC EVENT WITH NEW GP")
                await db.execute(
                    update(WorkerAssignmentShipment)
                    .where(WorkerAssignmentShipment.id == oc_event.id)
                    .values(

                        # 🔵 Always update gate pass timestamps (correct)
                        gate_pass_no=irr.gate_pass_no,
                        gate_pass_issued_date_time_combo=gp_combo,
                        gate_pass_end_datetime=irr.gate_pass_end_date_time,

                        # 🔵 IRR updates ONLY IF OC has NULL values
                        no_of_pc=case(
                            (WorkerAssignmentShipment.no_of_pc.is_(None), irr.pcs),
                            else_=WorkerAssignmentShipment.no_of_pc
                        ),
                        no_of_pc_recd=case(
                            (WorkerAssignmentShipment.no_of_pc_recd.is_(None), irr.pcs),
                            else_=WorkerAssignmentShipment.no_of_pc_recd
                        ),
                        weight_in_kgs=case(
                            (WorkerAssignmentShipment.weight_in_kgs.is_(None), irr.grg_wt),
                            else_=WorkerAssignmentShipment.weight_in_kgs
                        ),
                        chg_wgt_in_kg=case(
                            (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None), irr.chg_wt),
                            else_=WorkerAssignmentShipment.chg_wgt_in_kg
                        ),
                       location = case(
                            (
                                or_(
                                    WorkerAssignmentShipment.location.is_(None),
                                    func.trim(WorkerAssignmentShipment.location) == "",
                                    func.trim(WorkerAssignmentShipment.location) == "-"
                                ),
                                irr.location_pcs
                            ),
                            else_=WorkerAssignmentShipment.location
                        ),
                        agent_name=case(
                            (WorkerAssignmentShipment.agent_name.is_(None), irr.agent),
                            else_=WorkerAssignmentShipment.agent_name
                        ),
                        customer_name=case(
                            (WorkerAssignmentShipment.customer_name.is_(None), irr.consignee),
                            else_=WorkerAssignmentShipment.customer_name
                        ),
                        release_zone=case(
                            (WorkerAssignmentShipment.release_zone.is_(None), irr.dlv_zone),
                            else_=WorkerAssignmentShipment.release_zone
                        ),

                        updated_at=now
                    )
                )

                continue

            # CASE A2: Same GP number (multiple IRR updates)
            if oc_event.gate_pass_no == irr.gate_pass_no:
                # print("🟩 SAME GP FOR OC → UPDATE OC EVENT")
                await db.execute(
                    update(WorkerAssignmentShipment)
                    .where(WorkerAssignmentShipment.id == oc_event.id)
                    .values(

                        # 🔵 Always update gate pass timestamps (correct)
                        gate_pass_no=irr.gate_pass_no,
                        gate_pass_issued_date_time_combo=gp_combo,
                        gate_pass_end_datetime=irr.gate_pass_end_date_time,

                        # 🔵 IRR updates ONLY IF OC has NULL values
                        no_of_pc=case(
                            (WorkerAssignmentShipment.no_of_pc.is_(None), irr.pcs),
                            else_=WorkerAssignmentShipment.no_of_pc
                        ),
                        no_of_pc_recd=case(
                            (WorkerAssignmentShipment.no_of_pc_recd.is_(None), irr.pcs),
                            else_=WorkerAssignmentShipment.no_of_pc_recd
                        ),
                        weight_in_kgs=case(
                            (WorkerAssignmentShipment.weight_in_kgs.is_(None), irr.grg_wt),
                            else_=WorkerAssignmentShipment.weight_in_kgs
                        ),
                        chg_wgt_in_kg=case(
                            (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None), irr.chg_wt),
                            else_=WorkerAssignmentShipment.chg_wgt_in_kg
                        ),
                        location=case(
                            (WorkerAssignmentShipment.location.is_(None), irr.location_pcs),
                            else_=WorkerAssignmentShipment.location
                        ),
                        agent_name=case(
                            (WorkerAssignmentShipment.agent_name.is_(None), irr.agent),
                            else_=WorkerAssignmentShipment.agent_name
                        ),
                        customer_name=case(
                            (WorkerAssignmentShipment.customer_name.is_(None), irr.consignee),
                            else_=WorkerAssignmentShipment.customer_name
                        ),
                        release_zone=case(
                            (WorkerAssignmentShipment.release_zone.is_(None), irr.dlv_zone),
                            else_=WorkerAssignmentShipment.release_zone
                        ),

                        updated_at=now
                    )
                )

                continue

            # CASE A3: OC already has GP001, IRR brings GP002 → INVALID
            # print("🟥 ERROR: OC EVENT HAS AN EXISTING GATE PASS BUT IRR BRINGS A DIFFERENT ONE!")
            # raise Exception(
            #     f"Invalid IRR: Different gate_pass_no '{irr.gate_pass_no}' "
            #     f"received for OC shipment with existing gate_pass_no '{oc_event.gate_pass_no}'"
            # )
            print("⚠️OC EVENT HAS AN EXISTING GATE PASS BUT IRR BRINGS A DIFFERENT ONE! (INFO ONLY — PROCESS CONTINUES)")
            print( f"Info : received for OC shipment with existing gate_pass_no '{oc_event.gate_pass_no}' get different gate paas no '{irr.gate_pass_no}' on awb '{irr.awb} and hawb '{irr.hwb}''")

            # Collect debug / audit info
            errors.append({
                "type": "GP_MISMATCH",
                "awb": irr.awb,
                "hawb": irr.hwb,
                "existing_gate_pass": oc_event.gate_pass_no,
                "incoming_gate_pass": irr.gate_pass_no,
                "action": "ignored_irr_update",
                "message": "data already created from OC merge and then different data come from IRR with different gatepaas no.| It is may be case of partshipment"
            })

            # Skip this IRR row and continue batch
            continue


        # STEP 2 — No OC event exists → IRR-only shipment
        # print("🟧 NO OC EVENT FOUND → IRR-ONLY SHIPMENT LOGIC")

        # Try to find existing IRR event with same gate_pass_no
        existing_irr_event = (await db.execute(
            select(WorkerAssignmentShipment).where(
                WorkerAssignmentShipment.assignment_header_id == header_id,
                WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no
            )
        )).scalars().first()

        # Case B1: Same GP exists → UPDATE
        if existing_irr_event:
            # print("🟩 SAME IRR GP → UPDATE IRR EVENT")
            await db.execute(
                update(WorkerAssignmentShipment)
                .where(WorkerAssignmentShipment.id == existing_irr_event.id)
                .values(
                    gate_pass_issued_date_time_combo=gp_combo,
                    gate_pass_end_datetime=irr.gate_pass_end_date_time,
                    no_of_pc=irr.pcs,
                    no_of_pc_recd=irr.pcs,
                    weight_in_kgs=irr.grg_wt,
                    chg_wgt_in_kg=irr.chg_wt,
                    location=irr.location_pcs,
                    agent_name=irr.agent,
                    customer_name=irr.consignee,
                    release_zone=irr.dlv_zone,
                    updated_at=now
                )
            )
            continue

        # Case B2: No matching IRR GP → Insert new event (PART SHIPMENT)
        print("🟩 NEW IRR GP → INSERT NEW IRR EVENT (PART SHIPMENT)")

        await db.execute(
            insert(WorkerAssignmentShipment).values(
                assignment_header_id=header_id,
                gate_pass_no=irr.gate_pass_no,
                gate_pass_issued_date_time_combo=gp_combo,
                gate_pass_end_datetime=irr.gate_pass_end_date_time,
                flight_no=irr.flight_no,
                flight_date=irr.flight_date,
                no_of_pc=irr.pcs,
                no_of_pc_recd=irr.pcs,
                weight_in_kgs=irr.grg_wt,
                chg_wgt_in_kg=irr.chg_wt,
                location=irr.location_pcs,
                agent_name=irr.agent,
                customer_name=irr.consignee,
                release_zone=irr.dlv_zone,
                from_irr_table=True,
                created_at=now,
                updated_at=now
            )
        )

    # =====================================================
    # END + COMMIT
    # =====================================================
    await db.commit()

    print("\n================= 🟦 END PROCESS (DEBUG MODE) =================\n\n")

    return {
        "success": True,
        "merge_rows_processed": len(merge_rows),
        "irr_rows_processed": len(irr_rows),
        "headers_inserted": headers_inserted,
        "headers_updated": headers_updated,
        "events_processed": events_inserted,
        "warnings":errors
    }


# async def get_all_worker_assignments_list(db: AsyncSession):
#     query = select(WorkerAssignment).order_by(WorkerAssignment.id.desc())
#     result = await db.execute(query)
#     rows = result.scalars().all()
#     return rows







async def get_all_allowed_users_as_worker(db: AsyncSession) -> list[User]:
    allowed_roles_for_become_worker = ['imp_gp_user']  # Define the allowed role
    
    query = select(User).filter(User.role.in_(allowed_roles_for_become_worker), User.is_active == True)
    
    result = await db.execute(query)
    users = result.scalars().all()

    if not users:
        raise HTTPException(status_code=404, detail="No users found for assignment")
    
    return users


# Get all list of shipment based on assignd to particular worker ==============================
async def get_worker_assignment_lists_by_emp_id(
    db: AsyncSession,
    emp_id: str
) -> list[dict]:
    # ----------------------------------------------------
    # 1️⃣ Validate user
    # ----------------------------------------------------
    user = await db.scalar(
        select(User).where(User.emp_id == emp_id)
    )

    if not user:
        raise HTTPException(404, "User not found")

    if user.role != "imp_gp_user":
        raise HTTPException(403, "User is not authorized")

    # ----------------------------------------------------
    # 2️⃣ Query shipment + header
    # ----------------------------------------------------
    shipment = WorkerAssignmentShipment
    header = WorkerAssignmentHeader

    stmt = (
        select(shipment, header)
        .join(header, shipment.assignment_header_id == header.id)
        .where(shipment.assigned_person == emp_id)
        .where(
            or_(
                shipment.drop_dlv_zone.is_(None),
                func.trim(shipment.drop_dlv_zone) == "",
                func.trim(shipment.drop_dlv_zone) == "-"
            )
        )
        .order_by(shipment.integrate_date_time.desc())
    )

    rows = (await db.execute(stmt)).all()

    # ----------------------------------------------------
    # 3️⃣ Shape response (flat JSON)
    # ----------------------------------------------------
    results = []
    for shipment, header in rows:
        results.append({
                   # REQUIRED IDS
        "header_id": header.id,
        "shipment_id": shipment.id,

        # HEADER FIELDS
        "oc_no": header.oc_no,
        "awb_no": header.awb_no,
        "hawb": header.hawb,
        "temp_irm_oc_no": header.temp_irm_oc_no,
        "is_temp_irm_oc": header.is_temp_irm_oc,

        # SHIPMENT FIELDS
        "gate_pass_no": shipment.gate_pass_no,
        "gate_pass_issued_date_time_combo": shipment.gate_pass_issued_date_time_combo,
        "gate_pass_end_datetime": shipment.gate_pass_end_datetime,

        "assigned_person": shipment.assigned_person,
        "assigned_person_datetime": shipment.assigned_person_datetime,

        "drop_dlv_zone": shipment.drop_dlv_zone,
        "drop_dlv_zone_datetime": shipment.drop_dlv_zone_datetime,

        "integrate_date_time": shipment.integrate_date_time,
        "from_irr_table": shipment.from_irr_table,

        # OPERATIONAL DATA
        "location": shipment.location,
        "no_of_pc": shipment.no_of_pc,
        "weight_in_kgs": shipment.weight_in_kgs,
        "chg_wgt_in_kg": shipment.chg_wgt_in_kg,

        "flight_no": shipment.flight_no,
        "flight_date": shipment.flight_date,

        # TIMESTAMPS
        "created_at": shipment.created_at,
        "updated_at": shipment.updated_at,
        })

    return results


# # ==========Assign a user to the worker assignment table row data =============================
async def assign_user_to_worker_assignment(
    *,
    db: AsyncSession,
    header_id: int,
    shipment_id: int,
    oc_no: str,
    emp_id: str | None,          # None = unassign
    current_user_role: str,
    changed_by: str,
    ip_address: str | None,
    user_agent: str | None,
    device_id: str | None,
):
    try:
        # ─────────────────────────────────────────────
        # 1️⃣ FETCH HEADER
        # ─────────────────────────────────────────────
        header = (
            await db.execute(
                select(WorkerAssignmentHeader)
                .where(WorkerAssignmentHeader.id == header_id)
            )
        ).scalars().first()

        if not header:
            raise HTTPException(404, "Invalid header_id")

        if header.oc_no != oc_no:
            raise HTTPException(400, "OC number mismatch with header")

        # ─────────────────────────────────────────────
        # 2️⃣ FETCH SHIPMENT
        # ─────────────────────────────────────────────
        shipment = (
            await db.execute(
                select(WorkerAssignmentShipment)
                .where(
                    WorkerAssignmentShipment.id == shipment_id,
                    WorkerAssignmentShipment.assignment_header_id == header.id,
                )
            )
        ).scalars().first()

        if not shipment:
            raise HTTPException(404, "Shipment does not belong to this OC")

        old_value = shipment.assigned_person
        now = get_utc_now()

        # ─────────────────────────────────────────────
        # 3️⃣ NO CHANGE → EXIT
        # ─────────────────────────────────────────────
        if emp_id == old_value:
            return True

        # ─────────────────────────────────────────────
        # 4️⃣ UNASSIGN
        # ─────────────────────────────────────────────
        if emp_id is None:
            shipment.assigned_person = None
            shipment.assigned_person_datetime = None
            shipment.updated_at = now

            await log_worker_assignment_audit(
                db=db,
                header=header,
                shipment=shipment,
                field_name="assigned_person",
                old_value=old_value,
                new_value=None,
                changed_by=changed_by,
                changed_by_role=current_user_role,
                ip_address=ip_address,
                device_id=device_id,
                user_agent=user_agent,
                db_action="UPDATE",
                source_action="unassign_user",
            )

            await db.commit()
            return True

        # ─────────────────────────────────────────────
        # 5️⃣ VALIDATE WORKER
        # ─────────────────────────────────────────────
        user = (
            await db.execute(
                select(User).where(
                    User.emp_id == emp_id,
                    User.role == "imp_gp_user",
                    User.is_active.is_(True),
                )
            )
        ).scalars().first()

        if not user:
            raise HTTPException(
                400, f"Worker {emp_id} not found or inactive"
            )

        # ─────────────────────────────────────────────
        # 6️⃣ ASSIGN WORKER
        # ─────────────────────────────────────────────
        shipment.assigned_person = emp_id
        shipment.assigned_person_datetime = now
        shipment.updated_at = now

        await log_worker_assignment_audit(
            db=db,
            header=header,
            shipment=shipment,
            field_name="assigned_person",
            old_value=old_value,
            new_value=emp_id,
            changed_by=changed_by,
            changed_by_role=current_user_role,
            ip_address=ip_address,
            device_id=device_id,
            user_agent=user_agent,
            db_action="UPDATE",
            source_action="assign_user",
        )

        await db.commit()
        return True

    except HTTPException:
        await db.rollback()
        raise

    except Exception:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to assign worker"
        )


#==================== add drop_dlv_zone by assigned user or worker ===============================
async def add_drop_dlv_zone_by_assigned_worker(
    db: AsyncSession,
    *,
    header_id: int,
    shipment_id: int,
    oc_no: str,
    emp_id: str,
    current_user_role: str,
    drop_dlv_zone: str,
    ip_address: str | None = None,
    device_id: str | None = None,
    user_agent: str | None = None,
) -> dict:
    try:
        # ─────────────────────────────────────────────
        # 1️⃣ Fetch HEADER (by ID)
        # ─────────────────────────────────────────────
        header = (
            await db.execute(
                select(WorkerAssignmentHeader)
                .where(WorkerAssignmentHeader.id == header_id)
            )
        ).scalars().first()

        if not header:
            raise HTTPException(404, "Invalid header_id")

        # 🔐 SAFETY: OC must match header
        if header.oc_no != oc_no:
            raise HTTPException(
                status_code=400,
                detail="OC number does not match header"
            )

        # ─────────────────────────────────────────────
        # 2️⃣ Fetch SHIPMENT (by ID + ownership)
        # ─────────────────────────────────────────────
        shipment = (
            await db.execute(
                select(WorkerAssignmentShipment)
                .where(
                    WorkerAssignmentShipment.id == shipment_id,
                    WorkerAssignmentShipment.assignment_header_id == header.id,
                )
            )
        ).scalars().first()

        if not shipment:
            raise HTTPException(
                status_code=404,
                detail="Shipment does not belong to this OC"
            )

        # ─────────────────────────────────────────────
        # 3️⃣ Business validations
        # ─────────────────────────────────────────────
        if not shipment.assigned_person:
            raise HTTPException(
                status_code=400,
                detail="Shipment is not assigned to any worker"
            )

        if shipment.assigned_person != emp_id:
            raise HTTPException(
                status_code=403,
                detail="Shipment is assigned to another worker"
            )

        if shipment.drop_dlv_zone:
            raise HTTPException(
                status_code=400,
                detail="Drop delivery zone already added"
            )

        # ─────────────────────────────────────────────
        # 4️⃣ Update SHIPMENT
        # ─────────────────────────────────────────────
        old_value = shipment.drop_dlv_zone
        now = get_utc_now()

        await db.execute(
            update(WorkerAssignmentShipment)
            .where(WorkerAssignmentShipment.id == shipment.id)
            .values(
                drop_dlv_zone=drop_dlv_zone,
                drop_dlv_zone_datetime=now,
                updated_at=now,
            )
        )

        # ─────────────────────────────────────────────
        # 5️⃣ Audit log (NO COMMIT here)
        # ─────────────────────────────────────────────
        await log_worker_assignment_audit(
            db=db,
            header=header,
            shipment=shipment,
            field_name="drop_dlv_zone",
            old_value=old_value,
            new_value=drop_dlv_zone,
            changed_by=emp_id,
            changed_by_role=current_user_role,
            ip_address=ip_address,
            device_id=device_id,
            user_agent=user_agent,
            db_action="UPDATE",
            source_action="dlv_zone_update",
        )

        # ─────────────────────────────────────────────
        # 6️⃣ Commit once (atomic)
        # ─────────────────────────────────────────────
        await db.commit()

        return {
            "status": "success",
            "message": "Drop delivery zone added successfully"
        }

    except HTTPException:
        await db.rollback()
        raise

    except Exception as e:
        await db.rollback()
        raise HTTPException(
            status_code=500,
            detail="Failed to add drop delivery zone"
        )

# #=========== PAGINATED WORKER ASSIGNMENT DATA WITH FILTERS AND MATRIX COUNTS (NEW)

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

    async def calculate_matrix(base_query):
        shipment = WorkerAssignmentShipment

        # 1️⃣ PURE OC
        pure = base_query.where(
            and_(
                shipment.from_irr_table == False,
                or_(
                    shipment.gate_pass_no.is_(None),
                    func.trim(shipment.gate_pass_no) == ""
                )
            )
        )

        pure_count = (await db.execute(
            select(func.count()).select_from(pure.subquery())
        )).scalar() or 0

        # 2️⃣ TEMP IRM
        temp_irm = base_query.where(
            shipment.from_irr_table == True
        )

        temp_irm_count = (await db.execute(
            select(func.count()).select_from(temp_irm.subquery())
        )).scalar() or 0

        # 3️⃣ GP ALLOTTED
        gp = base_query.where(
            shipment.gate_pass_no.isnot(None),
            func.trim(shipment.gate_pass_no) != ""
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
    # STEP 1 – BUILD BASE QUERY (class based)
    # -----------------------------------------------------
    # -----------------------------------------------------
# STEP 1 – BUILD BASE QUERY (CLASS BASED)
# -----------------------------------------------------
    header = WorkerAssignmentHeader
    shipment = WorkerAssignmentShipment

    filters = WorkerAssignmentFilters(
        shipment_model=shipment,
        status=status,
        startDate=startDate,
        endDate=endDate
    )

    # base_query = filters.apply_all(select(model))



    base_query = (
        select(shipment, header)
        .join(header, shipment.assignment_header_id == header.id)
    )

    base_query = filters.apply_all(base_query)



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
    shipment.gate_pass_no.is_(None),
    shipment.gate_pass_no.asc(),
    header.oc_no.asc()
    )
        .offset(offset)
        .limit(page_size)
    )

    result = await db.execute(paginated_query)
    # records = result.scalars().all()
    rows = result.all()

    # records = [
    #     WorkerAssignmentResponseForWorker.from_orm(shipment, header)
    #     for shipment, header in rows
    # ]

    def safe_convert(value, target_type):
        """Safely convert database values to JSON-serializable Python types"""
        if value is None:
            return None
        return target_type(value)

    # Then use it:
    records = []
    for shipment, header in rows:
        records.append({
             # 🔥 REQUIRED IDS
            "header_id": header.id,
            
            # HEADER FIELDS
            "oc_no": header.oc_no,
            "awb_no": header.awb_no,
            "hawb": header.hawb,
            "temp_irm_oc_no": header.temp_irm_oc_no,
            "is_temp_irm_oc": safe_convert(header.is_temp_irm_oc, bool),

            # SHIPMENT FIELDS
            # "id": safe_convert(shipment.id, int),
            "shipment_id": shipment.id,
            "gate_pass_no": shipment.gate_pass_no,
            "gate_pass_issued_date_time_combo": shipment.gate_pass_issued_date_time_combo,
            "gate_pass_end_datetime": shipment.gate_pass_end_datetime,
            "assigned_person": shipment.assigned_person,
            "assigned_person_datetime": shipment.assigned_person_datetime,
            "drop_dlv_zone": shipment.drop_dlv_zone,
            "drop_dlv_zone_datetime": shipment.drop_dlv_zone_datetime,
            "flight_no": shipment.flight_no,
            "flight_date": shipment.flight_date,
            "location":shipment.location,
            "no_of_pc": safe_convert(shipment.no_of_pc, int),
            "weight_in_kgs": safe_convert(shipment.weight_in_kgs, float),
            "chg_wgt_in_kg" :safe_convert(shipment.chg_wgt_in_kg,float),
            "integrate_date_time":shipment.integrate_date_time,
            "from_irr_table": safe_convert(shipment.from_irr_table, bool),
            "created_at": shipment.created_at,
            "updated_at": shipment.updated_at,
        })
    # -----------------------------------------------------
    # STEP 4 – MATRIX COUNTS
    # -----------------------------------------------------
    # matrix_counts = await calculate_matrix(base_query)

    # -----------------------------------------------------
    # STEP 5 – RETURN RESPONSE
    # -----------------------------------------------------
    return {
        "data": records,
        "success": True,
    "message": "Worker assignments fetched successfully",
    #     "data": [WorkerAssignmentResponseForWorker.model_validate(r) for r in records],

        "pagination": {
          "current_page": int(page),  # 🔥 Convert
        "page_size": int(page_size),  # 🔥 Convert
        "total_records": int(total_records),  # 🔥 Convert
        "total_pages": int(total_pages),  # 🔥 Convert
        "has_previous": bool(page > 1),  # 🔥 Convert
        "has_next": bool(page < total_pages),  # 🔥 Convert
        "previous_page": int(page - 1) if page > 1 else None,
        "next_page": int(page + 1) if page < total_pages else None
        },
        # "matrix_counts": matrix_counts,
        "filters_applied": {
            "status": status,
            "start_date": startDate,
            "end_date": endDate
        }
    }










# 👌====================This is used for search in worker assignment page where I can search by awb hawb gp_no, oc_no, temp_oc -------
async def search_in_worker_assignments(
    db: AsyncSession,
    search_type: str,
    search_value: str
):

    header_fields = {
        "oc_no": WorkerAssignmentHeader.oc_no,
        "awb": WorkerAssignmentHeader.awb_no,
        "hawb": WorkerAssignmentHeader.hawb,
        "temp_oc": WorkerAssignmentHeader.temp_irm_oc_no,
    }

    shipment_fields = {
        "gp_no": WorkerAssignmentShipment.gate_pass_no,
    }
    def model_to_dict(obj):
        return {
            column.name: getattr(obj, column.name)
            for column in obj.__table__.columns
        }


    # ----------------------------------------------------------------
    # 1️⃣ HEADER SEARCH
    # ----------------------------------------------------------------
    if search_type in header_fields:
        column = header_fields[search_type]

        stmt = (
            select(WorkerAssignmentShipment, WorkerAssignmentHeader)
            .join(
                WorkerAssignmentHeader,
                WorkerAssignmentShipment.assignment_header_id == WorkerAssignmentHeader.id
            )
            .where(column == search_value)
        )

    # ----------------------------------------------------------------
    # 2️⃣ SHIPMENT SEARCH
    # ----------------------------------------------------------------
    elif search_type in shipment_fields:
        column = shipment_fields[search_type]

        stmt = (
            select(WorkerAssignmentShipment, WorkerAssignmentHeader)
            .join(
                WorkerAssignmentHeader,
                WorkerAssignmentShipment.assignment_header_id == WorkerAssignmentHeader.id
            )
            .where(func.lower(column).contains(search_value.lower()))
        )

    else:
        return []

    result = await db.execute(stmt)
    rows = result.all()

    response_list = []

    for shipment, header in rows:

        # Convert shipment model → dictionary (ALL columns)
        shipment_dict = model_to_dict(shipment)

        # Add header identity fields manually
        shipment_dict.update({
            "oc_no": header.oc_no,
            "awb_no": header.awb_no,
            "hawb": header.hawb,
            "temp_irm_oc_no": header.temp_irm_oc_no,
        })

        response_list.append(shipment_dict)

    return response_list

# 👌=================== EXPORT WORKER ASSIGNMNET REPORT BASED ON FILTERD (STREAMING) ===================
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
    Works with new multi-level structure (Header + Shipment)
    """

    # Create in-memory buffer
    output = io.BytesIO()
    
    # Create workbook and worksheet
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('Worker Assignments')
    
    # Define formats
    header_format = workbook.add_format({
        'bold': True,
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
        'SHC', 'IRR Codes', 'Irregularity Remarks',
        'Gate Pass No', 'GP Issue Date', 'GP End Date',
        'Assigned Person', 'Assigned Person Name', 'Assigned DateTime',
        'Drop Delivery Zone', 'Drop DLV DateTime',
        'From Source', 'Integrate Date', 'Created At'
    ]
    
    # Write headers
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header, header_format)
    
    # Set column widths
    column_widths = {
        0: 8,   # S.No
        1: 15,  # IGP No
        2: 15,  # OC No
        3: 15,  # Temp IRM OC
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
        14: 15, # SHC
        15: 20, # IRR Codes
        16: 35, # Irregularity Remarks
        17: 18, # Gate Pass No
        18: 18, # GP Issue Date
        19: 18, # GP End Date
        20: 20, # Assigned Person
        21: 25, # Assigned Person Name
        22: 18, # Assigned DateTime
        23: 20, # Drop Delivery Zone
        24: 18, # Drop DLV DateTime
        25: 15, # From Source
        26: 18, # Integrate Date
        27: 18  # Created At
    }
    
    for col, width in column_widths.items():
        worksheet.set_column(col, col, width)
    
    # Freeze header row
    worksheet.freeze_panes(1, 0)
    
    # Parse dates
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    
    # Build base query with new structure
    # ----------------------------------------
    
    # Create alias for User table
    UserAlias = aliased(User)
    
    # 🔑 NEW: Apply filters to WorkerAssignmentShipment model
    filters = WorkerAssignmentFilters(
        shipment_model=WorkerAssignmentShipment,  # ✅ Changed to Shipment model
        status=assignment_status,
        startDate=start_date,
        endDate=end_date
    )

    # 🔑 NEW: Join Header + Shipment + User
    base_query = (
        filters.apply_all(
            select(
                WorkerAssignmentHeader,      # Header data
                WorkerAssignmentShipment,    # Shipment data
                UserAlias.name.label("assigned_person_name")
            )
            .join(
                WorkerAssignmentShipment,
                WorkerAssignmentHeader.id == WorkerAssignmentShipment.assignment_header_id
            )
            .outerjoin(
                UserAlias,
                UserAlias.emp_id == WorkerAssignmentShipment.assigned_person
            )
        )
    )

    # SAME ORDERING AS TABLE VIEW
    # Order by gate_pass_no (from shipment), then oc_no (from header)
    base_query = base_query.order_by(
        WorkerAssignmentShipment.gate_pass_no.is_(None),
        WorkerAssignmentShipment.gate_pass_no.asc(),
        WorkerAssignmentHeader.oc_no.asc()
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
    
    # Helper function to get source value
    def get_source_label(header, shipment):
        """
        Determine source based on header and shipment flags
        """
        if shipment.from_irr_table and not header.temp_irm_oc_no:
            return "IRR"
        if header.temp_irm_oc_no and not shipment.from_irr_table:
            return "IRM"
        if not header.temp_irm_oc_no and not shipment.from_irr_table:
            return "OC MERGE"
        return ""

    # Process in chunks
    row_num = 1
    offset = 0
    
    while True:
        # Fetch chunk asynchronously
        chunk_query = base_query.offset(offset).limit(chunk_size)
        result = await db.execute(chunk_query)
        chunk = result.all()
        
        if not chunk:
            break
        
        # Write chunk to Excel
        # Each row is (header, shipment, assigned_person_name)
        for header, shipment, assigned_person_name in chunk:

            # S.No
            worksheet.write(row_num, 0, row_num, text_center)
            
            # IGP No (from HEADER)
            worksheet.write(row_num, 1, header.igp_no or '', text_format)
            
            # OC No (from HEADER)
            worksheet.write(row_num, 2, header.oc_no or '', text_format)
            
            # Temp IRM OC (from HEADER)
            worksheet.write(row_num, 3, header.temp_irm_oc_no or '', text_format)
            
            # AWB No (from HEADER)
            worksheet.write(row_num, 4, header.awb_no or '', text_format)
            
            # HAWB (from HEADER)
            worksheet.write(row_num, 5, header.hawb or '', text_format)
            
            # Flight No (from SHIPMENT)
            worksheet.write(row_num, 6, shipment.flight_no or '', text_format)
            
            # Flight Date (from SHIPMENT)
            if shipment.flight_date:
                worksheet.write_datetime(row_num, 7, to_ist_no_tz(shipment.flight_date), date_format)
            else:
                worksheet.write(row_num, 7, '', text_format)
            
            # No of Pieces (from SHIPMENT)
            if shipment.no_of_pc is not None:
                worksheet.write_number(row_num, 8, shipment.no_of_pc, integer_format)
            else:
                worksheet.write_blank(row_num, 8, None)
            
            # Weight (KG) (from SHIPMENT)
            if shipment.weight_in_kgs is not None:
                worksheet.write_number(row_num, 9, shipment.weight_in_kgs, number_format)
            else:
                worksheet.write_blank(row_num, 9, None)

            # Chargeable Weight (KG) (from SHIPMENT)
            if shipment.chg_wgt_in_kg is not None:
                worksheet.write_number(row_num, 10, shipment.chg_wgt_in_kg, number_format)
            else:
                worksheet.write_blank(row_num, 10, None)
            
            # Location (from SHIPMENT)
            worksheet.write(row_num, 11, shipment.location or '', text_format)
            
            # Agent Name (from SHIPMENT)
            worksheet.write(row_num, 12, shipment.agent_name or '', text_format)
            
            # Customer Name (from SHIPMENT)
            worksheet.write(row_num, 13, shipment.customer_name or '', text_format)
            
            # SHC (from SHIPMENT)
            worksheet.write(row_num, 14, shipment.shc or '', text_format)
            
            # IRR Codes (from SHIPMENT)
            worksheet.write(row_num, 15, shipment.irr_codes or '', text_format)
            
            # Irregularity Remarks (from SHIPMENT)
            worksheet.write(row_num, 16, shipment.irregularity_remarks or '', text_format)
            
            # Gate Pass No (from SHIPMENT)
            worksheet.write(row_num, 17, shipment.gate_pass_no or '', text_format)
            
            # GP Issue Date (from SHIPMENT)
            if shipment.gate_pass_issued_date_time_combo:
                worksheet.write_datetime(row_num, 18, to_ist_no_tz(shipment.gate_pass_issued_date_time_combo), date_format)
            else:
                worksheet.write(row_num, 18, '', text_format)
            
            # GP End Date (from SHIPMENT)
            if shipment.gate_pass_end_datetime:
                worksheet.write_datetime(row_num, 19, to_ist_no_tz(shipment.gate_pass_end_datetime), date_format)
            else:
                worksheet.write(row_num, 19, '', text_format)
            
            # Assigned Person (from SHIPMENT)
            worksheet.write(row_num, 20, shipment.assigned_person or '', text_format)

            # Assigned Person Name (from User join)
            worksheet.write(row_num, 21, assigned_person_name or '', text_format)
                        
            # Assigned DateTime (from SHIPMENT)
            if shipment.assigned_person_datetime:
                worksheet.write_datetime(row_num, 22, to_ist_no_tz(shipment.assigned_person_datetime), date_format)
            else:
                worksheet.write(row_num, 22, '', text_format)
            
            # Drop Delivery Zone (from SHIPMENT)
            worksheet.write(row_num, 23, shipment.drop_dlv_zone or '', text_format)
            
            # Drop DLV DateTime (from SHIPMENT)
            if shipment.drop_dlv_zone_datetime:
                worksheet.write_datetime(row_num, 24, to_ist_no_tz(shipment.drop_dlv_zone_datetime), date_format)
            else:
                worksheet.write(row_num, 24, '', text_format)
            
            # From Source (using both header and shipment flags)
            worksheet.write(row_num, 25, get_source_label(header, shipment), text_center)
            
            # Integrate Date (from SHIPMENT)
            if shipment.integrate_date_time:
                worksheet.write_datetime(row_num, 26, to_ist_no_tz(shipment.integrate_date_time), date_format)
            else:
                worksheet.write(row_num, 26, '', text_format)
            
            # Created At (from SHIPMENT)
            if shipment.created_at:
                worksheet.write_datetime(row_num, 27, to_ist_no_tz(shipment.created_at), date_format)
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


#👌 =========================  USER / WORKER ASSIGNMENT SUMMARY ============================

async def get_assignment_summary_according_to_assigned_person(
    db: AsyncSession,
    start_utc,
    end_utc,
):
    """
    Operator-wise shipment summary (NEW multi-level structure)

    Date logic:
    COALESCE(
        shipment.integrate_date_time,
        shipment.gate_pass_issued_date_time_combo
    )
    """

    # 🔑 Date fallback logic
    date_field = func.coalesce(
        WorkerAssignmentShipment.integrate_date_time,
        WorkerAssignmentShipment.gate_pass_issued_date_time_combo
    )

    stmt = (
        select(
            WorkerAssignmentShipment.assigned_person.label("operator"),

            # ✅ Assigned count
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.assigned_person.isnot(None),
                            WorkerAssignmentShipment.assigned_person_datetime.isnot(None)
                        ),
                        1
                    )
                )
            ).label("assigned"),

            # ✅ Completed count
            func.count(
                case(
                    (WorkerAssignmentShipment.drop_dlv_zone.isnot(None), 1)
                )
            ).label("completed"),
        )
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentHeader.id == WorkerAssignmentShipment.assignment_header_id
        )
        .where(
            WorkerAssignmentShipment.assigned_person.isnot(None),
            WorkerAssignmentShipment.assigned_person_datetime.isnot(None),
            date_field >= start_utc,
            date_field < end_utc,
        )
        .group_by(WorkerAssignmentShipment.assigned_person)
        .order_by(WorkerAssignmentShipment.assigned_person)
    )

    result = await db.execute(stmt)
    rows = result.all()

    summary = []
    total_assigned = 0
    total_completed = 0

    for row in rows:
        assigned = row.assigned or 0
        completed = row.completed or 0

        performance = round(
            (completed / assigned) * 100, 2
        ) if assigned else 0

        summary.append({
            "operator": row.operator,
            "assigned": assigned,
            "completed": completed,
            "performance": performance,
        })

        total_assigned += assigned
        total_completed += completed

    # ✅ TOTAL ROW
    total_performance = round(
        (total_completed / total_assigned) * 100, 2
    ) if total_assigned else 0

    summary.append({
        "operator": "TOTAL",
        "assigned": total_assigned,
        "completed": total_completed,
        "performance": total_performance,
    })

    return summary

# 👌==================== Assignment summary based on categories like IRR, IRM, OC MERGE ===================



# async def get_assignment_category_summary(
#     db: AsyncSession,
#     start_utc,
#     end_utc,
# ):
#     """
#     Category-wise shipment summary
#     (OC_MERGE / IRM / IRR)
#     """

#     ALL_CATEGORIES = ["OC_MERGE", "IRM", "IRR"]

#     category_case = case(
#         (WorkerAssignmentShipment.from_irr_table.is_(True), "IRR"),
#         (
#             and_(
#                 WorkerAssignmentHeader.temp_irm_oc_no.isnot(None),
#                 WorkerAssignmentHeader.temp_irm_oc_no != ""
#             ),
#             "IRM"
#         ),
#         else_="OC_MERGE"
#     ).label("category")

#     date_field = func.coalesce(
#         WorkerAssignmentShipment.integrate_date_time,
#         WorkerAssignmentShipment.gate_pass_issued_date_time_combo
#     )

#     stmt = (
#         select(
#             category_case,

#             # =========================
#             # BASIC COUNTS
#             # =========================
#             func.count(WorkerAssignmentShipment.id).label("total_data"),

#             func.count(
#                 case((WorkerAssignmentShipment.gate_pass_no.isnot(None), 1))
#             ).label("converted_to_gp"),

#             func.count(
#                 case((WorkerAssignmentShipment.gate_pass_no.is_(None), 1))
#             ).label("gp_not_generated"),

#             # =========================
#             # ASSIGNMENT / DELIVERY
#             # =========================
#             func.count(
#                 case(
#                     (
#                         and_(
#                             WorkerAssignmentShipment.assigned_person.is_(None),
#                             WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
#                         ),
#                         1
#                     )
#                 )
#             ).label("unassigned"),

#             func.count(
#                 case(
#                     (
#                         and_(
#                             WorkerAssignmentShipment.assigned_person.isnot(None),
#                             WorkerAssignmentShipment.drop_dlv_zone.is_(None),
#                             WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
#                         ),
#                         1
#                     )
#                 )
#             ).label("assigned_but_not_dropped_at_lift"),

#             func.count(
#                 case(
#                     (
#                         and_(
#                             WorkerAssignmentShipment.assigned_person.isnot(None),
#                             WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
#                             WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
#                         ),
#                         1
#                     )
#                 )
#             ).label("assigned_and_dropped_at_lift"),

#             # =========================
#             # GATE PASS END
#             # =========================
#             func.count(
#                 case(
#                     (
#                         and_(
#                             WorkerAssignmentShipment.gate_pass_no.isnot(None),
#                             WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None)
#                         ),
#                         1
#                     )
#                 )
#             ).label("gatepass_end_date_present_means_delivered"),

#             func.count(
#                 case(
#                     (
#                         and_(
#                             WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
#                             WorkerAssignmentShipment.assigned_person.isnot(None),
#                             # WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None)
#                         ),
#                         1
#                     )
#                 )
#             ).label("assigned_and_dropped_at_lift"),
#             func.count(
#                 case(
#                     (
#                         and_(
#                             WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
#                             WorkerAssignmentShipment.assigned_person.isnot(None),
#                             WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None)
#                         ),
#                         1
#                     )
#                 )
#             ).label("droped_at_lift_with_gatepass_end_date_present"),

#             # =========================
#             # SLA (4 HOURS)
#             # =========================
#             func.count(
#                 case(
#                     (
#                         and_(
#                             WorkerAssignmentShipment.gate_pass_issued_date_time_combo.isnot(None),
#                             WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None),
#                             func.extract(
#                                 "epoch",
#                                 WorkerAssignmentShipment.gate_pass_end_datetime
#                                 - WorkerAssignmentShipment.gate_pass_issued_date_time_combo
#                             ) <= 14400
#                         ),
#                         1
#                     )
#                 )
#             ).label("delivered_within_defined_hours"),
#         )
#         .join(
#             WorkerAssignmentHeader,
#             WorkerAssignmentHeader.id == WorkerAssignmentShipment.assignment_header_id
#         )
#         .where(
#             date_field >= start_utc,
#             date_field < end_utc
#         )
#         .group_by(category_case)
#     )

#     rows = (await db.execute(stmt)).all()

#     data_map = {row.category: row for row in rows}

#     summary = []
#     for cat in ALL_CATEGORIES:
#         row = data_map.get(cat)

#         summary.append({
#             "category": cat,
#             "total_data": row.total_data if row else 0,
#             "converted_to_gp": row.converted_to_gp if row else 0,
#             "gp_not_generated": row.gp_not_generated if row else 0,
#             "unassigned": row.unassigned if row else 0,
#             "assigned_but_not_dropped_at_lift": row.assigned_but_not_dropped_at_lift if row else 0,
#             "assigned_and_dropped_at_lift": row.assigned_and_dropped_at_lift if row else 0,
#             "gatepass_end_date_present_means_delivered": row.gatepass_end_date_present_means_delivered if row else 0,
#             "droped_at_lift_with_gatepass_end_date_present": row.droped_at_lift_with_gatepass_end_date_present if row else 0,
#             "delivered_within_defined_hours": row.delivered_within_defined_hours if row else 0,
#             "balance_for_delivered": (
#                 row.total_data - row.assigned_and_dropped_at_lift
#                 if row else 0
#             ),
#         })

#     return summary


async def get_assignment_category_summary(
    db: AsyncSession,
    start_utc,
    end_utc,
):
    """
    Category-wise shipment summary
    (OC_MERGE / IRM / IRR)
    """

    ALL_CATEGORIES = ["OC_MERGE", "IRM", "IRR"]

    category_case = case(
        (WorkerAssignmentShipment.from_irr_table.is_(True), "IRR"),
        (
            and_(
                WorkerAssignmentHeader.temp_irm_oc_no.isnot(None),
                WorkerAssignmentHeader.temp_irm_oc_no != ""
            ),
            "IRM"
        ),
        else_="OC_MERGE"
    ).label("category")

    date_field = func.coalesce(
        WorkerAssignmentShipment.integrate_date_time,
        WorkerAssignmentShipment.gate_pass_issued_date_time_combo
    )

    stmt = (
        select(
            category_case,

            # =========================
            # BASIC COUNTS
            # =========================
            func.count(WorkerAssignmentShipment.id).label("total_data"),

            func.count(
                case((WorkerAssignmentShipment.gate_pass_no.isnot(None), 1))
            ).label("converted_to_gp"),

            func.count(
                case((WorkerAssignmentShipment.gate_pass_no.is_(None), 1))
            ).label("gp_not_generated"),

            # =========================
            # ASSIGNMENT / DELIVERY
            # =========================
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.assigned_person.is_(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
                        ),
                        1
                    )
                )
            ).label("unassigned"),

            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.assigned_person.isnot(None),
                            WorkerAssignmentShipment.drop_dlv_zone.is_(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
                        ),
                        1
                    )
                )
            ).label("assigned_but_not_dropped_at_lift"),

            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.assigned_person.isnot(None),
                            WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
                        ),
                        1
                    )
                )
            ).label("assigned_and_dropped_at_lift"),

            # =========================
            # GATE PASS END
            # =========================
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.gate_pass_no.isnot(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None)
                        ),
                        1
                    )
                )
            ).label("gatepass_end_date_present_means_delivered"),

            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
                            WorkerAssignmentShipment.assigned_person.isnot(None),
                            # WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None)
                        ),
                        1
                    )
                )
            ).label("assigned_and_dropped_at_lift"),
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
                            WorkerAssignmentShipment.assigned_person.isnot(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None)
                        ),
                        1
                    )
                )
            ).label("dropped_at_lift_with_gatepass_end_date_present"),

            # =========================
            # SLA (4 HOURS)
            # =========================
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.isnot(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None),
                            func.extract(
                                "epoch",
                                WorkerAssignmentShipment.gate_pass_end_datetime
                                - WorkerAssignmentShipment.gate_pass_issued_date_time_combo
                            ) <= 14400
                        ),
                        1
                    )
                )
            ).label("delivered_within_defined_hours"),
        )
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentHeader.id == WorkerAssignmentShipment.assignment_header_id
        )
        .where(
            # date_field >= start_utc,
            # date_field < end_utc
             or_(
                WorkerAssignmentShipment.integrate_date_time.between(start_utc, end_utc),
                WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(start_utc, end_utc)
            )
        )
        .group_by(category_case)
    )

    rows = (await db.execute(stmt)).all()

    data_map = {row.category: row for row in rows}

    summary = []
    for cat in ALL_CATEGORIES:
        row = data_map.get(cat)

        summary.append({
            "category": cat,
            "total_data": row.total_data if row else 0,
            "converted_to_gp": row.converted_to_gp if row else 0,
            "gp_not_generated": row.gp_not_generated if row else 0,
            "unassigned": row.unassigned if row else 0,
            "assigned_but_not_dropped_at_lift": row.assigned_but_not_dropped_at_lift if row else 0,
            "assigned_and_dropped_at_lift": row.assigned_and_dropped_at_lift if row else 0,
            "gatepass_end_date_present_means_delivered": row.gatepass_end_date_present_means_delivered if row else 0,
            "dropped_at_lift_with_gatepass_end_date_present": row.dropped_at_lift_with_gatepass_end_date_present if row else 0,
            "delivered_within_defined_hours": row.delivered_within_defined_hours if row else 0,
            "balance_for_delivered": (
                row.total_data - row.assigned_and_dropped_at_lift
                if row else 0
            ),
        })

    return summary

async def get_assignment_overall_summary(
    db: AsyncSession,
    start_utc,
    end_utc,
):
    """
    Overall shipment summary (ALL categories combined)
    """

    date_field = func.coalesce(
        WorkerAssignmentShipment.integrate_date_time,
        WorkerAssignmentShipment.gate_pass_issued_date_time_combo
    )

    stmt = (
        select(
            # TOTAL SHIPMENTS
            func.count(WorkerAssignmentShipment.id).label("total_data"),

            # GP GENERATED
            func.count(
                case(
                    (WorkerAssignmentShipment.gate_pass_no.isnot(None), 1)
                )
            ).label("converted_to_gp"),

            # GP NOT GENERATED
            func.count(
                case(
                    (WorkerAssignmentShipment.gate_pass_no.is_(None), 1)
                )
            ).label("gp_not_generated"),

            # ASSIGNED BUT NOT DELIVERED
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.assigned_person.isnot(None),
                            WorkerAssignmentShipment.drop_dlv_zone.is_(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
                        ),
                        1
                    )
                )
            ).label("assigned_but_not_dropped_at_lift"),

            # ASSIGNED AND DELIVERED
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.assigned_person.isnot(None),
                            WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
                             WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
                        ),
                        1
                    )
                )
            ).label("assigned_and_dropped_at_lift"),

            # DELIVERED WITH GP END DATE
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
                        ),
                        1
                    )
                )
            ).label("dropped_at_lift_with_gatepass_end_date_present"),
            func.count(
                case(
                    (
                        and_(  
                            WorkerAssignmentShipment.gate_pass_no.isnot(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None)
                        ),
                        1
                    )
                )
            ).label("gatepass_end_date_present_means_delivered"),
        # 🆕 DELIVERED WITHIN 4 HOURS
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.isnot(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None),
                            func.extract(
                                'epoch',
                                WorkerAssignmentShipment.gate_pass_end_datetime - WorkerAssignmentShipment.gate_pass_issued_date_time_combo
                            ) <= 14400  # 4 hours = 14400 seconds
                        ),
                        1
                    )
                )
            ).label("delivered_within_defined_hours"),
        # 🆕 unassigned
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.assigned_person.is_(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
                        ),
                        1
                    )
                )
            ).label("unassigned"),
             # 🆕 Gatepass End date not present(not delivered ) 
            func.count(
                case(
                    (
                        and_(
                            # WorkerAssignmentShipment.assigned_person.is_(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),
                            WorkerAssignmentShipment.gate_pass_no.isnot(None)
                        ),
                        1
                    )
                )
            ).label("not_gatepass_end_date_but_have_gp_no"),
                         # 🆕 Gatepass End date not present(not delivered ) and how many are unassigned
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.assigned_person.is_(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),
                            WorkerAssignmentShipment.gate_pass_no.isnot(None)
                        ),
                        1
                    )
                )
            ).label("not_gatepass_end_date_but_have_gp_no_and_unassigned"),

                        # 🆕 Gatepass End date not present(not delivered ) and how many are assigned and not drop at lift
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.assigned_person.isnot(None),
                            WorkerAssignmentShipment.drop_dlv_zone.is_(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),
                            WorkerAssignmentShipment.gate_pass_no.isnot(None)
                        ),
                        1
                    )
                )
            ).label("not_gatepass_end_date_but_have_gp_no_and_assigned_notdropatlift"),
                 # 🆕 Gatepass End date not present(not delivered ) and how many are assigned and not drop at lift
            func.count(
                case(
                    (
                        and_(
                            WorkerAssignmentShipment.assigned_person.isnot(None),
                            WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
                            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),
                            WorkerAssignmentShipment.gate_pass_no.isnot(None)
                        ),
                        1
                    )
                )
            ).label("not_gatepass_end_date_but_have_gp_no_and_assigned_dropatlift"),
        )
        .where(
            # date_field >= start_utc,
            # date_field < end_utc
             or_(
                WorkerAssignmentShipment.integrate_date_time.between(start_utc, end_utc),
                WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(start_utc, end_utc)
            )
        )
    )



    row = (await db.execute(stmt)).one()
# ----------- previous -------------------
    # ton_stmt = (
    #     select(
    #         WorkerAssignmentShipment.drop_dlv_zone.label("ton_category"),
    #         func.count(WorkerAssignmentShipment.id).label("count"),
    #     )
    #     .where(
    #         # ✅ SAME business logic written DIRECTLY
    #         WorkerAssignmentShipment.assigned_person.isnot(None),
    #         WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
    #         WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),
    #         WorkerAssignmentShipment.gate_pass_no.isnot(None),

    #         # ✅ SAME date filter you already use
    #         or_(
    #             WorkerAssignmentShipment.integrate_date_time.between(start_utc, end_utc),
    #             WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
    #                 start_utc, end_utc
    #             ),
    #         )
    #     )
    #     .group_by(WorkerAssignmentShipment.drop_dlv_zone)
    # )

    # ton_rows = (await db.execute(ton_stmt)).all()
    # have_gatepass_and_assigned_drop_at_lift_ton_split = {
    #     row.ton_category: row.count
    #     for row in ton_rows
    # }
# -------------------------------------

    ton_stmt = (
    select(
        WorkerAssignmentShipment.drop_dlv_zone.label("ton_category"),

        # COUNT
        func.count(WorkerAssignmentShipment.id).label("shipment_count"),

        # ✅ SUMS
        func.coalesce(func.sum(WorkerAssignmentShipment.no_of_pc), 0).label("total_pcs"),
        func.coalesce(func.sum(WorkerAssignmentShipment.weight_in_kgs), 0).label("total_gross_weight"),
        func.coalesce(func.sum(WorkerAssignmentShipment.chg_wgt_in_kg), 0).label("total_chargeable_weight"),
    )
    .where(
        WorkerAssignmentShipment.assigned_person.isnot(None),
        WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
        WorkerAssignmentShipment.gate_pass_no.isnot(None),
        # WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),

        or_(
            WorkerAssignmentShipment.integrate_date_time.between(start_utc, end_utc),
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
                start_utc, end_utc
            ),
        )
    )
    .group_by(WorkerAssignmentShipment.drop_dlv_zone)
)

    ton_rows = (await db.execute(ton_stmt)).all()

    category_summary = {}
    overall_totals = {
        "shipment_count": 0,
        "total_pcs": 0,
        "total_gross_weight": 0.0,
        "total_chargeable_weight": 0.0,
    }

    for ton_row in ton_rows:
        category_summary[ton_row.ton_category] = {
            "shipment_count": ton_row.shipment_count,
            "total_pcs": int(ton_row.total_pcs),
            "total_gross_weight": float(ton_row.total_gross_weight),
            "total_chargeable_weight": float(ton_row.total_chargeable_weight),
        }

        overall_totals["shipment_count"] += ton_row.shipment_count
        overall_totals["total_pcs"] += ton_row.total_pcs
        overall_totals["total_gross_weight"] += ton_row.total_gross_weight
        overall_totals["total_chargeable_weight"] += ton_row.total_chargeable_weight




    return {
        "total_data": row.total_data,
        "converted_to_gp": row.converted_to_gp,
        "gp_not_generated": row.gp_not_generated,
        "unassigned": row.unassigned,
        "assigned_but_not_dropped_at_lift": row.assigned_but_not_dropped_at_lift,
        "assigned_and_dropped_at_lift": row.assigned_and_dropped_at_lift,
        "gatepass_end_date_present_means_delivered": row.gatepass_end_date_present_means_delivered,
        "delivered_within_defined_hours": row.delivered_within_defined_hours,
        # FIXED: Use the correct label name
        "not_gatepass_end_date_but_have_gp_no_and_assigned_dropatlift": row.not_gatepass_end_date_but_have_gp_no_and_assigned_dropatlift,
        "not_gatepass_end_date_but_have_gp_no_and_assigned_notdropatlift": row.not_gatepass_end_date_but_have_gp_no_and_assigned_notdropatlift,
        "not_gatepass_end_date_but_have_gp_no_and_unassigned": row.not_gatepass_end_date_but_have_gp_no_and_unassigned,
        "not_gatepass_end_date_but_have_gp_no": row.not_gatepass_end_date_but_have_gp_no,
    # 🆕 CATEGORY + TOTAL SUMMARY
    # -------------------------
    "have_gatepass_and_assigned_drop_at_lift_summary": {
        "by_category": category_summary,
        "overall_total": overall_totals
    },
        # ---------
        "dropped_at_lift_with_gatepass_end_date_present": row.dropped_at_lift_with_gatepass_end_date_present,
        "info":"we exclude shipments having gate pass end datetime from assigned and delivered related count",
        "hints": {
        "delivered": "drop_dlv_zone present",
        "assigned": "assigned_person present",
        "unassigned": "assigned_person absent",
        "gross_weight": "weight_in_kgs",
        "chargeable_weight": "chg_wgt_in_kg",
        "pcs": "no_of_pc"
    }
    }


async def get_data_at_user_based_assigned_not_dropped_at_lift_have_gatepass_no(
    db: AsyncSession,
    start_date: str,
    end_date: str,
):
    """
    Worker-wise breakdown for:
    - assigned
    - GP present
    - NOT delivered (gate_pass_end_datetime IS NULL)
    - NOT dropped at lift (drop_dlv_zone IS NULL)`
    """

    # 🔁 Convert IST → UTC using your existing util
    utc_start, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start_date)
    _, utc_end = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end_date)

    # stmt = (
    #     select(
    #         User.id.label("user_id"),
    #         User.name.label("user_name"),
    #         func.count(WorkerAssignmentShipment.id).label("assigned_count"),
    #     )
    #    .join(
    #         User,
    #         User.emp_id == WorkerAssignmentShipment.assigned_person
    #     )
    #     .where(
    #         # Core business conditions
    #         WorkerAssignmentShipment.assigned_person.isnot(None),
    #         WorkerAssignmentShipment.drop_dlv_zone.is_(None),
    #         WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),
    #         WorkerAssignmentShipment.gate_pass_no.isnot(None),

    #         # Date filter (same as summary)
    #         or_(
    #             WorkerAssignmentShipment.integrate_date_time.between(utc_start, utc_end),
    #             WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
    #                 utc_start, utc_end
    #             ),
    #         )
    #     )
    #     .group_by(User.id, User.name)
    #     .order_by(func.count(WorkerAssignmentShipment.id).desc())
    # )

    stmt = (
        select(
            User.id.label("user_id"),
            User.name.label("user_name"),
            User.emp_id.label("emp_id"),

            # count
            func.count(WorkerAssignmentShipment.id).label("assigned_count"),

            # ✅ separate sums
            func.coalesce(
                func.sum(WorkerAssignmentShipment.chg_wgt_in_kg), 0
            ).label("total_chargeable_weight"),

            func.coalesce(
                func.sum(WorkerAssignmentShipment.weight_in_kgs), 0
            ).label("total_gross_weight"),

            func.coalesce(
                func.sum(WorkerAssignmentShipment.no_of_pc), 0
            ).label("total_pcs"),
        )
        .join(
            User,
            User.emp_id == WorkerAssignmentShipment.assigned_person
        )
        .where(
            WorkerAssignmentShipment.assigned_person.isnot(None),
            WorkerAssignmentShipment.drop_dlv_zone.is_(None),
            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),
            WorkerAssignmentShipment.gate_pass_no.isnot(None),

            or_(
                WorkerAssignmentShipment.integrate_date_time.between(utc_start, utc_end),
                WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
                    utc_start, utc_end
                ),
            )
        )
        .group_by(User.id, User.name)
        .order_by(func.count(WorkerAssignmentShipment.id).desc())
    )

    result = await db.execute(stmt)
    rows = result.all()

    return {
        "total_workers": len(rows),
        "data": [
            {
                "user_id": row.user_id,
                "emp_id":row.emp_id,
                "name": row.user_name,
                "assigned_count": row.assigned_count,
                "total_gross_weight":row.total_gross_weight,
                "total_chargeable_weight":row.total_chargeable_weight,
                "total_pcs":row.total_pcs
            }
            for row in rows
        ],
    }




# ===============  Get all shipments of that ton(5 ton , 10 ton 3-ton like drop_dlv_zone) category drill down api service

# async def get_all_shipments_by_ton_category_value_particular_date_range(
#     db: AsyncSession,
#     start_date,
#     end_date,
#     ton_category: str,
# ):
#     """
#     Get all shipments for given TON category + date range
#     """

#     start_utc, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start_date)
#     _, end_utc = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end_date)

#     stmt = (
#         select(WorkerAssignmentShipment)
#         .where(
#             # Zone filter
#             WorkerAssignmentShipment.drop_dlv_zone == ton_category,

#             # Business rules (same as summary)
#             WorkerAssignmentShipment.assigned_person.isnot(None),
#             WorkerAssignmentShipment.gate_pass_no.isnot(None),

#             # Date filter
#             or_(
#                 WorkerAssignmentShipment.integrate_date_time.between(start_utc, end_utc),
#                 WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
#                     start_utc, end_utc
#                 ),
#             ),
#         )
#         .order_by(WorkerAssignmentShipment.gate_pass_no.desc())
#     )

#     result = await db.execute(stmt)

#     return result.scalars().all()

async def get_all_shipments_by_ton_category_value_particular_date_range(
    db: AsyncSession,
    start_date,
    end_date,
    ton_category: str,
):


    start_utc, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start_date)
    _, end_utc = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end_date)

    stmt = (
        select(
            # 🔑 IDs
            WorkerAssignmentShipment.id.label("shipment_id"),
            WorkerAssignmentShipment.assignment_header_id.label("assignment_header_id"),

            # =====================
            # HEADER INFO
            # =====================
            WorkerAssignmentHeader.oc_no.label("oc_no"),
            WorkerAssignmentHeader.awb_no.label("awb"),
            WorkerAssignmentHeader.hawb.label("hawb"),
            WorkerAssignmentHeader.igp_no.label("igp_no"),

            # =====================
            # SHIPMENT INFO
            # =====================
            WorkerAssignmentShipment.no_of_pc.label("pcs"),
            WorkerAssignmentShipment.weight_in_kgs.label("gross_weight"),
            WorkerAssignmentShipment.chg_wgt_in_kg.label("chargeable_weight"),

            WorkerAssignmentShipment.flight_no.label("flight_no"),
            WorkerAssignmentShipment.flight_date.label("flight_date"),

            WorkerAssignmentShipment.drop_dlv_zone.label("drop_dlv_zone"),

            WorkerAssignmentShipment.integrate_date_time.label("integrate_date_time"),
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.label("gp_issue_date_time"),
            WorkerAssignmentShipment.gate_pass_end_datetime.label("gate_pass_end_datetime"),
            WorkerAssignmentShipment.gate_pass_no.label("gate_pass_no"),

            WorkerAssignmentShipment.assigned_person.label("assigned_person"),
        )

        # 🔥 JOIN HEADER
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentShipment.assignment_header_id
            == WorkerAssignmentHeader.id
        )

        .where(
            # ✅ Zone filter
            WorkerAssignmentShipment.drop_dlv_zone == ton_category,

            # ✅ Business rules
            WorkerAssignmentShipment.gate_pass_no.isnot(None),
            WorkerAssignmentShipment.assigned_person.isnot(None),

            # ✅ Date filter
            or_(
                WorkerAssignmentShipment.integrate_date_time.between(start_utc, end_utc),
                WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
                    start_utc, end_utc
                ),
            ),
        )

        .order_by(WorkerAssignmentShipment.gate_pass_no.desc())
    )

    result = await db.execute(stmt)

    # ✅ Convert to dict list
    return result.mappings().all()
# ===================

# ✌️========Get accuracy summary based on time (on unassigned ands assigned shipments):==============

# async def get_shipment_delay_dashboard_data(db):
#     now = get_utc_now()
#     not_assigned_threshold = now - timedelta(minutes=15)
#     assigned_threshold = now - timedelta(minutes=30)

#     # ---------------------------
#     # COUNT QUERIES
#     # ---------------------------
#     not_assigned_count_stmt = select(func.count()).where(
#         WorkerAssignmentShipment.assigned_person.is_(None),
#         WorkerAssignmentShipment.drop_dlv_zone.is_(None),
#         WorkerAssignmentShipment.created_at <= not_assigned_threshold,
#     )

#     assigned_not_delivered_count_stmt = select(func.count()).where(
#         WorkerAssignmentShipment.assigned_person.isnot(None),
#         WorkerAssignmentShipment.drop_dlv_zone.is_(None),
#         WorkerAssignmentShipment.assigned_person_datetime <= assigned_threshold,
#     )

#     not_assigned_count = await db.scalar(not_assigned_count_stmt)
#     assigned_not_delivered_count = await db.scalar(
#         assigned_not_delivered_count_stmt
#     )

#     # ---------------------------
#     # LIST QUERIES
#     # ---------------------------
#     not_assigned_list_stmt = (
#         select(WorkerAssignmentShipment)
#         .where(
#             WorkerAssignmentShipment.assigned_person.is_(None),
#             WorkerAssignmentShipment.drop_dlv_zone.is_(None),
#             WorkerAssignmentShipment.created_at <= not_assigned_threshold,
#         )
#         .order_by(WorkerAssignmentShipment.created_at)
#     )

#     assigned_not_delivered_list_stmt = (
#         select(WorkerAssignmentShipment)
#         .where(
#             WorkerAssignmentShipment.assigned_person.isnot(None),
#             WorkerAssignmentShipment.drop_dlv_zone.is_(None),
#             WorkerAssignmentShipment.assigned_person_datetime <= assigned_threshold,
#         )
#         .order_by(WorkerAssignmentShipment.assigned_person_datetime)
#     )

#     not_assigned_rows = (
#         await db.execute(not_assigned_list_stmt)
#     ).scalars().all()

#     assigned_not_delivered_rows = (
#         await db.execute(assigned_not_delivered_list_stmt)
#     ).scalars().all()

#     return {
#         "counts": {
#             "not_assigned_15_min": not_assigned_count,
#             "assigned_not_delivered_30_min": assigned_not_delivered_count,
#         },
#         "data": {
#             "not_assigned_15_min": not_assigned_rows,
#             "assigned_not_delivered_30_min": assigned_not_delivered_rows,
#         },
#     }


def build_pagination(total: int, limit: int, offset: int):
    return {
        "total_records": total,
        "limit": limit,
        "offset": offset,
        "current_page": (offset // limit) + 1,
        "total_pages": (total + limit - 1) // limit if limit else 0,
        "has_next": offset + limit < total,
        "has_prev": offset > 0,
    }

async def get_shipment_delay_details(
    db,
    sla_type: str,
    lookback_days: int = 3,
    limit: int = 20,
    offset: int = 0,
):
    MAX_LIMIT = 200
    lookback_days = min(lookback_days, 20)
    limit = min(limit, MAX_LIMIT)

    now = get_utc_now()
    data_start_time = now - timedelta(days=lookback_days)

    not_assigned_threshold = now - timedelta(minutes=15)
    assigned_threshold = now - timedelta(minutes=30)

    # ----------------------------
    # SLA: NOT ASSIGNED 15 MIN
    # ----------------------------
    if sla_type == "NOT_ASSIGNED_15_MIN":
        base_filter = [
            WorkerAssignmentShipment.created_at >= data_start_time,
            WorkerAssignmentShipment.assigned_person.is_(None),
            WorkerAssignmentShipment.drop_dlv_zone.is_(None),
            WorkerAssignmentShipment.created_at <= not_assigned_threshold,
        ]

        total_stmt = select(func.count()).where(*base_filter)

        data_stmt = (
            select(
                WorkerAssignmentShipment.id,
                WorkerAssignmentShipment.created_at,
                WorkerAssignmentHeader.awb_no,
                WorkerAssignmentHeader.hawb,
                WorkerAssignmentHeader.oc_no,
            )
            .join(
                WorkerAssignmentHeader,
                WorkerAssignmentHeader.id
                == WorkerAssignmentShipment.assignment_header_id,
            )
            .where(*base_filter)
            .order_by(WorkerAssignmentShipment.created_at)
            .limit(limit)
            .offset(offset)
        )

    # ----------------------------
    # SLA: ASSIGNED NOT DELIVERED 30 MIN
    # ----------------------------
    elif sla_type == "ASSIGNED_NOT_DELIVERED_30_MIN":
        base_filter = [
            WorkerAssignmentShipment.created_at >= data_start_time,
            WorkerAssignmentShipment.assigned_person.isnot(None),
            WorkerAssignmentShipment.assigned_person_datetime.isnot(None),
            WorkerAssignmentShipment.drop_dlv_zone.is_(None),
            WorkerAssignmentShipment.assigned_person_datetime <= assigned_threshold,
        ]

        total_stmt = select(func.count()).where(*base_filter)

        data_stmt = (
            select(
                WorkerAssignmentShipment.id,
                WorkerAssignmentShipment.assigned_person,
                WorkerAssignmentShipment.assigned_person_datetime,
                WorkerAssignmentHeader.awb_no,
                WorkerAssignmentHeader.hawb,
                WorkerAssignmentHeader.oc_no,
            )
            .join(
                WorkerAssignmentHeader,
                WorkerAssignmentHeader.id
                == WorkerAssignmentShipment.assignment_header_id,
            )
            .where(*base_filter)
            .order_by(WorkerAssignmentShipment.assigned_person_datetime)
            .limit(limit)
            .offset(offset)
        )

    else:
        raise ValueError("Invalid SLA type")

    total = await db.scalar(total_stmt)
    rows = (await db.execute(data_stmt)).all()

    return {
        "sla_type": sla_type,
        "pagination": build_pagination(total, limit, offset),
        "records": [dict(r._mapping) for r in rows],
    }


async def get_shipment_delay_dashboard_counts(
    db,
    lookback_days: int = 3,
):
    lookback_days = min(lookback_days, 20)

    now = get_utc_now()
    data_start_time = now - timedelta(days=lookback_days)

    not_assigned_threshold = now - timedelta(minutes=15)
    assigned_threshold = now - timedelta(minutes=30)

    not_assigned_count_stmt = select(func.count()).where(
        WorkerAssignmentShipment.created_at >= data_start_time,
        WorkerAssignmentShipment.assigned_person.is_(None),
        WorkerAssignmentShipment.drop_dlv_zone.is_(None),
        WorkerAssignmentShipment.created_at <= not_assigned_threshold,
    )

    assigned_not_delivered_count_stmt = select(func.count()).where(
        WorkerAssignmentShipment.created_at >= data_start_time,
        WorkerAssignmentShipment.assigned_person.isnot(None),
        WorkerAssignmentShipment.assigned_person_datetime.isnot(None),
        WorkerAssignmentShipment.drop_dlv_zone.is_(None),
        WorkerAssignmentShipment.assigned_person_datetime <= assigned_threshold,
    )

    return {
        "info": {
            "lookback_days": lookback_days,
            "data_from": data_start_time,
            "data_upto": now,
            "sla_rules": {
                "not_assigned_minutes": 15,
                "assigned_not_delivered_minutes": 30,
            },
        },
        "counts": {
            "not_assigned_15_min": await db.scalar(not_assigned_count_stmt),
            "assigned_not_delivered_30_min": await db.scalar(
                assigned_not_delivered_count_stmt
            ),
        },
    }



# GET THE SHIPMENT DETAILS BY EMP ID THOSE WHO ASSIGNED But NOT DROP AT LIFT (those who have gatepass means IRR based data)
async def get_worker_shipment_details_by_empid_which_assigned_not_dropatlift(
   db: AsyncSession,
    emp_id: str,  # ✅ String, not int
    start_date: str,
    end_date: str,
    page: int = 1,
    page_size: int = 20,
):
    """
    Get paginated shipment details for a specific worker by emp_id
    Returns shipment-level records with header info,
    Here Those counts which have gatepass no and not have end gatepass no.
    """
    
    # Convert IST → UTC
    utc_start, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start_date)
    _, utc_end = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end_date)

    # ✅ NO NEED to query User table - use emp_id directly
    # Since emp_id is already the identifier stored in WorkerAssignmentShipment.assigned_person

    # Base query - same conditions as summary
    base_conditions = [
        WorkerAssignmentShipment.assigned_person == emp_id,  # ✅ Direct string comparison
        WorkerAssignmentShipment.drop_dlv_zone.is_(None),
        WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),
        WorkerAssignmentShipment.gate_pass_no.isnot(None),
        or_(
            WorkerAssignmentShipment.integrate_date_time.between(utc_start, utc_end),
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
                utc_start, utc_end
            ),
        )
    ]

    # Count total records
    count_stmt = select(func.count(WorkerAssignmentShipment.id)).where(*base_conditions)
    total_result = await db.execute(count_stmt)
    total_count = total_result.scalar()

    # Get paginated data WITH header info (JOIN)
    offset = (page - 1) * page_size
    
    data_stmt = (
        select(
            WorkerAssignmentShipment,
            WorkerAssignmentHeader
        )
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentHeader.id == WorkerAssignmentShipment.assignment_header_id
        )
        .where(*base_conditions)
        .order_by(WorkerAssignmentShipment.integrate_date_time.desc())
        .offset(offset)
        .limit(page_size)
    )
    
    result = await db.execute(data_stmt)
    rows = result.all()

    return {
        "emp_id": emp_id,  # ✅ Return emp_id as string
        "total_count": total_count,
        "page": page,
        "page_size": page_size,
        "total_pages": (total_count + page_size - 1) // page_size,
        "data": [
            {
                # ===== SHIPMENT LEVEL (event/part shipment) =====
                "shipment_id": shipment.id,
                "shipment_no_of_pc": shipment.no_of_pc,
                "shipment_weight_in_kgs": shipment.weight_in_kgs,
                "shipment_chg_wgt_in_kg": shipment.chg_wgt_in_kg,
                
                # Operational fields
                "gate_pass_no": shipment.gate_pass_no,
                "gate_pass_issued_date_time": shipment.gate_pass_issued_date_time_combo,
                "integrate_date_time": shipment.integrate_date_time,
                "assigned_person": shipment.assigned_person,
                "assigned_person_datetime": shipment.assigned_person_datetime,
                "drop_dlv_zone": shipment.drop_dlv_zone,
                "location": shipment.location,
                "flight_no": shipment.flight_no,
                "flight_date": shipment.flight_date,
                "from_irr_table": shipment.from_irr_table,
                
                # ===== HEADER LEVEL (shipment identity) =====
                "header_id": header.id,
                "oc_no": header.oc_no,
                "awb_no": header.awb_no,
                "hawb": header.hawb,
                "igp_no": header.igp_no,
                "is_temp_irm_oc": header.is_temp_irm_oc,
                "temp_irm_oc_no": header.temp_irm_oc_no,
                
                # Metadata
                "created_at": shipment.created_at,
                "updated_at": shipment.updated_at,
            }
            for shipment, header in rows
        ],
    }


# 👌⚠️⚠️⚠️⚠️⚠️⚠️⚠️⚠️========================= AUTO ASSIGN POM OC SHIPMENT TO PERTICULAR EMPLOYEE =====================

AUTO_ASSIGN_EMP_ID_POM = "523560"

async def auto_assign_pom_shipments(
    db: AsyncSession,
    process_date: date,
    assigned_by: str
):
    """
    Auto-assign unassigned POM shipments
    using hybrid date logic:
    integrate_date_time OR gate_pass_issued_date_time_combo
    """
#   Also check comming emp_id have appropriate role to auto assign POM shipments (role = 'imp_gp_user)

    # check role of user
    user = await db.execute(select(User).where(User.emp_id == AUTO_ASSIGN_EMP_ID_POM))  
    user_obj = user.scalars().first()

    if not user_obj:
        return {
            "total_found": 0,
            "assigned": 0,
            "message": "Auto-assign user not found."
        }

    # ✅ Check if role is exactly "imp_gp_user"
    if user_obj.role != "imp_gp_user":
        return {
            "total_found": 0,
            "assigned": 0,
            "message": "User does not have 'imp_gp_user' role required for auto-assigning POM shipments."
        }

    utc_start, utc_end = ist_day_to_utc_range(process_date)
    now = get_utc_now()

    result = await db.execute(
        select(WorkerAssignmentShipment)
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentShipment.assignment_header_id
            == WorkerAssignmentHeader.id,
        )
        .where(
            # 🔹 POM OC only
            WorkerAssignmentHeader.oc_no.ilike("POM%"),

            # 🔹 Not assigned yet
            WorkerAssignmentShipment.assigned_person.is_(None),

            # 🔹 HYBRID DATE CONDITION (SAME AS REFERENCE)
            or_(
                WorkerAssignmentShipment.integrate_date_time.between(
                    utc_start, utc_end
                ),
                WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
                    utc_start, utc_end
                ),
            ),
        )
    )

    shipments = result.scalars().all()

    for shipment in shipments:
        shipment.assigned_person = AUTO_ASSIGN_EMP_ID_POM
        shipment.assigned_person_datetime = now
        shipment.updated_at = now

    if shipments:
        await db.commit()

    return {
        "total_found": len(shipments),
        "assigned": len(shipments),
    }
