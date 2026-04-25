
# from __future__ import annotations

# from datetime import datetime, timezone
# from io import BytesIO

# import pandas as pd
# import pytz
# from sqlalchemy import text
# from sqlalchemy.dialects.postgresql import insert
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.db.models.exportOperation.car_message import ExportCarMessageAwbMaster
# from app.schemas.exportOperation.export_import_tp_report_for_car import ExportTpXrayUploadResponse
# from app.utils.exportOperation.export_tp_report_cleaning import clean_export_tp_xray
# from app.utils.exportOperation.import_tp_report_cleaning import clean_import_tp_xray

# IST = pytz.timezone("Asia/Kolkata")


# def _get_utc_now() -> datetime:
#     return datetime.now(timezone.utc)


# async def process_and_sync_export_tp_xray(
#     file_bytes: bytes,
#     file_type: str,
#     uploaded_by: str,
#     db: AsyncSession,
# ) -> ExportTpXrayUploadResponse:

#     # ── 1. Clean ────────────────────────────────────────────────────────────
#     #  All parsing / validation / type-casting done inside clean_export_tp_xray.
#     df, metadata = clean_export_tp_xray(BytesIO(file_bytes), file_type=file_type)

#     if df.empty:
#         return ExportTpXrayUploadResponse(
#             message="File processed but contained no valid AWB records.",
#             report_from_date=metadata.get("from_date"),
#             report_to_date=metadata.get("to_date"),
#             total_rows_in_file=0,
#             created=0,
#             updated=0,
#             skipped=0,
#         )

#     # ── 2. Rename report columns → model columns ────────────────────────────
#     df = df.rename(columns={
#         "AWB NO.":   "awb_no",
#         "ORGIN":     "origin",
#         "DESTINATION": "destination",
#         "PCS.":      "pcs",
#         "GROSS WT":  "gross_wt",
#         "CHG WT":    "chg_wt",
#         "NOG":       "nog",
#         "SHC":       "shc",

#         # keep original name temporarily — derived into 3 fields below
#           "X-RAY TYPE"  :    "xray_type",
#         "X-RAY START DATE & TIME": "_xray_start_dt",
#     })

#     # ── 3. Derive car_msg_date / car_msg_time (IST) + car_message_datetime_combo (UTC) ──
#     #
#     #  The cleaning function already parsed "X-RAY START DATE & TIME" into a
#     #  timezone-naive pandas Timestamp that represents IST wall-clock time.
#     #
#     #  car_msg_date             → IST date  (Date column in model)
#     #  car_msg_time             → IST HHMM string  e.g. "0924"  (String(20) in model)
#     #  car_message_datetime_combo → same moment converted to UTC-aware datetime

#     xray_start = df["_xray_start_dt"]   # tz-naive IST timestamps from cleaner

#     # Localise to IST then convert to UTC
#     xray_start_ist = xray_start.apply(
#         lambda ts: IST.localize(ts.to_pydatetime()) if pd.notna(ts) else None
#     )
#     xray_start_utc = xray_start_ist.apply(
#         lambda ts: ts.astimezone(timezone.utc) if ts is not None else None
#     )

#     df["car_msg_date"]              = xray_start_ist.apply(lambda ts: ts.date() if ts is not None else None)
#     df["car_msg_time"] = xray_start_ist.apply(lambda ts: ts.strftime("%H:%M:%S") if ts is not None else None)
#     df["car_message_datetime_combo"] = xray_start_utc

#     df = df.drop(columns=["_xray_start_dt"])

#     # ── 4. Select exactly the columns the model accepts from this report ─────
#     INSERT_COLS = [
#         "awb_no",
#         "origin", "destination",
#         "pcs", "gross_wt", "chg_wt",
#         "nog", "shc",
#         "car_msg_date", "car_msg_time",
#         "car_message_datetime_combo",
#          "xray_type"
#     ]
#     df = df[INSERT_COLS].copy()

#     # ── 5. Audit fields ─────────────────────────────────────────────────────
#     now = _get_utc_now()
#     df["uploaded_by"]         = uploaded_by
#     df["created_at"]          = now
#     df["updated_at"]          = now
#     df["is_ultra_fast"]       = False
#     df["is_manually_created"] = False
#     df["source"]              = "EXPORT_TP_XRAY" 

