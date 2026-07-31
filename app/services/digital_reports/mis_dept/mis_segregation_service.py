import io
import math
import datetime as dt
import pandas as pd
import numpy as np
from sqlalchemy import insert, delete, select
from sqlalchemy.ext.asyncio import AsyncSession

# Models
from app.db.models.digital_reports.mis_dept.mis_nog_list import DigitalMisNogMaster
from app.db.models.digital_reports.mis_dept.mis_segregation_cleaned import DigitalReportsMisSegregationCleaned
from app.db.models.digital_reports.mis_dept.mis_segregation import DigitalReportsMisSegregation
from app.db.models.digital_reports.mis_dept.mis_domestic_code import DigitalMisDomesticCode
from app.db.models.digital_reports.mis_dept.mis_international_code import DigitalMisInternationalCode
from app.db.models.digital_reports.mis_dept.mis_flt_country_cont import DigitalMisFltCountryContinent
from app.db.models.digital_reports.mis_dept.mis_flt_schedule_cleaning import DigitalReportsFlightScheduleImport
from sqlalchemy.dialects.postgresql import insert as pg_insert
# Utilities & Cleaners
from app.db.models.digital_reports.mis_dept.mis_shc_code import DigitalMisShcMaster
from app.utils.digital_reports.mis_dept.mis_segregation_cleaning import clean_segregation_bytes, validate_dates

BATCH_SIZE = 500


# ===================== HELPER CLEANING FUNCTIONS =====================

def _clean_value(v):
    """Safely normalizes NaN, NaT, and Pandas Timestamps for database insertion."""
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


def _safe_egm_igm_no(v):
    """Safely casts egm_igm_no values to clean integer or None."""
    v = _clean_value(v)
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _clean_flight_number(flt_no: str | None) -> str:
    """Normalizes flight number for accurate matching."""
    if flt_no is None or pd.isna(flt_no):
        return ""
    return str(flt_no).strip().upper().replace(" ", "").replace("-", "")


def _normalize_date_str(val) -> str | None:
    """Normalizes date values into YYYY-MM-DD string format."""
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (dt.datetime, dt.date, pd.Timestamp)):
        return val.strftime("%Y-%m-%d")
    val_str = str(val).strip()
    return val_str[:10] if len(val_str) >= 10 else None


# ===================== CODE MAPS & LOOKUPS =======================

async def _get_code_maps(session: AsyncSession):
    """Fetches international and domestic code mappings including country and continent."""
    intl_result = await session.execute(
        select(
            DigitalMisInternationalCode.code,
            DigitalMisInternationalCode.country,
            DigitalMisInternationalCode.continent
        )
    )
    intl_map = {r[0].strip().upper(): (r[1], r[2]) for r in intl_result.fetchall() if r[0]}

    dom_result = await session.execute(select(DigitalMisDomesticCode.code))
    dom_map = {row[0].strip().upper(): ("India", "Domestic") for row in dom_result.fetchall() if row[0]}

    return intl_map, dom_map


async def _get_flight_schedule_map(session: AsyncSession) -> dict[tuple[str, str], str]:
    """Fetches Flight Schedule mappings: (flt_no, report_to) -> origin."""
    stmt = select(
        DigitalReportsFlightScheduleImport.flt_no,
        DigitalReportsFlightScheduleImport.report_to,
        DigitalReportsFlightScheduleImport.origin
    )
    result = await session.execute(stmt)
    
    schedule_map = {}
    for r in result.fetchall():
        flt_no = _clean_flight_number(r[0])
        report_to_str = _normalize_date_str(r[1])
        origin = str(r[2]).strip().upper() if r[2] else None
        
        if flt_no and report_to_str and origin:
            schedule_map[(flt_no, report_to_str)] = origin
            
    return schedule_map


async def _get_flt_country_continent_map(session: AsyncSession) -> dict[str, tuple[str, str]]:
    """Fetches mis_flt_country_cont mappings: dest_code -> (country, continent)."""
    stmt = select(
        DigitalMisFltCountryContinent.dest,
        DigitalMisFltCountryContinent.country,
        DigitalMisFltCountryContinent.continent
    )
    result = await session.execute(stmt)
    
    cont_map = {}
    for r in result.fetchall():
        dest_code = str(r[0]).strip().upper() if r[0] else ""
        country = r[1]
        continent = r[2]
        if dest_code:
            cont_map[dest_code] = (country, continent)
            
    return cont_map


