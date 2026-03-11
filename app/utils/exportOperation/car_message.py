# """
# CAR MESSAGE REPORT - Data Cleaning Function
# ============================================
# Structure observed:
# - Row 6: Header row
# - Row 7+: 'Date' separator rows (e.g. Date | 01-Feb-26) — skip
# - Data rows come in PAIRS per AWB group:
#     * "Master" rows: have Sl.No., AWB, SB No., SB DATE, HWB, PCS, GWT, CHG WT, NOG, SHC, CAR MSG DATE, CAR MSG TIME — but NO ORIGIN/DEST
#     * "Detail" row (last row of each AWB group): has AWB, ORIGIN, DESTINATION, summary PCS/wts — but NO CAR MSG DATE/TIME
# - DAY TOTAL / GRAND TOTAL rows — skip
# - Goal: Produce one clean row per AWB group with:
#     Origin, Destination (from detail row)
#     CAR MSG DATE, CAR MSG TIME (from master rows — fill forward from previous same AWB if missing)
# """

# import pandas as pd
# import numpy as np
# import openpyxl
# from datetime import datetime


# def load_raw_rows(filepath: str, sheet_index: int = 0) -> list[dict]:
#     """Load all raw rows from the Excel file preserving original values."""
#     wb = openpyxl.load_workbook(filepath)
#     ws = wb.worksheets[sheet_index]

#     headers = [
#         "col_A", "SL_NO", "AWB_NO", "ORIGIN", "DESTINATION",
#         "SB_NO", "SB_DATE", "HWB_NO", "PCS", "GROSS_WT",
#         "VOLUMETRIC_WT", "CHG_WT", "NOG", "SHC", "CAR_MSG_DATE", "CAR_MSG_TIME"
#     ]

#     rows = []
#     for row in ws.iter_rows(min_row=7, values_only=True):  # skip title + header
#         row_dict = dict(zip(headers, row))
#         rows.append(row_dict)

#     return rows


# def is_separator_row(row: dict) -> bool:
#     """Detect DAY TOTAL, GRAND TOTAL, Date header rows, or fully empty rows."""
#     sl = str(row.get("SL_NO", "") or "").strip()
#     awb = str(row.get("AWB_NO", "") or "").strip()

#     # DAY TOTAL / GRAND TOTAL
#     if sl in ("DAY TOTAL", "GRAND TOTAL"):
#         return True
#     # Date separator row: SL_NO == 'Date' and AWB_NO is a date
#     if sl == "Date":
#         return True
#     # Fully empty / whitespace
#     non_null = [v for v in row.values() if v is not None and str(v).strip() != ""]
#     if len(non_null) == 0:
#         return True

#     return False


# def is_detail_row(row: dict) -> bool:
#     """
#     The 'detail' row for an AWB group:
#     - SL_NO is None (no serial number)
#     - Has ORIGIN and DESTINATION
#     - Has AWB_NO same as its group
#     """
#     sl = row.get("SL_NO")
#     origin = row.get("ORIGIN")
#     dest = row.get("DESTINATION")
#     awb = row.get("AWB_NO")

#     return (
#         sl is None
#         and awb is not None
#         and str(awb).strip() != ""
#         and origin is not None
#         and str(origin).strip() != ""
#         and dest is not None
#         and str(dest).strip() != ""
#     )


# def clean_car_message(filepath: str, sheet_index: int = 0) -> pd.DataFrame:
#     """
#     Main cleaning function.

#     Returns a DataFrame where:
#     - Each row = one AWB sub-shipment record (one SB No.)
#     - Origin & Destination are filled from the AWB group's detail row
#     - CAR_MSG_DATE & CAR_MSG_TIME are filled from the master row (or propagated
#       from a previous record with the same AWB if missing)
#     """
#     raw_rows = load_raw_rows(filepath, sheet_index)

#     # ── Step 1: Filter out separator / total / empty rows ──────────────────────
#     data_rows = [r for r in raw_rows if not is_separator_row(r)]

#     # ── Step 2: Group consecutive rows by AWB ─────────────────────────────────
#     #   Each AWB block = one or more master rows + one detail row at the end.
#     #   Build a list of blocks: {awb, master_rows[], detail_row}

#     blocks = []
#     current_awb = None
#     current_block = {"awb": None, "masters": [], "detail": None}

