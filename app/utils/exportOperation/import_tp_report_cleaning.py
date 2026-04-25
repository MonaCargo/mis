# import re

# import pandas as pd
# import numpy as np
# from io import BytesIO

# REQUIRED_COLUMNS = [
#     "SL.NO.", "AWB NO.", "ORGIN", "DESTINATION", "PCS.", "GROSS WT", "CHG WT",
#     "NOG", "SHC",
#     "X-RAY STRT DATE & TIME", "X-RAY END DATE & TIME",
#     "X-RAY TYPE", "X-RAY DT/TIME", "X-RAY-USER",
#     "PHS (PCS)", "ETD (PCS)", "EDS (PCS)", "EDD (PCS)", "VCK (PCS)", "CMD (PCS)",
#     "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME", "FLT NO",
#     "AGENT NAME", "SERIAL NO.", "DEVICE MODEL NO.", "REMARKS"
# ]

# NUMERIC_COLS = ["PCS.", "GROSS WT", "CHG WT",
#                 "PHS (PCS)", "ETD (PCS)", "EDS (PCS)",
#                 "EDD (PCS)", "VCK (PCS)", "CMD (PCS)"]

# DATETIME_COLS = [
#     "X-RAY STRT DATE & TIME", "X-RAY END DATE & TIME",
#     "X-RAY DT/TIME", "UPLIFTING DT/TIME"
# ]

# def _clean_awb(val):
#     if not val or str(val).strip().lower() in ("", "nan", "none"):
#         return None
#     s = re.sub(r"\s+", "", str(val).strip())
#     s = re.sub(r"-+", "-", s).replace("-", "")
#     s = s.rstrip("PA")   # strip suffix
#     if s and len(s) == 10:
#         s = s.zfill(11)
#     return s or None



# def _extract_metadata(df_raw: pd.DataFrame) -> dict:
#     """Extract report metadata (FROM DATE, TO DATE, Carrier) from header rows."""
#     metadata = {}
#     for _, row in df_raw.iterrows():
#         row_vals = row.dropna().astype(str).str.strip().tolist()
#         row_str = " ".join(row_vals)
#         if "FROM DATE" in row_str.upper():
#             for i, val in enumerate(row_vals):
#                 if "FROM DATE" in val.upper() and i + 1 < len(row_vals):
#                     metadata["from_date"] = row_vals[i + 1]
#                 if "TO DATE" in val.upper() and i + 1 < len(row_vals):
#                     metadata["to_date"] = row_vals[i + 1]
#                 if "CARRIER" in val.upper() and i + 1 < len(row_vals):
#                     metadata["carrier"] = row_vals[i + 1]
#     return metadata


# def _find_header_row(df_raw: pd.DataFrame) -> int:
#     """Locate the row index containing the actual column headers."""
#     for i, row in df_raw.iterrows():
#         vals = row.dropna().astype(str).str.upper().str.strip().tolist()
#         if "AWB NO." in vals or "AWB NO" in vals:
#             return i
#     raise ValueError("Could not find header row with 'AWB NO.' column.")


# def clean_import_tp_xray(file_bytes: BytesIO, file_type: str = "excel") -> tuple[pd.DataFrame, dict]:
#     """
#     Clean and extract data from the Import TP X-RAY report.

#     Args:
#         file_bytes: File content as BytesIO.
#         file_type: 'excel' or 'csv'.

#     Returns:
#         Tuple of (cleaned DataFrame, metadata dict with from_date / to_date / carrier).
#     """

#     # 1️⃣ Read raw file (no header)
#     if file_type == "excel":
#         df_raw = pd.read_excel(file_bytes, header=None, dtype=str)
#     elif file_type == "csv":
#         df_raw = pd.read_csv(file_bytes, header=None, dtype=str)
#     else:
#         raise ValueError("Unsupported file type. Use 'excel' or 'csv'.")

#     # 2️⃣ Extract metadata from header rows
#     metadata = _extract_metadata(df_raw)

#     # 3️⃣ Locate actual header row
#     header_row_idx = _find_header_row(df_raw)

