


"""
services/seg_import_service.py

DB service for Segregation Import.
Receives a CleanResult from seg_cleaner and handles all database operations.

This file has zero parsing / cleaning logic — it only:
  1. Accepts CleanResult
  2. Bulk-fetches existing flights and AWBs (2 SELECTs)
  3. Bulk-inserts new flights, then upserts all AWBs in one atomic statement
  4. Commits and returns stats

Total DB round-trips: 3–4, regardless of file size.

AWB upsert strategy (replaces deprecated bulk_update_mappings):
  INSERT ... ON CONFLICT (uq_dr_imp_seg_awb) DO UPDATE SET ... WHERE (pcs or wgt changed)
  · New AWB            → INSERT fires
  · Existing, changed  → UPDATE fires  (pcs IS DISTINCT FROM or gross_wgt IS DISTINCT FROM)
  · Existing, same     → WHERE is false → Postgres no-op, zero disk write
"""

from datetime import datetime, timezone

import pandas as pd
from fastapi import UploadFile
from sqlalchemy import select, tuple_
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.digital_reports.segrigation_report import (
    DigitalReportImportSegFlight,
    DigitalReportImportSegAwb,
)
from app.utils.digital_reports.import_dept.segrigation_report_cleaner import (
    CleanResult,
    clean_seg_file,
)

UTC = timezone.utc

# PostgreSQL allows at most 65,535 bind parameters per statement.
# AWB rows have ~26 columns; flights ~10. Chunk inserts so each statement stays
# well under the limit. 1000 AWB rows ≈ 26k params — safe headroom.
_AWB_CHUNK    = 1000
_FLIGHT_CHUNK = 1000


def _chunked(seq: list, size: int):
    """Yield successive chunks of `size` from list `seq`."""
    for i in range(0, len(seq), size):
        yield seq[i:i + size]


# Columns written on every conflict-update (everything except the PK and created_at)
_AWB_UPDATE_COLS = [
    "origin", "dest",
    "manifest_pcs", "manifest_wgt",
    "seg_pcs", "seg_wgt",
    "pcs", "gross_wgt", "chg_wgt",
    "vol_mc", "no_of_houses",
    "shc", "chg_shc", "billing_shc",
    "nog", "consignee", "egm_igm_no",
    "awd_date", "nfd_date", "rcf_date",
    "do_datetime", "tfd_datetime",
    "updated_at",
]


# ─────────────────────────────────────────────────────────────────────────────
# Row-builder helpers (pure, no I/O)
# ─────────────────────────────────────────────────────────────────────────────

def _nat_to_none(value):
    """
    Convert pandas NaT / NaN to None so the DB driver can encode it.
    Postgres drivers cannot encode pandas NaT as TIMESTAMP → must be None.
    Pass real datetimes / values through unchanged.
    """
    if value is None:
        return None
    # pd.isna handles NaT, NaN, None; guard against arrays
    try:
        if pd.isna(value):
            return None
    except (TypeError, ValueError):
        pass
    return value


def _clean(d: dict) -> dict:
    """Run every value through _nat_to_none — blanket NaT/NaN → None guard."""
    return {k: _nat_to_none(v) for k, v in d.items()}

def _flight_dict(row: pd.Series) -> dict:
    """Build INSERT dict for seg_flights from a flights_df row."""
    return _clean({
        "flight_no":        row["flight_no"],
        "flight_date":      row["flight_date"],
        "origin":           row.get("origin"),
        "dest":             row.get("dest"),
        "ata_datetime":     row.get("ata_datetime"),
        "flt_doc_arrival":  row.get("flt_doc_arrival"),
        "last_uld_arrival": row.get("last_uld_arrival"),
        "bulk_uld_arrival": row.get("bulk_uld_arrival"),
        "flt_com_dat_tim":  row.get("flt_com_dat_tim"),
        "flight_status":    row.get("flight_status"),
    })