#     # ── 6. pandas NA / NaT → None so SQLAlchemy sends NULL ──────────────────
#     records = df.where(df.notna(), other=None).to_dict(orient="records")

#     # ── 7. Bulk upsert ───────────────────────────────────────────────────────
#     stmt = insert(ExportCarMessageAwbMaster).values(records)
#     stmt = stmt.on_conflict_do_update(
#         constraint="uq_awb_car_msg",
#         set_={
#             # ✅ only these 6 fields are refreshed on re-upload
#             "origin":      stmt.excluded.origin,
#             "destination": stmt.excluded.destination,
#             "pcs":         stmt.excluded.pcs,
#             "gross_wt":    stmt.excluded.gross_wt,
#             "chg_wt":      stmt.excluded.chg_wt,
#             "nog":         stmt.excluded.nog,
#             "shc":         stmt.excluded.shc,
#             "updated_at":  now,
#             "xray_type":stmt.excluded.xray_type,
#             # 🔒 NOT updated on conflict (preserved as-is):
#             #   shc, car_msg_date, car_msg_time, car_message_datetime_combo
#             #   rcs_datetime, status, agent, uploaded_by
#             #   sb_no, sb_date, hwb_no, volumetric_wt, vol_mc
#             #   is_ultra_fast, is_ultra_fast_marked_by, is_ultra_fast_marked_at
#             #   is_manually_created, manual_created_by
#             #   remarks, manual_creation_remarks, manual_pcs
#             #   created_at
#         },
#         where=(ExportCarMessageAwbMaster.is_manually_created == True),  # noqa: E712
#     ).returning(
#         text("(xmax = 0) AS is_inserted")   # True = inserted, False = updated
#     )

#     result = await db.execute(stmt)
#     await db.flush()

#     rows = result.fetchall()

#     inserted_count = sum(1 for r in rows if r[0] is True)
#     updated_count  = sum(1 for r in rows if r[0] is False)
#     total_received = len(records)
#     skipped_count  = total_received - len(rows)   # WHERE = False → manually created → skipped

#     return ExportTpXrayUploadResponse(
#         message=(
#             f"Export TP X-RAY report processed successfully. "
#             f"{inserted_count} created, {updated_count} updated, {skipped_count} skipped."
#         ),
#         report_from_date=metadata.get("from_date"),
#         report_to_date=metadata.get("to_date"),
#         total_rows_in_file=total_received,
#         created=inserted_count,
#         updated=updated_count,
#         skipped=skipped_count,
#         details=getattr(result, "details", None),
#     )






# # ============================== ✅ Import tp report process and save service ===========

# async def process_and_sync_import_tp_xray(
#     file_bytes: bytes,
#     file_type: str,
#     uploaded_by: str,
#     db: AsyncSession,
# ) -> ExportTpXrayUploadResponse:
 
#     # ── 1. Clean ────────────────────────────────────────────────────────────
#     #  All parsing / validation / type-casting done inside clean_import_tp_xray.
#     df, metadata = clean_import_tp_xray(BytesIO(file_bytes), file_type=file_type)
 
#     if df.empty:
#         return ExportTpXrayUploadResponse(
#             message="File processed but contained no valid AWB records.",
#             report_from_date=metadata.get("from_date"),
#             report_to_date=metadata.get("to_date"),
#             total_rows_in_file=0,
#             created=0,
#             updated=0,
#             skipped=0,
#         )
 
#     # ── 2. Rename report columns → model columns ────────────────────────────
#     df = df.rename(columns={
#         "AWB NO.":                   "awb_no",
#         "ORGIN":                     "origin",
#         "DESTINATION":               "destination",
#         "PCS.":                      "pcs",
#         "GROSS WT":                  "gross_wt",
#         "CHG WT":                    "chg_wt",
#         "NOG":                       "nog",
#         "SHC":                       "shc",
#         "X-RAY TYPE":                "xray_type",
#         # keep temporarily — derived into 3 fields below
#         "X-RAY STRT DATE & TIME":    "_xray_start_dt",
#     })
 
