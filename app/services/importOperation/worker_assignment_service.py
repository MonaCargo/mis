

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



from __future__ import annotations
from datetime import datetime, time,date , timedelta
import io
import json
import xlsxwriter
from typing import Any, Dict, Generator, List, Optional, AsyncGenerator
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from numpy import ceil
import numpy as np
import pytz
from sqlalchemy import JSON, and_, case, cast, func, or_, select, text, update
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from app.api.routes.domesticOperation.domestic_xray_report import convert_ist_day_to_utc_range
from app.db.models.importOperation.damage_report import DamageReason, DamageReport, DamageReportReason
from app.db.models.importOperation.imp_truck_in_out_module import ImportGatePass, ImportGatePassAssignment, ImportTruckVisit
from app.db.models.importOperation.import_gp_mismatch_log import ImportGpMismatchLog
from app.db.models.importOperation.import_shipment_hold import ImportShipmentHold
from app.db.models.user import User
from app.services.exportOperation.car_message import ist_date_to_utc_range
from app.services.importOperation.audit_log_worker_assignment import log_worker_assignment_audit
from app.services.importOperation.import_shipment_hold import assert_not_on_hold
from app.utils.common.enums import DamageStatusInWorkerAssignmnet, WorkerAssignmentAuditSource
from app.utils.common.helperFunction import convert_ist_day_to_utc_range_helper, detect_origin_source, get_utc_now
from sqlalchemy.orm import aliased,selectinload
from sqlalchemy.dialects.postgresql import JSONB

from app.db.session import async_session
import re
from sqlalchemy.exc import IntegrityError

from app.db.models.importOperation.oc_merge_gatepass import OcMergeGatePass
from app.db.models.importOperation.import_release_report import IrrReport
from app.db.models.importOperation.worker_assignment import ImportLocationPickup, WorkerAssignmentHeader, WorkerAssignmentShipment
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
        SLA_STATUSES = {"sla_0_to_3_5", "sla_3_5_to_4", "sla_4_above"}

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
        # if status != "all":
        if status != "all" and status not in SLA_STATUSES:   # 🔧✅ guard added
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

    def apply_sla_filter(self, query):
        shipment = self.shipment
        status = self.status

        SLA_STATUSES = {"sla_0_to_3_5", "sla_3_5_to_4", "sla_4_above"}

        if status not in SLA_STATUSES:
            return query  # ← not an SLA request, skip

        # ---------------------------------------------------
        # Base condition: gp_received_datetime MUST be present
        # ---------------------------------------------------
        query = query.where(
            shipment.gp_received_datetime.isnot(None)
        )

        # ---------------------------------------------------
        # Compute diff in hours:
        #   if final_delivery_datetime present → use it
        #   else → use NOW (UTC)
        # ---------------------------------------------------
        effective_end = case(
            (shipment.final_delivery_datetime.isnot(None), shipment.final_delivery_datetime),
            else_=get_utc_now()   # DB-side UTC now
        )

        # PostgreSQL: EPOCH gives total seconds → divide to get hours
        diff_seconds = func.extract(
            "epoch",
            effective_end - shipment.gp_received_datetime
        )
        diff_hours = diff_seconds / 3600.0

        # ---------------------------------------------------
        # Bucket filters
        # ---------------------------------------------------
        if status == "sla_0_to_3_5":
            return query.where(
                and_(
                    diff_hours >= 0,
                    diff_hours < 3.0
                    # diff_hours < 3.5
                )
            )

        if status == "sla_3_5_to_4":
            return query.where(
                and_(
                     # diff_hours >= 3.5,
                    diff_hours >= 3.0,
                    diff_hours <= 4.0
                )
            )

        if status == "sla_4_above":
            return query.where(
                diff_hours > 4.0
            )

        return query  # fallback (should never reach)

    def apply_all(self, query):
        query = self.apply_dlv_zone_filter(query)
        query = self.apply_status_filter(query)
        query = self.apply_date_filter(query)
        query = self.apply_sla_filter(query)   # 🆕
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
# ------------------- OLD -----------------

# async def process_worker_assignment(db: AsyncSession, req):
#     """
#     ======================================================
#     WORKER ASSIGNMENT PROCESS (HYBRID CLEAN + DEBUG LOGGING)
#     ======================================================
#     """

#     print("\n\n================= 🟦 START PROCESS ASSIGNMENT (DEBUG MODE ON) =================")

#     utc_start, utc_end = ist_day_to_utc_range(req.date)
#     now = get_utc_now()

#     # print(f"\n📌 DATE RANGE (IST converted → UTC):")
#     # print("  → Start:", utc_start)
#     # print("  → End:  ", utc_end)

#     headers_inserted = 0
#     headers_updated = 0
#     events_inserted = 0
#     errors = []
#     # =====================================================
#     # 1️⃣ FETCH SOURCE DATA (OC + IRR)
#     # =====================================================
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

#     # print("\n================= 🟩 MERGE ROWS FOUND =================")
#     # for oc in merge_rows:
#     #     print({
#     #         "awb_no": oc.awb_no,
#     #         "hawb": oc.hawb,
#     #         "oc_no": oc.oc_no,
#     #         "integration": oc.integrate_date_time
#     #     })

#     # print("\n================= 🟥 IRR ROWS FOUND =================")
#     # for irr in irr_rows:
#     #     print({
#     #         "awb_no": irr.awb,
#     #         "hawb": irr.hwb,
#     #         "gp_no": irr.gate_pass_no,
#     #         "gp_date": irr.gate_pass_issued_date,
#     #     })

#     # =====================================================
#     # 2️⃣ PROCESS OC-MERGE DATA
#     # =====================================================
#     for oc in merge_rows:

#         # print("\n\n---------------------- 🟦 PROCESSING MERGE ROW ----------------------")

#         norm_hawb = (oc.hawb or "").strip()

#         # ---- HEADER UPSERT (same as your original, correct)
#         header_stmt = (
#             insert(WorkerAssignmentHeader)
#             .values(
#                 awb_no=oc.awb_no,
#                 hawb=norm_hawb,
#                 oc_no=oc.oc_no,
#                 temp_irm_oc_no=oc.temp_irm_oc_no,
#                 is_temp_irm_oc=oc.is_temp_irm_oc,
#                 igp_no=oc.igp_no,
#                 igp_print_date_time=oc.igp_print_date_time,
#                 created_at=now,
#                 updated_at=now
#             )
#             .on_conflict_do_update(
#                 index_elements=[WorkerAssignmentHeader.awb_no, text("COALESCE(hawb, '')")],
#                 set_={
#                     "oc_no": insert(WorkerAssignmentHeader).excluded.oc_no,
#                     "temp_irm_oc_no": case(
#                         (WorkerAssignmentHeader.temp_irm_oc_no.is_(None),
#                          insert(WorkerAssignmentHeader).excluded.temp_irm_oc_no),
#                         else_=WorkerAssignmentHeader.temp_irm_oc_no
#                     ),
#                     "igp_no": insert(WorkerAssignmentHeader).excluded.igp_no,
#                     "updated_at": now
#                 }
#             )
#             .returning(WorkerAssignmentHeader.id, text("CASE WHEN xmax = 0 THEN 1 ELSE 0 END"))
#         )

#         row = (await db.execute(header_stmt)).first()
#         header_id, is_insert = row

#         if is_insert:
#             headers_inserted += 1
#         else:
#             headers_updated += 1
        
#          # 🔒 IF IRR shipment already exists for this header → SKIP OC shipment
#         irr_exists = (await db.execute(
#             select(WorkerAssignmentShipment.id).where(
#                 WorkerAssignmentShipment.assignment_header_id == header_id,
#                 WorkerAssignmentShipment.from_irr_table == True
#             )
#         )).first()

#         if irr_exists:
#             # OC merge shipment is obsolete once IRR exists
#             continue

#         # ---- OC EVENT UPSERT
#         event_stmt = (
#             insert(WorkerAssignmentShipment)
#             .values(
#                 assignment_header_id=header_id,
#                 flight_no=oc.flight_no,
#                 flight_date=oc.flight_date,
#                 no_of_pc=oc.no_of_pc,
#                 weight_in_kgs=oc.weight_in_kgs,
#                 chg_wgt_in_kg=oc.chg_wgt_in_kg,
#                 location=oc.location,
#                 shc=oc.shc,
#                 irr_codes=oc.irr_codes,
#                 irregularity_remarks=oc.irregularity_remarks,
#                 integrate_date_time=oc.integrate_date_time,
#                 from_irr_table=False,
#                 created_at=now,
#                 updated_at=now
#             )
#             .on_conflict_do_update(
#                 index_elements=[WorkerAssignmentShipment.assignment_header_id,
#                                 WorkerAssignmentShipment.integrate_date_time],
#                 set_={
#                     "weight_in_kgs": case(
#                         (WorkerAssignmentShipment.weight_in_kgs.is_(None),
#                          insert(WorkerAssignmentShipment).excluded.weight_in_kgs),
#                         else_=WorkerAssignmentShipment.weight_in_kgs
#                     ),
#                     "chg_wgt_in_kg": case(
#                         (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None),
#                          insert(WorkerAssignmentShipment).excluded.chg_wgt_in_kg),
#                         else_=WorkerAssignmentShipment.chg_wgt_in_kg
#                     ),
#                     "no_of_pc": case(
#                         (WorkerAssignmentShipment.no_of_pc.is_(None),
#                          insert(WorkerAssignmentShipment).excluded.no_of_pc),
#                         else_=WorkerAssignmentShipment.no_of_pc
#                     ),
#                         # "location": case(
#                         #          (
#                         #     or_(
#                         #         WorkerAssignmentShipment.location.is_(None),
#                         #         func.trim(WorkerAssignmentShipment.location) == "",
#                         #         func.trim(WorkerAssignmentShipment.location) == "-"
#                         #     ),
#                         #     insert(WorkerAssignmentShipment).excluded.location
#                         # ),
#                         # else_=WorkerAssignmentShipment.location

#                         "location": case(
#                             (
#                                 and_(
#                                     insert(WorkerAssignmentShipment).excluded.location.isnot(None),
#                                     func.trim(insert(WorkerAssignmentShipment).excluded.location) != "",
#                                     func.trim(insert(WorkerAssignmentShipment).excluded.location) != "-",
#                                     # WorkerAssignmentShipment.location
#                                     # != insert(WorkerAssignmentShipment).excluded.location
#                                 ),
#                                 insert(WorkerAssignmentShipment).excluded.location
#                             ),
#                             else_=WorkerAssignmentShipment.location

#                     ),
#                     "updated_at": now
#                 }
#             )
#         )

#         await db.execute(event_stmt)
#         events_inserted += 1

#     # =====================================================
#     # 3️⃣ PROCESS IRR DATA   (THE MOST IMPORTANT PART)
#     # =====================================================
#     for irr in irr_rows:
#          # 🎯 DEBUG ONLY THIS GATE PASS
#         if str(irr.gate_pass_no) == "25277649":
#             print("\n================ 🎯 DEBUG GP 25277649 ================")
#             print("AWB:", irr.awb)
#             print("HAWB:", irr.hwb)
#             print("GP:", irr.gate_pass_no)
#             print("END_TIME:", irr.gate_pass_end_date_time)
#             print("PCS:", irr.pcs)
#             print("WEIGHT:", irr.grg_wt)

#         # print("\n\n---------------------- 🟥 PROCESSING IRR ROW ----------------------")

#         norm_hawb = (irr.hwb or "").strip()
#         gp_combo = combine_gate_pass_date_with_time_and_return_utc_datetime(
#             irr.gate_pass_issued_date, irr.gate_pass_issued_time
#         )

#         # ---- HEADER UPSERT (Same as your logic)
#         header_stmt = (
#             insert(WorkerAssignmentHeader)
#             .values(
#                 awb_no=irr.awb,
#                 hawb=norm_hawb,
#                 oc_no=irr.oc_num,
#                 is_temp_irm_oc=False,
#                 created_at=now,
#                 updated_at=now
#             )
#             .on_conflict_do_update(
#                 index_elements=[WorkerAssignmentHeader.awb_no, text("COALESCE(hawb, '')")],
#                 set_={
#                     "oc_no": insert(WorkerAssignmentHeader).excluded.oc_no,
#                     "is_temp_irm_oc": False,
#                     "updated_at": now
#                 }
#             )
#             .returning(WorkerAssignmentHeader.id)
#         )

#         header_id = (await db.execute(header_stmt)).scalar_one()

#         # ============================================================
#         # ========== IRR EVENT PROCESSING (FINAL BUSINESS RULES) ======
#         # ============================================================

#         # STEP 1 — Check OC event
#         oc_event = (await db.execute(
#             select(WorkerAssignmentShipment).where(
#                 WorkerAssignmentShipment.assignment_header_id == header_id,
#                 WorkerAssignmentShipment.from_irr_table == False
#             )
#         )).scalars().first()


#                 # ============================================================
#         # 🛡️ START — IRR EXISTENCE GUARD (DO NOT MOVE THIS)
#         # ============================================================
#         existing_irr_event = (await db.execute(
#             select(WorkerAssignmentShipment).where(
#                 WorkerAssignmentShipment.assignment_header_id == header_id,
#                 WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no,
#                 WorkerAssignmentShipment.from_irr_table == True
#             )
#         )).scalars().first()

#         if existing_irr_event:
#             # print(
#             #     f"🟨 IRR already exists → IGNORE OC update | "
#             #     f"awb={irr.awb}, hawb={irr.hwb}, gp={irr.gate_pass_no}"
#             # )
#             if existing_irr_event.gate_pass_end_datetime is None and irr.gate_pass_end_date_time:

#                 await db.execute(
#                     update(WorkerAssignmentShipment)
#                     .where(WorkerAssignmentShipment.id == existing_irr_event.id)
#                     .values(
#                         gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                         gate_pass_issued_date_time_combo=gp_combo,
#                         updated_at=now
#                     )
#                 )

#                 if str(irr.gate_pass_no) == "25276836":
#                     print("✅ FIX: Updated end time on existing IRR")
#             continue
#         # ============================================================
#         # 🛡️ END — IRR EXISTENCE GUARD
#         # ============================================================

# #------------ ---- CASE A: OC EVENT EXISTS
#         if oc_event:
#             # print("🟦 OC EVENT FOUND → APPLY OC-FIRST LOGIC")
#               # 🛡️ GLOBAL GP DUPLICATE GUARD (MUST BE HERE)
#             if oc_event and str(irr.gate_pass_no) == "25277649":
#                 print("✅ OC EVENT FOUND")
#                 print("OC ID:", oc_event.id)
#                 print("OC GP:", oc_event.gate_pass_no)

#             existing_gp_event = (
#                 await db.execute(
#                     select(WorkerAssignmentShipment).where(
#                         WorkerAssignmentShipment.assignment_header_id == header_id,
#                         WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no,
#                         WorkerAssignmentShipment.id != oc_event.id
#                     )
#                 )
#             ).scalars().first()

#             if existing_gp_event:
#                 if str(irr.gate_pass_no) == "25277649":
#                     print("❌ CASE: Global GP Duplicate Blocked")
#                     print("Existing Event ID:", existing_gp_event.id)

#                 print(
#                     f"⚠️ DUPLICATE GP BLOCKED → "
#                     f"header={header_id}, gp={irr.gate_pass_no}, "
#                     f"existing_event_id={existing_gp_event.id}"
#                 )

#                 errors.append({
#                     "type": "DUPLICATE_GP_CONFLICT",
#                     "awb": irr.awb,
#                     "hawb": irr.hwb,
#                     "gate_pass_no": irr.gate_pass_no,
#                     "existing_event_id": existing_gp_event.id,
#                     "action": "oc_update_skipped"
#                 })

#                 continue  # 🔴 DO NOT UPDATE OC EVENT
            
#             # CASE A1: OC has no gate pass yet → FIRST IRR ARRIVAL
#             if oc_event.gate_pass_no is None:
#                 # print("🟩 FIRST IRR FOR OC → UPDATE OC EVENT WITH NEW GP")
#                 if str(irr.gate_pass_no) == "25277649":
#                     print("✅ CASE: First IRR → Updating OC")
#                 # 🫷🫷🫷🫷🫷🫷🫷🫷
#                 if (
#                     irr.location_pcs
#                     and oc_event
#                     and oc_event.location != irr.location_pcs
#                 ):
#                     print(
#                         f"📍 LOCATION OVERRIDE | "
#                         f"AWB={irr.awb} | "
#                         f"OLD={oc_event.location} → NEW={irr.location_pcs}"
#                     )
#                     # 🫷

#                 await db.execute(
#                     update(WorkerAssignmentShipment)
#                     .where(WorkerAssignmentShipment.id == oc_event.id)
#                     .values(

#                         # 🔵 Always update gate pass timestamps (correct)
#                         gate_pass_no=irr.gate_pass_no,
#                         gate_pass_issued_date_time_combo=gp_combo,
#                         gate_pass_end_datetime=irr.gate_pass_end_date_time,

#                         # 🔵 IRR updates ONLY IF OC has NULL values
#                         no_of_pc=case(
#                             (WorkerAssignmentShipment.no_of_pc.is_(None), irr.pcs),
#                             else_=WorkerAssignmentShipment.no_of_pc
#                         ),
#                         no_of_pc_recd=case(
#                             (WorkerAssignmentShipment.no_of_pc_recd.is_(None), irr.pcs),
#                             else_=WorkerAssignmentShipment.no_of_pc_recd
#                         ),
#                         weight_in_kgs=case(
#                             (WorkerAssignmentShipment.weight_in_kgs.is_(None), irr.grg_wt),
#                             else_=WorkerAssignmentShipment.weight_in_kgs
#                         ),
#                         chg_wgt_in_kg=case(
#                             (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None), irr.chg_wt),
#                             else_=WorkerAssignmentShipment.chg_wgt_in_kg
#                         ),
#                     #    location = case(
#                     #         (
#                     #             or_(
#                     #                 WorkerAssignmentShipment.location.is_(None),
#                     #                 func.trim(WorkerAssignmentShipment.location) == "",
#                     #                 func.trim(WorkerAssignmentShipment.location) == "-"
#                     #             ),
#                     #             irr.location_pcs
#                     #         ),
#                     #         else_=WorkerAssignmentShipment.location
#                     #     ),
#                     location = case(
#                             (
#                                 and_(
#                                     # irr.location_pcs.isnot(None),
#                                       irr.location_pcs != None,
#                                     func.trim(irr.location_pcs) != "",
#                                     func.trim(irr.location_pcs) != "-",
#                                     # WorkerAssignmentShipment.location != irr.location_pcs
#                                 ),
#                                 irr.location_pcs
#                             ),
#                             else_=WorkerAssignmentShipment.location
#                         ),

#                         agent_name=case(
#                             (WorkerAssignmentShipment.agent_name.is_(None), irr.agent),
#                             else_=WorkerAssignmentShipment.agent_name
#                         ),
#                         customer_name=case(
#                             (WorkerAssignmentShipment.customer_name.is_(None), irr.consignee),
#                             else_=WorkerAssignmentShipment.customer_name
#                         ),
#                         release_zone=case(
#                             (WorkerAssignmentShipment.release_zone.is_(None), irr.dlv_zone),
#                             else_=WorkerAssignmentShipment.release_zone
#                         ),

#                         updated_at=now
#                     )
#                 )

#                 continue

#             # CASE A2: Same GP number (multiple IRR updates)
#             if oc_event.gate_pass_no == irr.gate_pass_no:
#                 # print("🟩 SAME GP FOR OC → UPDATE OC EVENT")
#                 if str(irr.gate_pass_no) == "25277649":
#                     print("✅ CASE: Same GP → Updating OC")
#                  # 🫷🫷🫷🫷🫷🫷🫷🫷
#                 if (
#                     irr.location_pcs
#                     and oc_event
#                     and oc_event.location != irr.location_pcs
#                 ):
#                     print(
#                         f"📍 LOCATION OVERRIDE | "
#                         f"AWB={irr.awb} | "
#                         f"OLD={oc_event.location} → NEW={irr.location_pcs}"
#                     )
#                     # 🫷

#                 await db.execute(
#                     update(WorkerAssignmentShipment)
#                     .where(WorkerAssignmentShipment.id == oc_event.id)
#                     .values(

#                         # 🔵 Always update gate pass timestamps (correct)
#                         gate_pass_no=irr.gate_pass_no,
#                         gate_pass_issued_date_time_combo=gp_combo,
#                         gate_pass_end_datetime=irr.gate_pass_end_date_time,

#                         # 🔵 IRR updates ONLY IF OC has NULL values
#                         no_of_pc=case(
#                             (WorkerAssignmentShipment.no_of_pc.is_(None), irr.pcs),
#                             else_=WorkerAssignmentShipment.no_of_pc
#                         ),
#                         no_of_pc_recd=case(
#                             (WorkerAssignmentShipment.no_of_pc_recd.is_(None), irr.pcs),
#                             else_=WorkerAssignmentShipment.no_of_pc_recd
#                         ),
#                         weight_in_kgs=case(
#                             (WorkerAssignmentShipment.weight_in_kgs.is_(None), irr.grg_wt),
#                             else_=WorkerAssignmentShipment.weight_in_kgs
#                         ),
#                         chg_wgt_in_kg=case(
#                             (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None), irr.chg_wt),
#                             else_=WorkerAssignmentShipment.chg_wgt_in_kg
#                         ),
#                         # location=case(
#                         #     (WorkerAssignmentShipment.location.is_(None), irr.location_pcs),
#                         #     else_=WorkerAssignmentShipment.location
#                         # ),
#                         location = case(
#                                     (
#                                         and_(
#                                              irr.location_pcs != None,
#                                             func.trim(irr.location_pcs) != "",
#                                             func.trim(irr.location_pcs) != "-",
#                                             # WorkerAssignmentShipment.location != irr.location_pcs
#                                         ),
#                                         irr.location_pcs
#                                     ),
#                                     else_=WorkerAssignmentShipment.location
#                                 ),

#                         agent_name=case(
#                             (WorkerAssignmentShipment.agent_name.is_(None), irr.agent),
#                             else_=WorkerAssignmentShipment.agent_name
#                         ),
#                         customer_name=case(
#                             (WorkerAssignmentShipment.customer_name.is_(None), irr.consignee),
#                             else_=WorkerAssignmentShipment.customer_name
#                         ),
#                         release_zone=case(
#                             (WorkerAssignmentShipment.release_zone.is_(None), irr.dlv_zone),
#                             else_=WorkerAssignmentShipment.release_zone
#                         ),

#                         updated_at=now
#                     )
#                 )

#                 continue

#             # CASE A3: OC already has GP001, IRR brings GP002 → INVALID
#             # print("🟥 ERROR: OC EVENT HAS AN EXISTING GATE PASS BUT IRR BRINGS A DIFFERENT ONE!")
#             # raise Exception(
#             #     f"Invalid IRR: Different gate_pass_no '{irr.gate_pass_no}' "
#             #     f"received for OC shipment with existing gate_pass_no '{oc_event.gate_pass_no}'"
#             # )
#             if str(irr.gate_pass_no) == "25277649":
#                 print("❌ CASE: GP MISMATCH")
#                 print("OC GP:", oc_event.gate_pass_no)
#                 print("IRR GP:", irr.gate_pass_no)
#             print("⚠️OC EVENT HAS AN EXISTING GATE PASS BUT IRR BRINGS A DIFFERENT ONE! (INFO ONLY — PROCESS CONTINUES)")
#             print( f"Info : received for OC shipment with existing gate_pass_no '{oc_event.gate_pass_no}' get different gate paas no '{irr.gate_pass_no}' on awb '{irr.awb} and hawb '{irr.hwb}''")

#             # Collect debug / audit info
#             errors.append({
#                 "type": "GP_MISMATCH",
#                 "awb": irr.awb,
#                 "hawb": irr.hwb,
#                 "existing_gate_pass": oc_event.gate_pass_no,
#                 "incoming_gate_pass": irr.gate_pass_no,
#                 "action": "ignored_irr_update",
#                 "message": "data already created from OC merge and then different data come from IRR with different gatepaas no.| It is may be case of partshipment"
#             })

#             # Skip this IRR row and continue batch
#             continue


#         # STEP 2 — No OC event exists → IRR-only shipment
#         # print("🟧 NO OC EVENT FOUND → IRR-ONLY SHIPMENT LOGIC")

#         # Try to find existing IRR event with same gate_pass_no
#         existing_irr_event = (await db.execute(
#             select(WorkerAssignmentShipment).where(
#                 WorkerAssignmentShipment.assignment_header_id == header_id,
#                 WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no
#             )
#         )).scalars().first()

#         # Case B1: Same GP exists → UPDATE
#         if existing_irr_event:
#             # print("🟩 SAME IRR GP → UPDATE IRR EVENT")
#             # 🫷
#             # 🔍 LOCATION DEBUG (IRR→IRR UPDATE)
#             if (
#                 irr.location_pcs
#                 and existing_irr_event.location
#                 and existing_irr_event.location != irr.location_pcs
#             ):
#                 print(
#                     f"📍 [IRR→IRR] LOCATION CHANGED | "
#                     f"AWB={irr.awb} | "
#                     f"OLD={existing_irr_event.location} → NEW={irr.location_pcs}"
#                 )
# # 🫷
#             await db.execute(
#                 update(WorkerAssignmentShipment)
#                 .where(WorkerAssignmentShipment.id == existing_irr_event.id)
#                 .values(
#                     gate_pass_issued_date_time_combo=gp_combo,
#                     gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                     no_of_pc=irr.pcs,
#                     no_of_pc_recd=irr.pcs,
#                     weight_in_kgs=irr.grg_wt,
#                     chg_wgt_in_kg=irr.chg_wt,
#                     # location=irr.location_pcs,
#                     location = case(
#                         (
#                             and_(
#                                  irr.location_pcs != None,
#                                 func.trim(irr.location_pcs) != "",
#                                 func.trim(irr.location_pcs) != "-",
#                                 # WorkerAssignmentShipment.location != irr.location_pcs
#                             ),
#                             irr.location_pcs
#                         ),
#                         else_=WorkerAssignmentShipment.location
#                     ),

#                     agent_name=irr.agent,
#                     customer_name=irr.consignee,
#                     release_zone=irr.dlv_zone,
#                     updated_at=now
#                 )
#             )
#             continue

#         # Case B2: No matching IRR GP → Insert new event (PART SHIPMENT)
#         print("🟩 NEW IRR GP → INSERT NEW IRR EVENT (PART SHIPMENT)")
#         if str(irr.gate_pass_no) == "25277649":
#             print("🆕 CASE: New IRR Insert")

#         await db.execute(
#             insert(WorkerAssignmentShipment).values(
#                 assignment_header_id=header_id,
#                 gate_pass_no=irr.gate_pass_no,
#                 gate_pass_issued_date_time_combo=gp_combo,
#                 gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                 flight_no=irr.flight_no,
#                 flight_date=irr.flight_date,
#                 no_of_pc=irr.pcs,
#                 no_of_pc_recd=irr.pcs,
#                 weight_in_kgs=irr.grg_wt,
#                 chg_wgt_in_kg=irr.chg_wt,
#                 location=irr.location_pcs,
#                 agent_name=irr.agent,
#                 customer_name=irr.consignee,
#                 release_zone=irr.dlv_zone,
#                 from_irr_table=True,
#                 created_at=now,
#                 updated_at=now
#             )
#         )

#     # =====================================================
#     # END + COMMIT
#     # =====================================================
#     await db.commit()

#     print("\n================= 🟦 END PROCESS (DEBUG MODE) =================\n\n")

#     return {
#         "success": True,
#         "merge_rows_processed": len(merge_rows),
#         "irr_rows_processed": len(irr_rows),
#         "headers_inserted": headers_inserted,
#         "headers_updated": headers_updated,
#         "events_processed": events_inserted,
#         "warnings":errors
#     }

# ------------ NEW ----- 

# ----------------------- New ----------------
def _parse_integrity_error(e: IntegrityError) -> dict:
    """
    Parses PostgreSQL IntegrityError detail string.
    Handles patterns like:
      - Key (oc_no)=(2068979755) already exists.
      - duplicate key value violates unique constraint "uq_worker_assignment_header_oc_no"
    Returns dict with constraint name and duplicate value (if extractable).
    """
    detail = str(e.orig)

    constraint_match = re.search(r'unique constraint "([^"]+)"', detail)
    constraint = constraint_match.group(1) if constraint_match else "unknown_constraint"

    key_match = re.search(r'Key \(([^)]+)\)=\(([^)]+)\)', detail)
    column = key_match.group(1) if key_match else None
    value  = key_match.group(2) if key_match else None

    return {
        "constraint": constraint,
        "column":     column,
        "value":      value,
    }


#✌️ ================= OLD 17-jun 2026 (without part shipment handling) =============================

# async def process_worker_assignment(db: AsyncSession, req):
#     """
#     ======================================================
#     WORKER ASSIGNMENT PROCESS (HYBRID CLEAN + DEBUG LOGGING)
#     ======================================================
#     """
#     print("\n\n================= 🟦 START PROCESS ASSIGNMENT (DEBUG MODE ON) =================")
#     utc_start, utc_end = ist_day_to_utc_range(req.date)
#     now = get_utc_now()

#     headers_inserted = 0
#     headers_updated = 0
#     events_inserted = 0
#     errors = []

#     # =====================================================
#     # 1️⃣ FETCH SOURCE DATA (OC + IRR)
#     # =====================================================
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

#     # =====================================================
#     # 2️⃣ PROCESS OC-MERGE DATA
#     # =====================================================
#     for oc in merge_rows:

#         norm_hawb = (oc.hawb or "").strip()

#         header_stmt = (
#             insert(WorkerAssignmentHeader)
#             .values(
#                 awb_no=oc.awb_no,
#                 hawb=norm_hawb,
#                 oc_no=oc.oc_no,
#                 temp_irm_oc_no=oc.temp_irm_oc_no,
#                 is_temp_irm_oc=oc.is_temp_irm_oc,
#                 igp_no=oc.igp_no,
#                 igp_print_date_time=oc.igp_print_date_time,
#                 created_at=now,
#                 updated_at=now
#             )
#             .on_conflict_do_update(
#                 index_elements=[WorkerAssignmentHeader.awb_no, text("COALESCE(hawb, '')")],
#                 set_={
#                     "oc_no": insert(WorkerAssignmentHeader).excluded.oc_no,
#                     "temp_irm_oc_no": case(
#                         (WorkerAssignmentHeader.temp_irm_oc_no.is_(None), insert(WorkerAssignmentHeader).excluded.temp_irm_oc_no),
#                         else_=WorkerAssignmentHeader.temp_irm_oc_no
#                     ),
#                     "igp_no": insert(WorkerAssignmentHeader).excluded.igp_no,
#                     "updated_at": now
#                 }
#             )
#             .returning(WorkerAssignmentHeader.id, text("CASE WHEN xmax = 0 THEN 1 ELSE 0 END"))
#         )

#         # 🔒 SAVEPOINT — catches duplicate oc_no without killing the whole batch
#         try:
#             sp = await db.begin_nested()
#             row = (await db.execute(header_stmt)).first()
#             await sp.commit()
#         except IntegrityError as e:
#             await sp.rollback()
#             parsed = _parse_integrity_error(e)
#             errors.append({
#                 "type":       "DUPLICATE_OC_NO",
#                 "source":     "OC_MERGE",
#                 "awb":        oc.awb_no,
#                 "hawb":       oc.hawb or "",
#                 "oc_no":      parsed["value"] or oc.oc_no,
#                 "constraint": parsed["constraint"],
#                 "message": (
#                     f"OC No '{parsed['value'] or oc.oc_no}' already assigned to a different "
#                     f"AWB/HAWB. Skipped → AWB={oc.awb_no}, HAWB={oc.hawb or 'N/A'}."
#                 )
#             })
#             continue  # ⛔ skip this OC row, move to next

#         header_id, is_insert = row
#         if is_insert:
#             headers_inserted += 1
#         else:
#             headers_updated += 1

#         # 🔒 IF IRR shipment already exists for this header → SKIP OC shipment
#         irr_exists = (await db.execute(
#             select(WorkerAssignmentShipment.id).where(
#                 WorkerAssignmentShipment.assignment_header_id == header_id,
#                 WorkerAssignmentShipment.from_irr_table == True
#             )
#         )).first()

#         if irr_exists:
#             continue

