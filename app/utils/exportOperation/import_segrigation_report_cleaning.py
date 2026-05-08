






























# import re
# import pytz
# import numpy as np
# import pandas as pd
# from io import BytesIO
# from datetime import datetime, timezone

# # ── Constants ────────────────────────────────────────────────────────────────

# BILLING_SHC_FILTER = {"TRM", "TPV"}

# REQUIRED_COLUMNS = [
#     "Flight No.", "Flight Date", "AWB No", "SFX",
#     "ATA_Date/Time", "FLT DOC Arrival_Date/Time",
#     "Last ULD Arrival Date & Time", "Bulk ULD Arrival Date & Time",
#     "Org", "DEST",
#     "Manifest Pcs", "Manifest Wgt",
#     "SEG Pcs", "SEG Wgt",
#     "PCS", "Gross weight", "CHG WGT", "Vol(MC)", "No of Houses",
#     "SHC", "CHG SHC", "Billing SHC",
#     "NOG", "Consignee Details",
#     "AWD date", "NFD date", "RCF date",
#     "DO date&time", "TFD date&time",
#     "EGM/IGM_NO", "FLT_COM_DAT_TIM", "FLIGHT STATUS",
# ]

# NUMERIC_COLS = [
#     "Manifest Pcs", "Manifest Wgt",
#     "SEG Pcs", "SEG Wgt",
#     "PCS", "Gross weight", "CHG WGT",
#     "Vol(MC)", "No of Houses",
# ]

# DATETIME_COLS = [
#     "ATA_Date/Time",
#     "FLT DOC Arrival_Date/Time",
#     "Last ULD Arrival Date & Time",
#     "Bulk ULD Arrival Date & Time",
#     "AWD date",
#     "NFD date",
#     "RCF date",
#     "DO date&time",
#     "TFD date&time",
#     "FLT_COM_DAT_TIM",
# ]

# FLIGHT_DATE_COL = "Flight Date"   # date-only column, parsed separately

# _IST = pytz.timezone("Asia/Kolkata")


# # ── Helpers ──────────────────────────────────────────────────────────────────

# def _clean_awb(val) -> str | None:
#     if not val or str(val).strip().lower() in ("", "nan", "none"):
#         return None
#     s = re.sub(r"\s+", "", str(val).strip())
#     s = re.sub(r"-+", "-", s).replace("-", "")
#     s = re.sub(r"\D", "", s)          # digits only
#     if s and len(s) == 10:
#         s = s.zfill(11)
#     return s or None


# def _to_utc(val, formats: list) -> pd.Timestamp:
#     """Parse datetime string (assumed IST) → UTC pd.Timestamp."""
#     if not val or str(val).strip().lower() in ("", "nan", "none", "nat"):
#         return pd.NaT
#     s = str(val).strip()

#     parsed_dt = None
#     for fmt in formats:
#         try:
#             tmp = pd.to_datetime(s, format=fmt, errors="coerce")
#             if pd.notna(tmp):
#                 parsed_dt = tmp.to_pydatetime()
#                 break
#         except Exception:
#             continue

#     if parsed_dt is None:
#         try:
#             tmp = pd.to_datetime(s, errors="coerce", dayfirst=True)
#             if pd.notna(tmp):
#                 parsed_dt = tmp.to_pydatetime()
#         except Exception:
#             return pd.NaT

#     if parsed_dt is None:
#         return pd.NaT

#     if parsed_dt.tzinfo is None:
#         local_dt = _IST.localize(parsed_dt, is_dst=None)
#         utc_dt   = local_dt.astimezone(pytz.utc)
#     else:
#         utc_dt = parsed_dt.astimezone(pytz.utc)

#     return pd.Timestamp(utc_dt)


# def _to_date_utc(val, formats: list) -> pd.Timestamp:
#     """Parse date-only string → midnight IST → UTC pd.Timestamp."""
#     if not val or str(val).strip().lower() in ("", "nan", "none", "nat"):
#         return pd.NaT
#     s = str(val).strip()
#     for fmt in formats:
#         try:
#             tmp = pd.to_datetime(s, format=fmt, errors="coerce")
#             if pd.notna(tmp):
#                 local_dt = _IST.localize(tmp.to_pydatetime(), is_dst=None)
#                 return pd.Timestamp(local_dt.astimezone(pytz.utc))
#         except Exception:
#             continue
#     return pd.NaT


# # ── Metadata ─────────────────────────────────────────────────────────────────

# def _extract_metadata(df_raw: pd.DataFrame) -> dict:
#     """
#     Extract FROM DATE / TO DATE / Carrier from header rows.
#     Handles both:
#       - value embedded in same cell: "FROM DATE :06MAY2026"
#       - value in next cell:          "FROM DATE"  |  "06MAY2026"
#     """
#     metadata = {}
#     for _, row in df_raw.iterrows():
#         row_vals = row.dropna().astype(str).str.strip().tolist()
#         row_str  = " ".join(row_vals).upper()
#         if "FROM DATE" not in row_str and "TO DATE" not in row_str:
#             continue
#         for i, val in enumerate(row_vals):
#             uv = val.upper()
#             # Embedded pattern: "FROM DATE :06MAY2026"
#             m = re.search(r"FROM\s*DATE\s*[:\s]+(\S+)", uv)
#             if m:
#                 metadata["from_date"] = m.group(1).strip(": ")
#             m = re.search(r"TO\s*DATE\s*[:\s]+(\S+)", uv)
#             if m:
#                 metadata["to_date"] = m.group(1).strip(": ")
#             # Fallback: next-cell pattern
#             if "FROM DATE" in uv and "from_date" not in metadata and i + 1 < len(row_vals):
#                 metadata["from_date"] = row_vals[i + 1].strip(": ")
#             if "TO DATE" in uv and "to_date" not in metadata and i + 1 < len(row_vals):
#                 metadata["to_date"] = row_vals[i + 1].strip(": ")
#             if "CARRIER" in uv and i + 1 < len(row_vals):
#                 metadata["carrier"] = row_vals[i + 1].strip(": ")
#     return metadata


# def _parse_month_uploaded(metadata: dict) -> str:
#     from_date_str = metadata.get("from_date", "")
#     try:
#         dt = pd.to_datetime(from_date_str, errors="raise")
#         return dt.strftime("%Y-%m")
#     except Exception:
#         return pd.Timestamp.now().strftime("%Y-%m")


# def validate_same_month(metadata: dict):
#     from_date_str = metadata.get("from_date")
#     to_date_str   = metadata.get("to_date")
#     if not from_date_str or not to_date_str:
#         raise ValueError("FROM DATE or TO DATE missing in report metadata.")
#     try:
#         from_dt = pd.to_datetime(from_date_str)
#         to_dt   = pd.to_datetime(to_date_str)
#     except Exception:
#         raise ValueError("Unable to parse FROM DATE / TO DATE from report.")
#     if from_dt.year != to_dt.year or from_dt.month != to_dt.month:
#         raise ValueError(
#             f"Invalid report period: FROM DATE ({from_dt.date()}) and "
#             f"TO DATE ({to_dt.date()}) must belong to same month."
#         )


# def _find_header_row(df_raw: pd.DataFrame) -> int:
#     for i, row in df_raw.iterrows():
#         vals = row.dropna().astype(str).str.upper().str.strip().tolist()
#         if "AWB NO" in vals or "FLIGHT NO." in vals or "FLIGHT NO" in vals:
#             return i
#     raise ValueError("Could not find header row with 'AWB No' / 'Flight No.' column.")


# def _read_raw_csv(file_bytes: BytesIO) -> pd.DataFrame:
#     """
#     Read CSV with variable column counts into a uniform DataFrame.
#     Pads every row to max_cols width so all rows have the same number of columns.
#     Column names are integers (0, 1, 2, ...).
#     """
#     raw_text = file_bytes.read().decode("utf-8", errors="replace")
#     file_bytes.seek(0)

#     lines     = raw_text.splitlines()
#     max_cols  = max((line.count(",") for line in lines), default=0) + 1

#     rows = []
#     for line in lines:
#         cells = line.split(",")
#         # Pad short rows to max_cols
#         cells += [""] * (max_cols - len(cells))
#         rows.append(cells[:max_cols])

#     return pd.DataFrame(rows, dtype=str)


# # ── Main cleaner ─────────────────────────────────────────────────────────────

# def clean_import_segregation_report(
#     file_bytes: BytesIO,
#     file_type: str = "csv",
# ) -> tuple[pd.DataFrame, dict]:
#     """
#     Parse and clean the Segregation Report (CSV or Excel).
#     Returns only rows where Billing SHC is TRM or TPV.
#     """

#     # ── 1. Read raw file (no header) ─────────────────────────────────────────
#     if file_type == "excel":
#         df_raw = pd.read_excel(file_bytes, header=None, dtype=str)
#     elif file_type == "csv":
#         df_raw = _read_raw_csv(file_bytes)
#     else:
#         raise ValueError("Unsupported file_type. Use 'excel' or 'csv'.")

#     # ── 2. Extract + validate metadata ───────────────────────────────────────
#     metadata       = _extract_metadata(df_raw)
#     validate_same_month(metadata)
#     month_uploaded = _parse_month_uploaded(metadata)
#     print(f"[meta] from={metadata.get('from_date')}  to={metadata.get('to_date')}  month={month_uploaded}")

#     # ── 3. Locate header row ──────────────────────────────────────────────────
#     header_row_idx = _find_header_row(df_raw)
#     print(f"[header] found at raw row index {header_row_idx}")

