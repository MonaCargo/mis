import io
import math
import re
import datetime as dt
import pandas as pd
from sqlalchemy import insert, select, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert as pg_insert

from app.db.models.digital_reports.mis_dept.mis_flt_country_cont import DigitalMisFltCountryContinent
from app.db.models.digital_reports.mis_dept.mis_nog_list import DigitalMisNogMaster
from app.db.models.digital_reports.mis_dept.mis_shc_code import DigitalMisShcMaster
from app.db.models.digital_reports.mis_dept.mis_uplifting_po_cleaned import DigitalReportsMisUpliftingCleaned
from app.db.models.digital_reports.mis_dept.mis_agent_list import DigitalMisPdaAgent
from app.db.models.digital_reports.mis_dept.mis_domestic_code import DigitalMisDomesticCode
from app.db.models.digital_reports.mis_dept.mis_international_code import DigitalMisInternationalCode
from app.db.models.digital_reports.mis_dept.mis_uplifting_po import DigitalReportsMisUpliftingPo
from app.db.models.digital_reports.mis_dept.mis_flight_status_cleaned import DigitalReportsMisFlightStatus

BATCH_SIZE = 500

# Constants required for seed_flt_country_continent
FLT_SHEET_NAME = 0  # Reads first sheet or specify exact sheet name e.g., "Sheet1"
FLT_COLUMN_MAP = {
    "dest": "dest",
    "country": "country",
    "continent": "continent"
}

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


def _safe_trm_number(v):
    v = _clean_value(v)
    if v is None:
        return None
    try:
        return int(str(v).strip())
    except (ValueError, TypeError):
        return None


def _clean_flight_number(flt_no: str | None) -> str:
    if flt_no is None or pd.isna(flt_no):
        return ""
    val = str(flt_no).strip().upper().replace(" ", "").replace("-", "")
    
    # Strip 'P' prefix ONLY if followed by carrier prefix + digits (e.g., PAI0161 -> AI0161)
    match = re.match(r"^P([A-Z0-9]{2}\d+)$", val)
    if match:
        return match.group(1)
        
    return val


def _normalize_date_str(val) -> str | None:
    if val is None or pd.isna(val):
        return None
    if isinstance(val, (dt.datetime, dt.date, pd.Timestamp)):
        return val.strftime("%Y-%m-%d")
    val_str = str(val).strip()
    return val_str[:10] if len(val_str) >= 10 else None


# ===================== TP TYPE & CALCULATIONS =======================

def _calculate_tp_type(row: pd.Series, intl_codes: set[str], dom_codes: set[str]) -> str:
    origin = str(row.get("origin", "")).strip().upper() if pd.notna(row.get("origin")) else ""
    dest = str(row.get("dest", "")).strip().upper() if pd.notna(row.get("dest")) else ""

    if not origin or not dest:
        return "NOT FOUND"

    if origin == "DEL":
        return "EXPORT"

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


def _calculate_month_year_and_year(row: pd.Series):
    fdate = row.get("flt_date")
    if fdate is None or (isinstance(fdate, float) and math.isnan(fdate)):
        return (None, None)
    try:
        return (fdate.strftime("%b-%Y"), fdate.year)
    except AttributeError:
        return (None, None)


def _calculate_grs_wgt_mt(row: pd.Series):
    grs_wgt = row.get("grs_wgt")
    if grs_wgt is None or (isinstance(grs_wgt, float) and math.isnan(grs_wgt)):
        return None
    return grs_wgt / 1000.0


def _df_to_records(df: pd.DataFrame, report_date: dt.date, uploaded_by: str | None) -> list[dict]:
    cols = set(DigitalReportsMisUpliftingPo.__table__.columns.keys())
    records = []
    for row in df.to_dict(orient="records"):
        rec = {k: _clean_value(v) for k, v in row.items() if k in cols}
        if "trm_number" in cols:
            rec["trm_number"] = _safe_trm_number(row.get("trm_number"))
        rec["report_date"] = report_date
        rec["uploaded_by"] = uploaded_by
        records.append(rec)
    return records


# ======================= CODE MAPS & FLIGHT STATUS =======================

