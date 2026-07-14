

# import re
# import numpy as np
# import pandas as pd
# import pytz
# from datetime import datetime


# # ─────────────────────────────────────────────
# # Helpers
# # ─────────────────────────────────────────────

# def parse_awb_field(value) -> tuple[str | None, str | None]:
#     """
#     Parse raw AWB field into (awb_no, awb_part).

#     COSYS appends a letter to indicate which part of a split shipment:
#       'P'  → Primary (majority of movements)
#       'A'  → Part A of a split shipment
#       'B'  → Part B of a split shipment

#     Examples
#     --------
#     '217 62504875 P'  → ('21762504875', 'P')
#     '105 51557866 A'  → ('10551557866', 'A')
#     '098 30881476 B'  → ('09830881476', 'B')
#     '21762504875'     → ('21762504875', None)
#     """
#     if value is None or (isinstance(value, float) and np.isnan(value)):
#         return None, None

#     raw = str(value).strip()
#     if not raw or raw.lower() in ('nan', 'none', 'nat'):
#         return None, None

#     tokens = raw.split()

#     # Last token is part indicator if purely alphabetic
#     awb_part = None
#     if tokens and re.fullmatch(r'[A-Za-z]+', tokens[-1]):
#         awb_part = tokens[-1].upper()
#         tokens = tokens[:-1]

#     # Remaining tokens → digits only → normalize to 11 digits
#     digits = re.sub(r'\D', '', ''.join(tokens))
#     if len(digits) == 10:
#         awb_no = '0' + digits
#     elif len(digits) == 11:
#         awb_no = digits
#     else:
#         awb_no = None

#     return awb_no, awb_part


# def ist_datetime_to_utc(dt) -> datetime | None:
#     """
#     Convert a naive datetime (assumed IST) to UTC-aware datetime.
#     Accepts:
#       - Python datetime objects  (pandas already parses Excel datetimes as these)
#       - String representations in common formats
#     Returns timezone-aware UTC datetime, or None if unparseable.
#     """
#     try:
#         if dt is None or (isinstance(dt, float) and np.isnan(dt)):
#             return None
#         if isinstance(dt, pd.NaT.__class__):
#             return None

#         # pandas / openpyxl gives us datetime objects directly from Excel cells
#         if isinstance(dt, datetime):
#             local_dt = dt
#         else:
#             # Fallback string parsing
#             dt_str = str(dt).strip()
#             if dt_str in ('', 'nan', 'None', 'NaT'):
#                 return None
#             formats = [
#                 "%d-%b-%Y %H:%M:%S",
#                 "%d-%m-%Y %H:%M:%S",
#                 "%Y-%m-%d %H:%M:%S",
#                 "%d/%m/%Y %H:%M:%S",
#                 "%Y-%m-%d %H:%M:%S.%f",
#             ]
#             local_dt = None
#             for fmt in formats:
#                 try:
#                     local_dt = datetime.strptime(dt_str, fmt)
#                     break
#                 except ValueError:
#                     continue
#             if local_dt is None:
#                 print(f"[WARN] Could not parse datetime: '{dt_str}'")
#                 return None

#         IST = pytz.timezone("Asia/Kolkata")
#         utc_dt = IST.localize(local_dt).astimezone(pytz.utc)
#         return utc_dt

#     except Exception as e:
#         print(f"[ERROR] ist_datetime_to_utc('{dt}'): {e}")
#         return None


# def clean_str(value) -> str | None:
#     """Strip whitespace and return None for blank / sentinel strings."""
#     NULLISH = {'nan', 'none', 'nat', 'n/a', ''}
#     if value is None:
#         return None
#     s = str(value).strip()
#     return None if s.lower() in NULLISH else s


# # ─────────────────────────────────────────────
# # Main cleaning function
# # ─────────────────────────────────────────────

# def clean_and_parse_truck_in_out_report(file, file_type: str) -> pd.DataFrame:
#     """
#     Parse and clean the Import Truck IN/OUT Excel / CSV report.

#     The report has 5 header rows before the actual column names (row index 5),
#     plus two leading unnamed columns that are dropped.