#     # ── 4. Build df: header row → column names, everything below → data ───────
#     if file_type == "excel":
#         file_bytes.seek(0)
#         df = pd.read_excel(file_bytes, header=header_row_idx, dtype=str)
#         # Excel gives UNNAMED cols for blank header cells — handled in step 5
#         df.columns = [str(c).strip() for c in df.columns]
#     else:
#         # Slice df_raw: header row values become column names
#         header_vals = [str(v).strip() for v in df_raw.iloc[header_row_idx].tolist()]
#         data        = df_raw.iloc[header_row_idx + 1:].copy()
#         data.columns = header_vals
#         df = data.reset_index(drop=True)

#     # ── 5. Drop junk columns ──────────────────────────────────────────────────
#     # After slicing, padding columns are named "" or "nan" or pure integers.
#     # Excel gives "Unnamed: N" style names for blank header cells.
#     # Keep only columns with a real non-empty, non-numeric name.
#     def _is_valid_col(name: str) -> bool:
#         n = name.strip()
#         if not n or n.lower() == "nan":
#             return False
#         if n.upper().startswith("UNNAMED"):
#             return False
#         # Pure integer names are padding artefacts from _read_raw_csv
#         try:
#             int(n)
#             return False
#         except ValueError:
#             return True

#     df = df.loc[:, [c for c in df.columns if _is_valid_col(c)]].copy()

#     # ── 6. Drop subtotal / grand-total / NIL CARRIER rows ────────────────────
#     # NIL CARRIER section: everything from that row onward is footer — drop it
#     nil_mask = df.apply(
#         lambda r: r.fillna("").astype(str).str.upper().str.contains("NIL CARRIER").any(),
#         axis=1,
#     )
#     if nil_mask.any():
#         df = df.loc[: nil_mask.idxmax() - 1]

#     # Subtotal rows: 3rd column (index 2) == "Total"
#     col2 = df.iloc[:, 2].astype(str).str.strip().str.upper()
#     df   = df[col2 != "TOTAL"].copy()

#     # Grand total row
#     grand_mask = df.apply(
#         lambda r: "GRAND TOTAL" in " ".join(r.fillna("").astype(str).str.upper().tolist()),
#         axis=1,
#     )
#     df = df[~grand_mask].copy()

#     # ── 7. Basic cleanup ──────────────────────────────────────────────────────
#     df = df.replace(r"^\s*$", np.nan, regex=True)
#     df = df.dropna(how="all")

#     # ── 8. Keep rows where AWB No is non-empty ────────────────────────────────
#     if "AWB No" in df.columns:
#         df = df[df["AWB No"].astype(str).str.strip().str.len() > 3]

#     # ── 9. Validate required columns ─────────────────────────────────────────
#     missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
#     if missing:
#         raise ValueError(f"Missing required columns: {missing}")

#     df = df[REQUIRED_COLUMNS].copy()

#     # ── 10. Strip whitespace on all cells ────────────────────────────────────
#     for col in df.columns:
#         df[col] = df[col].astype(str).str.strip()
#     df = df.replace({"nan": np.nan, "NaN": np.nan, "": np.nan})

#     # ── 11. Filter: Billing SHC must be TRM or TPV ───────────────────────────
#     df["Billing SHC"] = df["Billing SHC"].astype(str).str.strip().str.upper()
#     df = df[df["Billing SHC"].isin(BILLING_SHC_FILTER)].copy()
#     print(f"[filter] rows after Billing SHC filter (TRM/TPV): {len(df)}")

#     if df.empty:
#         return df, metadata

#     # ── 12. Clean AWB ─────────────────────────────────────────────────────────
#     df["AWB No"] = df["AWB No"].apply(_clean_awb)

#     # ── 13. Cast numeric columns ──────────────────────────────────────────────
#     for col in NUMERIC_COLS:
#         df[col] = pd.to_numeric(df[col], errors="coerce")

#     # ── 14. Parse Flight Date (date-only → midnight IST → UTC) ───────────────
#     flight_date_fmts = [
#         "%d-%b-%y",   # 05-MAY-26
#         "%d-%b-%Y",   # 05-MAY-2026
#         "%d/%m/%y",   # 05/05/26
#         "%d/%m/%Y",   # 05/05/2026
#     ]
#     df[FLIGHT_DATE_COL] = df[FLIGHT_DATE_COL].apply(
#         lambda x: _to_date_utc(x, flight_date_fmts)
#     )
#     df[FLIGHT_DATE_COL] = pd.to_datetime(df[FLIGHT_DATE_COL], errors="coerce", utc=True)

#     # ── 15. Parse all other datetime columns (IST → UTC) ─────────────────────
#     dt_fmts = [
#         "%d/%m/%y %H:%M",      # 05/05/26 22:19
#         "%d/%m/%y %H:%M:%S",   # 06/05/26 00:28:30
#         "%d/%m/%Y %H:%M",
#         "%d/%m/%Y %H:%M:%S",
#         "%d-%b-%y %H:%M",
#         "%d-%b-%Y %H:%M",
#         "%Y-%m-%d %H:%M:%S",
#     ]
#     for col in DATETIME_COLS:
#         df[col] = df[col].apply(lambda x: _to_utc(x, dt_fmts))
#         df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

#     # ── 16. Standardise remaining text columns ────────────────────────────────
#     text_cols = [
#         c for c in REQUIRED_COLUMNS
#         if c not in NUMERIC_COLS + DATETIME_COLS + [FLIGHT_DATE_COL]
#     ]
#     for col in text_cols:
#         s = df[col].astype(str).str.strip()
#         df[col] = s.where(s.str.lower() != "nan", other=np.nan)

#     # ── 17. Drop rows with no valid AWB ──────────────────────────────────────
#     df = df.dropna(subset=["AWB No"])

#     # ── 18. Attach metadata columns ───────────────────────────────────────────
#     df["month_uploaded"] = month_uploaded
#     df["uploaded_at"]    = datetime.now(tz=timezone.utc)

#     # ── 19. Final cleanup ─────────────────────────────────────────────────────
#     # Re-cast all datetime cols to UTC after text cleanup (replace NaN→None
#     # can strip the tz dtype). This ensures proper datetime64[us, UTC] dtype
#     # on all datetime columns going into the DB layer.
#     all_dt_cols = DATETIME_COLS + [FLIGHT_DATE_COL, "uploaded_at"]
#     for col in all_dt_cols:
#         if col in df.columns:
#             df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

#     # Replace remaining NaN/NaT with None for asyncpg compatibility
#     df = df.where(df.notna(), other=None)
#     df = df.reset_index(drop=True)

#     return df, metadata


# # ── Quick inspection ──────────────────────────────────────────────────────────

# if __name__ == "__main__":
#     import sys
#     import os

#     path = sys.argv[1] if len(sys.argv) > 1 else None

#     # Fallback: look in same directory as this script
#     if path is None:
#         script_dir = os.path.dirname(os.path.abspath(__file__))
#         for fname in os.listdir(script_dir):
#             if fname.upper().endswith(".CSV"):
#                 path = os.path.join(script_dir, fname)
#                 break

#     if path is None:
#         print("Usage: python import_segrigation_report_cleaning.py <path/to/file.csv>")
#         sys.exit(1)

#     print(f"[input] {path}")
#     with open(path, "rb") as f:
#         raw = f.read()

#     df, meta = clean_import_segregation_report(BytesIO(raw), file_type="csv")

#     pd.set_option("display.max_columns", None)
#     pd.set_option("display.width", 220)
#     pd.set_option("display.max_colwidth", 28)

#     print(f"\n{'='*60}")
#     print(f"Metadata  : {meta}")
#     print(f"Rows      : {len(df)}")
#     print(f"Columns   : {list(df.columns)}")

#     print(f"\n--- dtypes ---")
#     print(df.dtypes.to_string())

#     print(f"\n--- Sample rows (first 5) ---")
#     print(df.head(5).to_string())

#     print(f"\n--- Billing SHC value counts ---")
#     print(df["Billing SHC"].value_counts())

#     print(f"\n--- Flight Date samples ---")
#     print(df["Flight Date"].dropna().head(5).to_string())

#     print(f"\n--- ATA_Date/Time samples ---")
#     print(df["ATA_Date/Time"].dropna().head(5).to_string())

#     print(f"\n--- RCF date samples ---")
#     print(df["RCF date"].dropna().head(5).to_string())

#     print(f"\n--- AWB No samples ---")
#     print(df["AWB No"].dropna().head(10).tolist())

#     print(f"\n--- Null counts ---")
#     print(df.isnull().sum().to_string())




























# ------🫥🫥🫥--------------- TIME OPTIMIZE CODE (80 TO 16 SEC FOR 18000 ROWS )--------------

# import re
# import pytz
# import numpy as np
# import pandas as pd
# from io import BytesIO
# from datetime import datetime, timezone

# # ── Constants ────────────────────────────────────────────────────────────────

# BILLING_SHC_FILTER = {"TRM", "TPV"}

# REQUIRED_COLUMNS = [
#     "Flight No.", "Flight Date", "AWB No", "SFX",
#     "ATA_Date/Time", "FLT DOC Arrival_Date/Time",
#     "Last ULD Arrival Date & Time", "Bulk ULD Arrival Date & Time",
#     "Org", "DEST",
#     "Manifest Pcs", "Manifest Wgt",
#     "SEG Pcs", "SEG Wgt",
#     "PCS", "Gross weight", "CHG WGT", "Vol(MC)", "No of Houses",
#     "SHC", "CHG SHC", "Billing SHC",
#     "NOG", "Consignee Details",
#     "AWD date", "NFD date", "RCF date",
#     "DO date&time", "TFD date&time",
#     "EGM/IGM_NO", "FLT_COM_DAT_TIM", "FLIGHT STATUS",
# ]

