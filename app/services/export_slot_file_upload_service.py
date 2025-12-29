# from typing import List
# from fastapi import UploadFile
# from io import BytesIO
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import insert

# from app.db.models.export_slot_file import ExportSlotFileRecord
# from app.schemas.export_slot_file import ExportSlotFileRecord as ExportSlotFileRecordSchema
# from app.utils.cleaner import clean_file

# from pydantic import ValidationError

# async def insert_records_bulk(db: AsyncSession, records: List[ExportSlotFileRecordSchema]):
#     data = [r.model_dump() for r in records]
#     await db.execute(insert(ExportSlotFileRecord), data)
#     await db.commit()



# async def handle_file_upload(file: UploadFile, db: AsyncSession) -> dict:
#     file_type = "csv" if file.filename.lower().endswith(".csv") else "excel"
#     contents = await file.read()
#     buf = BytesIO(contents)

#     try:
#         df = clean_file(buf, file_type)
#     except ValueError as e:
#         return {"status": "error", "message": str(e)}

#     records = []
#     for row in df.to_dict(orient="records"):
#         try:
#             record = ExportSlotFileRecordSchema.model_validate(row)
#             records.append(record)
#         except ValidationError as e:
#             return {
#                 "status": "error",
#                 "message": f"Validation error in row {row}: {e.errors()}"
#             }

#     # No clearing, just insert
#     await insert_records_bulk(db, records)

#     return {"status": "success", "uploaded": len(records)}






# ================= NEW STRUCTURE ======================================================




# from typing import List
# from fastapi import UploadFile
# from io import BytesIO
# import pandas as pd
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.orm import selectinload

# from app.db.models.export_slot_file import ExportSlotFileRecord, ExportSlotAWB
# from app.schemas.export_slot_file import ExportSlotFileRecordSchema, AWBEntry
# from app.utils.cleaner import clean_file
# from pydantic import ValidationError


# async def handle_file_upload(file: UploadFile, db: AsyncSession) -> dict:
#     """
#     Handles file upload (CSV/Excel), cleans and groups data, then saves
#     to export_slot_file + export_slot_awb in DB.
#     """
#     file_type = "csv" if file.filename.lower().endswith(".csv") else "excel"
#     contents = await file.read()
#     buf = BytesIO(contents)

#     # Step 1: Clean the file
#     try:
#         df = clean_file(buf, file_type)
#     except ValueError as e:
#         return {"status": "error", "message": str(e)}

#     # Step 2: Group rows into parent-child structures
#     grouped = df.groupby(["truck_number", "token_no", "truck_slot_from"], dropna=False)

#     parent_records: List[ExportSlotFileRecord] = []
#     total_awbs = 0

#     for (truck_number, token_no, truck_slot_from), group in grouped:
#         first_row = group.iloc[0]

#         # Step 3: Build parent schema object
#         parent_schema = ExportSlotFileRecordSchema(
#             company_name=first_row["company_name"],
#             warehouse=first_row["warehouse"],
#             zone=first_row["zone"],
#             token_no=token_no,
#             truck_number=truck_number,
#             status=first_row.get("status"),
#             remarks=first_row.get("remarks"),
#             cargo_type=first_row.get("cargo_type"),
#             rescheduled=first_row.get("rescheduled"),
#             rescheduled_by=first_row.get("rescheduled_by"),
#             truck_slot_from=truck_slot_from,
#             truck_in_date_time=first_row.get("truck_in_date_time"),
#             awbList=[
#                 AWBEntry(awbid=str(row["awbid"]), pcs=int(row["pcs"]))
#                 for _, row in group.iterrows() if row["awbid"]
#             ]
#         )

#         # Step 4: Create ORM objects
#         parent = ExportSlotFileRecord(
#             company_name=parent_schema.company_name,
#             warehouse=parent_schema.warehouse,
#             zone=parent_schema.zone,
#             token_no=parent_schema.token_no,
#             truck_number=parent_schema.truck_number,
#             status=parent_schema.status,
#             remarks=parent_schema.remarks,
#             cargo_type=parent_schema.cargo_type,
#             rescheduled=parent_schema.rescheduled,
#             rescheduled_by=parent_schema.rescheduled_by,
#             truck_slot_from=parent_schema.truck_slot_from,
#             truck_in_date_time=parent_schema.truck_in_date_time,
#         )

#         # Step 5: Attach AWBs
#         for awb in parent_schema.awbList:
#             awb_obj = ExportSlotAWB(awbid=awb.awbid, pcs=awb.pcs)
#             parent.awbs.append(awb_obj)
#             total_awbs += 1

#         parent_records.append(parent)

#     # Step 6: Bulk insert ORM objects
#     db.add_all(parent_records)
#     await db.commit()

#     return {
#         "status": "success",
#         "uploaded_parents": len(parent_records),
#         "uploaded_awbs": total_awbs
#     }



