


"""
utils/seg_cleaner.py

Pure cleaning module for Segregation Import files.
No FastAPI, no database, no side effects.

Public API
----------
    from utils.seg_cleaner import clean_seg_file, CleanResult

    result: CleanResult = await clean_seg_file(file)   # UploadFile
    # or, if you already have a DataFrame / path:
    result: CleanResult = clean_seg_dataframe(raw_df)

CleanResult fields
------------------
    flights_df   : pd.DataFrame  — one row per unique (flight_no, flight_date)
    awbs_df      : pd.DataFrame  — one row per valid AWB, with flight_no + flight_date as FK keys
    dropped_awbs : list[dict]    — every rejected row with reason + original values
    total_parsed : int           — rows extracted from file before cleaning
    valid_count  : int           — rows that made it through
    dropped_count: int           — rows that were rejected
"""

import io
import re
import math
from dataclasses import dataclass, field
from datetime import datetime, timezone
from decimal import Decimal, ROUND_HALF_UP
from pathlib import Path
from zoneinfo import ZoneInfo

import pandas as pd
from fastapi import HTTPException, UploadFile

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

# ─────────────────────────────────────────────────────────────────────────────
# Constants
# ─────────────────────────────────────────────────────────────────────────────

ALLOWED_EXTENSIONS = {".csv", ".xlsx", ".xls"}

# Raw Excel/CSV column index → clean field name
COL_MAP: dict[int, str] = {
    3:  "sl_no",
    4:  "flight_no",
    5:  "flight_date",
    6:  "awb_no",
    7:  "sfx",
    8:  "ata_datetime",
    9:  "flt_doc_arrival",
    10: "last_uld_arrival",
    11: "bulk_uld_arrival",
    12: "origin",
    13: "dest",
    14: "manifest_pcs",
    15: "manifest_wgt",
    16: "seg_pcs",
    17: "seg_wgt",
    18: "pcs",
    19: "gross_wgt",
    20: "chg_wgt",
    21: "vol_mc",
    22: "no_of_houses",
    23: "shc",
    24: "chg_shc",
    25: "billing_shc",
    26: "nog",
    27: "consignee",
    28: "awd_date",
    29: "nfd_date",
    30: "rcf_date",
    31: "do_datetime",
    32: "tfd_datetime",
    33: "egm_igm_no",
    34: "flt_com_dat_tim",
    35: "flight_status",
}

# Columns that belong only in the flights table (flight-level metadata)
FLIGHT_COLS = [
    "flight_no", "flight_date", "origin", "dest",
    "ata_datetime", "flt_doc_arrival", "last_uld_arrival",
    "bulk_uld_arrival", "flt_com_dat_tim", "flight_status",
]

# IST datetimes → convert to UTC before storing
DATETIME_COLS = [
    "ata_datetime", "flt_doc_arrival", "last_uld_arrival", "bulk_uld_arrival",
    "flt_com_dat_tim", "awd_date", "nfd_date", "rcf_date",
    "do_datetime", "tfd_datetime",
]

# Piece count columns — always plain Python int, never float/Decimal
INT_COLS = ["manifest_pcs", "seg_pcs", "pcs", "no_of_houses"]

# Weight columns — stored as kg, Decimal with 2dp
WEIGHT_COLS = ["manifest_wgt", "seg_wgt", "gross_wgt", "chg_wgt"]

# Plain string columns
STRING_COLS = [
    "flight_no", "sfx", "origin", "dest",
    "shc", "chg_shc", "billing_shc", "nog", "consignee",
    "egm_igm_no", "flight_status",
]

# Keywords that mark non-data rows (totals, headers, summary blocks)
_EXCLUDED_KEYWORDS = frozenset({
    "total", "grand total", "nil carrier", "flt no.", "sl.no.",
    "carrier", "segregation report", "total shipment count",
})


# ─────────────────────────────────────────────────────────────────────────────
# Return type
# ─────────────────────────────────────────────────────────────────────────────

@dataclass
class CleanResult:
    """
    Everything the service layer needs — no raw file bytes, no DB calls.

    flights_df  : unique flights found in file (one row per flight_no + flight_date)
    awbs_df     : valid AWB rows, typed and normalised
    dropped_awbs: list of rejected rows with reason + original values for audit
    total_parsed: count of rows extracted from file (before cleaning)
    valid_count : count of rows in awbs_df
    dropped_count: count of rows in dropped_awbs
    """
    flights_df:    pd.DataFrame
    awbs_df:       pd.DataFrame
    dropped_awbs:  list[dict]  = field(default_factory=list)
    total_parsed:  int         = 0
    valid_count:   int         = 0
    dropped_count: int         = 0


# ─────────────────────────────────────────────────────────────────────────────
# Field-level helpers (pure functions, no I/O)
# ─────────────────────────────────────────────────────────────────────────────