#     for row in data_rows:
#         awb = str(row.get("AWB_NO", "") or "").strip()
#         if not awb:
#             continue

#         if is_detail_row(row):
#             # Close out current block
#             if current_block["awb"] == awb:
#                 current_block["detail"] = row
#             else:
#                 # Detail row for a different AWB (shouldn't happen, but handle)
#                 if current_block["awb"]:
#                     blocks.append(current_block)
#                 current_block = {"awb": awb, "masters": [], "detail": row}
#             blocks.append(current_block)
#             current_block = {"awb": None, "masters": [], "detail": None}
#             current_awb = None
#         else:
#             # Master row
#             if awb != current_awb:
#                 if current_block["awb"] is not None:
#                     # Previous block had no detail row yet — save it anyway
#                     blocks.append(current_block)
#                 current_block = {"awb": awb, "masters": [], "detail": None}
#                 current_awb = awb
#             current_block["masters"].append(row)

#     # Flush last block
#     if current_block["awb"]:
#         blocks.append(current_block)

#     # ── Step 3: Flatten blocks into records ────────────────────────────────────
#     #   Skip blocks that have no detail row (no Origin/Destination).
#     #   For each master row in the block, emit one record.

#     # Keep track of last-seen CAR_MSG_DATE/TIME per AWB for back-fill
#     awb_last_car_date: dict[str, tuple] = {}

#     records = []
#     for block in blocks:
#         awb = block["awb"]
#         detail = block["detail"]
#         masters = block["masters"]

#         if detail is None:
#             # No Origin/Destination found for this block — skip per requirements
#             continue

#         origin = str(detail.get("ORIGIN", "") or "").strip()
#         destination = str(detail.get("DESTINATION", "") or "").strip()

#         if not origin or not destination:
#             continue

#         # If no master rows, still emit one record using the detail row data
#         if not masters:
#             masters = [detail]

#         for master in masters:
#             car_date = master.get("CAR_MSG_DATE")
#             car_time = master.get("CAR_MSG_TIME")

#             # If missing, try to reuse same-AWB previous value
#             if car_date is None and car_time is None:
#                 prev = awb_last_car_date.get(awb)
#                 if prev:
#                     car_date, car_time = prev

#             # Update tracker if we have values
#             if car_date is not None or car_time is not None:
#                 awb_last_car_date[awb] = (car_date, car_time)

#             records.append({
#                 "AWB_NO":          awb,
#                 "ORIGIN":          origin,
#                 "DESTINATION":     destination,
#                 "SL_NO":           master.get("SL_NO"),
#                 "SB_NO":           master.get("SB_NO"),
#                 "SB_DATE":         master.get("SB_DATE"),
#                 "HWB_NO":          master.get("HWB_NO"),
#                 "PCS":             master.get("PCS"),
#                 "GROSS_WT":        master.get("GROSS_WT"),
#                 "VOLUMETRIC_WT":   master.get("VOLUMETRIC_WT"),
#                 "CHG_WT":          master.get("CHG_WT"),
#                 "NOG":             master.get("NOG"),
#                 "SHC":             master.get("SHC"),
#                 "CAR_MSG_DATE":    car_date,
#                 "CAR_MSG_TIME":    car_time,
#             })

#     df = pd.DataFrame(records)

#     # ── Step 4: Type cleanup ───────────────────────────────────────────────────
#     if not df.empty:
#         df["SB_DATE"] = pd.to_datetime(df["SB_DATE"], errors="coerce")
#         df["CAR_MSG_DATE"] = pd.to_datetime(df["CAR_MSG_DATE"], errors="coerce")

#         numeric_cols = ["PCS", "GROSS_WT", "VOLUMETRIC_WT", "CHG_WT"]
#         for col in numeric_cols:
#             df[col] = pd.to_numeric(df[col], errors="coerce")

#         df["AWB_NO"] = df["AWB_NO"].astype(str).str.strip()
#         df["HWB_NO"] = df["HWB_NO"].astype(str).str.strip()
#         df["SB_NO"] = df["SB_NO"].astype(str).str.strip()

#         # Reorder columns
#         col_order = [
#             "AWB_NO", "ORIGIN", "DESTINATION", "SL_NO",
#             "SB_NO", "SB_DATE", "HWB_NO",
#             "PCS", "GROSS_WT", "VOLUMETRIC_WT", "CHG_WT",
#             "NOG", "SHC", "CAR_MSG_DATE", "CAR_MSG_TIME"
#         ]
#         df = df[[c for c in col_order if c in df.columns]]
#         df = df.reset_index(drop=True)