def _awb_dict(row: pd.Series, flight_id: int) -> dict:
    """Build INSERT/upsert dict for seg_awbs from an awbs_df row."""
    d = _clean({
        "flight_id":    flight_id,
        "awb_no":       row["awb_no"],
        "sfx":          row["sfx"],
        "origin":       row.get("origin"),
        "dest":         row.get("dest"),
        "manifest_pcs": row.get("manifest_pcs"),
        "manifest_wgt": row.get("manifest_wgt"),
        "seg_pcs":      row.get("seg_pcs"),
        "seg_wgt":      row.get("seg_wgt"),
        "pcs":          row.get("pcs"),
        "gross_wgt":    row.get("gross_wgt"),
        "chg_wgt":      row.get("chg_wgt"),
        "vol_mc":       row.get("vol_mc"),
        "no_of_houses": row.get("no_of_houses"),
        "shc":          row.get("shc"),
        "chg_shc":      row.get("chg_shc"),
        "billing_shc":  row.get("billing_shc"),
        "nog":          row.get("nog"),
        "consignee":    row.get("consignee"),
        "egm_igm_no":   row.get("egm_igm_no"),
        "awd_date":     row.get("awd_date"),
        "nfd_date":     row.get("nfd_date"),
        "rcf_date":     row.get("rcf_date"),
        "do_datetime":  row.get("do_datetime"),
        "tfd_datetime": row.get("tfd_datetime"),
    })
    # Always stamp updated_at (never NaT) so Postgres receives it in EXCLUDED
    d["updated_at"] = datetime.now(UTC)
    return d


# ─────────────────────────────────────────────────────────────────────────────
# Core DB service
# ─────────────────────────────────────────────────────────────────────────────

async def save_seg_data(clean: CleanResult, db: AsyncSession) -> dict:
    """
    Persist a CleanResult into the database.
    Does NOT re-parse or re-clean anything — accepts typed data only.

    Round-trips:
      1. SELECT existing flights  (batch, 1 query)
      2. INSERT new flights       (batch, RETURNING id)
      3. SELECT existing AWBs     (batch, 1 query)
      4. UPSERT all AWBs          (INSERT … ON CONFLICT DO UPDATE WHERE …)
    """
    flights_df = clean.flights_df
    awbs_df    = clean.awbs_df

    stats = {
        "flights_created":  0,
        "flights_existing": 0,
        "awbs_inserted":    0,
        "awbs_updated":     0,
        "awbs_skipped":     0,
    }

    # ── Round-trip 1: fetch existing flights ──────────────────────────────────
    file_flt_keys = list(zip(flights_df["flight_no"], flights_df["flight_date"]))
    stmt = select(DigitalReportImportSegFlight).where(
        tuple_(
            DigitalReportImportSegFlight.flight_no,
            DigitalReportImportSegFlight.flight_date,
        ).in_(file_flt_keys)
    )
    result = await db.execute(stmt)
    existing_flights: dict[tuple, DigitalReportImportSegFlight] = {
        (f.flight_no, f.flight_date): f
        for f in result.scalars().all()
    }
    stats["flights_existing"] = len(existing_flights)

    # ── Round-trip 2: bulk-insert new flights, get IDs back via RETURNING ─────
    new_flight_rows = [
        _flight_dict(row)
        for _, row in flights_df.iterrows()
        if (row["flight_no"], row["flight_date"]) not in existing_flights
    ]
    stats["flights_created"] = len(new_flight_rows)

    if new_flight_rows:
        for chunk in _chunked(new_flight_rows, _FLIGHT_CHUNK):
            ins = (
                pg_insert(DigitalReportImportSegFlight)
                .values(chunk)
                .returning(
                    DigitalReportImportSegFlight.id,
                    DigitalReportImportSegFlight.flight_no,
                    DigitalReportImportSegFlight.flight_date,
                )
            )
            ins_result = await db.execute(ins)
            for r in ins_result.fetchall():
                # Lightweight stand-in so .id is accessible in flt_id_map below
                obj = type("_F", (), {
                    "id": r.id,
                    "flight_no": r.flight_no,
                    "flight_date": r.flight_date,
                })()
                existing_flights[(r.flight_no, r.flight_date)] = obj

    flt_id_map: dict[tuple, int] = {
        k: f.id for k, f in existing_flights.items()
    }

    # ── Round-trip 3: fetch existing AWBs for all relevant flight_ids ─────────
    all_flt_ids = list(flt_id_map.values())
    stmt2 = select(DigitalReportImportSegAwb).where(
        DigitalReportImportSegAwb.flight_id.in_(all_flt_ids)
    )
    result2 = await db.execute(stmt2)
    existing_awbs: dict[tuple, DigitalReportImportSegAwb] = {
        (a.flight_id, a.awb_no, a.sfx): a
        for a in result2.scalars().all()
    }

    # ── Build upsert payload + count stats in Python ──────────────────────────
    # We already have the full picture from existing_awbs, so we can count
    # inserted / updated / skipped without touching the DB again.
    to_upsert: list[dict] = []

    for _, row in awbs_df.iterrows():
        flt_id = flt_id_map.get((row["flight_no"], row["flight_date"]))
        if flt_id is None:
            continue   # should never happen — flights were inserted above

        awb_key  = (flt_id, row["awb_no"], row["sfx"])
        existing = existing_awbs.get(awb_key)

        to_upsert.append(_awb_dict(row, flt_id))

        if existing is None:
            # Not in DB → will be INSERTed
            stats["awbs_inserted"] += 1
        else:
            # In DB → check if pcs or gross_wgt actually differ
            # Use IS DISTINCT FROM semantics (None-safe) mirrored in Python:
            pcs_changed = existing.pcs != row.get("pcs")
            wgt_changed = (
                str(existing.gross_wgt or "") != str(row.get("gross_wgt") or "")
            )
            if pcs_changed or wgt_changed:
                stats["awbs_updated"] += 1
            else:
                stats["awbs_skipped"] += 1

    # ── Round-trip 4: single atomic UPSERT for all AWBs ──────────────────────
    #
    # INSERT ... ON CONFLICT ON CONSTRAINT uq_dr_imp_seg_awb
    #   DO UPDATE SET col = EXCLUDED.col, ...
    #   WHERE (
    #       dr_imp_seg_awbs.pcs       IS DISTINCT FROM EXCLUDED.pcs
    #    OR dr_imp_seg_awbs.gross_wgt IS DISTINCT FROM EXCLUDED.gross_wgt
    #   )
    #
    # IS DISTINCT FROM is NULL-safe: NULL IS DISTINCT FROM NULL → false (no update).
    # The WHERE means Postgres writes zero bytes for truly unchanged rows.
    #
    if to_upsert:
        tbl = DigitalReportImportSegAwb
        # Chunk so each INSERT … ON CONFLICT statement stays under PG's
        # 65,535 bind-parameter limit (a month of data can be ~14k rows).
        for chunk in _chunked(to_upsert, _AWB_CHUNK):
            exc = pg_insert(DigitalReportImportSegAwb)
            upsert_stmt = (
                exc
                .values(chunk)
                .on_conflict_do_update(
                    constraint="uq_dr_imp_seg_awb",
                    set_={col: exc.excluded[col] for col in _AWB_UPDATE_COLS},
                    where=(
                        tbl.pcs.is_distinct_from(exc.excluded.pcs)
                        | tbl.gross_wgt.is_distinct_from(exc.excluded.gross_wgt)
                    ),
                )
            )
            await db.execute(upsert_stmt)

    await db.commit()
    return stats


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point — called by the router
# ─────────────────────────────────────────────────────────────────────────────