# =================== FINAL VERSION AFTER NEW STRUCTURE DISCUSSION ======================================================


# from typing import List
# from fastapi import UploadFile
# from io import BytesIO
# from sqlalchemy import select, tuple_
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.db.models.export_slot_file import ExportSlotFileRecord, ExportSlotAWB
# from app.schemas.export_slot_file import AWBEntry
# from app.utils.cleaner import clean_file


# async def handle_file_upload(file: UploadFile, db: AsyncSession) -> dict:
#     """
#     Upload Excel/CSV, validate, remove duplicates, insert only new parents & AWBs.
#     """
#     file_type = "csv" if file.filename.lower().endswith(".csv") else "excel"
#     contents = await file.read()
#     buf = BytesIO(contents)

#     # Step 1: Clean and validate
#     try:
#         df = clean_file(buf, file_type)
#     except ValueError as e:
#         return {"status": "error", "message": str(e)}

#     # Step 2: Group by parent key
#     grouped = df.groupby(["truck_number", "token_no", "truck_slot_from"], dropna=False)

#     total_awbs = 0
#     existing_parents = {}

#     async with db.begin():  # atomic transaction
#         # Pre-fetch existing parents
#         parent_keys = [(row["token_no"], row["truck_number"], row["truck_slot_from"]) for _, row in df.iterrows()]
#         if parent_keys:
#             result = await db.execute(
#                 select(ExportSlotFileRecord).where(
#                     tuple_(
#                         ExportSlotFileRecord.token_no,
#                         ExportSlotFileRecord.truck_number,
#                         ExportSlotFileRecord.truck_slot_from
#                     ).in_(parent_keys)
#                 )
#             )
#             existing_parents = {(p.token_no, p.truck_number, p.truck_slot_from): p for p in result.scalars()}

#         # Process each parent group
#         for (truck_number, token_no, truck_slot_from), group in grouped:
#             key = (token_no, truck_number, truck_slot_from)

#             if key in existing_parents:
#                 parent = existing_parents[key]
#                 existing_awbs = {awb.awbid for awb in parent.awbs}
#             else:
#                 first_row = group.iloc[0]
#                 parent = ExportSlotFileRecord(
#                     company_name=first_row["company_name"],
#                     warehouse=first_row["warehouse"],
#                     zone=first_row["zone"],
#                     token_no=token_no,
#                     truck_number=truck_number,
#                     status=first_row.get("status"),
#                     remarks=first_row.get("remarks"),
#                     cargo_type=first_row.get("cargo_type"),
#                     rescheduled=first_row.get("rescheduled"),
#                     rescheduled_by=first_row.get("rescheduled_by"),
#                     truck_slot_from=truck_slot_from,
#                     truck_in_date_time=first_row.get("truck_in_date_time"),
#                 )
#                 db.add(parent)
#                 existing_parents[key] = parent
#                 existing_awbs = set()

#             # Add only new AWBs
#             for _, row in group.iterrows():
#                 awb_no = row.get("awbid")
#                 pcs = row.get("pcs")
#                 if awb_no and awb_no not in existing_awbs:
#                     awb_obj = ExportSlotAWB(awbid=awb_no, pcs=pcs)
#                     parent.awbs.append(awb_obj)
#                     total_awbs += 1
#                     existing_awbs.add(awb_no)

#     return {
#         "status": "success",
#         "uploaded_parents": len(existing_parents),
#         "uploaded_awbs": total_awbs
#     }









# ========================== working finale ----------------------

import csv
from datetime import datetime, timedelta, timezone, date, time

import io
from typing import AsyncGenerator, List, Optional, Tuple
import pytz
from sqlalchemy.orm import selectinload
from fastapi import HTTPException, UploadFile
from io import BytesIO
from sqlalchemy import and_, func, or_, select, tuple_
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from app.db.models.export_slot_file import AWBDockOperation, AWBSequence, ExportSlotFileRecord, ExportSlotAWB
from app.schemas.base import Pagination
from app.schemas.export_slot_file import AWBEntry, ExportSlotDownloadResponse, ExportSlotFullResponse
from app.utils.cleaner import clean_file

# utility function to get current datetime in utc.
def get_utc_now() -> datetime:
    """Returns current UTC time with timezone info"""
    return datetime.now(timezone.utc)

def ensure_utc_aware(dt):
    """
    Convert pandas Timestamp to tz-aware UTC datetime.
    """
    if pd.isnull(dt):
        return None
    if dt.tzinfo is None:
        return dt.tz_localize('UTC')
    else:
        return dt.tz_convert('UTC')