#     # ── 3. Derive car_msg_date / car_msg_time (IST) + car_message_datetime_combo (UTC) ──
#     #
#     #  Cleaning function returns "X-RAY STRT DATE & TIME" as tz-naive Timestamp
#     #  representing IST wall-clock time.
#     #
#     #  car_msg_date              → IST date        (Date column in model)
#     #  car_msg_time              → IST "HH:MM:SS"  (String(20) in model)
#     #  car_message_datetime_combo → UTC-aware datetime
 
#     xray_start = df["_xray_start_dt"]
 
#     xray_start_ist = xray_start.apply(
#         lambda ts: IST.localize(ts.to_pydatetime()) if pd.notna(ts) else None
#     )
#     xray_start_utc = xray_start_ist.apply(
#         lambda ts: ts.astimezone(timezone.utc) if ts is not None else None
#     )
 
#     df["car_msg_date"]               = xray_start_ist.apply(lambda ts: ts.date() if ts is not None else None)
#     df["car_msg_time"]               = xray_start_ist.apply(lambda ts: ts.strftime("%H:%M:%S") if ts is not None else None)
#     df["car_message_datetime_combo"] = xray_start_utc
 
#     df = df.drop(columns=["_xray_start_dt"])
 
#     # ── 4. Select exactly the columns the model accepts from this report ─────
#     INSERT_COLS = [
#         "awb_no",
#         "origin", "destination",
#         "pcs", "gross_wt", "chg_wt",
#         "nog", "shc",
#         "car_msg_date", "car_msg_time",
#         "car_message_datetime_combo",
#         "xray_type",
#     ]
#     df = df[INSERT_COLS].copy()
 
#     # ── 5. Audit fields ─────────────────────────────────────────────────────
#     now = _get_utc_now()
#     df["uploaded_by"]         = uploaded_by
#     df["created_at"]          = now
#     df["updated_at"]          = now
#     df["is_ultra_fast"]       = False
#     df["is_manually_created"] = False
#     df["source"]              = "IMPORT_TP_XRAY"
 
#     # ── 6. pandas NA / NaT → None so SQLAlchemy sends NULL ──────────────────
#     records = df.where(df.notna(), other=None).to_dict(orient="records")
 
#     # ── 7. Bulk upsert ───────────────────────────────────────────────────────
#     stmt = insert(ExportCarMessageAwbMaster).values(records)
 
#     stmt = stmt.on_conflict_do_update(
#         constraint="uq_awb_car_msg",
#         set_={
#             # ✅ only these 6 fields are refreshed on re-upload
#             "origin":      stmt.excluded.origin,
#             "destination": stmt.excluded.destination,
#             "pcs":         stmt.excluded.pcs,
#             "gross_wt":    stmt.excluded.gross_wt,
#             "chg_wt":      stmt.excluded.chg_wt,
#             "nog":         stmt.excluded.nog,
#             "shc":         stmt.excluded.shc,
#             "updated_at":  now,
#              "xray_type":stmt.excluded.xray_type,
#             # 🔒 NOT updated on conflict (preserved as-is):
#             #   shc, car_msg_date, car_msg_time, car_message_datetime_combo
#             #   xray_type, remarks, uploaded_by, source
#             #   rcs_datetime, status, agent
#             #   sb_no, sb_date, hwb_no, volumetric_wt, vol_mc
#             #   is_ultra_fast, is_ultra_fast_marked_by, is_ultra_fast_marked_at
#             #   is_manually_created, manual_created_by
#             #   manual_creation_remarks, manual_pcs
#             #   created_at
#         },
#         where=(ExportCarMessageAwbMaster.is_manually_created == True),  # noqa: E712
#     ).returning(
#         text("(xmax = 0) AS is_inserted")   # True = inserted, False = updated
#     )
 
#     result = await db.execute(stmt)
#     await db.flush()
   
 
#     rows = result.fetchall()
 
#     inserted_count = sum(1 for r in rows if r[0] is True)
#     updated_count  = sum(1 for r in rows if r[0] is False)
#     total_received = len(records)
#     skipped_count  = total_received - len(rows)   # WHERE = False → manually created → skipped
 