# NUMERIC_COLS = [
#     "Manifest Pcs", "Manifest Wgt",
#     "SEG Pcs", "SEG Wgt",
#     "PCS", "Gross weight", "CHG WGT",
#     "Vol(MC)", "No of Houses",
# ]

# DATETIME_COLS = [
#     "ATA_Date/Time",
#     "FLT DOC Arrival_Date/Time",
#     "Last ULD Arrival Date & Time",
#     "Bulk ULD Arrival Date & Time",
#     "AWD date",
#     "NFD date",
#     "RCF date",
#     "DO date&time",
#     "TFD date&time",
#     "FLT_COM_DAT_TIM",
# ]

# FLIGHT_DATE_COL = "Flight Date"   # date-only column, parsed separately

# _IST = pytz.timezone("Asia/Kolkata")


# # ── Helpers ──────────────────────────────────────────────────────────────────

# def _clean_awb(val) -> str | None:
#     if not val or str(val).strip().lower() in ("", "nan", "none"):
#         return None
#     s = re.sub(r"\s+", "", str(val).strip())
#     s = re.sub(r"-+", "-", s).replace("-", "")
#     s = re.sub(r"\D", "", s)          # digits only
#     if s and len(s) == 10:
#         s = s.zfill(11)
#     return s or None


# def _to_utc_series(series: pd.Series, formats: list) -> pd.Series:
#     """
#     Vectorized IST → UTC conversion for an entire Series.
#     Tries each format in order; falls back to dayfirst inference for
#     remaining NaT values. Far faster than per-row apply().
#     """
#     s = series.astype(str).str.strip()
#     # blank / nan sentinel → NaT
#     s = s.where(~s.str.lower().isin({"", "nan", "none", "nat"}), other=pd.NaT)

#     result = pd.Series(pd.NaT, index=series.index)

#     remaining = s.notna()
#     for fmt in formats:
#         if not remaining.any():
#             break
#         parsed = pd.to_datetime(s[remaining], format=fmt, errors="coerce")
#         filled = parsed.notna()
#         result[remaining & filled.reindex(series.index, fill_value=False)] = parsed[filled]
#         remaining = remaining & ~filled.reindex(series.index, fill_value=False)

#     # Fallback: dayfirst inference on any still-unparsed rows
#     if remaining.any():
#         parsed = pd.to_datetime(s[remaining], errors="coerce", dayfirst=True)
#         filled = parsed.notna()
#         result[remaining & filled.reindex(series.index, fill_value=False)] = parsed[filled]

#     # Localize IST → UTC (vectorized)
#     result = pd.to_datetime(result, errors="coerce")
#     result = result.dt.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="NaT")
#     result = result.dt.tz_convert("UTC")
#     return result


# def _to_date_utc_series(series: pd.Series, formats: list) -> pd.Series:
#     """Vectorized date-only → midnight IST → UTC conversion."""
#     s = series.astype(str).str.strip()
#     s = s.where(~s.str.lower().isin({"", "nan", "none", "nat"}), other=pd.NaT)

#     result = pd.Series(pd.NaT, index=series.index)
#     remaining = s.notna()

#     for fmt in formats:
#         if not remaining.any():
#             break
#         parsed = pd.to_datetime(s[remaining], format=fmt, errors="coerce")
#         # Normalize to midnight
#         parsed = parsed.dt.normalize()
#         filled = parsed.notna()
#         result[remaining & filled.reindex(series.index, fill_value=False)] = parsed[filled]
#         remaining = remaining & ~filled.reindex(series.index, fill_value=False)

#     result = pd.to_datetime(result, errors="coerce")
#     result = result.dt.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="NaT")
#     result = result.dt.tz_convert("UTC")
#     return result


# # ── Metadata ─────────────────────────────────────────────────────────────────

# def _extract_metadata(df_raw: pd.DataFrame) -> dict:
#     """
#     Extract FROM DATE / TO DATE / Carrier from header rows.
#     Scans only the first 12 rows — metadata is always in the report header.
#     Handles both:
#       - value embedded in same cell: "FROM DATE :06MAY2026"
#       - value in next cell:          "FROM DATE"  |  "06MAY2026"
#     """
#     metadata = {}
#     # Limit scan to first 12 rows — metadata never appears in data rows.
#     # iterrows over 18k rows costs ~8s; over 12 rows costs <1ms.
#     for _, row in df_raw.head(12).iterrows():
#         row_vals = row.dropna().astype(str).str.strip().tolist()
#         row_str  = " ".join(row_vals).upper()
#         if "FROM DATE" not in row_str and "TO DATE" not in row_str:
#             continue
#         for i, val in enumerate(row_vals):
#             uv = val.upper()
#             # Embedded pattern: "FROM DATE :06MAY2026"
#             m = re.search(r"FROM\s*DATE\s*[:\s]+(\S+)", uv)
#             if m:
#                 metadata["from_date"] = m.group(1).strip(": ")
#             m = re.search(r"TO\s*DATE\s*[:\s]+(\S+)", uv)
#             if m:
#                 metadata["to_date"] = m.group(1).strip(": ")
#             # Fallback: next-cell pattern
#             if "FROM DATE" in uv and "from_date" not in metadata and i + 1 < len(row_vals):
#                 metadata["from_date"] = row_vals[i + 1].strip(": ")
#             if "TO DATE" in uv and "to_date" not in metadata and i + 1 < len(row_vals):
#                 metadata["to_date"] = row_vals[i + 1].strip(": ")
#             if "CARRIER" in uv and i + 1 < len(row_vals):
#                 metadata["carrier"] = row_vals[i + 1].strip(": ")
#     return metadata


# def _parse_month_uploaded(metadata: dict) -> str:
#     from_date_str = metadata.get("from_date", "")
#     try:
#         dt = pd.to_datetime(from_date_str, errors="raise")
#         return dt.strftime("%Y-%m")
#     except Exception:
#         return pd.Timestamp.now().strftime("%Y-%m")


# def validate_same_month(metadata: dict):
#     from_date_str = metadata.get("from_date")
#     to_date_str   = metadata.get("to_date")
#     if not from_date_str or not to_date_str:
#         raise ValueError("FROM DATE or TO DATE missing in report metadata.")
#     try:
#         from_dt = pd.to_datetime(from_date_str)
#         to_dt   = pd.to_datetime(to_date_str)
#     except Exception:
#         raise ValueError("Unable to parse FROM DATE / TO DATE from report.")
#     if from_dt.year != to_dt.year or from_dt.month != to_dt.month:
#         raise ValueError(
#             f"Invalid report period: FROM DATE ({from_dt.date()}) and "
#             f"TO DATE ({to_dt.date()}) must belong to same month."
#         )


# def _find_header_row(df_raw: pd.DataFrame) -> int:
#     for i, row in df_raw.iterrows():
#         vals = row.dropna().astype(str).str.upper().str.strip().tolist()
#         if "AWB NO" in vals or "FLIGHT NO." in vals or "FLIGHT NO" in vals:
#             return i
#     raise ValueError("Could not find header row with 'AWB No' / 'Flight No.' column.")


# def _read_raw_csv(file_bytes: BytesIO) -> pd.DataFrame:
#     """
#     Read CSV with variable column counts into a uniform DataFrame.
#     Uses pandas engine with a pre-computed column count — much faster
#     than a Python-level line-by-line pad loop on 18k+ rows.
#     """
#     raw_text = file_bytes.read().decode("utf-8", errors="replace")
#     file_bytes.seek(0)

#     lines    = raw_text.splitlines()
#     max_cols = max((line.count(",") for line in lines), default=0) + 1

#     # Let pandas parse; name every column 0..max_cols-1 so short rows get NaN
#     # instead of raising. engine="python" handles variable-width rows cleanly.
#     return pd.read_csv(
#         file_bytes,
#         header=None,
#         names=range(max_cols),
#         dtype=str,
#         keep_default_na=False,   # keep empty strings as "" not NaN
#         engine="c",
#         on_bad_lines="skip",
#     )


# # ── Main cleaner ─────────────────────────────────────────────────────────────

# def clean_import_segregation_report(
#     file_bytes: BytesIO,
#     file_type: str = "csv",
# ) -> tuple[pd.DataFrame, dict]:
#     """
#     Parse and clean the Segregation Report (CSV or Excel).
#     Returns only rows where Billing SHC is TRM or TPV.
#     """

#     # ── 1. Read raw file (no header) ─────────────────────────────────────────
#     if file_type == "excel":
#         df_raw = pd.read_excel(file_bytes, header=None, dtype=str)
#     elif file_type == "csv":
#         df_raw = _read_raw_csv(file_bytes)
#     else:
#         raise ValueError("Unsupported file_type. Use 'excel' or 'csv'.")

#     # ── 2. Extract + validate metadata ───────────────────────────────────────
#     metadata       = _extract_metadata(df_raw)
#     validate_same_month(metadata)
#     month_uploaded = _parse_month_uploaded(metadata)
#     print(f"[meta] from={metadata.get('from_date')}  to={metadata.get('to_date')}  month={month_uploaded}")

#     # ── 3. Locate header row ──────────────────────────────────────────────────
#     header_row_idx = _find_header_row(df_raw)
#     print(f"[header] found at raw row index {header_row_idx}")

#     # ── 4. Build df: header row → column names, everything below → data ───────
#     if file_type == "excel":
#         file_bytes.seek(0)
#         df = pd.read_excel(file_bytes, header=header_row_idx, dtype=str)
#         # Excel gives UNNAMED cols for blank header cells — handled in step 5
#         df.columns = [str(c).strip() for c in df.columns]
#     else:
#         # Slice df_raw: header row values become column names
#         header_vals = [str(v).strip() for v in df_raw.iloc[header_row_idx].tolist()]
#         data        = df_raw.iloc[header_row_idx + 1:].copy()
#         data.columns = header_vals
#         df = data.reset_index(drop=True)

