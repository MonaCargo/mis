# app/services/dock_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.sql import func,desc
from fastapi import HTTPException
from app.db.models.dock_availability import DockAvailability
from app.db.models.export_slot_file import ExportSlotFileRecord,ExportSlotAWB,AWBSequence
from app.db.models.user import User


async def get_all_docks(db: AsyncSession):
    try:
        # 🔥 AUTO-SYNC: Free docks without active trucks
        occupied_docks = (await db.execute(
            select(DockAvailability).where(DockAvailability.is_dock_occupied == True)
        )).scalars().all()

        for dock in occupied_docks:
            # Check if there's actually an active truck
            active_truck = (await db.execute(
                select(ExportSlotFileRecord).where(
                    ExportSlotFileRecord.current_dock_number == dock.dock_no,
                    ExportSlotFileRecord.current_is_dock_in == True,
                    ExportSlotFileRecord.current_is_dock_out == False,
                    ExportSlotFileRecord.is_truck_out == False
                )
            )).scalar_one_or_none()

            # No active truck? Free it!
            if not active_truck:
                dock.is_dock_occupied = False
                dock.dock_in_time = None
                dock.updated_at = func.now()

        await db.commit()

        # Now return all docks

        result = await db.execute(
            select(DockAvailability).order_by(DockAvailability.dock_no)
        )
        return result.scalars().all()
    except Exception as e:
        # Rollback in case of DB error
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error fetching docks: {str(e)}")


async def occupy_dock(db: AsyncSession, dock_no: str):
    try:
        result = await db.execute(
            select(DockAvailability).where(DockAvailability.dock_no == dock_no)
        )
        dock = result.scalar_one_or_none()

        if not dock:
            raise HTTPException(status_code=404, detail="Dock not found")
        if dock.is_dock_occupied:
            raise HTTPException(status_code=400, detail="Dock already occupied")

        dock.is_dock_occupied = True
        dock.dock_in_time = func.now()

        await db.commit()
        await db.refresh(dock)
        return dock

    except HTTPException:
        # Re-raise known business errors
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error occupying dock: {str(e)}")


async def release_dock(db: AsyncSession, dock_no: str):
    try:
        result = await db.execute(
            select(DockAvailability).where(DockAvailability.dock_no == dock_no)
        )
        dock = result.scalar_one_or_none()

        if not dock:
            raise HTTPException(status_code=404, detail="Dock not found")

        dock.is_dock_occupied = False
        dock.dock_in_time = None

        await db.commit()
        await db.refresh(dock)
        return dock

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error releasing dock: {str(e)}")
    
    
async def create_dock(db: AsyncSession, dock_no: str):
    try:
        # Check if dock already exists
        result = await db.execute(
            select(DockAvailability).where(DockAvailability.dock_no == dock_no)
        )
        existing_dock = result.scalar_one_or_none()
        if existing_dock:
            raise HTTPException(status_code=400, detail=f"Dock {dock_no} already exists")

        # Create new dock
        new_dock = DockAvailability(
            dock_no=dock_no,
            is_dock_occupied=False,
            dock_in_time=None
        )
        db.add(new_dock)
        await db.commit()
        await db.refresh(new_dock)
        return new_dock

    except HTTPException:
        raise
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=f"Error creating dock: {str(e)}")
    


# async def get_dock_details(db: AsyncSession, dock_no: str):
#     try:
#         # Step 1: find latest truck record for this dock with employee info
#         latest_stmt = (
#             select(
#                 ExportSlotFileRecord.id,
#                 ExportSlotFileRecord.dock_number,
#                 ExportSlotFileRecord.dock_in_date_time,
#                 ExportSlotFileRecord.dock_out_date_time,
#                 ExportSlotFileRecord.is_dock_in,
#                 ExportSlotFileRecord.truck_number,
#                 ExportSlotFileRecord.token_no,
#                 ExportSlotFileRecord.truck_slot_from,
#                 User.emp_id,
#                 User.name,
#                 User.role,
#             )
#             .join(User, ExportSlotFileRecord.dock_in_by == User.emp_id, isouter=True)
#             .where(
#                 ExportSlotFileRecord.dock_number == dock_no,
#                 ExportSlotFileRecord.is_dock_in == True
#             )
#             .order_by(desc(ExportSlotFileRecord.dock_in_date_time))
#             .limit(1)
#         )
#         latest_result = await db.execute(latest_stmt)
#         latest_record = latest_result.first()
#         if not latest_record:
#             raise HTTPException(status_code=404, detail="Dock not found or no active truck")