#     return ExportTpXrayUploadResponse(
#         message=(
#             f"Import TP X-RAY report processed successfully. "
#             f"{inserted_count} created, {updated_count} updated, {skipped_count} skipped."
#         ),
#         report_from_date=metadata.get("from_date"),
#         report_to_date=metadata.get("to_date"),
#         total_rows_in_file=total_received,
#         created=inserted_count,
#         updated=updated_count,
#         skipped=skipped_count,
        
#     )
















# =================== 🫥 SAVING IMPORT AND EXPORT TP DATA IN BUFFER TABLE ===============================

"""
services/export_tp_xray_service.py

Business logic for persisting Export TP X-RAY data.

Upload flow
───────────
1. Caller passes a cleaned DataFrame (output of clean_export_tp_xray).
2. Service reads the month_uploaded value from the DataFrame.
3. Deletes ALL existing rows for that month_uploaded in one statement.
4. Bulk-inserts the new rows.
5. Returns a summary dict.

This replaces the entire month's data on every upload, which is what we
want because:
  - Same AWB with a new X-RAY START TIME = new part shipment → keep it.
  - True duplicates (same AWB + same X-RAY START TIME) were already
    dropped by the cleaner → we never insert them twice.
"""

from __future__ import annotations

import numpy as np
import pandas as pd
from sqlalchemy import delete
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.exportOperation.export_and_import_tp_xray import ExportTpXray, ImportTpXray
from app.db.models.exportOperation.car_message import ExportCarMessageAwbMaster
from app.services.export_slot_file_upload_service import get_utc_now


# ── Column map: DataFrame column name → ORM attribute name ──────────────────
_EXPORT_COL_MAP: dict[str, str] = {
    "AWB NO."                  : "awb_no",
    "ORGIN"                    : "origin",
    "DESTINATION"              : "destination",
    "PCS."                     : "pcs",
    "GROSS WT"                 : "grs_wt",
    "CHG WT"                   : "chg_wt",
    "NOG"                      : "nog",
    "SHC"                      : "shc",
    "X-RAY START DATE & TIME"  : "xray_start_datetime",
    "X-RAY END DATE & TIME"    : "xray_end_datetime",
    "X-RAY TYPE"               : "xray_type",
    "X-RAY DT/TIME"            : "xray_datetime",
    "X-RAY-USER"               : "xray_user",
    "DOC ACCPT DT/ TIME"       : "doc_accpt_datetime",
    "RCS/RCF/RCT DT/TIME"      : "rcs_rcf_rct_datetime",
    "UPLIFTING DT/TIME"        : "uplifting_datetime",
    "FLT NO"                   : "flt_no",
    "AGENT NAME"               : "agent_name",
    "DEVICE MODEL NO."         : "device_model_no",
    "month_uploaded"           : "month_uploaded",
    "uploaded_at"              : "uploaded_at",
    "Serial No."              : "serial_no",
}


# def _sanitize(val):
#     """Convert NaN / NaT / numpy scalars to Python-native types for SQLAlchemy."""
#     if val is None:
#         return None
#     if isinstance(val, float) and np.isnan(val):
#         return None
#     if isinstance(val, pd.Timestamp):
#         return None if pd.isna(val) else val.to_pydatetime()
#     if isinstance(val, np.generic):
#         return val.item()
#     return val

# AFTER — datetime/NaN fully handled in cleaner, only numpy scalars remain
def _sanitize(val):
    if isinstance(val, np.generic):
        return val.item()
    return val

def _df_to_export_orm_rows(df: pd.DataFrame) -> list[ExportTpXray]:
    """Convert a cleaned DataFrame to a list of ORM objects."""
    rows = []
    for record in df.to_dict(orient="records"):
        kwargs = {
            orm_col: _sanitize(record.get(src_col))
            for src_col, orm_col in _EXPORT_COL_MAP.items()
            if src_col in record
        }
        rows.append(ExportTpXray(**kwargs))
    return rows