#     return df


# # ── Entry point ──────────────────────────────────────────────────────────────
# if __name__ == "__main__":
#     import sys

#     input_file = sys.argv[1] if len(sys.argv) > 1 else "car-message.xlsx"
#     output_file = sys.argv[2] if len(sys.argv) > 2 else "car_message_cleaned.xlsx"

#     print(f"Reading: {input_file}")
#     df = clean_car_message(input_file)

#     print(f"\nCleaned records: {len(df)}")
#     print(f"Columns: {list(df.columns)}")
#     print(f"\nSample (first 5 rows):")
#     print(df.head(5).to_string())

#     print(f"\nRecords WITH Origin+Destination: {df[df['ORIGIN'].notna() & df['DESTINATION'].notna()].shape[0]}")
#     print(f"Records missing CAR_MSG_DATE: {df['CAR_MSG_DATE'].isna().sum()}")

#     df.to_excel(output_file, index=False)
#     print(f"\nSaved to: {output_file}")





# =============================================================================================

# """
# CAR MESSAGE REPORT - Strict Cleaner (No SL_NO Used)
# ---------------------------------------------------
# Rules:
# 1. Keep ONLY rows that have ORIGIN and DESTINATION.
# 2. For each such row:
#    - Take CAR_MSG_DATE and CAR_MSG_TIME
#      from its immediate previous row
#      ONLY IF previous row has same AWB_NO.
# 3. SL_NO is completely ignored.
# 4. No grouping logic.
# 5. No duplicate records.
# """

# import pandas as pd
# import openpyxl
# import re


# def normalize_awb_no(value) -> str | None:
#     if not value:
#         return None

#     value = str(value).strip()
#     cleaned = re.sub(r"\D", "", value)

#     if len(cleaned) == 11:
#         return cleaned
#     if len(cleaned) == 10:
#         return "0" + cleaned

#     return None


# def load_raw_rows(filepath: str, sheet_index: int = 0):
#     wb = openpyxl.load_workbook(filepath)
#     ws = wb.worksheets[sheet_index]

#     headers = [
#         "col_A", "SL_NO", "AWB_NO", "ORIGIN", "DESTINATION",
#         "SB_NO", "SB_DATE", "HWB_NO", "PCS", "GROSS_WT",
#         "VOLUMETRIC_WT", "CHG_WT", "NOG", "SHC",
#         "CAR_MSG_DATE", "CAR_MSG_TIME"
#     ]

#     rows = []
#     for row in ws.iter_rows(min_row=7, values_only=True):
#         row_dict = dict(zip(headers, row))
#         rows.append(row_dict)

#     return rows


# def is_separator_row(row: dict) -> bool:
#     sl = str(row.get("SL_NO", "") or "").strip()

#     if sl in ("DAY TOTAL", "GRAND TOTAL"):
#         return True

#     if sl == "Date":
#         return True

#     non_null = [v for v in row.values() if v is not None and str(v).strip() != ""]
#     return len(non_null) == 0


# def clean_car_message(filepath: str, sheet_index: int = 0) -> pd.DataFrame:

#     raw_rows = load_raw_rows(filepath, sheet_index)
#     data_rows = [r for r in raw_rows if not is_separator_row(r)]

#     records = []

#     for i in range(1, len(data_rows)):

#         current = data_rows[i]

#         # Normalize AWB
#         awb = normalize_awb_no(current.get("AWB_NO"))

#         origin = str(current.get("ORIGIN", "") or "").strip()
#         destination = str(current.get("DESTINATION", "") or "").strip()

#         # Only keep if:
#         # 1) Valid normalized AWB
#         # 2) Origin present
#         # 3) Destination present
#         if not awb or not origin or not destination:
#             continue

#         previous = data_rows[i - 1]
#         prev_awb = normalize_awb_no(previous.get("AWB_NO"))

#         car_date = None
#         car_time = None

#         # Only take CAR message if previous row has same cleaned AWB
#         if prev_awb == awb:
#             car_date = previous.get("CAR_MSG_DATE")
#             car_time = previous.get("CAR_MSG_TIME")