#     # ── 5. Drop junk columns ──────────────────────────────────────────────────
#     # After slicing, padding columns are named "" or "nan" or pure integers.
#     # Excel gives "Unnamed: N" style names for blank header cells.
#     # Keep only columns with a real non-empty, non-numeric name.
#     def _is_valid_col(name: str) -> bool:
#         n = name.strip()
#         if not n or n.lower() == "nan":
#             return False
#         if n.upper().startswith("UNNAMED"):
#             return False
#         # Pure integer names are padding artefacts from _read_raw_csv
#         try:
#             int(n)
#             return False
#         except ValueError:
#             return True

#     df = df.loc[:, [c for c in df.columns if _is_valid_col(c)]].copy()

#     # ── 6. Drop subtotal / grand-total / NIL CARRIER rows (vectorized) ─────────
#     # Check only the first 3 columns — all markers appear there.
#     # Avoid df.apply(axis=1) which is ~15x slower on 18k rows.
#     col0 = df.iloc[:, 0].fillna("").astype(str).str.strip().str.upper()
#     col2 = df.iloc[:, 2].fillna("").astype(str).str.strip().str.upper()

#     # NIL CARRIER: chop everything from first matching row onward
#     nil_mask = col0.str.contains("NIL CARRIER", na=False) | col2.str.contains("NIL CARRIER", na=False)
#     if nil_mask.any():
#         df = df.iloc[: nil_mask.values.argmax()]
#         col0 = col0.iloc[: len(df)]
#         col2 = col2.iloc[: len(df)]

#     # Subtotal rows: col2 == "TOTAL"
#     df = df[col2.loc[df.index] != "TOTAL"].copy()

#     # Grand total: scan only first 4 cols joined — avoids full-row string join
#     # GRAND TOTAL marker always appears in first or second col — no need for row join
#     grand_col = df.iloc[:, 0].fillna("").astype(str).str.upper()
#     df = df[~grand_col.str.contains("GRAND TOTAL", na=False)].copy()

#     # ── 7. Validate required columns ─────────────────────────────────────────
#     missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
#     if missing:
#         raise ValueError(f"Missing required columns: {missing}")

#     df = df[REQUIRED_COLUMNS].copy()

#     # ── 8. Filter: Billing SHC FIRST — reduces rows before all heavy work ────
#     # On 18k rows with ~2.8k valid: filters out 15k rows before any cleanup,
#     # cutting all subsequent work by ~85%.
#     billing = df["Billing SHC"].astype(str).str.strip().str.upper()
#     df = df[billing.isin(BILLING_SHC_FILTER)].copy()
#     print(f"[filter] rows after Billing SHC filter (TRM/TPV): {len(df)}")

#     if df.empty:
#         return df, metadata

#     # ── 9. Basic cleanup on filtered rows only ────────────────────────────────
#     df = df.replace(r"^\s*$", np.nan, regex=True)
#     df = df.dropna(how="all")

#     # ── 10. Keep rows where AWB No is non-empty ───────────────────────────────
#     if "AWB No" in df.columns:
#         df = df[df["AWB No"].astype(str).str.strip().str.len() > 3]

#     # ── 11. Strip whitespace on all cells ────────────────────────────────────
#     for col in df.columns:
#         df[col] = df[col].astype(str).str.strip()
#     df = df.replace({"nan": np.nan, "NaN": np.nan, "": np.nan})

#     # ── 12. Clean AWB ─────────────────────────────────────────────────────────
#     df["AWB No"] = df["AWB No"].apply(_clean_awb)

#     # ── 13. Cast numeric columns ──────────────────────────────────────────────
#     for col in NUMERIC_COLS:
#         df[col] = pd.to_numeric(df[col], errors="coerce")

#     # ── 14. Parse Flight Date (date-only → midnight IST → UTC) ───────────────
#     flight_date_fmts = [
#         "%d-%b-%y",   # 05-MAY-26
#         "%d-%b-%Y",   # 05-MAY-2026
#         "%d/%m/%y",   # 05/05/26
#         "%d/%m/%Y",   # 05/05/2026
#     ]
#     df[FLIGHT_DATE_COL] = _to_date_utc_series(df[FLIGHT_DATE_COL], flight_date_fmts)

#     # ── 15. Parse all other datetime columns (IST → UTC) — vectorized ────────
#     dt_fmts = [
#         "%d/%m/%y %H:%M",      # 05/05/26 22:19
#         "%d/%m/%y %H:%M:%S",   # 06/05/26 00:28:30
#         "%d/%m/%Y %H:%M",
#         "%d/%m/%Y %H:%M:%S",
#         "%d-%b-%y %H:%M",
#         "%d-%b-%Y %H:%M",
#         "%Y-%m-%d %H:%M:%S",
#     ]
#     for col in DATETIME_COLS:
#         df[col] = _to_utc_series(df[col], dt_fmts)

#     # ── 16. Standardise remaining text columns ────────────────────────────────
#     text_cols = [
#         c for c in REQUIRED_COLUMNS
#         if c not in NUMERIC_COLS + DATETIME_COLS + [FLIGHT_DATE_COL]
#     ]
#     for col in text_cols:
#         s = df[col].astype(str).str.strip()
#         df[col] = s.where(s.str.lower() != "nan", other=np.nan)

#     # ── 17. Drop rows with no valid AWB ──────────────────────────────────────
#     df = df.dropna(subset=["AWB No"])

#     # ── 18. Attach metadata columns ───────────────────────────────────────────
#     df["month_uploaded"] = month_uploaded
#     df["uploaded_at"]    = datetime.now(tz=timezone.utc)

#     # ── 19. Final cleanup ─────────────────────────────────────────────────────
#     # Re-cast all datetime cols to UTC after text cleanup (replace NaN→None
#     # can strip the tz dtype). This ensures proper datetime64[us, UTC] dtype
#     # on all datetime columns going into the DB layer.
#     all_dt_cols = DATETIME_COLS + [FLIGHT_DATE_COL, "uploaded_at"]
#     for col in all_dt_cols:
#         if col in df.columns:
#             df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

#     # Replace remaining NaN/NaT with None for asyncpg compatibility
#     df = df.where(df.notna(), other=None)
#     df = df.reset_index(drop=True)

#     return df, metadata


# # ── Quick inspection ──────────────────────────────────────────────────────────

# if __name__ == "__main__":
#     import sys
#     import os

#     path = sys.argv[1] if len(sys.argv) > 1 else None

#     # Fallback: look in same directory as this script
#     if path is None:
#         script_dir = os.path.dirname(os.path.abspath(__file__))
#         for fname in os.listdir(script_dir):
#             if fname.upper().endswith(".CSV"):
#                 path = os.path.join(script_dir, fname)
#                 break

#     if path is None:
#         print("Usage: python import_segrigation_report_cleaning.py <path/to/file.csv>")
#         sys.exit(1)

#     print(f"[input] {path}")
#     with open(path, "rb") as f:
#         raw = f.read()

#     df, meta = clean_import_segregation_report(BytesIO(raw), file_type="csv")

#     pd.set_option("display.max_columns", None)
#     pd.set_option("display.width", 220)
#     pd.set_option("display.max_colwidth", 28)

#     print(f"\n{'='*60}")
#     print(f"Metadata  : {meta}")
#     print(f"Rows      : {len(df)}")
#     print(f"Columns   : {list(df.columns)}")

#     print(f"\n--- dtypes ---")
#     print(df.dtypes.to_string())

#     print(f"\n--- Sample rows (first 5) ---")
#     print(df.head(5).to_string())

#     print(f"\n--- Billing SHC value counts ---")
#     print(df["Billing SHC"].value_counts())

#     print(f"\n--- Flight Date samples ---")
#     print(df["Flight Date"].dropna().head(5).to_string())

#     print(f"\n--- ATA_Date/Time samples ---")
#     print(df["ATA_Date/Time"].dropna().head(5).to_string())

#     print(f"\n--- RCF date samples ---")
#     print(df["RCF date"].dropna().head(5).to_string())

#     print(f"\n--- AWB No samples ---")
#     print(df["AWB No"].dropna().head(10).tolist())

#     print(f"\n--- Null counts ---")
#     print(df.isnull().sum().to_string())



# ======== 🫥🫥🫥 New with today date restriction in segrigation report ======================




# import re
# import pytz
# import numpy as np
# import pandas as pd
# from io import BytesIO
# from datetime import datetime, timezone

# # ── Constants ────────────────────────────────────────────────────────────────

# BILLING_SHC_FILTER = {"TRM", "TPV"}

# REQUIRED_COLUMNS = [
#     "Flight No.", "Flight Date", "AWB No", "SFX",
#     "ATA_Date/Time", "FLT DOC Arrival_Date/Time",
#     "Last ULD Arrival Date & Time", "Bulk ULD Arrival Date & Time",
#     "Org", "DEST",
#     "Manifest Pcs", "Manifest Wgt",
#     "SEG Pcs", "SEG Wgt",
#     "PCS", "Gross weight", "CHG WGT", "Vol(MC)", "No of Houses",
#     "SHC", "CHG SHC", "Billing SHC",
#     "NOG", "Consignee Details",
#     "AWD date", "NFD date", "RCF date",
#     "DO date&time", "TFD date&time",
#     "EGM/IGM_NO", "FLT_COM_DAT_TIM", "FLIGHT STATUS",
# ]

# NUMERIC_COLS = [
#     "Manifest Pcs", "Manifest Wgt",
#     "SEG Pcs", "SEG Wgt",
#     "PCS", "Gross weight", "CHG WGT",
#     "Vol(MC)", "No of Houses",
# ]