async def _get_code_maps(session: AsyncSession):
    intl_result = await session.execute(
        select(DigitalMisInternationalCode.code,
               DigitalMisInternationalCode.country,
               DigitalMisInternationalCode.continent)
    )
    intl_map = {r[0].strip().upper(): (r[1], r[2]) for r in intl_result.fetchall() if r[0]}

    dom_result = await session.execute(select(DigitalMisDomesticCode.code))
    dom_map = {row[0].strip().upper(): ("India", "Domestic") for row in dom_result.fetchall() if row[0]}

    return intl_map, dom_map


def _calculate_dest_country_continent(row: pd.Series, intl_map: dict, dom_map: dict):
    dest = str(row.get("dest", "")).strip().upper() if pd.notna(row.get("dest")) else ""
    if dest in intl_map:
        return intl_map[dest]
    if dest in dom_map:
        return dom_map[dest]
    return (None, None)


async def _get_flight_status_map(session: AsyncSession) -> dict[tuple[str, str], tuple[str, str, str]]:
    stmt = (
        select(
            DigitalReportsMisFlightStatus.flt_no,
            DigitalReportsMisFlightStatus.flt_date,
            DigitalReportsMisFlightStatus.dest.label("flt_dest"),
            DigitalMisFltCountryContinent.country.label("flt_dest_country"),
            DigitalMisFltCountryContinent.continent.label("flt_dest_continent"),
        )
        .outerjoin(
            DigitalMisFltCountryContinent,
            DigitalReportsMisFlightStatus.dest == DigitalMisFltCountryContinent.dest
        )
    )
    result = await session.execute(stmt)
    
    flt_map = {}
    for r in result.fetchall():
        flt_no = _clean_flight_number(r[0])
        flt_date_str = _normalize_date_str(r[1])
        
        if flt_no and flt_date_str:
            flt_map[(flt_no, flt_date_str)] = (r[2], r[3], r[4])
            
    return flt_map


def _calculate_flt_dest_country_continent(row: pd.Series, flt_map: dict):
    flt_no = _clean_flight_number(row.get("flt_no"))
    flt_date_str = _normalize_date_str(row.get("flt_date"))

    if not flt_no or not flt_date_str:
        return (None, None, None)

    lookup_key = (flt_no, flt_date_str)
    if lookup_key in flt_map:
        return flt_map[lookup_key]
    
    return (None, None, None)

# =====================line_flight_column add ===========================

def _calculate_line_flight_freighter(row: pd.Series) -> str | None:
    flt_no = str(row.get("flt_no", "")).strip().upper() if pd.notna(row.get("flt_no")) else ""
    pax_freighter = str(row.get("pax_freighter", "")).strip().upper() if pd.notna(row.get("pax_freighter")) else ""

    # 1. First character 'P' Check -> PO MAIL
    if flt_no.startswith("P"):
        return "PO MAIL"

    # 2. Check pax_freighter column value
    if "FREIGHTER" in pax_freighter :
        return "Freighter"
    elif "PASSENGER" in pax_freighter :
        return "Line Flight"

    return None

# ===================== BACKFILL / RESYNC ENRICHMENT =====================

async def resync_uplift_flt_enrichment(session: AsyncSession, flt_dates: set[dt.date]) -> int:
    
    if not flt_dates:
        return 0

    stmt = select(
        DigitalReportsMisUpliftingPo.id,
        DigitalReportsMisUpliftingPo.flt_no,
        DigitalReportsMisUpliftingPo.flt_date,
    ).where(DigitalReportsMisUpliftingPo.flt_date.in_(flt_dates))
    rows = (await session.execute(stmt)).all()
    if not rows:
        return 0

    flt_status_map = await _get_flight_status_map(session)

    updates = []
    for row_id, flt_no, flt_date in rows:
        flt_dest, flt_dest_country, flt_dest_continent = _calculate_flt_dest_country_continent(
            pd.Series({"flt_no": flt_no, "flt_date": flt_date}), flt_status_map
        )
        updates.append({
            "id": row_id,
            "flt_dest": flt_dest,
            "flt_dest_country": flt_dest_country,
            "flt_dest_continent": flt_dest_continent,
        })

    await session.execute(update(DigitalReportsMisUpliftingPo), updates)
    await session.flush()
    return len(updates)

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
# ===================== MAIN SERVICE FUNCTIONS =====================

