"""
uld_inventory_cleaner.py
------------------------
Standalone cleaner for ULD Count Report files.
Supports .csv and .xlsx / .xls

Usage (from your router):
    from uld_inventory_cleaner import extract_uld_inventory
    df = extract_uld_inventory(io.BytesIO(contents), file.filename)
"""

from __future__ import annotations

import io
from datetime import datetime
from typing import Optional

import pandas as pd

SUPPORTED_EXTENSIONS = {".csv", ".xlsx", ".xls"}


# ─────────────────────────────────────────────────────────────────────────────
# PUBLIC ENTRY POINT
# ─────────────────────────────────────────────────────────────────────────────

def extract_all_carrier_uld_inventory(source: io.BytesIO, filename: str) -> pd.DataFrame:
    """
    Parse a ULD Count Report from a CSV or Excel file and return a clean DataFrame.

    Raw file layout:
        row 0  →  title row  e.g. " , , ULD Count Report:  ,,"   (skip)
        row 1  →  blank row                                        (skip)
        row 2  →  real header: ,Sl.No.,ULD NUMBER,CARRIER CODE,ULD DATE
        row 3+ →  data

    Returns
    -------
    pd.DataFrame with columns:
        sl_no        : int     (nullable)
        uld_number   : str     (stripped + uppercased)
        carrier_code : str     (stripped + uppercased, None when blank)
        uld_date     : datetime | None
    """
    ext = _detect_extension(filename)
    raw_df = _read_raw(source, ext)
    return _clean(raw_df)


# ─────────────────────────────────────────────────────────────────────────────
# PRIVATE HELPERS
# ─────────────────────────────────────────────────────────────────────────────

def _detect_extension(filename: str) -> str:
    lower = (filename or "").lower()
    for ext in SUPPORTED_EXTENSIONS:
        if lower.endswith(ext):
            return ext
    raise ValueError(
        f"Unsupported file type: '{filename}'. "
        f"Allowed extensions: {', '.join(sorted(SUPPORTED_EXTENSIONS))}"
    )


def _read_raw(source: io.BytesIO, ext: str) -> pd.DataFrame:
    """Read the raw file, skipping the 2 junk header rows."""
    shared_kwargs = dict(skiprows=2, header=0, dtype=str, keep_default_na=False)

    if ext == ".csv":
        return pd.read_csv(source, **shared_kwargs)
    else:  # .xlsx / .xls
        return pd.read_excel(source, **shared_kwargs)


def _clean(df: pd.DataFrame) -> pd.DataFrame:
    df = _normalize_columns(df)
    df = _drop_empty_uld_rows(df)
    df = _clean_uld_number(df)
    df = _clean_carrier_code(df)
    df = _clean_sl_no(df)
    df = _parse_uld_date(df)
    df = _deduplicate(df)
    return df[["sl_no", "uld_number", "carrier_code", "uld_date"]].reset_index(drop=True)


def _normalize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Lowercase + snake_case all column names and drop the stray leading blank column."""
    df.columns = [
        str(c).strip().lower().replace(".", "").replace(" ", "_")
        for c in df.columns
    ]
    # The CSV has a leading empty column from the leading comma — remove it
    if df.columns[0] in {"", "unnamed:_0", "unnamed:0"}:
        df = df.drop(columns=df.columns[0])

    rename_map = {
        "slno":         "sl_no",
        "sl_no":        "sl_no",
        "uld_number":   "uld_number",
        "carrier_code": "carrier_code",
        "uld_date":     "uld_date",
    }
    return df.rename(columns={c: rename_map[c] for c in df.columns if c in rename_map})


def _drop_empty_uld_rows(df: pd.DataFrame) -> pd.DataFrame:
    return df[df["uld_number"].str.strip().astype(bool)].copy()


def _clean_uld_number(df: pd.DataFrame) -> pd.DataFrame:
    df["uld_number"] = df["uld_number"].str.strip().str.upper()
    return df


def _clean_carrier_code(df: pd.DataFrame) -> pd.DataFrame:
    df["carrier_code"] = (
        df["carrier_code"]
        .str.strip()
        .str.upper()
        .replace("", None)     # blank string → None
    )
    return df


def _clean_sl_no(df: pd.DataFrame) -> pd.DataFrame:
    df["sl_no"] = pd.to_numeric(df["sl_no"], errors="coerce").astype("Int64")
    return df


def _parse_uld_date(df: pd.DataFrame) -> pd.DataFrame:
    df["uld_date"] = df["uld_date"].apply(_parse_single_date)
    return df


def _parse_single_date(raw: str) -> Optional[datetime]:
    """Try multiple date formats; return None if nothing matches (never crash)."""
    raw = (raw or "").strip()
    if not raw:
        return None
    for fmt in (
        "%d-%m-%y %H:%M",      # 23-04-22 23:51  ← primary format in this report
        "%d-%m-%Y %H:%M",      # 23-04-2022 23:51
        "%Y-%m-%d %H:%M:%S",   # 2022-04-23 23:51:00
        "%Y-%m-%d",            # 2022-04-23
    ):
        try:
            return datetime.strptime(raw, fmt)
        except ValueError:
            continue
    return None  # unparseable → None, not an exception


def _deduplicate(df: pd.DataFrame) -> pd.DataFrame:
    """Keep first occurrence of each ULD number."""
    return df.drop_duplicates(subset=["uld_number"], keep="first")