#     # 4️⃣ Re-read with correct header
#     if file_type == "excel":
#         file_bytes.seek(0)
#         df = pd.read_excel(file_bytes, header=header_row_idx, dtype=str)
#     else:
#         file_bytes.seek(0)
#         df = pd.read_csv(file_bytes, header=header_row_idx, dtype=str)

#     # 5️⃣ Normalize column names
#     df.columns = df.columns.str.strip().str.upper()

#     # 6️⃣ Drop unnamed columns only (keep named cols even if fully empty — e.g. EDS, EDD, VCK, CMD)
#     df = df.loc[:, ~df.columns.str.startswith("UNNAMED")]

#     # 7️⃣ Rename Sl.No. column if present
#     df.columns = [col if col != "SL.NO" else "SL.NO." for col in df.columns]

#     # 8️⃣ Drop summary / footer rows (e.g., TOTAL row)
#     df = df[~df.iloc[:, 0].astype(str).str.upper().str.strip().isin(["TOTAL", "NAN", ""])]
#     df = df.replace(r"^\s*$", np.nan, regex=True)
#     df = df.dropna(how="all")

#     # 9️⃣ Keep only rows where AWB NO. is non-empty (import AWBs are alphanumeric e.g. 09830032866P)
#     if "AWB NO." in df.columns:
#         df = df[df["AWB NO."].astype(str).str.strip().str.len() > 3]

#     # 🔟 Validate required columns
#     missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
#     if missing_cols:
#         raise ValueError(f"Missing required columns: {missing_cols}")

#     df = df[REQUIRED_COLUMNS]

#     # 1️⃣1️⃣ Strip whitespace from all string columns
#     for col in df.columns:
#         df[col] = df[col].astype(str).str.strip()

#     df = df.replace({"nan": np.nan, "NaN": np.nan, "": np.nan})

#     # ✅ Clean AWB
#     df["AWB NO."] = df["AWB NO."].apply(_clean_awb)

#     # 1️⃣2️⃣ Cast numeric columns
#     for col in NUMERIC_COLS:
#         df[col] = pd.to_numeric(df[col], errors="coerce")

#     # 1️⃣3️⃣ Parse datetime columns (handles mixed formats silently)
#     for col in DATETIME_COLS:
#         df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed", dayfirst=True)

#     # 1️⃣4️⃣ Standardise text columns to UPPER
#     text_cols = [c for c in REQUIRED_COLUMNS if c not in NUMERIC_COLS + DATETIME_COLS]
#     for col in text_cols:
#         df[col] = df[col].astype(str).str.strip()
#         df[col] = df[col].replace({"NAN": np.nan})

#     # 1️⃣5️⃣ Drop rows missing the key identifier
#     df = df.dropna(subset=["AWB NO."])

#     # 1️⃣6️⃣ Remove duplicates on AWB + X-RAY START TIME
#     df = df.drop_duplicates(subset=["AWB NO.", "X-RAY STRT DATE & TIME"])

#     df = df.reset_index(drop=True)

#     return df, metadata


# # ── Quick smoke-test ────────────────────────────────────────────────────────
# # if __name__ == "__main__":
# #     FILE_PATH = "Import_TP_x-ray.xlsx"

# #     with open(FILE_PATH, "rb") as f:
# #         data = BytesIO(f.read())

# #     df_clean, meta = clean_import_tp_xray(data, file_type="excel")

# #     print("Metadata:", meta)
# #     print(f"Rows extracted: {len(df_clean)}")
# #     print(df_clean.head(3).to_string())
# #     print("\nDtypes:\n", df_clean.dtypes)































# import re
# from datetime import datetime, timezone

# import pandas as pd
# import numpy as np
# from io import BytesIO
# import pytz

