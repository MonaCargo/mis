# services/export_car_message_awb_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from app.db.models.exportOperation.car_message import (
    ExportCarMessageAwbMaster
)
from app.utils.common.helperFunction import get_utc_now

# async def save_export_car_message_awbs(db: AsyncSession, df):

#     if df.empty:
#         return {
#             "total_received": 0,
#             "inserted": 0,
#             "already_present": 0,
#         }

#     records = df.to_dict(orient="records")

#     stmt = insert(ExportCarMessageAwbMaster).values(records)

#     stmt = stmt.on_conflict_do_nothing(
#         constraint="uq_awb_car_msg"
#     )

#     result = await db.execute(stmt)
#     await db.commit()

#     inserted_count = result.rowcount or 0
#     total_received = len(records)
#     already_present = total_received - inserted_count

#     return {
#         "total_received": total_received,
#         "inserted": inserted_count,
#         "already_present": already_present,
#     }





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