async def upsert_export_tp_xray_month_data(db: AsyncSession, df: pd.DataFrame) -> dict:
    """
    Replace all rows for the given month_uploaded with the new DataFrame.

    Args:
        db:  SQLAlchemy Session (caller manages commit/rollback).
        df:  Cleaned DataFrame from clean_export_tp_xray().

    Returns:
        {
            "month_uploaded": "2025-03",
            "deleted_rows":   142,
            "inserted_rows":  157,
        }
    """
    if df.empty:
        raise ValueError("DataFrame is empty — nothing to save.")

    month_uploaded: str = df["month_uploaded"].iloc[0]

    # ── 1. Delete existing rows for this month ────────────────────────────────
    result =await db.execute(
        delete(ExportTpXray).where(
            ExportTpXray.month_uploaded == month_uploaded
        )
    )
    deleted_count = result.rowcount

    # ── 2. Insert new rows ────────────────────────────────────────────────────
    # AFTER
    # ── 2. Batch insert new rows (avoids query argument limit on large datasets) ──
    BATCH_SIZE = 500
    orm_rows = _df_to_export_orm_rows(df)

    for i in range(0, len(orm_rows), BATCH_SIZE):
        db.add_all(orm_rows[i : i + BATCH_SIZE])
        await db.flush()   # sends batch to DB without committing

    return {
        "month_uploaded": month_uploaded,
        "deleted_rows"  : deleted_count,
        "inserted_rows" : len(orm_rows),
    }



# ==== 🫥🫥🫥 Service for Import TP report ========================================================

_IMPORT_COL_MAP: dict[str, str] = {
    "AWB NO."                  : "awb_no",
    "ORGIN"                    : "origin",
    "DESTINATION"              : "destination",
    "PCS."                     : "pcs",
    "GROSS WT"                 : "grs_wt",
    "CHG WT"                   : "chg_wt",
    "NOG"                      : "nog",
    "SHC"                      : "shc",
    "X-RAY STRT DATE & TIME"   : "xray_start_datetime",   # note: STRT not START
    "X-RAY END DATE & TIME"    : "xray_end_datetime",
    "X-RAY TYPE"               : "xray_type",
    "X-RAY DT/TIME"            : "xray_datetime",
    "X-RAY-USER"               : "xray_user",
    "PHS (PCS)"                : "phs_pcs",
    "ETD (PCS)"                : "etd_pcs",
    "EDS (PCS)"                : "eds_pcs",
    "EDD (PCS)"                : "edd_pcs",
    "VCK (PCS)"                : "vck_pcs",
    "CMD (PCS)"                : "cmd_pcs",
    "RCS/RCF/RCT DT/TIME"      : "rcs_rcf_rct_datetime",
    "UPLIFTING DT/TIME"        : "uplifting_datetime",
    "FLT NO"                   : "flt_no",
    "AGENT NAME"               : "agent_name",
    "SERIAL NO."               : "serial_no",
    "DEVICE MODEL NO."         : "device_model_no",
    "REMARKS"                  : "remarks",
    "month_uploaded"           : "month_uploaded",
    "uploaded_at"              : "uploaded_at",
}


def _df_to_import_orm_rows(df: pd.DataFrame) -> list[ImportTpXray]:
    rows = []
    for record in df.to_dict(orient="records"):
        kwargs = {
            orm_col: _sanitize(record.get(src_col))
            for src_col, orm_col in _IMPORT_COL_MAP.items()
            if src_col in record
        }
        rows.append(ImportTpXray(**kwargs))
    return rows


async def upsert_import_tp_xray_month_data(db: AsyncSession, df: pd.DataFrame) -> dict:
    if df.empty:
        raise ValueError("DataFrame is empty — nothing to save.")

    month_uploaded: str = df["month_uploaded"].iloc[0]

    result = await db.execute(
        delete(ImportTpXray).where(ImportTpXray.month_uploaded == month_uploaded)
    )
    deleted_count = result.rowcount

    BATCH_SIZE = 500
    orm_rows = _df_to_import_orm_rows(df)

    for i in range(0, len(orm_rows), BATCH_SIZE):
        db.add_all(orm_rows[i : i + BATCH_SIZE])
        await db.flush()

    return {
        "month_uploaded": month_uploaded,
        "deleted_rows"  : deleted_count,
        "inserted_rows" : len(orm_rows),
    }