#     Final columns returned (all datetimes are UTC-aware):
#         gp_no           int
#         date            datetime (UTC)       ← ' DATE' column
#         awb_no          str | None           ← normalized 11-digit
#         awb_part        str | None           ← 'P' / 'A' / 'B' etc.
#         hawb_no         str | None
#         pcs             int | None
#         truck_no        str | None
#         driver_name     str | None
#         mobile_no       str | None           ← stored as string (leading zeros safe)
#         time_in         datetime | None (UTC)
#         time_out        datetime | None (UTC)
#         agent           str | None
#         sis_user_id     str | None

#     Parameters
#     ----------
#     file : path or file-like object
#     file_type : 'excel' or 'csv'
#     """
#     # ── 1. Read raw file ───────────────────────────────────────────────────
#     if file_type.lower() == "csv":
#         df = pd.read_csv(file, header=5)
#     elif file_type.lower() == "excel":
#         df = pd.read_excel(file, header=5)
#     else:
#         raise ValueError("Unsupported file_type. Use 'excel' or 'csv'.")

#     # ── 2. Drop the two leading unnamed columns ────────────────────────────
#     df = df.iloc[:, 2:]

#     # ── 3. Rename to snake_case ────────────────────────────────────────────
#     rename_map = {
#         'GP No':        'gp_no',
#         ' DATE':        'date',
#         'AWB No.':      'awb_no',
#         'HAWB No ':     'hawb_no',
#         'PCS':          'pcs',
#         'Truck No':     'truck_no',
#         'Driver Name':  'driver_name',
#         'Mobile No':    'mobile_no',
#         'Time In':      'time_in',
#         'Time Out':     'time_out',
#         'Agent':        'agent',
#         'USER ID':      'sis_user_id',
#     }
#     df = df[list(rename_map.keys())].rename(columns=rename_map)

#     # ── 4. Drop rows where GP No is missing (footer / blank rows) ─────────
#     df = df[df['gp_no'].notna()].copy()

#     # ── 5. AWB → (awb_no, awb_part) ───────────────────────────────────────
#     parsed = df['awb_no'].apply(parse_awb_field)
#     df['awb_no']   = parsed.apply(lambda t: t[0])
#     df['awb_part'] = parsed.apply(lambda t: t[1])

#     # ── 6. Datetime columns → UTC ──────────────────────────────────────────
#     for col in ('date', 'time_in', 'time_out'):
#         df[col] = df[col].apply(ist_datetime_to_utc)

#     # Validate: date must always be present
#     missing_date = df[df['date'].isna()]
#     if not missing_date.empty:
#         raise ValueError(
#             f"{len(missing_date)} rows have missing or unparseable DATE. "
#             f"GP Nos: {missing_date['gp_no'].tolist()}"
#         )

#     # ── 7. Mobile No → clean string (avoids float like 9971218940.0) ───────
#     def clean_mobile(val) -> str | None:
#         if val is None or (isinstance(val, float) and np.isnan(val)):
#             return None
#         digits = re.sub(r'\D', '', str(val).split('.')[0])
#         return digits if digits else None

#     df['mobile_no'] = df['mobile_no'].apply(clean_mobile)

#     # ── 8. PCS → int (nullable) ────────────────────────────────────────────
#     df['pcs'] = pd.to_numeric(df['pcs'], errors='coerce')
#     df['pcs'] = df['pcs'].apply(lambda x: int(x) if pd.notna(x) else None)

#     # ── 9. GP No → int ────────────────────────────────────────────────────
#     df['gp_no'] = df['gp_no'].apply(lambda x: int(x) if pd.notna(x) else None)

#     # ── 10. Clean all string columns ───────────────────────────────────────
#     str_cols = ['awb_no', 'awb_part', 'hawb_no', 'truck_no', 'driver_name', 'agent', 'sis_user_id']
#     for col in str_cols:
#         df[col] = df[col].apply(clean_str)

#     # ── 11. Reorder columns (awb_part right after awb_no) ─────────────────
#     col_order = [
#         'gp_no', 'date', 'awb_no', 'awb_part', 'hawb_no',
#         'pcs', 'truck_no', 'driver_name', 'mobile_no',
#         'time_in', 'time_out', 'agent', 'sis_user_id',
#     ]
#     df = df[col_order]

#     # ── 12. Replace remaining pandas NA / NaN with None ───────────────────
#     df = df.replace({np.nan: None, pd.NaT: None})