#         records.append({
#             "AWB_NO": awb,
#             "ORIGIN": origin,
#             "DESTINATION": destination,
#             "SB_NO": previous.get("SB_NO") if prev_awb == awb else None,
#             "SB_DATE": previous.get("SB_DATE") if prev_awb == awb else None,
#             "HWB_NO": previous.get("HWB_NO") if prev_awb == awb else None,
#             "PCS": previous.get("PCS") if prev_awb == awb else None,
#             "GROSS_WT": previous.get("GROSS_WT") if prev_awb == awb else None,
#             "VOLUMETRIC_WT": previous.get("VOLUMETRIC_WT") if prev_awb == awb else None,
#             "CHG_WT": previous.get("CHG_WT") if prev_awb == awb else None,
#             "NOG": previous.get("NOG") if prev_awb == awb else None,
#             "SHC": previous.get("SHC") if prev_awb == awb else None,
#             "CAR_MSG_DATE": car_date,
#             "CAR_MSG_TIME": car_time,
#         })

#     df = pd.DataFrame(records)

#     if not df.empty:
#         df["SB_DATE"] = pd.to_datetime(df["SB_DATE"], errors="coerce")
#         df["CAR_MSG_DATE"] = pd.to_datetime(df["CAR_MSG_DATE"], errors="coerce")

#         numeric_cols = ["PCS", "GROSS_WT", "VOLUMETRIC_WT", "CHG_WT"]
#         for col in numeric_cols:
#             df[col] = pd.to_numeric(df[col], errors="coerce")

#         df = df.reset_index(drop=True)

#     return df













# import pandas as pd
# import openpyxl
# import re
# import pytz
# from datetime import datetime

# IST = pytz.timezone("Asia/Kolkata")
# UTC = pytz.utc


# # ─────────────────────────────────────────────
# # Normalize AWB
# # ─────────────────────────────────────────────
# def normalize_awb_no(value) -> str | None:
#     if not value:
#         return None

#     value = str(value).strip()
#     cleaned = re.sub(r"\D", "", value)

#     if len(cleaned) == 11:
#         return cleaned
#     if len(cleaned) == 10:
#         return "0" + cleaned

#     return None


# # ─────────────────────────────────────────────
# # IST → UTC Combo Builder
# # ─────────────────────────────────────────────
# def build_utc_combo(date_value, time_value):
#     if not date_value:
#         return None

#     if not time_value:
#         time_value = "00:00:00"

#     try:
#         dt = datetime.combine(
#             date_value,
#             datetime.strptime(time_value, "%H:%M:%S").time()
#         )

#         ist_dt = IST.localize(dt)
#         return ist_dt.astimezone(UTC)

#     except Exception:
#         return None


# # ─────────────────────────────────────────────
# # Load Raw Rows
# # ─────────────────────────────────────────────
# def load_raw_rows(filepath: str, sheet_index: int = 0):
#     wb = openpyxl.load_workbook(filepath)
#     ws = wb.worksheets[sheet_index]

#     headers = [
#         "col_A", "SL_NO", "AWB_NO", "ORIGIN", "DESTINATION",
#         "SB_NO", "SB_DATE", "HWB_NO", "PCS", "GROSS_WT",
#         "VOLUMETRIC_WT", "CHG_WT", "NOG", "SHC",
#         "CAR_MSG_DATE", "CAR_MSG_TIME"
#     ]

#     rows = []
#     for row in ws.iter_rows(min_row=7, values_only=True):
#         rows.append(dict(zip(headers, row)))

#     return rows


# # ─────────────────────────────────────────────
# # Remove Separator Rows
# # ─────────────────────────────────────────────
# def is_separator_row(row: dict) -> bool:
#     sl = str(row.get("SL_NO", "") or "").strip()

#     if sl in ("DAY TOTAL", "GRAND TOTAL"):
#         return True

#     if sl == "Date":
#         return True

#     non_null = [v for v in row.values() if v is not None and str(v).strip() != ""]
#     return len(non_null) == 0


# # ─────────────────────────────────────────────
# # MAIN CLEANER
# # ─────────────────────────────────────────────
# def clean_car_message(filepath: str, sheet_index: int = 0) -> pd.DataFrame:

#     raw_rows = load_raw_rows(filepath, sheet_index)
#     data_rows = [r for r in raw_rows if not is_separator_row(r)]

#     records = []

#     for i in range(1, len(data_rows)):

