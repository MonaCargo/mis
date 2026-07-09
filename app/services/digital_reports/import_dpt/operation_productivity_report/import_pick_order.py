"""
save_pick_order_report(session, report_date, rows, uploaded_by) -> dict

Atomic replace-by-report_date:
  1. DELETE all existing dr_imp_pick_order rows for the given report_date.
  2. INSERT the freshly-cleaned rows, each tagged with that report_date.
Both happen in ONE transaction, so a failure leaves the day's data untouched
(no half-replaced state).

The cleaned `rows` come from clean_pick_order_report() and do NOT carry
report_date or uploaded_by — this service stamps them on.
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from sqlalchemy import delete, insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.digital_reports.import_dept.import_pick_order import DigitalReportImportPickOrder as PickOrder


# async def digital_report_save_pick_order_data(
#     session: AsyncSession,
#     report_date: date,
#     rows: list[dict],
#     uploaded_by: Optional[str] = None,
# ) -> dict:
#     """
#     Replace the pick-order data for `report_date` with `rows`, atomically.

#     Returns a small summary: {"report_date", "deleted", "inserted"}.
#     """
#     # Stamp report_date + uploader onto every row (bulk insert payload).
#     payload = [
#         {
#             **row,
#             "report_date": report_date,
#             "uploaded_by": uploaded_by,
#         }
#         for row in rows
#     ]

#     # One transaction: delete the day, then insert the new set.
#     # `session.begin()` opens a transaction that commits on success / rolls
#     # back on any exception — giving the all-or-nothing replace.
#     async with session.begin():
#         del_result = await session.execute(
#             delete(PickOrder).where(PickOrder.report_date == report_date)
#         )
#         deleted = del_result.rowcount or 0

#         inserted = 0
#         if payload:
#             # Chunk the insert to stay well under driver parameter limits
#             # (each row has ~9 columns; 1000-row chunks ≈ 9k params, safe).
#             CHUNK = 1000
#             for i in range(0, len(payload), CHUNK):
#                 await session.execute(insert(PickOrder), payload[i:i + CHUNK])
#             inserted = len(payload)

#     return {
#         "report_date": report_date.isoformat(),
#         "deleted": deleted,
#         "inserted": inserted,
#     }







async def digital_report_save_pick_order_data(
    db: AsyncSession,
    report_date: date,
    rows: list[dict],
    uploaded_by: Optional[str] = None,
) -> dict:
    """
    Atomic replace-by-report_date using explicit add_all + commit/rollback.
    Deletes the day's existing rows, then inserts the new set. On any error,
    rolls back so the day's data is left untouched.
    """
    try:
        # 1. Delete existing rows for this report_date.
        del_result = await db.execute(
            delete(PickOrder).where(PickOrder.report_date == report_date)
        )
        deleted = del_result.rowcount or 0

        # 2. Build ORM objects and add them.
        objs = [
            PickOrder(
                report_date=report_date,
                awb_no=row["awb_no"],
                hawb_no=row["hawb_no"],
                pcs_for_examination=row["pcs_for_examination"],
                rfe_datetime=row["rfe_datetime"],
                ffe_datetime=row["ffe_datetime"],
                poe_start_datetime=row["poe_start_datetime"],
                poe_end_datetime=row["poe_end_datetime"],
                uploaded_by=uploaded_by,
            )
            for row in rows
        ]
        db.add_all(objs)

        # 3. Commit the whole replace as one transaction.
        await db.commit()

        return {
            "report_date": report_date.isoformat(),
            "deleted": deleted,
            "inserted": len(objs),
        }

    except Exception:
        await db.rollback()
        raise