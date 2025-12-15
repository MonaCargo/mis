from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import HTTPException
import pytz
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.dock_availability import DockAvailability
from app.db.models.export_slot_file import AWBDockOperation, AWBSequence, DockOperationAWBLink, ExportSlotAWB, ExportSlotFileRecord
from app.schemas.base import Pagination
from app.schemas.dock import DockOutRequest, DockOutResponse, DockScanRead, DockScanRequest, DockScanResponse
from fastapi import HTTPException, status
from sqlalchemy.orm import selectinload
from app.schemas.export_slot_file import AWBSequenceResponse, AddAWBSequenceRequest, ExportSlotFullResponse, ExportSlotFullResponseForDock
from app.utils.common.helperFunction import *


class DockService:

    @staticmethod
    async def process_dock_scan(
        db: AsyncSession,
        scan_data: DockScanRequest,
        emp_id: str,
    ) -> DockScanResponse:
        """
        Process dock scan - update dock in time and related fields
        """
        try:
            # Find the export slot record
            stmt = select(ExportSlotFileRecord).where(
                and_(
                    ExportSlotFileRecord.token_no == scan_data.token_no,
                    ExportSlotFileRecord.truck_number == scan_data.truck_number,
                    ExportSlotFileRecord.truck_slot_from == scan_data.truck_slot_from
                )
            )
            result = await db.execute(stmt)
            export_slot = result.scalar_one_or_none()

            if not export_slot:
                raise ValueError("Export slot record not found")

            # 🚫 Must be truck-in first
            if not export_slot.is_truck_in:
                raise HTTPException(400, "Truck must be IN before docking")

            # 🚫 block only when currently docked in and not docked out
            if export_slot.current_is_dock_in and not export_slot.current_is_dock_out:
                raise HTTPException(400, "Truck already docked-in. Perform dock-out first.")
            
                        # 🚫 Must be truck-in first
            if export_slot.is_truck_out:
                raise HTTPException(400, "Truck already out.")

            # 🔥 Now update new structure fields
            now = datetime.now(timezone.utc)
            export_slot.current_is_dock_in = True
            export_slot.current_is_dock_out = False
            export_slot.current_dock_out_date_time = None
            export_slot.current_dock_in_date_time = now
            export_slot.current_dock_in_by = emp_id
            export_slot.current_dock_out_by = None
            export_slot.current_dock_in_by_device = scan_data.current_dock_in_by_device
            export_slot.updated_at = now

            if scan_data.current_dock_number:
                export_slot.current_dock_number = scan_data.current_dock_number


            # Commit changes
            await db.commit()
            await db.refresh(export_slot)

            # ✅ Convert SQLAlchemy model → Pydantic model
            dock_data = DockScanRead.model_validate(export_slot, from_attributes=True)

            return dock_data

        except Exception as e:
            await db.rollback()
            raise RuntimeError(f"Error processing dock scan: {str(e)}")

    # @staticmethod
    # async def process_dock_out(
    #     db: AsyncSession,
    #     scan_data: DockScanRequest,
    #     emp_id: str
    # ) -> DockOutResponse:
    #     """
    #     Process dock out - update dock out time and related fields
    #     """
    #     try:
    #         stmt = select(ExportSlotFileRecord).where(
    #             and_(
    #                 ExportSlotFileRecord.token_no == scan_data.token_no,
    #                 ExportSlotFileRecord.truck_number == scan_data.truck_number,
    #                 ExportSlotFileRecord.truck_slot_from == scan_data.truck_slot_from
    #             )
    #         )
    #         result = await db.execute(stmt)
    #         export_slot = result.scalar_one_or_none()

    #         if not export_slot:
    #             raise ValueError("Export slot record not found")

    #         if not export_slot.current_is_dock_in:
    #             raise ValueError("Truck is not docked in")

    #         if export_slot.current_is_dock_out:
    #             raise ValueError("Truck is already docked out")

    #         # Update dock out fields
    #         current_time = datetime.now(timezone.utc)
    #         export_slot.current_is_dock_out = True
    #         export_slot.current_dock_out_date_time = current_time
    #         export_slot.current_dock_out_by = emp_id
    #         export_slot.updated_at = get_utc_now()

    #         await db.commit()
    #         await db.refresh(export_slot)

            
    #         # Convert SQLAlchemy model → Pydantic model
    #         dock_data = DockScanRead.model_validate(export_slot, from_attributes=True)
    #         return dock_data

    #     except Exception as e:
    #         await db.rollback()
    #         raise RuntimeError(f"Error processing dock out: {str(e)}")
        
    @staticmethod
    async def process_dock_out(
    db: AsyncSession,
    scan_data: DockOutRequest,
    emp_id: str
) -> DockOutResponse:
        """
        Perform Dock-Out operation for a truck export slot.
        Rules:
        - Truck must be in
        - Must be currently docked in
        - Must NOT be already docked out
        - Dock operation session exists only if scans happened → close it
        """

        try:
            # ----------------📌 1) Verify Export Slot ----------------
            stmt = select(ExportSlotFileRecord).where(
                and_(
                    ExportSlotFileRecord.token_no == scan_data.token_no,
                    ExportSlotFileRecord.truck_number == scan_data.truck_number,
                    ExportSlotFileRecord.truck_slot_from == scan_data.truck_slot_from
                )
            )
            result = await db.execute(stmt)
            export_slot = result.scalar_one_or_none()

            if not export_slot:
                raise HTTPException(404, "Export slot not found")

            if not export_slot.is_truck_in:
                raise HTTPException(400, "Truck not IN, cannot dock-out")

            if not export_slot.current_is_dock_in:
                raise HTTPException(400, "Truck is not docked-in currently")

            if export_slot.current_is_dock_out:
                raise HTTPException(400, "Truck already docked-out")


            # ----------------📌 2) Find Active Dock Operation (if scans exist) ----------------
            active_dock = (await db.execute(
                select(AWBDockOperation).where(
                    and_(
                        AWBDockOperation.export_slot_id == export_slot.id,
                        AWBDockOperation.dock_out_date_time.is_(None)  # active
                    )
                )
            )).scalar_one_or_none()

            current_time = get_utc_now()

            # ---------🟢 Only close dock session if it exists (means at least one scan happened)
            if active_dock:
                active_dock.dock_out_date_time = current_time
                active_dock.is_dock_out = True
                active_dock.dock_out_by = emp_id
                active_dock.updated_at = current_time
                active_dock.dock_out_by_device = scan_data.dock_out_by_device


            # ----------------📌 3) Update Parent ExportSlot Live Status ----------------
            export_slot.current_is_dock_out = True
            export_slot.current_dock_out_date_time = current_time
            export_slot.current_dock_out_by = emp_id
            export_slot.updated_at = current_time

                    # ----------------📌 3.1) Free dock availability ----------------
            if export_slot.current_dock_number:
                dock = (
                    await db.execute(
                        select(DockAvailability).where(
                            DockAvailability.dock_no == export_slot.current_dock_number
                        )
                    )
                ).scalar_one_or_none()

                if dock:
                    dock.is_dock_occupied = False
                    dock.dock_in_time = None
                    dock.updated_at = current_time

            # ----------------📌 4) Commit & Return ----------------
            await db.commit()
            await db.refresh(export_slot)

            # return clean dock data after out
            # 🔥 Must return DockScanRead inside data
             # Convert to dock-view schema

            dock_view = DockScanRead.model_validate(export_slot, from_attributes=True)
            print(dock_view,"dock_view")
            # return DockOutResponse(
            #     success=True,
            #     message="Dock-out completed successfully",
            #     data=dock_view
            # )
            return dock_view

        except HTTPException:
            raise        # keep original status

        except Exception as e:
            await db.rollback()
            raise HTTPException(500, f"Dock-Out Error: {str(e)}")

    @staticmethod
    async def add_awb_sequences(db, request: AddAWBSequenceRequest,emp_id:str):

        slot = (await db.execute(
            select(ExportSlotFileRecord).where(
                and_(
                    ExportSlotFileRecord.token_no == request.token_no,
                    ExportSlotFileRecord.truck_number == request.truck_number,
                    ExportSlotFileRecord.truck_slot_from == request.truck_slot_from
                )
            )
        )).scalar_one_or_none()

        if not slot: raise HTTPException(404,"Slot not found")
        if not slot.is_truck_in: raise HTTPException(400,"Truck must be IN")
        if not slot.current_is_dock_in: raise HTTPException(400,"Dock-IN required before scanning")

        # find existing active dock session
        active_dock = (await db.execute(
            select(AWBDockOperation).where(
                and_(
                    AWBDockOperation.export_slot_id==slot.id,
                    AWBDockOperation.dock_out_date_time.is_(None)
                )
            )
        )).scalar_one_or_none()

        if not active_dock:
            active_dock = AWBDockOperation(
                export_slot_id=slot.id,
                dock_number=slot.current_dock_number,
                dock_in_by=emp_id,
                dock_in_by_device = slot.current_dock_in_by_device,
                dock_in_date_time=slot.current_dock_in_date_time
            )
            db.add(active_dock)
            await db.flush()

        all_seq = []
        for awb in request.awbList:

            # check awb exists
            awb_rec = (await db.execute(
                select(ExportSlotAWB).where(
                    and_(ExportSlotAWB.export_slot_id==slot.id, ExportSlotAWB.awb_id==awb.awb_id)
                )
            )).scalar_one_or_none()

            if not awb_rec:
                awb_rec = ExportSlotAWB(
                    export_slot_id=slot.id,
                    awb_id=awb.awb_id,
                    pcs=awb.pcs,
                    is_additional=awb.is_additional,
                    created_at=get_utc_now(),
                    updated_at=get_utc_now()
                )
                db.add(awb_rec)
                await db.flush()

            # 🔥 ensure awb linked to this dock session
            exists = (await db.execute(
                select(DockOperationAWBLink).where(
                    and_(
                        DockOperationAWBLink.dock_operation_id==active_dock.id,
                        DockOperationAWBLink.awb_record_id==awb_rec.id
                    )
                )
            )).scalar_one_or_none()

            if not exists:
                db.add(DockOperationAWBLink(dock_operation_id=active_dock.id, awb_record_id=awb_rec.id))

            for seq in awb.sequences:

                duplicate = (await db.execute(
                    select(AWBSequence).where(
                        and_(AWBSequence.awb_record_id==awb_rec.id,
                            AWBSequence.seq_number==seq.seq_number)
                    )
                )).scalar_one_or_none()

                if duplicate: continue

                s = AWBSequence(
                    awb_record_id=awb_rec.id,
                    dock_operation_id=active_dock.id,
                    seq_number=seq.seq_number,
                    seq_time=seq.seq_time,
                    scanned_by_user = emp_id or request.scanned_by_user,
                    scanned_by_device = request.scanned_by_device or None,

                    created_at=get_utc_now(), updated_at=get_utc_now()
                )
                db.add(s)
                all_seq.append(s)

        # await db.commit()
        # return [AWBSequenceResponse.model_validate(x, from_attributes=True) for x in all_seq]
                # ------------------ BEFORE RETURN SECTION ------------------
                await db.commit()
        for seq in all_seq:
            await db.refresh(seq)

        # -----------------------------------------
        # Transform Response according to schema
        # -----------------------------------------
        result = {}

        for seq in all_seq:

            # Fetch AWB via ID instead of lazy relationship call
            awb_row = await db.execute(
                select(ExportSlotAWB.awb_id).where(ExportSlotAWB.id == seq.awb_record_id)
            )
            awb_id = awb_row.scalar()  # string awb no

            if awb_id not in result:
                result[awb_id] = {
                    "awb_id": awb_id,
                    "new_sequences": []
                }

            result[awb_id]["new_sequences"].append({
                "seq_id": seq.id,
                "seq_number": seq.seq_number,
                "seq_time": seq.seq_time
            })

        return list(result.values())
      


    # @staticmethod
    # async def get_truck_slots_by_specific_date(
    #     db: AsyncSession,
    #     date: Optional[datetime] = None,
    #     limit: Optional[int] = None,
    #     offset: Optional[int] = None,
    #     dockOut: Optional[bool] = False,
    # ):
    #     IST = pytz.timezone("Asia/Kolkata")  # or ZoneInfo("Asia/Kolkata")
    #     # If no date provided, use today in IST
    #     if date is None:
    #         now_ist = datetime.now(IST)
    #         start_ist = datetime(now_ist.year, now_ist.month, now_ist.day, tzinfo=IST)
    #     else:
    #         # Incoming date is naive → treat as IST
    #         if date.tzinfo is None:
    #             start_ist = IST.localize(datetime(date.year, date.month, date.day))
    #         else:
    #             # Normalize to IST midnight
    #             start_ist = date.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)

    #     # End of day in IST
    #     end_ist = start_ist + timedelta(days=1)

    #     # Convert both to UTC for DB filtering
    #     start_utc = start_ist.astimezone(timezone.utc)
    #     end_utc = end_ist.astimezone(timezone.utc)

    #     # Count query
    #     count_stmt = select(func.count()).select_from(ExportSlotFileRecord).where(
    #         and_(
    #             ExportSlotFileRecord.truck_slot_from >= start_utc,
    #             ExportSlotFileRecord.truck_slot_from < end_utc,
    #         )
    #     )
    #     total = (await db.execute(count_stmt)).scalar_one()

    #     conditions = [
    #     ExportSlotFileRecord.truck_slot_from >= start_utc,
    #     ExportSlotFileRecord.truck_slot_from < end_utc,
    #     ExportSlotFileRecord.is_truck_in == True
    #     ]
    #     if dockOut:
    #         conditions.append(ExportSlotFileRecord.is_dock_in == True)
    

    #     # Main query
    #     stmt = (
    #         select(ExportSlotFileRecord)
    #         .options(
    #          selectinload(ExportSlotFileRecord.awbs)
    #         .selectinload(ExportSlotAWB.sequences),

    #          selectinload(ExportSlotFileRecord.awbs)
    #         .selectinload(ExportSlotAWB.dock_operations)
    #         .selectinload(AWBDockOperation.sequences),
    # )
    #         .where(
    #             and_(
    #                 *conditions
    #             )
    #         )
    #         .order_by(ExportSlotFileRecord.truck_slot_from.desc())
    #     )

    #     # Pagination defaults
    #     if limit is None:
    #         limit = total
    #     if offset is None:
    #         offset = 0

    #     stmt = stmt.limit(limit).offset(offset)

    #     result = await db.execute(stmt)
    #     records = result.scalars().unique().all()
    #     data = [ExportSlotFullResponseForDock.model_validate(r) for r in records]
    #     pagination = Pagination(total=total, limit=limit, offset=offset)

    #     return data, pagination
    @staticmethod
    async def get_truck_slots_by_specific_date(
        db: AsyncSession,
        date: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        dockOut: Optional[bool] = False,
    ):

        IST = pytz.timezone("Asia/Kolkata")

        if date is None:
            now_ist = datetime.now(IST)
            start_ist = datetime(now_ist.year, now_ist.month, now_ist.day, tzinfo=IST)
        else:
            start_ist = IST.localize(date) if date.tzinfo is None else date.astimezone(IST).replace(hour=0,minute=0,second=0,microsecond=0)

        end_ist = start_ist + timedelta(days=1)

        start_utc = start_ist.astimezone(timezone.utc)
        end_utc = end_ist.astimezone(timezone.utc)

        conditions = [
            ExportSlotFileRecord.truck_slot_from >= start_utc,
            ExportSlotFileRecord.truck_slot_from < end_utc,
            ExportSlotFileRecord.is_truck_in == True
        ]
        if dockOut:
            conditions.append(ExportSlotFileRecord.current_is_dock_in == True)

        # load all relations including dock + seq
        stmt = (
            select(ExportSlotFileRecord)
            .options(
                selectinload(ExportSlotFileRecord.awbs)
                    .selectinload(ExportSlotAWB.sequences),
                selectinload(ExportSlotFileRecord.awbs)
                    .selectinload(ExportSlotAWB.dock_operations)
                    .selectinload(AWBDockOperation.sequences)
            )
            .where(and_(*conditions))
            .order_by(ExportSlotFileRecord.truck_slot_from.desc())
            .limit(limit or 99999)
            .offset(offset or 0)
        )

        result = await db.execute(stmt)
        records = result.scalars().unique().all()

        final_response = []

        for slot in records:

            awb_list = []
            for awb in slot.awbs:

                # 1️⃣ Build dock summary with scanned_pcs count
                dock_summary = []
                for dock in awb.dock_operations:
                    scanned = len([s for s in dock.sequences if s.awb_record_id == awb.id])
                    dock_summary.append({
                        "id": dock.id,
                        "dock_number": dock.dock_number,
                        "dock_in_date_time": dock.dock_in_date_time,
                        "dock_out_date_time": dock.dock_out_date_time,
                        "scanned_pcs": scanned
                    })

                # 2️⃣ Add AWB mapped structure
                awb_list.append({
                    "id": awb.id,
                    "awb_id": awb.awb_id,
                    "export_slot_id": slot.id,
                    "pcs": awb.pcs,
                    "is_additional": awb.is_additional,
                    "dock_operations": dock_summary,
                    "sequences": [AWBSequenceResponse.model_validate(s) for s in awb.sequences]
                })

            # 3️⃣ Build complete parent row response
            final_response.append(
                ExportSlotFullResponseForDock.model_validate({
                    **slot.__dict__,
                    "awbs": awb_list      # maps into awbList via alias
                }, from_attributes=True)
            )

        if limit is None:
            limit = len(final_response)    # or total
        if offset is None:
            offset = 0

        pagination = Pagination(
            total=len(final_response),
            limit=limit,
            offset=offset
        )

        return final_response, pagination






                
    # @staticmethod
    # async def revert_dock_in(
    #     db,
    #     token_no: str,
    #     truck_number: str,
    #     truck_slot_from: datetime,
    #     emp_id: str
    # ):
    #     """
    #     Revert the dock-in process for a truck if:
    #     - is_dock_in == True
    #     - is_dock_out == False
    #     - is_truck_out == False
    #     """
    #     try:
    #         # 1️⃣ Find the export slot
    #         stmt = select(ExportSlotFileRecord).options(
    #           selectinload(ExportSlotFileRecord.awbs).selectinload(ExportSlotAWB.sequences)
    #         ).where(
    #             and_(
    #                 ExportSlotFileRecord.token_no == token_no,
    #                 ExportSlotFileRecord.truck_number == truck_number,
    #                 ExportSlotFileRecord.truck_slot_from == truck_slot_from
    #             )
    #         )
    #         result = await db.execute(stmt)
    #         export_slot = result.scalar_one_or_none()

    #         if not export_slot:
    #             raise HTTPException(
    #                 status_code=status.HTTP_404_NOT_FOUND,
    #                 detail="Export slot record not found."
    #             )

    #         # 2️⃣ Validate conditions
    #         if not export_slot.is_dock_in:
    #             raise HTTPException(
    #                 status_code=status.HTTP_400_BAD_REQUEST,
    #                 detail="Truck is not docked in — cannot revert."
    #             )
    #         if export_slot.is_dock_out:
    #             raise HTTPException(
    #                 status_code=status.HTTP_400_BAD_REQUEST,
    #                 detail="Truck already docked out — cannot revert dock-in."
    #             )
    #         if export_slot.is_truck_out:
    #             raise HTTPException(
    #                 status_code=status.HTTP_400_BAD_REQUEST,
    #                 detail="Truck already checked out — cannot revert dock-in."
    #             )

    #         # 3️⃣ Reset dock-in fields
    #         export_slot.is_dock_in = False
    #         export_slot.dock_in_date_time = None
    #         export_slot.dock_in_by = None
    #         export_slot.dock_number = None
           

    #         await db.commit()
    #         await db.refresh(export_slot)

    #         return export_slot

    #     except HTTPException:
    #         raise
    #     except Exception as e:
    #         await db.rollback()
    #         raise HTTPException(
    #             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
    #             detail=f"Error reverting dock-in: {str(e)}"
    #         )


    @staticmethod
    async def revert_dock_in(
        db: AsyncSession,
        token_no: str,
        truck_number: str,
        truck_slot_from: datetime,
        emp_id: str
    ):
        try:
            # ---------------- 1) Fetch Parent ----------------
            stmt = (
                select(ExportSlotFileRecord)
                .options(selectinload(ExportSlotFileRecord.awbs))
                .where(
                    ExportSlotFileRecord.token_no == token_no,
                    ExportSlotFileRecord.truck_number == truck_number,
                    ExportSlotFileRecord.truck_slot_from == truck_slot_from
                )
            )
            result = await db.execute(stmt)
            slot = result.scalar_one_or_none()

            if not slot:
                raise HTTPException(404, "Export slot not found")

            # ---------------- 2) Check Eligibility ----------------
            if not slot.current_is_dock_in:
                raise HTTPException(400, "Truck is not docked-in. Nothing to revert.")

            if slot.current_is_dock_out:
                raise HTTPException(400, "Truck already docked-out. Cannot revert.")

            if slot.is_truck_out:
                raise HTTPException(400, "Truck already exited yard. Cannot revert.")

            # ---------------- 3) Check If Current Dock Has Scans ----------------
            active_dock = (
                await db.execute(
                    select(AWBDockOperation)
                    .where(
                        AWBDockOperation.export_slot_id == slot.id,
                        AWBDockOperation.dock_out_date_time.is_(None)
                    )
                    .order_by(AWBDockOperation.id.desc())
                )
            ).scalar_one_or_none()

            if active_dock:
                # count scans
                seq_count = (
                    await db.execute(
                        select(func.count(AWBSequence.id))
                        .where(AWBSequence.dock_operation_id == active_dock.id)
                    )
                ).scalar_one()

                if seq_count > 0:
                    raise HTTPException(
                        400,
                        "Cannot revert dock-in — scans already exist. Perform Dock-Out instead."
                    )

                # Safe delete this empty dock session
                await db.delete(active_dock)


            # ---------------- 4) Restore Last Completed Dock If Exists ----------------
            # last_dock = (
            #     await db.execute(
            #         select(AWBDockOperation)
            #         .where(
            #             AWBDockOperation.export_slot_id == slot.id,
            #             AWBDockOperation.dock_out_date_time.isnot(None)
            #         )
            #         .order_by(AWBDockOperation.dock_out_date_time.desc())
            #     )
            # ).scalar_one_or_none()

            last_dock = (
            await db.execute(
                select(AWBDockOperation)
                .where(
                    AWBDockOperation.export_slot_id == slot.id,
                    AWBDockOperation.dock_out_date_time.isnot(None)
                )
                .order_by(AWBDockOperation.dock_out_date_time.desc())
             )
             ).scalars().first() 

            # ---------------- 4) FREE DOCK FROM AVAILABILITY BEFORE RESETTING ----------------
            previous_dock = slot.current_dock_number   # store old dock before modifying

            if previous_dock:
                dock = (await db.execute(
                    select(DockAvailability).where(
                        DockAvailability.dock_no == previous_dock
                    )
                )).scalar_one_or_none()

                if dock:
                    dock.is_dock_occupied = False
                    dock.dock_in_time = None
                    dock.updated_at = get_utc_now()

          # ---------------- 5) Restore Last Completed Dock If Exists ----------------
            if last_dock:
                slot.current_dock_number = last_dock.dock_number
                slot.current_dock_in_date_time = last_dock.dock_in_date_time
                slot.current_dock_out_date_time = last_dock.dock_out_date_time
                slot.current_dock_in_by = last_dock.dock_in_by
                slot.current_dock_out_by = last_dock.dock_out_by
                slot.current_is_dock_in = True
                slot.current_is_dock_out = True
            else:
                # No past history → clean slate
                slot.current_dock_number = None
                slot.current_dock_in_date_time = None
                slot.current_dock_out_date_time = None
                slot.current_dock_in_by_device = None
                slot.current_dock_in_by = None
                slot.current_dock_out_by = None
                slot.current_is_dock_in = False
                slot.current_is_dock_out = False

            slot.updated_at = get_utc_now()

            # ---------------- 5) Commit Changes ----------------
            await db.commit()
            await db.refresh(slot)

            return ExportSlotFullResponse.model_validate(slot, from_attributes=True)

        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            raise HTTPException(500, f"Revert Dock-In Error: {str(e)}")