# DATETIME_COLS = [
#     "ATA_Date/Time",
#     "FLT DOC Arrival_Date/Time",
#     "Last ULD Arrival Date & Time",
#     "Bulk ULD Arrival Date & Time",
#     "AWD date",
#     "NFD date",
#     "RCF date",
#     "DO date&time",
#     "TFD date&time",
#     "FLT_COM_DAT_TIM",
# ]

# FLIGHT_DATE_COL = "Flight Date"   # date-only column, parsed separately

# _IST = pytz.timezone("Asia/Kolkata")


# # ── Helpers ──────────────────────────────────────────────────────────────────

# def _clean_awb(val) -> str | None:
#     if not val or str(val).strip().lower() in ("", "nan", "none"):
#         return None
#     s = re.sub(r"\s+", "", str(val).strip())
#     s = re.sub(r"-+", "-", s).replace("-", "")
#     s = re.sub(r"\D", "", s)          # digits only
#     if s and len(s) == 10:
#         s = s.zfill(11)
#     return s or None


# def _to_utc_series(series: pd.Series, formats: list) -> pd.Series:
#     """
#     Vectorized IST → UTC conversion for an entire Series.
#     Tries each format in order; falls back to dayfirst inference for
#     remaining NaT values. Far faster than per-row apply().
#     """
#     s = series.astype(str).str.strip()
#     # blank / nan sentinel → NaT
#     s = s.where(~s.str.lower().isin({"", "nan", "none", "nat"}), other=pd.NaT)

#     result = pd.Series(pd.NaT, index=series.index)

#     remaining = s.notna()
#     for fmt in formats:
#         if not remaining.any():
#             break
#         parsed = pd.to_datetime(s[remaining], format=fmt, errors="coerce")
#         filled = parsed.notna()
#         result[remaining & filled.reindex(series.index, fill_value=False)] = parsed[filled]
#         remaining = remaining & ~filled.reindex(series.index, fill_value=False)

#     # Fallback: dayfirst inference on any still-unparsed rows
#     if remaining.any():
#         parsed = pd.to_datetime(s[remaining], errors="coerce", dayfirst=True)
#         filled = parsed.notna()
#         result[remaining & filled.reindex(series.index, fill_value=False)] = parsed[filled]

#     # Localize IST → UTC (vectorized)
#     result = pd.to_datetime(result, errors="coerce")
#     result = result.dt.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="NaT")
#     result = result.dt.tz_convert("UTC")
#     return result


# def _to_date_utc_series(series: pd.Series, formats: list) -> pd.Series:
#     """Vectorized date-only → midnight IST → UTC conversion."""
#     s = series.astype(str).str.strip()
#     s = s.where(~s.str.lower().isin({"", "nan", "none", "nat"}), other=pd.NaT)

#     result = pd.Series(pd.NaT, index=series.index)
#     remaining = s.notna()

#     for fmt in formats:
#         if not remaining.any():
#             break
#         parsed = pd.to_datetime(s[remaining], format=fmt, errors="coerce")
#         # Normalize to midnight
#         parsed = parsed.dt.normalize()
#         filled = parsed.notna()
#         result[remaining & filled.reindex(series.index, fill_value=False)] = parsed[filled]
#         remaining = remaining & ~filled.reindex(series.index, fill_value=False)

#     result = pd.to_datetime(result, errors="coerce")
#     result = result.dt.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="NaT")
#     result = result.dt.tz_convert("UTC")
#     return result


# # ── Metadata ─────────────────────────────────────────────────────────────────

# def _extract_metadata(df_raw: pd.DataFrame) -> dict:
#     """
#     Extract FROM DATE / TO DATE / Carrier from header rows.
#     Scans only the first 12 rows — metadata is always in the report header.
#     Handles both:
#       - value embedded in same cell: "FROM DATE :06MAY2026"
#       - value in next cell:          "FROM DATE"  |  "06MAY2026"
#     """
#     metadata = {}
#     # Limit scan to first 12 rows — metadata never appears in data rows.
#     # iterrows over 18k rows costs ~8s; over 12 rows costs <1ms.
#     for _, row in df_raw.head(12).iterrows():
#         row_vals = row.dropna().astype(str).str.strip().tolist()
#         row_str  = " ".join(row_vals).upper()
#         if "FROM DATE" not in row_str and "TO DATE" not in row_str:
#             continue
#         for i, val in enumerate(row_vals):
#             uv = val.upper()
#             # Embedded pattern: "FROM DATE :06MAY2026"
#             m = re.search(r"FROM\s*DATE\s*[:\s]+(\S+)", uv)
#             if m:
#                 metadata["from_date"] = m.group(1).strip(": ")
#             m = re.search(r"TO\s*DATE\s*[:\s]+(\S+)", uv)
#             if m:
#                 metadata["to_date"] = m.group(1).strip(": ")
#             # Fallback: next-cell pattern
#             if "FROM DATE" in uv and "from_date" not in metadata and i + 1 < len(row_vals):
#                 metadata["from_date"] = row_vals[i + 1].strip(": ")
#             if "TO DATE" in uv and "to_date" not in metadata and i + 1 < len(row_vals):
#                 metadata["to_date"] = row_vals[i + 1].strip(": ")
#             if "CARRIER" in uv and i + 1 < len(row_vals):
#                 metadata["carrier"] = row_vals[i + 1].strip(": ")
#     return metadata


# def _parse_month_uploaded(metadata: dict) -> str:
#     from_date_str = metadata.get("from_date", "")
#     try:
#         dt = pd.to_datetime(from_date_str, errors="raise")
#         return dt.strftime("%Y-%m")
#     except Exception:
#         return pd.Timestamp.now().strftime("%Y-%m")


# def validate_single_day_today(metadata: dict) -> pd.Timestamp:
#     """
#     Validates:
#       1. FROM DATE and TO DATE are present and parseable.
#       2. FROM DATE == TO DATE (report must cover exactly one day).
#       3. That date == today in IST (strict — no tolerance).
#     Returns the report date as a pd.Timestamp (date only, no tz).
#     """
#     from_date_str = metadata.get("from_date")
#     to_date_str   = metadata.get("to_date")

#     if not from_date_str or not to_date_str:
#         raise ValueError("FROM DATE or TO DATE missing in report metadata.")

#     try:
#         from_dt = pd.to_datetime(from_date_str)
#         to_dt   = pd.to_datetime(to_date_str)
#     except Exception:
#         raise ValueError("Unable to parse FROM DATE / TO DATE from report.")

#     # Must be same single day
#     if from_dt.date() != to_dt.date():
#         raise ValueError(
#             f"Report must cover a single day. "
#             f"FROM DATE ({from_dt.date()}) ≠ TO DATE ({to_dt.date()})."
#         )

#     # Must be today in IST
#     _IST = pytz.timezone("Asia/Kolkata")
#     today_ist = datetime.now(_IST).date()
#     report_date = from_dt.date()

#     if report_date != today_ist:
#         raise ValueError(
#             f"Report date ({report_date}) must be today's date ({today_ist} IST). "
#             f"Only today's report can be uploaded."
#         )

#     return pd.Timestamp(from_dt.date())


# def _find_header_row(df_raw: pd.DataFrame) -> int:
#     for i, row in df_raw.iterrows():
#         vals = row.dropna().astype(str).str.upper().str.strip().tolist()
#         if "AWB NO" in vals or "FLIGHT NO." in vals or "FLIGHT NO" in vals:
#             return i
#     raise ValueError("Could not find header row with 'AWB No' / 'Flight No.' column.")


# def _read_raw_csv(file_bytes: BytesIO) -> pd.DataFrame:
#     """
#     Read CSV with variable column counts into a uniform DataFrame.
#     Uses pandas engine with a pre-computed column count — much faster
#     than a Python-level line-by-line pad loop on 18k+ rows.
#     """
#     raw_text = file_bytes.read().decode("utf-8", errors="replace")
#     file_bytes.seek(0)

#     lines    = raw_text.splitlines()
#     max_cols = max((line.count(",") for line in lines), default=0) + 1

#     # Let pandas parse; name every column 0..max_cols-1 so short rows get NaN
#     # instead of raising. engine="python" handles variable-width rows cleanly.
#     return pd.read_csv(
#         file_bytes,
#         header=None,
#         names=range(max_cols),
#         dtype=str,
#         keep_default_na=False,   # keep empty strings as "" not NaN
#         engine="c",
#         on_bad_lines="skip",
#     )


# # ── Main cleaner ─────────────────────────────────────────────────────────────

# def clean_import_segregation_report(
#     file_bytes: BytesIO,
#     file_type: str = "csv",
# ) -> tuple[pd.DataFrame, dict]:
#     """
#     Parse and clean the Segregation Report (CSV or Excel).
#     Returns only rows where Billing SHC is TRM or TPV.
#     """

#     # ── 1. Read raw file (no header) ─────────────────────────────────────────
#     if file_type == "excel":
#         df_raw = pd.read_excel(file_bytes, header=None, dtype=str)
#     elif file_type == "csv":
#         df_raw = _read_raw_csv(file_bytes)
#     else:
#         raise ValueError("Unsupported file_type. Use 'excel' or 'csv'.")

#     # ── 2. Extract + validate metadata ───────────────────────────────────────
#     metadata       = _extract_metadata(df_raw)
#     report_date    = validate_single_day_today(metadata)   # raises if invalid
#     month_uploaded = _parse_month_uploaded(metadata)
#     print(f"[meta] from={metadata.get('from_date')}  to={metadata.get('to_date')}  month={month_uploaded}")

#     # ── 3. Locate header row ──────────────────────────────────────────────────
#     header_row_idx = _find_header_row(df_raw)
#     print(f"[header] found at raw row index {header_row_idx}")