async def handle_file_upload(file: UploadFile, db: AsyncSession) -> dict:
    """
    Upload Excel/CSV, validate, remove duplicates, insert only new parents & AWBs.
    """
    file_type = "csv" if file.filename.lower().endswith(".csv") else "excel"
    contents = await file.read()
    buf = BytesIO(contents)

    # Step 1: Clean and validate
    try:
        df = clean_file(buf, file_type)
    except ValueError as e:
        return {"status": "error", "message": str(e)}

    # Step 1b: Ensure tz-aware datetimes in UTC
    for col in ["truck_slot_from", "truck_in_date_time"]:
        if col in df.columns:
            df[col] = df[col].apply(ensure_utc_aware)

    # Step 2: Group by parent key
    grouped = df.groupby(["truck_number", "token_no", "truck_slot_from"], dropna=False)

    total_awbs = 0
    existing_parents = {}

    # Add statistics tracking
    stats = {
        "total_parents_processed": len(grouped),
        "existing_parents_found": 0,
        "new_parents_created": 0,
        "total_awbs_processed": 0,
        "new_awbs_added": 0,
        "duplicate_awbs_skipped": 0
    }

    async with db.begin():  # atomic transaction
        # Pre-fetch existing parents (you can improve by using list that have unique values only😎)
        parent_keys = [
            (row["token_no"], row["truck_number"], row["truck_slot_from"].to_pydatetime()) #.to_pydatetime() may fail formissing/null values (NaT)⚠️,
            for _, row in df.iterrows()
            if row["truck_slot_from"] is not None  # ✅ Handle NaT values
        ]
        if parent_keys:
            result = await db.execute(
                select(ExportSlotFileRecord)
                .options(selectinload(ExportSlotFileRecord.awbs))  # ✅ ADD THIS LINE
                .where(
                    tuple_(
                        ExportSlotFileRecord.token_no,
                        ExportSlotFileRecord.truck_number,
                        ExportSlotFileRecord.truck_slot_from
                    ).in_(parent_keys)
                )
            )
            existing_parents = {
                (p.token_no, p.truck_number, p.truck_slot_from): p
                for p in result.scalars()
            }

        # Process each parent group
        for (truck_number, token_no, truck_slot_from), group in grouped:
            key = (token_no, truck_number, truck_slot_from.to_pydatetime())
            stats["total_awbs_processed"] += len(group)

            if key in existing_parents:
                parent = existing_parents[key]
                existing_awbs = {awb.awb_id for awb in parent.awbs}
                stats["existing_parents_found"] += 1
            else:
                first_row = group.iloc[0]
                parent = ExportSlotFileRecord(
                    company_name=first_row["company_name"],
                    warehouse=first_row["warehouse"],
                    zone=first_row["zone"],
                    token_no=token_no,
                    truck_number=truck_number,
                    status=first_row.get("status"),
                    remarks=first_row.get("remarks"),
                    cargo_type=first_row.get("cargo_type"),
                    rescheduled=first_row.get("rescheduled"),
                    rescheduled_by=first_row.get("rescheduled_by"),
                    truck_slot_from=truck_slot_from.to_pydatetime(),
                    truck_in_date_time=first_row.get("truck_in_date_time"),
                )
                db.add(parent)
                existing_parents[key] = parent
                stats["new_parents_created"] += 1
                existing_awbs = set()

            # # Add only new AWBs
            # for _, row in group.iterrows():
            #     awb_no = row.get("awbid")
            #     pcs = row.get("pcs")
            #     if awb_no and awb_no not in existing_awbs:
            #         awb_obj = ExportSlotAWB(awbid=awb_no, pcs=pcs)
            #         parent.awbs.append(awb_obj)
            #         total_awbs += 1
            #         existing_awbs.add(awb_no)

             # Add only new AWBs
            for _, row in group.iterrows():
                awb_no = row.get("awb_id")
                pcs = row.get("pcs")
                if awb_no and awb_no not in existing_awbs:
                    awb_obj = ExportSlotAWB(awb_id=awb_no, pcs=pcs, created_at=get_utc_now(), updated_at=get_utc_now())
                    parent.awbs.append(awb_obj),
                    total_awbs += 1
                    existing_awbs.add(awb_no)
                    stats["new_awbs_added"] += 1  # ✅ COUNT NEW AWBs
                elif awb_no:
                    stats["duplicate_awbs_skipped"] += 1  # ✅ COUNT DUPLICATE AWBs



    return {
        "status": "success",
        "uploaded_parents": len(existing_parents),
        "uploaded_awbs": total_awbs,
        "stats": stats  # ✅ RETURN DETAILED STATS
    }