#         # Step 2: get AWBs for this truck record
#         awb_stmt = (
#             select(
#                 ExportSlotAWB.awb_id.label("awb_id"),
#                 # func.coalesce(func.sum(ExportSlotAWB.pcs), 0).label("total_pcs"),
#                 ExportSlotAWB.pcs.label("total_pcs"),   # take pcs directly, not SUM
#                 func.coalesce(func.count(AWBSequence.id), 0).label("scanned_pcs"),
#             )
#             .join(AWBSequence, AWBSequence.awb_record_id == ExportSlotAWB.id, isouter=True)
#             .where(ExportSlotAWB.export_slot_id == latest_record.id)
#             .group_by(ExportSlotAWB.awb_id, ExportSlotAWB.pcs)
#         )
#         awb_result = await db.execute(awb_stmt)
#         awb_rows = awb_result.all()

#         awb_list = [
#             {
#                 "awb_id": row.awb_id,
#                 "total_pcs": row.total_pcs,
#                 "scanned_pcs": row.scanned_pcs,
#             }
#             for row in awb_rows
#         ]

#         # Step 3: build response
#         return {
#             "dock_no": latest_record.dock_number,
#             "dock_in_time": latest_record.dock_in_date_time,
#             "dock_out_time": latest_record.dock_out_date_time,
#             "is_dock_occupied": latest_record.is_dock_in,
#             "truck_number": latest_record.truck_number,
#             "token_no": latest_record.token_no,
#             "truck_slot_from": latest_record.truck_slot_from,
#             "employee_info": {
#                 "emp_id": latest_record.emp_id,
#                 "name": latest_record.name,
#                 "role": latest_record.role,
#             },
#             "awb_list": awb_list,
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         await db.rollback()
#         raise HTTPException(status_code=500, detail=f"Error fetching dock details: {str(e)}")





async def get_dock_details(db: AsyncSession, dock_no: str):
    try:
        # Step 1: find latest truck record for this dock with employee info
        latest_stmt = (
            select(
                ExportSlotFileRecord.id,
                ExportSlotFileRecord.current_dock_number.label("dock_number"),
                ExportSlotFileRecord.current_dock_in_date_time.label("dock_in_time"),
                ExportSlotFileRecord.current_dock_out_date_time.label("dock_out_time"),
                ExportSlotFileRecord.current_is_dock_in.label("is_dock_occupied"),
                ExportSlotFileRecord.truck_number,
                ExportSlotFileRecord.token_no,
                ExportSlotFileRecord.truck_slot_from,
                User.emp_id,
                User.name,
                User.role,
            )
            .join(User, ExportSlotFileRecord.current_dock_in_by == User.emp_id, isouter=True)
            .where(
                ExportSlotFileRecord.current_dock_number == dock_no,
                ExportSlotFileRecord.current_is_dock_in.is_(True),
                ExportSlotFileRecord.current_is_dock_out.is_(False),  # 🔥 ADD THIS
                ExportSlotFileRecord.is_truck_out.is_(False)  # 🔥 ADD THIS
            )
            .order_by(desc(ExportSlotFileRecord.current_dock_in_date_time))
            .limit(1)
        )
        latest_result = await db.execute(latest_stmt)
        latest_record = latest_result.first()
        if not latest_record:
            raise HTTPException(status_code=404, detail="Dock not found or no active truck")
        # Step 2: get AWBs for this truck record
        awb_stmt = (
            select(
                ExportSlotAWB.awb_id.label("awb_id"),
                ExportSlotAWB.pcs.label("total_pcs"),
                func.coalesce(func.count(AWBSequence.id), 0).label("scanned_pcs"),
            )
            .join(AWBSequence, AWBSequence.awb_record_id == ExportSlotAWB.id, isouter=True)
            .where(ExportSlotAWB.export_slot_id == latest_record.id)
            .group_by(ExportSlotAWB.awb_id, ExportSlotAWB.pcs)
        )
        awb_result = await db.execute(awb_stmt)
        awb_rows = awb_result.all()
        awb_list = [
            {
                "awb_id": row.awb_id,
                "total_pcs": row.total_pcs,
                "scanned_pcs": row.scanned_pcs,
            }
            for row in awb_rows
        ]
        # Step 3: build response
        return {
            "dock_no": latest_record.dock_number,
            "dock_in_time": latest_record.dock_in_time,
            "dock_out_time": latest_record.dock_out_time,
            "is_dock_occupied": latest_record.is_dock_occupied,
            "truck_number": latest_record.truck_number,
            "token_no": latest_record.token_no,
            "truck_slot_from": latest_record.truck_slot_from,
            "employee_info": {
                "emp_id": latest_record.emp_id,
                "name": latest_record.name,
                "role": latest_record.role,
            },
            "awb_list": awb_list,
        }
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching dock details: {str(e)}")