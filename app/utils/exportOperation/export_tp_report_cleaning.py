# import re

# import pandas as pd
# import numpy as np
# from io import BytesIO

# REQUIRED_COLUMNS = [
#     "SL.NO.", "AWB NO.", "ORGIN", "DESTINATION", "PCS.", "GROSS WT", "CHG WT",
#     "NOG", "SHC", "X-RAY START DATE & TIME", "X-RAY END DATE & TIME",
#     "X-RAY TYPE", "X-RAY DT/TIME", "X-RAY-USER", "DOC ACCPT DT/ TIME",
#     "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME", "FLT NO",
#     "AGENT NAME", "SERIAL NO.", "DEVICE MODEL NO."
# ]

# NUMERIC_COLS = ["PCS.", "GROSS WT", "CHG WT"]

# DATETIME_COLS = [
#     "X-RAY START DATE & TIME", "X-RAY END DATE & TIME",
#     "DOC ACCPT DT/ TIME", "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME"
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


# def clean_export_tp_xray(file_bytes: BytesIO, file_type: str = "excel") -> tuple[pd.DataFrame, dict]:
#     """
#     Clean and extract data from the Export TP X-RAY report.

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

#     # 6️⃣ Drop unnamed / fully-empty columns
#     df = df.loc[:, ~df.columns.str.startswith("UNNAMED")]
#     df = df.dropna(axis=1, how="all")

#     # 7️⃣ Rename Sl.No. column if present
#     df.columns = [col if col != "SL.NO" else "SL.NO." for col in df.columns]

#     # 8️⃣ Drop summary / footer rows (e.g., TOTAL row)
#     df = df[~df.iloc[:, 0].astype(str).str.upper().str.strip().isin(["TOTAL", "NAN", ""])]
#     df = df.replace(r"^\s*$", np.nan, regex=True)
#     df = df.dropna(how="all")

#     # 9️⃣ Keep only rows where AWB NO. looks like a valid AWB (digits/dashes)
    

#     # 🔟 Validate required columns
#     missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
#     if missing_cols:
#         raise ValueError(f"Missing required columns: {missing_cols}")

#     df = df[REQUIRED_COLUMNS]

#     # 1️⃣1️⃣ Strip whitespace from all string columns
#     for col in df.columns:
#         df[col] = df[col].astype(str).str.strip()

#     df = df.replace({"nan": np.nan, "NaN": np.nan, "": np.nan})

#     # ✅ Clean AWB properly
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
#     df = df.drop_duplicates(subset=["AWB NO.", "X-RAY START DATE & TIME"])

#     df = df.reset_index(drop=True)

#     return df, metadata


# # # ── Quick smoke-test ────────────────────────────────────────────────────────
# # if __name__ == "__main__":
# #     FILE_PATH = "Export_tp.xlsx"

# #     with open(FILE_PATH, "rb") as f:
# #         data = BytesIO(f.read())

# #     df_clean, meta = clean_export_tp_xray(data, file_type="excel")

# #     print("Metadata:", meta)
# #     print(f"Rows extracted: {len(df_clean)}")
# #     print(df_clean.head(3).to_string())
# #     # print("\nDtypes:\n", df_clean.dtypes)





































# from datetime import datetime, timezone
# import re

# import pandas as pd
# import numpy as np
# from io import BytesIO

# import pytz

# from app.services.export_slot_file_upload_service import get_utc_now

# REQUIRED_COLUMNS = [
#     "SL.NO.", "AWB NO.", "ORGIN", "DESTINATION", "PCS.", "GROSS WT", "CHG WT",
#     "NOG", "SHC", "X-RAY START DATE & TIME", "X-RAY END DATE & TIME",
#     "X-RAY TYPE", "X-RAY DT/TIME", "X-RAY-USER", "DOC ACCPT DT/ TIME",
#     "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME", "FLT NO",
#     "AGENT NAME", "SERIAL NO.", "DEVICE MODEL NO."
# ]

# NUMERIC_COLS = ["PCS.", "GROSS WT", "CHG WT"]

# DATETIME_COLS = [
#     "X-RAY START DATE & TIME", "X-RAY END DATE & TIME","X-RAY DT/TIME",
#     "DOC ACCPT DT/ TIME", "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME"
# ]


