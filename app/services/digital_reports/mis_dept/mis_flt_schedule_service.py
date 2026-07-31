import math
import datetime as dt
import pandas as pd
from sqlalchemy import insert, delete
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.digital_reports.mis_dept.mis_flt_schedule_cleaning import (
    DigitalReportsFlightScheduleImport,
)
from app.utils.digital_reports.mis_dept.mis_flt_schedule_cleaning import (
    clean_flight_schedule_bytes,
    DateValidationError,
    CleanResult,
)

BATCH_SIZE = 500

CLEANED_COLUMNS: set[str] = set(
    DigitalReportsFlightScheduleImport.__table__.columns.keys()
)


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


def _df_to_records(
    df: pd.DataFrame,
    report_from: dt.date | None,
    report_to: dt.date | None,
    uploaded_by: str | None,
) -> list[dict]:
    records = []
    for row in df.to_dict(orient="records"):
        rec = {k: _clean_value(v) for k, v in row.items() if k in CLEANED_COLUMNS}
        rec["report_from"] = report_from
        rec["report_to"] = report_to
        rec["uploaded_by"] = uploaded_by
        records.append(rec)
    return records


def validate_report_dates(
    report_date: dt.date,
    report_from: dt.date | None,
    report_to: dt.date | None,
) -> None:
    """
    Enforces that:
    1. report_date matches report_to date.
    2. report_from matches (report_date - 1 day) [N-1 rule].
    """
    if not report_from or not report_to:
        raise DateValidationError(
            "Could not extract date range ('FROM DATE' / 'TO DATE') from the file preamble."
        )

    if report_date != report_to:
        raise DateValidationError(
            f"Selected report date ({report_date.strftime('%d-%b-%Y')}) does not match "
            f"file 'TO DATE' ({report_to.strftime('%d-%b-%Y')})."
        )

    expected_from = report_date - dt.timedelta(days=1)
    if report_from != expected_from:
        raise DateValidationError(
            f"File 'FROM DATE' ({report_from.strftime('%d-%b-%Y')}) is invalid. "
            f"Expected N-1 date: {expected_from.strftime('%d-%b-%Y')}."
        )


async def save_flight_schedule_df(
    session: AsyncSession,
    df: pd.DataFrame,
    report_from: dt.date | None,
    report_to: dt.date | None,
    uploaded_by: str | None = None,
) -> int:
    # Delete previous records matching this specific report_from / report_to window
    if report_from and report_to:
        await session.execute(
            delete(DigitalReportsFlightScheduleImport).where(
                DigitalReportsFlightScheduleImport.report_from == report_from,
                DigitalReportsFlightScheduleImport.report_to == report_to,
            )
        )

    if df is None or df.empty:
        await session.flush()
        return 0

    records = _df_to_records(df, report_from, report_to, uploaded_by)

    inserted = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i : i + BATCH_SIZE]
        await session.execute(insert(DigitalReportsFlightScheduleImport), chunk)
        inserted += len(chunk)

    await session.flush()
    return inserted


async def process_and_save_flight_schedule(
    session: AsyncSession,
    file_bytes: bytes,
    filename: str,
    report_date: dt.date,
    uploaded_by: str | None = None,
) -> dict:
    result: CleanResult = clean_flight_schedule_bytes(file_bytes, filename)

    # Enforce report_date == report_to and report_from == N-1 validation
    validate_report_dates(report_date, result.report_from, result.report_to)

    inserted = await save_flight_schedule_df(
        session=session,
        df=result.flights_df,
        report_from=result.report_from,
        report_to=result.report_to,
        uploaded_by=uploaded_by,
    )

    return {
        "total_parsed": result.total_parsed,
        "valid_count": result.valid_count,
        "dropped_count": result.dropped_count,
        "dropped_flights": result.dropped_flights,
        "report_date": report_date,
        "report_from": result.report_from,
        "report_to": result.report_to,
        "inserted": inserted,
    }