#     return df


# # # ─────────────────────────────────────────────
# # # Quick smoke-test (run directly)
# # # ─────────────────────────────────────────────
# # if __name__ == "__main__":
# #     import sys

# #     path = sys.argv[1] if len(sys.argv) > 1 else "import-truck-in-out-report-22-jun.xlsx"
# #     df = clean_and_parse_truck_in_out_report(path, file_type="excel")

# #     print(f"Rows: {len(df)}")
# #     print(df.dtypes)
# #     print()
# #     print(df.head(3).to_string())
# #     print()
# #     print("awb_part value counts:")
# #     print(df['awb_part'].value_counts(dropna=False))
# #     print()
# #     sample = df[['gp_no', 'date', 'time_in', 'time_out']].head(3)
# #     print("Sample UTC datetimes:")
# #     print(sample.to_string())



























# import re
# import numpy as np
# import pandas as pd
# import pytz
# from datetime import datetime


# # ─────────────────────────────────────────────
# # Helpers
# # ─────────────────────────────────────────────

# def parse_awb_field(value) -> tuple[str | None, str | None]:
#     """
#     Parse raw AWB field into (awb_no, awb_part).

#     COSYS appends a letter to indicate which part of a split shipment:
#       'P' → Primary, 'A' → Part A, 'B' → Part B.

#     '217 62504875 P' → ('21762504875', 'P')
#     '21762504875'    → ('21762504875', None)
#     """
#     if value is None or (isinstance(value, float) and np.isnan(value)):
#         return None, None
#     raw = str(value).strip()
#     if not raw or raw.lower() in ('nan', 'none', 'nat'):
#         return None, None
#     tokens = raw.split()
#     awb_part = None
#     if tokens and re.fullmatch(r'[A-Za-z]+', tokens[-1]):
#         awb_part = tokens[-1].upper()
#         tokens = tokens[:-1]
#     digits = re.sub(r'\D', '', ''.join(tokens))
#     if len(digits) == 10:
#         awb_no = '0' + digits
#     elif len(digits) == 11:
#         awb_no = digits
#     else:
#         awb_no = None
#     return awb_no, awb_part


# def ist_datetime_to_utc(dt) -> datetime | None:
#     """
#     Convert a naive datetime (assumed IST) to UTC-aware datetime.
#     Accepts datetime objects or common string formats, including the CSV's
#     day-first 2-digit-year format '07-07-26 0:33'.
#     """
#     try:
#         if dt is None or (isinstance(dt, float) and np.isnan(dt)):
#             return None
#         if isinstance(dt, pd.NaT.__class__):
#             return None
#         if isinstance(dt, datetime):
#             local_dt = dt
#         else:
#             dt_str = str(dt).strip()
#             if dt_str in ('', 'nan', 'None', 'NaT'):
#                 return None
#             formats = [
#                 "%d-%b-%Y %H:%M:%S",
#                 "%d-%m-%Y %H:%M:%S",
#                 "%Y-%m-%d %H:%M:%S",
#                 "%d/%m/%Y %H:%M:%S",
#                 "%Y-%m-%d %H:%M:%S.%f",
#                 "%d-%m-%y %H:%M:%S",   # 07-07-26 0:33:00
#                 "%d-%m-%y %H:%M",      # 07-07-26 0:33   (this CSV's format)
#                 "%d-%b-%y %H:%M",      # 07-Jul-26 0:33
#             ]
#             local_dt = None
#             for fmt in formats:
#                 try:
#                     local_dt = datetime.strptime(dt_str, fmt)
#                     break
#                 except ValueError:
#                     continue
#             if local_dt is None:
#                 print(f"[WARN] Could not parse datetime: '{dt_str}'")
#                 return None
#         IST = pytz.timezone("Asia/Kolkata")
#         return IST.localize(local_dt).astimezone(pytz.utc)
#     except Exception as e:
#         print(f"[ERROR] ist_datetime_to_utc('{dt}'): {e}")
#         return None


# def clean_str(value) -> str | None:
#     NULLISH = {'nan', 'none', 'nat', 'n/a', ''}
#     if value is None:
#         return None
#     s = str(value).strip()
#     return None if s.lower() in NULLISH else s