# def _clean_awb(val):
#     if not val or str(val).strip().lower() in ("", "nan", "none"):
#         return None
#     s = re.sub(r"\s+", "", str(val).strip())
#     s = re.sub(r"-+", "-", s).replace("-", "")
#     s = s.rstrip("PA")
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
#         dt = pd.to_datetime(from_date_str,  errors="raise")
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


# def convert_to_utc(dt_value, formats):
#     try:
#         if pd.isna(dt_value) or str(dt_value).strip() in ["", "nan", "None", "NaT"]:
#             return None

#         dt_str = str(dt_value).strip()

#         parsed_dt = None
#         for fmt in formats:
#             try:
#                 parsed_dt = datetime.strptime(dt_str, fmt)
#                 break
#             except ValueError:
#                 continue

#         if parsed_dt is None:
#             print(f"Could not parse datetime: {dt_str}")
#             return None

#         # Convert IST → UTC
#         local_dt = pytz.timezone("Asia/Kolkata").localize(parsed_dt)
#         utc_dt = local_dt.astimezone(pytz.utc)

#         return utc_dt

#     except Exception as e:
#         print(f"Datetime conversion error: {dt_value}, error: {e}")
#         return None
    

# def clean_export_tp_xray(
#     file_bytes: BytesIO, file_type: str = "excel"
# ) -> tuple[pd.DataFrame, dict]:
#     """
#     Clean and extract data from the Export TP X-RAY report.

#     Changes vs original:
#     - SL.NO. is parsed but dropped before returning (not stored in DB).
#     - month_uploaded (YYYY-MM from FROM DATE) added to every row.
#     - uploaded_at (server UTC timestamp) added to every row.
#     - Dedup kept on AWB NO. + X-RAY START DATE & TIME (true duplicates only).
#       Part shipments with different X-RAY START times are preserved.

#     Returns:
#         Tuple of (cleaned DataFrame ready for DB insert, metadata dict).
#     """
#     # ── 1. Read raw file (no header) ────────────────────────────────────────
#     if file_type == "excel":
#         df_raw = pd.read_excel(file_bytes, header=None, dtype=str)
#     elif file_type == "csv":
#         df_raw = pd.read_csv(file_bytes, header=None, dtype=str)
#     else:
#         raise ValueError("Unsupported file_type. Use 'excel' or 'csv'.")

#     # ── 2. Extract metadata ──────────────────────────────────────────────────
#     metadata = _extract_metadata(df_raw)
#     month_uploaded = _parse_month_uploaded(metadata)
#     uploaded_at = get_utc_now()

#     # ── 3. Locate header row ─────────────────────────────────────────────────
#     header_row_idx = _find_header_row(df_raw)

#     # ── 4. Re-read with correct header ──────────────────────────────────────
#     file_bytes.seek(0)
#     if file_type == "excel":
#         df = pd.read_excel(file_bytes, header=header_row_idx, dtype=str)
#     else:
#         df = pd.read_csv(file_bytes, header=header_row_idx, dtype=str)

#     # ── 5. Normalise column names ────────────────────────────────────────────
#     df.columns = df.columns.str.strip().str.upper()

#     # ── 6. Drop unnamed / fully-empty columns ───────────────────────────────
#     df = df.loc[:, ~df.columns.str.startswith("UNNAMED")]
#     df = df.dropna(axis=1, how="all")

#     # ── 7. Rename SL.NO variant ─────────────────────────────────────────────
#     df.columns = [col if col != "SL.NO" else "SL.NO." for col in df.columns]

#     # ── 8. Drop summary / footer rows ───────────────────────────────────────
#     df = df[~df.iloc[:, 0].astype(str).str.upper().str.strip().isin(["TOTAL", "NAN", ""])]
#     df = df.replace(r"^\s*$", np.nan, regex=True)
#     df = df.dropna(how="all")

#     # ── 9. Validate required columns ────────────────────────────────────────
#     missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
#     if missing_cols:
#         raise ValueError(f"Missing required columns: {missing_cols}")

#     df = df[REQUIRED_COLUMNS]

#     # ── 10. Strip whitespace ─────────────────────────────────────────────────
#     for col in df.columns:
#         df[col] = df[col].astype(str).str.strip()
#     df = df.replace({"nan": np.nan, "NaN": np.nan, "": np.nan})

#     # ── 11. Clean AWB ────────────────────────────────────────────────────────
#     df["AWB NO."] = df["AWB NO."].apply(_clean_awb)

