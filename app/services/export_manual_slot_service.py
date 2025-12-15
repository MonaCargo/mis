# from app.db.models.export_slot_file import ExportSlotAWB
# from app.db.models.manual_slot import ExportManualSlotFileRecord
# from fastapi import UploadFile
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select, tuple_
# from sqlalchemy.orm import selectinload
# from io import BytesIO
# import pandas as pd
# from datetime import datetime, timezone

# from app.utils.exportOperation.manual_slot_cleaner import clean_manual_slot_file, FileStructureError


# # --- Utility functions ---
# def get_utc_now() -> datetime:
#     """Returns current UTC time with timezone info"""
#     return datetime.now(timezone.utc)

# def ensure_utc_aware(dt):
#     """Convert pandas Timestamp to tz-aware UTC datetime."""
#     if pd.isnull(dt):
#         return NoneŚ
#     if dt.tzinfo is None:
#         return dt.tz_localize("UTC")
#     return dt.tz_convert("UTC")

# def generate_token_number(db_count: int, prefix: str = "DCSC") -> str:
#     """Generate a unique token number like DCŚSC20251103001 based on DB count."""
#     today = datetime.utcnow().strftime("%Y%m%d")
#     base = f"{prefix}{today}"
#     serial = f"{db_count + 1:03d}"
#     return f"{base}{serial}"


# # -----------------------------------------------------------------------------------------------

# async def handle_manual_file_upload(file: UploadFile, db: AsyncSession) -> dict:
#     """
#     Upload Excel/CSV for manual slot file, validate, remove duplicates,
#     insert only new parents & AWBs into PostgreSQL with sequential token numbers.
#     """
#     try:
#         # Validate file extension
#         if not file.filename:
#             return {
#                 "status": "error",
#                 "message": "No file uploaded. Please select a file to upload."
#             }
        
#         file_ext = file.filename.lower()
#         if not (file_ext.endswith(".csv") or file_ext.endswith((".xlsx", ".xls"))):
#             return {
#                 "status": "error",
#                 "message": f"Invalid file type. Please upload a CSV or Excel file. Received: {file.filename}"
#             }
        
#         file_type = "csv" if file_ext.endswith(".csv") else "excel"
#         contents = await file.read()
        
#         # Check if file is empty
#         if not contents or len(contents) == 0:
#             return {
#                 "status": "error",
#                 "message": "The uploaded file is empty. Please upload a file with data."
#             }
        
#         buf = BytesIO(contents)

#         # Step 1: Clean and validate
#         try:
#             df = clean_manual_slot_file(buf, file_type)
#         except FileStructureError as e:
#             return {
#                 "status": "error",
#                 "message": f"File structure validation failed: {str(e)}"
#             }
#         except ValueError as e:
#             return {
#                 "status": "error",
#                 "message": f"Validation error: {str(e)}"
#             }
#         except Exception as e:
#             return {
#                 "status": "error",
#                 "message": f"Failed to process file: {str(e)}"
#             }

#         # Step 1b: Ensure tz-aware datetimes in UTC
#         for col in ["merge_datetime", "truck_in_date_time", "truck_out_date_time",
#                     "dock_in_date_time", "dock_out_date_time"]:
#             if col in df.columns:
#                 df[col] = df[col].apply(ensure_utc_aware)

#         # Step 2: Group by AWB + TC_NO + merge_datetime
#         grouped = df.groupby(["awb", "tc_no", "merge_datetime"], dropna=False)

#         stats = {
#             "total_parents_processed": len(grouped),
#             "existing_parents_found": 0,
#             "new_parents_created": 0,
#             "total_awbs_processed": 0,

#         }

#         total_awbs = 0
#         existing_parents = {}

#         try:
#             async with db.begin():
#                 # Pre-fetch existing parents
#                 parent_keys = [
#                     (row["awb"], row["tc_no"], row["merge_datetime"].to_pydatetime())
#                     for _, row in df.iterrows()
#                     if row["awb"] and row["tc_no"] and row["merge_datetime"] is not None
#                 ]
                
