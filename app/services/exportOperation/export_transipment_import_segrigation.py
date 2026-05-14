from datetime import datetime, timezone

import pandas as pd
import pytz
from sqlalchemy import delete, func, or_, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exportOperation.car_message import ExportCarMessageAwbMaster
from app.db.models.exportOperation.export_transipment_report import ExportTranshipmentReport
from app.db.models.exportOperation.import_segrigation_report import ImportSegregationReport
from app.services.export_slot_file_upload_service import get_utc_now
from dateutil.relativedelta import relativedelta


# ── Column map: DataFrame col → ORM attribute ────────────────────────────────

_COL_MAP_IMP_SEGRIGATION: dict[str, str] = {
    "Flight No."                    : "flight_no",
    "Flight Date"                   : "flight_date",
    "AWB No"                        : "awb_no",
    "SFX"                           : "sfx",
    "ATA_Date/Time"                 : "ata_datetime",
    "FLT DOC Arrival_Date/Time"     : "flt_doc_arrival",
    "Last ULD Arrival Date & Time"  : "last_uld_arrival",
    "Bulk ULD Arrival Date & Time"  : "bulk_uld_arrival",
    "Org"                           : "org",
    "DEST"                          : "dest",
    "Manifest Pcs"                  : "manifest_pcs",
    "Manifest Wgt"                  : "manifest_wgt",
    "SEG Pcs"                       : "seg_pcs",
    "SEG Wgt"                       : "seg_wgt",
    "PCS"                           : "pcs",
    "Gross weight"                  : "gross_wgt",
    "CHG WGT"                       : "chg_wgt",
    "Vol(MC)"                       : "vol_mc",
    "No of Houses"                  : "no_of_houses",
    "SHC"                           : "shc",
    "CHG SHC"                       : "chg_shc",
    "Billing SHC"                   : "billing_shc",
    "NOG"                           : "nog",
    "Consignee Details"             : "consignee_details",
    "AWD date"                      : "awd_date",
    "NFD date"                      : "nfd_date",
    "RCF date"                      : "rcf_date",
    "DO date&time"                  : "do_datetime",
    "TFD date&time"                 : "tfd_datetime",
    "EGM/IGM_NO"                    : "egm_igm_no",
    "FLT_COM_DAT_TIM"               : "flt_com_datetime",
    "FLIGHT STATUS"                 : "flight_status",
    "month_uploaded"                : "month_uploaded",
    "report_date"                   : "report_date",
    "uploaded_at"                   : "uploaded_at",
}