#     # ── 12. Cast numeric columns ─────────────────────────────────────────────
#     for col in NUMERIC_COLS:
#         df[col] = pd.to_numeric(df[col], errors="coerce")

#     # ── 13. Parse datetime columns ───────────────────────────────────────────
#     # for col in DATETIME_COLS:
#     #     df[col] = pd.to_datetime(df[col], errors="coerce", format="mixed", dayfirst=True)

#     # ── 13. Parse datetime columns and localize to UTC ───────────────────────
#     # ── 13. Parse datetime columns, convert IST → UTC, replace NaT with None ────

#     # X-RAY START + END

#     xray_formats = [
#         "%d-%m-%Y %I:%M:%S %p",   # 05-03-2026 7:59:00 AM
#         "%d-%m-%Y %I:%M %p",      # 05-03-2026 7:59 AM
#         "%d/%m/%Y %I:%M %p",      # 05/03/2026 7:59 AM
#           "%Y-%m-%d %H:%M:%S", 
#     ]

#     for col in ["X-RAY START DATE & TIME", "X-RAY END DATE & TIME"]:
#         df[col] = df[col].apply(
#             lambda x: convert_to_utc(x, xray_formats)
#         )


#     # UPLIFTING DATE

#     uplifting_formats = [
#         "%d-%m-%Y",
#         "%d/%m/%Y",
#          "%Y-%m-%d %H:%M:%S",
#     ]

#     df["UPLIFTING DT/TIME"] = df["UPLIFTING DT/TIME"].apply(
#         lambda x: convert_to_utc(x, uplifting_formats)
#     )


#     # DOC ACCEPT / RCS / X-RAY DT

#     format_2_formats = [
#         "%d%b%Y %H%M",   # 05MAR2026 1340
#     ]

#     for col in [
#         "DOC ACCPT DT/ TIME",
#         "RCS/RCF/RCT DT/TIME",
#         "X-RAY DT/TIME",
#     ]:
#         df[col] = df[col].apply(
#             lambda x: convert_to_utc(x, format_2_formats)
#         )

#     # # A) X-RAY START + END → format like:
#     # # 05-03-2026 7:59:00 AM

#     # xray_datetime_cols = [
#     #     "X-RAY START DATE & TIME",
#     #     "X-RAY END DATE & TIME",
#     # ]

#     # for col in xray_datetime_cols:
#     #     parsed = pd.to_datetime(
#     #         df[col],
#     #         format="%d-%m-%Y %I:%M:%S %p",
#     #         errors="coerce"
#     #     )

#     #     parsed = parsed.dt.tz_localize("Asia/Kolkata").dt.tz_convert("UTC")

#     #     df[col] = parsed.apply(
#     #         lambda x: None if pd.isna(x) else x.to_pydatetime()
#     #     )


#     # # B) UPLIFTING DT/TIME → format like:
#     # # 06-03-2026 (date only)

#     # parsed = pd.to_datetime(
#     #     df["UPLIFTING DT/TIME"],
#     #     format="%d-%m-%Y",
#     #     errors="coerce"
#     # )

#     # parsed = parsed.dt.tz_localize("Asia/Kolkata").dt.tz_convert("UTC")

#     # df["UPLIFTING DT/TIME"] = parsed.apply(
#     #     lambda x: None if pd.isna(x) else x.to_pydatetime()
#     # )

#     # # Format 2 → "05MAR2026 1340"
#     # format_2_cols = [
#     #     "DOC ACCPT DT/ TIME",
#     #     "RCS/RCF/RCT DT/TIME",
#     #     "X-RAY DT/TIME",
#     # ]
#     # for col in format_2_cols:
#     #     parsed = pd.to_datetime(df[col], errors="coerce", format="%d%b%Y %H%M")
#     #     parsed = parsed.dt.tz_localize("Asia/Kolkata").dt.tz_convert("UTC")
#     #     df[col] = parsed.apply(lambda x: None if pd.isna(x) else x.to_pydatetime())

#     # ── 14. Standardise text columns ─────────────────────────────────────────
#     text_cols = [c for c in REQUIRED_COLUMNS if c not in NUMERIC_COLS + DATETIME_COLS]
#     for col in text_cols:
#         df[col] = df[col].astype(str).str.strip().replace({"NAN": np.nan})

#     # ── 15. Drop rows missing AWB ─────────────────────────────────────────────
#     df = df.dropna(subset=["AWB NO."])