#                 if parent_keys:
#                     result = await db.execute(
#                         select(ExportManualSlotFileRecord)
#                         .where(
#                             tuple_(
#                                 ExportManualSlotFileRecord.awb,
#                                 ExportManualSlotFileRecord.tc_no,
#                                 ExportManualSlotFileRecord.merge_datetime
#                             ).in_(parent_keys)
#                         )
#                     )
#                     existing_parents = {
#                         (p.awb, p.tc_no, p.merge_datetime): p
#                         for p in result.scalars()
#                     }

#                 # Count existing tokens for today once
#                 today_prefix = f"DCSC{datetime.utcnow().strftime('%Y%m%d')}"
#                 count_result = await db.execute(
#                     select(ExportManualSlotFileRecord.token_number).where(
#                         ExportManualSlotFileRecord.token_number.like(f"{today_prefix}%")
#                     )
#                 )
#                 db_count = len(count_result.scalars().all())

#                 # Process each parent group
#                 for (awb, tc_no, merge_datetime), group in grouped:
#                     key = (awb, tc_no, merge_datetime.to_pydatetime())
#                     stats["total_awbs_processed"] += len(group)

#                     if key in existing_parents:
#                         parent = existing_parents[key]
#                         existing_awbs = {awb.awb_id for awb in getattr(parent, "awbs", [])}
#                         stats["existing_parents_found"] += 1
#                     else:
#                         first_row = group.iloc[0]

#                         # Increment count for each new parent
#                         token_number = generate_token_number(db_count)
#                         db_count += 1

#                         parent = ExportManualSlotFileRecord(
#                             date=first_row["date"],
#                             time=first_row["time"],
#                             merge_datetime=merge_datetime.to_pydatetime(),
#                             tc_no=tc_no,
#                             awb=awb,
#                             pcs=first_row["pcs"],
#                             agent_name=first_row["agent_name"],
#                             user=first_row["user"],
#                             truck_in_date_time=first_row.get("truck_in_date_time"),
#                             truck_out_date_time=first_row.get("truck_out_date_time"),
#                             dock_in_date_time=first_row.get("dock_in_date_time"),
#                             dock_out_date_time=first_row.get("dock_out_date_time"),
#                             dock_number=first_row.get("dock_number"),
#                             truck_in_by=first_row.get("truck_in_by"),
#                             truck_out_by=first_row.get("truck_out_by"),
#                             dock_in_by=first_row.get("dock_in_by"),
#                             dock_out_by=first_row.get("dock_out_by"),
#                             token_number=token_number,
#                             truck_number=""
#                         )
#                         db.add(parent)
#                         existing_parents[key] = parent
#                         stats["new_parents_created"] += 1
#                         existing_awbs = set()

#                     # Add AWBs
#                     for _, row in group.iterrows():
#                         awb_no, pcs = row.get("awb_id"), row.get("pcs")
#                         if awb_no and awb_no not in existing_awbs:
#                             parent.awbs.append(ExportSlotAWB(awb_id=awb_no, pcs=pcs))
#                             total_awbs += 1
#                             existing_awbs.add(awb_no)
#                             stats["new_awbs_added"] += 1
#                         elif awb_no:
#                             stats["duplicate_awbs_skipped"] += 1

#         except Exception as e:
#             return {
#                 "status": "error",
#                 "message": f"Database operation failed: {str(e)}"
#             }

#         return {
#             "status": "success",
#             "uploaded_parents": len(existing_parents),
#             "uploaded_awbs": total_awbs,
#             "stats": stats
#         }
        
#     except Exception as e:
#         # Catch any unexpected errors
#         return {
#             "status": "error",
#             "message": f"Unexpected error during file upload: {str(e)}"
#         }
















































from app.db.models.export_slot_file import ExportSlotAWB , ExportSlotFileRecord
from app.db.models.manual_slot import ExportManualSlotFileRecord
from fastapi import UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, tuple_,and_,func,insert
from sqlalchemy.orm import selectinload
from io import BytesIO
import pandas as pd
from datetime import datetime, timedelta, timezone
from typing import Optional, Tuple, List
import pytz
from app.utils.exportOperation.manual_slot_cleaner import clean_manual_slot_file, FileStructureError
from app.schemas.manulal_slot import (
    ExportManualSlotFileRecordResponse,
    Pagination,
)

from app.utils.common.helperFunction import get_utc_now


# --- Utility functions ---
def get_utc_now() -> datetime:
    """Returns current UTC time with timezone info"""
    return datetime.now(timezone.utc)