#         current = data_rows[i]

#         awb = normalize_awb_no(current.get("AWB_NO"))
#         origin = str(current.get("ORIGIN", "") or "").strip()
#         destination = str(current.get("DESTINATION", "") or "").strip()

#         if not awb or not origin or not destination:
#             continue

#         previous = data_rows[i - 1]
#         prev_awb = normalize_awb_no(previous.get("AWB_NO"))

#         car_date = None
#         car_time = None

#         if prev_awb == awb:
#             car_date = previous.get("CAR_MSG_DATE")
#             car_time = previous.get("CAR_MSG_TIME")

#         # Convert date properly
#         if car_date:
#             car_date = pd.to_datetime(car_date, errors="coerce")
#             if pd.notna(car_date):
#                 car_date = car_date.date()
#             else:
#                 car_date = None

#         # Convert time properly
#         if car_time:
#             try:
#                 car_time = str(pd.to_datetime(car_time).time())
#             except Exception:
#                 car_time = None

#         combo_utc = build_utc_combo(car_date, car_time)

#         records.append({
#             "awb_no": awb,
#             "origin": origin,
#             "destination": destination,
#             "sb_no": previous.get("SB_NO") if prev_awb == awb else None,
#             "sb_date": previous.get("SB_DATE") if prev_awb == awb else None,
#             "hwb_no": previous.get("HWB_NO") if prev_awb == awb else None,
#             "pcs": previous.get("PCS") if prev_awb == awb else None,
#             "gross_wt": previous.get("GROSS_WT") if prev_awb == awb else None,
#             "volumetric_wt": previous.get("VOLUMETRIC_WT") if prev_awb == awb else None,
#             "chg_wt": previous.get("CHG_WT") if prev_awb == awb else None,
#             "nog": previous.get("NOG") if prev_awb == awb else None,
#             "shc": previous.get("SHC") if prev_awb == awb else None,
#             "car_msg_date": car_date,
#             "car_msg_time": car_time,
#             "car_message_datetime_combo": combo_utc,
#         })

#     return pd.DataFrame(records)










import numpy as np
import pandas as pd
import re
import pytz
from datetime import datetime
from typing import Tuple
from io import BytesIO

IST = pytz.timezone("Asia/Kolkata")
UTC = pytz.utc


# ─────────────────────────────────────────────
# Normalize AWB
# ─────────────────────────────────────────────
def normalize_awb_no(value) -> str | None:
    if not value:
        return None

    value = str(value).strip()
    cleaned = re.sub(r"\D", "", value)

    if len(cleaned) == 11:
        return cleaned
    if len(cleaned) == 10:
        return "0" + cleaned

    return None


# ─────────────────────────────────────────────
# IST → UTC Builder
# ─────────────────────────────────────────────
def build_utc_combo(date_value, time_value):
    if not date_value:
        return None

    if not time_value:
        time_value = "00:00:00"

    try:
        dt = datetime.combine(
            date_value,
            datetime.strptime(time_value, "%H:%M:%S").time()
        )

        ist_dt = IST.localize(dt)
        return ist_dt.astimezone(UTC)

    except Exception:
        return None


# ─────────────────────────────────────────────
# Remove separator rows
# ─────────────────────────────────────────────
def is_separator_row(row: dict) -> bool:
    sl = str(row.get("SL_NO", "") or "").strip()

    if sl in ("DAY TOTAL", "GRAND TOTAL"):
        return True

    if sl == "Date":
        return True

    non_null = [v for v in row.values() if pd.notna(v) and str(v).strip() != ""]
    return len(non_null) == 0