#         # ---- OC EVENT UPSERT
#         event_stmt = (
#             insert(WorkerAssignmentShipment)
#             .values(
#                 assignment_header_id=header_id,
#                 flight_no=oc.flight_no,
#                 flight_date=oc.flight_date,
#                 no_of_pc=oc.no_of_pc,
#                 weight_in_kgs=oc.weight_in_kgs,
#                 chg_wgt_in_kg=oc.chg_wgt_in_kg,
#                 location=oc.location,
#                 shc=oc.shc,
#                 irr_codes=oc.irr_codes,
#                 irregularity_remarks=oc.irregularity_remarks,
#                 integrate_date_time=oc.integrate_date_time,
#                 from_irr_table=False,
#                 created_at=now,
#                 updated_at=now
#             )
#             .on_conflict_do_update(
#                 index_elements=[WorkerAssignmentShipment.assignment_header_id, WorkerAssignmentShipment.integrate_date_time],
#                 set_={
#                     "weight_in_kgs": case(
#                         (WorkerAssignmentShipment.weight_in_kgs.is_(None), insert(WorkerAssignmentShipment).excluded.weight_in_kgs),
#                         else_=WorkerAssignmentShipment.weight_in_kgs
#                     ),
#                     "chg_wgt_in_kg": case(
#                         (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None), insert(WorkerAssignmentShipment).excluded.chg_wgt_in_kg),
#                         else_=WorkerAssignmentShipment.chg_wgt_in_kg
#                     ),
#                     "no_of_pc": case(
#                         (WorkerAssignmentShipment.no_of_pc.is_(None), insert(WorkerAssignmentShipment).excluded.no_of_pc),
#                         else_=WorkerAssignmentShipment.no_of_pc
#                     ),
#                     "location": case(
#                         (
#                             and_(
#                                 insert(WorkerAssignmentShipment).excluded.location.isnot(None),
#                                 func.trim(insert(WorkerAssignmentShipment).excluded.location) != "",
#                                 func.trim(insert(WorkerAssignmentShipment).excluded.location) != "-",
#                             ),
#                             insert(WorkerAssignmentShipment).excluded.location
#                         ),
#                         else_=WorkerAssignmentShipment.location
#                     ),
#                     "updated_at": now
#                 }
#             )
#         )

#         await db.execute(event_stmt)
#         events_inserted += 1

#     # =====================================================
#     # 3️⃣ PROCESS IRR DATA
#     # =====================================================
#     for irr in irr_rows:

#         # 🎯 DEBUG ONLY THIS GATE PASS
#         if str(irr.gate_pass_no) == "25277649":
#             print("\n================ 🎯 DEBUG GP 25277649 ================")
#             print("AWB:", irr.awb)
#             print("HAWB:", irr.hwb)
#             print("GP:", irr.gate_pass_no)
#             print("END_TIME:", irr.gate_pass_end_date_time)
#             print("PCS:", irr.pcs)
#             print("WEIGHT:", irr.grg_wt)

#         norm_hawb = (irr.hwb or "").strip()
#         gp_combo = combine_gate_pass_date_with_time_and_return_utc_datetime(
#             irr.gate_pass_issued_date,
#             irr.gate_pass_issued_time
#         )

#         # 🆕 Segregation datetime — same pattern as gate pass combo
#         seg_combo = None
#         if irr.segregation_date and irr.segregation_time:
#             try:
#                 seg_combo = combine_gate_pass_date_with_time_and_return_utc_datetime(
#                     irr.segregation_date,
#                     irr.segregation_time
#                 )
#             except Exception as e:
#                 print(f"⚠️ Failed to combine segregation datetime for GP={irr.gate_pass_no}: {e}")
#                 seg_combo = None

#         header_stmt = (
#             insert(WorkerAssignmentHeader)
#             .values(
#                 awb_no=irr.awb,
#                 hawb=norm_hawb,
#                 oc_no=irr.oc_num,
#                 is_temp_irm_oc=False,
#                 created_at=now,
#                 updated_at=now
#             )
#             .on_conflict_do_update(
#                 index_elements=[WorkerAssignmentHeader.awb_no, text("COALESCE(hawb, '')")],
#                 set_={
#                     "oc_no":          insert(WorkerAssignmentHeader).excluded.oc_no,
#                     "is_temp_irm_oc": False,
#                     "updated_at":     now
#                 }
#             )
#             .returning(WorkerAssignmentHeader.id)
#         )

#         # 🔒 SAVEPOINT — catches duplicate oc_no without killing the whole batch
#         try:
#             sp = await db.begin_nested()
#             header_id = (await db.execute(header_stmt)).scalar_one()
#             await sp.commit()
#         except IntegrityError as e:
#             await sp.rollback()
#             parsed = _parse_integrity_error(e)
#             errors.append({
#                 "type":       "DUPLICATE_OC_NO",
#                 "source":     "IRR",
#                 "awb":        irr.awb,
#                 "hawb":       irr.hwb or "",
#                 "gate_pass":  irr.gate_pass_no,
#                 "oc_no":      parsed["value"] or irr.oc_num,
#                 "constraint": parsed["constraint"],
#                 "message": (
#                     f"OC No '{parsed['value'] or irr.oc_num}' already assigned to a different "
#                     f"AWB/HAWB. Skipped → AWB={irr.awb}, HAWB={irr.hwb or 'N/A'}, "
#                     f"GP={irr.gate_pass_no}."
#                 )
#             })
#             continue  # ⛔ skip this IRR row, move to next

#         # ============================================================
#         # ========== IRR EVENT PROCESSING (FINAL BUSINESS RULES) =====
#         # ============================================================

#         # STEP 1 — Check OC event
#         oc_event = (await db.execute(
#             select(WorkerAssignmentShipment).where(
#                 WorkerAssignmentShipment.assignment_header_id == header_id,
#                 WorkerAssignmentShipment.from_irr_table == False
#             )
#         )).scalars().first()

#         # ============================================================
#         # 🛡️ START — IRR EXISTENCE GUARD (DO NOT MOVE THIS)
#         # ============================================================
#         existing_irr_event = (await db.execute(
#             select(WorkerAssignmentShipment).where(
#                 WorkerAssignmentShipment.assignment_header_id == header_id,
#                 WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no,
#                 WorkerAssignmentShipment.from_irr_table == True
#             )
#         )).scalars().first()

#         if existing_irr_event:
#             if existing_irr_event.gate_pass_end_datetime is None and irr.gate_pass_end_date_time:
#                 await db.execute(
#                     update(WorkerAssignmentShipment)
#                     .where(WorkerAssignmentShipment.id == existing_irr_event.id)
#                     .values(
#                         gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                         gate_pass_issued_date_time_combo=gp_combo,
#                         updated_at=now
#                     )
#                 )
#                 if str(irr.gate_pass_no) == "25276836":
#                     print("✅ FIX: Updated end time on existing IRR")

#             # 🆕 SAME PATTERN — only fill if NULL
#             # 🆕 MERGED PATCH — segregation + boe_no in ONE update trip
#             patch_segregation = existing_irr_event.segregation_datetime is None and seg_combo
#             patch_boe_no      = existing_irr_event.boe_no is None and irr.boe_num
#             patch_dlv_zone     = existing_irr_event.dlv_zone_from_irr is None and irr.dlv_zone  # 🆕

#             if patch_segregation or patch_boe_no or patch_dlv_zone:  # 🆕 add patch_dlv_zone:
#                 await db.execute(
#                     update(WorkerAssignmentShipment)
#                     .where(WorkerAssignmentShipment.id == existing_irr_event.id)
#                     .values(
#                         # 🟢 Only overwrite segregation if it was NULL
#                         segregation_datetime=case(
#                             (WorkerAssignmentShipment.segregation_datetime.is_(None), seg_combo),
#                             else_=WorkerAssignmentShipment.segregation_datetime
#                         ),
#                         # 🟢 Only overwrite boe_no if it was NULL
#                         boe_no=case(
#                             (WorkerAssignmentShipment.boe_no.is_(None), irr.boe_num),
#                             else_=WorkerAssignmentShipment.boe_no
#                         ),
#                           dlv_zone_from_irr=case(           # 🆕
#                          (WorkerAssignmentShipment.dlv_zone_from_irr.is_(None), irr.dlv_zone),
#                             else_=WorkerAssignmentShipment.dlv_zone_from_irr
#                         ),
#                         updated_at=now
#                     )
#                 )
#             continue

#         # ============================================================
#         # 🛡️ END — IRR EXISTENCE GUARD
#         # ============================================================

#         # ---- CASE A: OC EVENT EXISTS
#         if oc_event:

#             if oc_event and str(irr.gate_pass_no) == "25277649":
#                 print("✅ OC EVENT FOUND")
#                 print("OC ID:", oc_event.id)
#                 print("OC GP:", oc_event.gate_pass_no)

#             existing_gp_event = (
#                 await db.execute(
#                     select(WorkerAssignmentShipment).where(
#                         WorkerAssignmentShipment.assignment_header_id == header_id,
#                         WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no,
#                         WorkerAssignmentShipment.id != oc_event.id
#                     )
#                 )
#             ).scalars().first()

#             if existing_gp_event:
#                 if str(irr.gate_pass_no) == "25277649":
#                     print("❌ CASE: Global GP Duplicate Blocked")
#                     print("Existing Event ID:", existing_gp_event.id)
#                     print(
#                         f"⚠️ DUPLICATE GP BLOCKED → "
#                         f"header={header_id}, gp={irr.gate_pass_no}, "
#                         f"existing_event_id={existing_gp_event.id}"
#                     )
#                 errors.append({
#                     "type":              "DUPLICATE_GP_CONFLICT",
#                     "awb":               irr.awb,
#                     "hawb":              irr.hwb,
#                     "gate_pass_no":      irr.gate_pass_no,
#                     "existing_event_id": existing_gp_event.id,
#                     "action":            "oc_update_skipped"
#                 })
#                 continue  # 🔴 DO NOT UPDATE OC EVENT

#             # CASE A1: OC has no gate pass yet → FIRST IRR ARRIVAL
#             if oc_event.gate_pass_no is None:
#                 if str(irr.gate_pass_no) == "25277649":
#                     print("✅ CASE: First IRR → Updating OC")
#                 # if (
#                 #     irr.location_pcs and oc_event and
#                 #     oc_event.location != irr.location_pcs
#                 # ):
#                 #     print(
#                 #         f"📍 LOCATION OVERRIDE | "
#                 #         f"AWB={irr.awb} | "
#                 #         f"OLD={oc_event.location} → NEW={irr.location_pcs}"
#                 #     )
#                 await db.execute(
#                     update(WorkerAssignmentShipment)
#                     .where(WorkerAssignmentShipment.id == oc_event.id)
#                     .values(
#                         gate_pass_no=irr.gate_pass_no,
#                         gate_pass_issued_date_time_combo=gp_combo,
#                         gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                         no_of_pc=case(
#                             (WorkerAssignmentShipment.no_of_pc.is_(None), irr.pcs),
#                             else_=WorkerAssignmentShipment.no_of_pc
#                         ),
#                         no_of_pc_recd=case(
#                             (WorkerAssignmentShipment.no_of_pc_recd.is_(None), irr.pcs),
#                             else_=WorkerAssignmentShipment.no_of_pc_recd
#                         ),
#                         weight_in_kgs=case(
#                             (WorkerAssignmentShipment.weight_in_kgs.is_(None), irr.grg_wt),
#                             else_=WorkerAssignmentShipment.weight_in_kgs
#                         ),
#                         chg_wgt_in_kg=case(
#                             (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None), irr.chg_wt),
#                             else_=WorkerAssignmentShipment.chg_wgt_in_kg
#                         ),
#                         location=case(
#                             (
#                                 and_(
#                                     irr.location_pcs != None,
#                                     func.trim(irr.location_pcs) != "",
#                                     func.trim(irr.location_pcs) != "-",
#                                 ),
#                                 irr.location_pcs
#                             ),
#                             else_=WorkerAssignmentShipment.location
#                         ),
#                         agent_name=case(
#                             (WorkerAssignmentShipment.agent_name.is_(None), irr.agent),
#                             else_=WorkerAssignmentShipment.agent_name
#                         ),
#                         customer_name=case(
#                             (WorkerAssignmentShipment.customer_name.is_(None), irr.consignee),
#                             else_=WorkerAssignmentShipment.customer_name
#                         ),
#                         release_zone=case(
#                             (WorkerAssignmentShipment.release_zone.is_(None), irr.dlv_zone),
#                             else_=WorkerAssignmentShipment.release_zone
#                         ),

#                         # 🆕 ADD THIS
#                         segregation_datetime=case(
#                             (WorkerAssignmentShipment.segregation_datetime.is_(None), seg_combo),
#                             else_=WorkerAssignmentShipment.segregation_datetime
#                         ),
#                         # 🆕 ADD THIS
#                         boe_no=case(
#                             (WorkerAssignmentShipment.boe_no.is_(None), irr.boe_num),
#                             else_=WorkerAssignmentShipment.boe_no
#                         ),
#                        dlv_zone_from_irr=case(
#                         (WorkerAssignmentShipment.dlv_zone_from_irr.is_(None), irr.dlv_zone),
#                         else_=WorkerAssignmentShipment.dlv_zone_from_irr
#                     ),
#                         updated_at=now
#                     )
#                 )
#                 continue

#             # CASE A2: Same GP number (multiple IRR updates)
#             if oc_event.gate_pass_no == irr.gate_pass_no:
#                 if str(irr.gate_pass_no) == "25277649":
#                     print("✅ CASE: Same GP → Updating OC")
#                 # if (
#                 #     irr.location_pcs and oc_event and
#                 #     oc_event.location != irr.location_pcs
#                 # ):
#                 #     print(
#                 #         f"📍 LOCATION OVERRIDE | "
#                 #         f"AWB={irr.awb} | "
#                 #         f"OLD={oc_event.location} → NEW={irr.location_pcs}"
#                 #     )
#                 await db.execute(
#                     update(WorkerAssignmentShipment)
#                     .where(WorkerAssignmentShipment.id == oc_event.id)
#                     .values(
#                         gate_pass_no=irr.gate_pass_no,
#                         gate_pass_issued_date_time_combo=gp_combo,
#                         gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                         no_of_pc=case(
#                             (WorkerAssignmentShipment.no_of_pc.is_(None), irr.pcs),
#                             else_=WorkerAssignmentShipment.no_of_pc
#                         ),
#                         no_of_pc_recd=case(
#                             (WorkerAssignmentShipment.no_of_pc_recd.is_(None), irr.pcs),
#                             else_=WorkerAssignmentShipment.no_of_pc_recd
#                         ),
#                         weight_in_kgs=case(
#                             (WorkerAssignmentShipment.weight_in_kgs.is_(None), irr.grg_wt),
#                             else_=WorkerAssignmentShipment.weight_in_kgs
#                         ),
#                         chg_wgt_in_kg=case(
#                             (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None), irr.chg_wt),
#                             else_=WorkerAssignmentShipment.chg_wgt_in_kg
#                         ),
#                         location=case(
#                             (
#                                 and_(
#                                     irr.location_pcs != None,
#                                     func.trim(irr.location_pcs) != "",
#                                     func.trim(irr.location_pcs) != "-",
#                                 ),
#                                 irr.location_pcs
#                             ),
#                             else_=WorkerAssignmentShipment.location
#                         ),
#                         agent_name=case(
#                             (WorkerAssignmentShipment.agent_name.is_(None), irr.agent),
#                             else_=WorkerAssignmentShipment.agent_name
#                         ),
#                         customer_name=case(
#                             (WorkerAssignmentShipment.customer_name.is_(None), irr.consignee),
#                             else_=WorkerAssignmentShipment.customer_name
#                         ),
#                         release_zone=case(
#                             (WorkerAssignmentShipment.release_zone.is_(None), irr.dlv_zone),
#                             else_=WorkerAssignmentShipment.release_zone
#                         ),
#                         # 🆕 ADD THIS
#                         segregation_datetime=case(
#                             (WorkerAssignmentShipment.segregation_datetime.is_(None), seg_combo),
#                             else_=WorkerAssignmentShipment.segregation_datetime
#                         ),
#                         # 🆕 ADD THIS
#                         boe_no=case(
#                             (WorkerAssignmentShipment.boe_no.is_(None), irr.boe_num),
#                             else_=WorkerAssignmentShipment.boe_no
#                         ),

#                         dlv_zone_from_irr=case(
#                         (WorkerAssignmentShipment.dlv_zone_from_irr.is_(None), irr.dlv_zone),
#                         else_=WorkerAssignmentShipment.dlv_zone_from_irr
#                     ),

#                         updated_at=now
#                     )
#                 )
#                 continue

#             # CASE A3: OC already has GP001, IRR brings GP002 → GP MISMATCH
#             if str(irr.gate_pass_no) == "25277649":
#                 print("❌ CASE: GP MISMATCH")
#                 print("OC GP:", oc_event.gate_pass_no)
#                 print("IRR GP:", irr.gate_pass_no)
#                 print("⚠️ OC EVENT HAS AN EXISTING GATE PASS BUT IRR BRINGS A DIFFERENT ONE! (INFO ONLY — PROCESS CONTINUES)")
#                 print(
#                     f"Info : received for OC shipment with existing gate_pass_no '{oc_event.gate_pass_no}' "
#                     f"get different gate pass no '{irr.gate_pass_no}' on awb '{irr.awb}' and hawb '{irr.hwb}'"
#                 )
#                 # Here we save all gp mismatch data in a table and show for visibility
#             await db.execute(
#                 pg_insert(ImportGpMismatchLog)
#                 .values(
#                     assignment_header_id=header_id,
#                     awb_no=irr.awb,
#                     hawb=irr.hwb,
#                     existing_gate_pass=oc_event.gate_pass_no,
#                     incoming_gate_pass=irr.gate_pass_no,
#                     gp_issued_datetime=gp_combo,                 # available here
#                     integrate_date_time=oc_event.integrate_date_time,  # OC event's integrate time
#                     created_at=now,
#                 )
#                 .on_conflict_do_nothing(
#                     constraint="uq_gp_mismatch_awb_existing_incoming"
#                 )
#             )
#             errors.append({
#                 "type":               "GP_MISMATCH",
#                 "awb":                irr.awb,
#                 "hawb":               irr.hwb,
#                 "existing_gate_pass": oc_event.gate_pass_no,
#                 "incoming_gate_pass": irr.gate_pass_no,
#                 "action":             "ignored_irr_update",
#                 "message":            "data already created from OC merge and then different data come from IRR with different gate pass no. | It may be a case of part shipment"
#             })
#             continue

#         # STEP 2 — No OC event exists → IRR-only shipment
#         existing_irr_event = (await db.execute(
#             select(WorkerAssignmentShipment).where(
#                 WorkerAssignmentShipment.assignment_header_id == header_id,
#                 WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no
#             )
#         )).scalars().first()

#         # Case B1: Same GP exists → UPDATE
#         if existing_irr_event:
#             if (
#                 irr.location_pcs and existing_irr_event.location and
#                 existing_irr_event.location != irr.location_pcs
#             ):
#                 print(
#                     f"📍 [IRR→IRR] LOCATION CHANGED | "
#                     f"AWB={irr.awb} | "
#                     f"OLD={existing_irr_event.location} → NEW={irr.location_pcs}"
#                 )
#             await db.execute(
#                 update(WorkerAssignmentShipment)
#                 .where(WorkerAssignmentShipment.id == existing_irr_event.id)
#                 .values(
#                     gate_pass_issued_date_time_combo=gp_combo,
#                     gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                     no_of_pc=irr.pcs,
#                     no_of_pc_recd=irr.pcs,
#                     weight_in_kgs=irr.grg_wt,
#                     chg_wgt_in_kg=irr.chg_wt,
#                     location=case(
#                         (
#                             and_(
#                                 irr.location_pcs != None,
#                                 func.trim(irr.location_pcs) != "",
#                                 func.trim(irr.location_pcs) != "-",
#                             ),
#                             irr.location_pcs
#                         ),
#                         else_=WorkerAssignmentShipment.location
#                     ),
#                     agent_name=irr.agent,
#                     customer_name=irr.consignee,
#                     release_zone=irr.dlv_zone,
#                     segregation_datetime=seg_combo,
#                     boe_no=irr.boe_num, 
#                     dlv_zone_from_irr=case(
#                     ( 
#                         WorkerAssignmentShipment.dlv_zone_from_irr.is_(None),
#                       irr.dlv_zone),
#                     else_=WorkerAssignmentShipment.dlv_zone_from_irr
#                 ),
#                     updated_at=now
#                 )
#             )
#             continue

#         # Case B2: No matching IRR GP → Insert new event (PART SHIPMENT)
#         print("🟩 NEW IRR GP → INSERT NEW IRR EVENT (PART SHIPMENT)")
#         if str(irr.gate_pass_no) == "25277649":
#             print("🆕 CASE: New IRR Insert")

#         await db.execute(
#             insert(WorkerAssignmentShipment).values(
#                 assignment_header_id=header_id,
#                 gate_pass_no=irr.gate_pass_no,
#                 gate_pass_issued_date_time_combo=gp_combo,
#                 gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                 flight_no=irr.flight_no,
#                 flight_date=irr.flight_date,
#                 no_of_pc=irr.pcs,
#                 no_of_pc_recd=irr.pcs,
#                 weight_in_kgs=irr.grg_wt,
#                 chg_wgt_in_kg=irr.chg_wt,
#                 location=irr.location_pcs,
#                 agent_name=irr.agent,
#                 customer_name=irr.consignee,
#                 release_zone=irr.dlv_zone,
#                 segregation_datetime=seg_combo,   # 🆕
#                 boe_no=irr.boe_num,  #   🆕
#                 from_irr_table=True,

#                dlv_zone_from_irr=irr.dlv_zone,   # 🆕

#                 created_at=now,
#                 updated_at=now
#             )
#         )

#     # =====================================================
#     # END + COMMIT
#     # =====================================================
#     await db.commit()
#     print("\n================= 🟦 END PROCESS (DEBUG MODE) =================\n\n")

#     return {
#         "success":               True,
#         "merge_rows_processed":  len(merge_rows),
#         "irr_rows_processed":    len(irr_rows),
#         "headers_inserted":      headers_inserted,
#         "headers_updated":       headers_updated,
#         "events_processed":      events_inserted,
#         "warnings":              errors
#     }

# ============= New with part shipment handling ==============

# async def process_worker_assignment(db: AsyncSession, req):
#     """
#     ======================================================
#     WORKER ASSIGNMENT PROCESS (HYBRID CLEAN + DEBUG LOGGING)
#     ======================================================
#     """
#     print("\n\n================= 🟦 START PROCESS ASSIGNMENT (DEBUG MODE ON) =================")
#     utc_start, utc_end = ist_day_to_utc_range(req.date)
#     now = get_utc_now()

#     headers_inserted = 0
#     headers_updated = 0
#     events_inserted = 0
#     errors = []

#     # =====================================================
#     # 1️⃣ FETCH SOURCE DATA (OC + IRR)
#     # =====================================================
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

#     # =====================================================
#     # 2️⃣ PROCESS OC-MERGE DATA
#     # =====================================================
#     for oc in merge_rows:

#         norm_hawb = (oc.hawb or "").strip()

#         header_stmt = (
#             insert(WorkerAssignmentHeader)
#             .values(
#                 awb_no=oc.awb_no,
#                 hawb=norm_hawb,
#                 oc_no=oc.oc_no,
#                 temp_irm_oc_no=oc.temp_irm_oc_no,
#                 is_temp_irm_oc=oc.is_temp_irm_oc,
#                 igp_no=oc.igp_no,
#                 igp_print_date_time=oc.igp_print_date_time,
#                 created_at=now,
#                 updated_at=now
#             )
#             .on_conflict_do_update(
#                 index_elements=[WorkerAssignmentHeader.awb_no, text("COALESCE(hawb, '')")],
#                 set_={
#                     "oc_no": insert(WorkerAssignmentHeader).excluded.oc_no,
#                     "temp_irm_oc_no": case(
#                         (WorkerAssignmentHeader.temp_irm_oc_no.is_(None), insert(WorkerAssignmentHeader).excluded.temp_irm_oc_no),
#                         else_=WorkerAssignmentHeader.temp_irm_oc_no
#                     ),
#                     "igp_no": insert(WorkerAssignmentHeader).excluded.igp_no,
#                     "updated_at": now
#                 }
#             )
#             .returning(WorkerAssignmentHeader.id, text("CASE WHEN xmax = 0 THEN 1 ELSE 0 END"))
#         )

#         # 🔒 SAVEPOINT — catches duplicate oc_no without killing the whole batch
#         try:
#             sp = await db.begin_nested()
#             row = (await db.execute(header_stmt)).first()
#             await sp.commit()
#         except IntegrityError as e:
#             await sp.rollback()
#             parsed = _parse_integrity_error(e)
#             errors.append({
#                 "type":       "DUPLICATE_OC_NO",
#                 "source":     "OC_MERGE",
#                 "awb":        oc.awb_no,
#                 "hawb":       oc.hawb or "",
#                 "oc_no":      parsed["value"] or oc.oc_no,
#                 "constraint": parsed["constraint"],
#                 "message": (
#                     f"OC No '{parsed['value'] or oc.oc_no}' already assigned to a different "
#                     f"AWB/HAWB. Skipped → AWB={oc.awb_no}, HAWB={oc.hawb or 'N/A'}."
#                 )
#             })
#             continue  # ⛔ skip this OC row, move to next

#         header_id, is_insert = row
#         if is_insert:
#             headers_inserted += 1
#         else:
#             headers_updated += 1

#         # 🔒 IF IRR shipment already exists for this header → SKIP OC shipment
#         irr_exists = (await db.execute(
#             select(WorkerAssignmentShipment.id).where(
#                 WorkerAssignmentShipment.assignment_header_id == header_id,
#                 WorkerAssignmentShipment.from_irr_table == True
#             )
#         )).first()

#         if irr_exists:
#             continue

#         # ---- OC EVENT UPSERT
#         event_stmt = (
#             insert(WorkerAssignmentShipment)
#             .values(
#                 assignment_header_id=header_id,
#                 flight_no=oc.flight_no,
#                 flight_date=oc.flight_date,
#                 no_of_pc=oc.no_of_pc,
#                 weight_in_kgs=oc.weight_in_kgs,
#                 chg_wgt_in_kg=oc.chg_wgt_in_kg,
#                 location=oc.location,
#                 shc=oc.shc,
#                 irr_codes=oc.irr_codes,
#                 irregularity_remarks=oc.irregularity_remarks,
#                 integrate_date_time=oc.integrate_date_time,
#                 from_irr_table=False,
#                 created_at=now,
#                 updated_at=now
#             )
#             .on_conflict_do_update(
#                 index_elements=[WorkerAssignmentShipment.assignment_header_id, WorkerAssignmentShipment.integrate_date_time],
#                 set_={
#                     "weight_in_kgs": case(
#                         (WorkerAssignmentShipment.weight_in_kgs.is_(None), insert(WorkerAssignmentShipment).excluded.weight_in_kgs),
#                         else_=WorkerAssignmentShipment.weight_in_kgs
#                     ),
#                     "chg_wgt_in_kg": case(
#                         (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None), insert(WorkerAssignmentShipment).excluded.chg_wgt_in_kg),
#                         else_=WorkerAssignmentShipment.chg_wgt_in_kg
#                     ),
#                     "no_of_pc": case(
#                         (WorkerAssignmentShipment.no_of_pc.is_(None), insert(WorkerAssignmentShipment).excluded.no_of_pc),
#                         else_=WorkerAssignmentShipment.no_of_pc
#                     ),
#                     "location": case(
#                         (
#                             and_(
#                                 insert(WorkerAssignmentShipment).excluded.location.isnot(None),
#                                 func.trim(insert(WorkerAssignmentShipment).excluded.location) != "",
#                                 func.trim(insert(WorkerAssignmentShipment).excluded.location) != "-",
#                             ),
#                             insert(WorkerAssignmentShipment).excluded.location
#                         ),
#                         else_=WorkerAssignmentShipment.location
#                     ),
#                     "updated_at": now
#                 }
#             )
#         )

#         await db.execute(event_stmt)
#         events_inserted += 1

#     # =====================================================
#     # 3️⃣ PROCESS IRR DATA
#     # =====================================================
#     for irr in irr_rows:

#         norm_hawb = (irr.hwb or "").strip()
#         gp_combo = combine_gate_pass_date_with_time_and_return_utc_datetime(
#             irr.gate_pass_issued_date,
#             irr.gate_pass_issued_time
#         )

#         # 🆕 Segregation datetime — same pattern as gate pass combo
#         seg_combo = None
#         if irr.segregation_date and irr.segregation_time:
#             try:
#                 seg_combo = combine_gate_pass_date_with_time_and_return_utc_datetime(
#                     irr.segregation_date,
#                     irr.segregation_time
#                 )
#             except Exception as e:
#                 print(f"⚠️ Failed to combine segregation datetime for GP={irr.gate_pass_no}: {e}")
#                 seg_combo = None

#         header_stmt = (
#             insert(WorkerAssignmentHeader)
#             .values(
#                 awb_no=irr.awb,
#                 hawb=norm_hawb,
#                 oc_no=irr.oc_num,
#                 is_temp_irm_oc=False,
#                 created_at=now,
#                 updated_at=now
#             )
#             .on_conflict_do_update(
#                 index_elements=[WorkerAssignmentHeader.awb_no, text("COALESCE(hawb, '')")],
#                 set_={
#                     "oc_no":          insert(WorkerAssignmentHeader).excluded.oc_no,
#                     "is_temp_irm_oc": False,
#                     "updated_at":     now
#                 }
#             )
#             .returning(WorkerAssignmentHeader.id)
#         )

#         # 🔒 SAVEPOINT — catches duplicate oc_no without killing the whole batch
#         try:
#             sp = await db.begin_nested()
#             header_id = (await db.execute(header_stmt)).scalar_one()
#             await sp.commit()
#         except IntegrityError as e:
#             await sp.rollback()
#             parsed = _parse_integrity_error(e)
#             errors.append({
#                 "type":       "DUPLICATE_OC_NO",
#                 "source":     "IRR",
#                 "awb":        irr.awb,
#                 "hawb":       irr.hwb or "",
#                 "gate_pass":  irr.gate_pass_no,
#                 "oc_no":      parsed["value"] or irr.oc_num,
#                 "constraint": parsed["constraint"],
#                 "message": (
#                     f"OC No '{parsed['value'] or irr.oc_num}' already assigned to a different "
#                     f"AWB/HAWB. Skipped → AWB={irr.awb}, HAWB={irr.hwb or 'N/A'}, "
#                     f"GP={irr.gate_pass_no}."
#                 )
#             })
#             continue  # ⛔ skip this IRR row, move to next

#         # ============================================================
#         # IRR EVENT RESOLUTION — Step 0 / 1 / 2
#         # ------------------------------------------------------------
#         # Step 0: same GP already on header        → re-update
#         # Step 1: GP-less row, strict pcs match     → attach (A1 semantics)
#         # Step 2: no match                          → spawn new part shipment
#         #
#         # Invariants:
#         #   - GP unique per header (Step 0 + DB constraint)
#         #   - IRR-origin rows always integrate_date_time = NULL
#         #   - strict pcs match, NULL never matches (Option A)
#         #   - from_irr_table written on every path
#         #   - no ImportGpMismatchLog write from this path
#         # ============================================================

#         # ─────────────────────────────────────────────────────────────
#         # STEP 0 — Same GP already on this header  →  RE-UPDATE
#         # (subsumes old A2 + old IRR-existence guard)
#         # ─────────────────────────────────────────────────────────────
#         existing_gp_event = (await db.execute(
#             select(WorkerAssignmentShipment).where(
#                 WorkerAssignmentShipment.assignment_header_id == header_id,
#                 WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no,
#             )
#         )).scalars().first()

#         if existing_gp_event:
#             # Fill end-time only if it was missing
#             if existing_gp_event.gate_pass_end_datetime is None and irr.gate_pass_end_date_time:
#                 await db.execute(
#                     update(WorkerAssignmentShipment)
#                     .where(WorkerAssignmentShipment.id == existing_gp_event.id)
#                     .values(
#                         gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                         gate_pass_issued_date_time_combo=gp_combo,
#                         updated_at=now,
#                     )
#                 )

#             # NULL-fill segregation / boe / dlv_zone in one trip
#             patch_segregation = existing_gp_event.segregation_datetime is None and seg_combo
#             patch_boe_no      = existing_gp_event.boe_no is None and irr.boe_num
#             patch_dlv_zone    = existing_gp_event.dlv_zone_from_irr is None and irr.dlv_zone

#             if patch_segregation or patch_boe_no or patch_dlv_zone:
#                 await db.execute(
#                     update(WorkerAssignmentShipment)
#                     .where(WorkerAssignmentShipment.id == existing_gp_event.id)
#                     .values(
#                         segregation_datetime=case(
#                             (WorkerAssignmentShipment.segregation_datetime.is_(None), seg_combo),
#                             else_=WorkerAssignmentShipment.segregation_datetime
#                         ),
#                         boe_no=case(
#                             (WorkerAssignmentShipment.boe_no.is_(None), irr.boe_num),
#                             else_=WorkerAssignmentShipment.boe_no
#                         ),
#                         dlv_zone_from_irr=case(
#                             (WorkerAssignmentShipment.dlv_zone_from_irr.is_(None), irr.dlv_zone),
#                             else_=WorkerAssignmentShipment.dlv_zone_from_irr
#                         ),
#                         updated_at=now,
#                     )
#                 )
#             continue