def ensure_utc_aware(dt):
    """Convert pandas Timestamp to tz-aware UTC datetime."""
    if pd.isnull(dt):
        return None
    if dt.tzinfo is None:
        return dt.tz_localize("UTC")
    return dt.tz_convert("UTC")

def generate_token_number(db_count: int, prefix: str = "M") -> str:
    """Generate a unique token number like DCSC20251103001 based on DB count."""
    ist = pytz.timezone('Asia/Kolkata')
    today = datetime.now(ist).strftime("%Y%m%d")
    base = f"{prefix}{today}"
    serial = f"{db_count + 1:04d}"
    return f"{base}{serial}"

# ---  Mian Handler-----------------------

async def handle_manual_file_upload(file: UploadFile, db: AsyncSession) -> dict:
    """
    Upload Excel/CSV for manual slot file, validate, remove duplicates,
    insert only new parents & AWBs into PostgreSQL with sequential token numbers.
    """
    try:
        # Validate file extension
        if not file.filename:
            return {
                "status": "error",
                "message": "No file uploaded. Please select a file to upload."
            }
        
        file_ext = file.filename.lower()
        if not (file_ext.endswith(".csv") or file_ext.endswith((".xlsx", ".xls"))):
            return {
                "status": "error",
                "message": f"Invalid file type. Please upload a CSV or Excel file. Received: {file.filename}"
            }
        
        file_type = "csv" if file_ext.endswith(".csv") else "excel"
        contents = await file.read()
        
        # Check if file is empty
        if not contents or len(contents) == 0:
            return {
                "status": "error",
                "message": "The uploaded file is empty. Please upload a file with data."
            }
        
        buf = BytesIO(contents)

        # Step 1: Clean and validate
        try:
            df = clean_manual_slot_file(buf, file_type)
        except FileStructureError as e:
            return {
                "status": "error",
                "message": f"File structure validation failed: {str(e)}"
            }
        except ValueError as e:
            return {
                "status": "error",
                "message": f"Validation error: {str(e)}"
            }
        except Exception as e:
            return {
                "status": "error",
                "message": f"Failed to process file: {str(e)}"
            }

        # Step 1b: Ensure tz-aware datetimes in UTC
        for col in ["merge_datetime", "truck_in_date_time", "truck_out_date_time",
                    "dock_in_date_time", "dock_out_date_time"]:
            if col in df.columns:
                df[col] = df[col].apply(ensure_utc_aware)

        # Step 2: Group by AWB + TC_NO + merge_datetime
        grouped = df.groupby(["awb", "tc_no", "merge_datetime"], dropna=False)

        stats = {
            "total_parents_processed": len(grouped),
            "existing_parents_found": 0,
            "new_parents_created": 0,
            "total_awbs_processed": 0,
            "new_awbs_added": 0,
            "duplicate_awbs_skipped": 0
        }

        total_awbs = 0
        existing_parents = {}

        try:
            # async with db.begin():
                # Pre-fetch existing parents
                parent_keys = [
                    (row["awb"], row["tc_no"], row["merge_datetime"].to_pydatetime())
                    for _, row in df.iterrows()
                    if row["awb"] and row["tc_no"] and row["merge_datetime"] is not None
                ]
                
                if parent_keys:
                    result = await db.execute(
                        select(ExportManualSlotFileRecord)
                        .where(
                            tuple_(
                                ExportManualSlotFileRecord.awb,
                                ExportManualSlotFileRecord.tc_no,
                                ExportManualSlotFileRecord.merge_datetime
                            ).in_(parent_keys)
                        )
                    )
                    existing_parents = {
                        (p.awb, p.tc_no, p.merge_datetime): p
                        for p in result.scalars()
                    }

                # Count existing tokens for today once
                today_prefix = f"M{datetime.utcnow().strftime('%Y%m%d')}"
                count_result = await db.execute(
                    select(ExportManualSlotFileRecord.token_number).where(
                        ExportManualSlotFileRecord.token_number.like(f"{today_prefix}%")
                    )
                )
                db_count = len(count_result.scalars().all())

                # Process each parent group
                for (awb, tc_no, merge_datetime), group in grouped:
                    key = (awb, tc_no, merge_datetime.to_pydatetime())
                    stats["total_awbs_processed"] += len(group)

                    if key in existing_parents:
                        parent = existing_parents[key]
                        existing_awbs = {awb.awb_id for awb in getattr(parent, "awbs", [])}
                        stats["existing_parents_found"] += 1
                    else:
                        first_row = group.iloc[0]

                        # Increment count for each new parent
                        token_number = generate_token_number(db_count)
                        db_count += 1
                        utc_now = datetime.now(timezone.utc) 
                        parent = ExportManualSlotFileRecord(
                            date=first_row["date"],
                            time=first_row["time"],
                            merge_datetime=merge_datetime.to_pydatetime(),
                            tc_no=tc_no,
                            awb=awb,
                            pcs=first_row["pcs"],
                            agent_name=first_row["agent_name"],
                            user=first_row["user"],
                            truck_in_date_time=first_row.get("truck_in_date_time"),
                            truck_out_date_time=first_row.get("truck_out_date_time"),
                            dock_in_date_time=first_row.get("dock_in_date_time"),
                            dock_out_date_time=first_row.get("dock_out_date_time"),
                            dock_number=first_row.get("dock_number"),
                            truck_in_by=first_row.get("truck_in_by"),
                            truck_out_by=first_row.get("truck_out_by"),
                            dock_in_by=first_row.get("dock_in_by"),
                            dock_out_by=first_row.get("dock_out_by"),
                            token_number=token_number,
                            truck_number=None,
                            created_at=utc_now,  # ✅ Explicit UTC
                            updated_at=utc_now   # ✅ Explicit UTC
                        )
                        db.add(parent)
                        existing_parents[key] = parent
                        stats["new_parents_created"] += 1
                        existing_awbs = set()

                    # Add AWBs
                    for _, row in group.iterrows():
                        awb_no, pcs = row.get("awb_id"), row.get("pcs")
                        if awb_no and awb_no not in existing_awbs:
                            parent.awbs.append(ExportSlotAWB(awb_id=awb_no, pcs=pcs))
                            total_awbs += 1
                            existing_awbs.add(awb_no)
                            stats["new_awbs_added"] += 1
                        elif awb_no:
                            stats["duplicate_awbs_skipped"] += 1

                    await db.commit()

        except Exception as e:
            return {
                "status": "error",
                "message": f"Database operation failed: {str(e)}"
            }

        return {
            "status": "success",
            "uploaded_parents": len(existing_parents),
            "uploaded_awbs": total_awbs,
            "stats": stats
        }
        
    except Exception as e:
        # Catch any unexpected errors
        return {
            "status": "error",
            "message": f"Unexpected error during file upload: {str(e)}"
        }
 