# ─────────────────────────────────────────────
# MAIN CLEANER
# ─────────────────────────────────────────────
def clean_car_message(
    file_bytes: BytesIO,
    file_type: str
) -> Tuple[pd.DataFrame, pd.DataFrame]:

    # 🔹 Read file
    if file_type == "excel":
        df_raw = pd.read_excel(file_bytes, header=None)
    else:
        df_raw = pd.read_csv(file_bytes, header=None)

    # 🔹 Map columns (based on your Excel structure)
    headers = [
        "col_A", "SL_NO", "AWB_NO", "ORIGIN", "DESTINATION",
        "SB_NO", "SB_DATE", "HWB_NO", "PCS", "GROSS_WT",
        "VOLUMETRIC_WT", "CHG_WT", "NOG", "SHC",
        "CAR_MSG_DATE", "CAR_MSG_TIME"
    ]

    df_raw = df_raw.iloc[6:]  # Skip first 6 rows (title + header)
    df_raw.columns = headers[:len(df_raw.columns)]

    raw_rows = df_raw.to_dict(orient="records")

    # 🔹 Remove separator rows
    data_rows = [r for r in raw_rows if not is_separator_row(r)]

    cleaned_records = []
    faulty_records = []

    for i in range(1, len(data_rows)):

        current = data_rows[i]

        awb = normalize_awb_no(current.get("AWB_NO"))
        # origin = str(current.get("ORIGIN", "") or "").strip()
        # destination = str(current.get("DESTINATION", "") or "").strip()

        # if not awb or not origin or not destination:
        #     faulty_records.append(current)
        #     continue

        origin_raw = current.get("ORIGIN")
        destination_raw = current.get("DESTINATION")

        if pd.isna(origin_raw) or pd.isna(destination_raw):
            faulty_records.append(current)
            continue

        origin = str(origin_raw).strip()
        destination = str(destination_raw).strip()

        if not origin or not destination:
            faulty_records.append(current)
            continue

        previous = data_rows[i - 1]
        prev_awb = normalize_awb_no(previous.get("AWB_NO"))

        car_date = None
        car_time = None

        if prev_awb == awb:
            # print("DATE RAW:", previous.get("CAR_MSG_DATE"))
            # print("TIME RAW:", previous.get("CAR_MSG_TIME"))
            car_date = previous.get("CAR_MSG_DATE")
            car_time = previous.get("CAR_MSG_TIME")

        # Convert date
        if car_date:
            car_date = pd.to_datetime(car_date, errors="coerce")
            if pd.notna(car_date):
                car_date = car_date.date()
            else:
                car_date = None

        # Convert time

        if car_time:
            if hasattr(car_time, "strftime"):
                car_time = car_time.strftime("%H:%M:%S")
            else:
                try:
                    car_time = pd.to_datetime(car_time).strftime("%H:%M:%S")
                except Exception:
                    car_time = None

        combo_utc = build_utc_combo(car_date, car_time)

        cleaned_records.append({
            "awb_no": awb,
            "origin": origin,
            "destination": destination,
            "sb_no": previous.get("SB_NO") if prev_awb == awb else None,
            "sb_date": previous.get("SB_DATE") if prev_awb == awb else None,
            "hwb_no": previous.get("HWB_NO") if prev_awb == awb else None,
            
            #  "pcs": current.get("PCS"),
            "pcs": int(current.get("PCS")) if current.get("PCS") is not None else None,

            "gross_wt": current.get("GROSS_WT"),
            "volumetric_wt": current.get("VOLUMETRIC_WT"),
            "chg_wt": current.get("CHG_WT"),
            "nog": current.get("NOG"),
            "shc": current.get("SHC"),
            # "gross_wt": previous.get("GROSS_WT") if prev_awb == awb else None,
            # "volumetric_wt": previous.get("VOLUMETRIC_WT") if prev_awb == awb else None,
            # "chg_wt": previous.get("CHG_WT") if prev_awb == awb else None,
            # "nog": previous.get("NOG") if prev_awb == awb else None,
            # "shc": previous.get("SHC") if prev_awb == awb else None,

            "car_msg_date": car_date,
            "car_msg_time": car_time,
            "car_message_datetime_combo": combo_utc,
        })

       
    cleaned_df = pd.DataFrame(cleaned_records)
    faulty_df = pd.DataFrame(faulty_records)

       # Replace pandas NaN/NaT with Python None for database compatibility
    cleaned_df = cleaned_df.replace({np.nan: None, pd.NaT: None})
    faulty_df = faulty_df.replace({np.nan: None, pd.NaT: None})

    # 🔥 Ensure identifier columns are always strings (important for asyncpg)
    string_columns = [
        "awb_no",
        "sb_no",
        "hwb_no",
        "origin",
        "destination",
        "nog",
        "shc",
        "car_msg_time",
    ]

    for col in string_columns:
        if col in cleaned_df.columns:
            cleaned_df[col] = cleaned_df[col].apply(
                lambda x: str(x).strip() if x is not None else None
            )

    print(cleaned_df.head(6))

    return cleaned_df, faulty_df