async def get_export_slots_search(
    db: AsyncSession,
    truck_number: Optional[str] = None,
    token_no: Optional[str] = None,
    limit: Optional[int] = None,   # Make optional
    offset: Optional[int] = None,  # Make optional
):
    conditions = []

    if truck_number and truck_number.strip():
        conditions.append(ExportSlotFileRecord.truck_number == truck_number.strip())
    elif token_no and token_no.strip():
        conditions.append(ExportSlotFileRecord.token_no == token_no.strip())

    if not conditions:
        raise ValueError("No valid search filter provided")

    count_stmt = select(func.count()).select_from(ExportSlotFileRecord).where(and_(*conditions))
    total = (await db.execute(count_stmt)).scalar_one()

    stmt = (
        select(ExportSlotFileRecord)
        .options(
         selectinload(ExportSlotFileRecord.awbs).selectinload(ExportSlotAWB.sequences)
        )
        .where(and_(*conditions))
        .order_by(ExportSlotFileRecord.truck_slot_from.desc())
       
    )
    
    # if value provodes of limit and offset then apply pagination otherwise fetch all records
    if limit is None:
       limit = total  # return all records
    if offset is None:
       offset = 0

    stmt = stmt.limit(limit).offset(offset)

    result = await db.execute(stmt)
    records = result.scalars().unique().all()
    data = [ExportSlotFullResponse.model_validate(r) for r in records]
    pagination = Pagination(total=total, limit=limit, offset=offset)
    
    return data, pagination