def _calculate_line_flight_freighter(row: pd.Series) -> str | None:
    flt_no = str(row.get("flt_no", "")).strip().upper() if pd.notna(row.get("flt_no")) else ""
    flight_status = str(row.get("flight_status", "")).strip().upper() if pd.notna(row.get("flight_status")) else ""

    # 1. First character 'P' Check -> PO MAIL
    if flt_no.startswith("P"):
        return "PO MAIL"

    # 2. Check flight_status column value
    if "FREIGHTER" in flight_status:
        return "Freighter"
    elif "PASSENGER" in flight_status:
        return "Line Flight"

    return None


def _calculate_country_continent(row: pd.Series, intl_map: dict, dom_map: dict):
    """Resolves country and continent mapping based on the origin code."""
    origin = str(row.get("origin", "")).strip().upper() if pd.notna(row.get("origin")) else ""
    if origin in intl_map:
        return intl_map[origin]
    if origin in dom_map:
        return dom_map[origin]
    return (None, None)


def _calculate_flt_origin_details(
    row: pd.Series, 
    schedule_map: dict[tuple[str, str], str], 
    flt_cont_map: dict[str, tuple[str, str]]
) -> tuple[str | None, str | None, str | None]:
    """
    1. Matches segregation row (flt_no + flt_com_date) with Flight Schedule (flt_no + report_to) to get flt_origin.
    2. Maps flt_origin with mis_flt_country_cont (dest_code) to get country and continent.
    """
    flt_no = _clean_flight_number(row.get("flt_no"))
    flt_com_date_str = _normalize_date_str(row.get("flt_com_date"))

    if not flt_no or not flt_com_date_str:
        return (None, None, None)

    lookup_key = (flt_no, flt_com_date_str)
    
    # Match flt_no & flt_com_date in Flight Schedule map
    flt_origin = schedule_map.get(lookup_key)
    if not flt_origin:
        return (None, None, None)

    # Match flt_origin with country & continent map
    flt_org_country, flt_org_continents = flt_cont_map.get(flt_origin, (None, None))

    return (flt_origin, flt_org_country, flt_org_continents)

# ===================== SHC MASTER =====================

SHC_SHEET_NAME = 0
SHC_COLUMN_MAP = {
    "shc": "shc",
    "final shc": "final_shc",
    "final_shc": "final_shc",
}
async def seed_shc_master(file_bytes: bytes, session: AsyncSession) -> dict:
    """Read SHC master xlsx and insert EVERY row without dropping duplicates."""
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=SHC_SHEET_NAME)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df.rename(columns=SHC_COLUMN_MAP, inplace=True)

    missing = {"shc", "final_shc"} - set(df.columns)
    if missing:
        raise ValueError(f"Uploaded file is missing expected column(s): {missing}")

    # (Optional) Clean null / NaN rows
    df = df.dropna(subset=["shc", "final_shc"])

    # Prepare bulk insert objects
    objects_to_insert = []
    for _, row in df.iterrows():
        shc_code = str(row["shc"]).strip().upper()
        final_shc = str(row["final_shc"]).strip().upper()
        
        # Check if empty string or 'NAN'
        if not shc_code or shc_code == "NAN" or not final_shc or final_shc == "NAN":
            continue

        objects_to_insert.append(
            DigitalMisShcMaster(shc=shc_code, final_shc=final_shc)
        )

    # Simple Bulk Insert (Inserts ALL rows including duplicates)
    session.add_all(objects_to_insert)

    await session.flush()
    return {"total_rows": len(df), "processed": len(objects_to_insert)}
# ===================== SHC ENRICHMENT HELPERS =====================

async def _get_shc_map(session: AsyncSession) -> dict[str, str]:
    """Return {shc: final_shc} map from DB."""
    result = await session.execute(
        select(DigitalMisShcMaster.shc, DigitalMisShcMaster.final_shc)
    )
    return {r[0].strip().upper(): r[1] for r in result.fetchall() if r[0]}


def _calculate_final_shc(row: pd.Series, shc_map: dict[str, str]) -> str | None:
    """Calculates/looks up the final_shc based on input shc."""
    shc_val = str(row.get("shc", "")).strip().upper() if pd.notna(row.get("shc")) else ""
    if not shc_val:
        return None
    return shc_map.get(shc_val)


async def list_shc_masters(
    session: AsyncSession,
    search: str | None = None,
) -> list[dict]:
    """Return all SHC master rows, optionally filtered by shc/final_shc."""
    stmt = select(DigitalMisShcMaster)
    if search:
        like = f"%{search.strip().upper()}%"
        stmt = stmt.where(
            (DigitalMisShcMaster.shc.ilike(like))
            | (DigitalMisShcMaster.final_shc.ilike(like))
        )
    stmt = stmt.order_by(DigitalMisShcMaster.shc)

    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        {"id": r.id, "shc": r.shc, "final_shc": r.final_shc}
        for r in rows
    ]