#     # ── 4. Build df: header row → column names, everything below → data ───────
#     if file_type == "excel":
#         file_bytes.seek(0)
#         df = pd.read_excel(file_bytes, header=header_row_idx, dtype=str)
#         # Excel gives UNNAMED cols for blank header cells — handled in step 5
#         df.columns = [str(c).strip() for c in df.columns]
#     else:
#         # Slice df_raw: header row values become column names
#         header_vals = [str(v).strip() for v in df_raw.iloc[header_row_idx].tolist()]
#         data        = df_raw.iloc[header_row_idx + 1:].copy()
#         data.columns = header_vals
#         df = data.reset_index(drop=True)

#     # ── 5. Drop junk columns ──────────────────────────────────────────────────
#     # After slicing, padding columns are named "" or "nan" or pure integers.
#     # Excel gives "Unnamed: N" style names for blank header cells.
#     # Keep only columns with a real non-empty, non-numeric name.
#     def _is_valid_col(name: str) -> bool:
#         n = name.strip()
#         if not n or n.lower() == "nan":
#             return False
#         if n.upper().startswith("UNNAMED"):
#             return False
#         # Pure integer names are padding artefacts from _read_raw_csv
#         try:
#             int(n)
#             return False
#         except ValueError:
#             return True

#     df = df.loc[:, [c for c in df.columns if _is_valid_col(c)]].copy()

#     # ── 6. Drop subtotal / grand-total / NIL CARRIER rows (vectorized) ─────────
#     # Check only the first 3 columns — all markers appear there.
#     # Avoid df.apply(axis=1) which is ~15x slower on 18k rows.
#     col0 = df.iloc[:, 0].fillna("").astype(str).str.strip().str.upper()
#     col2 = df.iloc[:, 2].fillna("").astype(str).str.strip().str.upper()

#     # NIL CARRIER: chop everything from first matching row onward
#     nil_mask = col0.str.contains("NIL CARRIER", na=False) | col2.str.contains("NIL CARRIER", na=False)
#     if nil_mask.any():
#         df = df.iloc[: nil_mask.values.argmax()]
#         col0 = col0.iloc[: len(df)]
#         col2 = col2.iloc[: len(df)]

#     # Subtotal rows: col2 == "TOTAL"
#     df = df[col2.loc[df.index] != "TOTAL"].copy()

#     # Grand total: scan only first 4 cols joined — avoids full-row string join
#     # GRAND TOTAL marker always appears in first or second col — no need for row join
#     grand_col = df.iloc[:, 0].fillna("").astype(str).str.upper()
#     df = df[~grand_col.str.contains("GRAND TOTAL", na=False)].copy()

#     # ── 7. Validate required columns ─────────────────────────────────────────
#     missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
#     if missing:
#         raise ValueError(f"Missing required columns: {missing}")

#     df = df[REQUIRED_COLUMNS].copy()

#     # ── 8. Filter: Billing SHC FIRST — reduces rows before all heavy work ────
#     # On 18k rows with ~2.8k valid: filters out 15k rows before any cleanup,
#     # cutting all subsequent work by ~85%.
#     billing = df["Billing SHC"].astype(str).str.strip().str.upper()
#     df = df[billing.isin(BILLING_SHC_FILTER)].copy()
#     print(f"[filter] rows after Billing SHC filter (TRM/TPV): {len(df)}")

#     if df.empty:
#         return df, metadata

#     # ── 9. Basic cleanup on filtered rows only ────────────────────────────────
#     df = df.replace(r"^\s*$", np.nan, regex=True)
#     df = df.dropna(how="all")

#     # ── 10. Keep rows where AWB No is non-empty ───────────────────────────────
#     if "AWB No" in df.columns:
#         df = df[df["AWB No"].astype(str).str.strip().str.len() > 3]

#     # ── 11. Strip whitespace on all cells ────────────────────────────────────
#     for col in df.columns:
#         df[col] = df[col].astype(str).str.strip()
#     df = df.replace({"nan": np.nan, "NaN": np.nan, "": np.nan})

#     # ── 12. Clean AWB ─────────────────────────────────────────────────────────
#     df["AWB No"] = df["AWB No"].apply(_clean_awb)

#     # ── 13. Cast numeric columns ──────────────────────────────────────────────
#     for col in NUMERIC_COLS:
#         df[col] = pd.to_numeric(df[col], errors="coerce")

#     # ── 14. Parse Flight Date (date-only → midnight IST → UTC) ───────────────
#     flight_date_fmts = [
#         "%d-%b-%y",   # 05-MAY-26
#         "%d-%b-%Y",   # 05-MAY-2026
#         "%d/%m/%y",   # 05/05/26
#         "%d/%m/%Y",   # 05/05/2026
#     ]
#     df[FLIGHT_DATE_COL] = _to_date_utc_series(df[FLIGHT_DATE_COL], flight_date_fmts)

#     # ── 15. Parse all other datetime columns (IST → UTC) — vectorized ────────
#     dt_fmts = [
#         "%d/%m/%y %H:%M",      # 05/05/26 22:19
#         "%d/%m/%y %H:%M:%S",   # 06/05/26 00:28:30
#         "%d/%m/%Y %H:%M",
#         "%d/%m/%Y %H:%M:%S",
#         "%d-%b-%y %H:%M",
#         "%d-%b-%Y %H:%M",
#         "%Y-%m-%d %H:%M:%S",
#     ]
#     for col in DATETIME_COLS:
#         df[col] = _to_utc_series(df[col], dt_fmts)

#     # ── 16. Standardise remaining text columns ────────────────────────────────
#     text_cols = [
#         c for c in REQUIRED_COLUMNS
#         if c not in NUMERIC_COLS + DATETIME_COLS + [FLIGHT_DATE_COL]
#     ]
#     for col in text_cols:
#         s = df[col].astype(str).str.strip()
#         df[col] = s.where(s.str.lower() != "nan", other=np.nan)

#     # ── 17. Drop rows with no valid AWB ──────────────────────────────────────
#     df = df.dropna(subset=["AWB No"])

#     # ── 18. Attach metadata columns ───────────────────────────────────────────
#     df["month_uploaded"] = month_uploaded
#     df["report_date"]    = report_date.date()   # plain Python date — no tz, stored as DATE in DB
#     df["uploaded_at"]    = datetime.now(tz=timezone.utc)

#     # ── 19. Final cleanup ─────────────────────────────────────────────────────
#     # Re-cast all datetime cols to UTC after text cleanup (replace NaN→None
#     # can strip the tz dtype). This ensures proper datetime64[us, UTC] dtype
#     # on all datetime columns going into the DB layer.
#     all_dt_cols = DATETIME_COLS + [FLIGHT_DATE_COL, "uploaded_at"]
#     for col in all_dt_cols:
#         if col in df.columns:
#             df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

#     # Replace remaining NaN/NaT with None for asyncpg compatibility
#     df = df.where(df.notna(), other=None)
#     df = df.reset_index(drop=True)

#     return df, metadata


# # ── Quick inspection ✅ ──────────────────────────────────────────────────────────

# if __name__ == "__main__":
#     import sys
#     import os

#     path = sys.argv[1] if len(sys.argv) > 1 else None

#     # Fallback: look in same directory as this script
#     if path is None:
#         script_dir = os.path.dirname(os.path.abspath(__file__))
#         for fname in os.listdir(script_dir):
#             if fname.upper().endswith(".CSV"):
#                 path = os.path.join(script_dir, fname)
#                 break

#     if path is None:
#         print("Usage: python import_segrigation_report_cleaning.py <path/to/file.csv>")
#         sys.exit(1)

#     print(f"[input] {path}")
#     with open(path, "rb") as f:
#         raw = f.read()

#     df, meta = clean_import_segregation_report(BytesIO(raw), file_type="csv")

#     pd.set_option("display.max_columns", None)
#     pd.set_option("display.width", 220)
#     pd.set_option("display.max_colwidth", 28)

#     print(f"\n{'='*60}")
#     print(f"Metadata  : {meta}")
#     print(f"Rows      : {len(df)}")
#     print(f"Columns   : {list(df.columns)}")

#     print(f"\n--- dtypes ---")
#     print(df.dtypes.to_string())

#     print(f"\n--- Sample rows (first 5) ---")
#     print(df.head(5).to_string())

#     print(f"\n--- Billing SHC value counts ---")
#     print(df["Billing SHC"].value_counts())

#     print(f"\n--- Flight Date samples ---")
#     print(df["Flight Date"].dropna().head(5).to_string())

#     print(f"\n--- ATA_Date/Time samples ---")
#     print(df["ATA_Date/Time"].dropna().head(5).to_string())

#     print(f"\n--- RCF date samples ---")
#     print(df["RCF date"].dropna().head(5).to_string())

#     print(f"\n--- AWB No samples ---")
#     print(df["AWB No"].dropna().head(10).tolist())

#     print(f"\n--- Null counts ---")
#     print(df.isnull().sum().to_string())

































import re
import pytz
import numpy as np
import pandas as pd
from io import BytesIO
from datetime import datetime, timezone

# ── Constants ────────────────────────────────────────────────────────────────

BILLING_SHC_FILTER = {"TRM", "TPV"}

REQUIRED_COLUMNS = [
    "Flight No.", "Flight Date", "AWB No", "SFX",
    "ATA_Date/Time", "FLT DOC Arrival_Date/Time",
    "Last ULD Arrival Date & Time", "Bulk ULD Arrival Date & Time",
    "Org", "DEST",
    "Manifest Pcs", "Manifest Wgt",
    "SEG Pcs", "SEG Wgt",
    "PCS", "Gross weight", "CHG WGT", "Vol(MC)", "No of Houses",
    "SHC", "CHG SHC", "Billing SHC",
    "NOG", "Consignee Details",
    "AWD date", "NFD date", "RCF date",
    "DO date&time", "TFD date&time",
    "EGM/IGM_NO", "FLT_COM_DAT_TIM", "FLIGHT STATUS",
]