# REQUIRED_COLUMNS = [
#     "SL.NO.", "AWB NO.", "ORGIN", "DESTINATION", "PCS.", "GROSS WT", "CHG WT",
#     "NOG", "SHC",
#     "X-RAY STRT DATE & TIME", "X-RAY END DATE & TIME",
#     "X-RAY TYPE", "X-RAY DT/TIME", "X-RAY-USER",
#     "PHS (PCS)", "ETD (PCS)", "EDS (PCS)", "EDD (PCS)", "VCK (PCS)", "CMD (PCS)",
#     "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME", "FLT NO",
#     "AGENT NAME", "SERIAL NO.", "DEVICE MODEL NO.", "REMARKS"
# ]

# NUMERIC_COLS = [
#     "PCS.", "GROSS WT", "CHG WT",
#     "PHS (PCS)", "ETD (PCS)", "EDS (PCS)",
#     "EDD (PCS)", "VCK (PCS)", "CMD (PCS)"
# ]

# DATETIME_COLS = [
#     "X-RAY STRT DATE & TIME", "X-RAY END DATE & TIME",
#     "X-RAY DT/TIME", "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME"
# ]

# _IST = pytz.timezone("Asia/Kolkata")


# def _clean_awb(val):
#     if not val or str(val).strip().lower() in ("", "nan", "none"):
#         return None
#     s = re.sub(r"\s+", "", str(val).strip())
#     s = re.sub(r"-+", "-", s).replace("-", "")
#     # s = s.rstrip("PA")
#     # keep only digits
#     s = re.sub(r"\D", "", s)

#     if s and len(s) == 10:
#         s = s.zfill(11)
#     return s or None


# def _extract_metadata(df_raw: pd.DataFrame) -> dict:
#     """Extract FROM DATE, TO DATE, Carrier from header rows."""
#     metadata = {}
#     for _, row in df_raw.iterrows():
#         row_vals = row.dropna().astype(str).str.strip().tolist()
#         row_str = " ".join(row_vals)
#         if "FROM DATE" in row_str.upper():
#             for i, val in enumerate(row_vals):
#                 if "FROM DATE" in val.upper() and i + 1 < len(row_vals):
#                     metadata["from_date"] = row_vals[i + 1]
#                 if "TO DATE" in val.upper() and i + 1 < len(row_vals):
#                     metadata["to_date"] = row_vals[i + 1]
#                 if "CARRIER" in val.upper() and i + 1 < len(row_vals):
#                     metadata["carrier"] = row_vals[i + 1]
#     return metadata


# def _parse_month_uploaded(metadata: dict) -> str:
#     """
#     Derive month_uploaded (YYYY-MM) from the FROM DATE in metadata.
#     Falls back to current month if parsing fails.
#     """
#     from_date_str = metadata.get("from_date", "")
#     try:
#         dt = pd.to_datetime(from_date_str, errors="raise")
#         return dt.strftime("%Y-%m")
#     except Exception:
#         return pd.Timestamp.now().strftime("%Y-%m")


# def _find_header_row(df_raw: pd.DataFrame) -> int:
#     """Locate the row index containing the actual column headers."""
#     for i, row in df_raw.iterrows():
#         vals = row.dropna().astype(str).str.upper().str.strip().tolist()
#         if "AWB NO." in vals or "AWB NO" in vals:
#             return i
#     raise ValueError("Could not find header row with 'AWB NO.' column.")


# def _to_utc(val, formats: list) -> datetime | None:
#     """Parse a datetime string using the given formats and convert IST → UTC."""
#     if not val or str(val).strip().lower() in ("", "nan", "none", "nat"):
#         return None
#     s = str(val).strip()
#     for fmt in formats:
#         try:
#             return _IST.localize(datetime.strptime(s, fmt)).astimezone(pytz.utc)
#         except ValueError:
#             continue
#     print(f"Could not parse datetime: {s!r}")
#     return None

# def validate_same_month(metadata: dict):
#     """
#     Ensure FROM DATE and TO DATE belong to same month + same year.

#     Reject:
#         10-Mar-2026 → 10-Apr-2026

#     Allow:
#         01-Mar-2026 → 31-Mar-2026
#     """

#     from_date_str = metadata.get("from_date")
#     to_date_str = metadata.get("to_date")