# ============== 🫥🫥🫥🫥🫥 SERVICE USED TO SAVED DATA IN CAR MESSAGE AWB MASTER TABLE ======================




from datetime import datetime
from collections import defaultdict

import pytz
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exportOperation.export_and_import_tp_xray import ExportTpXray



IST = pytz.timezone("Asia/Kolkata")


def convert_utc_to_ist_date_time(dt):
    """
    Convert UTC datetime → IST date + IST time string

    Example:
        2026-03-05 07:36:00+00:00
        →
        car_msg_date = 2026-03-05
        car_msg_time = "13:06:00"
    """
    if not dt:
        return None, None

    # safety if timezone missing
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)

    ist_dt = dt.astimezone(IST)

    return (
        ist_dt.date(),
        ist_dt.strftime("%H:%M:%S")
    )


# DYNAMIC FUNCTION TO KNOW WHICH TP NEED TO PROCESS 
async def process_tp_to_car_message_master(
    db: AsyncSession,
    month_uploaded: str,
    emp_id: str,
    source_type: str,
):
    """
    Generic processor for BOTH:
        - export_tp_xray
        - import_tp_xray

    source_type:
        "export"
        "import"

    Rules:
    - group by AWB
    - sum pcs / gross_wt / chg_wt
    - first occurrence for:
        origin, destination, nog, shc,
        xray_type, xray_start_datetime
    - save into export_car_message_awb_master
    - ON CONFLICT UPDATE for existing AWB
    - car_msg_date/time + combo datetime never change
    """

    # =====================================================
    # STEP 1 → dynamic model selection
    # =====================================================

    if source_type == "export":
        model = ExportTpXray
        source_name = "EXPORT_TP_XRAY"

    elif source_type == "import":
        model = ImportTpXray
        source_name = "IMPORT_TP_XRAY"

    else:
        raise ValueError("source_type must be either 'export' or 'import'")

    # =====================================================
    # STEP 2 → fetch required rows
    # =====================================================

    result = await db.execute(
        select(
            model.awb_no,
            model.origin,
            model.destination,
            model.pcs,
            model.grs_wt,
            model.chg_wt,
            model.nog,
            model.shc,
            model.xray_type,
            model.xray_start_datetime,
        )
        .where(
            model.month_uploaded == month_uploaded
        )
        .order_by(
            model.awb_no,
            model.xray_start_datetime.asc()
        )
    )

    rows = result.all()

    if not rows:
        return {
            "source": source_name,
            "month_uploaded": month_uploaded,
            "processed": 0,
            "created_or_updated": 0,
        }

    # =====================================================
    # STEP 3 → group by AWB
    # =====================================================

    grouped = {}

    for row in rows:
        awb = row.awb_no

        if awb not in grouped:
            grouped[awb] = {
                "awb_no": awb,
                "origin": row.origin,
                "destination": row.destination,
                "pcs": row.pcs or 0,
                "gross_wt": float(row.grs_wt or 0),
                "chg_wt": float(row.chg_wt or 0),
                "nog": row.nog,
                "shc": row.shc,
                "xray_type": row.xray_type,
                "first_xray_start": row.xray_start_datetime,
            }
        else:
            grouped[awb]["pcs"] += row.pcs or 0
            grouped[awb]["gross_wt"] += float(row.grs_wt or 0)
            grouped[awb]["chg_wt"] += float(row.chg_wt or 0)

    print(f"{source_name} total rows fetched: {len(rows)}")
    print(f"{source_name} unique AWBs: {len(grouped)}")
    print(f"{source_name} duplicate rows merged: {len(rows) - len(grouped)}")

    # =====================================================
    # STEP 4 → prepare payload
    # =====================================================

    payload = []
    now = get_utc_now()

    for _, item in grouped.items():
        combo_dt = item["first_xray_start"]
        car_msg_date, car_msg_time = convert_utc_to_ist_date_time(combo_dt)

        payload.append({
            "awb_no": item["awb_no"],
            "origin": item["origin"],
            "destination": item["destination"],
            "pcs": item["pcs"],
            "gross_wt": item["gross_wt"],
            "chg_wt": item["chg_wt"],
            "nog": item["nog"],
            "shc": item["shc"],
            "car_message_datetime_combo": combo_dt,
            "car_msg_date": car_msg_date,
            "car_msg_time": car_msg_time,
            "xray_type": item["xray_type"],
            "source": source_name,
            "uploaded_by": emp_id,
            "created_at": now,
            "updated_at": now,
        })

    # =====================================================
    # STEP 5 → batch UPSERT
    # =====================================================

    BATCH_SIZE = 300

    for i in range(0, len(payload), BATCH_SIZE):
        batch = payload[i:i + BATCH_SIZE]

        stmt = insert(ExportCarMessageAwbMaster).values(batch)

        stmt = stmt.on_conflict_do_update(
            constraint="uq_awb_car_msg",
            set_={
                "pcs": stmt.excluded.pcs,
                "gross_wt": stmt.excluded.gross_wt,
                "chg_wt": stmt.excluded.chg_wt,
                "nog": stmt.excluded.nog,
                "shc": stmt.excluded.shc,
                "updated_at": stmt.excluded.updated_at,
                # intentionally NOT updating:
                # car_msg_date
                # car_msg_time
                # car_message_datetime_combo
            }
        )

        await db.execute(stmt)

    await db.flush()

    return {
        "source": source_name,
        "month_uploaded": month_uploaded,
        "processed": len(grouped),
        "created_or_updated": len(payload),
    }