#         # ─────────────────────────────────────────────────────────────
#         # STEP 1 — Attach GP to a GP-less row by STRICT pcs match
#         # (replaces old A1; works regardless of OC vs IRR origin)
#         #
#         # Match = same header, gate_pass_no IS NULL, no_of_pc == irr.pcs,
#         #         irr.pcs IS NOT NULL.  Lowest id if several.
#         #
#         # Fill semantics IDENTICAL to old A1:
#         #   - GP fields always set
#         #   - no_of_pc / no_of_pc_recd / weight / chg / agent / customer /
#         #     release_zone / segregation / boe / dlv_zone_from_irr → NULL-fill
#         #   - location → set only when IRR location_pcs is non-empty / non-"-"
#         #   - flight_no / flight_date → NOT touched (same as old A1)
#         # ─────────────────────────────────────────────────────────────
#         attach_target = None
#         if irr.pcs is not None:
#             attach_target = (await db.execute(
#                 select(WorkerAssignmentShipment).where(
#                     WorkerAssignmentShipment.assignment_header_id == header_id,
#                     WorkerAssignmentShipment.gate_pass_no.is_(None),
#                     WorkerAssignmentShipment.no_of_pc == irr.pcs,            # OPTION A (strict)
#                     # ── OPTION B (wildcard for NULL-pcs seed) ──────────────
#                     # To let a GP-less seed row with NULL pcs absorb the first
#                     # GP, REPLACE the line above with the or_() block below:
#                     #
#                     # or_(
#                     #     WorkerAssignmentShipment.no_of_pc == irr.pcs,
#                     #     WorkerAssignmentShipment.no_of_pc.is_(None),
#                     # ),
#                     #
#                     # NOTE: with Option B, also drop the `if irr.pcs is not None`
#                     # guard above so a NULL-pcs seed can match when irr.pcs is None.
#                 )
#                 .order_by(WorkerAssignmentShipment.id.asc())
#             )).scalars().first()

#         if attach_target:
#             await db.execute(
#                 update(WorkerAssignmentShipment)
#                 .where(WorkerAssignmentShipment.id == attach_target.id)
#                 .values(
#                     gate_pass_no=irr.gate_pass_no,
#                     gate_pass_issued_date_time_combo=gp_combo,
#                     gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                     no_of_pc=case(
#                         (WorkerAssignmentShipment.no_of_pc.is_(None), irr.pcs),
#                         else_=WorkerAssignmentShipment.no_of_pc
#                     ),
#                     no_of_pc_recd=case(
#                         (WorkerAssignmentShipment.no_of_pc_recd.is_(None), irr.pcs),
#                         else_=WorkerAssignmentShipment.no_of_pc_recd
#                     ),
#                     weight_in_kgs=case(
#                         (WorkerAssignmentShipment.weight_in_kgs.is_(None), irr.grg_wt),
#                         else_=WorkerAssignmentShipment.weight_in_kgs
#                     ),
#                     chg_wgt_in_kg=case(
#                         (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None), irr.chg_wt),
#                         else_=WorkerAssignmentShipment.chg_wgt_in_kg
#                     ),
#                     location=case(
#                         (
#                             and_(
#                                 irr.location_pcs != None,
#                                 func.trim(irr.location_pcs) != "",
#                                 func.trim(irr.location_pcs) != "-",
#                             ),
#                             irr.location_pcs
#                         ),
#                         else_=WorkerAssignmentShipment.location
#                     ),
#                     agent_name=case(
#                         (WorkerAssignmentShipment.agent_name.is_(None), irr.agent),
#                         else_=WorkerAssignmentShipment.agent_name
#                     ),
#                     customer_name=case(
#                         (WorkerAssignmentShipment.customer_name.is_(None), irr.consignee),
#                         else_=WorkerAssignmentShipment.customer_name
#                     ),
#                     release_zone=case(
#                         (WorkerAssignmentShipment.release_zone.is_(None), irr.dlv_zone),
#                         else_=WorkerAssignmentShipment.release_zone
#                     ),
#                     segregation_datetime=case(
#                         (WorkerAssignmentShipment.segregation_datetime.is_(None), seg_combo),
#                         else_=WorkerAssignmentShipment.segregation_datetime
#                     ),
#                     boe_no=case(
#                         (WorkerAssignmentShipment.boe_no.is_(None), irr.boe_num),
#                         else_=WorkerAssignmentShipment.boe_no
#                     ),
#                     dlv_zone_from_irr=case(
#                         (WorkerAssignmentShipment.dlv_zone_from_irr.is_(None), irr.dlv_zone),
#                         else_=WorkerAssignmentShipment.dlv_zone_from_irr
#                     ),
#                     updated_at=now,
#                 )
#             )
#             continue

#         # ─────────────────────────────────────────────────────────────
#         # STEP 2 — No match  →  SPAWN new part shipment
#         # (replaces old B2; same fields as old B2 insert)
#         #   - from_irr_table = True
#         #   - integrate_date_time = NULL  (IRR-origin invariant)
#         # ─────────────────────────────────────────────────────────────
#         await db.execute(
#             insert(WorkerAssignmentShipment).values(
#                 assignment_header_id=header_id,
#                 gate_pass_no=irr.gate_pass_no,
#                 gate_pass_issued_date_time_combo=gp_combo,
#                 gate_pass_end_datetime=irr.gate_pass_end_date_time,
#                 flight_no=irr.flight_no,
#                 flight_date=irr.flight_date,
#                 no_of_pc=irr.pcs,
#                 no_of_pc_recd=irr.pcs,
#                 weight_in_kgs=irr.grg_wt,
#                 chg_wgt_in_kg=irr.chg_wt,
#                 location=irr.location_pcs,
#                 agent_name=irr.agent,
#                 customer_name=irr.consignee,
#                 release_zone=irr.dlv_zone,
#                 segregation_datetime=seg_combo,
#                 boe_no=irr.boe_num,
#                 from_irr_table=True,
#                 dlv_zone_from_irr=irr.dlv_zone,
#                 # integrate_date_time intentionally omitted → stays NULL
#                 created_at=now,
#                 updated_at=now
#             )
#         )
#         events_inserted += 1

#     # =====================================================
#     # END + COMMIT
#     # =====================================================
#     await db.commit()
#     print("\n================= 🟦 END PROCESS (DEBUG MODE) =================\n\n")

#     return {
#         "success":               True,
#         "merge_rows_processed":  len(merge_rows),
#         "irr_rows_processed":    len(irr_rows),
#         "headers_inserted":      headers_inserted,
#         "headers_updated":       headers_updated,
#         "events_processed":      events_inserted,
#         "warnings":              errors
#     }









async def process_worker_assignment(db: AsyncSession, req):
    """
    ======================================================
    WORKER ASSIGNMENT PROCESS (HYBRID CLEAN + DEBUG LOGGING)
    ======================================================
    """
    print("\n\n================= 🟦 START PROCESS ASSIGNMENT (DEBUG MODE ON) =================")
    utc_start, utc_end = ist_day_to_utc_range(req.date)
    now = get_utc_now()

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

    # 🐞 DEBUG TRACE — is the target GP even in the fetched IRR set?
    _DBG_GP = "26051498"
    _dbg_present = any(str(r.gate_pass_no) == _DBG_GP for r in irr_rows)
    print(f"🐞 [FETCH] window {utc_start} → {utc_end} | irr_rows={len(irr_rows)} | "
          f"GP {_DBG_GP} present in fetch: {_dbg_present}")
    if not _dbg_present:
        print(f"🐞 [FETCH] ⚠️ GP {_DBG_GP} NOT in fetched IRR set → "
              f"check gate_pass_issued_date vs req.date ({req.date}).")

    # =====================================================
    # 2️⃣ PROCESS OC-MERGE DATA
    # =====================================================
    for oc in merge_rows:

        norm_hawb = (oc.hawb or "").strip()

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
                        (WorkerAssignmentHeader.temp_irm_oc_no.is_(None), insert(WorkerAssignmentHeader).excluded.temp_irm_oc_no),
                        else_=WorkerAssignmentHeader.temp_irm_oc_no
                    ),
                    "igp_no": insert(WorkerAssignmentHeader).excluded.igp_no,
                    "updated_at": now
                }
            )
            .returning(WorkerAssignmentHeader.id, text("CASE WHEN xmax = 0 THEN 1 ELSE 0 END"))
        )

        # 🔒 SAVEPOINT — catches duplicate oc_no without killing the whole batch
        try:
            sp = await db.begin_nested()
            row = (await db.execute(header_stmt)).first()
            await sp.commit()
        except IntegrityError as e:
            await sp.rollback()
            parsed = _parse_integrity_error(e)
            errors.append({
                "type":       "DUPLICATE_OC_NO",
                "source":     "OC_MERGE",
                "awb":        oc.awb_no,
                "hawb":       oc.hawb or "",
                "oc_no":      parsed["value"] or oc.oc_no,
                "constraint": parsed["constraint"],
                "message": (
                    f"OC No '{parsed['value'] or oc.oc_no}' already assigned to a different "
                    f"AWB/HAWB. Skipped → AWB={oc.awb_no}, HAWB={oc.hawb or 'N/A'}."
                )
            })
            continue  # ⛔ skip this OC row, move to next

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
                index_elements=[WorkerAssignmentShipment.assignment_header_id, WorkerAssignmentShipment.integrate_date_time],
                set_={
                    "weight_in_kgs": case(
                        (WorkerAssignmentShipment.weight_in_kgs.is_(None), insert(WorkerAssignmentShipment).excluded.weight_in_kgs),
                        else_=WorkerAssignmentShipment.weight_in_kgs
                    ),
                    "chg_wgt_in_kg": case(
                        (WorkerAssignmentShipment.chg_wgt_in_kg.is_(None), insert(WorkerAssignmentShipment).excluded.chg_wgt_in_kg),
                        else_=WorkerAssignmentShipment.chg_wgt_in_kg
                    ),
                    "no_of_pc": case(
                        (WorkerAssignmentShipment.no_of_pc.is_(None), insert(WorkerAssignmentShipment).excluded.no_of_pc),
                        else_=WorkerAssignmentShipment.no_of_pc
                    ),
                    "location": case(
                        (
                            and_(
                                insert(WorkerAssignmentShipment).excluded.location.isnot(None),
                                func.trim(insert(WorkerAssignmentShipment).excluded.location) != "",
                                func.trim(insert(WorkerAssignmentShipment).excluded.location) != "-",
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
    # 3️⃣ PROCESS IRR DATA
    # =====================================================
    for irr in irr_rows:

        _is_dbg = str(irr.gate_pass_no) == _DBG_GP
        if _is_dbg:
            print("🐞" + "="*60)
            print(f"🐞 [ROW] GP={irr.gate_pass_no} AWB={irr.awb} HWB={irr.hwb} "
                  f"OC={irr.oc_num} PCS={irr.pcs}")
            print(f"🐞 [ROW] gp_issued_date={irr.gate_pass_issued_date} "
                  f"gp_issued_time={irr.gate_pass_issued_time} "
                  f"gp_end={irr.gate_pass_end_date_time}")

        norm_hawb = (irr.hwb or "").strip()
        gp_combo = combine_gate_pass_date_with_time_and_return_utc_datetime(
            irr.gate_pass_issued_date,
            irr.gate_pass_issued_time
        )

        # 🆕 Segregation datetime — same pattern as gate pass combo
        seg_combo = None
        if irr.segregation_date and irr.segregation_time:
            try:
                seg_combo = combine_gate_pass_date_with_time_and_return_utc_datetime(
                    irr.segregation_date,
                    irr.segregation_time
                )
            except Exception as e:
                print(f"⚠️ Failed to combine segregation datetime for GP={irr.gate_pass_no}: {e}")
                seg_combo = None

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
                    "oc_no":          insert(WorkerAssignmentHeader).excluded.oc_no,
                    "is_temp_irm_oc": False,
                    "updated_at":     now
                }
            )
            .returning(WorkerAssignmentHeader.id)
        )

        # 🔒 SAVEPOINT — catches duplicate oc_no without killing the whole batch
        try:
            sp = await db.begin_nested()
            header_id = (await db.execute(header_stmt)).scalar_one()
            await sp.commit()
            if _is_dbg:
                print(f"🐞 [HEADER] upsert OK → header_id={header_id}")
        except IntegrityError as e:
            await sp.rollback()
            if _is_dbg:
                print(f"🐞 [HEADER] ❌ IntegrityError (DUPLICATE_OC_NO) → "
                      f"row SKIPPED. detail={str(e.orig)[:160]}")
            parsed = _parse_integrity_error(e)
            errors.append({
                "type":       "DUPLICATE_OC_NO",
                "source":     "IRR",
                "awb":        irr.awb,
                "hawb":       irr.hwb or "",
                "gate_pass":  irr.gate_pass_no,
                "oc_no":      parsed["value"] or irr.oc_num,
                "constraint": parsed["constraint"],
                "message": (
                    f"OC No '{parsed['value'] or irr.oc_num}' already assigned to a different "
                    f"AWB/HAWB. Skipped → AWB={irr.awb}, HAWB={irr.hwb or 'N/A'}, "
                    f"GP={irr.gate_pass_no}."
                )
            })
            continue  # ⛔ skip this IRR row, move to next

        # ============================================================
        # IRR EVENT RESOLUTION — Step 0 / 1 / 2
        # ------------------------------------------------------------
        # Step 0: same GP already on header        → re-update
        # Step 1: GP-less row, strict pcs match     → attach (A1 semantics)
        # Step 2: no match                          → spawn new part shipment
        #
        # Invariants:
        #   - GP unique per header (Step 0 + DB constraint)
        #   - IRR-origin rows always integrate_date_time = NULL
        #   - strict pcs match, NULL never matches (Option A)
        #   - from_irr_table written on every path
        #   - no ImportGpMismatchLog write from this path
        # ============================================================

        # ─────────────────────────────────────────────────────────────
        # STEP 0 — Same GP already on this header  →  RE-UPDATE
        # (subsumes old A2 + old IRR-existence guard)
        # ─────────────────────────────────────────────────────────────
        existing_gp_event = (await db.execute(
            select(WorkerAssignmentShipment).where(
                WorkerAssignmentShipment.assignment_header_id == header_id,
                WorkerAssignmentShipment.gate_pass_no == irr.gate_pass_no,
            )
        )).scalars().first()

        if _is_dbg:
            print(f"🐞 [STEP0] existing GP row on header? "
                  f"{'YES id='+str(existing_gp_event.id) if existing_gp_event else 'NO'}")

        if existing_gp_event:
            if _is_dbg:
                print(f"🐞 [STEP0] → RE-UPDATE existing row id={existing_gp_event.id}")
            # Fill end-time only if it was missing
            if existing_gp_event.gate_pass_end_datetime is None and irr.gate_pass_end_date_time:
                await db.execute(
                    update(WorkerAssignmentShipment)
                    .where(WorkerAssignmentShipment.id == existing_gp_event.id)
                    .values(
                        gate_pass_end_datetime=irr.gate_pass_end_date_time,
                        gate_pass_issued_date_time_combo=gp_combo,
                        updated_at=now,
                    )
                )

            # NULL-fill segregation / boe / dlv_zone in one trip
            patch_segregation = existing_gp_event.segregation_datetime is None and seg_combo
            patch_boe_no      = existing_gp_event.boe_no is None and irr.boe_num
            patch_dlv_zone    = existing_gp_event.dlv_zone_from_irr is None and irr.dlv_zone

            if patch_segregation or patch_boe_no or patch_dlv_zone:
                await db.execute(
                    update(WorkerAssignmentShipment)
                    .where(WorkerAssignmentShipment.id == existing_gp_event.id)
                    .values(
                        segregation_datetime=case(
                            (WorkerAssignmentShipment.segregation_datetime.is_(None), seg_combo),
                            else_=WorkerAssignmentShipment.segregation_datetime
                        ),
                        boe_no=case(
                            (WorkerAssignmentShipment.boe_no.is_(None), irr.boe_num),
                            else_=WorkerAssignmentShipment.boe_no
                        ),
                        dlv_zone_from_irr=case(
                            (WorkerAssignmentShipment.dlv_zone_from_irr.is_(None), irr.dlv_zone),
                            else_=WorkerAssignmentShipment.dlv_zone_from_irr
                        ),
                        updated_at=now,
                    )
                )
            continue

        # ─────────────────────────────────────────────────────────────
        # STEP 1 — Attach GP to a GP-less row by STRICT pcs match
        # (replaces old A1; works regardless of OC vs IRR origin)
        #
        # Match = same header, gate_pass_no IS NULL, no_of_pc == irr.pcs,
        #         irr.pcs IS NOT NULL.  Lowest id if several.
        #
        # Fill semantics IDENTICAL to old A1:
        #   - GP fields always set
        #   - no_of_pc / no_of_pc_recd / weight / chg / agent / customer /
        #     release_zone / segregation / boe / dlv_zone_from_irr → NULL-fill
        #   - location → set only when IRR location_pcs is non-empty / non-"-"
        #   - flight_no / flight_date → NOT touched (same as old A1)
        # ─────────────────────────────────────────────────────────────
        attach_target = None
        if irr.pcs is not None:
            attach_target = (await db.execute(
                select(WorkerAssignmentShipment).where(
                    WorkerAssignmentShipment.assignment_header_id == header_id,
                    WorkerAssignmentShipment.gate_pass_no.is_(None),
                    WorkerAssignmentShipment.no_of_pc == irr.pcs,            # OPTION A (strict)
                    # ── OPTION B (wildcard for NULL-pcs seed) ──────────────
                    # To let a GP-less seed row with NULL pcs absorb the first
                    # GP, REPLACE the line above with the or_() block below:
                    #
                    # or_(
                    #     WorkerAssignmentShipment.no_of_pc == irr.pcs,
                    #     WorkerAssignmentShipment.no_of_pc.is_(None),
                    # ),
                    #
                    # NOTE: with Option B, also drop the `if irr.pcs is not None`
                    # guard above so a NULL-pcs seed can match when irr.pcs is None.
                )
                .order_by(WorkerAssignmentShipment.id.asc())
            )).scalars().first()

        if _is_dbg:
            if irr.pcs is None:
                print("🐞 [STEP1] irr.pcs is NULL → strict match skipped (Option A)")
            print(f"🐞 [STEP1] GP-less pcs-match row? "
                  f"{'YES id='+str(attach_target.id) if attach_target else 'NO'} "
                  f"(looking for no_of_pc={irr.pcs})")

        if attach_target:
            if _is_dbg:
                print(f"🐞 [STEP1] → ATTACH GP onto row id={attach_target.id}")
            await db.execute(
                update(WorkerAssignmentShipment)
                .where(WorkerAssignmentShipment.id == attach_target.id)
                .values(
                    gate_pass_no=irr.gate_pass_no,
                    gate_pass_issued_date_time_combo=gp_combo,
                    gate_pass_end_datetime=irr.gate_pass_end_date_time,
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
                        (
                            and_(
                                irr.location_pcs != None,
                                func.trim(irr.location_pcs) != "",
                                func.trim(irr.location_pcs) != "-",
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
                    segregation_datetime=case(
                        (WorkerAssignmentShipment.segregation_datetime.is_(None), seg_combo),
                        else_=WorkerAssignmentShipment.segregation_datetime
                    ),
                    boe_no=case(
                        (WorkerAssignmentShipment.boe_no.is_(None), irr.boe_num),
                        else_=WorkerAssignmentShipment.boe_no
                    ),
                    dlv_zone_from_irr=case(
                        (WorkerAssignmentShipment.dlv_zone_from_irr.is_(None), irr.dlv_zone),
                        else_=WorkerAssignmentShipment.dlv_zone_from_irr
                    ),
                    updated_at=now,
                )
            )
            continue

        # ─────────────────────────────────────────────────────────────
        # STEP 2 — No match  →  SPAWN new part shipment
        # (replaces old B2; same fields as old B2 insert)
        #   - from_irr_table = True
        #   - integrate_date_time = NULL  (IRR-origin invariant)
        # ─────────────────────────────────────────────────────────────
        if _is_dbg:
            print(f"🐞 [STEP2] → SPAWN new part shipment under header_id={header_id} "
                  f"(gp={irr.gate_pass_no}, pcs={irr.pcs}, integrate=NULL)")

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
                segregation_datetime=seg_combo,
                boe_no=irr.boe_num,
                from_irr_table=True,
                dlv_zone_from_irr=irr.dlv_zone,
                # integrate_date_time intentionally omitted → stays NULL
                created_at=now,
                updated_at=now
            )
        )
        events_inserted += 1

    # =====================================================
    # END + COMMIT
    # =====================================================
    await db.commit()
    print("\n================= 🟦 END PROCESS (DEBUG MODE) =================\n\n")

    return {
        "success":               True,
        "merge_rows_processed":  len(merge_rows),
        "irr_rows_processed":    len(irr_rows),
        "headers_inserted":      headers_inserted,
        "headers_updated":       headers_updated,
        "events_processed":      events_inserted,
        "warnings":              errors
    }



# =================😎 new end ===============

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


# 🫷🫷🫷Get all list of shipment based on assignd to particular worker ==============================
# async def get_worker_assignment_lists_by_emp_id(
#     db: AsyncSession,
#     emp_id: str
# ) -> list[dict]:
#     # ----------------------------------------------------
#     # 1️⃣ Validate user
#     # ----------------------------------------------------
#     user = await db.scalar(
#         select(User).where(User.emp_id == emp_id)
#     )

#     if not user:
#         raise HTTPException(404, "User not found")

#     allowed_roles = {"imp_gp_user", "imp_tracer"} # ✅ add all allowed roles here if user.role not in
#     if user.role not in allowed_roles:
#         raise HTTPException(403, "User is not authorized")

#     # ----------------------------------------------------
#     # 2️⃣ Query shipment + header
#     # ----------------------------------------------------
#     shipment = WorkerAssignmentShipment
#     header = WorkerAssignmentHeader

#     stmt = (
#         select(shipment, header)
#         .join(header, shipment.assignment_header_id == header.id)
#         .where(shipment.assigned_person == emp_id)
#         .where(
#             or_(
#                 shipment.drop_dlv_zone.is_(None),
#                 func.trim(shipment.drop_dlv_zone) == "",
#                 func.trim(shipment.drop_dlv_zone) == "-"
#             )
#         )
#         .order_by(shipment.integrate_date_time.desc())
#     )

#     rows = (await db.execute(stmt)).all()

#     # ----------------------------------------------------
#     # 3️⃣ Shape response (flat JSON)
#     # ----------------------------------------------------
#     results = []
#     for shipment, header in rows:
#         results.append({
#                    # REQUIRED IDS
#         "header_id": header.id,
#         "shipment_id": shipment.id,

#         # HEADER FIELDS
#         "oc_no": header.oc_no,
#         "awb_no": header.awb_no,
#         "hawb": header.hawb,
#         "temp_irm_oc_no": header.temp_irm_oc_no,
#         "is_temp_irm_oc": header.is_temp_irm_oc,

#         # SHIPMENT FIELDS
#         "gate_pass_no": shipment.gate_pass_no,
#         "gate_pass_issued_date_time_combo": shipment.gate_pass_issued_date_time_combo,
#         "gate_pass_end_datetime": shipment.gate_pass_end_datetime,

#         "assigned_person": shipment.assigned_person,
#         "assigned_person_datetime": shipment.assigned_person_datetime,

#         "drop_dlv_zone": shipment.drop_dlv_zone,
#         "drop_dlv_zone_datetime": shipment.drop_dlv_zone_datetime,

#         "integrate_date_time": shipment.integrate_date_time,
#         "from_irr_table": shipment.from_irr_table,

#         # OPERATIONAL DATA
#         "location": shipment.location,
#         "no_of_pc": shipment.no_of_pc,
#         "weight_in_kgs": shipment.weight_in_kgs,
#         "chg_wgt_in_kg": shipment.chg_wgt_in_kg,

#         "damage_report_status":shipment.damage_report_status,

#         "flight_no": shipment.flight_no,
#         "flight_date": shipment.flight_date,

#         # TIMESTAMPS
#         "created_at": shipment.created_at,
#         "updated_at": shipment.updated_at,
#         })

#     return results

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

    allowed_roles = {"imp_gp_user", "imp_tracer"} # ✅ add all allowed roles here if user.role not in
    if user.role not in allowed_roles:
        raise HTTPException(403, "User is not authorized")

    # ----------------------------------------------------
    # 2️⃣ Query shipment + header
    # ----------------------------------------------------
    shipment = WorkerAssignmentShipment
    header = WorkerAssignmentHeader

    # stmt = (
    #     select(shipment, header)
    #     .join(header, shipment.assignment_header_id == header.id)
    #     .where(shipment.assigned_person == emp_id)
    #     .where(
    #         or_(
    #             shipment.drop_dlv_zone.is_(None),
    #             func.trim(shipment.drop_dlv_zone) == "",
    #             func.trim(shipment.drop_dlv_zone) == "-"
    #         )
    #     )
    #     .order_by(shipment.integrate_date_time.desc())
    # )
    
    damage = DamageReport
    stmt = (
    select(
        shipment,
        header,

        # ✅ Fixed: Use json type instead of JSONB
        func.coalesce(
            func.json_agg(
                func.json_build_object(
                    "id", damage.id,
                    "location", damage.location,
                    "status", func.coalesce(damage.status, "")  # ✅ Default to "open" or ""
                )
            ).filter(damage.id.isnot(None)),
            func.cast("[]", JSON)   # ✅ Changed from JSONB to JSON
        ).label("damages")

    )

    .join(header, shipment.assignment_header_id == header.id)

    # ✅ LEFT JOIN Damage
    .outerjoin(
        damage,
        damage.assignment_shipment_id == shipment.id
    )

    .where(shipment.assigned_person == emp_id)

    .where(
        or_(
            shipment.drop_dlv_zone.is_(None),
            func.trim(shipment.drop_dlv_zone) == "",
            func.trim(shipment.drop_dlv_zone) == "-"
        )
    )

    # # ✅ REQUIRED for aggregation
    # .group_by(shipment.id, header.id)

    # .order_by(shipment.integrate_date_time.desc())
)
    # ✅ ADD ROLE FILTER HERE (before group_by)
    if user.role == "imp_gp_user":
        stmt = stmt.where(
            or_(
                shipment.damage_report_status.is_(None),
                shipment.damage_report_status == DamageStatusInWorkerAssignmnet.OPEN.value
            )
        )

    elif user.role == "imp_tracer":
        stmt = stmt.where(
            shipment.damage_report_status ==
            DamageStatusInWorkerAssignmnet.IN_PROGRESS.value
        )


    # ✅ NOW add aggregation and sorting
    stmt = stmt.group_by(
        shipment.id,
        header.id
    ).order_by(
        shipment.integrate_date_time.desc()
    )
    
    rows = (await db.execute(stmt)).all()

    # ─────────────────────────────────────────────────────────────────────
    # 📍 PICKED LOCATIONS for this page's shipments (one query, grouped)
    # ─────────────────────────────────────────────────────────────────────
    shipment_ids = [s.id for (s, h, d) in rows]

    pickups_by_shipment: dict[int, list] = {}
    if shipment_ids:
        pickup_rows = (await db.execute(
            select(ImportLocationPickup)
            .where(
                ImportLocationPickup.assignment_shipment_id.in_(shipment_ids),
                ImportLocationPickup.is_picked == True, # Only active picks (not send unpicked )
            )
            .order_by(ImportLocationPickup.picked_datetime.desc())
        )).scalars().all()

        for p in pickup_rows:
            pickups_by_shipment.setdefault(
                p.assignment_shipment_id, []
            ).append({
                "id": p.id,
                "location": p.location,
                "is_picked": p.is_picked,
                "picked_by": p.picked_by,
                "picked_datetime": p.picked_datetime,
                "unpicked_by": p.unpicked_by,
                "unpicked_datetime": p.unpicked_datetime,
            })

    # ----------------------------------------------------
    # 3️⃣ Shape response (flat JSON)
    # ----------------------------------------------------
    results = []
    for shipment, header, damages in rows:
        damages_list = json.loads(damages) if isinstance(damages, str) else damages
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

        "damage_report_status":shipment.damage_report_status,

        "flight_no": shipment.flight_no,
        "flight_date": shipment.flight_date,

        # TIMESTAMPS
        "created_at": shipment.created_at,
        "updated_at": shipment.updated_at,

        "damages": damages_list,
                    # 📍 picked locations for this shipment
            "picked_locations": pickups_by_shipment.get(shipment.id, []),

        })

    return results


# ----------------------------------------🫷🫷🫷🫷
# # ==========Assign a user to the worker assignment table row data =============================
# async def assign_user_to_worker_assignment(
#     *,
#     db: AsyncSession,
#     header_id: int,
#     shipment_id: int,
#     oc_no: str,
#     emp_id: str | None,          # None = unassign
#     current_user_role: str,
#     changed_by: str,
#     ip_address: str | None,
#     user_agent: str | None,
#     device_id: str | None,
# ):
#     try:
#         # ─────────────────────────────────────────────
#         # 1️⃣ FETCH HEADER
#         # ─────────────────────────────────────────────
#         header = (
#             await db.execute(
#                 select(WorkerAssignmentHeader)
#                 .where(WorkerAssignmentHeader.id == header_id)
#             )
#         ).scalars().first()

#         if not header:
#             raise HTTPException(404, "Invalid header_id")

#         if header.oc_no != oc_no:
#             raise HTTPException(400, "OC number mismatch with header")

#         # ─────────────────────────────────────────────
#         # 2️⃣ FETCH SHIPMENT
#         # ─────────────────────────────────────────────
#         shipment = (
#             await db.execute(
#                 select(WorkerAssignmentShipment)
#                 .where(
#                     WorkerAssignmentShipment.id == shipment_id,
#                     WorkerAssignmentShipment.assignment_header_id == header.id,
#                 )
#             )
#         ).scalars().first()

#         if not shipment:
#             raise HTTPException(404, "Shipment does not belong to this OC")

#         old_value = shipment.assigned_person
#         now = get_utc_now()

#         # ─────────────────────────────────────────────
#         # 3️⃣ NO CHANGE → EXIT
#         # ─────────────────────────────────────────────
#         if emp_id == old_value:
#             return True

#         # ─────────────────────────────────────────────
#         # 4️⃣ UNASSIGN
#         # ─────────────────────────────────────────────
#         if emp_id is None:
#             shipment.assigned_person = None
#             shipment.assigned_person_datetime = None
#             shipment.updated_at = now

#             await log_worker_assignment_audit(
#                 db=db,
#                 header=header,
#                 shipment=shipment,
#                 field_name="assigned_person",
#                 old_value=old_value,
#                 new_value=None,
#                 changed_by=changed_by,
#                 changed_by_role=current_user_role,
#                 ip_address=ip_address,
#                 device_id=device_id,
#                 user_agent=user_agent,
#                 db_action="UPDATE",
#                 source_action="unassign_user",
#             )

#             await db.commit()
#             return True

#         # ─────────────────────────────────────────────
#         # 5️⃣ VALIDATE WORKER
#         # ─────────────────────────────────────────────
#         user = (
#             await db.execute(
#                 select(User).where(
#                     User.emp_id == emp_id,
#                     User.role == "imp_gp_user",
#                     User.is_active.is_(True),
#                 )
#             )
#         ).scalars().first()

#         if not user:
#             raise HTTPException(
#                 400, f"Worker {emp_id} not found or inactive"
#             )

#         # ─────────────────────────────────────────────
#         # 6️⃣ ASSIGN WORKER
#         # ─────────────────────────────────────────────
#         shipment.assigned_person = emp_id
#         shipment.assigned_person_datetime = now
#         shipment.updated_at = now

#         await log_worker_assignment_audit(
#             db=db,
#             header=header,
#             shipment=shipment,
#             field_name="assigned_person",
#             old_value=old_value,
#             new_value=emp_id,
#             changed_by=changed_by,
#             changed_by_role=current_user_role,
#             ip_address=ip_address,
#             device_id=device_id,
#             user_agent=user_agent,
#             db_action="UPDATE",
#             source_action="assign_user",
#         )

#         await db.commit()
#         return True

#     except HTTPException:
#         await db.rollback()
#         raise