#     if not from_date_str or not to_date_str:
#         raise ValueError(
#             "FROM DATE or TO DATE missing in report metadata."
#         )

#     try:
#         from_dt = pd.to_datetime(from_date_str, dayfirst=True)
#         to_dt = pd.to_datetime(to_date_str, dayfirst=True)

#     except Exception:
#         raise ValueError(
#             "Unable to parse FROM DATE / TO DATE from report."
#         )

#     if (
#         from_dt.year != to_dt.year
#         or
#         from_dt.month != to_dt.month
#     ):
#         raise ValueError(
#             f"Invalid report period: FROM DATE ({from_dt.date()}) "
#             f"and TO DATE ({to_dt.date()}) must belong to same month."
#         )    


# def clean_import_tp_xray(
#     file_bytes: BytesIO, file_type: str = "excel"
# ) -> tuple[pd.DataFrame, dict]:
#     """
#     Clean and extract data from the Import TP X-RAY report.

#     - SL.NO. dropped before returning (not stored in DB).
#     - month_uploaded (YYYY-MM from FROM DATE) added to every row.
#     - uploaded_at (stdlib UTC datetime) added to every row.
#     - Dedup on AWB + X-RAY STRT DATE & TIME kept for true duplicates only.
#       Part shipments (different X-RAY START time) are preserved.
#     - All datetimes converted IST → UTC as stdlib datetime (asyncpg-safe).
#     - All NaN/NaT replaced with None at the end.

#     Returns:
#         Tuple of (cleaned DataFrame ready for DB insert, metadata dict).
#     """

#     # ── 1. Read raw file (no header) ─────────────────────────────────────────
#     if file_type == "excel":
#         df_raw = pd.read_excel(file_bytes, header=None, dtype=str)
#     elif file_type == "csv":
#         df_raw = pd.read_csv(file_bytes, header=None, dtype=str)
#     else:
#         raise ValueError("Unsupported file_type. Use 'excel' or 'csv'.")

#     # ── 2. Extract metadata ───────────────────────────────────────────────────
#     metadata = _extract_metadata(df_raw)

#     # validate FROM DATE and TO DATE must belong to same month
#     validate_same_month(metadata)
    
#     month_uploaded = _parse_month_uploaded(metadata)

#     # ── 3. Locate header row ──────────────────────────────────────────────────
#     header_row_idx = _find_header_row(df_raw)

#     # ── 4. Re-read with correct header ───────────────────────────────────────
#     file_bytes.seek(0)
#     if file_type == "excel":
#         df = pd.read_excel(file_bytes, header=header_row_idx, dtype=str)
#     else:
#         df = pd.read_csv(file_bytes, header=header_row_idx, dtype=str)

#     # ── 5. Normalise column names ─────────────────────────────────────────────
#     df.columns = df.columns.str.strip().str.upper()

#     # ── 6. Drop unnamed columns only (keep named cols even if fully empty) ────
#     df = df.loc[:, ~df.columns.str.startswith("UNNAMED")]

#     # ── 7. Rename SL.NO variant ──────────────────────────────────────────────
#     df.columns = [col if col != "SL.NO" else "SL.NO." for col in df.columns]

#     # ── 8. Drop summary / footer rows ────────────────────────────────────────
#     df = df[~df.iloc[:, 0].astype(str).str.upper().str.strip().isin(["TOTAL", "NAN", ""])]
#     df = df.replace(r"^\s*$", np.nan, regex=True)
#     df = df.dropna(how="all")

#     # ── 9. Keep only rows where AWB NO. is non-empty ─────────────────────────
#     if "AWB NO." in df.columns:
#         df = df[df["AWB NO."].astype(str).str.strip().str.len() > 3]

#     # ── 10. Validate required columns ────────────────────────────────────────
#     missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
#     if missing_cols:
#         raise ValueError(f"Missing required columns: {missing_cols}")

#     df = df[REQUIRED_COLUMNS]