# --------------------------------------------

async def get_export_manual_slots_by_date(
    db: AsyncSession,
    date: Optional[datetime] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
    truck_out_only: bool = False,
) -> Tuple[List[ExportManualSlotFileRecordResponse], Pagination]:
    IST = pytz.timezone("Asia/Kolkata")

    # Normalize input date
    if date is None:
        now_ist = datetime.now(IST)
        start_ist = datetime(now_ist.year, now_ist.month, now_ist.day, tzinfo=IST)
    else:
        if date.tzinfo is None:
            start_ist = IST.localize(datetime(date.year, date.month, date.day))
        else:
            start_ist = date.astimezone(IST).replace(hour=0, minute=0, second=0, microsecond=0)

    end_ist = start_ist + timedelta(days=1)

    # Convert to UTC
    start_utc = start_ist.astimezone(timezone.utc)
    end_utc = end_ist.astimezone(timezone.utc)

    # Count query
    count_stmt = select(func.count()).select_from(ExportManualSlotFileRecord).where(
        and_(
            ExportManualSlotFileRecord.merge_datetime >= start_utc,
            ExportManualSlotFileRecord.merge_datetime < end_utc,
        )
    )
    total = (await db.execute(count_stmt)).scalar_one()

    # Main query
    conditions = [
        ExportManualSlotFileRecord.merge_datetime >= start_utc,
        ExportManualSlotFileRecord.merge_datetime < end_utc,
    ]
    if truck_out_only:
        conditions.append(ExportManualSlotFileRecord.is_truck_out.is_(True))

    stmt = (
        select(ExportManualSlotFileRecord)
        .where(and_(*conditions))
        .order_by(ExportManualSlotFileRecord.merge_datetime.desc())
    )

    # Pagination defaults
    if limit is None:
        limit = total
    if offset is None:
        offset = 0

    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    records = result.scalars().unique().all()

    data = [ExportManualSlotFileRecordResponse.model_validate(r,from_attributes=True) for r in records]
    pagination = Pagination(total=total, limit=limit, offset=offset)

    return data, pagination