#     except Exception:
#         await db.rollback()
#         raise HTTPException(
#             status_code=500,
#             detail="Failed to assign worker"
#         )
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
    ENFORCE_TRACER_ALWAYS_ASSIGNED = True # It means in case of tracer flow tracer unser never unassign (not go assign a user to none in person)
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
        # 🔒 hold guard
        await assert_not_on_hold(db, shipment, header)

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

            # Prevent unassigning active tracer (future policy)
            # if (
            #     ENFORCE_TRACER_ALWAYS_ASSIGNED
            #     and shipment.damage_report_status in [
            #         DamageStatusInWorkerAssignmnet.NEED_TRACER.value,
            #         DamageStatusInWorkerAssignmnet.OPEN.value,
            #         DamageStatusInWorkerAssignmnet.IN_PROGRESS.value
            #     ]
            # ):
            #     raise HTTPException(
            #         400,
            #          "Cannot unassign. Shipment with damage must remain assigned to tracer"
            #     )
            if (
                ENFORCE_TRACER_ALWAYS_ASSIGNED
                and shipment.damage_report_status is not None
            ):
                raise HTTPException(
                    400,
                    "Cannot unassign. Shipment with damage must remain assigned to tracer"
                )


            # # Clear tracer status (optional)
            # if shipment.damage_report_status in [
            #     DamageStatusInWorkerAssignmnet.OPEN.value,
            #     DamageStatusInWorkerAssignmnet.IN_PROGRESS.value
            # ]:
            #     shipment.damage_report_status = None
            #     shipment.damage_resolve_datetime = None


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
        # 5️⃣ VALIDATE WORKER (OPS OR TRACER)
        # ─────────────────────────────────────────────

        user = (
            await db.execute(
                select(User).where(
                    User.emp_id == emp_id,
                    User.role.in_(["imp_gp_user", "imp_tracer"]),
                    User.is_active.is_(True),
                )
            )
        ).scalars().first()

        if not user:
            raise HTTPException(
                400, f"Worker {emp_id} not found, inactive, or invalid role"
            )


        is_tracer = user.role == "imp_tracer"

        # 🚫 Block assignment if shipment already resolved
        if shipment.damage_report_status == DamageStatusInWorkerAssignmnet.RESOLVED.value:
            raise HTTPException(
                400,
                "Shipment damages already resolved"
            )
        # 🚫 Block OPS assignment if ANY damage exists
        if (
            shipment.damage_report_status is not None
            and not is_tracer
        ):
            raise HTTPException(
                400,
                "Shipment has damage and requires tracer handling"
            )

        # ✅ ADD THIS BLOCK HERE
        # Prevent OPS assignment when shipment needs tracer
        if (
            shipment.damage_report_status
            == DamageStatusInWorkerAssignmnet.NEED_TRACER.value
            and not is_tracer
        ):
            raise HTTPException(
                400,
                "Shipment requires tracer user assignment"
            )



        # # Prevent ops overriding active tracer
        # if (
        #     shipment.damage_report_status in [
        #         DamageStatusInWorkerAssignmnet.IN_PROGRESS.value
        #     ]
        #     and not is_tracer
        # ):
        #     raise HTTPException(
        #         400,
        #         "Shipment is under tracer investigation"
        #     )


        # ─────────────────────────────────────────────
        # 6️⃣ ASSIGN USER
        # ─────────────────────────────────────────────

        shipment.assigned_person = emp_id
        shipment.assigned_person_datetime = now
        shipment.updated_at = now


        # Mark shipment under tracer (optional)
        # Mark shipment under tracer only if NEED_TRACER
        if (
            is_tracer
            and shipment.damage_report_status
            == DamageStatusInWorkerAssignmnet.NEED_TRACER.value
        ):
            shipment.damage_report_status = DamageStatusInWorkerAssignmnet.IN_PROGRESS.value



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

            source_action=(
                WorkerAssignmentAuditSource.TRACER_ASSIGN.value
                if is_tracer
                else WorkerAssignmentAuditSource.USER_ASSIGN.value
            ),
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
        # It check that comming dat is irm originated data
        is_irm_shipment = bool(header.temp_irm_oc_no)
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

        # 🔒 HOLD GUARD — block if shipment is on hold
        await assert_not_on_hold(db, shipment, header)

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
                detail="Shipment is assigned to another person"
            )
        # if irm shipment then only allow to add gaain drop dlv

        if shipment.drop_dlv_zone and not is_irm_shipment:
            raise HTTPException(
                status_code=400,
                detail="Drop delivery zone already added"
            )

        origin_source = detect_origin_source(header,shipment)

        # # ─────────────────────────────────────────────
        # # 4️⃣ Update SHIPMENT
        # # ─────────────────────────────────────────────
        # old_value = shipment.drop_dlv_zone
        # now = get_utc_now()

        # await db.execute(
        #     update(WorkerAssignmentShipment)
        #     .where(WorkerAssignmentShipment.id == shipment.id)
        #     .values(
        #         drop_dlv_zone=drop_dlv_zone,
        #         drop_dlv_zone_datetime=now,
        #         updated_at=now,
        #     )
        # )

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
        # Get fresh damage status
        # ─────────────────────────────────────────────
        current_damage_status = (
            await db.execute(
                select(WorkerAssignmentShipment.damage_report_status)
                .where(WorkerAssignmentShipment.id == shipment.id)
            )
        ).scalar_one()


        # ─────────────────────────────────────────────
        # 4.1️⃣ AUTO RESOLVE DAMAGE (TRACER ONLY)
        # ─────────────────────────────────────────────

        if (
            current_user_role == "imp_tracer"
            and current_damage_status in [
                DamageStatusInWorkerAssignmnet.OPEN.value,
                DamageStatusInWorkerAssignmnet.IN_PROGRESS.value,
            ]
        ):

            await db.execute(
                update(WorkerAssignmentShipment)
                .where(WorkerAssignmentShipment.id == shipment.id)
                .values(
                    damage_report_status=DamageStatusInWorkerAssignmnet.RESOLVED.value,
                    damage_resolve_datetime=now,
                    updated_at=now,
                )
            )

            await db.execute(
                update(DamageReport)
                .where(
                    DamageReport.assignment_shipment_id == shipment.id,
                    DamageReport.status != "resolved",
                )
                .values(
                    status="resolved",
                    resolved_date_time=now,
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
            origin_source_type=origin_source.value,
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

    # ─────────────────────────────────────────────────────────────────────
    # 🔒(New addon) ACTIVE SHIPMENT HOLDS (≈30 rows) — load once, match in memory
    # ─────────────────────────────────────────────────────────────────────
    hold_oc: set = set()
    hold_boe: set = set()
    hold_gp: set = set()
    hold_awb_hawb: set = set()   # (awb_no, hawb_or_empty)

    hold_rows = (await db.execute(
        select(
            ImportShipmentHold.hold_type,
            ImportShipmentHold.awb_no,
            ImportShipmentHold.hawb,
            ImportShipmentHold.oc_no,
            ImportShipmentHold.boe_no,
            ImportShipmentHold.gate_pass_no,
        ).where(ImportShipmentHold.is_active == True)
    )).all()

    for h in hold_rows:
        if h.hold_type == "OC" and h.oc_no:
            hold_oc.add(h.oc_no.strip())
        elif h.hold_type == "BOE" and h.boe_no:
            hold_boe.add(h.boe_no.strip())
        elif h.hold_type == "GP" and h.gate_pass_no:
            hold_gp.add(h.gate_pass_no.strip())
        elif h.hold_type == "AWB_HAWB" and h.awb_no:
            hold_awb_hawb.add((h.awb_no.strip(), (h.hawb or "").strip()))

    def _is_on_hold(shipment, header) -> bool:
        # OC / AWB+HAWB → header level (locks all part shipments)
        if header.oc_no and header.oc_no.strip() in hold_oc:
            return True
        if header.awb_no and (
            header.awb_no.strip(), (header.hawb or "").strip()
        ) in hold_awb_hawb:
            return True
        # BOE / GP → this shipment row only
        if shipment.boe_no and shipment.boe_no.strip() in hold_boe:
            return True
        if shipment.gate_pass_no and shipment.gate_pass_no.strip() in hold_gp:
            return True
        return False

    # ─────────────────────────────────────────────────────────────────────
    # ✌️NON-COSYS truck-in-out visits for this page's GPs (batched — 2 queries max)
    # ─────────────────────────────────────────────────────────────────────
    page_gp_nos = [
        s.gate_pass_no for (s, h) in rows
        if s.gate_pass_no and s.gate_pass_no.strip()
    ]

    cosys_by_gp: Dict[str, list] = {}
    if page_gp_nos:
        cosys_rows = (await db.execute( 
            select(
                ImportGatePass.gate_pass_no,
                ImportTruckVisit.id.label("visit_id"),
                ImportTruckVisit.visit_type,
                ImportTruckVisit.truck_number,
                ImportTruckVisit.driver_name,
                ImportTruckVisit.driver_contact,
                ImportTruckVisit.truck_in_date_time,
                ImportTruckVisit.truck_out_date_time,
                ImportTruckVisit.truck_in_by,
                ImportTruckVisit.truck_out_by,
                ImportTruckVisit.is_truck_in,
                ImportTruckVisit.is_truck_out,
                ImportTruckVisit.token_no,
                ImportTruckVisit.queue_no,
                ImportGatePassAssignment.is_active.label("assignment_active"),
            )
            .join(ImportGatePassAssignment,
                  ImportGatePassAssignment.gate_pass_id == ImportGatePass.id)
            .join(ImportTruckVisit,
                  ImportTruckVisit.id == ImportGatePassAssignment.truck_visit_id)
            .where(ImportGatePass.gate_pass_no.in_(page_gp_nos))
            .order_by(ImportTruckVisit.truck_in_date_time.desc().nullslast())
        )).all()

        # Resolve in-by / out-by emp_ids → names in ONE query
        emp_ids = set()
        for r in cosys_rows:
            if r.truck_in_by:
                emp_ids.add(r.truck_in_by)
            if r.truck_out_by:
                emp_ids.add(r.truck_out_by)

        name_map: Dict[str, str] = {}
        if emp_ids:
            users = (await db.execute(
                select(User.emp_id, User.name).where(User.emp_id.in_(emp_ids))
            )).all()
            name_map = {u.emp_id: u.name for u in users}

        # Group visits per GP (already newest-first from ORDER BY)
        for r in cosys_rows:
            is_by_hand = (r.visit_type == "BY_HAND")
            cosys_by_gp.setdefault(r.gate_pass_no, []).append({
                "non_cosys_visit_id":          r.visit_id,
                "non_cosys_is_by_hand":        is_by_hand,
                "non_cosys_truck_no":          r.truck_number,        # None for by-hand
                "non_cosys_driver_name":       r.driver_name,
                "non_cosys_driver_contact":    r.driver_contact,
                "non_cosys_truck_in":          r.truck_in_date_time,
                "non_cosys_truck_out":         r.truck_out_date_time,
                "non_cosys_truck_in_by":       r.truck_in_by,
                "non_cosys_truck_in_by_name":  name_map.get(r.truck_in_by),
                "non_cosys_truck_out_by":      r.truck_out_by,
                "non_cosys_truck_out_by_name": name_map.get(r.truck_out_by),
                "non_cosys_is_truck_in":       bool(r.is_truck_in),
                "non_cosys_is_truck_out":      bool(r.is_truck_out),
                "non_cosys_token_no":          r.token_no,
                "non_cosys_queue_no":          r.queue_no,
                "non_cosys_assignment_active": bool(r.assignment_active),
            })
# =================================================================================
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
        is_hold = _is_on_hold(shipment, header)   # 🔒 add this line
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

            "damage_report_status":shipment.damage_report_status,
            "damage_resolve_datetime":shipment.damage_resolve_datetime,
            "is_final_delivered":shipment.is_final_delivered,
            "loading_in_lift_zone":shipment.loading_in_lift_zone,
            "loading_in_lift_zone_datetime":shipment.loading_in_lift_zone_datetime,
            "loading_in_lift_person":shipment.loading_in_lift_person,
            "unloading_from_lift_zone":shipment.unloading_from_lift_zone,
            "unloading_from_lift_zone_datetime":shipment.unloading_from_lift_zone_datetime,
            "unloading_from_lift_person":shipment.unloading_from_lift_person,

            "gp_received_by":shipment.gp_received_by,
            "gp_received_datetime":shipment.gp_received_datetime,
            "final_delivery_datetime":shipment.final_delivery_datetime,

            "truck_no":shipment.truck_no,
            "truck_in_datetime":shipment.truck_in_datetime,
            "truck_out_datetime":shipment.truck_out_datetime,

             # ── NON-COSYS truck-in-out module visits (list — a GP can be on many) ──
            "non_cosys_truck_visits": cosys_by_gp.get(shipment.gate_pass_no, []),

              "is_hold": is_hold,   # 🔒 add this field


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
        shipment_dict = model_to_dict(shipment)
        shipment_dict.update({
            "oc_no": header.oc_no,
            "awb_no": header.awb_no,
            "hawb": header.hawb,
            "temp_irm_oc_no": header.temp_irm_oc_no,
        })
        response_list.append(shipment_dict)

    # ============================================================
    # 🆕 ENRICH: Add *_name fields by looking up users by emp_id
    # ============================================================
    USER_ID_FIELDS = [
        "assigned_person",
        # "verified_by",
        "loading_in_lift_person",
        "unloading_from_lift_person",
        "final_delivery_by_person",
        "gp_received_by",
    ]

    # 1. Collect all unique emp_ids across all records
    emp_ids = set()
    for row in response_list:
        for field in USER_ID_FIELDS:
            val = row.get(field)
            if val:
                emp_ids.add(val)

    # 2. One query → fetch all needed user names
    users_map = {}
    if emp_ids:
        res = await db.execute(
            select(User.emp_id, User.name).where(User.emp_id.in_(emp_ids))
        )
        users_map = {u.emp_id: u.name for u in res.fetchall()}

    # 3. Inject *_name field next to each emp_id field
    for row in response_list:
        for field in USER_ID_FIELDS:
            emp_id_val = row.get(field)
            row[f"{field}_name"] = users_map.get(emp_id_val) if emp_id_val else None

    return response_list

# async def search_in_worker_assignments(
#     db: AsyncSession,
#     search_type: str,
#     search_value: str
# ):

#     header_fields = {
#         "oc_no": WorkerAssignmentHeader.oc_no,
#         "awb": WorkerAssignmentHeader.awb_no,
#         "hawb": WorkerAssignmentHeader.hawb,
#         "temp_oc": WorkerAssignmentHeader.temp_irm_oc_no,
#     }

#     shipment_fields = {
#         "gp_no": WorkerAssignmentShipment.gate_pass_no,
#     }
#     def model_to_dict(obj):
#         return {
#             column.name: getattr(obj, column.name)
#             for column in obj.__table__.columns
#         }


#     # ----------------------------------------------------------------
#     # 1️⃣ HEADER SEARCH
#     # ----------------------------------------------------------------
#     if search_type in header_fields:
#         column = header_fields[search_type]

#         stmt = (
#             select(WorkerAssignmentShipment, WorkerAssignmentHeader)
#             .join(
#                 WorkerAssignmentHeader,
#                 WorkerAssignmentShipment.assignment_header_id == WorkerAssignmentHeader.id
#             )
#             .where(column == search_value)
#         )

#     # ----------------------------------------------------------------
#     # 2️⃣ SHIPMENT SEARCH
#     # ----------------------------------------------------------------
#     elif search_type in shipment_fields:
#         column = shipment_fields[search_type]

#         stmt = (
#             select(WorkerAssignmentShipment, WorkerAssignmentHeader)
#             .join(
#                 WorkerAssignmentHeader,
#                 WorkerAssignmentShipment.assignment_header_id == WorkerAssignmentHeader.id
#             )
#             .where(func.lower(column).contains(search_value.lower()))
#         )

#     else:
#         return []

#     result = await db.execute(stmt)
#     rows = result.all()

#     response_list = []

#     for shipment, header in rows:

#         # Convert shipment model → dictionary (ALL columns)
#         shipment_dict = model_to_dict(shipment)

#         # Add header identity fields manually
#         shipment_dict.update({
#             "oc_no": header.oc_no,
#             "awb_no": header.awb_no,
#             "hawb": header.hawb,
#             "temp_irm_oc_no": header.temp_irm_oc_no,
#         })

#         response_list.append(shipment_dict)

#     return response_list

# 👌👌=================== EXPORT WORKER ASSIGNMNET REPORT BASED ON FILTERD (STREAMING) ===================
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
        'From Source', 'Integrate Date', 'Created At','GP Received Time', 'Final delivery Time'
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
        27: 18,  # Created At
        28: 18,  # GP Received Datetime
        29: 18  # Final Delivery datetime
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
            # gp_received_datetime At (from SHIPMENT)
            if shipment.gp_received_datetime:
                worksheet.write_datetime(row_num, 28, to_ist_no_tz(shipment.gp_received_datetime), date_format)
            else:
                worksheet.write(row_num, 28, '', text_format)
            # gp_received_datetime At (from SHIPMENT)
            if shipment.final_delivery_datetime:
                worksheet.write_datetime(row_num, 29, to_ist_no_tz(shipment.final_delivery_datetime), date_format)
            else:
                worksheet.write(row_num, 29, '', text_format)
            
            row_num += 1
        
        offset += chunk_size
    
    # Close workbook to finalize
    workbook.close()
    
    # Seek to beginning
    output.seek(0)
    
    # Yield the complete file
    yield output.read()

# 🫷 Ageing report for worker assignment---------

async def generate_ageing_report_for_worker_assignment(
    db: AsyncSession,
    assignment_status: str,
    start_date: str,
    end_date: str,
    chunk_size: int = 1000
) -> AsyncGenerator[bytes, None]:
    """
    AGEING REPORT
    - Only active Gatepasses
    - Excludes completed GP
    - Uses Header + Shipment
    """

    # ================= BUFFER =================

    output = io.BytesIO()

    workbook = xlsxwriter.Workbook(output, {"in_memory": True})
    worksheet = workbook.add_worksheet("Ageing Report")

    # ================= FORMATS =================

    header_format = workbook.add_format({
        "bold": True,
        "border": 1,
        "align": "center",
        "valign": "vcenter"
    })

    text_format = workbook.add_format({
        "align": "left",
        "border": 1
    })

    number_format = workbook.add_format({
        "align": "right",
        "border": 1,
        "num_format": "0.00"
    })

    int_format = workbook.add_format({
        "align": "right",
        "border": 1,
        "num_format": "0"
    })

    date_format = workbook.add_format({
        "align": "left",
        "border": 1,
        "num_format": "dd/mm/yyyy hh:mm"
    })

    center_format = workbook.add_format({
        "align": "center",
        "border": 1
    })

    # ================= HEADERS =================

    headers = [
        "S.No",
        "Gate Pass No",
        "AWB No",
        "HAWB",
        "No of Pieces",
        "Weight (KG)",
        "GP Issue Date",
        "GP End Date",
        "Assigned Person Name",
        "Assigned DateTime",
        "Drop Delivery Zone",
        "Drop DLV DateTime",
    ]

    for col, h in enumerate(headers):
        worksheet.write(0, col, h, header_format)
        worksheet.set_column(col, col, 18)

    worksheet.freeze_panes(1, 0)

    # ================= QUERY =================

    UserAlias = aliased(User)

    filters = WorkerAssignmentFilters(
        shipment_model=WorkerAssignmentShipment,
        status=assignment_status,
        startDate=start_date,
        endDate=end_date
    )

    # 🔥 JOIN HEADER + SHIPMENT (same as default)
    base_query = (
        filters.apply_all(
            select(
                WorkerAssignmentHeader,
                WorkerAssignmentShipment,
                UserAlias.name.label("assigned_person_name")
            )
            .join(
                WorkerAssignmentShipment,
                WorkerAssignmentHeader.id ==
                WorkerAssignmentShipment.assignment_header_id
            )
            .outerjoin(
                UserAlias,
                UserAlias.emp_id ==
                WorkerAssignmentShipment.assigned_person
            )
        )

        # 🔥 Exclude completed GP
        .where(
            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None)
        )

        .order_by(
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.asc()
        )
    )

    # ================= IST CONVERTER =================

    IST = pytz.timezone("Asia/Kolkata")

    def to_ist(dt):
        if not dt:
            return None

        if dt.tzinfo:
            dt = dt.astimezone(IST)

        return dt.replace(tzinfo=None)

    # ================= STREAM =================

    row_num = 1
    offset = 0

    while True:

        result = await db.execute(
            base_query.offset(offset).limit(chunk_size)
        )

        rows = result.all()

        if not rows:
            break

        # Each row = (header, shipment, name)
        for header, shipment, assigned_person_name in rows:

            worksheet.write(row_num, 0, row_num, center_format)

            # Gate Pass
            worksheet.write(row_num, 1, shipment.gate_pass_no or "", text_format)

            # AWB / HAWB from HEADER ✅
            worksheet.write(row_num, 2, header.awb_no or "", text_format)
            worksheet.write(row_num, 3, header.hawb or "", text_format)

            # PCS
            if shipment.no_of_pc is not None:
                worksheet.write_number(row_num, 4, shipment.no_of_pc, int_format)
            else:
                worksheet.write_blank(row_num, 4, None)

            # Weight
            if shipment.weight_in_kgs is not None:
                worksheet.write_number(
                    row_num, 5, shipment.weight_in_kgs, number_format
                )
            else:
                worksheet.write_blank(row_num, 5, None)

            # GP Issue Date
            if shipment.gate_pass_issued_date_time_combo:
                worksheet.write_datetime(
                    row_num,
                    6,
                    to_ist(shipment.gate_pass_issued_date_time_combo),
                    date_format
                )
            else:
                worksheet.write(row_num, 6, "", text_format)

            # GP End Date (always empty)
            worksheet.write(row_num, 7, "", text_format)

            # Assigned Name
            worksheet.write(row_num, 8, assigned_person_name or "", text_format)

            # Assigned Date
            if shipment.assigned_person_datetime:
                worksheet.write_datetime(
                    row_num,
                    9,
                    to_ist(shipment.assigned_person_datetime),
                    date_format
                )
            else:
                worksheet.write(row_num, 9, "", text_format)

            # Drop Zone
            worksheet.write(row_num, 10, shipment.drop_dlv_zone or "", text_format)

            # Drop Time
            if shipment.drop_dlv_zone_datetime:
                worksheet.write_datetime(
                    row_num,
                    11,
                    to_ist(shipment.drop_dlv_zone_datetime),
                    date_format
                )
            else:
                worksheet.write(row_num, 11, "", text_format)

            row_num += 1

        offset += chunk_size

    workbook.close()
    output.seek(0)

    yield output.read()

# Full report with steps timeline for worker assignment
async def generate_excel_stream_export_worker_assignment_with_step_timeline(
    db: AsyncSession,
    assignment_status: str,
    start_date: str,
    end_date: str,
    chunk_size: int = 1000,
    time_diff_format: str = "decimal"  # "decimal" -> 3.75  |  "hm" -> "3h 45m"
) -> AsyncGenerator[bytes, None]:
    """
    Async generator that streams Excel file in chunks (STEP-TIMELINE report).

    Superset of `generate_excel_stream_export_worker_assignment`:
    - Includes all base columns
    - Adds lift loading / unloading datetimes
    - Adds step-by-step time-diff columns (decimal hours by default)
    - Column order matches the frontend UserAssignmentTable
    - Negative time diffs are shown (in RED) to flag data ordering issues

    Args:
        time_diff_format: "decimal" -> writes decimal hours (e.g. 3.75) [DEFAULT]
                         "hm"      -> writes string format (e.g. "3h 45m")
    """

    # -------------------------------------------------------------------------
    # Setup workbook
    # -------------------------------------------------------------------------
    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('Worker Assignments Timeline')

    # ---- Formats ----
    header_format = workbook.add_format({
        'bold': True,
        'border': 1,
        'align': 'center',
        'valign': 'vcenter',
        'text_wrap': True,
        'bg_color': '#F3F4F6'
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
    decimal_hours_format = workbook.add_format({
        'num_format': '0.00',
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

    # 🔴 Negative-value formats (to flag data ordering issues)
    negative_hours_format = workbook.add_format({
        'num_format': '0.00',
        'align': 'right',
        'font_color': '#DC2626',  # red
        'bold': True
    })
    negative_hm_format = workbook.add_format({
        'align': 'right',
        'font_color': '#DC2626',
        'bold': True
    })

    # -------------------------------------------------------------------------
    # Column definitions (ORDER MATCHES FRONTEND TABLE)
    # -------------------------------------------------------------------------
    diff_header_suffix = "(hrs)" if time_diff_format == "decimal" else "(h m)"

    headers = [
        'S.No',                                        # 0
        f'SLA Time Diff {diff_header_suffix}',         # 1
        'OC No',                                       # 2
        'Gate Pass No',                                # 3
        'Gate Pass Issue Date',                        # 4
        'AWB',                                         # 5
        'HAWB',                                        # 6
        'Pcs',                                         # 7
        'Gross Wgt',                                   # 8
        'GP Received Time (by security)',              # 9
        'Operator Emp ID',                             # 10
        'Operator Name',                               # 11
        'Operator Assigned Date/Time',                 # 12
        f'GP Issued vs Opr Assign {diff_header_suffix}',  # 13
        'From Where',                                  # 14
        'Location',                                    # 15
        'Drop Dlv Zone',                               # 16
        'Drop Dlv Zone Date/Time',                     # 17
        f'Assign vs Lift Drop {diff_header_suffix}',   # 18
        'Lift Loading Date Time',                      # 19
        f'Lift Drop vs Lift Loading {diff_header_suffix}',  # 20
        'Lift Unloading Date Time',                    # 21
        f'Lift Loading vs Lift Unloading {diff_header_suffix}',  # 22
        'Final Delivery Time (by security)',           # 23
        f'Final Delivery vs Lift Unloading {diff_header_suffix}',  # 24
        f'GP Issue vs Final Delivery {diff_header_suffix}',  # 25
        f'GP Received vs Final Delivery {diff_header_suffix}',  # 26
        'Gatepass End Datetime (COSYS)',               # 27

        # 🆕 Truck section
    'Truck In Date/Time',                          # 28
    'Truck Number',                                # 29
    'Truck Out Date/Time',                         # 30
    f'Truck In vs Truck Out {diff_header_suffix}',              # 31
    f'GP Issue vs Truck In {diff_header_suffix}',               # 32
    f'Final Delivery vs Truck In {diff_header_suffix}',         # 33
    f'Final Delivery vs Truck Out {diff_header_suffix}',        # 34
    f'GP End (COSYS) vs Truck In {diff_header_suffix}',         # 35
    f'GP End (COSYS) vs Truck Out {diff_header_suffix}',        # 36
    f'GP Received vs Truck In {diff_header_suffix}',            # 37
    f'GP Received vs Truck Out {diff_header_suffix}',           # 38
    # ---- tail (shifted) ----
    'Integrated At',                               # 39
    'Temp IRM OC No',                              # 40
    'CHG Wgt',                                     # 41
    'Damage Report Status',                        # 42

       
    ]

    # Write headers
    for col_num, header in enumerate(headers):
        worksheet.write(0, col_num, header, header_format)

    # Column widths
    column_widths = {
        0: 6,    # S.No
        1: 14,   # SLA Time Diff
        2: 15,   # OC No
        3: 18,   # Gate Pass No
        4: 18,   # GP Issue Date
        5: 18,   # AWB
        6: 18,   # HAWB
        7: 8,    # Pcs
        8: 12,   # Gross Wgt
        9: 18,   # GP Received Time
        10: 14,  # Operator Emp ID
        11: 25,  # Operator Name
        12: 18,  # Operator Assigned DateTime
        13: 16,  # GP Issued vs Opr Assign
        14: 12,  # From Where
        15: 30,  # Location
        16: 18,  # Drop Dlv Zone
        17: 18,  # Drop Dlv Zone Date/Time
        18: 16,  # Assign vs Lift Drop
        19: 18,  # Lift Loading Date Time
        20: 16,  # Lift Drop vs Lift Loading
        21: 18,  # Lift Unloading Date Time
        22: 16,  # Lift Loading vs Lift Unloading
        23: 18,  # Final Delivery Time
        24: 16,  # Final Delivery vs Lift Unloading
        25: 16,  # GP Issue vs Final Delivery
        26: 16,  # GP Received vs Final Delivery
        27: 18,  # Gatepass End Datetime (COSYS)
        # 🆕 Truck section
    28: 18,  # Truck In Date/Time
    29: 16,  # Truck Number
    30: 18,  # Truck Out Date/Time
    31: 16,  # Truck In vs Truck Out
    32: 16,  # GP Issue vs Truck In
    33: 16,  # Final Delivery vs Truck In
    34: 16,  # Final Delivery vs Truck Out
    35: 16,  # GP End (COSYS) vs Truck In
    36: 16,  # GP End (COSYS) vs Truck Out
    37: 16,  # GP Received vs Truck In
    38: 16,  # GP Received vs Truck Out
    # ---- tail (shifted) ----
    39: 18,  # Integrated At
    40: 15,  # Temp IRM OC No
    41: 12,  # CHG Wgt
    42: 18,  # Damage Report Status
    }
    for col, width in column_widths.items():
        worksheet.set_column(col, col, width)

    worksheet.freeze_panes(1, 0)

    # -------------------------------------------------------------------------
    # Date parsing
    # -------------------------------------------------------------------------
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()

    # -------------------------------------------------------------------------
    # Query construction (same pattern as base export)
    # -------------------------------------------------------------------------
    UserAlias = aliased(User)

    filters = WorkerAssignmentFilters(
        shipment_model=WorkerAssignmentShipment,
        status=assignment_status,
        startDate=start_date,
        endDate=end_date
    )

    base_query = (
        filters.apply_all(
            select(
                WorkerAssignmentHeader,
                WorkerAssignmentShipment,
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

    base_query = base_query.order_by(
        WorkerAssignmentShipment.gate_pass_no.is_(None),
        WorkerAssignmentShipment.gate_pass_no.asc(),
        WorkerAssignmentHeader.oc_no.asc()
    )

    # -------------------------------------------------------------------------
    # Helpers
    # -------------------------------------------------------------------------
    IST = pytz.timezone("Asia/Kolkata")

    def to_ist_no_tz(dt):
        """UTC -> IST naive datetime (for Excel)."""
        if not dt:
            return None
        if dt.tzinfo:
            dt = dt.astimezone(IST)
        return dt.replace(tzinfo=None)

    def get_source_label(header, shipment):
        if shipment.from_irr_table and not header.temp_irm_oc_no:
            return "IRR"
        if header.temp_irm_oc_no and not shipment.from_irr_table:
            return "IRM"
        if not header.temp_irm_oc_no and not shipment.from_irr_table:
            return "OC MERGE"
        return ""

    def compute_diff_hours(start_dt, end_dt):
        """
        Return diff in hours as float (decimal).
        Returns None ONLY if dates are missing.
        Negative values are returned as-is (indicates data ordering issue).
        """
        if not start_dt or not end_dt:
            return None
        try:
            # Both should be tz-aware (UTC from DB) -> safe subtraction
            delta_seconds = (end_dt - start_dt).total_seconds()
            return delta_seconds / 3600.0
        except Exception:
            return None

    def write_diff(row_num, col_num, start_dt, end_dt):
        """
        Write a time diff cell in the chosen format.
        decimal -> number (3.75, or -2.50 for negative)
        hm      -> string ("3h 45m", or "-2h 30m" for negative)
        Negative values are highlighted in red bold.
        """
        hours = compute_diff_hours(start_dt, end_dt)
        if hours is None:
            worksheet.write(row_num, col_num, '', text_format)
            return

        is_negative = hours < 0

        if time_diff_format == "decimal":
            fmt = negative_hours_format if is_negative else decimal_hours_format
            worksheet.write_number(row_num, col_num, round(hours, 2), fmt)
        else:
            abs_hours = abs(hours)
            h = int(abs_hours)
            m = int(round((abs_hours - h) * 60))
            sign = "-" if is_negative else ""
            fmt = negative_hm_format if is_negative else text_format
            worksheet.write(row_num, col_num, f"{sign}{h}h {m}m", fmt)

    def compute_sla_diff_hours(shipment):
        """
        SLA: from gp_received_datetime to final_delivery_datetime.
        If final_delivery_datetime is null -> use current time (export time).
        """
        if not shipment.gp_received_datetime:
            return None

        end_dt = shipment.final_delivery_datetime
        if not end_dt:
            # Use current UTC time (tz-aware to match DB datetimes)
            end_dt = datetime.now(pytz.UTC)

        return compute_diff_hours(shipment.gp_received_datetime, end_dt)

    def write_sla(row_num, col_num, shipment):
        hours = compute_sla_diff_hours(shipment)
        if hours is None:
            worksheet.write(row_num, col_num, '', text_format)
            return

        is_negative = hours < 0

        if time_diff_format == "decimal":
            fmt = negative_hours_format if is_negative else decimal_hours_format
            worksheet.write_number(row_num, col_num, round(hours, 2), fmt)
        else:
            abs_hours = abs(hours)
            h = int(abs_hours)
            m = int(round((abs_hours - h) * 60))
            sign = "-" if is_negative else ""
            fmt = negative_hm_format if is_negative else text_format
            worksheet.write(row_num, col_num, f"{sign}{h}h {m}m", fmt)

    def write_dt(row_num, col_num, dt_value):
        """Write datetime or blank."""
        if dt_value:
            worksheet.write_datetime(row_num, col_num, to_ist_no_tz(dt_value), date_format)
        else:
            worksheet.write(row_num, col_num, '', text_format)

    # -------------------------------------------------------------------------
    # Stream rows
    # -------------------------------------------------------------------------
    row_num = 1
    offset = 0

    while True:
        chunk_query = base_query.offset(offset).limit(chunk_size)
        result = await db.execute(chunk_query)
        chunk = result.all()

        if not chunk:
            break

        for header, shipment, assigned_person_name in chunk:

            # 0 - S.No
            worksheet.write(row_num, 0, row_num, text_center)

            # 1 - SLA Time Diff (gp_received -> final_delivery OR now)
            write_sla(row_num, 1, shipment)

            # 2 - OC No (header)
            worksheet.write(row_num, 2, header.oc_no or '', text_format)

            # # 3 - Gate Pass No
            # worksheet.write(row_num, 3, shipment.gate_pass_no or '', text_format)
            
            # 3 - Gate Pass No (numeric if possible, blank otherwise)
            if shipment.gate_pass_no is not None and str(shipment.gate_pass_no).strip().isdigit():
                worksheet.write_number(row_num, 3, int(shipment.gate_pass_no), integer_format)
            else:
                worksheet.write_blank(row_num, 3, None)

            # 4 - Gate Pass Issue Date
            write_dt(row_num, 4, shipment.gate_pass_issued_date_time_combo)

            # 5 - AWB (header)
            worksheet.write(row_num, 5, header.awb_no or '', text_format)

            # 6 - HAWB (header)
            worksheet.write(row_num, 6, header.hawb or '', text_format)

            # 7 - Pcs
            if shipment.no_of_pc is not None:
                worksheet.write_number(row_num, 7, shipment.no_of_pc, integer_format)
            else:
                worksheet.write_blank(row_num, 7, None)

            # 8 - Gross Wgt
            if shipment.weight_in_kgs is not None:
                worksheet.write_number(row_num, 8, shipment.weight_in_kgs, number_format)
            else:
                worksheet.write_blank(row_num, 8, None)

            # 9 - GP Received Time
            write_dt(row_num, 9, shipment.gp_received_datetime)

            # 10 - Operator Emp ID (as number when possible)
            if shipment.assigned_person is not None and str(shipment.assigned_person).strip().isdigit():
                worksheet.write_number(row_num, 10, int(shipment.assigned_person), integer_format)
            else:
                worksheet.write(row_num, 10, shipment.assigned_person or '', text_format)

            # 11 - Operator Name
            worksheet.write(row_num, 11, assigned_person_name or '', text_format)

            # 12 - Operator Assigned Date/Time
            write_dt(row_num, 12, shipment.assigned_person_datetime)

            # 13 - GP Issued vs Opr Assign
            write_diff(
                row_num, 13,
                shipment.gate_pass_issued_date_time_combo,
                shipment.assigned_person_datetime
            )

            # 14 - From Where
            worksheet.write(row_num, 14, get_source_label(header, shipment), text_center)

            # 15 - Location
            worksheet.write(row_num, 15, shipment.location or '', text_format)

            # 16 - Drop Dlv Zone
            worksheet.write(row_num, 16, shipment.drop_dlv_zone or '', text_format)

            # 17 - Drop Dlv Zone Date/Time
            write_dt(row_num, 17, shipment.drop_dlv_zone_datetime)

            # 18 - Assign vs Lift Drop
            write_diff(
                row_num, 18,
                shipment.assigned_person_datetime,
                shipment.drop_dlv_zone_datetime
            )

            # 19 - Lift Loading Date Time
            write_dt(row_num, 19, shipment.loading_in_lift_zone_datetime)

            # 20 - Lift Drop vs Lift Loading
            write_diff(
                row_num, 20,
                shipment.drop_dlv_zone_datetime,
                shipment.loading_in_lift_zone_datetime
            )

            # 21 - Lift Unloading Date Time
            write_dt(row_num, 21, shipment.unloading_from_lift_zone_datetime)

            # 22 - Lift Loading vs Lift Unloading
            write_diff(
                row_num, 22,
                shipment.loading_in_lift_zone_datetime,
                shipment.unloading_from_lift_zone_datetime
            )

            # 23 - Final Delivery Time
            write_dt(row_num, 23, shipment.final_delivery_datetime)

            # 24 - Final Delivery vs Lift Unloading
            write_diff(
                row_num, 24,
                shipment.unloading_from_lift_zone_datetime,
                shipment.final_delivery_datetime
            )

            # 25 - GP Issue vs Final Delivery
            write_diff(
                row_num, 25,
                shipment.gate_pass_issued_date_time_combo,
                shipment.final_delivery_datetime
            )

            # 26 - GP Received vs Final Delivery
            write_diff(
                row_num, 26,
                shipment.gp_received_datetime,
                shipment.final_delivery_datetime
            )

            # 27 - Gatepass End Datetime (COSYS)
            write_dt(row_num, 27, shipment.gate_pass_end_datetime)

            # 🆕 ── Truck section ───────────────────────────────────────────

            # 28 - Truck In Date/Time
            write_dt(row_num, 28, shipment.truck_in_datetime)

            # 29 - Truck Number
            worksheet.write(row_num, 29, shipment.truck_no or '', text_format)

            # 30 - Truck Out Date/Time
            write_dt(row_num, 30, shipment.truck_out_datetime)

            # 31 - Truck In vs Truck Out
            write_diff(
                row_num, 31,
                shipment.truck_in_datetime,
                shipment.truck_out_datetime
            )

            # 32 - GP Issue vs Truck In
            write_diff(
                row_num, 32,
                shipment.gate_pass_issued_date_time_combo,
                shipment.truck_in_datetime
            )

            # 33 - Final Delivery vs Truck In
            write_diff(
                row_num, 33,
                shipment.truck_in_datetime,
                shipment.final_delivery_datetime
            )

            # 34 - Final Delivery vs Truck Out
            write_diff(
                row_num, 34,
                shipment.truck_out_datetime,
                shipment.final_delivery_datetime
            )

            # 35 - GP End (COSYS) vs Truck In
            write_diff(
                row_num, 35,
                shipment.gate_pass_end_datetime,
                shipment.truck_in_datetime
            )

            # 36 - GP End (COSYS) vs Truck Out
            write_diff(
                row_num, 36,
                shipment.gate_pass_end_datetime,
                shipment.truck_out_datetime
            )

            # 37 - GP Received vs Truck In
            write_diff(
                row_num, 37,
                shipment.gp_received_datetime,
                shipment.truck_in_datetime
            )

            # 38 - GP Received vs Truck Out
            write_diff(
                row_num, 38,
                shipment.gp_received_datetime,
                shipment.truck_out_datetime
            )

            # 🆕 ── End truck section ───────────────────────────────────────

            # 39 - Integrated At
            write_dt(row_num, 39, shipment.integrate_date_time)

            # 40 - Temp IRM OC No (header)
            worksheet.write(row_num, 40, header.temp_irm_oc_no or '', text_format)

            # 41 - CHG Wgt
            if shipment.chg_wgt_in_kg is not None:
                worksheet.write_number(row_num, 41, shipment.chg_wgt_in_kg, number_format)
            else:
                worksheet.write_blank(row_num, 41, None)

            # 42 - Damage Report Status
            worksheet.write(row_num, 42, shipment.damage_report_status or '', text_format)

            row_num += 1

        offset += chunk_size

    # -------------------------------------------------------------------------
    # METADATA FOOTER
    # -------------------------------------------------------------------------
    # Leave 2 empty rows after data, then write metadata
    meta_start_row = row_num + 2

    # Metadata-specific formats
    meta_label_format = workbook.add_format({
        'bold': True,
        'align': 'left',
        'valign': 'vcenter',
        'bg_color': '#E5E7EB',
        'border': 1
    })
    meta_value_format = workbook.add_format({
        'align': 'left',
        'valign': 'vcenter',
        'text_wrap': True,
        'border': 1
    })
    meta_section_format = workbook.add_format({
        'bold': True,
        'font_size': 11,
        'align': 'left',
        'valign': 'vcenter',
        'bg_color': '#1F2937',
        'font_color': '#FFFFFF',
        'border': 1
    })

    # IST current time (for "downloaded at")
    now_ist = datetime.now(pytz.UTC).astimezone(IST).replace(tzinfo=None)

    # ---- Section 1: File metadata ----
    worksheet.merge_range(meta_start_row, 0, meta_start_row, 3,
                          'REPORT METADATA', meta_section_format)

    meta_rows = [
        ('Report Type', 'Operator Assignment with Step Timeline'),
        ('Downloaded At (IST)', now_ist.strftime('%d-%b-%Y %H:%M:%S')),
        ('Filter: Assignment Status', assignment_status or 'ALL'),
        ('Filter: Start Date', start_date),
        ('Filter: End Date', end_date),
        ('Total Records', row_num - 1),
        ('Time Diff Format', 'Decimal hours (e.g. 3.75)' if time_diff_format == "decimal"
                              else 'Hours & minutes (e.g. 3h 45m)'),
    ]

    for i, (label, value) in enumerate(meta_rows):
        r = meta_start_row + 1 + i
        worksheet.write(r, 0, label, meta_label_format)
        worksheet.merge_range(r, 1, r, 3, str(value), meta_value_format)

    # ---- Section 2: SLA calculation logic ----
    sla_section_row = meta_start_row + 1 + len(meta_rows) + 1
    worksheet.merge_range(sla_section_row, 0, sla_section_row, 3,
                          'SLA TIME DIFF — CALCULATION LOGIC', meta_section_format)

    sla_rows = [
        ('Base Field',
         'gp_received_datetime (time gatepass physically received by security)'),
        ('Condition 1: Shipment Delivered',
         'When final_delivery_datetime IS present  →  '
         'SLA = final_delivery_datetime − gp_received_datetime'),
        ('Condition 2: Shipment NOT Yet Delivered',
         'When final_delivery_datetime is NULL  →  '
         'SLA = (Report Download Time) − gp_received_datetime  '
         '(i.e. live elapsed time at the moment this file was generated)'),
        ('Note on Blank Cells',
         'Blank cells in any time-diff column mean one of the required datetimes is missing.'),
        ('Note on Negative Values',
         'Negative values (shown in RED, e.g. -2.50) indicate the end datetime is BEFORE the start datetime. '
         'This points to a data-entry / ordering issue and should be investigated. '
         'You can sort the column ascending or filter "less than 0" to find all such records.'),
    ]

    for i, (label, value) in enumerate(sla_rows):
        r = sla_section_row + 1 + i
        worksheet.write(r, 0, label, meta_label_format)
        worksheet.merge_range(r, 1, r, 3, str(value), meta_value_format)
        # Taller row for the explanation cells
        worksheet.set_row(r, 30)

    workbook.close()
    output.seek(0)
    yield output.read()
# ------------------------------------------------
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

    # ADD THIS AFTER rows for get those data which deleiverd but take more than four hours
    outside_sla_stmt = (
        select(WorkerAssignmentShipment, WorkerAssignmentHeader)
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentHeader.id == WorkerAssignmentShipment.assignment_header_id
        )
        .where(
            WorkerAssignmentShipment.gate_pass_no.isnot(None),
            WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None),
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.isnot(None),
            func.extract(
                "epoch",
                WorkerAssignmentShipment.gate_pass_end_datetime
                - WorkerAssignmentShipment.gate_pass_issued_date_time_combo
            ) > 14400,
            or_(
                WorkerAssignmentShipment.integrate_date_time.between(start_utc, end_utc),
                WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(start_utc, end_utc)
            )
        )
        .order_by(WorkerAssignmentShipment.id.asc())
    )

    outside_sla_records = (await db.execute(outside_sla_stmt)).all()
    # -----


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

            "delivered_outside_defined_hours_shipments": [
                {
                    "id": shipment.id,
                    "gate_pass_no": shipment.gate_pass_no,
                    "oc_no": header.oc_no,        # 👈 from header
                    "awb_no": header.awb_no,      # 👈 from header
                    "hawb_no": header.hawb,       # 👈 from header (column name is hawb)
                    "gate_pass_issued_date_time_combo": shipment.gate_pass_issued_date_time_combo,
                    "gate_pass_end_datetime": shipment.gate_pass_end_datetime,
                    "assigned_person": shipment.assigned_person,
                    "drop_dlv_zone": shipment.drop_dlv_zone,
                }
                for shipment, header in outside_sla_records  # 👈 unpack both
            ],

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
        WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),

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

        # =====
    outside_sla_stmt = (
        select(WorkerAssignmentShipment, WorkerAssignmentHeader)
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentHeader.id == WorkerAssignmentShipment.assignment_header_id
        )
        .where(
            WorkerAssignmentShipment.gate_pass_no.isnot(None),
            WorkerAssignmentShipment.gate_pass_end_datetime.isnot(None),
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.isnot(None),
            func.extract(
                "epoch",
                WorkerAssignmentShipment.gate_pass_end_datetime
                - WorkerAssignmentShipment.gate_pass_issued_date_time_combo
            ) > 14400,
            or_(
                WorkerAssignmentShipment.integrate_date_time.between(start_utc, end_utc),
                WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(start_utc, end_utc)
            )
        )
        .order_by(WorkerAssignmentShipment.id.asc())
         )
    outside_sla_records = (await db.execute(outside_sla_stmt)).all()




    return {
        "total_data": row.total_data,
        "converted_to_gp": row.converted_to_gp,
        "gp_not_generated": row.gp_not_generated,
        "unassigned": row.unassigned,
        "assigned_but_not_dropped_at_lift": row.assigned_but_not_dropped_at_lift,
        "assigned_and_dropped_at_lift": row.assigned_and_dropped_at_lift,
        "gatepass_end_date_present_means_delivered": row.gatepass_end_date_present_means_delivered,
        "delivered_within_defined_hours": row.delivered_within_defined_hours,

        "delivered_outside_defined_hours_shipments": [
            {
                "id": shipment.id,
                "gate_pass_no": shipment.gate_pass_no,
                "oc_no": header.oc_no,
                "awb_no": header.awb_no,
                "hawb_no": header.hawb,
                "gate_pass_issued_date_time_combo": shipment.gate_pass_issued_date_time_combo,
                "gate_pass_end_datetime": shipment.gate_pass_end_datetime,
                "assigned_person": shipment.assigned_person,
                "drop_dlv_zone": shipment.drop_dlv_zone,
            }
            for shipment, header in outside_sla_records
        ],

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

# Get the summary stats data to show in mobile admin dashboard
async def get_damage_shipment_summary_stats(
    db,
    start_utc,
    end_utc,
):
    stmt = (
        select(
            func.count().label("total"),

            func.sum(
                case(
                    (WorkerAssignmentShipment.damage_report_status == "open", 1),
                    else_=0
                )
            ).label("open"),

            func.sum(
                case(
                    (WorkerAssignmentShipment.damage_report_status == "in_progress", 1),
                    else_=0
                )
            ).label("in_progress"),

            func.sum(
                case(
                    (WorkerAssignmentShipment.damage_report_status == "resolved", 1),
                    else_=0
                )
            ).label("resolved"),
        )
        .where(
    and_(
        or_(
            WorkerAssignmentShipment.integrate_date_time.between(start_utc, end_utc),
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(start_utc, end_utc),
        ),
        WorkerAssignmentShipment.damage_report_status.isnot(None)
    )
)

    )

    result = await db.execute(stmt)
    row = result.first()

    return {
        "total": row.total or 0,
        "open": row.open or 0,
        "in_progress": row.in_progress or 0,
        "resolved": row.resolved or 0,
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
            WorkerAssignmentShipment.gate_pass_end_datetime.is_(None),
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


# 
async def get_particular_user_drop_shipments_details(
    db: AsyncSession,
    emp_id: str,
    start_date: str,   # "YYYY-MM-DD"
    end_date: str,     # "YYYY-MM-DD"
):
    """
    Fetch dropped shipments of user + dynamic zone metrics (date range)
    """

    # ----------------------------------
    # 1️⃣ Convert IST → UTC Range
    # ----------------------------------
    start_utc, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start_date)
    _, end_utc = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end_date)

    # ----------------------------------
    # 2️⃣ Main Data Query
    # ----------------------------------
    data_stmt = (
        select(
            WorkerAssignmentShipment,
            WorkerAssignmentHeader
        )
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentShipment.assignment_header_id
            == WorkerAssignmentHeader.id
        )
        .where(

            # ✅ User filter
            WorkerAssignmentShipment.assigned_person == emp_id,

            # ✅ Only dropped shipments
            WorkerAssignmentShipment.drop_dlv_zone.isnot(None),

            # ✅ Date Range (IST handled)
            WorkerAssignmentShipment.drop_dlv_zone_datetime.between(
                start_utc,
                end_utc
            ),
        )
        .order_by(
            WorkerAssignmentShipment.drop_dlv_zone_datetime.desc()
        )
    )

    data_result = await db.execute(data_stmt)
    rows = data_result.all()

    # ----------------------------------
    # 3️⃣ Metrics Query (GROUP BY)
    # ----------------------------------
    metrics_stmt = (
        select(
            WorkerAssignmentShipment.drop_dlv_zone,
            func.count().label("total")
        )
        .where(

            WorkerAssignmentShipment.assigned_person == emp_id,

            WorkerAssignmentShipment.drop_dlv_zone.isnot(None),

            WorkerAssignmentShipment.drop_dlv_zone_datetime.between(
                start_utc,
                end_utc
            ),
        )
        .group_by(
            WorkerAssignmentShipment.drop_dlv_zone
        )
    )

    metrics_result = await db.execute(metrics_stmt)

    # Build metrics dict
    count_metrics = {
        row.drop_dlv_zone: row.total
        for row in metrics_result
    }

    # ----------------------------------
    # 4️⃣ Build Full Data
    # ----------------------------------
    full_data = []

    for shipment, header in rows:

        item = {
                "header_id": header.id,
                "oc_no": header.oc_no,
                "awb_no": header.awb_no,
                "hawb": header.hawb,
                "igp_no": header.igp_no,
                "shipment_id": shipment.id,
                "no_of_pc": shipment.no_of_pc,
                "weight_in_kgs": shipment.weight_in_kgs,
                "flight_no": shipment.flight_no,
                "location": shipment.location,


                "assigned_person": shipment.assigned_person,
                "assigned_person_datetime":shipment.assigned_person_datetime,
                "drop_dlv_zone": shipment.drop_dlv_zone,
                "drop_dlv_zone_datetime": shipment.drop_dlv_zone_datetime,

                "gate_pass_no": shipment.gate_pass_no,
                "gate_pass_issued_date_time_combo":shipment.gate_pass_issued_date_time_combo,
                "integrate_date_time": shipment.integrate_date_time,

                "created_at": shipment.created_at,
        }

        full_data.append(item)

    # ----------------------------------
    # 5️⃣ Final Response
    # ----------------------------------
    return {
        "count_metrics": count_metrics,
        "total_records": len(full_data),
        "full_data": full_data,
    }





# ============================ LIFT LOADING AND UNLOADING RELATED SERVICES ==========================================

# async def get_shipments_for_loading_in_lift(
#     db: AsyncSession,
#     drop_dlv_zone_term: str,
#     user,
#     start_date:str,
#     end_date:str,
# ):
#     """
#     Shipments ready for lift loading
#     """
#     start_utc, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start_date)
#     _, end_utc = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end_date)

#     stmt = (
#         select(WorkerAssignmentShipment)
#         .where(

#             # Assigned
#             WorkerAssignmentShipment.assigned_person.isnot(None),

#             # Drop zone exists
#             WorkerAssignmentShipment.drop_dlv_zone.isnot(None),

#             # Vehicle type
#             WorkerAssignmentShipment.drop_dlv_zone == drop_dlv_zone_term,

#             # Not loaded, not unloaded
#             WorkerAssignmentShipment.loading_in_lift_zone.is_(None),
#             WorkerAssignmentShipment.unloading_from_lift_zone.is_(None),
#             # ✅ Date filter (RANGE)
#             or_(
#                 WorkerAssignmentShipment.integrate_date_time.between(
#                     start_utc, end_utc
#                 ),
#                 WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
#                     start_utc, end_utc
#                 ),
#             ),
#         )
#         # .order_by(WorkerAssignmentShipment.created_at.asc())
#         .order_by(
#     WorkerAssignmentShipment.gate_pass_issued_date_time_combo.asc().nulls_last(),
#     WorkerAssignmentShipment.drop_dlv_zone_datetime.asc().nulls_last(),
# )


#     )

#     result = await db.execute(stmt)

#     return result.scalars().all()

async def get_shipments_for_loading_in_lift(
    db: AsyncSession,
    drop_dlv_zone_term: str,
    user,
    start_date: str,
    end_date: str,
):
    """
    Shipments ready for lift loading (with header info + count)
    """

    # # Convert IST → UTC
    # start_utc, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start_date)
    # _, end_utc = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end_date)


    #==== Temporary solution (for handling strt flow of data) ---------------------------------------
    now_ist = datetime.now(ZoneInfo("Asia/Kolkata"))

    # Format current date as YYYY-MM-DD
    current_date_str = now_ist.strftime("%Y-%m-%d")

    # Get next day
    next_day_ist = now_ist + timedelta(days=1)
    next_date_str = next_day_ist.strftime("%Y-%m-%d")
     #========================================================================
    # Convert IST → UTC
    start_utc, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range("2026-05-02")
    _, end_utc = WorkerAssignmentFilters.convert_ist_day_to_utc_range(next_date_str)

    # Base filters (reusable)
    base_filters = [

        WorkerAssignmentShipment.assigned_person.isnot(None),
        WorkerAssignmentShipment.drop_dlv_zone.isnot(None),

        # Vehicle
        WorkerAssignmentShipment.drop_dlv_zone == drop_dlv_zone_term,

        # Status
        WorkerAssignmentShipment.loading_in_lift_zone.is_(None),
        WorkerAssignmentShipment.unloading_from_lift_zone.is_(None),

        # Date Range
        or_(
            WorkerAssignmentShipment.integrate_date_time.between(
                start_utc, end_utc
            ),
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
                start_utc, end_utc
            ),
        ),
    ]

    # ============================
    # 1️⃣ Main Data Query (JOIN)
    # ============================

    data_stmt = (
        select(
            WorkerAssignmentShipment.id.label("shipment_id"),
            WorkerAssignmentShipment.assignment_header_id.label("header_id"),

            # Header fields
            WorkerAssignmentHeader.oc_no,
            WorkerAssignmentHeader.awb_no,
            WorkerAssignmentHeader.hawb,

            WorkerAssignmentShipment.no_of_pc,
            WorkerAssignmentShipment.weight_in_kgs,
            WorkerAssignmentShipment.chg_wgt_in_kg,

            # Shipment fields
            WorkerAssignmentShipment.gate_pass_no,
            WorkerAssignmentShipment.integrate_date_time,
            WorkerAssignmentShipment.drop_dlv_zone,
            WorkerAssignmentShipment.drop_dlv_zone_datetime,
            WorkerAssignmentShipment.assigned_person,
            WorkerAssignmentShipment.loading_in_lift_zone,
            WorkerAssignmentShipment.loading_in_lift_zone_datetime,
            WorkerAssignmentShipment.unloading_from_lift_zone_datetime,
            WorkerAssignmentShipment.unloading_from_lift_zone,
        )
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentShipment.assignment_header_id
            == WorkerAssignmentHeader.id
        )
        .where(*base_filters)
        .order_by(
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo
            .asc()
            .nulls_last(),

            WorkerAssignmentShipment.drop_dlv_zone_datetime
            .asc()
            .nulls_last(),
        )
    )

    result = await db.execute(data_stmt)
    rows = result.mappings().all()   # ← gives dict-like rows

    # ============================
    # 2️⃣ Count Query
    # ============================

    count_stmt = (
        select(func.count())
        .select_from(WorkerAssignmentShipment)
        .where(*base_filters)
    )

    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar() or 0

    # ============================
    # 3️⃣ Format Response
    # ============================

    data = []

    for row in rows:
        data.append({
            "shipment_id": row["shipment_id"],
            "header_id": row["header_id"],

            "oc_no": row["oc_no"],
            "awb_no": row["awb_no"],
            "hawb": row["hawb"],

            "no_of_pc": row['no_of_pc'],
            "weight_in_kgs": row['weight_in_kgs'],
            "chg_wgt_in_kg": row['chg_wgt_in_kg'],

            "gate_pass_no": row["gate_pass_no"],
            "integrate_date_time": row["integrate_date_time"],
            "drop_dlv_zone": row["drop_dlv_zone"],
            "drop_dlv_zone_datetime": row["drop_dlv_zone_datetime"],

            "assigned_person": row["assigned_person"],

            "loading_in_lift_zone_datetime": row["loading_in_lift_zone_datetime"],
            "loading_in_lift_zone":row['loading_in_lift_zone'],
            "unloading_from_lift_zone":row["unloading_from_lift_zone"],
            "unloading_from_lift_zone_datetime":row["unloading_from_lift_zone_datetime"],

            "loading_status": (
                "PENDING" if not row["loading_in_lift_zone"] else "DONE"
            ),
            "unloading_status": (
                "PENDING" if not row["unloading_from_lift_zone"] else "DONE"
            ),
        })

    # ============================
    # 4️⃣ Final API Response
    # ============================

    return {
        "total_count": total_count,
        "start_date": start_date,
        "end_date": end_date,
        "records": data,
    }

async def get_shipments_for_unloading_from_lift(
    db: AsyncSession,
    drop_dlv_zone_term: str,
    user,
    start_date: str,
    end_date: str,
):
    """
    Shipments ready for lift unloading (with header info + count)
    """

    # Convert IST → UTC
    # start_utc, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range("2026-02-11")
    start_utc, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range("2026-05-02")
    _, end_utc = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end_date)

    # Common filters
    base_filters = [

        # Assigned
        WorkerAssignmentShipment.assigned_person.isnot(None),

        # Drop zone exists
        WorkerAssignmentShipment.drop_dlv_zone.isnot(None),

        # Vehicle type
        WorkerAssignmentShipment.loading_in_lift_zone == drop_dlv_zone_term,

        # Loaded but NOT unloaded
        WorkerAssignmentShipment.loading_in_lift_zone.isnot(None),
        WorkerAssignmentShipment.unloading_from_lift_zone.is_(None),

        # Date range
        or_(
            WorkerAssignmentShipment.integrate_date_time.between(
                start_utc, end_utc
            ),
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
                start_utc, end_utc
            ),
        ),
    ]

    # ============================
    # 1️⃣ Data Query (JOIN)
    # ============================

    data_stmt = (
        select(
            WorkerAssignmentShipment.id.label("shipment_id"),
            WorkerAssignmentShipment.assignment_header_id.label("header_id"),

            # Header info
            WorkerAssignmentHeader.oc_no,
            WorkerAssignmentHeader.awb_no,
            WorkerAssignmentHeader.hawb,

            # Shipment info
            WorkerAssignmentShipment.gate_pass_no,
            WorkerAssignmentShipment.integrate_date_time,

            WorkerAssignmentShipment.no_of_pc,
            WorkerAssignmentShipment.weight_in_kgs,
            WorkerAssignmentShipment.chg_wgt_in_kg,

            WorkerAssignmentShipment.drop_dlv_zone,
            WorkerAssignmentShipment.drop_dlv_zone_datetime,

            WorkerAssignmentShipment.assigned_person,

            WorkerAssignmentShipment.loading_in_lift_zone,
            WorkerAssignmentShipment.loading_in_lift_zone_datetime,

            WorkerAssignmentShipment.unloading_from_lift_zone,
            WorkerAssignmentShipment.unloading_from_lift_zone_datetime,
        )
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentShipment.assignment_header_id
            == WorkerAssignmentHeader.id
        )
        .where(*base_filters)
        .order_by(
            # FIFO: unload in order of loading
            WorkerAssignmentShipment.loading_in_lift_zone_datetime
            .asc()
            .nulls_last()
        )
    )

    result = await db.execute(data_stmt)
    rows = result.mappings().all()

    # ============================
    # 2️⃣ Count Query
    # ============================

    count_stmt = (
        select(func.count())
        .select_from(WorkerAssignmentShipment)
        .where(*base_filters)
    )

    count_result = await db.execute(count_stmt)
    total_count = count_result.scalar() or 0

    # ============================
    # 3️⃣ Format Response
    # ============================

    data = []

    for row in rows:
        data.append({

            "shipment_id": row["shipment_id"],
            "header_id": row["header_id"],

            "oc_no": row["oc_no"],
            "awb_no": row["awb_no"],
            "hawb": row["hawb"],

            "gate_pass_no": row["gate_pass_no"],
            "integrate_date_time": row["integrate_date_time"],

            "no_of_pc": row['no_of_pc'],
            "weight_in_kgs": row['weight_in_kgs'],
            "chg_wgt_in_kg": row['chg_wgt_in_kg'],

            "drop_dlv_zone": row["drop_dlv_zone"],
            "drop_dlv_zone_datetime": row["drop_dlv_zone_datetime"],

            "assigned_person": row["assigned_person"],

            "loading_in_lift_zone_datetime": row["loading_in_lift_zone_datetime"],
            "loading_in_lift_zone":row['loading_in_lift_zone'],
            "unloading_from_lift_zone":row["unloading_from_lift_zone"],
            "unloading_from_lift_zone_datetime":row["unloading_from_lift_zone_datetime"]

        })

    # ============================
    # 4️⃣ Final Response
    # ============================

    return {
        "total_count": total_count,
        "start_date": start_date,
        "end_date": end_date,
        "records": data,
    }