#     # ── 11. Strip whitespace ──────────────────────────────────────────────────
#     for col in df.columns:
#         df[col] = df[col].astype(str).str.strip()
#     df = df.replace({"nan": np.nan, "NaN": np.nan, "": np.nan})

#     # ── 12. Clean AWB ─────────────────────────────────────────────────────────
#     df["AWB NO."] = df["AWB NO."].apply(_clean_awb)

#     # ── 13. Cast numeric columns ──────────────────────────────────────────────
#     for col in NUMERIC_COLS:
#         df[col] = pd.to_numeric(df[col], errors="coerce")

#     # ── 14. Parse datetime columns, convert IST → UTC ────────────────────────

#     # "15-04-26 1:40"  or  "15-04-26 1:40:00"  (2-digit year, 24h)
#     xray_formats = [
#         "%d-%m-%y %H:%M",       # 15-04-26 1:40
#         "%d-%m-%y %H:%M:%S",    # 15-04-26 1:40:00
#         "%d-%m-%Y %H:%M",       # 15-04-2026 1:40  (4-digit year fallback)
#          "%d-%m-%Y %I:%M %p",      # 05-03-2026 7:59 AM
#         "%d/%m/%Y %I:%M %p",      # 05/03/2026 7:59 AM
#         "%d-%m-%Y %H:%M:%S",
#         "%Y-%m-%d %H:%M:%S",
#     ]
#     for col in ["X-RAY STRT DATE & TIME", "X-RAY END DATE & TIME", "X-RAY DT/TIME"]:
#         df[col] = df[col].apply(lambda x: _to_utc(x, xray_formats))

#     # "14APR2026 2338"
#     rcs_formats = ["%d%b%Y %H%M"]
#     df["RCS/RCF/RCT DT/TIME"] = df["RCS/RCF/RCT DT/TIME"].apply(
#         lambda x: _to_utc(x, rcs_formats)
#     )

#     # "14-Apr-26"  (date only → midnight IST)
#     uplifting_formats = [
#         "%d-%b-%y",     # 14-Apr-26
#         "%d-%b-%Y",     # 14-Apr-2026 fallback
#         "%d-%m-%Y",
#         "%d/%m/%Y",
#           "%Y-%m-%d %H:%M:%S",
#     ]
#     df["UPLIFTING DT/TIME"] = df["UPLIFTING DT/TIME"].apply(
#         lambda x: _to_utc(x, uplifting_formats)
#     )

#     # ── 15. Standardise text columns ─────────────────────────────────────────
#     text_cols = [c for c in REQUIRED_COLUMNS if c not in NUMERIC_COLS + DATETIME_COLS]
#     for col in text_cols:
#         df[col] = df[col].astype(str).str.strip().replace({"NAN": np.nan})

#     # ── 16. Drop rows missing AWB ─────────────────────────────────────────────
#     df = df.dropna(subset=["AWB NO."])

#     # ── 17. Dedup: same AWB + same X-RAY START TIME = true duplicate
#     #         Different X-RAY START TIME = part shipment → KEEP BOTH
#     # df = df.drop_duplicates(subset=["AWB NO.", "X-RAY STRT DATE & TIME"])

#     # ── 18. Drop SL.NO. — not stored in DB ───────────────────────────────────
#     df = df.drop(columns=["SL.NO."], errors="ignore")

#     # ── 19. Attach metadata columns ──────────────────────────────────────────
#     df["month_uploaded"] = month_uploaded           # e.g. "2026-04"
#     df["uploaded_at"]    = datetime.now(tz=timezone.utc)   # stdlib UTC — asyncpg-safe

#     # ── 20. Final cleanup — NaN / NaT → None (DB compatible) ─────────────────
#     df = df.replace({np.nan: None, pd.NaT: None})
#     df = df.reset_index(drop=True)

#     return df, metadata










import re
from datetime import datetime, timezone

import pandas as pd
import numpy as np
from io import BytesIO
import pytz