async def get_export_slots_by_specific_date(
    db: AsyncSession,
    date: Optional[datetime] = None,
    limit: Optional[int] = None,
    offset: Optional[int] = None,
     truckOut: Optional[bool] = False,
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


         # Main query
    conditions = [
        ExportSlotFileRecord.truck_slot_from >= start_utc,
        ExportSlotFileRecord.truck_slot_from < end_utc,
        ]
    if truckOut:
        # 👌👌👌👌👌👌👌👌👌👌👌👌👌👌👌👌 1 chnages
        # conditions.append(ExportSlotFileRecord.is_dock_out == True)
        conditions.append(ExportSlotFileRecord.is_truck_in == True)

    # stmt = (
    #     select(ExportSlotFileRecord)
    #     .options(selectinload(ExportSlotFileRecord.awbs)
    #              .selectinload(ExportSlotAWB.sequences))
    #     .where(
    #         and_(
    #             *conditions
    #         )
    #     )
    #     .order_by(ExportSlotFileRecord.truck_slot_from.desc())
    # )

    stmt = (
    select(ExportSlotFileRecord)
    .options(
        selectinload(ExportSlotFileRecord.awbs)
            .selectinload(ExportSlotAWB.sequences),
        selectinload(ExportSlotFileRecord.awbs)
            .selectinload(ExportSlotAWB.dock_operations)
            .selectinload(AWBDockOperation.sequences),
    )
    .where(and_(*conditions))
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


# async def get_export_slots_list(
#     db: AsyncSession,
#     truck_number: Optional[str] = None,
#     token_no: Optional[str] = None,
#     date: Optional[datetime] = None,
#     limit: int = 20,
#     offset: int = 0,
# ) -> Tuple[List[ExportSlotFullResponse], Pagination]:
#     """
#     Fetch export slot records filtered automatically:
#     - Always filter by date (default today)
#     - If truck_number → filter by it
#     - Else if token_no → filter by it
#     - Else → all records for that date
#     - Supports pagination via limit & offset
#     - If both truck_number & token_no provided, truck_number takes precedence
#     """

#     # 1️⃣ Default to today (UTC)
#     if date is None:
#         now = datetime.utcnow()
#         start_of_day = datetime(now.year, now.month, now.day)
#     else:
#         start_of_day = datetime(date.year, date.month, date.day)

#     end_of_day = start_of_day + timedelta(days=1)

#     # 2️⃣ Base date filter
#     conditions = [
#         ExportSlotFileRecord.truck_slot_from >= start_of_day,
#         ExportSlotFileRecord.truck_slot_from < end_of_day,
#     ]

#     # 3️⃣ Optional filters
#     if truck_number and truck_number.strip():
#         conditions.append(ExportSlotFileRecord.truck_number == truck_number.strip())
#     elif token_no and token_no.strip():
#         conditions.append(ExportSlotFileRecord.token_no == token_no.strip())

#     # 4️⃣ Count total
#     count_stmt = select(func.count()).select_from(ExportSlotFileRecord).where(and_(*conditions))
#     total = (await db.execute(count_stmt)).scalar_one()

#     # 5️⃣ Fetch records with pagination
#     stmt = (
#         select(ExportSlotFileRecord)
#         .options(selectinload(ExportSlotFileRecord.awbs)) # <-- eager load
#         .where(and_(*conditions))
#         .order_by(ExportSlotFileRecord.truck_slot_from.desc())
#         .limit(limit)
#         .offset(offset)
#     )
#     result = await db.execute(stmt)
#     records = result.scalars().unique().all()

#     data = [ExportSlotFullResponse.model_validate(r) for r in records]
#     pagination = Pagination(total=total, limit=limit, offset=offset)

#     return data, pagination








async def get_export_slots_by_date_range(
    db: AsyncSession,
    start_date: datetime,
    end_date: datetime,
    limit: int = 20,
    offset: int = 0,
) -> Tuple[List[ExportSlotFullResponse], Pagination]:
    """
    Fetch export slot records purely based on a date range (inclusive).
    Pagination is applied.
    """

    # Normalize dates to cover full days (MAKE IT TIMEZONE AWAEW AMD UTC)
    start_of_day = datetime(
        start_date.year, start_date.month, start_date.day, 
        tzinfo=timezone.utc
    )
    end_of_day = datetime(
        end_date.year, end_date.month, end_date.day, 
        tzinfo=timezone.utc
    ) + timedelta(days=1)

    # Date filter condition
    conditions = [
        ExportSlotFileRecord.truck_slot_from >= start_of_day,
        ExportSlotFileRecord.truck_slot_from < end_of_day,
        ExportSlotFileRecord.is_truck_in == True
    ]

    # Count total records
    count_stmt = select(func.count()).select_from(ExportSlotFileRecord).where(and_(*conditions))
    total = (await db.execute(count_stmt)).scalar_one()

    # Fetch records with pagination
    stmt = (
        select(ExportSlotFileRecord)
        .options(selectinload(ExportSlotFileRecord.awbs))
        .where(and_(*conditions))
        .order_by(ExportSlotFileRecord.created_at.desc())
        .limit(limit)
        .offset(offset)
    )
    result = await db.execute(stmt)
    records = result.scalars().unique().all()

    data = [ExportSlotFullResponse.model_validate(r) for r in records]
    pagination = Pagination(total=total, limit=limit, offset=offset)

    return data, pagination



# ====================Streaming download service csv data maker(truck_in_out_download)============================================


#   ---- THESE HELPER FUNCTION CONVERT OUR UTC DATETIME TO IST AND FORMATTING THEM ----
def to_ist(dt):
    if not dt:
        return None
    if dt.tzinfo is None:
        # assume input is UTC naive
        dt = dt.replace(tzinfo=pytz.UTC)
    return dt.astimezone(pytz.timezone("Asia/Kolkata"))


def fmt_date(dt):
    dt = to_ist(dt)
    if not dt:
        return ""
    return dt.strftime("%d-%b-%Y")       # 14-NOV-2025


def fmt_datetime(dt):
    dt = to_ist(dt)
    if not dt:
        return ""
    return dt.strftime("%d-%b-%Y %H:%M") # 14-NOV-2025 13:56


async def generate_csv_rows_for_download_truck_in_out_by_stream(
    db: AsyncSession,
    start_date: datetime,
    end_date: datetime
) -> AsyncGenerator[str, None]:
    """
    Optimized generator for large CSV exports.
    Memory-efficient with batched yielding.
    """
    
    output = io.StringIO()
    writer = csv.writer(output)
    
    # Write header row
    header = [
        "Truck Number", "AWB Number", "PCS",
        "Truck In Date Time", "Truck Out Date Time",
        "Truck Slot From", "Truck Slot To", "Status", "Company Name",
        "Warehouse", "Zone", "Token No", "Cargo Type",
        "Dock Number", "Truck In By", "Truck Out By",
        "Dock In Date Time", "Dock Out Date Time",
        "Dock In By", "Dock Out By", "Is Additional"
    ]
    writer.writerow(header)
    yield output.getvalue()
    output.truncate(0)
    output.seek(0)
    
    # ⚡ Optimized query with eager loading
    from sqlalchemy.orm import selectinload
    
    query = (
        select(ExportSlotFileRecord)
        .options(selectinload(ExportSlotFileRecord.awbs))  # ⚡ Load AWBs in same query
        .where(
            ExportSlotFileRecord.truck_slot_from >= start_date,
            ExportSlotFileRecord.truck_slot_from <= end_date,
            ExportSlotFileRecord.is_truck_in == True
        )
        .order_by(ExportSlotFileRecord.truck_slot_from)
        .execution_options(yield_per=1000)  # ⚡ Larger chunks
    )
    
    result = await db.stream(query)
    
    # ⚡ Buffer rows before yielding (reduces I/O overhead)
    rows_buffer = []
    buffer_size = 100
    
    async for (slot,) in result:
        # AWBs already loaded via selectinload
        
        if not slot.awbs:
            # Slot without AWBs
            row = [
                slot.truck_number,
                "", "",
                # slot.truck_in_date_time.isoformat() if slot.truck_in_date_time else "",
                # slot.truck_out_date_time.isoformat() if slot.truck_out_date_time else "",
                # slot.truck_slot_from.isoformat() if slot.truck_slot_from else "",
                fmt_datetime(slot.truck_in_date_time),
        fmt_datetime(slot.truck_out_date_time),
        fmt_datetime(slot.truck_slot_from),
                "",
                slot.status or "",
                slot.company_name,
                slot.warehouse,
                slot.zone,
                slot.token_no or "",
                slot.cargo_type or "",
                slot.dock_number or "",
                slot.truck_in_by or "",
                slot.truck_out_by or "",
                # slot.dock_in_date_time.isoformat() if slot.dock_in_date_time else "",
                # slot.dock_out_date_time.isoformat() if slot.dock_out_date_time else "",
                fmt_datetime(slot.dock_in_date_time),
        fmt_datetime(slot.dock_out_date_time),
                slot.dock_in_by or "",
                slot.dock_out_by or "",
                ""
            ]
            writer.writerow(row)
            rows_buffer.append(output.getvalue())
            output.truncate(0)
            output.seek(0)
        else:
            # Create row for each AWB
            for awb in slot.awbs:
                row = [
                    slot.truck_number,
                    
                    awb.awb_id,
                    awb.pcs,
                    # slot.truck_in_date_time.isoformat() if slot.truck_in_date_time else "",
                    # slot.truck_out_date_time.isoformat() if slot.truck_out_date_time else "",
                    # slot.truck_slot_from.isoformat() if slot.truck_slot_from else "",
                    fmt_datetime(slot.truck_in_date_time),
        fmt_datetime(slot.truck_out_date_time),
        fmt_datetime(slot.truck_slot_from),
                    "",
                    slot.status or "",
                    slot.company_name,
                    slot.warehouse,
                    slot.zone,
                    slot.token_no or "",
                    slot.cargo_type or "",
                    slot.dock_number or "",
                    slot.truck_in_by or "",
                    slot.truck_out_by or "",
                    # slot.dock_in_date_time.isoformat() if slot.dock_in_date_time else "",
                    # slot.dock_out_date_time.isoformat() if slot.dock_out_date_time else "",
                    fmt_datetime(slot.dock_in_date_time),
        fmt_datetime(slot.dock_out_date_time),
                    slot.dock_in_by or "",
                    slot.dock_out_by or "",
                    "Yes" if awb.is_additional else "No"
                ]
                writer.writerow(row)
                rows_buffer.append(output.getvalue())
                output.truncate(0)
                output.seek(0)
        
        # ⚡ Yield buffer when it reaches threshold
        if len(rows_buffer) >= buffer_size:
            yield ''.join(rows_buffer)
            rows_buffer = []
    
    # ⚡ Yield any remaining rows
    if rows_buffer:
        yield ''.join(rows_buffer)



# =================================================================================================


# It is used for mark truck in
class ExportSlotService:

    @staticmethod
    async def get_unresolved_truck_ins(db: AsyncSession, truck_number: str):
        """Returns list of unresolved truck slots (Python objects)"""
        now_utc = get_utc_now()

        unresolved_stmt = await db.execute(
            select(ExportSlotFileRecord.truck_slot_from,
                    ExportSlotFileRecord.id,
                    ExportSlotFileRecord.is_truck_in,
                    ExportSlotFileRecord.is_truck_out,
                   
                   )
            .where(
                ExportSlotFileRecord.truck_number == truck_number,
                ExportSlotFileRecord.is_truck_in == True,
                ExportSlotFileRecord.is_truck_out == False,
                ExportSlotFileRecord.truck_slot_from <= now_utc
            )
        )
        return unresolved_stmt.all() 

    @staticmethod
    async def mark_truck_in(db: AsyncSession, truck_number: str, token_no: str, truck_slot_from: datetime,emp_id: str,truck_in_device: Optional[str] = None ):
        """Marks the truck in for a given slot. Returns the slot record object or None."""
        slot_stmt = await db.execute(
            select(ExportSlotFileRecord)
            .where(
                ExportSlotFileRecord.truck_number == truck_number,
                ExportSlotFileRecord.token_no == token_no,
                ExportSlotFileRecord.truck_slot_from == truck_slot_from,
                ExportSlotFileRecord.truck_in_date_time == None
                
            )
        )
        slot_record = slot_stmt.scalars().first()
        if not slot_record:
            return None

        now_utc = get_utc_now()
        slot_record.truck_in_date_time = now_utc
        slot_record.is_truck_in = True
        slot_record.truck_in_by = emp_id  # ✅ Set the user who marked i
        slot_record.truck_in_device = truck_in_device  
        db.add(slot_record)
        await db.commit()
        await db.refresh(slot_record)

        return slot_record




async def mark_truck_out(db: AsyncSession, truck_number: str, truck_slot_from: datetime,token_no:str,emp_id: str,truck_out_device: Optional[str] = None):
    """Marks the truck out for a given slot. Returns (slot_record, message)."""

    # Fetch the latest matching slot for the truck and slot time
    slot_stmt = await db.execute(
        select(ExportSlotFileRecord)
        .where(
            ExportSlotFileRecord.truck_number == truck_number,
            ExportSlotFileRecord.token_no == token_no,
            ExportSlotFileRecord.truck_slot_from == truck_slot_from
        )
    )
    slot_record = slot_stmt.scalars().first()

    if not slot_record:
        return None, "No slot record found for this truck and slot time."

    # Now check step-by-step eligibility
    if not slot_record.truck_in_date_time or not slot_record.is_truck_in:
        return None, "Truck has not been marked IN yet."

#   👌👌👌👌👌👌👌👌👌👌👌👌👌👌👌👌 2 chnages
    # if not slot_record.is_dock_in:
    #     return None, "Truck has not docked IN yet."

    # if not slot_record.is_dock_out:
    #     return None, "Truck has not docked OUT yet."

    if slot_record.truck_out_date_time is not None or slot_record.is_truck_out:
        return None, "Truck is already marked OUT."

    # ✅ If all checks pass, mark it out
    now_utc = get_utc_now()
    slot_record.truck_out_date_time = now_utc
    slot_record.is_truck_out = True
    slot_record.truck_out_by = emp_id
    slot_record.truck_out_device = truck_out_device 

    db.add(slot_record)
    await db.commit()
    await db.refresh(slot_record)

    return slot_record, "Truck marked out successfully."



# ------------------------------------------


@staticmethod
async def get_daily_summary(db: AsyncSession, summary_date: date):
    """
    Daily summary using NEW dock session model (AWBDockOperation).
    """
    start_dt = datetime.combine(summary_date, time.min, tzinfo=timezone.utc)
    end_dt = datetime.combine(summary_date, time.max, tzinfo=timezone.utc)

    try:
        # -------------------- 1) TRUCK IN --------------------
        truck_in_count = (
            await db.execute(
                select(func.count(ExportSlotFileRecord.id)).where(
                    ExportSlotFileRecord.truck_in_date_time.between(start_dt, end_dt)
                )
            )
        ).scalar() or 0


        # -------------------- 2) TRUCK OUT --------------------
        truck_out_count = (
            await db.execute(
                select(func.count(ExportSlotFileRecord.id)).where(
                    ExportSlotFileRecord.truck_out_date_time.between(start_dt, end_dt)
                )
            )
        ).scalar() or 0


        # -------------------- 3) DOCK IN events --------------------
        dock_in_count = (
            await db.execute(
                select(func.count(AWBDockOperation.id)).where(
                    AWBDockOperation.dock_in_date_time.between(start_dt, end_dt)
                )
            )
        ).scalar() or 0


        # -------------------- 4) DOCK OUT events --------------------
        dock_out_count = (
            await db.execute(
                select(func.count(AWBDockOperation.id)).where(
                    AWBDockOperation.dock_out_date_time.between(start_dt, end_dt)
                )
            )
        ).scalar() or 0


        # -------------------- 5) TOTAL SCANNED PCS --------------------
        scanned_pcs = (
            await db.execute(
                select(func.count(AWBSequence.id)).where(
                    AWBSequence.seq_time.between(start_dt, end_dt)
                )
            )
        ).scalar() or 0


        # -------------------- 6) TOTAL PCS SCHEDULED --------------------
        total_pcs = (
            await db.execute(
                select(func.coalesce(func.sum(ExportSlotAWB.pcs), 0))
                .join(ExportSlotFileRecord,
                      ExportSlotAWB.export_slot_id == ExportSlotFileRecord.id)
                .where(
                    ExportSlotFileRecord.truck_in_date_time.between(start_dt, end_dt)
                )
            )
        ).scalar() or 0

        # 6️⃣ Count additional PCS scanned (only for additional AWBs)
        result_additional_scanned = await db.execute(
            select(func.count(AWBSequence.id))
            .join(ExportSlotAWB, ExportSlotAWB.id == AWBSequence.awb_record_id)
            .where(
                and_(
                    ExportSlotAWB.is_additional == True,
                    AWBSequence.seq_time.between(start_dt, end_dt)
                )
            )
        )

        additional_scanned_pcs = result_additional_scanned.scalar() or 0

        # -------------------- 7) FLAG COUNT CHECKS --------------------
        flag_counts = (
            await db.execute(
                select(
                    func.count().filter(ExportSlotFileRecord.is_truck_in == True),
                    func.count().filter(ExportSlotFileRecord.is_truck_out == True),
                    func.count().filter(ExportSlotFileRecord.current_is_dock_in == True),
                    func.count().filter(ExportSlotFileRecord.current_is_dock_out == True),
                )
            )
        ).first() or (0,0,0,0)

        truck_in_flag, truck_out_flag, dock_in_flag, dock_out_flag = flag_counts


        return {
            "summary": {
                "truck_in": truck_in_count,
                "truck_out": truck_out_count,
                "dock_in": dock_in_count,         # <-- ACCURATE
                "dock_out": dock_out_count,       # <-- ACCURATE
                "total_pcs": total_pcs,
                "scanned_pcs": scanned_pcs,
                "additional_scanned_pcs": additional_scanned_pcs,


                "truck_in_flag": truck_in_flag,
                "truck_out_flag": truck_out_flag,
                "dock_in_flag": dock_in_flag,
                "dock_out_flag": dock_out_flag,

                "query_start": start_dt.isoformat(),
                "query_end": end_dt.isoformat(),
            }
        }

    except Exception as e:
        await db.rollback()
        raise HTTPException(500, f"Error fetching daily summary: {str(e)}")




# async def get_daily_summary(db: AsyncSession, summary_date: date):
#     """Fetch daily summary of truck and dock activity for a given date."""

#     # Convert date to start/end datetime in UTC
#     start_dt = datetime.combine(summary_date, time.min, tzinfo=timezone.utc)
#     end_dt = datetime.combine(summary_date, time.max, tzinfo=timezone.utc)

#     try:
#         # 1️⃣ Trucks that came IN on this date
#         result_in = await db.execute(
#             select(func.count(ExportSlotFileRecord.id)).where(
#                 ExportSlotFileRecord.truck_in_date_time.between(start_dt, end_dt)
#             )
#         )
#         truck_in_count = result_in.scalar() or 0

#         # 2️⃣ Trucks that went OUT on this date
#         result_out = await db.execute(
#             select(func.count(ExportSlotFileRecord.id)).where(
#                 ExportSlotFileRecord.truck_out_date_time.between(start_dt, end_dt)
#             )
#         )
#         truck_out_count = result_out.scalar() or 0

#         # 3️⃣ Dock IN activities on this date
#         result_dock_in = await db.execute(
#             select(func.count(ExportSlotFileRecord.id)).where(
#                 ExportSlotFileRecord.dock_in_date_time.between(start_dt, end_dt)
#             )
#         )
#         dock_in_count = result_dock_in.scalar() or 0

#         # 4️⃣ Dock OUT activities on this date
#         result_dock_out = await db.execute(
#             select(func.count(ExportSlotFileRecord.id)).where(
#                 ExportSlotFileRecord.dock_out_date_time.between(start_dt, end_dt)
#             )
#         )
#         dock_out_count = result_dock_out.scalar() or 0

#         # 5️⃣ Calculate SCANNED PCS (AWB Sequences) for this date
#         result_scanned = await db.execute(
#             select(func.count(AWBSequence.id)).where(
#                 AWBSequence.seq_time.between(start_dt, end_dt)
#             )
#         )
#         scanned_pcs = result_scanned.scalar() or 0

#         # 6️⃣ Total PCS scheduled for this date (from AWBs linked to slots)
#         result_total_pcs = await db.execute(
#             select(func.coalesce(func.sum(ExportSlotAWB.pcs), 0))
#             .join(ExportSlotFileRecord, ExportSlotAWB.export_slot_id == ExportSlotFileRecord.id)
#             .where(
#                 or_(
#                     ExportSlotFileRecord.truck_in_date_time.between(start_dt, end_dt),
#                     ExportSlotFileRecord.dock_in_date_time.between(start_dt, end_dt)
#                 )
#             )
#         )
#         total_pcs = result_total_pcs.scalar() or 0

#         # 7️⃣ Boolean flag counts (cross‑verification)
#         result_flags = await db.execute(
#             select(
#                 func.count(ExportSlotFileRecord.id).filter(ExportSlotFileRecord.is_truck_in == True),
#                 func.count(ExportSlotFileRecord.id).filter(ExportSlotFileRecord.is_truck_out == True),
#                 func.count(ExportSlotFileRecord.id).filter(ExportSlotFileRecord.is_dock_in == True),
#                 func.count(ExportSlotFileRecord.id).filter(ExportSlotFileRecord.is_dock_out == True),
#             ).where(
#                 or_(
#                     ExportSlotFileRecord.truck_in_date_time.between(start_dt, end_dt),
#                     ExportSlotFileRecord.truck_out_date_time.between(start_dt, end_dt),
#                     ExportSlotFileRecord.dock_in_date_time.between(start_dt, end_dt),
#                     ExportSlotFileRecord.dock_out_date_time.between(start_dt, end_dt),
#                 )
#             )
#         )
#         flag_counts = result_flags.first() or (0, 0, 0, 0)
#         truck_in_by_flags, truck_out_by_flags, dock_in_by_flags, dock_out_by_flags = flag_counts

#         return {
#             "summary": {
#                 "truck_in": truck_in_count,
#                 "truck_out": truck_out_count,
#                 "dock_in": dock_in_count,
#                 "dock_out": dock_out_count,
#                 "total_pcs": total_pcs,
#                 "scanned_pcs": scanned_pcs,

#                 # Cross‑verification using flags
#                 "truck_in_by_flags": truck_in_by_flags,
#                 "truck_out_by_flags": truck_out_by_flags,
#                 "dock_in_by_flags": dock_in_by_flags,
#                 "dock_out_by_flags": dock_out_by_flags,

#                 # Date range used for query
#                 "query_start": start_dt.isoformat(),
#                 "query_end": end_dt.isoformat(),
#             }
#         }

#     except Exception as e:
#         await db.rollback()
#         raise HTTPException(status_code=500, detail=f"Error fetching daily summary: {str(e)}")