async def add_loading_in_lift_by_assigned_worker(
    db: AsyncSession,
    *,
    header_id: int,
    shipment_id: int,
    oc_no: str,
    emp_id: str,
    current_user_role: str,
    loading_in_lift_zone: str,
    ip_address: str | None = None,
    device_id: str | None = None,
    user_agent: str | None = None,
) -> dict:

    try:
        # ─────────────────────────────
        # 1️⃣ Fetch HEADER
        # ─────────────────────────────
        header = (
            await db.execute(
                select(WorkerAssignmentHeader)
                .where(WorkerAssignmentHeader.id == header_id)
            )
        ).scalars().first()

        if not header:
            raise HTTPException(404, "Invalid header_id")

        if header.oc_no != oc_no:
            raise HTTPException(
                400,
                "OC number does not match header"
            )

        # ─────────────────────────────
        # 2️⃣ Fetch SHIPMENT
        # ─────────────────────────────
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

        # ─────────────────────────────
        # 3️⃣ Validations
        # ─────────────────────────────
        if not shipment.assigned_person:
            raise HTTPException(400, "Shipment not assigned")

        # if shipment.assigned_person != emp_id:
        #     raise HTTPException(403, "Assigned to another worker")

        # ❌ Prevent double loading
        if shipment.loading_in_lift_zone:
            raise HTTPException(400, "Shipment already loaded in lift")

        # ❌ Must have drop zone first
        if not shipment.drop_dlv_zone:
            raise HTTPException(
                400,
                "Drop delivery zone not assigned yet"
            )

        origin_source = detect_origin_source(header, shipment)

        # 🔒 HOLD GUARD — block if shipment is on hold
        await assert_not_on_hold(db, shipment, header)

        # ─────────────────────────────
        # 4️⃣ Update
        # ─────────────────────────────
        old_value = shipment.loading_in_lift_zone
        now = get_utc_now()

        await db.execute(
            update(WorkerAssignmentShipment)
            .where(WorkerAssignmentShipment.id == shipment.id)
            .values(
                loading_in_lift_zone=loading_in_lift_zone,
                loading_in_lift_person=emp_id,
                loading_in_lift_zone_datetime=now,
                updated_at=now,
            )
        )

        # ─────────────────────────────
        # 5️⃣ Audit Log
        # ─────────────────────────────
        await log_worker_assignment_audit(
            db=db,
            header=header,
            shipment=shipment,
            field_name="loading_in_lift_zone",
            old_value=old_value,
            new_value=loading_in_lift_zone,
            changed_by=emp_id,
            changed_by_role=current_user_role,
            ip_address=ip_address,
            device_id=device_id,
            user_agent=user_agent,
            db_action="UPDATE",
            source_action="lift_loading_update",
            origin_source_type=origin_source.value,
        )

        # ─────────────────────────────
        # 6️⃣ Commit
        # ─────────────────────────────
        await db.commit()

        return {
            "status": "success",
            "message": "Loading in lift added successfully"
        }

    except HTTPException:
        await db.rollback()
        raise

    except Exception:
        await db.rollback()
        raise HTTPException(
            500,
            "Failed to update loading in lift"
        )

async def add_unloading_from_lift_by_assigned_worker(
    db: AsyncSession,
    *,
    header_id: int,
    shipment_id: int,
    oc_no: str,
    emp_id: str,
    current_user_role: str,
    unloading_from_lift_zone: str,
    ip_address: str | None = None,
    device_id: str | None = None,
    user_agent: str | None = None,
) -> dict:

    try:
        # ─────────────────────────────
        # 1️⃣ Fetch HEADER
        # ─────────────────────────────
        header = (
            await db.execute(
                select(WorkerAssignmentHeader)
                .where(WorkerAssignmentHeader.id == header_id)
            )
        ).scalars().first()

        if not header:
            raise HTTPException(404, "Invalid header_id")

        if header.oc_no != oc_no:
            raise HTTPException(
                400,
                "OC number does not match header"
            )

        # ─────────────────────────────
        # 2️⃣ Fetch SHIPMENT
        # ─────────────────────────────
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

        # ─────────────────────────────
        # 3️⃣ Validations
        # ─────────────────────────────
        if not shipment.assigned_person:
            raise HTTPException(400, "Shipment not assigned")

        # if shipment.assigned_person != emp_id:
        #     raise HTTPException(403, "Assigned to another worker")

        # ❌ Must be loaded first
        if not shipment.loading_in_lift_zone:
            raise HTTPException(
                400,
                "Shipment not loaded in lift yet"
            )

        # ❌ Prevent double unload
        if shipment.unloading_from_lift_zone:
            raise HTTPException(400, "shipment Already unloaded from lift")

        origin_source = detect_origin_source(header, shipment)

        # 🔒 HOLD GUARD — block if shipment is on hold
        await assert_not_on_hold(db, shipment, header)
        # ─────────────────────────────
        # 4️⃣ Update
        # ─────────────────────────────
        old_value = shipment.unloading_from_lift_zone
        now = get_utc_now()
        print(unloading_from_lift_zone,"unloading_from_lift_zone")
        await db.execute(
            update(WorkerAssignmentShipment)
            .where(WorkerAssignmentShipment.id == shipment.id)
            .values(
                unloading_from_lift_zone=unloading_from_lift_zone,
                unloading_from_lift_person=emp_id,
                unloading_from_lift_zone_datetime=now,
                updated_at=now,
            )
        )

        # ─────────────────────────────
        # 5️⃣ Audit Log
        # ─────────────────────────────
        await log_worker_assignment_audit(
            db=db,
            header=header,
            shipment=shipment,
            field_name="unloading_from_lift_zone",
            old_value=old_value,
            new_value=unloading_from_lift_zone,
            changed_by=emp_id,
            changed_by_role=current_user_role,
            ip_address=ip_address,
            device_id=device_id,
            user_agent=user_agent,
            db_action="UPDATE",
            source_action="lift_unloading_update",
            origin_source_type=origin_source.value,
        )

        # ─────────────────────────────
        # 6️⃣ Commit
        # ─────────────────────────────
        await db.commit()

        return {
            "status": "success",
            "message": "Unloading from lift added successfully"
        }

    except HTTPException:
        await db.rollback()
        raise

    except Exception:
        await db.rollback()
        raise HTTPException(
            500,
            "Failed to update unloading from lift"
        )