REQUIRED_COLUMNS = [
    "SL.NO.", "AWB NO.", "ORGIN", "DESTINATION", "PCS.", "GROSS WT", "CHG WT",
    "NOG", "SHC",
    "X-RAY STRT DATE & TIME", "X-RAY END DATE & TIME",
    "X-RAY TYPE", "X-RAY DT/TIME", "X-RAY-USER",
    "PHS (PCS)", "ETD (PCS)", "EDS (PCS)", "EDD (PCS)", "VCK (PCS)", "CMD (PCS)",
    "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME", "FLT NO",
    "AGENT NAME", "SERIAL NO.", "DEVICE MODEL NO.", "REMARKS"
]

NUMERIC_COLS = [
    "PCS.", "GROSS WT", "CHG WT",
    "PHS (PCS)", "ETD (PCS)", "EDS (PCS)",
    "EDD (PCS)", "VCK (PCS)", "CMD (PCS)"
]

DATETIME_COLS = [
    "X-RAY STRT DATE & TIME", "X-RAY END DATE & TIME",
    "X-RAY DT/TIME", "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME"
]

_IST = pytz.timezone("Asia/Kolkata")

def _clean_awb(val):
    if not val or str(val).strip().lower() in ("", "nan", "none"):
        return None
    s = re.sub(r"\s+", "", str(val).strip())
    s = re.sub(r"-+", "-", s).replace("-", "")
    # s = s.rstrip("PA")
    
    # keep only digits
    s = re.sub(r"\D", "", s)
    
    if s and len(s) == 10:
        s = s.zfill(11)
    return s or None


def _extract_metadata(df_raw: pd.DataFrame) -> dict:
    """Extract FROM DATE, TO DATE, Carrier from header rows."""
    metadata = {}
    for _, row in df_raw.iterrows():
        row_vals = row.dropna().astype(str).str.strip().tolist()
        row_str = " ".join(row_vals)
        if "FROM DATE" in row_str.upper():
            for i, val in enumerate(row_vals):
                if "FROM DATE" in val.upper() and i + 1 < len(row_vals):
                    metadata["from_date"] = row_vals[i + 1]
                if "TO DATE" in val.upper() and i + 1 < len(row_vals):
                    metadata["to_date"] = row_vals[i + 1]
                if "CARRIER" in val.upper() and i + 1 < len(row_vals):
                    metadata["carrier"] = row_vals[i + 1]
    return metadata


def _parse_month_uploaded(metadata: dict) -> str:
    """
    Derive month_uploaded (YYYY-MM) from the FROM DATE in metadata.
    Falls back to current month if parsing fails.
    """
    from_date_str = metadata.get("from_date", "")
    try:
        dt = pd.to_datetime(from_date_str,  errors="raise")
        return dt.strftime("%Y-%m")
    except Exception:
        return pd.Timestamp.now().strftime("%Y-%m")


def _find_header_row(df_raw: pd.DataFrame) -> int:
    """Locate the row index containing the actual column headers."""
    for i, row in df_raw.iterrows():
        vals = row.dropna().astype(str).str.upper().str.strip().tolist()
        if "AWB NO." in vals or "AWB NO" in vals:
            return i
    raise ValueError("Could not find header row with 'AWB NO.' column.")


def _to_utc(val, formats: list) -> pd.Timestamp:
    """Parse a datetime string using the given formats and convert IST \u2192 UTC, returning a pd.Timestamp."""
    if not val or str(val).strip().lower() in ("", "nan", "none", "nat"):
        return pd.NaT
    s = str(val).strip()

    parsed_dt = None
    # Try parsing with explicit formats using pandas.to_datetime for robustness
    for fmt in formats:
        try:
            temp_dt = pd.to_datetime(s, format=fmt, errors='coerce')
            if pd.notna(temp_dt):
                parsed_dt = temp_dt.to_pydatetime()
                break
        except Exception:
            continue

    # If explicit formats fail, try general pandas parsing
    if parsed_dt is None:
        try:
            # Use dayfirst=True as a common convention.
            temp_dt = pd.to_datetime(s, errors='coerce', dayfirst=True)
            if pd.notna(temp_dt):
                parsed_dt = temp_dt.to_pydatetime()
        except Exception:
            return pd.NaT

    if parsed_dt is None:
        return pd.NaT

    # Handle timezone localization and conversion
    if parsed_dt.tzinfo is None:
        # If naive, localize to IST and then convert to UTC
        local_dt = _IST.localize(parsed_dt, is_dst=None) # is_dst=None to handle ambiguous times
        utc_dt = local_dt.astimezone(pytz.utc)
    else:
        # If already timezone-aware, just convert to UTC
        utc_dt = parsed_dt.astimezone(pytz.utc)

    return pd.Timestamp(utc_dt) # Return pd.Timestamp directly