async def save_uplift_df(session: AsyncSession, df: pd.DataFrame, report_date: dt.date, uploaded_by: str | None = None) -> int:
    await session.execute(
        delete(DigitalReportsMisUpliftingPo).where(
            DigitalReportsMisUpliftingPo.report_date == report_date
        )
    )

    if df is None or df.empty:
        await session.flush()
        return 0

    intl_map, dom_map = await _get_code_maps(session)
    intl_codes, dom_codes = set(intl_map.keys()), set(dom_map.keys())
    flt_status_map = await _get_flight_status_map(session)
    shc_map = await _get_shc_map(session)
    agent_map = await _get_agent_map(session)
    nog_map = await _get_nog_map(session)

    df["final_shc"] = df.apply(lambda r: _calculate_final_shc(r, shc_map), axis=1)
    nog_tuples = df.apply(lambda r: _calculate_nog_mapping(r, nog_map), axis=1)
    df["nog_1"] = [t[0] for t in nog_tuples]
    df["nog_2"] = [t[1] for t in nog_tuples]
    
    df["agent_name"] = df.apply(lambda r: _calculate_agent_name(r, agent_map), axis=1)
    df["line_flight_freighter"] = df.apply(_calculate_line_flight_freighter, axis=1)
    df["tp_type"] = df.apply(_calculate_tp_type, axis=1, args=(intl_codes, dom_codes))
    df[["awb_dest_country", "awb_dest_continents"]] = df.apply(
        lambda r: pd.Series(_calculate_dest_country_continent(r, intl_map, dom_map)), axis=1
    )
    df[["month_year", "year"]] = df.apply(
        lambda r: pd.Series(_calculate_month_year_and_year(r)), axis=1
    )
    df["grs_wgt_mt"] = df.apply(_calculate_grs_wgt_mt, axis=1)

    df[["flt_dest", "flt_dest_country", "flt_dest_continent"]] = df.apply(
        lambda r: pd.Series(_calculate_flt_dest_country_continent(r, flt_status_map)), axis=1
    )

    records = _df_to_records(df, report_date, uploaded_by)
    inserted = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i:i + BATCH_SIZE]
        await session.execute(insert(DigitalReportsMisUpliftingPo), chunk)
        inserted += len(chunk)

    await session.flush()
    return inserted


async def seed_flt_country_continent(file_bytes: bytes, session: AsyncSession) -> dict:
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=FLT_SHEET_NAME)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns=FLT_COLUMN_MAP)

    missing = {"dest", "country", "continent"} - set(df.columns)
    if missing:
        raise ValueError(f"Uploaded file is missing expected column(s): {missing}")

    processed = 0
    for _, row in df.iterrows():
        dest = str(row["dest"]).strip().upper()
        country = str(row["country"]).strip()
        continent = str(row["continent"]).strip()
        if not dest:
            continue

        stmt = pg_insert(DigitalMisFltCountryContinent).values(
            dest=dest, country=country, continent=continent
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[DigitalMisFltCountryContinent.dest],
            set_={"country": country, "continent": continent},
        )
        await session.execute(stmt)
        processed += 1

    await session.flush()
    return {"total_rows": len(df), "processed": processed}

# ===================== PDA AGENT MASTER =====================

PDA_SHEET_NAME = 0  # "Sheet1"
PDA_COLUMN_MAP = {
    "pda code": "agent_code",
    "pda name": "agent_name",
}


async def seed_pda_agents(file_bytes: bytes, session: AsyncSession) -> dict:
    """Read the PDA master xlsx and upsert every row by agent_code
    (insert new, update agent_name if the code already exists)."""
    df = pd.read_excel(io.BytesIO(file_bytes), sheet_name=PDA_SHEET_NAME)
    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns=PDA_COLUMN_MAP)

    missing = {"agent_code", "agent_name"} - set(df.columns)
    if missing:
        raise ValueError(f"Uploaded file is missing expected column(s): {missing}")

    processed = 0
    for _, row in df.iterrows():
        agent_code = str(row["agent_code"]).strip().upper()
        agent_name = str(row["agent_name"]).strip()
        if not agent_code:
            continue

        stmt = pg_insert(DigitalMisPdaAgent).values(
            agent_code=agent_code, agent_name=agent_name
        )
        stmt = stmt.on_conflict_do_update(
            index_elements=[DigitalMisPdaAgent.agent_code],
            set_={"agent_name": agent_name},
        )
        await session.execute(stmt)
        processed += 1

    await session.flush()
    return {"total_rows": len(df), "processed": processed}

