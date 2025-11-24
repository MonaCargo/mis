from datetime import datetime, timedelta, timezone
from typing import List, Optional
from fastapi import HTTPException
import pytz
from sqlalchemy import and_, func, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.export_slot_file import AWBSequence, ExportSlotAWB, ExportSlotFileRecord
from app.schemas.base import Pagination
from app.schemas.dock import DockOutResponse, DockScanRead, DockScanRequest, DockScanResponse
from fastapi import HTTPException, status
from sqlalchemy.orm import selectinload
from app.schemas.export_slot_file import AWBSequenceResponse, AddAWBSequenceRequest, ExportSlotFullResponse
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

            # Check if already docked in
            if export_slot.is_dock_in or export_slot.dock_in_date_time:
                raise ValueError("Truck is already docked in")

            # Check if truck is in (truck_in )
            if not export_slot.is_truck_in:
                raise ValueError("Truck must be in before docking")

            # Update dock in fields
            current_time = datetime.now(timezone.utc)
            export_slot.is_dock_in = True
            export_slot.dock_in_date_time = current_time
            export_slot.dock_in_by = emp_id
            export_slot.updated_at = get_utc_now()

            if scan_data.dock_number:
                export_slot.dock_number = scan_data.dock_number

            # Commit changes
            await db.commit()
            await db.refresh(export_slot)

            # ✅ Convert SQLAlchemy model → Pydantic model
            dock_data = DockScanRead.model_validate(export_slot, from_attributes=True)

            return dock_data

        except Exception as e:
            await db.rollback()
            raise RuntimeError(f"Error processing dock scan: {str(e)}")

    @staticmethod
    async def process_dock_out(
        db: AsyncSession,
        scan_data: DockScanRequest,
        emp_id: str
    ) -> DockOutResponse:
        """
        Process dock out - update dock out time and related fields
        """
        try:
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

            if not export_slot.is_dock_in:
                raise ValueError("Truck is not docked in")

            if export_slot.is_dock_out:
                raise ValueError("Truck is already docked out")

            # Update dock out fields
            current_time = datetime.now(timezone.utc)
            export_slot.is_dock_out = True
            export_slot.dock_out_date_time = current_time
            export_slot.dock_out_by = emp_id
            export_slot.updated_at = get_utc_now()

            await db.commit()
            await db.refresh(export_slot)

            
            # Convert SQLAlchemy model → Pydantic model
            dock_data = DockScanRead.model_validate(export_slot, from_attributes=True)
            return dock_data

        except Exception as e:
            await db.rollback()
            raise RuntimeError(f"Error processing dock out: {str(e)}")
        


    @staticmethod
    async def add_awb_sequences(
        db,
        request: AddAWBSequenceRequest,
    ) -> List[AWBSequenceResponse]:
        """
        Add AWBs + sequences for a given export slot (truck).
        - Creates new AWB entries if missing
        - Adds multiple sequences per AWB
        - Validates truck_in and dock_in before proceeding
        """
        try:
            # 1️⃣ Fetch export slot (truck record)
            stmt = select(ExportSlotFileRecord).where(
                and_(
                    ExportSlotFileRecord.token_no == request.token_no,
                    ExportSlotFileRecord.truck_number == request.truck_number,
                    ExportSlotFileRecord.truck_slot_from == request.truck_slot_from
                )
            )
            result = await db.execute(stmt)
            export_slot = result.scalar_one_or_none()

            if not export_slot:
                raise HTTPException(status_code=404, detail="Export slot not found")

            # 2️⃣ Validate truck_in and dock_in status
            if not export_slot.is_truck_in:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Truck must be checked in before adding AWBs or sequences",
                )
            if not export_slot.is_dock_in:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Truck must be docked in before adding AWBs or sequences",
                )

            all_new_sequences = []

            # 3️⃣ Process each AWB in the list
            for awb_item in request.awbList:
                awb_id = str(awb_item.awb_id)
                pcs = awb_item.pcs
                is_additional = awb_item.is_additional

                # Check if AWB already exists for this export slot
                awb_stmt = select(ExportSlotAWB).where(
                    and_(
                        ExportSlotAWB.export_slot_id == export_slot.id,
                        ExportSlotAWB.awb_id == awb_id
                    )
                )
                awb_result = await db.execute(awb_stmt)
                awb_record = awb_result.scalar_one_or_none()

                # 4️⃣ If not found → create a new AWB record
                if not awb_record:
                    awb_record = ExportSlotAWB(
                        export_slot_id=export_slot.id,
                        awb_id=awb_id,
                        pcs=pcs,
                        is_additional=is_additional,
                        created_at=get_utc_now(),
                        updated_at=get_utc_now(),
                    )
                    export_slot.updated_at = get_utc_now()  # mark parent as updated        
                    db.add(awb_record)
                    await db.flush()  # Get the new AWB ID

                # 5️⃣ Add all sequences under this AWB
                for seq_item in awb_item.sequences:
                    # Optional: Skip duplicate sequence numbers
                    existing_seq_stmt = select(AWBSequence).where(
                        and_(
                            AWBSequence.awb_record_id == awb_record.id,
                            AWBSequence.seq_number == seq_item.seq_number
                        )
                    )
                    existing_seq = (await db.execute(existing_seq_stmt)).scalar_one_or_none()
                    if existing_seq:
                        continue  # Skip duplicates

                    new_seq = AWBSequence(
                        awb_record_id=awb_record.id,
                        seq_number=seq_item.seq_number,
                        seq_time=seq_item.seq_time,
                        created_at=get_utc_now(),
                        updated_at=get_utc_now(),
                        
                        # created_at=datetime.utcnow(), #LET'S HANDLE IT BY DATABASE LEVEL
                        # updated_at=datetime.utcnow(),
                    )
                    db.add(new_seq)
                    all_new_sequences.append(new_seq)
            export_slot.updated_at = get_utc_now()  # ✅ This updates parent when AWBs/sequences change
            # 6️⃣ Commit everything
            await db.commit()

            # 7️⃣ Refresh to get IDs
            for seq in all_new_sequences:
                await db.refresh(seq)

            # 8️⃣ Return all new sequences as responses
            return [AWBSequenceResponse.model_validate(seq, from_attributes=True) for seq in all_new_sequences]

        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error while adding AWBs and sequences: {str(e)}",
            )

    
    @staticmethod
    async def revert_dock_in(
        db,
        token_no: str,
        truck_number: str,
        truck_slot_from: datetime,
        emp_id: str
    ):
        """
        Revert the dock-in process for a truck if:
        - is_dock_in == True
        - is_dock_out == False
        - is_truck_out == False
        """
        try:
            # 1️⃣ Find the export slot
            stmt = select(ExportSlotFileRecord).options(
              selectinload(ExportSlotFileRecord.awbs).selectinload(ExportSlotAWB.sequences)
            ).where(
                and_(
                    ExportSlotFileRecord.token_no == token_no,
                    ExportSlotFileRecord.truck_number == truck_number,
                    ExportSlotFileRecord.truck_slot_from == truck_slot_from
                )
            )
            result = await db.execute(stmt)
            export_slot = result.scalar_one_or_none()

            if not export_slot:
                raise HTTPException(
                    status_code=status.HTTP_404_NOT_FOUND,
                    detail="Export slot record not found."
                )

            # 2️⃣ Validate conditions
            if not export_slot.is_dock_in:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Truck is not docked in — cannot revert."
                )
            if export_slot.is_dock_out:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Truck already docked out — cannot revert dock-in."
                )
            if export_slot.is_truck_out:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="Truck already checked out — cannot revert dock-in."
                )

            # 3️⃣ Reset dock-in fields
            export_slot.is_dock_in = False
            export_slot.dock_in_date_time = None
            export_slot.dock_in_by = None
            export_slot.dock_number = None
           

            await db.commit()
            await db.refresh(export_slot)

            return export_slot

        except HTTPException:
            raise
        except Exception as e:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail=f"Error reverting dock-in: {str(e)}"
            )

    @staticmethod
    async def get_truck_slots_by_specific_date(
        db: AsyncSession,
        date: Optional[datetime] = None,
        limit: Optional[int] = None,
        offset: Optional[int] = None,
        dockOut: Optional[bool] = False,
    ):
        IST = pytz.timezone("Asia/Kolkata")  # or ZoneInfo("Asia/Kolkata")
        # If no date provided, use today in IST
        if date is None:
            now_ist = datetime.now(IST)
            start_ist = datetime(now_ist.year, now_ist.month, now_ist.day, tzinfo=IST)
        else:
            # Incoming date is naive → treat as IST
            if date.tzinfo is None:
                start_ist = IST.localize(datetime(date.year, date.month, date.day))
            else:
                # Normalize to IST midnight
                start_ist = date.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)

        # End of day in IST
        end_ist = start_ist + timedelta(days=1)

        # Convert both to UTC for DB filtering
        start_utc = start_ist.astimezone(timezone.utc)
        end_utc = end_ist.astimezone(timezone.utc)

        # Count query
        count_stmt = select(func.count()).select_from(ExportSlotFileRecord).where(
            and_(
                ExportSlotFileRecord.truck_slot_from >= start_utc,
                ExportSlotFileRecord.truck_slot_from < end_utc,
            )
        )
        total = (await db.execute(count_stmt)).scalar_one()

        conditions = [
        ExportSlotFileRecord.truck_slot_from >= start_utc,
        ExportSlotFileRecord.truck_slot_from < end_utc,
        ExportSlotFileRecord.is_truck_in == True
        ]
        if dockOut:
            conditions.append(ExportSlotFileRecord.is_dock_in == True)
    

        # Main query
        stmt = (
            select(ExportSlotFileRecord)
            .options(selectinload(ExportSlotFileRecord.awbs)
                    .selectinload(ExportSlotAWB.sequences))
            .where(
                and_(
                    *conditions
                )
            )
            .order_by(ExportSlotFileRecord.truck_slot_from.desc())
        )

        # Pagination defaults
        if limit is None:
            limit = total
        if offset is None:
            offset = 0

        stmt = stmt.limit(limit).offset(offset)

        result = await db.execute(stmt)
        records = result.scalars().unique().all()
        data = [ExportSlotFullResponse.model_validate(r) for r in records]
        pagination = Pagination(total=total, limit=limit, offset=offset)

        return data, pagination