# def _clean_gp_no(value) -> str | None:
#     """
#     GP No as a clean STRING. The report includes manual gate passes prefixed
#     'MAN' (e.g. 'MAN90969') alongside numeric ones, so gp_no must be text.
#     Excel may give numeric GPs as floats (26066271.0) → strip the '.0'.
#     """
#     if value is None or (isinstance(value, float) and np.isnan(value)):
#         return None
#     s = str(value).strip()
#     if s.endswith(".0") and s[:-2].isdigit():
#         s = s[:-2]
#     return s or None


# # ─────────────────────────────────────────────
# # Main cleaning function
# # ─────────────────────────────────────────────

# def clean_and_parse_truck_in_out_report(file, file_type: str) -> pd.DataFrame:
#     """
#     Parse and clean the Import Truck IN/OUT Excel / CSV report.

#     The header row ("GP No, DATE, ...") sits at a DIFFERENT offset in CSV vs
#     Excel (different number of title/blank rows), and the CSV has no leading
#     unnamed columns while some Excel exports do. So instead of hardcoding
#     `header=5` and `df.iloc[:, 2:]`, we DETECT the header row and drop leading
#     unnamed columns only when present.

#     gp_no is kept as a STRING to preserve 'MAN...' manual gate passes.
#     All datetimes returned are UTC-aware.
#     """
#     # ── 0. Normalise the input to raw bytes ────────────────────────────────
#     # The file is read TWICE (once to detect the header row, once to parse), so
#     # we must not depend on a stream's cursor position — reading a spent stream
#     # gives pandas "No columns to parse from file". Read the bytes once here and
#     # hand a fresh BytesIO to each pandas call.
#     import io
#     if hasattr(file, "read"):
#         # UploadFile.file, BytesIO, open() handle, etc.
#         try:
#             file.seek(0)
#         except Exception:
#             pass
#         data = file.read()
#         if isinstance(data, str):
#             data = data.encode("utf-8")
#     elif isinstance(file, (bytes, bytearray)):
#         data = bytes(file)
#     else:
#         # A path string — read the file off disk.
#         with open(file, "rb") as fh:
#             data = fh.read()

#     if not data:
#         raise ValueError("Uploaded file is empty (no bytes to parse).")

#     def _reader():
#         """A fresh in-memory stream positioned at 0 for each pandas read."""
#         return io.BytesIO(data)

#     # ── 1. Read raw (no header) and DETECT the header row ──────────────────
#     if file_type.lower() == "csv":
#         raw = pd.read_csv(_reader(), header=None, dtype=str)
#     elif file_type.lower() == "excel":
#         raw = pd.read_excel(_reader(), header=None, dtype=str)
#     else:
#         raise ValueError("Unsupported file_type. Use 'excel' or 'csv'.")

#     header_idx = None
#     for i in range(min(15, len(raw))):
#         row_vals = [str(v).strip() for v in raw.iloc[i].tolist()]
#         if any(v == "GP No" for v in row_vals):
#             header_idx = i
#             break
#     if header_idx is None:
#         raise ValueError("Could not locate the 'GP No' header row in the file.")

#     # ── 2. Re-read using the detected header row (fresh stream) ────────────
#     if file_type.lower() == "csv":
#         df = pd.read_csv(_reader(), header=header_idx)
#     else:
#         df = pd.read_excel(_reader(), header=header_idx)

#     # ── 3. Drop leading unnamed columns ONLY if present ───────────────────
#     lead_drop = 0
#     for col in df.columns:
#         name = str(col).strip()
#         if name == "" or name.lower().startswith("unnamed"):
#             lead_drop += 1
#         else:
#             break
#     if lead_drop:
#         df = df.iloc[:, lead_drop:]

#     # ── 4. Rename to snake_case ────────────────────────────────────────────
#     rename_map = {
#         'GP No':        'gp_no',
#         ' DATE':        'date',
#         'AWB No.':      'awb_no',
#         'HAWB No ':     'hawb_no',
#         'PCS':          'pcs',
#         'Truck No':     'truck_no',
#         'Driver Name':  'driver_name',
#         'Mobile No':    'mobile_no',
#         'Time In':      'time_in',
#         'Time Out':     'time_out',
#         'Agent':        'agent',
#         'USER ID':      'sis_user_id',
#     }
#     df = df[list(rename_map.keys())].rename(columns=rename_map)