def normalize_awb_no(value) -> str | None:
    """
    Normalise AWB to exactly 11 digits (strip dashes/spaces).
    Returns None for anything that can't be made valid — caller logs and drops.
    """
    if not value:
        return None
    cleaned = re.sub(r"\D", "", str(value))
    if len(cleaned) == 11:
        return cleaned
    if len(cleaned) == 10:
        return "0" + cleaned
    return None


def _to_decimal2(value) -> Decimal | None:
    """kg weight → Decimal with exactly 2 decimal places."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return Decimal(str(value)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    except Exception:
        return None


def _ist_to_utc(value) -> datetime | None:
    """
    Naive datetime from file → assume IST → return UTC-aware datetime.
    Already tz-aware values are converted directly to UTC.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, str):
        try:
            value = datetime.fromisoformat(value)
        except ValueError:
            return None
    if isinstance(value, datetime):
        if value.tzinfo is None:
            value = value.replace(tzinfo=IST)
        return value.astimezone(UTC)
    return None


def _safe_int(value) -> int | None:
    """
    Always returns plain Python int or None.
    Handles Excel floats like "34.0" → 34.
    """
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return None


def _safe_str(value) -> str | None:
    """Strip and return string; return None for blank / 'nan' / 'none'."""
    if value is None:
        return None
    s = str(value).strip()
    return s if s and s.lower() not in ("nan", "none", "") else None


# ─────────────────────────────────────────────────────────────────────────────
# Step 1 — Read file bytes into raw DataFrame
# ─────────────────────────────────────────────────────────────────────────────

def _validate_extension(filename: str) -> str:
    ext = Path(filename).suffix.lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed: .csv, .xlsx, .xls",
        )
    return ext


async def _read_raw(file: UploadFile) -> pd.DataFrame:
    """Read UploadFile → raw DataFrame, all columns as object dtype."""
    ext = _validate_extension(file.filename)
    contents = await file.read()
    buf = io.BytesIO(contents)
    if ext == ".csv":
        return pd.read_csv(buf, header=None, dtype=object)
    return pd.read_excel(buf, sheet_name=0, header=None, dtype=object)


# ─────────────────────────────────────────────────────────────────────────────
# Step 2 — Parse: extract only genuine AWB data rows
# ─────────────────────────────────────────────────────────────────────────────

def _parse_raw(raw: pd.DataFrame) -> pd.DataFrame:
    """
    Keep only rows that are genuine flight+AWB data rows.
    Rejects: Total Shipment Count rows, GRAND TOTAL, NIL CARRIER block, headers.

    A row is genuine when ALL four conditions hold:
      - col 3 (sl_no)      is a positive digit  → "1", "2", "3" …
      - col 4 (flight_no)  is not a keyword      → not "Total", "Carrier" …
      - col 5 (flight_date) parses as a real date
      - col 6 (awb_no)     is not empty
    """
    if len(raw.columns) <= 6:
        raise HTTPException(
            status_code=422,
            detail="File does not match the expected Segregation Report format.",
        )

    def _is_pos_int(val) -> bool:
        try:
            return str(val).strip().isdigit() and int(str(val).strip()) > 0
        except Exception:
            return False

    def _not_keyword(val) -> bool:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return False
        return str(val).strip().lower() not in _EXCLUDED_KEYWORDS

    def _is_real_date(val) -> bool:
        if val is None or (isinstance(val, float) and math.isnan(val)):
            return False
        try:
            pd.to_datetime(str(val))
            return True
        except Exception:
            return False

    mask = (
        raw.iloc[:, 3].apply(_is_pos_int)
        & raw.iloc[:, 4].apply(_not_keyword)
        & raw.iloc[:, 5].apply(_is_real_date)
        & raw.iloc[:, 6].notna()
    )

    available = {i: COL_MAP[i] for i in COL_MAP if i < len(raw.columns)}
    df = raw.loc[mask, list(available.keys())].copy()
    df.rename(columns=available, inplace=True)
    df.reset_index(drop=True, inplace=True)
    return df


# ─────────────────────────────────────────────────────────────────────────────
# Step 3 — Clean & type-cast every field
# ─────────────────────────────────────────────────────────────────────────────