async def process_seg_upload(file: UploadFile, db: AsyncSession) -> dict:
    """
    Full pipeline:
      clean_seg_file(file)     →  CleanResult  (no DB, no side effects)
      save_seg_data(clean, db) →  DB stats

    The router calls only this function.
    """
    clean: CleanResult = await clean_seg_file(file)
    db_stats = await save_seg_data(clean, db)

    return {
        "total_rows_parsed":    clean.total_parsed,
        "valid_rows_processed": clean.valid_count,
        "dropped_awb_count":    clean.dropped_count,
        "dropped_awbs":         clean.dropped_awbs,
        **db_stats,
    }






# =====================================================================================================





"""
services/digital_reports/import_dept/seg_report_service.py

Generates the Segregation Import pivot report from stored DB data.
Returns aggregated data dict — the router calls build_excel() or build_csv() on top.

Performance notes (24000 AWBs / 2100 flights for 1 month):
  - 1 DB query with JOIN — no Python loops over DB rows
  - All aggregation done in pandas (vectorised)
  - AWB dedup (same awb_no under same flight+date) handled in groupby before pivot
  - MT conversion done in the same aggregation pass
"""



from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo

import pandas as pd
from sqlalchemy import select, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.digital_reports.segrigation_report import (
    DigitalReportImportSegFlight,
    DigitalReportImportSegAwb,
)

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

MAX_DAYS = 31

# ─────────────────────────────────────────────────────────────────────────────
# Airline master  (hardcoded as per requirement)
# ─────────────────────────────────────────────────────────────────────────────