# async def get_shipments_for_final_delivery(
#     db: AsyncSession,
#     drop_dlv_zone_term: str,
#     user,
#     start_date: str,
#     end_date: str,
# ):
#     """
#     Get shipments ready for final delivery
#     """

#     # Convert IST → UTC
#     start_utc, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start_date)
#     _, end_utc = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end_date)

#     # Common filters
#     base_filters = [

#         # Assigned
#         WorkerAssignmentShipment.assigned_person.isnot(None),

#         # Drop zone
#         WorkerAssignmentShipment.drop_dlv_zone.isnot(None),

#         # Vehicle
#         WorkerAssignmentShipment.drop_dlv_zone == drop_dlv_zone_term,

#         # Must be unloaded
#         WorkerAssignmentShipment.unloading_from_lift_zone.isnot(None),



#         # Not yet delivered
#         WorkerAssignmentShipment.is_final_delivered.is_(False),

#         # Date filter
#         or_(
#             and_(
#                 WorkerAssignmentShipment.integrate_date_time >= start_utc,
#                 WorkerAssignmentShipment.integrate_date_time < end_utc,
#             ),
#             and_(
#                 WorkerAssignmentShipment.gate_pass_issued_date_time_combo >= start_utc,
#                 WorkerAssignmentShipment.gate_pass_issued_date_time_combo < end_utc,
#             ),
#         ),
#     ]

#     # ============================
#     # 1️⃣ Data Query
#     # ============================

#     data_stmt = (
#         select(
#             # IDs
#             WorkerAssignmentShipment.id.label("shipment_id"),
#             WorkerAssignmentShipment.assignment_header_id.label("header_id"),

#             # Header
#             WorkerAssignmentHeader.oc_no,
#             WorkerAssignmentHeader.awb_no,
#             WorkerAssignmentHeader.hawb,

#             # Shipment
#             WorkerAssignmentShipment.gate_pass_no,
#             WorkerAssignmentShipment.integrate_date_time,

#             WorkerAssignmentShipment.drop_dlv_zone,
#             WorkerAssignmentShipment.drop_dlv_zone_datetime,

#             WorkerAssignmentShipment.loading_in_lift_zone,
#             WorkerAssignmentShipment.loading_in_lift_zone_datetime,

#             WorkerAssignmentShipment.unloading_from_lift_zone,
#             WorkerAssignmentShipment.unloading_from_lift_zone_datetime,

#             WorkerAssignmentShipment.assigned_person,

#             # Final delivery fields
#             WorkerAssignmentShipment.final_delivery_by_person,
#             WorkerAssignmentShipment.final_delivery_datetime,
#             WorkerAssignmentShipment.is_final_delivered,
#         )
#         .join(
#             WorkerAssignmentHeader,
#             WorkerAssignmentShipment.assignment_header_id
#             == WorkerAssignmentHeader.id
#         )
#         .where(*base_filters)
#         .order_by(
#             # FIFO: unload first → deliver first
#             WorkerAssignmentShipment.unloading_from_lift_zone_datetime
#             .asc()
#             .nulls_last()
#         )
#     )

#     result = await db.execute(data_stmt)
#     rows = result.mappings().all()

#     # ============================
#     # 2️⃣ Count
#     # ============================

#     count_stmt = (
#         select(func.count())
#         .select_from(WorkerAssignmentShipment)
#         .where(*base_filters)
#     )

#     count_result = await db.execute(count_stmt)
#     total_count = count_result.scalar() or 0

#     # ============================
#     # 3️⃣ Format
#     # ============================

#     data = []

#     for row in rows:
#         data.append({

#             "shipment_id": row["shipment_id"],
#             "header_id": row["header_id"],

#             "oc_no": row["oc_no"],
#             "awb_no": row["awb_no"],
#             "hawb": row["hawb"],

#             "gate_pass_no": row["gate_pass_no"],
#             "integrate_date_time": row["integrate_date_time"],

#             "drop_dlv_zone": row["drop_dlv_zone"],
#             "drop_dlv_zone_datetime": row["drop_dlv_zone_datetime"],

#             "unloading_from_lift_zone": row["unloading_from_lift_zone"],
#             "unloading_from_lift_zone_datetime": row["unloading_from_lift_zone_datetime"],
#             "loading_in_lift_zone": row["loading_in_lift_zone"],
#             "loading_in_lift_zone_datetime": row["loading_in_lift_zone_datetime"],

#             "assigned_person": row["assigned_person"],

#             "final_delivery_by_person": row["final_delivery_by_person"],
#             "final_delivery_datetime": row["final_delivery_datetime"],
#             "is_final_delivered": row["is_final_delivered"],
#         })

#     # ============================
#     # 4️⃣ Response
#     # ============================

#     return {
#         "total_count": total_count,
#         "start_date": start_date,
#         "end_date": end_date,
#         "records": data,
#     }

async def get_shipments_for_final_delivery(
    db: AsyncSession,
    *,
    start_date: str,
    end_date: str,
    status: str,
    page: int,
    page_size: int,
    user,
) -> tuple[list[dict], int]:
    """
    Fetch final delivery shipments with pagination
    """

    # IST → UTC
    start_utc, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(start_date)
    _, end_utc = WorkerAssignmentFilters.convert_ist_day_to_utc_range(end_date)


    # ============================
    # Build Filters
    # ============================

    conditions = [

        # Assigned
        WorkerAssignmentShipment.assigned_person.isnot(None),

        # Has drop zone
        WorkerAssignmentShipment.drop_dlv_zone.isnot(None),

        # Must be unloaded
        WorkerAssignmentShipment.unloading_from_lift_zone.isnot(None),

        # Date range
        or_(
            and_(
                WorkerAssignmentShipment.integrate_date_time >= start_utc,
                WorkerAssignmentShipment.integrate_date_time < end_utc,
            ),
            and_(
                WorkerAssignmentShipment.gate_pass_issued_date_time_combo >= start_utc,
                WorkerAssignmentShipment.gate_pass_issued_date_time_combo < end_utc,
            ),
        ),
    ]


    # ============================
    # Status Filter
    # ============================

    if status != "all":

        if status == "final_delivered":
            conditions.append(
                WorkerAssignmentShipment.is_final_delivered.is_(True)
            )

        elif status == "final_not_delivered":
            conditions.append(
                WorkerAssignmentShipment.is_final_delivered.is_(False)
            )
        # Zone Status (3 Ton / 5 Ton / 10 Ton)
        elif status in {"3 Ton", "5 Ton", "10 Ton"}:

            conditions.append(
                WorkerAssignmentShipment.unloading_from_lift_zone == status
            )

        else:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid status: {status}"
            )


    # ============================
    # Base Queries
    # ============================

    base_query = (
        select(
            WorkerAssignmentShipment.id.label("shipment_id"),
            WorkerAssignmentShipment.assignment_header_id.label("header_id"),

            WorkerAssignmentHeader.oc_no,
            WorkerAssignmentHeader.awb_no,
            WorkerAssignmentHeader.hawb,

            WorkerAssignmentShipment.gate_pass_no,
            WorkerAssignmentShipment.no_of_pc,
            WorkerAssignmentShipment.chg_wgt_in_kg,
            WorkerAssignmentShipment.weight_in_kgs,
            WorkerAssignmentShipment.integrate_date_time,
            WorkerAssignmentShipment.gate_pass_end_datetime,
            WorkerAssignmentShipment.gate_pass_issued_date_time_combo,


            WorkerAssignmentShipment.drop_dlv_zone,
            WorkerAssignmentShipment.drop_dlv_zone_datetime,

            WorkerAssignmentShipment.loading_in_lift_zone,
            WorkerAssignmentShipment.loading_in_lift_person,
            WorkerAssignmentShipment.loading_in_lift_zone_datetime,
            WorkerAssignmentShipment.unloading_from_lift_zone,
            WorkerAssignmentShipment.unloading_from_lift_person,
            WorkerAssignmentShipment.unloading_from_lift_zone_datetime,

            WorkerAssignmentShipment.assigned_person,

            WorkerAssignmentShipment.final_delivery_by_person,
            WorkerAssignmentShipment.final_delivery_datetime,
            WorkerAssignmentShipment.is_final_delivered,
        )
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentShipment.assignment_header_id
            == WorkerAssignmentHeader.id
        )
        .where(and_(*conditions))
    )


    # ============================
    # Count Query
    # ============================

    count_stmt = (
        select(func.count())
        .select_from(WorkerAssignmentShipment)
        .join(
            WorkerAssignmentHeader,
            WorkerAssignmentShipment.assignment_header_id
            == WorkerAssignmentHeader.id
        )
        .where(and_(*conditions))
    )

    total_result = await db.execute(count_stmt)
    total = total_result.scalar() or 0


    # ============================
    # Pagination
    # ============================

    offset = (page - 1) * page_size


    data_stmt = (
        base_query
        .order_by(
            WorkerAssignmentShipment.unloading_from_lift_zone_datetime
            .asc()
            .nulls_last()
        )
        .offset(offset)
        .limit(page_size)
    )


    # ============================
    # Execute
    # ============================

    result = await db.execute(data_stmt)

    rows = result.mappings().all()


    # ============================
    # Format Response
    # ============================

    records = []

    for row in rows:

        records.append({

            "shipment_id": row["shipment_id"],
            "header_id": row["header_id"],

            "oc_no": row["oc_no"],
            "awb_no": row["awb_no"],
            "hawb": row["hawb"],

            "gate_pass_no": row["gate_pass_no"],
            "integrate_date_time": row["integrate_date_time"],
            "no_of_pc": row["no_of_pc"],
            "weight_in_kgs": row["weight_in_kgs"],
            "chg_wgt_in_kg": row["chg_wgt_in_kg"],

            "drop_dlv_zone": row["drop_dlv_zone"],
            "drop_dlv_zone_datetime": row["drop_dlv_zone_datetime"],

            "loading_in_lift_zone": row["loading_in_lift_zone"],
            "loading_in_lift_person": row["loading_in_lift_person"],
            "loading_in_lift_zone_datetime": row["loading_in_lift_zone_datetime"],
            "unloading_from_lift_zone": row["unloading_from_lift_zone"],
            "unloading_from_lift_person": row["unloading_from_lift_person"],
            "unloading_from_lift_zone_datetime": row["unloading_from_lift_zone_datetime"],

            "assigned_person": row["assigned_person"],

            "final_delivery_by_person": row["final_delivery_by_person"],
            "final_delivery_datetime": row["final_delivery_datetime"],
            "is_final_delivered": row["is_final_delivered"],
            "gate_pass_end_datetime":row["gate_pass_end_datetime"],
            "gate_pass_issued_date_time_combo":row["gate_pass_issued_date_time_combo"]

        })


    return records, total









async def mark_final_delivery_by_assigned_worker(
    db: AsyncSession,
    *,
    header_id: int,
    shipment_id: int,
    oc_no: str,
    emp_id: str,
    current_user_role: str,

    ip_address: str | None = None,
    device_id: str | None = None,
    user_agent: str | None = None,
) -> dict:

    try:
        # ─────────────────────────────
        # 1️⃣ Fetch HEADER
        # ─────────────────────────────
        header = (
            await db.execute(
                select(WorkerAssignmentHeader)
                .where(WorkerAssignmentHeader.id == header_id)
            )
        ).scalars().first()

        if not header:
            raise HTTPException(404, "Invalid header_id")

        if header.oc_no != oc_no:
            raise HTTPException(400, "OC number does not match header")

        # ─────────────────────────────
        # 2️⃣ Fetch SHIPMENT
        # ─────────────────────────────
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

        # ─────────────────────────────
        # 3️⃣ Validations
        # ─────────────────────────────

        if not shipment.assigned_person:
            raise HTTPException(400, "Shipment not assigned")

        if not shipment.loading_in_lift_zone:
            raise HTTPException(
                400,
                "Shipment not loaded  in lift yet"
            )
        
        # Must be unloaded first
        if not shipment.unloading_from_lift_zone:
            raise HTTPException(
                400,
                "Shipment not unloaded from lift yet"
            )

        # Prevent double delivery
        if shipment.is_final_delivered:
            raise HTTPException(
                400,
                "Shipment already final delivered"
            )

        origin_source = detect_origin_source(header, shipment)

        # ─────────────────────────────
        # 4️⃣ Update
        # ─────────────────────────────
        old_value = shipment.is_final_delivered
        now = get_utc_now()

        await db.execute(
            update(WorkerAssignmentShipment)
            .where(WorkerAssignmentShipment.id == shipment.id)
            .values(
                final_delivery_by_person=emp_id,
                final_delivery_datetime=now,
                is_final_delivered=True,
                updated_at=now,
            )
        )

        # ─────────────────────────────
        # 5️⃣ Audit Log
        # ─────────────────────────────
        await log_worker_assignment_audit(
            db=db,
            header=header,
            shipment=shipment,

            field_name="is_final_delivered",

            old_value=str(old_value),
            new_value="True",

            changed_by=emp_id,
            changed_by_role=current_user_role,

            ip_address=ip_address,
            device_id=device_id,
            user_agent=user_agent,

            db_action="UPDATE",
            source_action="final_delivery_update",

            origin_source_type=origin_source.value,
        )

        # ─────────────────────────────
        # 6️⃣ Commit
        # ─────────────────────────────
        await db.commit()

        return {
            "status": "success",
            "message": "Final delivery marked successfully"
        }

    except HTTPException:
        await db.rollback()
        raise

    except Exception:
        await db.rollback()
        raise HTTPException(
            500,
            "Failed to mark final delivery"
        )
# ---------------------------------------------------------------------------------


# ================================ 😎 IMPORT TRACER RELATED SERVICES  ====================================
# Previous running code
# async def get_paginated_worker_assignments_with_damage_filter(
#     db: AsyncSession,
#     status: str,
#     startDate: Optional[str],
#     endDate: Optional[str],
#     page: int,
#     page_size: int,
# ) -> Dict[str, Any]:

#     shipment_model = WorkerAssignmentShipment
#     header_model = WorkerAssignmentHeader
#     damage_model = DamageReport



#     # =====================================================
#     # STEP 1 — BASE QUERY
#     # =====================================================


#     user_model = User   # alias


#     query = (
#         select(
#             shipment_model,
#             header_model,
#             damage_model,
#             user_model
#         )
#         .join(
#             header_model,
#             shipment_model.assignment_header_id == header_model.id
#         )
#         .join(
#             damage_model,
#             damage_model.assignment_shipment_id == shipment_model.id,
#             isouter=True
#         )
#         .join(
#             user_model,
#             user_model.emp_id == shipment_model.assigned_person,
#             isouter=True   # LEFT JOIN (important)
#         )
#     )



#     # =====================================================
#     # STEP 2 — DATE FILTER (IST → UTC SAFE)
#     # =====================================================

#     if startDate and endDate:

#         start_dt, end_dt = convert_ist_day_to_utc_range_helper(startDate)
#         _, end_dt2 = convert_ist_day_to_utc_range_helper(endDate)

#         # Use start of startDate and end of endDate
#         if start_dt and end_dt2:

#             query = query.where(
#                 damage_model.reported_at.isnot(None),
#                 damage_model.reported_at.between(start_dt, end_dt2)
#             )


#     # =====================================================
#     # STEP 3 — DAMAGE STATUS FILTER
#     # =====================================================

#     if status == "damage_open":

#         query = query.where(
#             shipment_model.damage_report_status == "open"
#         )

#     elif status == "damage_resolved":

#         query = query.where(
#             shipment_model.damage_report_status == "resolved"
#         )
#     elif status == "damage_in_progress":

#         query = query.where(
#             shipment_model.damage_report_status == "in_progress"
#         )

#     elif status == "all":

#         query = query.where(
#             shipment_model.damage_report_status.isnot(None)
#         )


#     # =====================================================
#     # STEP 4 — TOTAL COUNT
#     # =====================================================

#     total_records = (
#         await db.execute(
#             select(func.count())
#             .select_from(query.subquery())
#         )
#     ).scalar() or 0


#     total_pages = ceil(total_records / page_size) if page_size else 0


#     if page > total_pages and total_pages > 0:
#         page = total_pages

#     offset = (page - 1) * page_size


#     # =====================================================
#     # STEP 5 — PAGINATION + ORDER
#     # =====================================================

#     paginated_query = (
#         query
#         .order_by(
#             damage_model.reported_at.desc().nullslast(),
#             shipment_model.id.desc()
#         )
#         .offset(offset)
#         .limit(page_size)
#     )


#     result = await db.execute(paginated_query)

#     rows = result.all()


#     # =====================================================
#     # STEP 6 — SERIALIZATION
#     # =====================================================

#     def safe(val, tp):
#         if val is None:
#             return None
#         return tp(val)


#     records = []


#     for shipment_row, header_row, damage_row, user_row  in rows:


#         records.append({

#             # ---------------- HEADER ----------------
#             "header_id": header_row.id,
#             "oc_no": header_row.oc_no,
#             "awb_no": header_row.awb_no,
#             "hawb": header_row.hawb,
#             "temp_irm_oc_no":header_row.temp_irm_oc_no,


#             # ---------------- SHIPMENT ----------------
#             "shipment_id": shipment_row.id,
#                         # Flags
#             "from_irr_table": shipment_row.from_irr_table,

#             # Package Info
#             "no_of_pc": shipment_row.no_of_pc,
#             "no_of_pc_recd": shipment_row.no_of_pc_recd,

#             "weight_in_kgs": shipment_row.weight_in_kgs,
#             "chg_wgt_in_kg": shipment_row.chg_wgt_in_kg,

#             # Flight
#             "flight_no": shipment_row.flight_no,
#             "flight_date": shipment_row.flight_date,

#             # Location
#             "location": shipment_row.location,
#             "shc": shipment_row.shc,

#             # IRR
#             "irr_codes": shipment_row.irr_codes,
#             "irregularity_remarks": shipment_row.irregularity_remarks,

#             # Parties
#             "agent_name": shipment_row.agent_name,
#             "customer_name": shipment_row.customer_name,

#             # Zones
#             "release_zone": shipment_row.release_zone,
#             "drop_dlv_zone": shipment_row.drop_dlv_zone,
#             "drop_dlv_zone_datetime": shipment_row.drop_dlv_zone_datetime,

#             # Integration
#             "integrate_date_time": shipment_row.integrate_date_time,

#             # Gate Pass
#             "gate_pass_no": shipment_row.gate_pass_no,
#             "gate_pass_issued_date_time_combo": shipment_row.gate_pass_issued_date_time_combo,
#             "gate_pass_end_datetime": shipment_row.gate_pass_end_datetime,

#             # Assignment
#              "assigned_person": (
#                 user_row.name if user_row else None
#             ),

#             "assigned_person_emp_id": (
#                 user_row.emp_id if user_row else None
#             ),

#             "assigned_person_datetime": shipment_row.assigned_person_datetime,

#             "verified_by": shipment_row.verified_by,
#             "pd_in_time": shipment_row.pd_in_time,

#             # Lift Loading
#             "loading_in_lift_zone": shipment_row.loading_in_lift_zone,
#             "loading_in_lift_person": shipment_row.loading_in_lift_person,
#             "loading_in_lift_zone_datetime": shipment_row.loading_in_lift_zone_datetime,

#             # Lift Unloading
#             "unloading_from_lift_zone": shipment_row.unloading_from_lift_zone,
#             "unloading_from_lift_person": shipment_row.unloading_from_lift_person,
#             "unloading_from_lift_zone_datetime": shipment_row.unloading_from_lift_zone_datetime,

#             # Final Delivery
#             "final_delivery_by_person": shipment_row.final_delivery_by_person,
#             "final_delivery_datetime": shipment_row.final_delivery_datetime,
#             "is_final_delivered": shipment_row.is_final_delivered,

#             # Damage Info
#             "damage_report_status": shipment_row.damage_report_status,
#             "damage_resolve_datetime": shipment_row.damage_resolve_datetime,

#             # Audit
#             "created_at": shipment_row.created_at,
#             "updated_at": shipment_row.updated_at,


#             # ---------------- DAMAGE ----------------
#             "damage_report_id": damage_row.id if damage_row else None,

#             "damage_remarks": damage_row.remarks if damage_row else None,

#             "damage_reported_at": damage_row.reported_at if damage_row else None,
#             "damage_location": damage_row.location if damage_row else None,

#             # "damage_resolved_at": damage_row.resolved_date_time if damage_row else None,
#         })


#     # =====================================================
#     # STEP 7 — DAMAGE COUNTS (MATRIX)
#     # =====================================================

#     open_count = (
#         await db.execute(
#             select(func.count())
#             .select_from(shipment_model)
#             .where(shipment_model.damage_report_status == "open")
#         )
#     ).scalar() or 0


#     resolved_count = (
#         await db.execute(
#             select(func.count())
#             .select_from(shipment_model)
#             .where(shipment_model.damage_report_status == "resolved")
#         )
#     ).scalar() or 0


#     total_damage = (
#         await db.execute(
#             select(func.count())
#             .select_from(WorkerAssignmentShipment)
#             .where(shipment_model.damage_report_status.isnot(None))
#         )
#     ).scalar() or 0


#     # =====================================================
#     # STEP 8 — FINAL RESPONSE
#     # =====================================================

#     return {

#         "success": True,

#         "message": "Damage worker assignments fetched successfully",

#         "data": records,


#         # ---------------- PAGINATION ----------------
#         "pagination": {

#             "current_page": int(page),

#             "page_size": int(page_size),

#             "total_records": int(total_records),

#             "total_pages": int(total_pages),

#             "has_previous": bool(page > 1),

#             "has_next": bool(page < total_pages),

#             "previous_page": page - 1 if page > 1 else None,

#             "next_page": page + 1 if page < total_pages else None,
#         },


#         # ---------------- COUNTS ----------------
#         "damage_summary": {

#             "open": int(open_count),

#             "resolved": int(resolved_count),

#             "total": int(total_damage),
#         },


#         # ---------------- FILTERS ----------------
#         "filters_applied": {

#             "status": status,

#             "start_date": startDate,

#             "end_date": endDate,
#         }
#     }

# New with gatepass issueDate and integration date time range
async def get_paginated_worker_assignments_with_damage_filter(
    db: AsyncSession,
    status: str,
    startDate: Optional[str],
    endDate: Optional[str],
    page: int,
    page_size: int,
) -> Dict[str, Any]:

    shipment_model = WorkerAssignmentShipment
    header_model = WorkerAssignmentHeader
    damage_model = DamageReport



    # =====================================================
    # STEP 1 — BASE QUERY
    # =====================================================


    user_model = User   # alias


    query = (
        select(
            shipment_model,
            header_model,
            user_model
        )
        .join(
            header_model,
            shipment_model.assignment_header_id == header_model.id
        )
        .join(
            user_model,
            user_model.emp_id == shipment_model.assigned_person,
            isouter=True   # LEFT JOIN (important)
        )
    )



    # =====================================================
    # STEP 2 — DATE FILTER (IST → UTC SAFE)
    # =====================================================

    if startDate and endDate:

        start_dt, end_dt = convert_ist_day_to_utc_range_helper(startDate)
        _, end_dt2 = convert_ist_day_to_utc_range_helper(endDate)

        # Use start of startDate and end of endDate
        if start_dt and end_dt2:

          query = query.where(
    shipment_model.damage_report_status.isnot(None),
    func.coalesce(
        shipment_model.gate_pass_issued_date_time_combo,
        shipment_model.integrate_date_time
    ).between(start_dt, end_dt2)
)



    # =====================================================
    # STEP 3 — DAMAGE STATUS FILTER
    # =====================================================

    if status == "damage_open":

        query = query.where(
            shipment_model.damage_report_status == "open"
        )

    elif status == "damage_resolved":

        query = query.where(
            shipment_model.damage_report_status == "resolved"
        )
    elif status == "damage_in_progress":

        query = query.where(
            shipment_model.damage_report_status == "in_progress"
        )

    elif status == "all":

        query = query.where(
            shipment_model.damage_report_status.isnot(None)
        )


    # =====================================================
    # STEP 4 — TOTAL COUNT
    # =====================================================

    total_records = (
        await db.execute(
            select(func.count())
            .select_from(query.subquery())
        )
    ).scalar() or 0


    total_pages = ceil(total_records / page_size) if page_size else 0


    if page > total_pages and total_pages > 0:
        page = total_pages

    offset = (page - 1) * page_size


    # =====================================================
    # STEP 5 — PAGINATION + ORDER
    # =====================================================

    paginated_query = (
        query
        .order_by(
            shipment_model.created_at.desc(),
            shipment_model.id.desc()
        )
        .offset(offset)
        .limit(page_size)
    )


    result = await db.execute(paginated_query)

    rows = result.all()


    # =====================================================
    # STEP 6 — SERIALIZATION
    # =====================================================

    shipment_ids = [shipment_row.id for shipment_row, _, _ in rows]

    damage_counts_map = {}

    if shipment_ids:
        damage_count_result = await db.execute(
            select(
                DamageReport.assignment_shipment_id,
                func.count(DamageReport.id)
            )
            .where(DamageReport.assignment_shipment_id.in_(shipment_ids))
            .group_by(DamageReport.assignment_shipment_id)
        )

        damage_counts_map = {
            shipment_id: count
            for shipment_id, count in damage_count_result.all()
        }

    def safe(val, tp):
        if val is None:
            return None
        return tp(val)


    records = []


    for shipment_row, header_row, user_row  in rows:


        records.append({

            # ---------------- HEADER ----------------
            "header_id": header_row.id,
            "oc_no": header_row.oc_no,
            "awb_no": header_row.awb_no,
            "hawb": header_row.hawb,
            "temp_irm_oc_no":header_row.temp_irm_oc_no,


            # ---------------- SHIPMENT ----------------
            "shipment_id": shipment_row.id,
                        # Flags
            "from_irr_table": shipment_row.from_irr_table,

            # Package Info
            "no_of_pc": shipment_row.no_of_pc,
            "no_of_pc_recd": shipment_row.no_of_pc_recd,

            "weight_in_kgs": shipment_row.weight_in_kgs,
            "chg_wgt_in_kg": shipment_row.chg_wgt_in_kg,

            # Flight
            "flight_no": shipment_row.flight_no,
            "flight_date": shipment_row.flight_date,

            # Location
            "location": shipment_row.location,
            "shc": shipment_row.shc,

            # IRR
            "irr_codes": shipment_row.irr_codes,
            "irregularity_remarks": shipment_row.irregularity_remarks,

            # Parties
            "agent_name": shipment_row.agent_name,
            "customer_name": shipment_row.customer_name,

            # Zones
            "release_zone": shipment_row.release_zone,
            "drop_dlv_zone": shipment_row.drop_dlv_zone,
            "drop_dlv_zone_datetime": shipment_row.drop_dlv_zone_datetime,

            # Integration
            "integrate_date_time": shipment_row.integrate_date_time,

            # Gate Pass
            "gate_pass_no": shipment_row.gate_pass_no,
            "gate_pass_issued_date_time_combo": shipment_row.gate_pass_issued_date_time_combo,
            "gate_pass_end_datetime": shipment_row.gate_pass_end_datetime,

            # Assignment
             "assigned_person": (
                user_row.name if user_row else None
            ),

            "assigned_person_emp_id": (
                user_row.emp_id if user_row else None
            ),

            "assigned_person_datetime": shipment_row.assigned_person_datetime,

            "verified_by": shipment_row.verified_by,
            "pd_in_time": shipment_row.pd_in_time,

            # Lift Loading
            "loading_in_lift_zone": shipment_row.loading_in_lift_zone,
            "loading_in_lift_person": shipment_row.loading_in_lift_person,
            "loading_in_lift_zone_datetime": shipment_row.loading_in_lift_zone_datetime,

            # Lift Unloading
            "unloading_from_lift_zone": shipment_row.unloading_from_lift_zone,
            "unloading_from_lift_person": shipment_row.unloading_from_lift_person,
            "unloading_from_lift_zone_datetime": shipment_row.unloading_from_lift_zone_datetime,

            # Final Delivery
            "final_delivery_by_person": shipment_row.final_delivery_by_person,
            "final_delivery_datetime": shipment_row.final_delivery_datetime,
            "is_final_delivered": shipment_row.is_final_delivered,

            # Damage Info
            "damage_report_status": shipment_row.damage_report_status,
            "damage_resolve_datetime": shipment_row.damage_resolve_datetime,

            # Audit
            "created_at": shipment_row.created_at,
            "updated_at": shipment_row.updated_at,

            "total_damage_count": damage_counts_map.get(shipment_row.id, 0),



            # ---------------- DAMAGE ----------------
            # "damage_report_id": damage_row.id if damage_row else None,

            # "damage_remarks": damage_row.remarks if damage_row else None,

            # "damage_reported_at": damage_row.reported_at if damage_row else None,
            # "damage_location": damage_row.location if damage_row else None,

            # "damage_resolved_at": damage_row.resolved_date_time if damage_row else None,
        })


    # =====================================================
    # STEP 7 — DAMAGE COUNTS (MATRIX)
    # =====================================================

    open_count = (
        await db.execute(
            select(func.count())
            .select_from(shipment_model)
            .where(shipment_model.damage_report_status == "open")
        )
    ).scalar() or 0


    resolved_count = (
        await db.execute(
            select(func.count())
            .select_from(shipment_model)
            .where(shipment_model.damage_report_status == "resolved")
        )
    ).scalar() or 0


    total_damage = (
        await db.execute(
            select(func.count())
            .select_from(WorkerAssignmentShipment)
            .where(shipment_model.damage_report_status.isnot(None))
        )
    ).scalar() or 0


    # =====================================================
    # STEP 8 — FINAL RESPONSE
    # =====================================================

    return {

        "success": True,

        "message": "Damage worker assignments fetched successfully",

        "data": records,


        # ---------------- PAGINATION ----------------
        "pagination": {

            "current_page": int(page),

            "page_size": int(page_size),

            "total_records": int(total_records),

            "total_pages": int(total_pages),

            "has_previous": bool(page > 1),

            "has_next": bool(page < total_pages),

            "previous_page": page - 1 if page > 1 else None,

            "next_page": page + 1 if page < total_pages else None,
        },


        # ---------------- COUNTS ----------------
        "damage_summary": {

            "open": int(open_count),

            "resolved": int(resolved_count),

            "total": int(total_damage),
        },


        # ---------------- FILTERS ----------------
        "filters_applied": {

            "status": status,

            "start_date": startDate,

            "end_date": endDate,
        }
    }




async def get_full_damage_report_by_id_for_tracer(
    db: AsyncSession,
    report_id: int
) -> Dict[str, Any] | None:

    # -----------------------------------
    # MAIN QUERY (WITH RELATIONS)
    # -----------------------------------

    query = (
        select(DamageReport)
        .options(

            # Load reasons + master reason
            selectinload(DamageReport.reasons)
            .selectinload(DamageReportReason.reason),

            # Load images
            selectinload(DamageReport.images),
        )
        .where(DamageReport.id == report_id)
    )

    result = await db.execute(query)

    report = result.scalar_one_or_none()

    if not report:
        return None


    # -----------------------------------
    # SERIALIZE REASONS
    # -----------------------------------

    reasons = []

    for rr in report.reasons:

        reason_master: DamageReason = rr.reason

        reasons.append({

            "id": rr.id,

            "reason_id": reason_master.id,
            "reason_code": reason_master.reason_code,
            "reason_name": reason_master.reason_name,
            "description": reason_master.description,

            "emp_id": rr.emp_id,
            "device_id": rr.device_id,

            "created_at": rr.created_at,
        })


    # -----------------------------------
    # SERIALIZE IMAGES
    # -----------------------------------

    images = []

    for img in report.images:

        images.append({

            "id": img.id,

            "image_url": img.image_url,
            "image_name": img.image_name,

            "file_size": img.file_size,
            "mime_type": img.mime_type,

            "emp_id": img.emp_id,
            "device_id": img.device_id,

            "uploaded_at": img.uploaded_at,
        })


    # -----------------------------------
    # FINAL RESPONSE
    # -----------------------------------

    return {

        # ================= MAIN REPORT =================

        "id": report.id,

        "status": report.status,
        "resolved_date_time": report.resolved_date_time,

        "assignment_header_id": report.assignment_header_id,
        "assignment_shipment_id": report.assignment_shipment_id,

        "oc_no": report.oc_no,
        "awb_no": report.awb_no,
        "hawb": report.hawb,
        "location": report.location,

        "remarks": report.remarks,

        "reported_at": report.reported_at,

        "created_at": report.created_at,
        "updated_at": report.updated_at,


        # ================= RELATIONS =================

        "reasons": reasons,

        "images": images,
    }


from typing import List, Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession

from typing import Dict, Any
from sqlalchemy import select
from sqlalchemy.orm import selectinload
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert


