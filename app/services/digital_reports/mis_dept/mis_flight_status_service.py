
import math
import datetime as dt
import pandas as pd
from sqlalchemy import insert, delete
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.digital_reports.mis_dept.mis_uplifting_po_service import resync_uplift_flt_enrichment
from app.db.models.digital_reports.mis_dept.mis_flight_status_cleaned import (
    DigitalReportsMisFlightStatus,
)
from app.utils.digital_reports.mis_dept.mis_flight_status_cleaning import (
    clean_flight_status_bytes,
    validate_dates,
    DateValidationError,
    CleanResult,
)

BATCH_SIZE = 500

CLEANED_COLUMNS: set[str] = set(DigitalReportsMisFlightStatus.__table__.columns.keys())


def _clean_value(v):
    if v is None:
        return None
    if isinstance(v, float) and math.isnan(v):
        return None
    try:
        if v is pd.NaT or pd.isna(v):
            return None
    except (TypeError, ValueError):
        pass
    if isinstance(v, pd.Timestamp):
        return v.to_pydatetime()
    return v

def _df_to_records(df: pd.DataFrame, report_date: dt.date,
                   uploaded_by: str | None) -> list[dict]:
    records = []
    for row in df.to_dict(orient="records"):
        rec = {k: _clean_value(v) for k, v in row.items() if k in CLEANED_COLUMNS}
        rec["report_date"] = report_date
        rec["uploaded_by"] = uploaded_by
        records.append(rec)
    return records


async def save_flight_status_df(
    session: AsyncSession,
    df: pd.DataFrame,
    report_date: dt.date,
    uploaded_by: str | None = None,
) -> int:
    await session.execute(
        delete(DigitalReportsMisFlightStatus).where(
            DigitalReportsMisFlightStatus.report_date == report_date
        )
    )

    if df is None or df.empty:
        await session.flush()
        return 0

    records = _df_to_records(df, report_date, uploaded_by)

    inserted = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i : i + BATCH_SIZE]
        await session.execute(insert(DigitalReportsMisFlightStatus), chunk)
        inserted += len(chunk)

    await session.flush()
    return inserted



async def process_and_save_flight_status(
    session: AsyncSession,
    file_bytes: bytes,
    filename: str,
    report_date: dt.date,
    uploaded_by: str | None = None,
) -> dict:
    result: CleanResult = clean_flight_status_bytes(file_bytes, filename)
    validate_dates(result, report_date)

    inserted = await save_flight_status_df(
        session, result.flights_df, report_date, uploaded_by
    )

    # NEW: backfill enrichment on any existing uplift rows for these flight dates
    flt_dates = set(result.flt_dates) | {report_date}
    resynced = await resync_uplift_flt_enrichment(session, flt_dates)

    return {
        "total_parsed": result.total_parsed,
        "valid_count": result.valid_count,
        "dropped_count": result.dropped_count,
        "dropped_flights": result.dropped_flights,
        "report_date": report_date,
        "inserted": inserted,
        "uplift_rows_resynced": resynced,  
    }