# (airline_code, airline_name, type)  type: PAX | CAO
# Source of truth: airline_name_code_and_category.xlsx (hardcoded here).
# Category (PAX/CAO) ALWAYS comes from this list — never from the segregation
# report's flight_status column.
_AIRLINE_MASTER: list[tuple[str, str, str]] = [
    ("AI",  "AIR INDIA ( DELHI )",          "PAX"),   # AI + dest=DEL
    ("AI",  "AIR INDIA ( TP )",             "PAX"),   # AI + dest≠DEL — handled in code
    ("DR",  "AIR SHAGOON",                  "CAO"),
    ("D7",  "AIRASIA X BERHAD",             "PAX"),
    ("NH",  "ALL NIPPON AIRWAYS",           "PAX"),
    ("B2",  "BELAVIA-BELARUSIAN",           "PAX"),
    ("B3",  "BHUTAN",                       "PAX"),
    ("BG",  "BIMAN BANGLADESH",             "PAX"),
    ("BZ",  "BLUE DART",                    "PAX"),
    ("X6",  "CHALLENGE AIR CARGO",          "CAO"),
    ("CH",  "CHALLENGE AIR CARGO",          "CAO"),
    ("GI",  "CHINA CENTRAL LONG HAO",       "CAO"),
    ("MS",  "EGYPT AIR",                    "PAX"),
    ("EK",  "EMIRATES",                     "PAX"),
    ("EY",  "ETIHAD  AIRWAYS",              "PAX"),
    ("AY",  "FINNAIR",                      "PAX"),
    ("RH",  "HONG KONG AIR CARGO",          "CAO"),
    ("MR",  "HUNNU AIR",                    "PAX"),
    ("AZ",  "ITA AIRWAYS",                  "PAX"),
    ("RQ",  "KAM AIR",                      "CAO"),
    ("LH",  "LUFTHANSA",                    "PAX"),
    ("W5",  "MAHAN AIR",                    "PAX"),
    ("C6",  "MY FREIGHTER",                 "CAO"),
    ("8M",  "MYANMAR AIRWAYS",              "PAX"),
    ("6P",  "PRADHAAN AIR EXPRESS PVT LTD", "PAX"),
    ("OV",  "SALAM AIR",                    "PAX"),
    ("7L",  "SILK WAY WEST",                "CAO"),
    ("SQ",  "SINGAPORE",                    "PAX"),
    ("SH",  "SOLITAIR AVIATION SERVICE",    "CAO"),
    ("SZ",  "SOMON AIR",                    "PAX"),
    ("SG",  "SPICE JET",                    "PAX"),
    ("UL",  "SRI LANKAN",                   "PAX"),
    ("Y8",  "SUPARNA",                      "CAO"),
    ("LX",  "SWISS",                        "PAX"),
    ("XJ",  "THAI AIRASIA X",               "PAX"),
    ("TG",  "THAI AIRWAYS",                 "PAX"),
    ("HT",  "TIANJIN AIR CARGO",            "CAO"),
    ("VJ",  "VIETJET AIR",                  "PAX"),
    ("VN",  "VIETNAM",                      "PAX"),
    ("YG",  "YTO CARGO",                    "CAO"),
    ("JG",  "JIANGSU JINGDONG CARGO",       "CAO"),
    ("PXX", "PO Mail",                      "PAX"),   # flight_no carrier code starts with P
    ("TS",  "AIR TRANSAT",                  "CAO"),
    ("VG",  "FLY VAAYU",                    "CAO"),
]

# Others bucket (any code not in master) — Passenger per master file
_OTHERS_NAME = "OTHERS"
_OTHERS_TYPE = "PAX"

# Fast lookup: code → (name, type)  [AI handled separately]
_CODE_TO_INFO: dict[str, tuple[str, str]] = {}
for _code, _name, _type in _AIRLINE_MASTER:
    if _code == "AI":
        continue   # AI resolved at row level (Delhi vs TP)
    if _code not in _CODE_TO_INFO:
        _CODE_TO_INFO[_code] = (_name, _type)

# Ordered list for report rows (dedup AI into 2 rows)
_REPORT_AIRLINE_ORDER: list[tuple[str, str, str]] = []
_seen: set[tuple[str, str]] = set()
for _code, _name, _type in _AIRLINE_MASTER:
    if (_code, _name) not in _seen:
        _REPORT_AIRLINE_ORDER.append((_code, _name, _type))
        _seen.add((_code, _name))


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _extract_airline_code(flight_no: str) -> str:
    """
    Airline code from flight number:
    - If the carrier code (alphabetic prefix) starts with 'P' → PXX (PO Mail).
      e.g. "PXX1234", "POM123", "P51234" all → PXX.
    - Otherwise → first 2 chars as the IATA carrier code.
    """
    if not flight_no:
        return ""
    fn = str(flight_no).strip().upper()
    if fn and fn[0] == "P":
        return "PXX"
    return fn[:2]