#     # ── 16. Dedup: same AWB + same X-RAY START TIME = true duplicate ──────────
#     #         Different X-RAY START TIME = part shipment → KEEP BOTH
#     # df = df.drop_duplicates(subset=["AWB NO.", "X-RAY START DATE & TIME"])

#     # ── 17. Drop SL.NO. — not stored in DB ───────────────────────────────────
#     df = df.drop(columns=["SL.NO."], errors="ignore")

#     # ── 18. Attach metadata columns ──────────────────────────────────────────
#     df["month_uploaded"] = month_uploaded   # e.g. "2025-03"
#     df["uploaded_at"] =  datetime.now(tz=timezone.utc)          # UTC timestamp of this upload


#     df = df.replace({np.nan: None, pd.NaT: None})
#     print(df["X-RAY START DATE & TIME"].head(20))
#     print(df["X-RAY END DATE & TIME"].head(20))
#     df = df.reset_index(drop=True)
#     return df, metadata












































from datetime import datetime, timezone
import re

import pandas as pd
import numpy as np
from io import BytesIO

import pytz

# Mocking get_utc_now for demonstration purposes as it's from an app service
def get_utc_now():
    return datetime.now(tz=timezone.utc)

REQUIRED_COLUMNS = [
    "SL.NO.", "AWB NO.", "ORGIN", "DESTINATION", "PCS.", "GROSS WT", "CHG WT",
    "NOG", "SHC", "X-RAY START DATE & TIME", "X-RAY END DATE & TIME",
    "X-RAY TYPE", "X-RAY DT/TIME", "X-RAY-USER", "DOC ACCPT DT/ TIME",
    "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME", "FLT NO",
    "AGENT NAME", "SERIAL NO.", "DEVICE MODEL NO."
]

NUMERIC_COLS = ["PCS.", "GROSS WT", "CHG WT"]

DATETIME_COLS = [
    "X-RAY START DATE & TIME", "X-RAY END DATE & TIME","X-RAY DT/TIME",
    "DOC ACCPT DT/ TIME", "RCS/RCF/RCT DT/TIME", "UPLIFTING DT/TIME"
]

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


def convert_to_utc(dt_value, formats):
    try:
        if pd.isna(dt_value) or str(dt_value).strip() in ["", "nan", "None", "NaT"]:
            return None

        dt_str = str(dt_value).strip()

        parsed_dt = None
        for fmt in formats:
            try:
                parsed_dt = datetime.strptime(dt_str, fmt)
                break
            except ValueError:
                continue

        if parsed_dt is None:
            # If still not parsed, try parsing with mixed format
            try:
                parsed_dt = pd.to_datetime(dt_str, errors='coerce', dayfirst=True).to_pydatetime()
                if parsed_dt is None:
                    raise ValueError(f"Could not parse datetime: {dt_str}")
            except (ValueError, TypeError):
                print(f"Could not parse datetime after all attempts: {dt_str}")
                return None

        # Convert IST \u2192 UTC
        local_dt = pytz.timezone("Asia/Kolkata").localize(parsed_dt)
        utc_dt = local_dt.astimezone(pytz.utc)

        return utc_dt

    except Exception as e:
        print(f"Datetime conversion error: {dt_value}, error: {e}")
        return None

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
        # print(from_dt)
        # print(to_dt)

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