async def get_full__all_damage_grouped_by_shipment_for_tracer(
    db: AsyncSession,

    header_id: int,
    shipment_id: int,
    oc_no: str

) -> Dict[str, Any] | None:

    # -----------------------------------
    # MAIN QUERY
    # -----------------------------------

    query = (
        select(DamageReport)
        .options(

            selectinload(DamageReport.reasons)
            .selectinload(DamageReportReason.reason),

            selectinload(DamageReport.images),

        )
        .where(
            DamageReport.assignment_header_id == header_id,
            DamageReport.assignment_shipment_id == shipment_id,
            DamageReport.oc_no == oc_no
        )
        .order_by(DamageReport.created_at.asc())
    )

    result = await db.execute(query)

    reports = result.scalars().all()

    if not reports:
        return None


    # -----------------------------------
    # BUILD DAMAGES ARRAY
    # -----------------------------------

    damages = []


    for report in reports:

        # ---------- REASONS ----------

        reasons = []

        for rr in report.reasons:

            master = rr.reason

            reasons.append({

                "id": rr.id,

                "reason_id": master.id,
                "reason_code": master.reason_code,
                "reason_name": master.reason_name,
                "description": master.description,

                "emp_id": rr.emp_id,
                "device_id": rr.device_id,

                "created_at": rr.created_at,
            })


        # ---------- IMAGES ----------

        images = []

        for img in report.images:

            images.append({

                "id": img.id,

                "image_url": f"/{img.image_url.replace('\\', '/')}",
                "image_name": img.image_name,

                "file_size": img.file_size,
                "mime_type": img.mime_type,

                "emp_id": img.emp_id,
                "device_id": img.device_id,

                "uploaded_at": img.uploaded_at,
            })


        # ---------- DAMAGE OBJECT ----------

        damages.append({

            "id": report.id,

            "location": report.location,

            "status": report.status,
            "resolved_date_time": report.resolved_date_time,

            "remarks": report.remarks,
            "tracer_remarks": report.tracer_remarks,

            "reported_at": report.reported_at,

            "created_at": report.created_at,
            "updated_at": report.updated_at,

            "reasons": reasons,

            "images": images,
        })


    # -----------------------------------
    # SHIPMENT LEVEL OBJECT
    # -----------------------------------

    first = reports[0]


    return {

        # ===== Shipment Info =====

        "assignment_header_id": first.assignment_header_id,
        "assignment_shipment_id": first.assignment_shipment_id,

        "oc_no": first.oc_no,
        "awb_no": first.awb_no,
        "hawb": first.hawb,

        "created_at": first.created_at,
        "updated_at": first.updated_at,

        # ===== Damages =====

        "damages": damages
    }


async def get_all_open_damage_shipments(
    db: AsyncSession,
) -> list[dict]:

    shipment = WorkerAssignmentShipment
    header = WorkerAssignmentHeader
    damage = DamageReport
    user = User


    query = (
    select(
        shipment.id.label("shipment_id"),
        header.id.label("header_id"),
        header.oc_no,
        header.awb_no,
        header.hawb,
        shipment.no_of_pc.label("pcs"),
        shipment.weight_in_kgs.label("weight"),
        shipment.assigned_person,
        shipment.damage_report_status.label("damage_report_status"),
        shipment.gate_pass_no,
        func.array_agg(
            func.json_build_object(
                "id", damage.id,
                "reported_at", damage.reported_at,
                "description", damage.remarks
            )
        ).filter(damage.id.isnot(None)).label("damages")
    )
    .join(header, shipment.assignment_header_id == header.id)
    .join(damage, damage.assignment_shipment_id == shipment.id, isouter=True)
    .where(shipment.damage_report_status.in_(["need_tracer", "in_progress"]))
    .group_by(
        shipment.id,
        header.id,
        header.oc_no,
        header.awb_no,
        header.hawb,
        shipment.no_of_pc,
        shipment.weight_in_kgs,
        shipment.assigned_person,
        shipment.damage_report_status,
        shipment.gate_pass_no
    )
    # .order_by(shipment.id.desc())
    .order_by(
    case(
        (shipment.damage_report_status == "open", 1),
        (shipment.damage_report_status == "in_progress", 2),
        else_=3
    ),
    shipment.id.desc()
)
)

    result = await db.execute(query)

    rows = result.all()

    records = []

    for row in rows:
        records.append({
            "id": row.shipment_id,
            "header_id": row.header_id,
            "shipment_id":row.shipment_id,
            "oc_no": row.oc_no,
            "awb_no": row.awb_no,
            "hawb": row.hawb,
            "pcs": row.pcs,
            "weight": row.weight,
            "assigned_person": row.assigned_person,
            "damage_report_status": row.damage_report_status,
            "gate_pass_no": row.gate_pass_no,
            "damages": row.damages or []  # aggregated array of damages
        })

    return records

async def mark_shipment_need_tracer(
    *,
    db: AsyncSession,
    header_id: int,
    shipment_id: int,
    oc_no: str,
    device_id: str,
    changed_by: str,
    role: str,
):
    now = get_utc_now()

    # ─────────────────────────────
    # 1️⃣ Validate header
    # ─────────────────────────────
    header = (
        await db.execute(
            select(WorkerAssignmentHeader)
            .where(WorkerAssignmentHeader.id == header_id)
        )
    ).scalars().first()

    if not header:
        raise HTTPException(404, "Invalid header_id")

    if header.oc_no != oc_no:
        raise HTTPException(400, "OC number mismatch")

    # ─────────────────────────────
    # 2️⃣ Validate shipment belongs to header
    # ─────────────────────────────
    shipment = (
        await db.execute(
            select(WorkerAssignmentShipment)
            .where(
                WorkerAssignmentShipment.id == shipment_id,
                WorkerAssignmentShipment.assignment_header_id == header_id,
            )
        )
    ).scalars().first()

    if not shipment:
        raise HTTPException(404, "Shipment not found")

    # ─────────────────────────────
    # 3️⃣ Validate damage exists
    # ─────────────────────────────
    if shipment.damage_report_status is None:
        raise HTTPException(
            400,
            "Cannot mark NEED_TRACER. No damage exists."
        )

    # ─────────────────────────────
    # 4️⃣ Only OPEN → NEED_TRACER allowed
    # ─────────────────────────────
    if shipment.damage_report_status != DamageStatusInWorkerAssignmnet.OPEN.value:
        raise HTTPException(
            400,
            f"Cannot mark NEED_TRACER from status '{shipment.damage_report_status}'"
        )

    # Save old value first
    old_status = shipment.damage_report_status

    # ─────────────────────────────
    # 5️⃣ Update status
    # ─────────────────────────────
    shipment.damage_report_status = DamageStatusInWorkerAssignmnet.NEED_TRACER.value
    shipment.updated_at = now

    # ─────────────────────────────
    # 5.1️⃣ Sync ALL related damage reports
    # ─────────────────────────────
    await db.execute(
        update(DamageReport)
        .where(
            DamageReport.assignment_shipment_id == shipment.id,
            DamageReport.status == DamageStatusInWorkerAssignmnet.OPEN.value  # update only open reports
        )
        .values(
            status=DamageStatusInWorkerAssignmnet.NEED_TRACER.value,
            updated_at=now
        )
    )

    # ─────────────────────────────
    # 6️⃣ Audit log
    # ─────────────────────────────
    await log_worker_assignment_audit(
        db=db,
        header=header,
        shipment=shipment,

        field_name="damage_report_status",

        # old_value=DamageStatusInWorkerAssignmnet.OPEN.value,
        # new_value=DamageStatusInWorkerAssignmnet.NEED_TRACER.value,
        old_value=old_status,  # use actual old value from DB
        new_value=DamageStatusInWorkerAssignmnet.NEED_TRACER.value,

        changed_by=changed_by,
        changed_by_role=role,

        device_id=device_id,
        ip_address=None,
        user_agent=None,

        db_action="UPDATE",
        source_action="mark_need_tracer",
    )

    await db.commit()

    return shipment

# ---------------------------------------------------------------------------------------------------------------

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




















# =======================================================================


async def update_drop_dlv_zone(
    db: AsyncSession,
    *,
    header_id: int,
    shipment_id: int,
    oc_no: str,
    emp_id: str,
    current_user_role: str,
    drop_dlv_zone: str | None,
    ip_address: str | None = None,
    device_id: str | None = None,
    user_agent: str | None = None,
) -> dict:

    try:

        # -------------------------------
        # 1. Fetch Header
        # -------------------------------
        header = (
            await db.execute(
                select(WorkerAssignmentHeader)
                .where(WorkerAssignmentHeader.id == header_id)
            )
        ).scalars().first()

        if not header:
            raise HTTPException(404, "Invalid header_id")

        if header.oc_no != oc_no:
            raise HTTPException(400, "OC mismatch")

        is_irm = bool(header.temp_irm_oc_no)

        # -------------------------------
        # 2. Fetch Shipment
        # -------------------------------
        shipment = (
            await db.execute(
                select(WorkerAssignmentShipment)
                .where(
                    WorkerAssignmentShipment.id == shipment_id,
                    WorkerAssignmentShipment.assignment_header_id == header.id
                )
            )
        ).scalars().first()

        if not shipment:
            raise HTTPException(404, "Shipment not found")

        # -------------------------------
        # 3. Validations
        # -------------------------------
        if not shipment.assigned_person:
            raise HTTPException(400, "Not assigned")

        # if shipment.assigned_person != emp_id:
        #     raise HTTPException(403, "Not your shipment")

        # If not IRM → prevent overwrite (optional)
        # if shipment.drop_dlv_zone and not is_irm:
        #     raise HTTPException(400, "Already set") 
        # Restrict if shipment is already in loading/unloading process 
       # In your service, change the loading/unloading check to be explicit:

        if shipment.unloading_from_lift_zone:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot update drop zone: shipment is already unloaded from {shipment.unloading_from_lift_zone} lift."
            )
        
        if shipment.loading_in_lift_zone:
            raise HTTPException(
                status_code=400,
                detail=f"Cannot update drop zone: shipment is already loaded in {shipment.loading_in_lift_zone} lift."
            )

      
                # -------------------------------
        # 4. Update
        # -------------------------------
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

        # -------------------------------
        # 5. Auto resolve damage (Tracer)
        # -------------------------------
        status = (
            await db.execute(
                select(WorkerAssignmentShipment.damage_report_status)
                .where(WorkerAssignmentShipment.id == shipment.id)
            )
        ).scalar_one()

        if (
            current_user_role == "imp_tracer"
            and status in ["open", "in_progress"]
        ):

            await db.execute(
                update(WorkerAssignmentShipment)
                .where(WorkerAssignmentShipment.id == shipment.id)
                .values(
                    damage_report_status="resolved",
                    damage_resolve_datetime=now,
                    updated_at=now,
                )
            )

            await db.execute(
                update(DamageReport)
                .where(
                    DamageReport.assignment_shipment_id == shipment.id,
                    DamageReport.status != "resolved",
                )
                .values(
                    status="resolved",
                    resolved_date_time=now,
                    updated_at=now,
                )
            )

        # -------------------------------
        # 6. Audit
        # -------------------------------
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
            source_action="dlv_zone_update_manual",
        )

        # -------------------------------
        # 7. Commit
        # -------------------------------
        await db.commit()

        return {
            "status": "success",
            "message": "Drop zone updated"
        }

    except HTTPException:
        await db.rollback()
        raise

    except Exception as e:

        await db.rollback()

        raise HTTPException(
            500,
            "Failed to update drop zone"
        )







# =================================== TOP PERFORMER ASSIGNMENT WORKER =========================================
# async def get_top_performers(
#     db,
#     start_date,
#     end_date,
#     limit: int = 10
# ):
#     """
#     Get top operators by dropped shipments (drop_dlv_zone present)
#     Date filter applies on:
#     - integrate_date_time OR
#     - gate_pass_issued_date_time_combo
#     """

#     # =================================================
#     # Convert IST → UTC Range
#     # =================================================

#     utc_start, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(
#         start_date
#     )

#     _, utc_end = WorkerAssignmentFilters.convert_ist_day_to_utc_range(
#         end_date
#     )

#     # =================================================
#     # Metrics
#     # =================================================

#     # Total assigned shipments
#     assigned_count = func.count(
#         WorkerAssignmentShipment.id
#     )

#     # Completed = dropped to delivery zone
#     completed_count = func.sum(
#         case(
#             (
#                 and_(
#                     WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
#                     WorkerAssignmentShipment.drop_dlv_zone != ""
#                 ),
#                 1
#             ),
#             else_=0
#         )
#     )

#     # =================================================
#     # Main Query
#     # =================================================

#     stmt = (
#         select(
#             User.id.label("id"),
#             User.name.label("name"),
#             User.emp_id.label("code"),

#             assigned_count.label("assigned"),
#             completed_count.label("completed"),
            
#         )
#         .join(
#             WorkerAssignmentShipment,
#             WorkerAssignmentShipment.assigned_person == User.emp_id
#         )
#         .where(

#             # Must be assigned
#             WorkerAssignmentShipment.assigned_person.isnot(None),

#             # Date range: Integrate OR Gatepass
#             or_(
#                 WorkerAssignmentShipment.integrate_date_time.between(
#                     utc_start, utc_end
#                 ),

#                 WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
#                     utc_start, utc_end
#                 ),
#             )
#         )
#         .group_by(
#             User.id,
#             User.name,
#             User.emp_id
#         )
#         .order_by(
#             completed_count.desc()
#         )
#         .limit(limit)
#     )

#     result = await db.execute(stmt)

#     rows = result.all()

#     # =================================================
#     # Format Response
#     # =================================================

#     performers = []

#     for row in rows:

#         assigned = row.assigned or 0
#         completed = row.completed or 0

#         performance = (
#             round((completed / assigned) * 100, 2)
#             if assigned > 0 else 0
#         )

#         performers.append({
#             "id": row.id,
#             "name": row.name,
#             "code": row.code,
#             "assigned": assigned,
#             "completed": completed,
#             "performance": performance,
#         })

#     return performers







async def get_top_performers(
    db,
    start_date,
    end_date,
    limit: int = 10
):
    """
    Get top operators with:
    - assigned count / weight / pcs
    - completed count / weight / pcs
    """

    # =================================================
    # Convert IST → UTC
    # =================================================

    utc_start, _ = WorkerAssignmentFilters.convert_ist_day_to_utc_range(
        start_date
    )

    _, utc_end = WorkerAssignmentFilters.convert_ist_day_to_utc_range(
        end_date
    )

    # =================================================
    # CONDITIONS
    # =================================================

    is_completed = and_(
        WorkerAssignmentShipment.drop_dlv_zone.isnot(None),
        WorkerAssignmentShipment.drop_dlv_zone != ""
    )

    # =================================================
    # COUNTS
    # =================================================

    assigned_count = func.count(
        WorkerAssignmentShipment.id
    )

    completed_count = func.sum(
        case((is_completed, 1), else_=0)
    )

    # =================================================
    # WEIGHT SUMS
    # =================================================

    assigned_weight = func.coalesce(
        func.sum(WorkerAssignmentShipment.weight_in_kgs), 0
    )

    completed_weight = func.coalesce(
        func.sum(
            case(
                (is_completed, WorkerAssignmentShipment.weight_in_kgs),
                else_=0
            )
        ),
        0
    )

    # =================================================
    # PCS SUMS
    # =================================================

    assigned_pcs = func.coalesce(
        func.sum(WorkerAssignmentShipment.no_of_pc), 0
    )

    completed_pcs = func.coalesce(
        func.sum(
            case(
                (is_completed, WorkerAssignmentShipment.no_of_pc),
                else_=0
            )
        ),
        0
    )

    # =================================================
    # MAIN QUERY
    # =================================================

    stmt = (
        select(
            User.id.label("id"),
            User.name.label("name"),
            User.emp_id.label("code"),

            # Counts
            assigned_count.label("assigned"),
            completed_count.label("completed"),

            # Weight
            assigned_weight.label("assigned_weight"),
            completed_weight.label("completed_weight"),

            # PCS
            assigned_pcs.label("assigned_pcs"),
            completed_pcs.label("completed_pcs"),
        )
        .join(
            WorkerAssignmentShipment,
            WorkerAssignmentShipment.assigned_person == User.emp_id
        )
        .where(

            WorkerAssignmentShipment.assigned_person.isnot(None),

            # Date filter (Integrate OR Gatepass)
            or_(
                WorkerAssignmentShipment.integrate_date_time.between(
                    utc_start, utc_end
                ),
                WorkerAssignmentShipment.gate_pass_issued_date_time_combo.between(
                    utc_start, utc_end
                ),
            )
        )
        .group_by(
            User.id,
            User.name,
            User.emp_id
        )
        .order_by(
            completed_count.desc()
        )
        .limit(limit)
    )

    result = await db.execute(stmt)

    rows = result.all()

    # =================================================
    # FORMAT RESPONSE
    # =================================================

    performers = []

    for row in rows:

        assigned = row.assigned or 0
        completed = row.completed or 0

        performance = (
            round((completed / assigned) * 100, 2)
            if assigned > 0 else 0
        )

        performers.append({
            "id": row.id,
            "name": row.name,
            "code": row.code,

            # Counts
            "assigned": assigned,
            "completed": completed,

            # Weight
            "assigned_weight": float(row.assigned_weight or 0),
            "completed_weight": float(row.completed_weight or 0),

            # PCS
            "assigned_pcs": int(row.assigned_pcs or 0),
            "completed_pcs": int(row.completed_pcs or 0),

            # %
            "performance": performance,
        })

    return performers











# ================= 🫥✅ GATE PASS PHYSICALLY RECIVED IN SECURITY SERVICE ==========================================




# ---------------------------------------------------------------------------
# FILTER CLASS
# ---------------------------------------------------------------------------

class GpReceivedFilters:
    """
    Encapsulates all filter logic for the GP-received list.

    Allowed status values
    ---------------------
    gp_not_received  →  gate_pass_no exists  AND  gp_received_datetime IS NULL
    gp_received      →  gate_pass_no exists  AND  gp_received_datetime IS NOT NULL
    all              →  gate_pass_no exists  (both received & not-received)
    """

    ALLOWED_STATUSES = {"all", "gp_received", "gp_not_received"}

    def __init__(
        self,
        shipment_model,
        status: str = "all",
        startDate: Optional[str] = None,
        endDate: Optional[str] = None,
    ):
        self.shipment = shipment_model
        self.status = status
        self.startDate = startDate
        self.endDate = endDate

    # ------------------------------------------------------------------
    # INTERNAL: IST date-string → UTC (start-of-day, end-of-day)
    # ------------------------------------------------------------------
    @staticmethod
    def _ist_to_utc_range(date_str: str):
        """Convert 'YYYY-MM-DD' (IST) to a UTC (start, end) tuple."""
        ist = pytz.timezone("Asia/Kolkata")
        d = datetime.strptime(date_str, "%Y-%m-%d")
        start_ist = ist.localize(d.replace(hour=0, minute=0, second=0, microsecond=0))
        end_ist = ist.localize(
            d.replace(hour=23, minute=59, second=59, microsecond=999999)
        )
        return start_ist.astimezone(pytz.UTC), end_ist.astimezone(pytz.UTC)

    # ------------------------------------------------------------------
    # FILTER 1 – Only rows that have a gate pass (mandatory baseline)
    # ------------------------------------------------------------------
    def _apply_gp_exists(self, query):
        """Every row in this view MUST have a gate pass number."""
        return query.where(
            and_(
                self.shipment.gate_pass_no.isnot(None),
                func.trim(self.shipment.gate_pass_no) != "",
            )
        )

    # ------------------------------------------------------------------
    # FILTER 2 – GP received / not-received / all
    # ------------------------------------------------------------------
    def _apply_status_filter(self, query):
        if self.status == "gp_received":
            return query.where(
                self.shipment.gp_received_datetime.isnot(None)
            )

        if self.status == "gp_not_received":
            return query.where(
                self.shipment.gp_received_datetime.is_(None)
            )

        # "all" → no extra filter beyond gp_exists
        return query

    # ------------------------------------------------------------------
    # FILTER 3 – Date range across BOTH datetime columns (OR logic)
    #
    # Matches the existing worker-assignment service behaviour:
    #   a row is included if EITHER
    #     • gate_pass_issued_date_time_combo falls in the range, OR
    #     • integrate_date_time falls in the range
    # ------------------------------------------------------------------
    def _apply_date_filter(self, query):
        if not (self.startDate and self.endDate):
            return query

        utc_start, _ = self._ist_to_utc_range(self.startDate)
        _, utc_end = self._ist_to_utc_range(self.endDate)

        return query.where(
            or_(
                self.shipment.gate_pass_issued_date_time_combo.between(utc_start, utc_end),
                self.shipment.integrate_date_time.between(utc_start, utc_end),
            )
        )

    # ------------------------------------------------------------------
    # PUBLIC: Apply every filter in order
    # ------------------------------------------------------------------
    def apply_all(self, query):
        query = self._apply_gp_exists(query)
        query = self._apply_status_filter(query)
        query = self._apply_date_filter(query)
        return query


# ---------------------------------------------------------------------------
# SERVICE 1 – Paginated GP receipt list
# ---------------------------------------------------------------------------

async def get_paginated_gp_received_list(
    db: AsyncSession,
    status: str = "all",
    startDate: Optional[str] = None,
    endDate: Optional[str] = None,
    page: int = 1,
    page_size: int = 10,
) -> Dict[str, Any]:
    """
    Returns a paginated list of shipments that have a gate pass,
    optionally filtered by receipt status and date range.

    Each record includes all fields needed for the confirmation UI,
    plus the two new receipt fields.
    """

    header = WorkerAssignmentHeader
    shipment = WorkerAssignmentShipment
    UserAlias = aliased(User)
    # ── Build base query (shipment JOIN header) ──────────────────────────
    filters = GpReceivedFilters(
        shipment_model=shipment,
        status=status,
        startDate=startDate,
        endDate=endDate,
    )

    base_query = (
        select(shipment, header, UserAlias.name.label("gp_received_by_name"))
        .join(header, shipment.assignment_header_id == header.id)
          # 🔥 ADD THIS
    .outerjoin(
        UserAlias,
        UserAlias.emp_id == shipment.gp_received_by
    )
    )
    base_query = filters.apply_all(base_query)

    # ── Total count ───────────────────────────────────────────────────────
    total_records = (
        await db.execute(
            select(func.count()).select_from(base_query.subquery())
        )
    ).scalar() or 0

    total_pages = ceil(total_records / page_size) if page_size else 0

    # Clamp page
    page = max(1, min(page, total_pages) if total_pages else page)
    offset = (page - 1) * page_size

    # ── Paginated data ────────────────────────────────────────────────────
    paginated_query = (
        base_query
    .order_by(
    # case(
    #     (shipment.gp_received_datetime.is_(None), 1),
    #     else_=0
    # ).desc(),
    shipment.gate_pass_no.asc(),
    header.oc_no.asc(),
)
        .offset(offset)
        .limit(page_size)
    )

    rows = (await db.execute(paginated_query)).all()

    # ── Serialize ─────────────────────────────────────────────────────────
    def to_py(value, cast=None):
        """
        Convert any DB value (including numpy scalars) to a 
        plain JSON-serializable Python type.
        """
        if value is None:
            return None
        # Strip numpy wrapper first
        if isinstance(value, np.generic):
            value = value.item()  # .item() always returns native Python scalar
        # Apply cast if requested
        if cast is not None:
            return cast(value)
        return value
   

    records = []
    for s, h, user_name in rows:
      
        records.append({
            # Identity
            "shipment_id":      to_py(s.id, int),
            "header_id":        to_py(h.id, int),
            "oc_no":            to_py(h.oc_no),
            "awb_no":           to_py(h.awb_no),
            "hawb":             to_py(h.hawb),
            "temp_irm_oc_no":   to_py(h.temp_irm_oc_no),
            "is_temp_irm_oc":   to_py(h.is_temp_irm_oc, bool),

            # Gate pass
            "gate_pass_no":                    to_py(s.gate_pass_no),
            "gate_pass_issued_date_time_combo": s.gate_pass_issued_date_time_combo,
            "gate_pass_end_datetime":           s.gate_pass_end_datetime,

            # GP Receipt
            "gp_received_datetime": s.gp_received_datetime,
            "gp_received_by":       to_py(s.gp_received_by),
            "gp_received_by_name": to_py(user_name),

            # Shipment details
            "flight_no":            to_py(s.flight_no),
            "flight_date":          s.flight_date,
            "no_of_pc":             to_py(s.no_of_pc, int),
            "weight_in_kgs":        to_py(s.weight_in_kgs, float),
            "chg_wgt_in_kg":        to_py(s.chg_wgt_in_kg, float),
            "location":             to_py(s.location),
            "integrate_date_time":  s.integrate_date_time,
            "assigned_person":      to_py(s.assigned_person),
            "drop_dlv_zone":        to_py(s.drop_dlv_zone),
            "from_irr_table":       to_py(s.from_irr_table, bool),
            "is_final_delivered":   to_py(s.is_final_delivered, bool),
            "damage_report_status": to_py(s.damage_report_status),

            # Timestamps
            "created_at":  s.created_at,
            "updated_at":  s.updated_at,
        })

    # ── Summary counts (quick, re-uses same join) ─────────────────────────
    all_gp_base = (
        select(func.count())
        .select_from(
            select(shipment, header)
            .join(header, shipment.assignment_header_id == header.id)
            .where(
                and_(
                    shipment.gate_pass_no.isnot(None),
                    func.trim(shipment.gate_pass_no) != "",
                )
            )
            .subquery()
        )
    )

    total_gp_count = (await db.execute(all_gp_base)).scalar() or 0

    received_base = (
        select(func.count())
        .select_from(
            select(shipment)
            .where(
                and_(
                    shipment.gate_pass_no.isnot(None),
                    func.trim(shipment.gate_pass_no) != "",
                    shipment.gp_received_datetime.isnot(None),
                )
            )
            .subquery()
        )
    )
    received_count = (await db.execute(received_base)).scalar() or 0

    _page = int(page)
    _page_size = int(page_size)
    _total_records = int(total_records)
    _total_pages = int(total_pages)
    _total_gp_count = int(total_gp_count)
    _received_count = int(received_count)

    return {
        "success": True,
        "message": "GP receipt list fetched successfully",
        "data": records,
      "pagination": {
        "current_page":  _page,
        "page_size":     _page_size,
        "total_records": _total_records,
        "total_pages":   _total_pages,
        "has_previous":  bool(_page > 1),               # ← explicit bool()
        "has_next":      bool(_page < _total_pages),     # ← explicit bool()
        "previous_page": (_page - 1) if _page > 1 else None,
        "next_page":     (_page + 1) if _page < _total_pages else None,
    },
        "summary": {
            # Global counts (not filtered by date/status)
            "total_gp_generated": int(total_gp_count),
            "total_gp_received": int(received_count),
            "total_gp_not_received": int(total_gp_count - received_count),
        },
        "filters_applied": {
            "status": status,
            "start_date": startDate,
            "end_date": endDate,
        },
    }


# ---------------------------------------------------------------------------
# SERVICE 2 – Confirm GP receipt (PATCH)
# ---------------------------------------------------------------------------

async def confirm_gp_received(
    db: AsyncSession,
    shipment_id: int,
    received_by: str,
) -> Dict[str, Any]:
    """
    Stamps gp_received_datetime (now, UTC) and gp_received_by on the
    WorkerAssignmentShipment row identified by shipment_id.

    Business rules:
    - Row must exist.
    - Row must already have a gate_pass_no (can't receive a GP that was never generated).
    - If already received → return current values without overwriting
      (idempotent; front-end can call safely on double-click).
    """

    shipment = WorkerAssignmentShipment

    result = await db.execute(
        select(shipment).where(shipment.id == shipment_id)
    )
    row: Optional[WorkerAssignmentShipment] = result.scalar_one_or_none()

    if not row:
        return {
            "success": False,
            "message": f"Shipment with id={shipment_id} not found.",
        }

    if not row.gate_pass_no or not row.gate_pass_no.strip():
        return {
            "success": False,
            "message": "Cannot confirm GP receipt: no gate pass number exists for this shipment.",
        }

    if row.gp_received_datetime is not None:
        # Already confirmed — return existing data, do NOT overwrite
        return {
            "success": True,
            "already_received": True,
            "message": "GP was already marked as received.",
            "data": {
                "shipment_id": row.id,
                "gate_pass_no": row.gate_pass_no,
                "gp_received_datetime": row.gp_received_datetime,
                "gp_received_by": row.gp_received_by,
            },
        }

    # Stamp now (UTC)
    now_utc = datetime.now(tz=pytz.UTC)
    row.gp_received_datetime = now_utc
    row.gp_received_by = received_by.strip()
    row.updated_at = now_utc

    await db.commit()
    await db.refresh(row)

    return {
        "success": True,
        "already_received": False,
        "message": "GP receipt confirmed successfully.",
        "data": {
            "shipment_id": row.id,
            "gate_pass_no": row.gate_pass_no,
            "gp_received_datetime": row.gp_received_datetime,
            "gp_received_by": row.gp_received_by,
        },
    }





# ==========  New dashboard metrics for worker assignment for SLA   ===================== 


async def get_gp_received_sla_summary(db, start_date: date, end_date: date):

    now = get_utc_now()

    shipment = WorkerAssignmentShipment

    start_utc,_  = convert_ist_day_to_utc_range(start_date)
    _, end_utc = convert_ist_day_to_utc_range(end_date)


    result = await db.execute(
        select(
            shipment.gp_received_datetime,
            shipment.gate_pass_no
        ).where(
            shipment.gate_pass_no.isnot(None),  # 🔥 MUST

            shipment.gate_pass_issued_date_time_combo >= start_utc,
            shipment.gate_pass_issued_date_time_combo <= end_utc,
        )
    )

    rows = result.fetchall()

    count_not_received = 0
    count_0_to_3_5 = 0
    count_3_5_to_4 = 0
    count_above_4 = 0

    for row in rows:
        received = row.gp_received_datetime

        # 🟡 NOT RECEIVED
        if received is None:
            count_not_received += 1
            continue

        diff_hours = (now - received).total_seconds() / 3600

        if diff_hours < 3.5:
            count_0_to_3_5 += 1

        elif 3.5 <= diff_hours <= 4:
            count_3_5_to_4 += 1

        else:
            count_above_4 += 1  # 🔥 NEW

    return {
        "gp_no_present_but_not_gp_received": count_not_received,
        "sla_0_to_3_5_hours": count_0_to_3_5,
        "sla_3_5_to_4_hours": count_3_5_to_4,
        "sla_above_4_hours": count_above_4,
        "total": len(rows)
    }




async def get_sla_dashboard_drilldown_detail(
    db: AsyncSession,
    report_date: date,
    detail_type: str,
):

    day_start_utc, day_end_utc = ist_date_to_utc_range(report_date)
    IST = ZoneInfo("Asia/Kolkata")


    shipment = WorkerAssignmentShipment
    header = WorkerAssignmentHeader
    now = get_utc_now()

    # ✅ Base Query (same for all)
    result = await db.execute(
        select(
            # shipment.id,
            # header.awb_no,
            # shipment.gate_pass_no,
            # shipment.gp_received_datetime,
            # shipment.gp_received_by,
            # shipment.gate_pass_issued_date_time_combo
            shipment.id,

        # HEADER
        header.awb_no,
        header.hawb,
        header.oc_no,

        # SHIPMENT BASIC
        shipment.no_of_pc,
        shipment.weight_in_kgs,
        shipment.chg_wgt_in_kg,

        # GP
        shipment.gate_pass_no,
        shipment.gate_pass_issued_date_time_combo,
        shipment.gp_received_datetime,
        shipment.gp_received_by,

        # ASSIGNMENT
        shipment.assigned_person,
        shipment.assigned_person_datetime,

        # ZONE
        shipment.drop_dlv_zone,
        shipment.drop_dlv_zone_datetime,

        # LIFT
        shipment.loading_in_lift_zone,
        shipment.loading_in_lift_zone_datetime,
        shipment.unloading_from_lift_zone,
        shipment.unloading_from_lift_zone_datetime,

        # FINAL
        shipment.final_delivery_datetime,
        shipment.is_final_delivered,

        )  .join(
        WorkerAssignmentHeader,
        WorkerAssignmentHeader.id == shipment.assignment_header_id  # ✅ FIX
    ).where(
            shipment.gate_pass_no.isnot(None),

            shipment.gate_pass_issued_date_time_combo >= day_start_utc,
            shipment.gate_pass_issued_date_time_combo <= day_end_utc,
        )
    )

    rows = result.mappings().all()

    items = []

    for r in rows:
        received = r.gp_received_datetime

        # 🟡 NOT RECEIVED
        if detail_type == "gp_no_present_but_not_gp_received":
            if not received:
                items.append({
                    # "awb_no": r.awb_no,
                    # "gate_pass_no": r.gate_pass_no,
                    # "gp_received_by": r.gp_received_by,
                    # "gp_received_datetime": None,

                        # 🔹 Identity
    "shipment_id": r.id,
    "awb_no": r.awb_no,
    "hawb": r.hawb,
    "oc_no": r.oc_no,

    # 🔹 Basic
    "pcs": r.no_of_pc,
    "weight": r.weight_in_kgs,
    "chg_weight": r.chg_wgt_in_kg,

    # 🔹 Gate Pass
    "gate_pass_no": r.gate_pass_no,
    "gp_issued_at": r.gate_pass_issued_date_time_combo,
    "gp_received_datetime": r.gp_received_datetime,
    "gp_received_by": r.gp_received_by,

    # 🔹 Assignment
    "assigned_person": r.assigned_person,
    "assigned_at": r.assigned_person_datetime,

    # 🔹 Zone
    "drop_zone": r.drop_dlv_zone,
    "drop_zone_at": r.drop_dlv_zone_datetime,

    # 🔹 Lift
    "loading_zone": r.loading_in_lift_zone,
    "loading_at": r.loading_in_lift_zone_datetime,
    "unloading_zone": r.unloading_from_lift_zone,
    "unloading_at": r.unloading_from_lift_zone_datetime,

    # 🔹 Final
    "final_delivery_at": r.final_delivery_datetime,
    "is_final_delivered": r.is_final_delivered,

    "sla_hours":None
                })
            continue

        # skip if no received
        if not received:
            continue

        diff_hours = (now - received).total_seconds() / 3600

        if detail_type == "sla_0_3_5" and diff_hours < 3.5:
            pass
        elif detail_type == "sla_3_5_4" and 3.5 <= diff_hours <= 4:
            pass
        elif detail_type == "sla_above_4" and diff_hours > 4:
            pass
        else:
            continue

        items.append({
            # "awb_no": r.awb_no,
            # "gate_pass_no": r.gate_pass_no,
            # "gp_received_by": r.gp_received_by,
            # "gp_received_datetime": r.gp_received_datetime,

                # 🔹 Identity
    "shipment_id": r.id,
    "awb_no": r.awb_no,
    "hawb": r.hawb,
    "oc_no": r.oc_no,

    # 🔹 Basic
    "pcs": r.no_of_pc,
    "weight": r.weight_in_kgs,
    "chg_weight": r.chg_wgt_in_kg,

    # 🔹 Gate Pass
    "gate_pass_no": r.gate_pass_no,
    "gp_issued_at": r.gate_pass_issued_date_time_combo,
    "gp_received_datetime": r.gp_received_datetime,
    "gp_received_by": r.gp_received_by,

    # 🔹 Assignment
    "assigned_person": r.assigned_person,
    "assigned_at": r.assigned_person_datetime,

    # 🔹 Zone
    "drop_zone": r.drop_dlv_zone,
    "drop_zone_at": r.drop_dlv_zone_datetime,

    # 🔹 Lift
    "loading_zone": r.loading_in_lift_zone,
    "loading_at": r.loading_in_lift_zone_datetime,
    "unloading_zone": r.unloading_from_lift_zone,
    "unloading_at": r.unloading_from_lift_zone_datetime,

    # 🔹 Final
    "final_delivery_at": r.final_delivery_datetime,
    "is_final_delivered": r.is_final_delivered,

            "sla_hours": round(diff_hours, 2),  # 🔥 IMPORTANT
        })

    return {
        "detail_type": detail_type,
        "report_date": str(report_date),
        "total": len(items),
        "items": items,
    }