def _resolve_airline(flight_no: str, dest: str) -> tuple[str, str, str]:
    """
    Returns (airline_key, airline_name, airline_type).
    airline_key is used for grouping: 'AI_DEL', 'AI_TP', code, or 'Others'.
    Category (PAX/CAO) always comes from the master list above.
    """
    code = _extract_airline_code(flight_no)

    if code == "AI":
        if str(dest).strip().upper() == "DEL":
            return ("AI_DEL", "AIR INDIA ( DELHI )", "PAX")
        return ("AI_TP", "AIR INDIA ( TP )", "PAX")

    if code in _CODE_TO_INFO:
        name, typ = _CODE_TO_INFO[code]
        return (code, name, typ)

    return ("Others", _OTHERS_NAME, _OTHERS_TYPE)   # unknown → Others → PAX bucket


def _validate_range(from_dt: datetime, to_dt: datetime) -> None:
    if to_dt <= from_dt:
        raise ValueError("to_datetime must be after from_datetime.")
    delta = to_dt - from_dt
    if delta > timedelta(days=MAX_DAYS):
        raise ValueError(
            f"Date range exceeds {MAX_DAYS} days. "
            f"Selected range is {delta.days} day(s). "
            f"Please select a range of {MAX_DAYS} days or less."
        )


# ─────────────────────────────────────────────────────────────────────────────
# DB fetch — 1 query via JOIN
# ─────────────────────────────────────────────────────────────────────────────

async def _fetch_raw(
    db: AsyncSession,
    from_dt: datetime,
    to_dt: datetime,
) -> pd.DataFrame:
    """
    Single JOIN query: seg_flights + seg_awbs filtered by flt_com_dat_tim range.
    Returns flat DataFrame with all columns needed for aggregation.
    """
    F = DigitalReportImportSegFlight
    A = DigitalReportImportSegAwb

    stmt = (
        select(
            F.flight_no,
            A.dest,                 # AWB-level dest (AI Delhi/TP split needs per-AWB dest)
            F.flt_com_dat_tim,
            A.awb_no,
            A.pcs,
            A.gross_wgt,
            A.chg_wgt,
        )
        .join(A, A.flight_id == F.id)
        .where(
            and_(
                F.flt_com_dat_tim >= from_dt,
                F.flt_com_dat_tim <= to_dt,
            )
        )
    )

    result = await db.execute(stmt)
    rows = result.fetchall()

    if not rows:
        return pd.DataFrame(columns=[
            "flight_no", "dest", "flt_com_dat_tim", "awb_no", "pcs", "gross_wgt", "chg_wgt"
        ])

    df = pd.DataFrame(rows, columns=[
        "flight_no", "dest", "flt_com_dat_tim", "awb_no", "pcs", "gross_wgt", "chg_wgt"
    ])
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Aggregation — all vectorised, single pass
# ─────────────────────────────────────────────────────────────────────────────