def validate_same_month(metadata: dict):
    """
    Ensure FROM DATE and TO DATE belong to same month + same year.

    Reject:
        10-Mar-2026 → 10-Apr-2026

    Allow:
        01-Mar-2026 → 31-Mar-2026
    """

    from_date_str = metadata.get("from_date")
    to_date_str = metadata.get("to_date")

    if not from_date_str or not to_date_str:
        raise ValueError(
            "FROM DATE or TO DATE missing in report metadata."
        )

    try:
        from_dt = pd.to_datetime(from_date_str)
        to_dt = pd.to_datetime(to_date_str)

    except Exception:
        raise ValueError(
            "Unable to parse FROM DATE / TO DATE from report."
        )

    if (
        from_dt.year != to_dt.year
        or
        from_dt.month != to_dt.month
    ):
        raise ValueError(
            f"Invalid report period: FROM DATE ({from_dt.date()}) "
            f"and TO DATE ({to_dt.date()}) must belong to same month."
        )    


def clean_import_tp_xray(
    file_bytes: BytesIO, file_type: str = "excel"
) -> tuple[pd.DataFrame, dict]:
  

    # \u2500\u2500 1. Read raw file (no header) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    if file_type == "excel":
        df_raw = pd.read_excel(file_bytes, header=None, dtype=str)
    elif file_type == "csv":
        df_raw = pd.read_csv(file_bytes, header=None, dtype=str)
    else:
        raise ValueError("Unsupported file_type. Use 'excel' or 'csv'.")

    # \u2500\u2500 2. Extract metadata \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    metadata = _extract_metadata(df_raw)

    # validate FROM DATE and TO DATE must belong to same month
    validate_same_month(metadata)
    print(metadata)
    month_uploaded = _parse_month_uploaded(metadata)

    # \u2500\u2500 3. Locate header row \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    header_row_idx = _find_header_row(df_raw)

    # \u2500\u2500 4. Re-read with correct header \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    file_bytes.seek(0)
    if file_type == "excel":
        df = pd.read_excel(file_bytes, header=header_row_idx, dtype=str)
    else:
        df = pd.read_csv(file_bytes, header=header_row_idx, dtype=str)

    # \u2500\u2500 5. Normalise column names \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    df.columns = df.columns.str.strip().str.upper()

    # \u2500\u2500 6. Drop unnamed columns only (keep named cols even if fully empty) \u2500\u2500\u2500\u2500\u2500\n
    df = df.loc[:, ~df.columns.str.startswith("UNNAMED")]

    # \u2500\u2500 7. Rename SL.NO variant \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    df.columns = [col if col != "SL.NO" else "SL.NO." for col in df.columns]

    # \u2500\u2500 8. Drop summary / footer rows \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    df = df[~df.iloc[:, 0].astype(str).str.upper().str.strip().isin(["TOTAL", "NAN", ""])].copy()
    df = df.replace(r"^\s*$", np.nan, regex=True)
    df = df.dropna(how="all")

    # \u2500\u2500 9. Keep only rows where AWB NO. is non-empty \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    if "AWB NO." in df.columns:
        df = df[df["AWB NO."].astype(str).str.strip().str.len() > 3]

    # \u2500\u2500 10. Validate required columns \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    df = df[REQUIRED_COLUMNS]

    # \u2500\u2500 11. Strip whitespace \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    df = df.replace({"nan": np.nan, "NaN": np.nan, "": np.nan})

    # \u2500\u2500 12. Clean AWB \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    df["AWB NO."] = df["AWB NO."].apply(_clean_awb)

    # \u2500\u2500 13. Cast numeric columns \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # \u2500\u2500 14. Parse datetime columns, convert IST \u2192 UTC \u2500\u2500\u2500\u2500\u2500\n
    # "15-04-26 1:40"  or  "15-04-26 1:40:00"  (2-digit year, 24h)
    xray_formats = [
        "%d-%m-%y %H:%M",       # 15-04-26 1:40
        "%d-%m-%y %H:%M:%S",    # 15-04-26 1:40:00
        "%d-%m-%Y %H:%M",       # 15-04-2026 1:40  (4-digit year fallback)
         "%d-%m-%Y %I:%M %p",      # 05-03-2026 7:59 AM
        "%d/%m/%Y %I:%M %p",      # 05/03/2026 7:59 AM
        "%d-%m-%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d%b%Y %H%M"           # Added this format for X-RAY END DATE & TIME and X-RAY DT/TIME
    ]
    for col in ["X-RAY STRT DATE & TIME", "X-RAY END DATE & TIME", "X-RAY DT/TIME"]:
        df[col] = pd.to_datetime(df[col].apply(lambda x: _to_utc(x, xray_formats)), errors='coerce', utc=True)
        # print(f"After X-RAY conversion for {col}: {df[col].dtype}")

    # "14APR2026 2338"
    rcs_formats = ["%d%b%Y %H%M"]
    df["RCS/RCF/RCT DT/TIME"] = pd.to_datetime(df["RCS/RCF/RCT DT/TIME"].apply(
        lambda x: _to_utc(x, rcs_formats)
    ), errors='coerce', utc=True)
    # print(f"After RCS/RCF/RCT conversion: {df['RCS/RCF/RCT DT/TIME'].dtype}")

    # "14-Apr-26"  (date only \u2192 midnight IST)
    uplifting_formats = [
        "%d-%b-%y",     # 14-Apr-26
        "%d-%b-%Y",     # 14-Apr-2026 fallback
        "%d-%m-%Y",
        "%d/%m/%Y",
          "%Y-%m-%d %H:%M:%S",
    ]
    df["UPLIFTING DT/TIME"] = pd.to_datetime(df["UPLIFTING DT/TIME"].apply(
        lambda x: _to_utc(x, uplifting_formats)
    ), errors='coerce', utc=True)
    # print(f"After UPLIFTING conversion: {df['UPLIFTING DT/TIME'].dtype}")

    # \u2500\u2500 15. Standardise text columns \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    text_cols = [c for c in REQUIRED_COLUMNS if c not in NUMERIC_COLS + DATETIME_COLS]
    for col in text_cols:
        df[col] = df[col].astype(str).str.strip().replace({"NAN": np.nan})

    # \u2500\u2500 16. Drop rows missing AWB \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    df = df.dropna(subset=["AWB NO."])

    # \u2500\u2500 17. Dedup: same AWB + same X-RAY STRT DATE & TIME = true duplicate
    #         Different X-RAY STRT DATE & TIME = part shipment \u2192 KEEP BOTH
    # df = df.drop_duplicates(subset=["AWB NO.", "X-RAY STRT DATE & TIME"])

    # \u2500\u2500 18. Drop SL.NO. \u2014 not stored in DB \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    df = df.drop(columns=["SL.NO."], errors="ignore")

    # \u2500\u2500 19. Attach metadata columns \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n
    df["month_uploaded"] = month_uploaded           # e.g. "2026-04"
    df["uploaded_at"]    = datetime.now(tz=timezone.utc)   # stdlib UTC \u2014 asyncpg-safe

    # \u2500\u2500 20. Final cleanup \u2500\u2500\u2500\u2500\u2500\n
    df = df.replace({np.nan: None, pd.NaT: None})
    df = df.reset_index(drop=True)

    return df, metadata