async def generate_excel_stream_export_gp_received(
    db: AsyncSession,
    status: str = "all",
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    chunk_size: int = 1000
) -> AsyncGenerator[bytes, None]:
    """
    Streams GP Received list as Excel file.
    Mirrors generate_excel_stream_export_worker_assignment pattern.
    """
    import io
    import xlsxwriter
    import numpy as np
    import pytz
    from sqlalchemy.orm import aliased

    output = io.BytesIO()
    workbook = xlsxwriter.Workbook(output, {'in_memory': True})
    worksheet = workbook.add_worksheet('GP Received')

    # ── Formats ────────────────────────────────────────────────────────
    header_format = workbook.add_format({
        'bold': True, 'border': 1,
        'align': 'center', 'valign': 'vcenter',
    })
    date_format   = workbook.add_format({'num_format': 'dd/mm/yyyy hh:mm', 'align': 'left'})
    number_format = workbook.add_format({'num_format': '0.00', 'align': 'right'})
    integer_format= workbook.add_format({'num_format': '0',    'align': 'right'})
    text_format   = workbook.add_format({'align': 'left',   'valign': 'top', 'text_wrap': True})
    text_center   = workbook.add_format({'align': 'center', 'valign': 'vcenter'})

    # ── Headers ────────────────────────────────────────────────────────
    headers = [
        'S.No',
        'OC No',          'Temp IRM OC',     'AWB No',          'HAWB',
        'Flight No',      'Flight Date',
        'No of Pieces',   'Weight (KG)',      'Chargeable Weight (KG)',
        'Location',
        'Gate Pass No',   'GP Issue Date',    'GP End Date',
        'GP Received DateTime', 'GP Received By (EmpID)', 'GP Received By (Name)',
        'Assigned Person','Drop DLV Zone',
        'Integrate Date', 'Created At',
        'Is Final Delivered',
    ]

    col_widths = [
        8,   # S.No
        15,  # OC No
        15,  # Temp IRM OC
        18,  # AWB No
        18,  # HAWB
        12,  # Flight No
        18,  # Flight Date
        12,  # No of Pieces
        12,  # Weight
        20,  # Chargeable Weight
        25,  # Location
        18,  # Gate Pass No
        20,  # GP Issue Date
        20,  # GP End Date
        22,  # GP Received DateTime
        22,  # GP Received By EmpID
        25,  # GP Received By Name
        18,  # Assigned Person
        18,  # Drop DLV Zone
        20,  # Integrate Date
        18,  # Created At
        18,  # Is Final Delivered
    ]

    for col, (h, w) in enumerate(zip(headers, col_widths)):
        worksheet.write(0, col, h, header_format)
        worksheet.set_column(col, col, w)

    worksheet.freeze_panes(1, 0)

    # ── Helpers ────────────────────────────────────────────────────────
    def to_ist_no_tz(dt):
        IST = pytz.timezone("Asia/Kolkata")
        if not dt:
            return None
        if dt.tzinfo:
            dt = dt.astimezone(IST)
        return dt.replace(tzinfo=None)

    # ── Query (same join pattern as get_paginated_gp_received_list) ────
    UserAlias = aliased(User)

    filters = GpReceivedFilters(
        shipment_model=WorkerAssignmentShipment,
        status=status,
        startDate=start_date,
        endDate=end_date,
    )

    base_query = filters.apply_all(
        select(WorkerAssignmentShipment, WorkerAssignmentHeader, UserAlias.name.label("gp_received_by_name"))
        .join(WorkerAssignmentHeader, WorkerAssignmentShipment.assignment_header_id == WorkerAssignmentHeader.id)
        .outerjoin(UserAlias, UserAlias.emp_id == WorkerAssignmentShipment.gp_received_by)
    ).order_by(
        WorkerAssignmentShipment.gate_pass_no.asc(),
        WorkerAssignmentHeader.oc_no.asc(),
    )

    # ── Stream in chunks ───────────────────────────────────────────────
    row_num = 1
    offset  = 0

    while True:
        rows = (await db.execute(base_query.offset(offset).limit(chunk_size))).all()
        if not rows:
            break

        for s, h, gp_received_by_name in rows:
            c = 0

            worksheet.write(row_num, c, row_num, text_center);                                         c+=1
            worksheet.write(row_num, c, h.oc_no or '', text_format);                                   c+=1
            worksheet.write(row_num, c, h.temp_irm_oc_no or '', text_format);                          c+=1
            worksheet.write(row_num, c, h.awb_no or '', text_format);                                  c+=1
            worksheet.write(row_num, c, h.hawb or '', text_format);                                    c+=1
            worksheet.write(row_num, c, s.flight_no or '', text_format);                               c+=1

            if s.flight_date:
                worksheet.write_datetime(row_num, c, to_ist_no_tz(s.flight_date), date_format)
            else:
                worksheet.write(row_num, c, '', text_format)
            c+=1

            if s.no_of_pc is not None:
                worksheet.write_number(row_num, c, s.no_of_pc, integer_format)
            else:
                worksheet.write_blank(row_num, c, None)
            c+=1

            if s.weight_in_kgs is not None:
                worksheet.write_number(row_num, c, s.weight_in_kgs, number_format)
            else:
                worksheet.write_blank(row_num, c, None)
            c+=1

            if s.chg_wgt_in_kg is not None:
                worksheet.write_number(row_num, c, s.chg_wgt_in_kg, number_format)
            else:
                worksheet.write_blank(row_num, c, None)
            c+=1

            worksheet.write(row_num, c, s.location or '', text_format);                                c+=1
            worksheet.write(row_num, c, s.gate_pass_no or '', text_format);                            c+=1

            for dt_field in [s.gate_pass_issued_date_time_combo, s.gate_pass_end_datetime, s.gp_received_datetime]:
                if dt_field:
                    worksheet.write_datetime(row_num, c, to_ist_no_tz(dt_field), date_format)
                else:
                    worksheet.write(row_num, c, '', text_format)
                c+=1

            worksheet.write(row_num, c, s.gp_received_by or '', text_format);                         c+=1
            worksheet.write(row_num, c, gp_received_by_name or '', text_format);                       c+=1
            worksheet.write(row_num, c, s.assigned_person or '', text_format);                         c+=1
            worksheet.write(row_num, c, s.drop_dlv_zone or '', text_format);                           c+=1

            if s.integrate_date_time:
                worksheet.write_datetime(row_num, c, to_ist_no_tz(s.integrate_date_time), date_format)
            else:
                worksheet.write(row_num, c, '', text_format)
            c+=1

            if s.created_at:
                worksheet.write_datetime(row_num, c, to_ist_no_tz(s.created_at), date_format)
            else:
                worksheet.write(row_num, c, '', text_format)
            c+=1

            worksheet.write(row_num, c, "Yes" if s.is_final_delivered else "No", text_center)

            row_num += 1

        offset += chunk_size

    workbook.close()
    output.seek(0)
    yield output.read()


# ============================== ----🫥 Generate Operator / Employee productivity Report -------------===================

def _parse_display_date(date_str: str) -> str:
    """
    Convert 'YYYY-MM-DD' → 'DD/MM/YYYY' for header display.
    Falls back to the original string on parse error.
    """
    try:
        return datetime.strptime(date_str, "%Y-%m-%d").strftime("%d/%m/%Y")
    except ValueError:
        return date_str
 

async def get_operator_productivity_preview(
    db: AsyncSession,
    start_date: str,
    end_date: str,
    extra_filters: Optional[List] = None,
) -> dict:
    """
    Returns:
    {
        "start_date": "2026-01-01",
        "end_date":   "2026-01-31",
        "rows": [
            {
                "emp_code":     "EMP001",
                "emp_name":     "John Doe",
                "shipment_count":    12,
                "piece_count":  85,
                "total_weight": 320.5
            },
            ...
        ]
    }
    """
 
    # ── Same CTE as the XLSX service ─────────────────────────────
    filters = WorkerAssignmentFilters(
        shipment_model=WorkerAssignmentShipment,
        status=None,
        startDate=start_date,
        endDate=end_date,
    )
 
    # Step 1 — deduplicate: one row per (assigned_person, header_id)
    dedup_inner = (
        filters.apply_date_filter(
            select(
                WorkerAssignmentShipment.assigned_person,
                WorkerAssignmentShipment.assignment_header_id,
                func.max(WorkerAssignmentShipment.no_of_pc)
                    .label("no_of_pc"),
                func.max(WorkerAssignmentShipment.weight_in_kgs)
                    .label("weight_in_kgs"),
            )
            .where(
                WorkerAssignmentShipment.assigned_person.isnot(None)
            )
        )
        .group_by(
            WorkerAssignmentShipment.assigned_person,
            WorkerAssignmentShipment.assignment_header_id,
        )
    )
 
    if extra_filters:
        for f in extra_filters:
            dedup_inner = dedup_inner.where(f)
 
    dedup_cte = dedup_inner.cte("deduplicated_shipments")
 
    # Step 2 — aggregate per employee
    UserAlias = aliased(User)
 
    agg_query = (
        select(
            dedup_cte.c.assigned_person.label("emp_code"),
            UserAlias.name.label("emp_name"),
            func.count(dedup_cte.c.assignment_header_id)
                .label("shipment_count"),
            func.coalesce(func.sum(dedup_cte.c.no_of_pc), 0)
                .label("piece_count"),
            func.coalesce(func.sum(dedup_cte.c.weight_in_kgs), 0.0)
                .label("total_weight"),
        )
        .outerjoin(
            UserAlias,
            UserAlias.emp_id == dedup_cte.c.assigned_person,
        )
        .group_by(
            dedup_cte.c.assigned_person,
            UserAlias.name,
        )
        .order_by(UserAlias.name.asc())
    )
 
    result = await db.execute(agg_query)
    rows = result.all()
 
    return {
        "start_date": start_date,
        "end_date":   end_date,
        "rows": [
            {
                "emp_code":     row.emp_code or "",
                "emp_name":     row.emp_name or "",
                "shipment_count":    int(row.shipment_count),
                "piece_count":  int(row.piece_count),
                "total_weight": round(float(row.total_weight), 2),
            }
            for row in rows
        ],
    }


async def generate_operator_productivity_report(
    db: AsyncSession,
    start_date: str,           # 'YYYY-MM-DD' IST
    end_date: str,             # 'YYYY-MM-DD' IST
    extra_filters: Optional[List] = None,   # 🔌 extension point for future filters
    chunk_size: int = 500,
) -> AsyncGenerator[bytes, None]:
    """
    Streams a single XLSX file (as bytes) containing the Operator
    Productivity Report.
 
    Columns
    -------
    SN | Emp Code | Assigned Person Name | AWB Count | Piece Count | Weight (Kgs)
 
    Footer row shows column totals.
    """

     # ── Helpers ────────────────────────────────────────────────────────
    def _to_ist_naive(dt):
        IST = pytz.timezone("Asia/Kolkata")
        if not dt:
            return None
        if dt.tzinfo:
            dt = dt.astimezone(IST)
        return dt.replace(tzinfo=None)
    
    def _parse_display_date_in_excel(date_str: str) -> str:
        dt = datetime.strptime(date_str, "%Y-%m-%d")
        return dt.strftime("%d %b %Y")
 
    # ═══════════════════════════════════════════════════════════════
    # 1. WORKBOOK SETUP
    # ═══════════════════════════════════════════════════════════════
 
    output = io.BytesIO()
    wb = xlsxwriter.Workbook(output, {"in_memory": True})
    ws = wb.add_worksheet("Operator Productivity")
 
    # ── Formats ──────────────────────────────────────────────────
 
    title_fmt = wb.add_format({
        "bold": True,
        "font_name": "Arial",
        "font_size": 12,
        "align": "center",
        "valign": "vcenter",
        "bg_color": "#FFFF00",
        "border": 1,
    })
 
    sub_title_fmt = wb.add_format({
        "bold": True,
        "font_name": "Arial",
        "font_size": 10,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
    })
 
    date_label_fmt = wb.add_format({
        "bold": True,
        "font_name": "Arial",
        "font_size": 10,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
    })
 
    header_fmt = wb.add_format({
        "bold": True,
        "font_name": "Arial",
        "font_size": 10,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
        "text_wrap": True,
    })
 
    text_fmt = wb.add_format({
        "font_name": "Arial",
        "font_size": 10,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
    })
 
    center_fmt = wb.add_format({
        "font_name": "Arial",
        "font_size": 10,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
    })
 
    int_fmt = wb.add_format({
        "font_name": "Arial",
        "font_size": 10,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
        "num_format": "0",
    })
 
    number_fmt = wb.add_format({
        "font_name": "Arial",
        "font_size": 10,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
        "num_format": "0.00",
    })
 
    total_label_fmt = wb.add_format({
        "bold": True,
        "font_name": "Arial",
        "font_size": 10,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
    })
 
    total_int_fmt = wb.add_format({
        "bold": True,
        "font_name": "Arial",
        "font_size": 10,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
        "num_format": "0",
    })
 
    total_number_fmt = wb.add_format({
        "bold": True,
        "font_name": "Arial",
        "font_size": 10,
        "align": "center",
        "valign": "vcenter",
        "border": 1,
        "num_format": "0.00",
    })
 
    # ── Column widths (A-F → 0-5) ──────────────────────────────
    col_widths = [6, 30, 28, 24, 14, 28]
    for col, w in enumerate(col_widths):
        ws.set_column(col, col, w)
 
    # ═══════════════════════════════════════════════════════════════
    # 2. HEADER ROWS  (rows 0-2, data starts at row 3)
    # ═══════════════════════════════════════════════════════════════
 
    # Row 0 — Report title (merged A1:F1)
    ws.merge_range(0, 0, 0, 5,
                   "Import Release Operator Productivity Report",
                   title_fmt)
 

 
    # Row 2 — From Date … To Date
    from_display = _parse_display_date_in_excel(start_date)
    to_display   = _parse_display_date_in_excel(end_date)
 
    ws.merge_range(
        1, 0, 1, 5,
        f"From: {from_display} to {to_display}",
        sub_title_fmt
    )
 
    # Row 3 — Column headers
    headers = [
        "SN",
        "Assigned Person (Emp. Code)",
        "Assigned Person Name",
        "(Awb + Hwb) Combination",
        "Pieces Sum",
        "Grs. Weight Sum ( Kgs. )",
    ]
    for col, h in enumerate(headers):
        ws.write(3, col, h, header_fmt)
    ws.set_row(3, 30)      # taller header row for wrapped text
 
    ws.freeze_panes(4, 0)  # freeze title + header rows
 
    # ═══════════════════════════════════════════════════════════════
    # 3. BUILD THE CTE QUERY
    # ═══════════════════════════════════════════════════════════════
    #
    # CTE: deduplicated_shipments
    # ────────────────────────────
    # For each (assigned_person, assignment_header_id) pair that
    # passes the date filter, we keep ONE representative row.
    # We pick MAX(no_of_pc) and MAX(weight_in_kgs) to avoid zeros
    # when one event row has NULLs/zeros and another has real values.
    #
    # This CTE is a subquery alias in SQLAlchemy core, then we
    # aggregate on top of it.
    # ─────────────────────────────────────────────────────────────
 
    # Step 1 — build the date-filtered, deduplicated subquery
    filters = WorkerAssignmentFilters(
        shipment_model=WorkerAssignmentShipment,
        status=None,           # no status filter for this report
        startDate=start_date,
        endDate=end_date,
    )
 
    # Inner query: one row per (assigned_person, header_id)
    dedup_inner = (
        filters.apply_date_filter(
            select(
                WorkerAssignmentShipment.assigned_person,
                WorkerAssignmentShipment.assignment_header_id,
                func.max(WorkerAssignmentShipment.no_of_pc)
                    .label("no_of_pc"),
                func.max(WorkerAssignmentShipment.weight_in_kgs)
                    .label("weight_in_kgs"),
            )
            .where(
                WorkerAssignmentShipment.assigned_person.isnot(None)
            )
        )
        .group_by(
            WorkerAssignmentShipment.assigned_person,
            WorkerAssignmentShipment.assignment_header_id,
        )
    )
 
    # 🔌 Extension point — attach any future extra filters to inner query
    if extra_filters:
        for f in extra_filters:
            dedup_inner = dedup_inner.where(f)
 
    dedup_cte = dedup_inner.cte("deduplicated_shipments")
 
    # Step 2 — aggregate over the CTE + join User for name
    UserAlias = aliased(User)
 
    agg_query = (
        select(
            dedup_cte.c.assigned_person.label("emp_code"),
            UserAlias.name.label("emp_name"),
            func.count(dedup_cte.c.assignment_header_id)
             .label("shipment_count"),
            func.coalesce(func.sum(dedup_cte.c.no_of_pc), 0)
                .label("piece_count"),
            func.coalesce(func.sum(dedup_cte.c.weight_in_kgs), 0.0)
                .label("total_weight"),
        )
        .outerjoin(
            UserAlias,
            UserAlias.emp_id == dedup_cte.c.assigned_person,
        )
        .group_by(
            dedup_cte.c.assigned_person,
            UserAlias.name,
        )
        .order_by(
            UserAlias.name.asc(),
        )
    )
 
    # ═══════════════════════════════════════════════════════════════
    # 4. STREAM DATA IN CHUNKS
    # ═══════════════════════════════════════════════════════════════
 
    row_num   = 4      # data starts at Excel row index 4 (5th row)
    sn        = 1
    total_awb = 0
    total_pcs = 0
    total_wgt = 0.0
    offset    = 0
 
    while True:
        result = await db.execute(
            agg_query.offset(offset).limit(chunk_size)
        )
        rows = result.all()
 
        if not rows:
            break
 
        for row in rows:
            ws.write(row_num, 0, sn,                         center_fmt)
            # ws.write(row_num, 1, row.emp_code or "",          text_fmt)
            ws.write_number(row_num,1,int(row.emp_code) if row.emp_code else 0,int_fmt)
            ws.write(row_num, 2, row.emp_name or "",          text_fmt)
            ws.write_number(row_num, 3, row.shipment_count,        int_fmt)
            ws.write_number(row_num, 4, row.piece_count,      int_fmt)
            ws.write_number(row_num, 5, float(row.total_weight), number_fmt)
 
            total_awb += row.shipment_count
            total_pcs += row.piece_count
            total_wgt += float(row.total_weight)
 
            row_num += 1
            sn      += 1
 
        offset += chunk_size
 
    # ═══════════════════════════════════════════════════════════════
    # 5. TOTALS ROW
    # ═══════════════════════════════════════════════════════════════
 
    ws.merge_range(row_num, 0, row_num, 2, "Total", total_label_fmt)
    ws.write_number(row_num, 3, total_awb,        total_int_fmt)
    ws.write_number(row_num, 4, total_pcs,        total_int_fmt)
    ws.write_number(row_num, 5, total_wgt,        total_number_fmt)
 
    # ═══════════════════════════════════════════════════════════════
    # 6. CLOSE & YIELD
    # ═══════════════════════════════════════════════════════════════
 
    wb.close()
    output.seek(0)
    yield output.read()
 


# ============== ✌️✌️✌️✌️✌️✌️ Auto assignment of workers (new) ==========================
# 🤖 AUTO-ASSIGNMENT — v1 (core: balance by current in-hand load only)
# ============================================================================
import logging
logger = logging.getLogger(__name__)

AUTO_ASSIGN_ACTIVITY_WINDOW_MIN    = 25
AUTO_ASSIGN_MAX_ACTIVE             = 10
AUTO_ASSIGN_DEFAULT_LOOKBACK_HOURS = 240

# # Tunable knobs (change freely):
# AUTO_ASSIGN_ACTIVITY_WINDOW_MIN     = 20   # worker must be active within this many minutes
# AUTO_ASSIGN_MAX_ACTIVE              = 4    # max active in-hand shipments per worker
# AUTO_ASSIGN_DEFAULT_LOOKBACK_HOURS  = 24   # which shipments to consider (recent only)
# AUTO_ASSIGN_FAIRNESS_WINDOW_HOURS   = 6    # "recent drops" window for fairness tie-break



async def run_auto_assignment(
    db: AsyncSession,
    *,
    changed_by: str,
    lookback_hours: int = AUTO_ASSIGN_DEFAULT_LOOKBACK_HOURS,
) -> dict:
    now = get_utc_now()
    activity_cutoff = now - timedelta(minutes=AUTO_ASSIGN_ACTIVITY_WINDOW_MIN)
    shipment_cutoff = now - timedelta(hours=lookback_hours)
    shipment = WorkerAssignmentShipment
    # ── 1) POOL: eligible workers + current in-hand load ──────────────────
    # active in-hand = assigned, not dropped, not delivered, has GP
    active_subq = (
        select(
            shipment.assigned_person.label("emp_id"),
            func.count(shipment.id).label("active_count"),
        )
        .where(
            shipment.assigned_person.isnot(None),
            shipment.drop_dlv_zone.is_(None),
            shipment.gate_pass_end_datetime.is_(None),
            shipment.gate_pass_no.isnot(None),
        )
        .group_by(shipment.assigned_person)
        .subquery()
    )
    pool_rows = (await db.execute(
        select(
            User.emp_id,
            func.coalesce(active_subq.c.active_count, 0).label("active_count"),
        )
        .outerjoin(active_subq, active_subq.c.emp_id == User.emp_id)
        .where(
            User.role == "imp_gp_user",
            User.is_active.is_(True),
            User.last_login_at.isnot(None),
            or_(
                User.last_logout_at.is_(None),
                User.last_login_at > User.last_logout_at,
            ),
            User.last_active_at >= activity_cutoff,
            func.coalesce(active_subq.c.active_count, 0) < AUTO_ASSIGN_MAX_ACTIVE,
        )
    )).all()
    if not pool_rows:
        return {"success": True, "assigned": 0, "pool_size": 0,
                "message": "No eligible workers."}
    load = {r.emp_id: int(r.active_count) for r in pool_rows}
    cap  = {r.emp_id: AUTO_ASSIGN_MAX_ACTIVE - int(r.active_count) for r in pool_rows}
    # ── 2) SHIPMENTS: unassigned, has GP, recent ──────────────────────────
    shipments = (await db.execute(
        select(shipment)
        .where(
            shipment.assigned_person.is_(None),
            shipment.gate_pass_no.isnot(None),
            func.trim(shipment.gate_pass_no) != "",
            or_(
                shipment.gate_pass_issued_date_time_combo >= shipment_cutoff,
                shipment.integrate_date_time >= shipment_cutoff,
            ),
        )
        .order_by(shipment.gate_pass_issued_date_time_combo.asc().nulls_last())
    )).scalars().all()

    if not shipments:
        return {"success": True, "assigned": 0, "pool_size": len(pool_rows),
                "message": "No assignable shipments."}
    # ── 3) DISTRIBUTE: least-loaded first ─────────────────────────────────
    assigned = 0
    # per-worker breakdown: emp_id -> list of full shipment info dicts
    assignments_by_worker: dict[str, list[dict]] = {}
    for s in shipments:
        candidates = [emp for emp in cap if cap[emp] > 0]
        if not candidates:
            break  # everyone full
        best = min(candidates, key=lambda e: (load[e], e))  # least-loaded
        s.assigned_person = best
        s.assigned_person_datetime = now
        s.updated_at = now
        load[best] += 1
        cap[best]  -= 1
        assigned += 1

        # full shipment info (every column on the row), not just a subset
        shipment_info = {
            col.name: getattr(s, col.name)
            for col in shipment.__table__.columns
        }
        assignments_by_worker.setdefault(best, []).append(shipment_info)

    await db.commit()

    # ── 4) LOG: summary only ───────────────────────────────────────────────
    for emp_id, items in assignments_by_worker.items():
        logger.info(
            "AutoAssign -> worker %s received %d shipment(s)",
            emp_id, len(items),
        )

    return {
        "success": True,
        "assigned": assigned,
        "pool_size": len(pool_rows),
        "total_candidates": len(shipments),
        "lookback_hours": lookback_hours,
        "assignments_by_worker": assignments_by_worker,
    }


async def auto_assign_job():
    """Background wrapper — opens its own session, calls the core assigner."""
    async with async_session() as db:
        try:
            result = await run_auto_assignment(db=db, changed_by="SYSTEM")

            assigned = result.get("assigned", 0)
            by_worker = result.get("assignments_by_worker", {})

            print(f">>> AUTO-ASSIGN DONE: {assigned} assigned <<<")

            # per-worker breakdown: who got how many, and each GP + shipment
            for emp_id, items in by_worker.items():
                print(f"    worker {emp_id} got {len(items)} shipment(s):")
                for s in items:
                    print(
                        f"        gp={s.get('gate_pass_no')} "
                        f"| shipment_id={s.get('id')} "
                        f"| header_id={s.get('assignment_header_id')}"
                    )

            logger.info(
                "[auto-assign job] assigned=%s pool=%s candidates=%s",
                result["assigned"], result["pool_size"], result.get("total_candidates", 0),
            )
        except Exception as e:
            logger.exception("[auto-assign job] FAILED: %s", e)
            print(f">>> AUTO-ASSIGN FAILED: {e} <<<")

# async def auto_assign_job():
#     """Background wrapper — opens its own session, calls the core assigner."""
#     async with async_session() as db:
#         try:
#             result = await run_auto_assignment(db=db, changed_by="SYSTEM")
#             print(f">>> AUTO-ASSIGN DONE: {result.get('assigned')} assigned <<<")  # 🆕
#             logger.info(
#                 "[auto-assign job] assigned=%s pool=%s candidates=%s",
#                 result["assigned"], result["pool_size"], result.get("total_candidates", 0),
#             )
#         except Exception as e:
#             logger.exception("[auto-assign job] FAILED: %s", e)
#             print(f">>> AUTO-ASSIGN FAILED: {e} <<<")


# ================------------------------>end auto assignment ---------------------==============


async def get_imp_gp_user_presence_list(db: AsyncSession) -> list[dict]:
    """
    List active imp_gp_user workers with login/logout/activity state,
    an online flag (active within AUTO_ASSIGN_ACTIVITY_WINDOW_MIN),
    and their current active-shipment count (in-hand: assigned, not dropped,
    not delivered, has GP).
    """
    now = get_utc_now()
    activity_cutoff = now - timedelta(minutes=AUTO_ASSIGN_ACTIVITY_WINDOW_MIN)

    shipment = WorkerAssignmentShipment

    # per-worker active in-hand count (same 4-condition definition)
    active_subq = (
        select(
            shipment.assigned_person.label("emp_id"),
            func.count(shipment.id).label("active_count"),
        )
        .where(
            shipment.assigned_person.isnot(None),
            shipment.drop_dlv_zone.is_(None),
            # shipment.gate_pass_end_datetime.is_(None),
            # shipment.gate_pass_no.isnot(None),
        )
        .group_by(shipment.assigned_person)
        .subquery()
    )

    stmt = (
        select(
            User.emp_id,
            User.name,
            User.is_active,
            User.last_login_at,
            User.last_logout_at,
            User.last_active_at,
            func.coalesce(active_subq.c.active_count, 0).label("active_count"),
        )
        .outerjoin(active_subq, active_subq.c.emp_id == User.emp_id)
        .where(
            User.role == "imp_gp_user",
            User.is_active.is_(True),
        )
        .order_by(User.name.asc())
    )

    rows = (await db.execute(stmt)).all()

    results = []
    for r in rows:
        # logged in = has a login, and it's newer than last logout (or never logged out)
        logged_in = (
            r.last_login_at is not None
            and (r.last_logout_at is None or r.last_login_at > r.last_logout_at)
        )
        # fresh = acted within the activity window
        fresh = r.last_active_at is not None and r.last_active_at >= activity_cutoff

        is_online = bool(logged_in and fresh)

        results.append({
            "emp_id": r.emp_id,
            "name": r.name,
            "is_active": r.is_active,
            "last_login_at": r.last_login_at,
            "last_logout_at": r.last_logout_at,
            "last_active_at": r.last_active_at,
            "is_online": is_online,
            "active_shipment_count": int(r.active_count),
        })

    return results , AUTO_ASSIGN_ACTIVITY_WINDOW_MIN



async def get_worker_assigned_shipments_drilldown(
    db: AsyncSession,
    emp_id: str,
    drop_status: str = "not_dropped",   # not_dropped | dropped | all
    window: str = "24h",                # 24h | 48h | 1week | all
) -> dict:
    """
    Drill-down: shipments assigned to a worker, filtered by drop status
    and an assignment-time window (on assigned_person_datetime).
    """
    now = get_utc_now()

    # --- time window (on assigned_person_datetime) ---
    window_map = {
        "24h":   timedelta(hours=24),
        "48h":   timedelta(hours=48),
        "1week": timedelta(days=7),
    }
    cutoff = None if window == "all" else now - window_map.get(window, timedelta(hours=24))

    shipment = WorkerAssignmentShipment
    header = WorkerAssignmentHeader

    conditions = [
        shipment.assigned_person == emp_id,
        # shipment.gate_pass_no.isnot(None),   # real GP shipments
    ]

    # --- drop status filter ---
    if drop_status == "not_dropped":
        conditions += [
            shipment.drop_dlv_zone.is_(None),
            # shipment.gate_pass_end_datetime.is_(None),
        ]
    elif drop_status == "dropped":
        conditions.append(shipment.drop_dlv_zone.isnot(None))
    # "all" → no extra drop condition

    # --- window filter ---
    if cutoff is not None:
        conditions.append(shipment.assigned_person_datetime >= cutoff)

    stmt = (
        select(shipment, header)
        .join(header, shipment.assignment_header_id == header.id)
        .where(*conditions)
        .order_by(shipment.assigned_person_datetime.desc())
    )

    rows = (await db.execute(stmt)).all()

    data = []
    for s, h in rows:
        data.append({
            # identity
            "shipment_id": s.id,
            "header_id": h.id,
            "oc_no": h.oc_no,
            "awb_no": h.awb_no,
            "hawb": h.hawb,
            "gate_pass_no": s.gate_pass_no,

            # operational
            "location": s.location,
            "no_of_pc": s.no_of_pc,
            "weight_in_kgs": s.weight_in_kgs,
            "chg_wgt_in_kg": s.chg_wgt_in_kg,
            "drop_dlv_zone": s.drop_dlv_zone,

            # timestamps (the focus)
            "gate_pass_issued_date_time_combo": s.gate_pass_issued_date_time_combo,
            "gate_pass_end_datetime": s.gate_pass_end_datetime,
            "integrate_date_time": s.integrate_date_time,
            "assigned_person_datetime": s.assigned_person_datetime,
            "drop_dlv_zone_datetime": s.drop_dlv_zone_datetime,
            "gp_received_datetime": s.gp_received_datetime,
            "final_delivery_datetime": s.final_delivery_datetime,

            # status helpers for the UI
            "is_dropped": s.drop_dlv_zone is not None,
            "is_delivered": s.gate_pass_end_datetime is not None,
        })

    return {
        "emp_id": emp_id,
        "drop_status": drop_status,
        "window": window,
        "total": len(data),
        "data": data,
    }