def _aggregate(df: pd.DataFrame) -> pd.DataFrame:
    """
    Input : flat AWB rows (one row per AWB record)
    Output: aggregated rows with one row per (airline_key, airline_name, type, date)
            columns: flight_count, awb_count, pcs, gross_wgt_mt

    Steps (all vectorised):
    1. Extract airline_key, airline_name, airline_type per row
    2. Extract report_date from flt_com_dat_tim
    3. Dedup AWBs: same awb_no under same (flight_no, report_date) → sum pcs+wgt, count as 1
    4. Aggregate per (airline_key, airline_name, airline_type, report_date)
    5. Convert gross_wgt kg → MT in the same groupby
    """
    if df.empty:
        return pd.DataFrame()

    # ── Steps 1+2: enrich (airline resolution, report_date, numeric casts) ───
    df = _enrich(df)

    # ── Departure count: distinct (flight_no, flt_com_dat_tim) per (airline, date) ──
    # A flight that operates twice in a day = 2 departures = flight_count 2.
    dep = df.copy()
    dep["_dep_key"] = (
        dep["flight_no"].astype(str) + "|" + dep["flt_com_dat_tim"].astype(str)
    )
    dep_count = (
        dep.groupby(["airline_key", "report_date"], sort=False)["_dep_key"]
        .nunique()
        .reset_index(name="flight_count")
    )

    # ── Step 3: AWB dedup within (flight_no, report_date) ────────────────────
    # Same awb_no on same flight+date → sum pcs and gross_wgt, count AWB once
    awb_dedup = (
        df.groupby(
            ["airline_key", "airline_name", "airline_type",
             "report_date", "flight_no", "awb_no"],
            sort=False,
        )
        .agg(
            pcs       = ("pcs",       "sum"),
            gross_wgt = ("gross_wgt", "sum"),
            chg_wgt   = ("chg_wgt",   "sum"),
        )
        .reset_index()
    )

    # ── Step 4+5: aggregate per (airline, date) — awb count, pcs, wgt MT ──────
    agg = (
        awb_dedup.groupby(
            ["airline_key", "airline_name", "airline_type", "report_date"],
            sort=False,
        )
        .agg(
            awb_count     = ("awb_no",     "nunique"),
            pcs           = ("pcs",        "sum"),
            gross_wgt_mt  = ("gross_wgt",  lambda x: round(x.sum() / 1000, 3)),
            chg_wgt_mt    = ("chg_wgt",    lambda x: round(x.sum() / 1000, 3)),
        )
        .reset_index()
    )

    # Merge in the departure-based flight_count
    agg = agg.merge(dep_count, on=["airline_key", "report_date"], how="left")
    agg["flight_count"] = agg["flight_count"].fillna(0).astype(int)

    return agg


def _aggregate_flights(df: pd.DataFrame) -> pd.DataFrame:
    """
    Flight-level aggregation for the DETAILED report format.

    Output: one row per (airline_key, airline_name, type, report_date, flight_no)
            columns: flight_count, awb_count, pcs, gross_wgt_mt, chg_wgt_mt

    Same dedup rule as _aggregate, but the final groupby keeps flight_no, so each
    individual flight number gets its own per-date metrics. A flight that ran twice
    in one day (two flt_com_dat_tim in range, same date) collapses into one row with
    summed pcs/weight; flight_count for that cell = number of departures (distinct
    flt_com_dat_tim values) — so twice-in-a-day = 2.

    Assumes df already has airline_* + report_date columns added by _enrich —
    so this is called on the SAME enriched df.
    """
    if df.empty:
        return pd.DataFrame()

    # ── Departure count per (flight_no, date): distinct flt_com_dat_tim ──────
    dep_count = (
        df.groupby(
            ["airline_key", "report_date", "flight_no"], sort=False
        )["flt_com_dat_tim"]
        .nunique()
        .reset_index(name="flight_count")
    )

    # AWB dedup within (flight_no, report_date) — identical to _aggregate Step 3
    awb_dedup = (
        df.groupby(
            ["airline_key", "airline_name", "airline_type",
             "report_date", "flight_no", "awb_no"],
            sort=False,
        )
        .agg(
            pcs       = ("pcs",       "sum"),
            gross_wgt = ("gross_wgt", "sum"),
            chg_wgt   = ("chg_wgt",   "sum"),
        )
        .reset_index()
    )

    # Final groupby KEEPS flight_no → one row per flight per date
    flt_agg = (
        awb_dedup.groupby(
            ["airline_key", "airline_name", "airline_type", "report_date", "flight_no"],
            sort=False,
        )
        .agg(
            awb_count     = ("awb_no",     "nunique"),
            pcs           = ("pcs",        "sum"),
            gross_wgt_mt  = ("gross_wgt",  lambda x: round(x.sum() / 1000, 3)),
            chg_wgt_mt    = ("chg_wgt",    lambda x: round(x.sum() / 1000, 3)),
        )
        .reset_index()
    )

    # Merge in departure-based flight_count
    flt_agg = flt_agg.merge(
        dep_count, on=["airline_key", "report_date", "flight_no"], how="left"
    )
    flt_agg["flight_count"] = flt_agg["flight_count"].fillna(0).astype(int)

    return flt_agg