NUMERIC_COLS = [
    "Manifest Pcs", "Manifest Wgt",
    "SEG Pcs", "SEG Wgt",
    "PCS", "Gross weight", "CHG WGT",
    "Vol(MC)", "No of Houses",
]

DATETIME_COLS = [
    "ATA_Date/Time",
    "FLT DOC Arrival_Date/Time",
    "Last ULD Arrival Date & Time",
    "Bulk ULD Arrival Date & Time",
    "AWD date",
    "NFD date",
    "RCF date",
    "DO date&time",
    "TFD date&time",
    "FLT_COM_DAT_TIM",
]

FLIGHT_DATE_COL = "Flight Date"   # date-only column, parsed separately

_IST = pytz.timezone("Asia/Kolkata")


# ── Helpers ──────────────────────────────────────────────────────────────────

def _clean_awb(val) -> str | None:
    if not val or str(val).strip().lower() in ("", "nan", "none"):
        return None
    s = re.sub(r"\s+", "", str(val).strip())
    s = re.sub(r"-+", "-", s).replace("-", "")
    s = re.sub(r"\D", "", s)          # digits only
    if s and len(s) == 10:
        s = s.zfill(11)
    return s or None


def _to_utc_series(series: pd.Series, formats: list) -> pd.Series:
    """
    Vectorized IST → UTC conversion for an entire Series.
    Tries each format in order; falls back to dayfirst inference for
    remaining NaT values. Far faster than per-row apply().
    """
    s = series.astype(str).str.strip()
    # blank / nan sentinel → NaT
    s = s.where(~s.str.lower().isin({"", "nan", "none", "nat"}), other=pd.NaT)

    result = pd.Series(pd.NaT, index=series.index)

    remaining = s.notna()
    for fmt in formats:
        if not remaining.any():
            break
        parsed = pd.to_datetime(s[remaining], format=fmt, errors="coerce")
        filled = parsed.notna()
        result[remaining & filled.reindex(series.index, fill_value=False)] = parsed[filled]
        remaining = remaining & ~filled.reindex(series.index, fill_value=False)

    # Fallback: dayfirst inference on any still-unparsed rows
    if remaining.any():
        import warnings
        with warnings.catch_warnings():
            warnings.filterwarnings("ignore", category=UserWarning, message="Could not infer format")
            parsed = pd.to_datetime(s[remaining], errors="coerce", dayfirst=True)
        filled = parsed.notna()
        result[remaining & filled.reindex(series.index, fill_value=False)] = parsed[filled]

    # Localize IST → UTC (vectorized)
    result = pd.to_datetime(result, errors="coerce")
    result = result.dt.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="NaT")
    result = result.dt.tz_convert("UTC")
    return result


def _to_date_utc_series(series: pd.Series, formats: list) -> pd.Series:
    """Vectorized date-only → midnight IST → UTC conversion."""
    s = series.astype(str).str.strip()
    s = s.where(~s.str.lower().isin({"", "nan", "none", "nat"}), other=pd.NaT)

    result = pd.Series(pd.NaT, index=series.index)
    remaining = s.notna()

    for fmt in formats:
        if not remaining.any():
            break
        parsed = pd.to_datetime(s[remaining], format=fmt, errors="coerce")
        # Normalize to midnight
        parsed = parsed.dt.normalize()
        filled = parsed.notna()
        result[remaining & filled.reindex(series.index, fill_value=False)] = parsed[filled]
        remaining = remaining & ~filled.reindex(series.index, fill_value=False)

    result = pd.to_datetime(result, errors="coerce")
    result = result.dt.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="NaT")
    result = result.dt.tz_convert("UTC")
    return result


# ── Metadata ─────────────────────────────────────────────────────────────────

def _extract_metadata(df_raw: pd.DataFrame) -> dict:
    """
    Extract FROM DATE / TO DATE / Carrier from header rows.
    Scans only the first 12 rows — metadata is always in the report header.
    Handles both:
      - value embedded in same cell: "FROM DATE :06MAY2026"
      - value in next cell:          "FROM DATE"  |  "06MAY2026"
    """
    metadata = {}
    # Limit scan to first 12 rows — metadata never appears in data rows.
    # iterrows over 18k rows costs ~8s; over 12 rows costs <1ms.
    for _, row in df_raw.head(12).iterrows():
        row_vals = row.dropna().astype(str).str.strip().tolist()
        row_str  = " ".join(row_vals).upper()
        if "FROM DATE" not in row_str and "TO DATE" not in row_str:
            continue
        for i, val in enumerate(row_vals):
            uv = val.upper()
            # Embedded pattern: "FROM DATE :06MAY2026"
            m = re.search(r"FROM\s*DATE\s*[:\s]+(\S+)", uv)
            if m:
                metadata["from_date"] = m.group(1).strip(": ")
            m = re.search(r"TO\s*DATE\s*[:\s]+(\S+)", uv)
            if m:
                metadata["to_date"] = m.group(1).strip(": ")
            # Fallback: next-cell pattern
            if "FROM DATE" in uv and "from_date" not in metadata and i + 1 < len(row_vals):
                metadata["from_date"] = row_vals[i + 1].strip(": ")
            if "TO DATE" in uv and "to_date" not in metadata and i + 1 < len(row_vals):
                metadata["to_date"] = row_vals[i + 1].strip(": ")
            if "CARRIER" in uv and i + 1 < len(row_vals):
                metadata["carrier"] = row_vals[i + 1].strip(": ")
    return metadata


def _parse_month_uploaded(metadata: dict) -> str:
    from_date_str = metadata.get("from_date", "")
    try:
        dt = pd.to_datetime(from_date_str, errors="raise")
        return dt.strftime("%Y-%m")
    except Exception:
        return pd.Timestamp.now().strftime("%Y-%m")


def validate_single_day_today(metadata: dict) -> pd.Timestamp:
    """
    Validates:
      1. FROM DATE and TO DATE are present and parseable.
      2. FROM DATE == TO DATE (report must cover exactly one day).
      3. That date == today in IST (strict — no tolerance).
    Returns the report date as a pd.Timestamp (date only, no tz).
    """
    from_date_str = metadata.get("from_date")
    to_date_str   = metadata.get("to_date")

    if not from_date_str or not to_date_str:
        raise ValueError("FROM DATE or TO DATE missing in report metadata.")

    try:
        from_dt = pd.to_datetime(from_date_str)
        to_dt   = pd.to_datetime(to_date_str)
    except Exception:
        raise ValueError("Unable to parse FROM DATE / TO DATE from report.")

    # Must be same single day
    if from_dt.date() != to_dt.date():
        raise ValueError(
            f"Report must cover a single day. "
            f"FROM DATE ({from_dt.date()}) ≠ TO DATE ({to_dt.date()})."
        )

    # Must be today in IST
    _IST = pytz.timezone("Asia/Kolkata")
    today_ist = datetime.now(_IST).date()
    report_date = from_dt.date()

    if report_date != today_ist:
        raise ValueError(
            f"Report date ({report_date}) must be today's date ({today_ist} IST). "
            f"Only today's report can be uploaded."
        )

    return pd.Timestamp(from_dt.date())


def _find_header_row(df_raw: pd.DataFrame) -> int:
    for i, row in df_raw.iterrows():
        vals = row.dropna().astype(str).str.upper().str.strip().tolist()
        if "AWB NO" in vals or "FLIGHT NO." in vals or "FLIGHT NO" in vals:
            return i
    raise ValueError("Could not find header row with 'AWB No' / 'Flight No.' column.")


def _read_raw_csv(file_bytes: BytesIO) -> pd.DataFrame:
    """
    Read CSV with variable column counts into a uniform DataFrame.
    Uses pandas engine with a pre-computed column count — much faster
    than a Python-level line-by-line pad loop on 18k+ rows.
    """
    raw_text = file_bytes.read().decode("utf-8", errors="replace")
    file_bytes.seek(0)

    lines    = raw_text.splitlines()
    max_cols = max((line.count(",") for line in lines), default=0) + 1

    # Let pandas parse; name every column 0..max_cols-1 so short rows get NaN
    # instead of raising. engine="python" handles variable-width rows cleanly.
    return pd.read_csv(
        file_bytes,
        header=None,
        names=range(max_cols),
        dtype=str,
        keep_default_na=False,   # keep empty strings as "" not NaN
        engine="c",
        on_bad_lines="skip",
    )


# ── Main cleaner ─────────────────────────────────────────────────────────────