#     # ── 5. Drop rows where GP No is missing (footer / blank rows) ─────────
#     df = df[df['gp_no'].notna()].copy()

#     # ── 6. AWB → (awb_no, awb_part) ───────────────────────────────────────
#     parsed = df['awb_no'].apply(parse_awb_field)
#     df['awb_no']   = parsed.apply(lambda t: t[0])
#     df['awb_part'] = parsed.apply(lambda t: t[1])

#     # ── 7. Datetime columns → UTC ──────────────────────────────────────────
#     for col in ('date', 'time_in', 'time_out'):
#         df[col] = df[col].apply(ist_datetime_to_utc)

#     missing_date = df[df['date'].isna()]
#     if not missing_date.empty:
#         raise ValueError(
#             f"{len(missing_date)} rows have missing or unparseable DATE. "
#             f"GP Nos: {missing_date['gp_no'].tolist()[:10]}"
#         )

#     # ── 8. Mobile No → clean string ────────────────────────────────────────
#     def clean_mobile(val):
#         if val is None or (isinstance(val, float) and np.isnan(val)):
#             return None
#         digits = re.sub(r'\D', '', str(val).split('.')[0])
#         return digits if digits else None
#     df['mobile_no'] = df['mobile_no'].apply(clean_mobile)

#     # ── 9. PCS → int (nullable) ────────────────────────────────────────────
#     df['pcs'] = pd.to_numeric(df['pcs'], errors='coerce')
#     df['pcs'] = df['pcs'].apply(lambda x: int(x) if pd.notna(x) else None)

#     # ── 10. GP No → clean STRING (keeps 'MAN...' values) ──────────────────
#     df['gp_no'] = df['gp_no'].apply(_clean_gp_no)

#     # ── 11. Clean all string columns ───────────────────────────────────────
#     str_cols = ['awb_no', 'awb_part', 'hawb_no', 'truck_no', 'driver_name', 'agent', 'sis_user_id']
#     for col in str_cols:
#         df[col] = df[col].apply(clean_str)

#     # ── 12. Reorder columns ────────────────────────────────────────────────
#     df = df[[
#         'gp_no', 'date', 'awb_no', 'awb_part', 'hawb_no',
#         'pcs', 'truck_no', 'driver_name', 'mobile_no',
#         'time_in', 'time_out', 'agent', 'sis_user_id',
#     ]]

#     # ── 13. Replace remaining pandas NA / NaN with None ───────────────────
#     df = df.replace({np.nan: None, pd.NaT: None})

#     return df





















import re
import numpy as np
import pandas as pd
import pytz
from datetime import datetime

# Widest column count we allow when reading a ragged CSV (title/date rows above
# the header have fewer fields than the data rows). Short rows pad with NaN.
_MAX_COLS = 30


# ─────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────