async def mark_truck_in(
    db: AsyncSession,
    token_no: str,
    tc_no: str,
    emp_id: str,
    truck_number: str,
    truck_in_device:Optional[str] =None
) -> ExportManualSlotFileRecordResponse | None:

    try:
        # FETCH MANUAL SLOT RECORD
        result = await db.execute(
            select(ExportManualSlotFileRecord).where(
                ExportManualSlotFileRecord.token_number == token_no,
                ExportManualSlotFileRecord.tc_no == tc_no,
            )
        )
        record = result.scalar_one_or_none()

        if not record:
            return None

        if record.is_truck_in:
            raise RuntimeError("Truck already marked as IN for this record")

        # ====== CHECK IF ALREADY EXISTS IN export_slot_file ======
        existing_export_slot = await db.execute(
            select(ExportSlotFileRecord).where(
                ExportSlotFileRecord.token_no == record.token_number,
                ExportSlotFileRecord.truck_number == truck_number,
                ExportSlotFileRecord.truck_slot_from == record.merge_datetime,
            )
        )
        existing_record = existing_export_slot.scalar_one_or_none()

        if existing_record:
            raise RuntimeError(
                f"Record already exists in export_slot_file with "
                f"token_no={record.token_number}, truck_number={truck_number}, "
                f"and slot_time={record.merge_datetime}"
            )

        # ====== UPDATE MANUAL TABLE (truck in) ======
        utc_now = get_utc_now()
        record.truck_in_date_time = utc_now
        record.truck_in_by = emp_id
        record.is_truck_in = True
        record.truck_number = truck_number
        record.updated_at = utc_now
        record.truck_in_device = truck_in_device

        # ====== INSERT INTO export_slot_file TABLE ======
        stmt = insert(ExportSlotFileRecord).values(
            company_name=record.agent_name,
            warehouse="EXP-I",
            zone="ZONE-I",
            token_no=record.token_number,
            truck_number=truck_number,
            status="BOOKED",
            remarks="Manual Slot - Truck In",
            cargo_type='M_NORMAL',
            rescheduled=None,
            rescheduled_by=None,
            truck_slot_from=record.merge_datetime,
            truck_in_date_time=record.truck_in_date_time,
            is_truck_in=True,
            is_truck_out=False,
            # is_dock_in=False,
            # is_dock_out=False,
            # dock_in_date_time=None,
            # dock_out_date_time=None,
            # dock_in_by=None,
            # dock_out_by=None,
            # dock_number=None,
            current_dock_in_date_time=None,
            current_dock_out_date_time=None,
            current_is_dock_in=False,
            current_is_dock_out=False,
                 current_dock_number=None,
            current_dock_in_by=None,
            current_dock_out_by=None,
            truck_in_device = truck_in_device,

            truck_out_by=None,
            truck_in_by=emp_id,
        ).returning(ExportSlotFileRecord.id)

        export_result = await db.execute(stmt)
        new_export_id = export_result.scalar_one()

        # ====== INSERT SINGLE AWB ======
        awb_stmt = insert(ExportSlotAWB).values(
            export_slot_id=new_export_id,
            awb_id=record.awb,  # single AWB string
            pcs=record.pcs,
            is_additional=False,
            created_at=get_utc_now(),
            updated_at=get_utc_now(),
        ).returning(ExportSlotAWB.id)

        awb_result = await db.execute(awb_stmt)
        new_awb_id = awb_result.scalar_one()

        # COMMIT BOTH
        await db.commit()

        await db.refresh(record)

        return ExportManualSlotFileRecordResponse.model_validate(
            record,
            from_attributes=True
        )

    except Exception as e:
        await db.rollback()
        raise RuntimeError(f"Failed to mark truck in: {str(e)}")