# common and for both in sequential run
async def process_both_tp_to_car_message_master(
    db: AsyncSession,
    month_uploaded: str,
    emp_id: str,
):
    """
    Final main function

    Process sequence:
        1. IMPORT first
        2. EXPORT second

    Same month_uploaded
    Same master table
    One button → one route → both process
    """

    import_summary = await process_tp_to_car_message_master(
        db=db,
        month_uploaded=month_uploaded,
        emp_id=emp_id,
        source_type="import",
    )

    export_summary = await process_tp_to_car_message_master(
        db=db,
        month_uploaded=month_uploaded,
        emp_id=emp_id,
        source_type="export",
    )

    return {
        "status": "success",
        "month_uploaded": month_uploaded,
        "import_processed": import_summary["processed"],
        "import_created_or_updated": import_summary["created_or_updated"],
        "export_processed": export_summary["processed"],
        "export_created_or_updated": export_summary["created_or_updated"],
        "final_master_updated": True,
    }











# 🫥 OLD SINGLE EXPORT TP FUNCTION TO SAVE IN CAR MESSAGE TABLE--
# async def process_export_tp_to_car_message_master(
#     db: AsyncSession,
#     month_uploaded: str,
#     emp_id:str,
# ):
#     """
#     Process one month of Export TP X-RAY data
#     and save into export_car_message_awb_master.

#     Rules:
#     ------
#     1. Group by AWB
#     2. Sum:
#         - pcs
#         - gross_wt
#         - chg_wt
#     3. First occurrence values:
#         - origin
#         - destination
#         - nog
#         - shc
#         - xray_type
#         - xray_start_datetime
#     4. car_message_datetime_combo
#         = first xray_start_datetime
#     5. car_msg_date
#         = IST date of first xray_start_datetime
#     6. car_msg_time
#         = IST time string of first xray_start_datetime
#     7. source
#         = EXPORT_TP_XRAY

#     ON CONFLICT:
#     ------------
#     If AWB already exists:
#         update only:
#             pcs
#             gross_wt
#             chg_wt
#             origin
#             destination
#             nog
#             shc
#             xray_type
#             source
#             updated_at

#         NEVER update:
#             car_msg_date
#             car_msg_time
#             car_message_datetime_combo

#     because first CAR message datetime must remain fixed.
#     """

#     # =====================================================
#     # STEP 1: fetch only required columns for one month
#     # =====================================================