def _enrich(df: pd.DataFrame) -> pd.DataFrame:
    """
    Shared enrichment: add airline_key/name/type + report_date + numeric casts.
    Used by both _aggregate and _aggregate_flights so they operate on the same df.
    """
    if df.empty:
        return df

    resolved = df[["flight_no", "dest"]].apply(
        lambda r: pd.Series(_resolve_airline(r["flight_no"], r["dest"])),
        axis=1,
    )
    resolved.columns = ["airline_key", "airline_name", "airline_type"]
    df = pd.concat([df, resolved], axis=1)

    # Bucket by IST calendar date. flt_com_dat_tim is stored as UTC; a flight at
    # 26-Jun 02:00 IST is 25-Jun 20:30 UTC, so we must convert to IST before
    # taking .date(), otherwise it lands in the wrong (previous) day column.
    _ts = pd.to_datetime(df["flt_com_dat_tim"], utc=True)
    df["report_date"] = _ts.dt.tz_convert(IST).dt.date
    df["pcs"]       = pd.to_numeric(df["pcs"],       errors="coerce").fillna(0)
    df["gross_wgt"] = pd.to_numeric(df["gross_wgt"], errors="coerce").fillna(0)
    df["chg_wgt"]   = pd.to_numeric(df["chg_wgt"],   errors="coerce").fillna(0)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Build report dict
# ─────────────────────────────────────────────────────────────────────────────

def _empty_metrics() -> dict:
    return {"flight_count": 0, "awb_count": 0, "pcs": 0, "gross_wgt_mt": 0.0, "chg_wgt_mt": 0.0}


def _build_report(
    agg: pd.DataFrame,
    dates: list[date],
    flt_agg: pd.DataFrame | None = None,
) -> dict:
    """
    Reshapes flat aggregated DataFrame into the nested report dict:
    {
      dates: [...],
      pax:   { airlines: [...], totals: {date: metrics, grand_total: metrics} },
      cao:   { same },
      grand_total: { date: metrics, grand_total: metrics }
    }
    Each airline entry:
    {
      airline_key, airline_name, airline_type,
      per_date: {date_str: metrics},
      grand_total: metrics,
      flights: [ {flight_no, per_date, grand_total}, ... ]   # only if flt_agg given
    }
    """
    date_strs = [d.isoformat() for d in dates]

    # Index agg by (airline_key, report_date) for O(1) lookup
    if not agg.empty:
        agg_idx = agg.set_index(["airline_key", "report_date"])
    else:
        agg_idx = pd.DataFrame()

    # Build per-airline → per-flight lookup for the detailed format
    # flights_by_airline[airline_key] = ordered list of flight_no
    # flt_idx[(airline_key, flight_no, report_date)] = metrics
    flights_by_airline: dict[str, list[str]] = {}
    flt_idx = {}
    if flt_agg is not None and not flt_agg.empty:
        for _, r in flt_agg.iterrows():
            akey = r["airline_key"]
            fno  = r["flight_no"]
            flt_idx[(akey, fno, r["report_date"])] = {
                "flight_count": int(r["flight_count"]),
                "awb_count":    int(r["awb_count"]),
                "pcs":          int(r["pcs"]),
                "gross_wgt_mt": float(r["gross_wgt_mt"]),
                "chg_wgt_mt":   float(r["chg_wgt_mt"]),
            }
            flights_by_airline.setdefault(akey, [])
            if fno not in flights_by_airline[akey]:
                flights_by_airline[akey].append(fno)

    def _get(airline_key: str, d: date) -> dict:
        if agg_idx.empty:
            return _empty_metrics()
        try:
            row = agg_idx.loc[(airline_key, d)]
            # loc can return Series (one row) or DataFrame (multiple) — handle both
            if isinstance(row, pd.DataFrame):
                row = row.iloc[0]
            return {
                "flight_count": int(row["flight_count"]),
                "awb_count":    int(row["awb_count"]),
                "pcs":          int(row["pcs"]),
                "gross_wgt_mt": float(row["gross_wgt_mt"]),
                "chg_wgt_mt":   float(row["chg_wgt_mt"]),
            }
        except KeyError:
            return _empty_metrics()

    def _sum_metrics(metrics_list: list[dict]) -> dict:
        return {
            "flight_count": sum(m["flight_count"] for m in metrics_list),
            "awb_count":    sum(m["awb_count"]    for m in metrics_list),
            "pcs":          sum(m["pcs"]           for m in metrics_list),
            "gross_wgt_mt": round(sum(m["gross_wgt_mt"] for m in metrics_list), 3),
            "chg_wgt_mt":   round(sum(m["chg_wgt_mt"]   for m in metrics_list), 3),
        }

    def _build_flights(key: str) -> list[dict]:
        """Build the per-flight rows for one airline (detailed format only)."""
        if key not in flights_by_airline:
            return []
        out = []
        for fno in flights_by_airline[key]:
            per_date: dict[str, dict] = {}
            for d, ds in zip(dates, date_strs):
                per_date[ds] = flt_idx.get((key, fno, d), _empty_metrics())
            out.append({
                "flight_no":   fno,
                "per_date":    per_date,
                "grand_total": _sum_metrics(list(per_date.values())),
            })
        return out

    def _build_group(type_filter: str) -> dict:
        airlines_out = []

        for code, name, atype in _REPORT_AIRLINE_ORDER:
            if atype != type_filter:
                continue
            # Determine the lookup key
            if code == "AI" and name == "AIR INDIA ( DELHI )":
                key = "AI_DEL"
            elif code == "AI" and name == "AIR INDIA ( TP )":
                key = "AI_TP"
            else:
                key = code

            per_date: dict[str, dict] = {}
            for d, ds in zip(dates, date_strs):
                per_date[ds] = _get(key, d)

            grand_total = _sum_metrics(list(per_date.values()))

            # Only include airline if it has any data
            if grand_total["flight_count"] > 0:
                airlines_out.append({
                    "airline_code":  code,
                    "airline_name":  name,
                    "airline_type":  atype,
                    "per_date":      per_date,
                    "grand_total":   grand_total,
                    "flights":       _build_flights(key),
                })

        # Also add Others — belongs under PAX per master file (OTHERS = Passenger)
        others_per_date: dict[str, dict] = {}
        for d, ds in zip(dates, date_strs):
            others_per_date[ds] = _get("Others", d)
        others_total = _sum_metrics(list(others_per_date.values()))
        if others_total["flight_count"] > 0 and type_filter == _OTHERS_TYPE:
            airlines_out.append({
                "airline_code":  "",
                "airline_name":  _OTHERS_NAME,
                "airline_type":  _OTHERS_TYPE,
                "per_date":      others_per_date,
                "grand_total":   others_total,
                "flights":       _build_flights("Others"),
            })

        # Group totals = sum of all airline rows per date
        group_per_date: dict[str, dict] = {}
        for ds in date_strs:
            group_per_date[ds] = _sum_metrics(
                [a["per_date"][ds] for a in airlines_out]
            )
        group_grand = _sum_metrics(list(group_per_date.values()))

        return {
            "airlines":    airlines_out,
            "per_date":    group_per_date,
            "grand_total": group_grand,
        }

    pax = _build_group("PAX")
    cao = _build_group("CAO")

    # Grand total per date = PAX + CAO
    grand_per_date: dict[str, dict] = {}
    for ds in date_strs:
        grand_per_date[ds] = _sum_metrics([
            pax["per_date"].get(ds, _empty_metrics()),
            cao["per_date"].get(ds, _empty_metrics()),
        ])
    grand_total = _sum_metrics(list(grand_per_date.values()))

    return {
        "dates":       date_strs,
        "pax":         pax,
        "cao":         cao,
        "per_date":    grand_per_date,
        "grand_total": grand_total,
    }