# ===================== BUSINESS LOGIC & TP TYPE =====================

def _calculate_tp_type(row: pd.Series, intl_codes: set[str], dom_codes: set[str]) -> str:
    origin = str(row.get("origin", "")).strip().upper() if pd.notna(row.get("origin")) else ""
    dest = str(row.get("dest", "")).strip().upper() if pd.notna(row.get("dest")) else ""

    if not origin or not dest:
        return "NOT FOUND"

    # 1. Check EXPORT (Origin is DEL)
    if origin == "DEL":
        return "EXPORT"

    # 2. Check IMPORT (Destination is DEL)
    if dest == "DEL":
        return "IMPORT"

    # 3. Check International / Domestic Combinations
    is_origin_intl = origin in intl_codes
    is_dest_intl = dest in intl_codes
    is_origin_dom = origin in dom_codes
    is_dest_dom = dest in dom_codes

    if is_origin_intl and is_dest_intl:
        return "I-I"
    if is_origin_dom and is_dest_intl:
        return "D-I"
    if is_origin_intl and is_dest_dom:
        return "I-D"
    if is_origin_dom and is_dest_dom:
        return "D-D"

    return "NOT FOUND"


def apply_business_logic(
    df: pd.DataFrame, 
    intl_map: dict, 
    dom_map: dict,
    schedule_map: dict,
    flt_cont_map: dict,
    shc_map: dict | None = None
) -> pd.DataFrame:
    """Applies weight discrepancy, metric ton conversion, month-year, TP Type, origin country/continent, Line Flight/Freighter, and Flight Origin mapping."""
    processed_df = df.copy()

    intl_codes = set(intl_map.keys())
    dom_codes = set(dom_map.keys())

    # 1. Weight Difference & Discrepancy Calculation
    if "manifest_wgt" in processed_df.columns and "seg_wgt" in processed_df.columns:
        m_wgt = pd.to_numeric(processed_df["manifest_wgt"], errors="coerce").fillna(0)
        s_wgt = pd.to_numeric(processed_df["seg_wgt"], errors="coerce").fillna(0)

        processed_df["weight_difference"] = m_wgt - s_wgt
        processed_df["discrepancy_status"] = processed_df["weight_difference"].apply(
            lambda x: "MISMATCH" if abs(x) > 0.001 else "MATCH"
        )

    # 2. grs_wgt_mt calculation (grs_wgt / 1000)
    if "grs_wgt" in processed_df.columns:
        g_wgt = pd.to_numeric(processed_df["grs_wgt"], errors="coerce")
        processed_df["grs_wgt_mt"] = np.round(g_wgt / 1000.0, 1)

    # 3. month_year calculation based on flt_com_date
    if "flt_com_date" in processed_df.columns:
        com_dates = pd.to_datetime(processed_df["flt_com_date"], errors="coerce")
        processed_df["month_year"] = com_dates.dt.strftime("%b-%Y")

    # 4. tp_type calculation
    processed_df["tp_type"] = processed_df.apply(
        _calculate_tp_type, axis=1, args=(intl_codes, dom_codes)
    )

    # 5. awb_org_country and awb_org_continents calculation
    processed_df[["awb_org_country", "awb_org_continents"]] = processed_df.apply(
        lambda r: pd.Series(_calculate_country_continent(r, intl_map, dom_map)), axis=1
    )

    # 6. line_flight_freighter calculation
    processed_df["line_flight_freighter"] = processed_df.apply(
        _calculate_line_flight_freighter, axis=1
    )

    # 7. ADDED: flt_origin, flt_org_country, and flt_org_continents calculation
    processed_df[["flt_origin", "flt_org_country", "flt_org_continents"]] = processed_df.apply(
        lambda r: pd.Series(_calculate_flt_origin_details(r, schedule_map, flt_cont_map)), axis=1
    )
    if shc_map:
        processed_df["final_shc"] = processed_df.apply(
            lambda r: _calculate_final_shc(r, shc_map), axis=1
        )

    return processed_df


# ===================== DYNAMIC DB RECORD CONVERTER =====================

def _df_to_records(
    df: pd.DataFrame, 
    model_cls: type, 
    report_date: dt.date, 
    uploaded_by: str | None = None
) -> list[dict]:
    """Dynamically parses and sanitizes DataFrames to model record dictionaries."""
    valid_cols = set(model_cls.__table__.columns.keys())
    records = []

    for row in df.to_dict(orient="records"):
        rec = {k: _clean_value(v) for k, v in row.items() if k in valid_cols}

        if "egm_igm_no" in valid_cols:
            rec["egm_igm_no"] = _safe_egm_igm_no(row.get("egm_igm_no"))

        rec["report_date"] = report_date
        rec["uploaded_by"] = uploaded_by
        records.append(rec)

    return records