def _sanitize(val):
    """Convert NaN / NaT / pandas NA → None for asyncpg compatibility."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    try:
        if pd.isnull(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _df_to_orm_rows_segrigation(df: pd.DataFrame) -> list[ImportSegregationReport]:
    rows = []
    for record in df.to_dict(orient="records"):
        kwargs = {
            orm_col: _sanitize(record.get(src_col))
            for src_col, orm_col in _COL_MAP_IMP_SEGRIGATION.items()
            if src_col in record
        }
        rows.append(ImportSegregationReport(**kwargs))
    return rows


async def upsert_import_segregation_report_month(
    db: AsyncSession,
    df: pd.DataFrame,
) -> dict:
    """
    Delete all existing rows for the month in df, then bulk-insert new rows.
    Returns summary dict with deleted_rows, inserted_rows, month_uploaded.
    """
    if df.empty:
        raise ValueError("DataFrame is empty — nothing to save.")

    month_uploaded: str = df["month_uploaded"].iloc[0]

    report_date         = df["report_date"].iloc[0]   # datetime.date — delete by day
 
    # Delete only rows for this specific report date (not the whole month),
    # so re-uploading today's report replaces only today's data.
    result = await db.execute(
        delete(ImportSegregationReport).where(
            ImportSegregationReport.report_date == report_date
        )
    )

    deleted_count = result.rowcount

    # ── Bulk insert in batches ────────────────────────────────────────────────
    BATCH_SIZE = 500
    orm_rows   = _df_to_orm_rows_segrigation(df)

    for i in range(0, len(orm_rows), BATCH_SIZE):
        db.add_all(orm_rows[i : i + BATCH_SIZE])
        await db.flush()

    return {
        "month_uploaded": month_uploaded,
         "report_date"   : str(report_date),
        "deleted_rows"  : deleted_count,
        "inserted_rows" : len(orm_rows),
    }













# ======================== Export transipment report ==============================


# ── Column map: cleaned DataFrame col → ORM attribute ────────────────────────

_COL_MAP: dict[str, str] = {
    "AWB No"                        : "awb_no",
    "PCS"                           : "pcs",
    "Gross wgt"                     : "gross_wgt",
    "Rec_PCS"                       : "rec_pcs",
    "Received wgt"                  : "received_wgt",
    "Received_Chg_Wgt"              : "received_chg_wgt",
    "SHC"                           : "shc",
    "Billing SHC"                   : "billing_shc",
    "Commodity"                     : "commodity",
    "ORG"                           : "org",
    "DES"                           : "des",
    "DOC DATE & TIME"               : "doc_datetime",
    "EXP TP SEG FLIGHT No."         : "exp_tp_seg_flight_no",
    "EXP TP FLIGHT DATE"            : "exp_tp_flight_date",
    "EXP TP SEG No DATE AND TIME"   : "exp_tp_seg_datetime",
    "TRM NO"                        : "trm_no",
    "TRM DATE"                      : "trm_date",
    "XRAY DATETIME"                 : "xray_datetime",          # merged X-Ray DATE + TIME
    "RAMP TRANSFER DATE/TIME"       : "ramp_transfer_datetime",
    "RAMP TRANSFER REMARK"          : "ramp_transfer_remark",
    "RAMP TRANSFER USER"            : "ramp_transfer_user",
    "AIRLINE CD"                    : "airline_cd",
    "FLIGHT NO"                     : "flight_no",
    "FLIGHT DATE"                   : "flight_date",
    "ULD LOAD"                      : "uld_load",
    "DEPARTURE DATE & TIME"         : "departure_datetime",
    "month_uploaded"                : "month_uploaded",
    "uploaded_at"                   : "uploaded_at",
}


def _sanitize(val):
    """Convert NaN / NaT / pandas NA → None for asyncpg compatibility."""
    if val is None:
        return None
    if isinstance(val, float) and pd.isna(val):
        return None
    try:
        if pd.isnull(val):
            return None
    except (TypeError, ValueError):
        pass
    return val


def _df_to_orm_rows_for_transipment(df: pd.DataFrame) -> list[ExportTranshipmentReport]:
    rows = []
    for record in df.to_dict(orient="records"):
        kwargs = {
            orm_col: _sanitize(record.get(src_col))
            for src_col, orm_col in _COL_MAP.items()
            if src_col in record
        }
        rows.append(ExportTranshipmentReport(**kwargs))
    return rows


async def upsert_export_transhipment_month(
    db: AsyncSession,
    df: pd.DataFrame,
) -> dict:
    """
    Delete all existing rows for month_uploaded, then bulk-insert new rows.
    Returns summary dict: deleted_rows, inserted_rows, month_uploaded.
    """
    if df.empty:
        raise ValueError("DataFrame is empty — nothing to save.")

    month_uploaded: str = df["month_uploaded"].iloc[0]

    # ── Delete existing month data ────────────────────────────────────────────
    result = await db.execute(
        delete(ExportTranshipmentReport).where(
            ExportTranshipmentReport.month_uploaded == month_uploaded
        )
    )
    deleted_count = result.rowcount

    # ── Bulk insert in batches ────────────────────────────────────────────────
    BATCH_SIZE = 500
    orm_rows   = _df_to_orm_rows_for_transipment(df)

    for i in range(0, len(orm_rows), BATCH_SIZE):
        db.add_all(orm_rows[i : i + BATCH_SIZE])
        await db.flush()

    return {
        "month_uploaded": month_uploaded,
        "deleted_rows"  : deleted_count,
        "inserted_rows" : len(orm_rows),
    }




# ============== 🫥 Imp Segrigation and Exp transipment two month process ========================

_IST = pytz.timezone("Asia/Kolkata")
 
 
def _utc_to_ist_date_time(dt):
    if not dt:
        return None, None
    if dt.tzinfo is None:
        dt = pytz.utc.localize(dt)
    ist_dt = dt.astimezone(_IST)
    return ist_dt.date(), ist_dt.strftime("%H:%M:%S")
 
 
def _prev_month(month_uploaded: str) -> str:
    dt = datetime.strptime(month_uploaded, "%Y-%m")
    return (dt - relativedelta(months=1)).strftime("%Y-%m")
 
async def _process_segregation(db, month_current, month_prev, emp_id):
    result = await db.execute(
        select(
            ImportSegregationReport.awb_no,
            ImportSegregationReport.org,
            ImportSegregationReport.dest,
            ImportSegregationReport.pcs,
            ImportSegregationReport.gross_wgt,
            ImportSegregationReport.chg_wgt,
            ImportSegregationReport.nog,
            ImportSegregationReport.billing_shc,
            ImportSegregationReport.flt_doc_arrival,
        )
        .where(or_(
            ImportSegregationReport.month_uploaded == month_current,
            ImportSegregationReport.month_uploaded == month_prev,
        ))
        .order_by(
            ImportSegregationReport.awb_no,
            ImportSegregationReport.flt_doc_arrival.asc(),
        )
    )
    rows = result.all()
 
    if not rows:
        print(f"[IMP_SEGRATION] no data for {month_prev}+{month_current}")
        return {"source": "IMP_SEGRATION", "processed": 0}
 
    grouped = {}
    for row in rows:
        awb = row.awb_no
        if not awb:
            continue
        if awb not in grouped:
            grouped[awb] = {
                "awb_no"      : awb,
                "origin"      : row.org,
                "destination" : row.dest,
                "nog"         : row.nog,
                "shc"         : row.billing_shc,
                "combo_dt"    : row.flt_doc_arrival,
                "pcs"         : row.pcs or 0,
                "gross_wt"    : float(row.gross_wgt or 0),
                "chg_wt"      : float(row.chg_wgt or 0),
            }
        else:
            grouped[awb]["pcs"]      += row.pcs or 0
            grouped[awb]["gross_wt"] += float(row.gross_wgt or 0)
            grouped[awb]["chg_wt"]   += float(row.chg_wgt or 0)
 
    print(f"[IMP_SEGRATION] months={month_prev}+{month_current}  rows={len(rows)}  unique_awb={len(grouped)}")
 
    now, payload = get_utc_now(), []
    for item in grouped.values():
        car_msg_date, car_msg_time = _utc_to_ist_date_time(item["combo_dt"])
        payload.append({
            "awb_no"                     : item["awb_no"],
            "origin"                     : item["origin"],
            "destination"                : item["destination"],
            "pcs"                        : item["pcs"],
            "gross_wt"                   : item["gross_wt"],
            "chg_wt"                     : item["chg_wt"],
            "nog"                        : item["nog"],
            "shc"                        : item["shc"],
            "xray_type"                  : None,
            "car_message_datetime_combo" : item["combo_dt"],
            "car_msg_date"               : car_msg_date,
            "car_msg_time"               : car_msg_time,
            "source"                     : "IMP_SEGRATION",
            "uploaded_by"                : emp_id,
            "created_at"                 : now,
            "updated_at"                 : now,
        })
 
    for i in range(0, len(payload), 300):
        stmt = insert(ExportCarMessageAwbMaster).values(payload[i:i+300])
        stmt = stmt.on_conflict_do_update(
            constraint="uq_awb_car_msg",
            set_={
                "pcs"        : stmt.excluded.pcs,
                "gross_wt"   : stmt.excluded.gross_wt,
                "chg_wt"     : stmt.excluded.chg_wt,
                "nog"        : stmt.excluded.nog,
                "shc"        : stmt.excluded.shc,
                "updated_at" : stmt.excluded.updated_at,
                 "source"     : func.coalesce(
            func.nullif(func.trim(ExportCarMessageAwbMaster.source), ''),
            stmt.excluded.source,
        ),
            },
        )
        await db.execute(stmt)
 
    await db.flush()
    return {"source": "IMP_SEGRATION", "processed": len(grouped)}
 
 
# async def _process_transhipment(db, month_current, month_prev, emp_id):
#     result = await db.execute(
#         select(
#             ExportTranshipmentReport.awb_no,
#             ExportTranshipmentReport.org,
#             ExportTranshipmentReport.des,
#             ExportTranshipmentReport.rec_pcs,
#             ExportTranshipmentReport.received_wgt,
#             ExportTranshipmentReport.received_chg_wgt,
#             ExportTranshipmentReport.billing_shc,
#             ExportTranshipmentReport.doc_datetime,
#         )
#         .where(or_(
#             ExportTranshipmentReport.month_uploaded == month_current,
#             ExportTranshipmentReport.month_uploaded == month_prev,
#         ))
#         .order_by(
#             ExportTranshipmentReport.awb_no,
#             ExportTranshipmentReport.doc_datetime.asc(),
#         )
#     )
#     rows = result.all()
 
#     if not rows:
#         print(f"[EXP_TRANSHIP] no data for {month_prev}+{month_current}")
#         return {"source": "EXP_TRANSHIP", "processed": 0}
 
#     grouped = {}
#     for row in rows:
#         awb = row.awb_no
#         if not awb:
#             continue
#         if awb not in grouped:
#             grouped[awb] = {
#                 "awb_no"      : awb,
#                 "origin"      : row.org,
#                 "destination" : row.des,
#                 "shc"         : row.billing_shc,
#                 "combo_dt"    : row.doc_datetime,
#                 "pcs"         : row.rec_pcs or 0,
#                 "gross_wt"    : float(row.received_wgt or 0),
#                 "chg_wt"      : float(row.received_chg_wgt or 0),
#             }
#         else:
#             grouped[awb]["pcs"]      += row.rec_pcs or 0
#             grouped[awb]["gross_wt"] += float(row.received_wgt or 0)
#             grouped[awb]["chg_wt"]   += float(row.received_chg_wgt or 0)
 
#     print(f"[EXP_TRANSHIP] months={month_prev}+{month_current}  rows={len(rows)}  unique_awb={len(grouped)}")
 
#     now, payload = get_utc_now(), []
#     for item in grouped.values():
#         car_msg_date, car_msg_time = _utc_to_ist_date_time(item["combo_dt"])
#         payload.append({
#             "awb_no"                     : item["awb_no"],
#             "origin"                     : item["origin"],
#             "destination"                : item["destination"],
#             "pcs"                        : item["pcs"],
#             "gross_wt"                   : item["gross_wt"],
#             "chg_wt"                     : item["chg_wt"],
#             "nog"                        : None,
#             "shc"                        : item["shc"],
#             "xray_type"                  : None,
#             "car_message_datetime_combo" : item["combo_dt"],
#             "car_msg_date"               : car_msg_date,
#             "car_msg_time"               : car_msg_time,
#             "source"                     : "EXP_TRANSHIP",
#             "uploaded_by"                : emp_id,
#             "created_at"                 : now,
#             "updated_at"                 : now,
#         })
 
#     for i in range(0, len(payload), 300):
#         stmt = insert(ExportCarMessageAwbMaster).values(payload[i:i+300])
#         stmt = stmt.on_conflict_do_update(
#             constraint="uq_awb_car_msg",
#             set_={
#                 "pcs"        : stmt.excluded.pcs,
#                 "gross_wt"   : stmt.excluded.gross_wt,
#                 "chg_wt"     : stmt.excluded.chg_wt,
#                 "shc"        : stmt.excluded.shc,
#                 "updated_at" : stmt.excluded.updated_at,
#             },
#         )
#         await db.execute(stmt)
 
#     await db.flush()
#     return {"source": "EXP_TRANSHIP", "processed": len(grouped)}
 
DEBUG_AWB = "00652959373" 
async def _process_transhipment(db, month_current, month_prev, emp_id):
    result = await db.execute(
        select(
            ExportTranshipmentReport.awb_no,
            ExportTranshipmentReport.org,
            ExportTranshipmentReport.des,
            ExportTranshipmentReport.rec_pcs,
            ExportTranshipmentReport.received_wgt,
            ExportTranshipmentReport.received_chg_wgt,
            ExportTranshipmentReport.billing_shc,
            ExportTranshipmentReport.doc_datetime,
        )
        .where(or_(
            ExportTranshipmentReport.month_uploaded == month_current,
            ExportTranshipmentReport.month_uploaded == month_prev,
        ))
        .order_by(
            ExportTranshipmentReport.awb_no,
            ExportTranshipmentReport.doc_datetime.asc(),
        )
    )
    rows = result.all()
 
    if not rows:
        print(f"[EXP_TRANSHIP] no data for {month_prev}+{month_current}")
        return {"source": "EXP_TRANSHIP", "processed": 0}
 
    # ── DEBUG: print ALL raw rows for the target AWB from DB ─────────────────
    if DEBUG_AWB:
        debug_rows = [r for r in rows if r.awb_no == DEBUG_AWB]
        print(f"\n{'='*60}")
        print(f"[DEBUG] AWB {DEBUG_AWB} — raw rows from buffer table ({len(debug_rows)} rows):")
        for i, r in enumerate(debug_rows):
            dt = r.doc_datetime
            tzinfo = dt.tzinfo if dt else "None"
            ist_str = dt.astimezone(_IST).strftime("%Y-%m-%d %H:%M:%S %Z") if dt and dt.tzinfo else (
                _IST.localize(dt).strftime("%Y-%m-%d %H:%M:%S %Z") if dt else "NULL"
            )
            print(f"  row[{i}]  doc_datetime raw = {dt}  |  tzinfo = {tzinfo}  |  IST = {ist_str}")
        if not debug_rows:
            print(f"  [DEBUG] AWB {DEBUG_AWB} NOT FOUND in buffer for months {month_prev}+{month_current}")
        print(f"{'='*60}\n")
 
    # ── Group by AWB ──────────────────────────────────────────────────────────
    grouped = {}
    for row in rows:
        awb = row.awb_no
        if not awb:
            continue
        if awb not in grouped:
            grouped[awb] = {
                "awb_no"      : awb,
                "origin"      : row.org,
                "destination" : row.des,
                "shc"         : row.billing_shc,
                "combo_dt"    : row.doc_datetime,
                "pcs"         : row.rec_pcs or 0,
                "gross_wt"    : float(row.received_wgt or 0),
                "chg_wt"      : float(row.received_chg_wgt or 0),
            }
 
            # ── DEBUG: first-row selection ────────────────────────────────────
            if DEBUG_AWB and awb == DEBUG_AWB:
                print(f"[DEBUG] AWB {DEBUG_AWB} — FIRST ROW selected as combo_dt:")
                print(f"  combo_dt raw     = {row.doc_datetime}")
                print(f"  combo_dt tzinfo  = {row.doc_datetime.tzinfo if row.doc_datetime else 'None'}")
 
        else:
            grouped[awb]["pcs"]      += row.rec_pcs or 0
            grouped[awb]["gross_wt"] += float(row.received_wgt or 0)
            grouped[awb]["chg_wt"]   += float(row.received_chg_wgt or 0)
 
    print(f"[EXP_TRANSHIP] months={month_prev}+{month_current}  rows={len(rows)}  unique_awb={len(grouped)}")
 
    # ── Build payload ─────────────────────────────────────────────────────────
    now, payload = get_utc_now(), []
    for item in grouped.values():
        car_msg_date, car_msg_time = _utc_to_ist_date_time(item["combo_dt"])
 
        # ── DEBUG: full conversion trace for target AWB ───────────────────────
        if DEBUG_AWB and item["awb_no"] == DEBUG_AWB:
            combo = item["combo_dt"]
            print(f"\n[DEBUG] AWB {DEBUG_AWB} — _utc_to_ist_date_time trace:")
            print(f"  input combo_dt           = {combo}")
            print(f"  input tzinfo             = {combo.tzinfo if combo else 'None'}")
            if combo:
                if combo.tzinfo is None:
                    import pytz as _pytz
                    localized = _pytz.utc.localize(combo if not isinstance(combo, type(None)) else combo)
                    print(f"  [WARN] no tzinfo → localized as UTC = {localized}")
                    ist = localized.astimezone(_IST)
                else:
                    ist = combo.astimezone(_IST)
                    print(f"  tzinfo present → astimezone IST = {ist}")
                print(f"  car_msg_date             = {car_msg_date}")
                print(f"  car_msg_time             = {car_msg_time}")
 
            # Also check what's CURRENTLY in car_message for this AWB
            from sqlalchemy import text
            existing = await db.execute(
                text("""
                    SELECT car_message_datetime_combo,
                           car_msg_date,
                           car_msg_time,
                           source,
                           updated_at
                    FROM export_car_message_awb_master
                    WHERE awb_no = :awb
                """),
                {"awb": DEBUG_AWB}
            )
            existing_row = existing.fetchone()
            if existing_row:
                print(f"\n  [DEBUG] EXISTING car_message row for this AWB:")
                print(f"    car_message_datetime_combo = {existing_row[0]}")
                print(f"    car_msg_date               = {existing_row[1]}")
                print(f"    car_msg_time               = {existing_row[2]}")
                print(f"    source                     = {existing_row[3]}")
                print(f"    updated_at                 = {existing_row[4]}")
                print(f"  → ON CONFLICT will keep existing datetime, only update pcs/weights/shc")
            else:
                print(f"\n  [DEBUG] NO existing car_message row → fresh INSERT")
            print()
 
        payload.append({
            "awb_no"                     : item["awb_no"],
            "origin"                     : item["origin"],
            "destination"                : item["destination"],
            "pcs"                        : item["pcs"],
            "gross_wt"                   : item["gross_wt"],
            "chg_wt"                     : item["chg_wt"],
            "nog"                        : None,
            "shc"                        : item["shc"],
            "xray_type"                  : None,
            "car_message_datetime_combo" : item["combo_dt"],
            "car_msg_date"               : car_msg_date,
            "car_msg_time"               : car_msg_time,
            "source"                     : "EXP_TRANSHIP",
            "uploaded_by"                : emp_id,
            "created_at"                 : now,
            "updated_at"                 : now,
        })
 
    # ── Upsert ────────────────────────────────────────────────────────────────
    for i in range(0, len(payload), 300):
        stmt = insert(ExportCarMessageAwbMaster).values(payload[i:i+300])
        stmt = stmt.on_conflict_do_update(
            constraint="uq_awb_car_msg",
            set_={
                "pcs"        : stmt.excluded.pcs,
                "gross_wt"   : stmt.excluded.gross_wt,
                "chg_wt"     : stmt.excluded.chg_wt,
                "shc"        : stmt.excluded.shc,
                "updated_at" : stmt.excluded.updated_at,
                  "source"     : func.coalesce(
                    func.nullif(func.trim(ExportCarMessageAwbMaster.source), ''),
                    stmt.excluded.source,
                ),
                # ── NOT updated (by design — first datetime never changes):
                # "car_message_datetime_combo"
                # "car_msg_date"
                # "car_msg_time"
            },
        )
        await db.execute(stmt)
 
    await db.flush()
    return {"source": "EXP_TRANSHIP", "processed": len(grouped)}
 
 
async def process_seg_tranship_to_car_message_master(
    db: AsyncSession,
    month_uploaded: str,
    emp_id: str,
) -> dict:
    """
    Fetch current + previous month data for both sources in 2 queries total,
    sum repeated AWBs across both months, upsert into car message master.
    """
    month_prev      = _prev_month(month_uploaded)
    seg_result      = await _process_segregation(db, month_uploaded, month_prev, emp_id)
    tranship_result = await _process_transhipment(db, month_uploaded, month_prev, emp_id)
 
    return {
        "months_processed"   : [month_prev, month_uploaded],
        "seg_processed"      : seg_result["processed"],
        "tranship_processed" : tranship_result["processed"],
    }