# ─────────────────────────────────────────────────────────────────────────────
# Public entry point
# ─────────────────────────────────────────────────────────────────────────────

async def generate_seg_report(
    db: AsyncSession,
    from_dt: datetime,
    to_dt: datetime,
    detailed: bool = False,
) -> dict:
    """
    Main service function called by the router.

    from_dt / to_dt : timezone-aware datetimes (UTC).
    detailed        : if True, also include per-flight breakdown under each airline
                      (consumed by build_excel_detailed).
    Raises ValueError for invalid / oversized ranges.
    Returns the full report dict consumed by the builders.
    """
    _validate_range(from_dt, to_dt)

    df = await _fetch_raw(db, from_dt, to_dt)

    # Enrich once, reuse for both airline-level and flight-level aggregation
    enriched = _enrich(df)
    agg = _aggregate(df)
    flt_agg = _aggregate_flights(enriched) if detailed else None

    # Build date list (IST calendar days in range, inclusive).
    # from_dt/to_dt are UTC-aware; convert to IST first so the columns match
    # the IST buckets used in _enrich (otherwise a UTC .date() shows the wrong day).
    dates: list[date] = []
    cur = from_dt.astimezone(IST).date()
    end = to_dt.astimezone(IST).date()
    while cur <= end:
        dates.append(cur)
        cur += timedelta(days=1)

    report = _build_report(agg, dates, flt_agg)
    report["from_dt"]  = from_dt.isoformat()
    report["to_dt"]    = to_dt.isoformat()
    report["detailed"] = detailed
    return report