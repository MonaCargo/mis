"""
import_truck_in_out_cleaning.py
--------------------------------
Cleans the IMPORT Truck IN/OUT Excel/CSV export from DCSC.

Mandatory fields (drop row if missing):
  - GP No  : must be present AND purely numeric
  - AWB No : must be present and non-blank

Optional fields (keep row, store NULL if missing):
  - Truck No, HAWB No, PCS, Driver Name, Mobile No, Agent, User ID
  - Time In  : optional — if present, converted IST → UTC
  - Time Out : optional — if present, converted IST → UTC

Optimised for speed:
  - pandas vectorised ops throughout (no row-by-row loops)
  - datetime parsing done once with explicit format string
  - timezone conversion via a single timedelta subtract
"""

from __future__ import annotations

import io
from datetime import timezone, timedelta
from typing import Union

import pandas as pd

# ── Constants ─────────────────────────────────────────────────────

IST_OFFSET = timedelta(hours=5, minutes=30)
UTC        = timezone.utc

_SKIP_ROWS = 5   # Excel export always has 5 junk rows before the real header
_DT_FMT    = "%d-%b-%Y %H:%M"

_RAW_COLS = [
    "gp_no", "date", "awb_no", "hawb_no", "pcs",
    "truck_no", "driver_name", "mobile_no",
    "time_in", "time_out", "agent", "user_id",
]


# ── Public API ────────────────────────────────────────────────────

def clean_import_truck_file(
    source: Union[str, bytes, io.IOBase],
) -> pd.DataFrame:
    """
    Read and clean an IMPORT Truck IN/OUT file.

    Returns a DataFrame with:
        gp_no        Int64
        awb_no       str
        hawb_no      str   (nullable)
        pcs          Int64 (nullable)
        truck_no     str   (nullable)
        driver_name  str   (nullable)
        mobile_no    str   (nullable)
        time_in_utc  datetime64[us, UTC]  (nullable)
        time_out_utc datetime64[us, UTC]  (nullable)
        agent        str   (nullable)
        user_id      str   (nullable)
        date         str   (nullable, kept as-is from source)
    """
    df = _read_raw(source)
    df = _drop_invalid_rows(df)
    df = _convert_times_to_utc(df)
    df = _coerce_types(df)
    return df


def truck_in_out_clean_with_report(
    source: Union[str, bytes, io.IOBase],
) -> tuple[pd.DataFrame, dict]:
    """
    Same as clean_import_truck_file but also returns:
        {
            "total_raw":      int,
            "dropped_no_gp":  int,
            "dropped_no_awb": int, 
            "final_count":    int,
        }
    """
    df_raw = _read_raw(source)
    total_raw = len(df_raw)

    gp_mask = _valid_gp_mask(df_raw)
    dropped_gp = int((~gp_mask).sum())
    df_after_gp = df_raw[gp_mask].copy()

    awb_mask = _valid_awb_mask(df_after_gp)
    dropped_awb = int((~awb_mask).sum())
    df_clean = df_after_gp[awb_mask].copy()

    df_clean = _convert_times_to_utc(df_clean)
    df_clean = _coerce_types(df_clean)

    return df_clean, {
        "total_raw":      total_raw,
        "dropped_no_gp":  dropped_gp,
        "dropped_no_awb": dropped_awb,
        "final_count":    len(df_clean),
    }


# ── Internal helpers ──────────────────────────────────────────────

def _read_raw(source: Union[str, bytes, io.IOBase]) -> pd.DataFrame:
    """Read the file, skip header junk, assign canonical column names."""
    read_kwargs = dict(
        skiprows=_SKIP_ROWS,
        header=0,
        dtype=str,
        keep_default_na=False,
        na_values=["", "NaN", "nan", "NULL", "null", "N/A", "n/a"],
    )

    if isinstance(source, str):
        if source.lower().endswith((".xlsx", ".xls")):
            df = pd.read_excel(source, **read_kwargs)
        else:
            df = pd.read_csv(source, **read_kwargs)
    elif isinstance(source, bytes):
        buf = io.BytesIO(source)
        try:
            df = pd.read_excel(buf, **read_kwargs)
        except Exception:
            buf.seek(0)
            df = pd.read_csv(buf, **read_kwargs)
    else:
        try:
            df = pd.read_excel(source, **read_kwargs)
        except Exception:
            source.seek(0)
            df = pd.read_csv(source, **read_kwargs)

    # df = df.iloc[:, : len(_RAW_COLS)].copy() 
    df = df.iloc[:, 2 : 2 + len(_RAW_COLS)].copy()   # skip the 2 empty leading cols
    df.columns = _RAW_COLS[: df.shape[1]]

    # Drop leftover header row if skiprows landed on a blank line
    if len(df) and df["gp_no"].iloc[0] == "GP No":
        df = df.iloc[1:].reset_index(drop=True)

    return df


def _valid_gp_mask(df: pd.DataFrame) -> pd.Series:
    """True where gp_no is present and purely numeric."""
    gp = df["gp_no"].str.strip()
    return pd.to_numeric(gp, errors="coerce").notna() & gp.notna()


def _valid_awb_mask(df: pd.DataFrame) -> pd.Series:
    """True where awb_no is present and non-blank."""
    return df["awb_no"].notna() & (df["awb_no"].str.strip() != "")


def _drop_invalid_rows(df: pd.DataFrame) -> pd.DataFrame:
    df = df[_valid_gp_mask(df)].copy()
    df = df[_valid_awb_mask(df)].copy()
    return df.reset_index(drop=True)


def _parse_ist_column(series: pd.Series) -> pd.Series:
    """Parse an IST datetime string column into tz-aware UTC datetimes."""
    parsed = pd.to_datetime(series, format=_DT_FMT, errors="coerce")

    # Fallback for any edge-case formats
    failed_mask = parsed.isna() & series.notna()
    if failed_mask.any():
        parsed[failed_mask] = pd.to_datetime(
            series[failed_mask], infer_datetime_format=True, errors="coerce"
        )

    # IST → UTC: subtract offset, then localize as UTC
    return (parsed - IST_OFFSET).dt.tz_localize(UTC)


def _convert_times_to_utc(df: pd.DataFrame) -> pd.DataFrame:
    df["time_in_utc"]  = _parse_ist_column(df["time_in"])
    df["time_out_utc"] = _parse_ist_column(df["time_out"])
    return df.drop(columns=["time_in", "time_out"])


def _coerce_types(df: pd.DataFrame) -> pd.DataFrame:
    df["gp_no"] = pd.to_numeric(df["gp_no"], errors="coerce").astype("Int64")
    df["pcs"]   = pd.to_numeric(df["pcs"],   errors="coerce").astype("Int64")

    str_cols = ["awb_no", "hawb_no", "truck_no", "driver_name",
                "mobile_no", "agent", "user_id", "date"]
    for col in str_cols:
        if col in df.columns:
            df[col] = df[col].str.strip().replace({"": None})

    return df.reset_index(drop=True)