def parse_awb_field(value) -> tuple[str | None, str | None]:
    """
    Parse raw AWB field into (awb_no, awb_part).

    COSYS appends a letter to indicate which part of a split shipment:
      'P' → Primary, 'A' → Part A, 'B' → Part B.

    '217 62504875 P' → ('21762504875', 'P')
    '21762504875'    → ('21762504875', None)
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None, None
    raw = str(value).strip()
    if not raw or raw.lower() in ('nan', 'none', 'nat'):
        return None, None
    tokens = raw.split()
    awb_part = None
    if tokens and re.fullmatch(r'[A-Za-z]+', tokens[-1]):
        awb_part = tokens[-1].upper()
        tokens = tokens[:-1]
    digits = re.sub(r'\D', '', ''.join(tokens))
    if len(digits) == 10:
        awb_no = '0' + digits
    elif len(digits) == 11:
        awb_no = digits
    else:
        awb_no = None
    return awb_no, awb_part


def ist_datetime_to_utc(dt) -> datetime | None:
    """
    Convert a naive datetime (assumed IST) to UTC-aware datetime.
    Accepts datetime objects or common string formats, including the CSV's
    day-first 2-digit-year format '07-07-26 0:33'.
    """
    try:
        if dt is None or (isinstance(dt, float) and np.isnan(dt)):
            return None
        if isinstance(dt, pd.NaT.__class__):
            return None
        if isinstance(dt, datetime):
            local_dt = dt
        else:
            dt_str = str(dt).strip()
            if dt_str in ('', 'nan', 'None', 'NaT'):
                return None
            formats = [
                "%d-%b-%Y %H:%M:%S",
                "%d-%m-%Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S",
                "%d/%m/%Y %H:%M:%S",
                "%Y-%m-%d %H:%M:%S.%f",
                "%d-%m-%y %H:%M:%S",   # 07-07-26 0:33:00
                "%d-%m-%y %H:%M",      # 07-07-26 0:33   (this CSV's format)
                "%d-%b-%y %H:%M",      # 07-Jul-26 0:33
            ]
            local_dt = None
            for fmt in formats:
                try:
                    local_dt = datetime.strptime(dt_str, fmt)
                    break
                except ValueError:
                    continue
            if local_dt is None:
                print(f"[WARN] Could not parse datetime: '{dt_str}'")
                return None
        IST = pytz.timezone("Asia/Kolkata")
        return IST.localize(local_dt).astimezone(pytz.utc)
    except Exception as e:
        print(f"[ERROR] ist_datetime_to_utc('{dt}'): {e}")
        return None


def clean_str(value) -> str | None:
    NULLISH = {'nan', 'none', 'nat', 'n/a', ''}
    if value is None:
        return None
    s = str(value).strip()
    return None if s.lower() in NULLISH else s


def _clean_gp_no(value) -> str | None:
    """
    GP No as a clean STRING. The report includes manual gate passes prefixed
    'MAN' (e.g. 'MAN90969') alongside numeric ones, so gp_no must be text.
    Excel may give numeric GPs as floats (26066271.0) → strip the '.0'.
    """
    if value is None or (isinstance(value, float) and np.isnan(value)):
        return None
    s = str(value).strip()
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s or None


# ─────────────────────────────────────────────
# Main cleaning function
# ─────────────────────────────────────────────

def clean_and_parse_truck_in_out_report(file, file_type: str) -> pd.DataFrame:
    """
    Parse and clean the Import Truck IN/OUT Excel / CSV report.

    The header row ("GP No, DATE, ...") sits at a DIFFERENT offset in CSV vs
    Excel (different number of title/blank rows), and the CSV has no leading
    unnamed columns while some Excel exports do. So instead of hardcoding
    `header=5` and `df.iloc[:, 2:]`, we DETECT the header row and drop leading
    unnamed columns only when present.

    gp_no is kept as a STRING to preserve 'MAN...' manual gate passes.
    All datetimes returned are UTC-aware.
    """
    # ── 0. Normalise the input to raw bytes ────────────────────────────────
    # The file is read TWICE (once to detect the header row, once to parse), so
    # we must not depend on a stream's cursor position — reading a spent stream
    # gives pandas "No columns to parse from file". Read the bytes once here and
    # hand a fresh BytesIO to each pandas call.
    import io
    if hasattr(file, "read"):
        # UploadFile.file, BytesIO, open() handle, etc.
        try:
            file.seek(0)
        except Exception:
            pass
        data = file.read()
        if isinstance(data, str):
            data = data.encode("utf-8")
    elif isinstance(file, (bytes, bytearray)):
        data = bytes(file)
    else:
        # A path string — read the file off disk.
        with open(file, "rb") as fh:
            data = fh.read()

    if not data:
        raise ValueError("Uploaded file is empty (no bytes to parse).")

    def _reader():
        """A fresh in-memory stream positioned at 0 for each pandas read."""
        return io.BytesIO(data)

    # ── 1. Read raw (no header) and DETECT the header row ──────────────────
    # The title/date rows above the header have FEWER fields than the data rows
    # (e.g. a 5-field title, a 7-field date row, then a 14-field header). Pandas'
    # default C parser infers the column count from the first rows and then errors
    # with "Expected 5 fields in line 5, saw 7". Forcing a wide fixed column set
    # (names=range(_MAX_COLS)) makes short rows pad with NaN instead of blowing up,
    # and the python engine is more tolerant of ragged input.
    if file_type.lower() == "csv":
        raw = pd.read_csv(
            _reader(), header=None, dtype=str,
            engine="python", names=range(_MAX_COLS),
        )
    elif file_type.lower() == "excel":
        raw = pd.read_excel(_reader(), header=None, dtype=str)
    else:
        raise ValueError("Unsupported file_type. Use 'excel' or 'csv'.")

    header_idx = None
    for i in range(min(15, len(raw))):
        row_vals = [str(v).strip() for v in raw.iloc[i].tolist()]
        if any(v == "GP No" for v in row_vals):
            header_idx = i
            break
    if header_idx is None:
        raise ValueError("Could not locate the 'GP No' header row in the file.")

    # ── 2. Re-read using the detected header row (fresh stream) ────────────
    # Same tolerance needed here: the short title/date rows are still above the
    # header, and rows below can have trailing empty fields.
    if file_type.lower() == "csv":
        df = pd.read_csv(_reader(), header=header_idx, engine="python")
    else:
        df = pd.read_excel(_reader(), header=header_idx)

    # ── 3. Drop leading unnamed columns ONLY if present ───────────────────
    lead_drop = 0
    for col in df.columns:
        name = str(col).strip()
        if name == "" or name.lower().startswith("unnamed"):
            lead_drop += 1
        else:
            break
    if lead_drop:
        df = df.iloc[:, lead_drop:]

    # ── 4. Rename to snake_case ────────────────────────────────────────────
    rename_map = {
        'GP No':        'gp_no',
        ' DATE':        'date',
        'AWB No.':      'awb_no',
        'HAWB No ':     'hawb_no',
        'PCS':          'pcs',
        'Truck No':     'truck_no',
        'Driver Name':  'driver_name',
        'Mobile No':    'mobile_no',
        'Time In':      'time_in',
        'Time Out':     'time_out',
        'Agent':        'agent',
        'USER ID':      'sis_user_id',
    }
    df = df[list(rename_map.keys())].rename(columns=rename_map)

    # ── 5. Drop rows where GP No is missing (footer / blank rows) ─────────
    df = df[df['gp_no'].notna()].copy()

    # ── 6. AWB → (awb_no, awb_part) ───────────────────────────────────────
    parsed = df['awb_no'].apply(parse_awb_field)
    df['awb_no']   = parsed.apply(lambda t: t[0])
    df['awb_part'] = parsed.apply(lambda t: t[1])

    # ── 7. Datetime columns → UTC ──────────────────────────────────────────
    for col in ('date', 'time_in', 'time_out'):
        df[col] = df[col].apply(ist_datetime_to_utc)

    missing_date = df[df['date'].isna()]
    if not missing_date.empty:
        raise ValueError(
            f"{len(missing_date)} rows have missing or unparseable DATE. "
            f"GP Nos: {missing_date['gp_no'].tolist()[:10]}"
        )

    # ── 8. Mobile No → clean string ────────────────────────────────────────
    def clean_mobile(val):
        if val is None or (isinstance(val, float) and np.isnan(val)):
            return None
        digits = re.sub(r'\D', '', str(val).split('.')[0])
        return digits if digits else None
    df['mobile_no'] = df['mobile_no'].apply(clean_mobile)

    # ── 9. PCS → int (nullable) ────────────────────────────────────────────
    df['pcs'] = pd.to_numeric(df['pcs'], errors='coerce')
    df['pcs'] = df['pcs'].apply(lambda x: int(x) if pd.notna(x) else None)

    # ── 10. GP No → clean STRING (keeps 'MAN...' values) ──────────────────
    df['gp_no'] = df['gp_no'].apply(_clean_gp_no)

    # ── 11. Clean all string columns ───────────────────────────────────────
    str_cols = ['awb_no', 'awb_part', 'hawb_no', 'truck_no', 'driver_name', 'agent', 'sis_user_id']
    for col in str_cols:
        df[col] = df[col].apply(clean_str)

    # ── 12. Reorder columns ────────────────────────────────────────────────
    df = df[[
        'gp_no', 'date', 'awb_no', 'awb_part', 'hawb_no',
        'pcs', 'truck_no', 'driver_name', 'mobile_no',
        'time_in', 'time_out', 'agent', 'sis_user_id',
    ]]

    # ── 13. Replace remaining pandas NA / NaN with None ───────────────────
    df = df.replace({np.nan: None, pd.NaT: None})

    return df