def clean_import_segregation_report(
    file_bytes: BytesIO,
    file_type: str = "csv",
) -> tuple[pd.DataFrame, dict]:
    """
    Parse and clean the Segregation Report (CSV or Excel).
    Returns only rows where Billing SHC is TRM or TPV.
    """

    # ── 1. Read raw file (no header) ─────────────────────────────────────────
    if file_type == "excel":
        df_raw = pd.read_excel(file_bytes, header=None, dtype=str)
    elif file_type == "csv":
        df_raw = _read_raw_csv(file_bytes)
    else:
        raise ValueError("Unsupported file_type. Use 'excel' or 'csv'.")

    # ── 2. Extract + validate metadata ───────────────────────────────────────
    metadata       = _extract_metadata(df_raw)
    report_date    = validate_single_day_today(metadata)   # raises if invalid
    month_uploaded = _parse_month_uploaded(metadata)
    print(f"[meta] from={metadata.get('from_date')}  to={metadata.get('to_date')}  month={month_uploaded}")

    # ── 3. Locate header row ──────────────────────────────────────────────────
    header_row_idx = _find_header_row(df_raw)
    print(f"[header] found at raw row index {header_row_idx}")

    # ── 4. Build df: header row → column names, everything below → data ───────
    if file_type == "excel":
        file_bytes.seek(0)
        df = pd.read_excel(file_bytes, header=header_row_idx, dtype=str)
        # Excel gives UNNAMED cols for blank header cells — handled in step 5
        df.columns = [str(c).strip() for c in df.columns]
    else:
        # Slice df_raw: header row values become column names
        header_vals = [str(v).strip() for v in df_raw.iloc[header_row_idx].tolist()]
        data        = df_raw.iloc[header_row_idx + 1:].copy()
        data.columns = header_vals
        df = data.reset_index(drop=True)

    # ── 5. Drop junk columns ──────────────────────────────────────────────────
    # After slicing, padding columns are named "" or "nan" or pure integers.
    # Excel gives "Unnamed: N" style names for blank header cells.
    # Keep only columns with a real non-empty, non-numeric name.
    def _is_valid_col(name: str) -> bool:
        n = name.strip()
        if not n or n.lower() == "nan":
            return False
        if n.upper().startswith("UNNAMED"):
            return False
        # Pure integer names are padding artefacts from _read_raw_csv
        try:
            int(n)
            return False
        except ValueError:
            return True

    df = df.loc[:, [c for c in df.columns if _is_valid_col(c)]].copy()

    # ── 6. Drop subtotal / grand-total / NIL CARRIER rows (vectorized) ─────────
    # Check only the first 3 columns — all markers appear there.
    # Avoid df.apply(axis=1) which is ~15x slower on 18k rows.
    col0 = df.iloc[:, 0].fillna("").astype(str).str.strip().str.upper()
    col2 = df.iloc[:, 2].fillna("").astype(str).str.strip().str.upper()

    # NIL CARRIER: chop everything from first matching row onward
    nil_mask = col0.str.contains("NIL CARRIER", na=False) | col2.str.contains("NIL CARRIER", na=False)
    if nil_mask.any():
        df = df.iloc[: nil_mask.values.argmax()]
        col0 = col0.iloc[: len(df)]
        col2 = col2.iloc[: len(df)]

    # Subtotal rows: col2 == "TOTAL"
    df = df[col2.loc[df.index] != "TOTAL"].copy()

    # Grand total: scan only first 4 cols joined — avoids full-row string join
    # GRAND TOTAL marker always appears in first or second col — no need for row join
    grand_col = df.iloc[:, 0].fillna("").astype(str).str.upper()
    df = df[~grand_col.str.contains("GRAND TOTAL", na=False)].copy()

    # ── 7. Validate required columns ─────────────────────────────────────────
    missing = [c for c in REQUIRED_COLUMNS if c not in df.columns]
    if missing:
        raise ValueError(f"Missing required columns: {missing}")

    df = df[REQUIRED_COLUMNS].copy()

    # ── 8. Filter: Billing SHC FIRST — reduces rows before all heavy work ────
    # On 18k rows with ~2.8k valid: filters out 15k rows before any cleanup,
    # cutting all subsequent work by ~85%.
    billing = df["Billing SHC"].astype(str).str.strip().str.upper()
    df = df[billing.isin(BILLING_SHC_FILTER)].copy()
    print(f"[filter] rows after Billing SHC filter (TRM/TPV): {len(df)}")

    if df.empty:
        return df, metadata

    # ── 9. Diagnostic: warn if any TRM/TPV rows have blank Flight No. ─────────
    # This should never happen per business rules, but log it so we can
    # diagnose production files without crashing the upload.
    blank_fn = df["Flight No."].astype(str).str.strip().isin(["", "nan", "None"])
    if blank_fn.any():
        print(f"[warn] {blank_fn.sum()} TRM/TPV rows have blank Flight No. — AWBs: "
              f"{df.loc[blank_fn, 'AWB No'].astype(str).str.strip().tolist()[:10]}")

    # ── 10. Basic cleanup on filtered rows only ───────────────────────────────
    df = df.apply(lambda col: col.map(lambda x: np.nan if isinstance(x, str) and x.strip() == "" else x))
    df = df.dropna(how="all")

    # ── 11. Keep rows where AWB No is non-empty ───────────────────────────────
    if "AWB No" in df.columns:
        df = df[df["AWB No"].astype(str).str.strip().str.len() > 3]

    # ── 12. Strip whitespace on all cells ────────────────────────────────────
    for col in df.columns:
        df[col] = df[col].astype(str).str.strip()
    for col in df.columns:
        if df[col].dtype == object:
            df[col] = df[col].apply(
                lambda x: np.nan if isinstance(x, str) and x.strip().lower() in ("nan", "") else x
            )

    # ── 13. Clean AWB ─────────────────────────────────────────────────────────
    df["AWB No"] = df["AWB No"].apply(_clean_awb)

    # ── 14. Cast numeric columns ──────────────────────────────────────────────
    for col in NUMERIC_COLS:
        df[col] = pd.to_numeric(df[col], errors="coerce")

    # ── 15. Parse Flight Date (date-only → midnight IST → UTC) ───────────────
    flight_date_fmts = [
        "%d-%b-%y",   # 05-MAY-26
        "%d-%b-%Y",   # 05-MAY-2026
        "%d/%m/%y",   # 05/05/26
        "%d/%m/%Y",   # 05/05/2026
    ]
    df[FLIGHT_DATE_COL] = _to_date_utc_series(df[FLIGHT_DATE_COL], flight_date_fmts)

    # ── 16. Parse all other datetime columns (IST → UTC) — vectorized ────────
    dt_fmts = [
        "%d/%m/%y %H:%M",      # 05/05/26 22:19
        "%d/%m/%y %H:%M:%S",   # 06/05/26 00:28:30
        "%d/%m/%Y %H:%M",
        "%d/%m/%Y %H:%M:%S",
        "%d-%b-%y %H:%M",
        "%d-%b-%Y %H:%M",
        "%Y-%m-%d %H:%M:%S",
    ]
    for col in DATETIME_COLS:
        df[col] = _to_utc_series(df[col], dt_fmts)

    # ── 17. Standardise remaining text columns ────────────────────────────────
    text_cols = [
        c for c in REQUIRED_COLUMNS
        if c not in NUMERIC_COLS + DATETIME_COLS + [FLIGHT_DATE_COL]
    ]
    for col in text_cols:
        s = df[col].astype(str).str.strip()
        df[col] = s.where(s.str.lower() != "nan", other=np.nan)

    # ── 18. Drop rows with no valid AWB ──────────────────────────────────────
    df = df.dropna(subset=["AWB No"])

    # ── 19. Attach metadata columns ───────────────────────────────────────────
    df["month_uploaded"] = month_uploaded
    df["report_date"]    = report_date.date()   # plain Python date — no tz, stored as DATE in DB
    df["uploaded_at"]    = datetime.now(tz=timezone.utc)

    # ── 20. Final cleanup ─────────────────────────────────────────────────────
    # Re-cast all datetime cols to UTC after text cleanup (replace NaN→None
    # can strip the tz dtype). This ensures proper datetime64[us, UTC] dtype
    # on all datetime columns going into the DB layer.
    all_dt_cols = DATETIME_COLS + [FLIGHT_DATE_COL, "uploaded_at"]
    for col in all_dt_cols:
        if col in df.columns:
            df[col] = pd.to_datetime(df[col], errors="coerce", utc=True)

    # Replace remaining NaN/NaT with None for asyncpg compatibility
    df = df.where(df.notna(), other=None)

    # Re-apply report_date as proper datetime.date (df.where strips the type)
    if "report_date" in df.columns:
        df["report_date"] = df["report_date"].apply(
            lambda x: x if isinstance(x, __import__("datetime").date) else
            pd.Timestamp(x).date() if x is not None else None
        )

    df = df.reset_index(drop=True)

    return df, metadata


# ── Quick inspection ──────────────────────────────────────────────────────────

if __name__ == "__main__":
    import sys
    import os

    path = sys.argv[1] if len(sys.argv) > 1 else None

    # Fallback: look in same directory as this script
    if path is None:
        script_dir = os.path.dirname(os.path.abspath(__file__))
        for fname in os.listdir(script_dir):
            if fname.upper().endswith(".CSV"):
                path = os.path.join(script_dir, fname)
                break

    if path is None:
        print("Usage: python import_segrigation_report_cleaning.py <path/to/file.csv>")
        sys.exit(1)

    print(f"[input] {path}")
    with open(path, "rb") as f:
        raw = f.read()

    df, meta = clean_import_segregation_report(BytesIO(raw), file_type="csv")

    pd.set_option("display.max_columns", None)
    pd.set_option("display.width", 220)
    pd.set_option("display.max_colwidth", 28)

    print(f"\n{'='*60}")
    print(f"Metadata  : {meta}")
    print(f"Rows      : {len(df)}")
    print(f"Columns   : {list(df.columns)}")

    print(f"\n--- dtypes ---")
    print(df.dtypes.to_string())

    print(f"\n--- Sample rows (first 5) ---")
    print(df.head(5).to_string())

    print(f"\n--- Billing SHC value counts ---")
    print(df["Billing SHC"].value_counts())

    print(f"\n--- Flight Date samples ---")
    print(df["Flight Date"].dropna().head(5).to_string())

    print(f"\n--- ATA_Date/Time samples ---")
    print(df["ATA_Date/Time"].dropna().head(5).to_string())

    print(f"\n--- RCF date samples ---")
    print(df["RCF date"].dropna().head(5).to_string())

    print(f"\n--- AWB No samples ---")
    print(df["AWB No"].dropna().head(10).tolist())

    print(f"\n--- Null counts ---")
    print(df.isnull().sum().to_string())