def _apply_types(df: pd.DataFrame) -> tuple[pd.DataFrame, list[dict]]:
    """
    Type-cast all columns. Collect every row that must be dropped with reason.
    Returns (typed_df, dropped_awbs).
    """
    dropped_awbs: list[dict] = []

    # ── String columns ────────────────────────────────────────────────────────
    for col in STRING_COLS:
        if col in df.columns:
            df[col] = df[col].apply(_safe_str)

    # ── SFX: default to "P" if missing ───────────────────────────────────────
    if "sfx" in df.columns:
        df["sfx"] = df["sfx"].apply(lambda x: _safe_str(x) or "P")

    # ── AWB normalise — keep originals for drop report ────────────────────────
    raw_awb = df["awb_no"].copy()
    df["awb_no"] = df["awb_no"].apply(normalize_awb_no)

    # ── flight_date → plain Python date (no timezone) ─────────────────────────
    df["flight_date"] = pd.to_datetime(df["flight_date"], errors="coerce").dt.date

    # ── Datetime columns: naive IST → UTC-aware ───────────────────────────────
    for col in DATETIME_COLS:
        if col in df.columns:
            df[col] = (
                pd.to_datetime(df[col], errors="coerce")
                .apply(lambda x: _ist_to_utc(x) if pd.notna(x) else None)
            )

    # ── Int columns — dtype=object prevents pandas float64 upcasting ──────────
    # Without dtype=object, pandas converts [177, None, 20] → [177.0, NaN, 20.0]
    for col in INT_COLS:
        if col in df.columns:
            df[col] = pd.Series(
                [_safe_int(v) for v in df[col]],
                index=df.index,
                dtype=object,       # keeps Python int / None, never numpy float64
            )

    # ── Weight columns: Decimal 2dp (kg) ─────────────────────────────────────
    for col in WEIGHT_COLS:
        if col in df.columns:
            df[col] = df[col].apply(_to_decimal2)

    # ── vol_mc: 4dp float ────────────────────────────────────────────────────
    if "vol_mc" in df.columns:
        df["vol_mc"] = pd.to_numeric(df["vol_mc"], errors="coerce").round(4)

    # ── Collect invalid rows ──────────────────────────────────────────────────
    bad_awb = df["awb_no"].isna()
    bad_flt = df["flight_no"].isna() | df["flight_date"].isna()

    for idx in df[bad_awb].index:
        dropped_awbs.append({
            "reason":       "invalid_awb_format",
            "original_awb": _safe_str(raw_awb.iloc[idx]),
            "flight_no":    df.at[idx, "flight_no"],
            "flight_date":  str(df.at[idx, "flight_date"]),
            "sfx":          df.at[idx, "sfx"],
            "row_index":    int(idx),
        })

    for idx in df[bad_flt & ~bad_awb].index:
        dropped_awbs.append({
            "reason":       "missing_flight_key",
            "original_awb": _safe_str(raw_awb.iloc[idx]),
            "flight_no":    df.at[idx, "flight_no"],
            "flight_date":  str(df.at[idx, "flight_date"]),
            "sfx":          df.at[idx, "sfx"],
            "row_index":    int(idx),
        })

    df = df[~(bad_awb | bad_flt)].reset_index(drop=True)
    return df, dropped_awbs


# ─────────────────────────────────────────────────────────────────────────────
# Step 4 — Split into flights_df and awbs_df
# ─────────────────────────────────────────────────────────────────────────────

def _split(df: pd.DataFrame) -> tuple[pd.DataFrame, pd.DataFrame]:
    """
    flights_df : one row per (flight_no, flight_date) — first row wins for metadata
    awbs_df    : all AWB rows, still carries flight_no + flight_date as join keys,
                 PLUS origin + dest which are AWB-level (same flight can carry AWBs
                 with different origin/dest, so they must be stored per-AWB).
    """
    # origin + dest live at BOTH levels: flight-level (first row, for metadata)
    # and AWB-level (each AWB keeps its own). These must survive into awbs_df.
    AWB_LEVEL_SHARED = ("flight_no", "flight_date", "origin", "dest")

    flights_df = (
        df[FLIGHT_COLS]
        .drop_duplicates(subset=["flight_no", "flight_date"])
        .reset_index(drop=True)
    )
    # Drop only the flight-ONLY columns from awbs_df; keep origin + dest per AWB
    awbs_df = df.drop(
        columns=[c for c in FLIGHT_COLS if c not in AWB_LEVEL_SHARED],
        errors="ignore",
    ).reset_index(drop=True)

    return flights_df, awbs_df


# ─────────────────────────────────────────────────────────────────────────────
# Public API
# ─────────────────────────────────────────────────────────────────────────────

async def clean_seg_file(file: UploadFile) -> CleanResult:
    """
    Full cleaning pipeline for an uploaded UploadFile.
    No DB calls. Returns CleanResult ready for the service layer to consume.
    """
    raw = await _read_raw(file)
    return clean_seg_dataframe(raw)


def clean_seg_dataframe(raw: pd.DataFrame) -> CleanResult:
    """
    Same pipeline but takes a raw DataFrame directly.
    Useful for testing, batch jobs, or pre-loaded data.
    """
    # Parse
    df = _parse_raw(raw)
    total_parsed = len(df)

    if df.empty:
        raise HTTPException(status_code=422, detail="No valid data rows found in file.")

    # Clean + type-cast
    df, dropped_awbs = _apply_types(df)

    if df.empty:
        raise HTTPException(status_code=422, detail="All rows were invalid after cleaning.")

    # Split
    flights_df, awbs_df = _split(df)

    return CleanResult(
        flights_df   = flights_df,
        awbs_df      = awbs_df,
        dropped_awbs = dropped_awbs,
        total_parsed = total_parsed,
        valid_count  = len(awbs_df),
        dropped_count= len(dropped_awbs),
    )