# ===================== AGENT NAME ENRICHMENT =====================

async def _get_agent_map(session: AsyncSession) -> dict[str, str]:
    """Return {agent_code: agent_name} from the PDA agent master table."""
    result = await session.execute(
        select(DigitalMisPdaAgent.agent_code, DigitalMisPdaAgent.agent_name)
    )
    return {r[0].strip().upper(): r[1] for r in result.fetchall() if r[0]}


def _calculate_agent_name(row: pd.Series, agent_map: dict[str, str]) -> str | None:
    agent_code = str(row.get("agent", "")).strip().upper() if pd.notna(row.get("agent")) else ""
    if not agent_code:
        return None
    return agent_map.get(agent_code)

async def list_pda_agents(
    session: AsyncSession,
    search: str | None = None,
) -> list[dict]:
    """Return all PDA agent rows, optionally filtered by code/name."""
    stmt = select(DigitalMisPdaAgent)
    if search:
        like = f"%{search.strip().upper()}%"
        stmt = stmt.where(
            (DigitalMisPdaAgent.agent_code.ilike(like))
            | (DigitalMisPdaAgent.agent_name.ilike(like))
        )
    stmt = stmt.order_by(DigitalMisPdaAgent.agent_code)

    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        {"id": r.id, "agent_code": r.agent_code, "agent_name": r.agent_name}
        for r in rows
    ]


async def list_flt_country_continent(
    session: AsyncSession,
    search: str | None = None,
    continent: str | None = None,
) -> list[dict]:
    stmt = select(DigitalMisFltCountryContinent)
    if search:
        like = f"%{search.strip().upper()}%"
        stmt = stmt.where(
            (DigitalMisFltCountryContinent.dest.ilike(like))
            | (DigitalMisFltCountryContinent.country.ilike(like))
        )
    if continent:
        stmt = stmt.where(DigitalMisFltCountryContinent.continent == continent)
    stmt = stmt.order_by(DigitalMisFltCountryContinent.dest)

    result = await session.execute(stmt)
    rows = result.scalars().all()
    return [
        {
            "id": r.id,
            "dest": r.dest,
            "country": r.country,
            "continent": r.continent,
        }
        for r in rows
    ]


CLEANED_COLUMNS: list[str] = [
    "carrier", "awb_no", "sl_no", "flt_no", "awb_sfx", "origin", "dest",
    "pcs", "grs_wgt", "chg_wgt", "volume_mc", "uld_no", "nog", "shc",
    "chg_shc", "billing_shc", "agent", "shipper_name", "trm_number",
    "pax_freighter", "flt_date", "trm_date",
    "car_date", "car_time", "doc_date", "doc_time",
    "xray_date", "xray_time", "rcs_date", "rcs_time",
    "flight_etd_date", "flight_etd_time",
    "flight_dep_date", "flight_dep_time",
    "uld_release_date", "uld_release_time",
    "car_date_time_combine", "doc_date_time_combine", "xray_date_time_combine",
    "rcs_date_time_combine", "flight_etd_date_time_combine",
    "flight_dep_date_time_combine", "uld_release_date_time_combine",
]


async def save_cleaned_df(session: AsyncSession, df: pd.DataFrame, report_date: dt.date, uploaded_by: str | None = None) -> int:
    await session.execute(
        delete(DigitalReportsMisUpliftingCleaned).where(
            DigitalReportsMisUpliftingCleaned.report_date == report_date
        )
    )

    if df is None or df.empty:
        await session.flush()
        return 0

    records = []
    for row in df.to_dict(orient="records"):
        rec = {k: _clean_value(v) for k, v in row.items() if k in CLEANED_COLUMNS}
        rec["trm_number"] = _safe_trm_number(row.get("trm_number"))
        rec["report_date"] = report_date
        rec["uploaded_by"] = uploaded_by
        records.append(rec)

    inserted = 0
    for i in range(0, len(records), BATCH_SIZE):
        chunk = records[i:i + BATCH_SIZE]
        await session.execute(insert(DigitalReportsMisUpliftingCleaned), chunk)
        inserted += len(chunk)

    await session.flush()
    return inserted