#     result = await db.execute(
#         select(
#             ExportTpXray.awb_no,
#             ExportTpXray.origin,
#             ExportTpXray.destination,
#             ExportTpXray.pcs,
#             ExportTpXray.grs_wt,
#             ExportTpXray.chg_wt,
#             ExportTpXray.nog,
#             ExportTpXray.shc,
#             ExportTpXray.xray_type,
#             ExportTpXray.xray_start_datetime,
#         )
#         .where(
#             ExportTpXray.month_uploaded == month_uploaded
#         )
#         .order_by(
#             ExportTpXray.awb_no,
#             ExportTpXray.xray_start_datetime.asc()
#         )
#     )

#     rows = result.all()

#     if not rows:
#         return {
#             "month_uploaded": month_uploaded,
#             "processed": 0,
#             "created_or_updated": 0,
#         }

#     # =====================================================
#     # STEP 2: group by AWB in Python
#     # (important before ON CONFLICT)
#     # =====================================================

#     grouped = {}

#     for row in rows:
#         awb = row.awb_no

#         if awb not in grouped:
#             # first occurrence → keep first values
#             grouped[awb] = {
#                 "awb_no": awb,
#                 "origin": row.origin,
#                 "destination": row.destination,
#                 "pcs": row.pcs or 0,
#                 "gross_wt": float(row.grs_wt or 0),
#                 "chg_wt": float(row.chg_wt or 0),
#                 "nog": row.nog,
#                 "shc": row.shc,
#                 "xray_type": row.xray_type,
#                 "first_xray_start": row.xray_start_datetime,
#             }
#         else:
#             # repeated AWB → only sum numeric values
#             grouped[awb]["pcs"] += row.pcs or 0
#             grouped[awb]["gross_wt"] += float(row.grs_wt or 0)
#             grouped[awb]["chg_wt"] += float(row.chg_wt or 0)

#     # =====================================================
#     # STEP 3: prepare payload for bulk UPSERT
#     # =====================================================

#     payload = []

#     for awb, item in grouped.items():
#         combo_dt = item["first_xray_start"]

#         car_msg_date, car_msg_time = convert_utc_to_ist_date_time(combo_dt)

#         payload.append({
#             "awb_no": item["awb_no"],
#             "origin": item["origin"],
#             "destination": item["destination"],
#             "pcs": item["pcs"],
#             "gross_wt": item["gross_wt"],
#             "chg_wt": item["chg_wt"],
#             "nog": item["nog"],
#             "shc": item["shc"],
#             "car_message_datetime_combo": combo_dt,
#             "car_msg_date": car_msg_date,
#             "car_msg_time": car_msg_time,
#             "xray_type": item["xray_type"],
#             "source": "EXPORT_TP_XRAY",
#             "created_at":get_utc_now(),
#             "updated_at": get_utc_now(),
#             "uploaded_by":emp_id 
#         })

#     # =====================================================
#     # STEP 4: PostgreSQL bulk UPSERT
#     # (fast even for 4000+ rows)
#     # =====================================================


#     BATCH_SIZE = 500

#     for i in range(0, len(payload), BATCH_SIZE):
#         batch = payload[i : i + BATCH_SIZE]

#         stmt = insert(ExportCarMessageAwbMaster).values(batch)

#         stmt = stmt.on_conflict_do_update(
#             constraint="uq_awb_car_msg",  # unique constraint on awb_no
#             set_={
#                 # update allowed fields only
#                 # "origin": stmt.excluded.origin,
#                 # "destination": stmt.excluded.destination,
#                 "pcs": stmt.excluded.pcs,
#                 "gross_wt": stmt.excluded.gross_wt,
#                 "chg_wt": stmt.excluded.chg_wt,
#                 "nog": stmt.excluded.nog,
#                 "shc": stmt.excluded.shc,
#                 # "xray_type": stmt.excluded.xray_type,
#                 # "source": stmt.excluded.source,
#                 "updated_at": stmt.excluded.updated_at,

#                 # intentionally NOT updating:
#                 # car_msg_date
#                 # car_msg_time
#                 # car_message_datetime_combo
#             }
#          )

#         await db.execute(stmt)

#     await db.flush()

#     return {
#         "month_uploaded": month_uploaded,
#         "processed": len(grouped),
#         "created_or_updated": len(payload),
#     }
