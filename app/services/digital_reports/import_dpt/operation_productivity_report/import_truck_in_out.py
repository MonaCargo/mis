

"""
app/services/digitalReport/imp_truck_in_out_service.py
"""

import io
import traceback
from math import ceil
from typing import Any

import numpy as np
import pandas as pd
from fastapi import UploadFile
from sqlalchemy import func, select
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.digital_reports.import_dept.import_truck_in_out import DigitalReportImportTruckInOut
from app.utils.digital_reports.import_dept.operation_productivity_report.imp_truck_in_out import clean_and_parse_truck_in_out_report

BATCH_SIZE = 600
REQUIRED_FIELDS = ["gp_no", "date", "pcs", "awb_no"]


# ─────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────

def _sanitize_record(record: dict) -> dict:
    """
    Convert pandas/numpy types → native Python so asyncpg can bind them.
    pandas Timestamp → datetime, numpy.int64 → int, NaT/NaN → None
    """
    clean = {}
    for k, v in record.items():
        if isinstance(v, pd.Timestamp):
            clean[k] = None if pd.isnull(v) else v.to_pydatetime()
        elif isinstance(v, np.integer):
            clean[k] = int(v)
        elif isinstance(v, np.floating):
            clean[k] = None if np.isnan(v) else float(v)
        elif isinstance(v, float) and np.isnan(v):
            clean[k] = None
        elif v is pd.NaT:
            clean[k] = None
        else:
            clean[k] = v
    return clean


def _validate_record(record: dict, row_num: int) -> str | None:
    """Returns error string if a required field is missing, else None."""
    for field in REQUIRED_FIELDS:
        if record.get(field) is None:
            return (
                f"Row {row_num}: '{field}' is required but missing "
                f"(GP No: {record.get('gp_no', 'unknown')})"
            )
    return None


def _error_response(filename: str, message: str) -> dict[str, Any]:
    return {
        "filename":      filename,
        "records_found": 0,
        "inserted":      0,
        "skipped":       0,
        "rejected":      0,
        "total_batches": 0,
        "status":        "failed",
        "errors":        [message],
    }


# ─────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────

class DigitalReportImpTruckInOutService:

    @staticmethod
    async def upload(
        file: UploadFile,
        db: AsyncSession,
    ) -> dict[str, Any]:

        filename = file.filename or "unknown"
        errors: list[str] = []

        print(f"[ImpTruckInOut] upload() called — file: {filename}")

        # ── 1. Detect file type ────────────────────────────────────────────
        lower = filename.lower()
        if lower.endswith((".xlsx", ".xls")):
            file_type = "excel"
        elif lower.endswith(".csv"):
            file_type = "csv"
        else:
            return _error_response(
                filename,
                "Unsupported file type. Upload .xlsx, .xls, or .csv."
            )

        # ── 2. Read & clean ────────────────────────────────────────────────
        try:
            content = await file.read()
            file_like = io.BytesIO(content)
            df = clean_and_parse_truck_in_out_report(file_like, file_type=file_type)
        except ValueError as exc:
            return _error_response(filename, str(exc))
        except Exception:
            traceback.print_exc()
            return _error_response(filename, "File parsing failed. Check format and headers.")

        if df.empty:
            return _error_response(filename, "No valid records found after cleaning.")

        records_found = len(df)

        # ── 3. Sanitize types + validate required fields ───────────────────
        valid_records: list[dict] = []
        rejected = 0

        for i, raw in enumerate(df.to_dict(orient="records"), start=1):
            record = _sanitize_record(raw)
            err = _validate_record(record, row_num=i)
            if err:
                errors.append(err)
                rejected += 1
            else:
                valid_records.append(record)

        if not valid_records:
            return {
                "filename":      filename,
                "records_found": records_found,
                "inserted":      0,
                "skipped":       0,
                "rejected":      rejected,
                "total_batches": 0,
                "status":        "failed",
                "errors":        errors,
            }

        # ── 4. Batch insert ────────────────────────────────────────────────
        total_to_insert = len(valid_records)
        total_batches = ceil(total_to_insert / BATCH_SIZE)

        stmt = insert(DigitalReportImportTruckInOut).on_conflict_do_nothing(
            index_elements=["gp_no"]
        )

        try:
            # Count existing rows before insert to calculate actual inserted
            count_before_res = await db.execute(
                select(func.count()).select_from(DigitalReportImportTruckInOut)
            )
            count_before = count_before_res.scalar()

            for batch_num, start in enumerate(range(0, total_to_insert, BATCH_SIZE), 1):
                batch = valid_records[start : start + BATCH_SIZE]
                await db.execute(stmt, batch)
                print(
                    f"[ImpTruckInOut] Batch {batch_num}/{total_batches} — "
                    f"rows {start + 1}–{min(start + BATCH_SIZE, total_to_insert)} done"
                )

            await db.commit()

            # Count after commit to get accurate inserted count
            count_after_res = await db.execute(
                select(func.count()).select_from(DigitalReportImportTruckInOut)
            )
            count_after = count_after_res.scalar()

            inserted = count_after - count_before

        except Exception:
            traceback.print_exc()
            await db.rollback()
            return _error_response(filename, "Database insert failed. Transaction rolled back.")

        skipped = total_to_insert - inserted   # rows skipped due to duplicate gp_no
        status = "success" if not errors else "partial"

        return {
            "filename":      filename,
            "records_found": records_found,
            "inserted":      inserted,
            "skipped":       skipped,
            "rejected":      rejected,
            "total_batches": total_batches,
            "status":        status,
            "errors":        errors,
        }