# ===================== NOG MASTER HELPERS =====================

async def _get_nog_map(session: AsyncSession) -> dict[str, dict[str, str]]:
    """Return {nog: {'nog_1': ..., 'nog_2': ...}} dictionary from DB."""
    result = await session.execute(
        select(DigitalMisNogMaster.nog, DigitalMisNogMaster.nog_1, DigitalMisNogMaster.nog_2)
    )
    nog_map = {}
    for r in result.fetchall():
        if r[0]:
            key = r[0].strip().upper()
            nog_map[key] = {
                "nog_1": r[1].strip() if r[1] else "",
                "nog_2": r[2].strip() if r[2] else "",
            }
    return nog_map


def _calculate_nog_mapping(row: pd.Series, nog_map: dict[str, dict[str, str]]) -> tuple[str | None, str | None]:
    """Look up nog_1 and nog_2 based on input NOG."""
    nog_val = str(row.get("nog", "")).strip().upper() if pd.notna(row.get("nog")) else ""
    if not nog_val or nog_val not in nog_map:
        return None, None
    
    mapping = nog_map[nog_val]
    return mapping.get("nog_1"), mapping.get("nog_2")

# ===================== MAIN PIPELINE SERVICE =====================
async def process_clean_and_apply_logic(
    session: AsyncSession, 
    file_bytes: bytes, 
    filename: str,
    report_date: dt.date, 
    uploaded_by: str | None = None
) -> dict:
    """Main ingestion pipeline for Segregation reports."""

    # 1. Parse & Clean Excel/CSV File
    result = clean_segregation_bytes(file_bytes, filename)
    validate_dates(result, report_date)
    
    df_cleaned = result.seg_df

    # 2. Fetch Master Lookup Maps (shc_map yahan fetch ho raha h)
    intl_map, dom_map = await _get_code_maps(session)
    schedule_map = await _get_flight_schedule_map(session)
    flt_cont_map = await _get_flt_country_continent_map(session)
    nog_map = await _get_nog_map(session)
    shc_map = await _get_shc_map(session)  # <--- CHANGE 1: DB se existing SHC map liya

    # 3. Apply Flight Origin & NOG Mapping on Cleaned Staging DataFrame
    df_cleaned[["flt_origin", "flt_org_country", "flt_org_continents"]] = df_cleaned.apply(
        lambda r: pd.Series(_calculate_flt_origin_details(r, schedule_map, flt_cont_map)), axis=1
    )

    nog_tuples = df_cleaned.apply(lambda r: _calculate_nog_mapping(r, nog_map), axis=1)
    df_cleaned["nog_1"] = [t[0] for t in nog_tuples]
    df_cleaned["nog_2"] = [t[1] for t in nog_tuples]

    # 4. Save Cleaned Staging Records
    cleaned_records = _df_to_records(df_cleaned, DigitalReportsMisSegregationCleaned, report_date, uploaded_by)
    
    await session.execute(
        delete(DigitalReportsMisSegregationCleaned).where(DigitalReportsMisSegregationCleaned.report_date == report_date)
    )
    for i in range(0, len(cleaned_records), BATCH_SIZE):
        chunk = cleaned_records[i:i + BATCH_SIZE]
        await session.execute(insert(DigitalReportsMisSegregationCleaned), chunk)

    # 5. Apply Business Logic for Processed Data (shc_map yahan pass kar diya)
    df_processed = apply_business_logic(
        df_cleaned, 
        intl_map, 
        dom_map, 
        schedule_map, 
        flt_cont_map, 
        shc_map=shc_map  # <--- CHANGE 2: shc_map pass kiya
    )

    # 6. Save Processed Main Records
    processed_records = _df_to_records(df_processed, DigitalReportsMisSegregation, report_date, uploaded_by)
    
    await session.execute(
        delete(DigitalReportsMisSegregation).where(DigitalReportsMisSegregation.report_date == report_date)
    )
    for i in range(0, len(processed_records), BATCH_SIZE):
        chunk = processed_records[i:i + BATCH_SIZE]
        await session.execute(insert(DigitalReportsMisSegregation), chunk)

    # Flush changes
    await session.flush()

    return {
        "status": "success",
        "cleaned_inserted": len(cleaned_records),
        "processed_inserted": len(processed_records),
        "total_parsed": result.total_parsed
    }