def clean_export_tp_xray(
    file_bytes: BytesIO, file_type: str = "excel"
) -> tuple[pd.DataFrame, dict]:
    """
    Clean and extract data from the Export TP X-RAY report.

    Changes vs original:
    - SL.NO. is parsed but dropped before returning (not stored in DB).
    - month_uploaded (YYYY-MM from FROM DATE) added to every row.
    - uploaded_at (server UTC timestamp) added to every row.
    - Dedup kept on AWB NO. + X-RAY START DATE & TIME (true duplicates only).
      Part shipments with different X-RAY START times are preserved.

    Returns:
        Tuple of (cleaned DataFrame ready for DB insert, metadata dict).
    """
    # \u2500\u2500 1. Read raw file (no header) \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
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
    month_uploaded = _parse_month_uploaded(metadata)
    uploaded_at = get_utc_now()

    # \u2500\u2500 3. Locate header row \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    header_row_idx = _find_header_row(df_raw)

    # \u2500\u2500 4. Re-read with correct header \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    file_bytes.seek(0)
    if file_type == "excel":
        df = pd.read_excel(file_bytes, header=header_row_idx, dtype=str)
    else:
        df = pd.read_csv(file_bytes, header=header_row_idx, dtype=str)

    # \u2500\u2500 5. Normalise column names \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    df.columns = df.columns.str.strip().str.upper()

    # \u2500\u2500 6. Drop unnamed / fully-empty columns \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    df = df.loc[:, ~df.columns.str.startswith("UNNAMED")]
    df = df.dropna(axis=1, how="all")

    # \u2500\u2500 7. Rename SL.NO variant \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    df.columns = [col if col != "SL.NO" else "SL.NO." for col in df.columns]

    # \u2500\u2500 8. Drop summary / footer rows \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    df = df[~df.iloc[:, 0].astype(str).str.upper().str.strip().isin(["TOTAL", "NAN", ""])].copy()
    df = df.replace(r"^\s*$", np.nan, regex=True)
    df = df.dropna(how="all")

    # \u2500\u2500 9. Validate required columns \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    df = df[REQUIRED_COLUMNS].copy()

    # \u2500\u2500 10. Strip whitespace \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    df = df.replace({"nan": np.nan, "NaN": np.nan, "": np.nan})

    # \u2500\u2500 11. Clean AWB \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    df["AWB NO."] = df["AWB NO."].apply(_clean_awb)

    # \u2500\u2500 12. Cast numeric columns \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # \u2500\u2500 13. Parse datetime columns, convert IST \u2192 UTC, replace NaT with None \u2500\u2500\u2500\u2500\n
    # X-RAY START + END
    xray_formats = [
        "%d-%m-%Y %I:%M:%S %p",   # 05-03-2026 7:59:00 AM
        "%d-%m-%Y %I:%M %p",      # 05-03-2026 7:59 AM
        "%d/%m/%Y %I:%M %p",      # 05/03/2026 7:59 AM
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%y %H:%M"        # Added for formats like 09-03-26 15:14
    ]

    for col in ["X-RAY START DATE & TIME", "X-RAY END DATE & TIME"]:
        df[col] = df[col].apply(
            lambda x: convert_to_utc(x, xray_formats)
        )


    # UPLIFTING DATE
    uplifting_formats = [
        "%d-%m-%Y",
        "%d/%m/%Y",
        "%Y-%m-%d %H:%M:%S",
        "%d-%b-%y"            # Added for formats like 09-Mar-26
    ]

    df["UPLIFTING DT/TIME"] = df["UPLIFTING DT/TIME"].apply(
        lambda x: convert_to_utc(x, uplifting_formats)
    )


    # DOC ACCEPT / RCS / X-RAY DT
    format_2_formats = [
        "%d%b%Y %H%M",   # 05MAR2026 1340
    ]

    for col in [
        "DOC ACCPT DT/ TIME",
        "RCS/RCF/RCT DT/TIME",
        "X-RAY DT/TIME",
    ]:
        df[col] = df[col].apply(
            lambda x: convert_to_utc(x, format_2_formats)
        )

    # \u2500\u2500 14. Standardise text columns \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    text_cols = [c for c in REQUIRED_COLUMNS if c not in NUMERIC_COLS + DATETIME_COLS]
    for col in text_cols:
        df[col] = df[col].astype(str).str.strip().replace({"NAN": np.nan})

    # \u2500\u2500 15. Drop rows missing AWB \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    df = df.dropna(subset=["AWB NO."])

    # \u2500\u2500 16. Dedup: same AWB + same X-RAY START TIME = true duplicate \u2500\u2500\u2500\n    #         Different X-RAY START TIME = part shipment \u2192 KEEP BOTH
    # df = df.drop_duplicates(subset=["AWB NO.", "X-RAY START DATE & TIME"])

    # \u2500\u2500 17. Drop SL.NO. \u2014 not stored in DB \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    df = df.drop(columns=["SL.NO."], errors="ignore")

    # \u2500\u2500 18. Attach metadata columns \u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\u2500\n    
    df["month_uploaded"] = month_uploaded   # e.g. "2025-03"
    df["uploaded_at"] =  datetime.now(tz=timezone.utc)          # UTC timestamp of this upload


    df = df.replace({np.nan: None, pd.NaT: None})
    # print(df["X-RAY START DATE & TIME"].head(20))
    # print(df["X-RAY END DATE & TIME"].head(20))
    df = df.reset_index(drop=True)
    return df, metadata