
# """

# Pure cleaning module for the Cargo Uplifting Report.
# Mirrors the seg_cleaner.py conventions (pandas, IST->UTC, CleanResult).

# Handles:
#   * .xlsx / .xls  -> dates are real Excel date objects, written with day/month
#                      TRANSPOSED by the export. dayfirst=True reverses it.
#   * .csv          -> dates are TEXT (already correct day-first). Parsed with
#                      explicit day-first formats, no swap.
#   * NIL CARRIER block -> flights that departed with no cargo. Stored in the SAME
#                      table with carrier="NIL", awb_no=None, only flight fields
#                      filled (flt_no, flt_date, origin, dest, ETD, departure).
#   * Date validation -> caller passes from_date/to_date/report_date (frontend).
#                      validate_dates() rejects the whole upload if any row's
#                      flt_date falls outside [from_date, to_date] or report_date
#                      is outside that range.
#   * report_date + uploaded_by are stamped on every row by the caller/service.

# All *_date_time columns are IST->UTC.
# """

# import io
# import re
# import csv
# import math
# from dataclasses import dataclass, field
# from datetime import date, datetime, time, timezone
# from zoneinfo import ZoneInfo

# import pandas as pd

# IST = ZoneInfo("Asia/Kolkata")
# UTC = timezone.utc

# DEFAULT_DAYFIRST = True   # for Excel; CSV loader overrides to False

# # ── main AWB block layout (0-based raw index -> field) ───────────────────────
# COL_MAP: dict[int, str] = {
#     1: "sl_no", 2: "flt_no", 4: "awb_no", 5: "awb_sfx", 6: "origin",
#     7: "dest", 8: "pcs", 9: "grs_wgt", 10: "chg_wgt", 11: "volume_mc",
#     24: "uld_no", 27: "nog", 28: "shc", 29: "chg_shc", 30: "billing_shc",
#     31: "agent", 32: "shipper_name", 33: "trm_number", 35: "pax_freighter",
# }
# DATETIME_PAIRS: dict[str, tuple[int, int]] = {
#     "car_date_time":         (12, 13),
#     "doc_date_time":         (14, 15),
#     "xray_date_time":        (16, 17),
#     "rcs_date_time":         (18, 19),
#     "flight_etd_date_time":  (20, 21),
#     "flight_dep_date_time":  (22, 23),
#     "uld_release_date_time": (25, 26),
# }
# DATE_ONLY_NO_SWAP: dict[str, int] = {"flt_date": 3, "trm_date": 34}

# # ── NIL CARRIER block layout (narrower schema) ───────────────────────────────
# NIL_COL_MAP: dict[int, str] = {1: "sl_no", 2: "flt_no", 4: "origin", 5: "dest"}
# NIL_DATE_ONLY: dict[str, int] = {"flt_date": 3}
# NIL_DATETIME_PAIRS: dict[str, tuple[int, int]] = {
#     "flight_etd_date_time": (6, 7),
#     "flight_dep_date_time": (8, 9),
# }

# INT_COLS    = ["sl_no", "pcs"]
# FLOAT_COLS  = ["grs_wgt", "chg_wgt", "volume_mc"]
# STRING_COLS = ["flt_no", "awb_sfx", "origin", "dest", "uld_no", "nog",
#                "shc", "chg_shc", "billing_shc", "agent", "shipper_name",
#                "trm_number", "pax_freighter"]

# _CARRIER_RE    = re.compile(r"^\s*carrier\s*:", re.I)
# _NIL_CARRIER_RE = re.compile(r"^\s*nil\s+carrier\s*:", re.I)
# _HEADER_RE      = re.compile(r"^\s*sl\.?\s*no", re.I)

# _DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d-%b-%y",
#                  "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d")
# _TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%H%M")


# @dataclass
# class CleanResult:
#     awbs_df:       pd.DataFrame
#     dropped_awbs:  list[dict] = field(default_factory=list)
#     total_parsed:  int = 0
#     valid_count:   int = 0
#     dropped_count: int = 0
#     carriers:      list[str] = field(default_factory=list)
#     nil_count:     int = 0
#     source_kind:   str = ""
#     flt_dates:     list[date] = field(default_factory=list)  # for validation


# # ── field helpers ────────────────────────────────────────────────────────────

# def normalize_awb_no(value) -> str | None:
#     if not value:
#         return None
#     cleaned = re.sub(r"\D", "", str(value))
#     if len(cleaned) == 11:
#         return cleaned
#     if len(cleaned) == 10:
#         return "0" + cleaned
#     return None


# def _safe_str(value) -> str | None:
#     if value is None:
#         return None
#     s = str(value).strip()
#     return s if s and s.lower() not in ("nan", "none", "") else None


# def _safe_int(value) -> int | None:
#     if value is None or (isinstance(value, float) and math.isnan(value)):
#         return None
#     try:
#         return int(float(str(value)))
#     except (ValueError, TypeError):
#         return None


# def _safe_float(value) -> float | None:
#     if value is None or (isinstance(value, float) and math.isnan(value)):
#         return None
#     try:
#         return float(value)
#     except (ValueError, TypeError):
#         return None


# def _to_date(value) -> date | None:
#     if value is None or (isinstance(value, float) and math.isnan(value)):
#         return None
#     if isinstance(value, datetime):
#         return value.date()
#     if isinstance(value, pd.Timestamp):
#         return value.date()
#     if isinstance(value, date):
#         return value
#     s = str(value).strip()
#     if not s or s.lower() in ("nan", "none", "nat"):
#         return None
#     for fmt in _DATE_FORMATS:
#         try:
#             return datetime.strptime(s, fmt).date()
#         except ValueError:
#             continue
#     return None


# def _maybe_swap(d: date | None, dayfirst: bool) -> date | None:
#     if d is None or not dayfirst:
#         return d
#     if d.day <= 12:
#         try:
#             return date(d.year, d.day, d.month)
#         except ValueError:
#             return d
#     return d


# def _to_time(value) -> time:
#     if isinstance(value, time):
#         return value
#     if isinstance(value, datetime):
#         return value.time()
#     if isinstance(value, pd.Timestamp):
#         return value.time()
#     if value is None:
#         return time(0, 0)
#     s = str(value).strip()
#     if not s or s.lower() in ("nan", "none"):
#         return time(0, 0)
#     if s.isdigit() and len(s) in (3, 4):
#         s = s.zfill(4)
#         try:
#             return time(int(s[:2]), int(s[2:]))
#         except ValueError:
#             return time(0, 0)
#     for fmt in _TIME_FORMATS:
#         try:
#             return datetime.strptime(s, fmt).time()
#         except ValueError:
#             continue
#     return time(0, 0)


# def _combine_utc(date_val, time_val, dayfirst: bool) -> datetime | None:
#     d = _maybe_swap(_to_date(date_val), dayfirst)
#     if d is None:
#         return None
#     return datetime.combine(d, _to_time(time_val), tzinfo=IST).astimezone(UTC)

# def _combine_utc_parts(date_val, time_val, dayfirst: bool) -> tuple[date | None, time | None]:
#     """Same IST->UTC conversion as _combine_utc, but returned as separate
#     (date, time) parts instead of a single merged datetime value. This is
#     what keeps the *_date and *_time columns separate in the output."""
#     dt_utc = _combine_utc(date_val, time_val, dayfirst)
#     if dt_utc is None:
#         return (None, None)
#     return (dt_utc.date(), dt_utc.time())
# # ── core ─────────────────────────────────────────────────────────────────────

# def clean_uplift_dataframe(raw_df: pd.DataFrame, dayfirst: bool = DEFAULT_DAYFIRST,
#                            source_kind: str = "") -> CleanResult:
#     rows, dropped, carriers = [], [], []
#     carrier = None
#     in_nil = False
#     total = 0
#     nil_count = 0
#     flt_dates: list[date] = []

#     for _, raw in raw_df.iterrows():
#         c0 = _safe_str(raw.iloc[0]) if len(raw) else None
#         c1 = _safe_str(raw.iloc[1]) if len(raw) > 1 else None

#         if (c0 and _NIL_CARRIER_RE.match(c0)) or (c1 and _NIL_CARRIER_RE.match(c1)):
#             carrier = "NIL"
#             in_nil = True
#             if "NIL" not in carriers:
#                 carriers.append("NIL")
#             continue

#         if c0 and _CARRIER_RE.match(c0):
#             carrier = _safe_str(raw.iloc[1])
#             in_nil = False
#             if carrier and carrier not in carriers:
#                 carriers.append(carrier)
#             continue

#         if c1 and _HEADER_RE.match(c1):
#             continue

#         sl_int = _safe_int(raw.iloc[1] if len(raw) > 1 else None)
#         if sl_int is None:
#             continue

#         if in_nil:
#             fdate = _to_date(raw.iloc[3]) if len(raw) > 3 else None
#             rec = {"carrier": "NIL", "awb_no": None, "sl_no": sl_int}
#             for idx, name in NIL_COL_MAP.items():
#                 if name == "sl_no":
#                     continue
#                 rec[name] = _safe_str(raw.iloc[idx]) if len(raw) > idx else None
#             for name, idx in NIL_DATE_ONLY.items():
#                 rec[name] = fdate
#             for name, (di, ti) in NIL_DATETIME_PAIRS.items():
#                 dv = raw.iloc[di] if len(raw) > di else None
#                 tv = raw.iloc[ti] if len(raw) > ti else None
#                 d_part, t_part = _combine_utc_parts(dv, tv, dayfirst=False)
#                 base = name[:-len("_date_time")] if name.endswith("_date_time") else name
#                 rec[f"{base}_date"] = d_part
#                 rec[f"{base}_time"] = t_part
            
#             # ── NEW LOGIC: Calculated Columns for NIL Rows ──
#             if fdate:
#                 flt_dates.append(fdate)
#             #     rec["month_year"] = fdate.strftime("%b-%Y") # Alternative: fdate.strftime("%m-%Y")
#             #     rec["year"] = fdate.year
#             # else:
#             #     rec["month_year"] = None
#             #     rec["year"] = None
            
#             # rec["grs_wgt_mt"] = None # NIL flights don't have individual weights

#             rows.append(rec)
#             nil_count += 1
#             total += 1
#             continue

#         # normal AWB row
#         total += 1
#         awb = normalize_awb_no(raw.iloc[4] if len(raw) > 4 else None)
#         if awb is None:
#             dropped.append({"reason": "invalid_awb", "carrier": carrier,
#                             "sl_no": sl_int,
#                             "awb_raw": raw.iloc[4] if len(raw) > 4 else None})
#             continue

#         rec = {"carrier": carrier, "awb_no": awb}
#         for idx, name in COL_MAP.items():
#             if name == "awb_no":
#                 continue
#             val = raw.iloc[idx] if len(raw) > idx else None
#             if name in INT_COLS:
#                 rec[name] = _safe_int(val)
#             elif name in FLOAT_COLS:
#                 rec[name] = _safe_float(val)
#             elif name in STRING_COLS:
#                 rec[name] = _safe_str(val)
#             else:
#                 rec[name] = val
#         for name, idx in DATE_ONLY_NO_SWAP.items():
#             rec[name] = _to_date(raw.iloc[idx]) if len(raw) > idx else None
#         for name, (di, ti) in DATETIME_PAIRS.items():
#             dv = raw.iloc[di] if len(raw) > di else None
#             tv = raw.iloc[ti] if len(raw) > ti else None
#             d_part, t_part = _combine_utc_parts(dv, tv, dayfirst)
#             base = name[:-len("_date_time")] if name.endswith("_date_time") else name
#             rec[f"{base}_date"] = d_part
#             rec[f"{base}_time"] = t_part

#         # ── NEW LOGIC: Calculated Columns for Normal AWB Rows ──
#         fdate = rec.get("flt_date")
#         if fdate:
#             flt_dates.append(fdate)
#         #     rec["month_year"] = fdate.strftime("%b-%Y") # Outputs: "Jul-2026"
#         #     rec["year"] = fdate.year
#         # else:
#         #     rec["month_year"] = None
#         #     rec["year"] = None

#         # # Safe division for Metric Tons calculation
#         # if rec.get("grs_wgt") is not None:
#         #     rec["grs_wgt_mt"] = rec["grs_wgt"] / 1000.0
#         # else:
#         #     rec["grs_wgt_mt"] = None

#         rows.append(rec)

#     # Fallback to empty DataFrame structure if no rows are processed
#     # df_result = pd.DataFrame(rows) if rows else pd.DataFrame(columns=list(COL_MAP.values()) + ["month_year", "year", "grs_wgt_mt"])
#     df_result = pd.DataFrame(rows) if rows else pd.DataFrame(columns=list(COL_MAP.values()))

#     return CleanResult(
#         awbs_df=df_result,
#         dropped_awbs=dropped,
#         total_parsed=total,
#         valid_count=len(rows),
#         dropped_count=len(dropped),
#         carriers=carriers,
#         nil_count=nil_count,
#         source_kind=source_kind,
#         flt_dates=flt_dates,
#     )


# # ── date validation ──────────────────────────────────────────────────────────

# def _fmt(d: date) -> str:
#     """10 Jul 2026 style."""
#     return d.strftime("%d %b %Y").lstrip("0")


# class DateValidationError(ValueError):
#     """Raised when file dates fall outside the frontend-supplied range."""


# def validate_dates(result: CleanResult, report_date: date) -> None:
#     out = sorted({d for d in result.flt_dates if d != report_date})
#     if out:
#         shown = ", ".join(_fmt(d) for d in out[:5])
#         more = f" and {len(out) - 5} more" if len(out) > 5 else ""
#         raise DateValidationError(
#             f"File contains flight dates that do not match the report date "
#             f"{_fmt(report_date)}: {shown}{more}. "
#             f"Please upload the correct report."
#         )


# # ── loaders ──────────────────────────────────────────────────────────────────

# def _read_csv_bytes(data: bytes) -> pd.DataFrame:
#     text = data.decode("utf-8-sig", errors="replace")
#     rows = list(csv.reader(io.StringIO(text)))
#     if not rows:
#         return pd.DataFrame()
#     maxc = max(len(r) for r in rows)
#     rows = [r + [None] * (maxc - len(r)) for r in rows]
#     return pd.DataFrame(rows)


# def clean_uplift_bytes(data: bytes, filename: str) -> CleanResult:
#     ext = (filename or "").lower().rsplit(".", 1)[-1]
#     if ext == "csv":
#         return clean_uplift_dataframe(_read_csv_bytes(data),
#                                       dayfirst=False, source_kind="csv")
#     raw_df = pd.read_excel(io.BytesIO(data), header=None, dtype=object)
#     return clean_uplift_dataframe(raw_df, dayfirst=True, source_kind="excel")


# def clean_uplift_file(path: str) -> CleanResult:
#     with open(path, "rb") as f:
#         return clean_uplift_bytes(f.read(), path)


# if __name__ == "__main__":
#     import sys
#     p = sys.argv[1] if len(sys.argv) > 1 else "16JUL261216.xlsx"
#     res = clean_uplift_file(p)
#     print(f"[{res.source_kind}] parsed={res.total_parsed} valid={res.valid_count} "
#           f"dropped={res.dropped_count} nil={res.nil_count} "
#           f"carriers={len(res.carriers)}")
    
#     # Showcase the new fields on a standard row
#     normal_rows = res.awbs_df[res.awbs_df['carrier'] != 'NIL']
#     if len(normal_rows):
#         print("\nNormal sample row:")
#         print(normal_rows.iloc[0][
#             ['carrier', 'awb_no', 'flt_date', 'grs_wgt',
#              'car_date', 'car_time', 'flight_etd_date', 'flight_etd_time']
#         ].to_dict())









































"""

Pure cleaning module for the Cargo Uplifting Report.
Mirrors the seg_cleaner.py conventions (pandas, IST->UTC, CleanResult).

Handles:
  * .xlsx / .xls  -> dates are real Excel date objects, written with day/month
                     TRANSPOSED by the export. dayfirst=True reverses it.
  * .csv          -> dates are TEXT (already correct day-first). Parsed with
                     explicit day-first formats, no swap.
  * NIL CARRIER block -> flights that departed with no cargo. Stored in the SAME
                     table with carrier="NIL", awb_no=None, only flight fields
                     filled (flt_no, flt_date, origin, dest, ETD, departure).
  * Date validation -> caller passes from_date/to_date/report_date (frontend).
                     validate_dates() rejects the whole upload if any row's
                     flt_date falls outside [from_date, to_date] or report_date
                     is outside that range.
  * report_date + uploaded_by are stamped on every row by the caller/service.

All *_date_time columns are IST->UTC.
"""

import io
import re
import csv
import math
from dataclasses import dataclass, field
from datetime import date, datetime, time, timezone
from zoneinfo import ZoneInfo

import pandas as pd

IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

DEFAULT_DAYFIRST = True   # for Excel; CSV loader overrides to False

# ── main AWB block layout (0-based raw index -> field) ───────────────────────
COL_MAP: dict[int, str] = {
    1: "sl_no", 2: "flt_no", 4: "awb_no", 5: "awb_sfx", 6: "origin",
    7: "dest", 8: "pcs", 9: "grs_wgt", 10: "chg_wgt", 11: "volume_mc",
    24: "uld_no", 27: "nog", 28: "shc", 29: "chg_shc", 30: "billing_shc",
    31: "agent", 32: "shipper_name", 33: "trm_number", 35: "pax_freighter",
}
DATETIME_PAIRS: dict[str, tuple[int, int]] = {
    "car_date_time":         (12, 13),
    "doc_date_time":         (14, 15),
    "xray_date_time":        (16, 17),
    "rcs_date_time":         (18, 19),
    "flight_etd_date_time":  (20, 21),
    "flight_dep_date_time":  (22, 23),
    "uld_release_date_time": (25, 26),
}
DATE_ONLY_NO_SWAP: dict[str, int] = {"flt_date": 3, "trm_date": 34}

# ── NIL CARRIER block layout (narrower schema) ───────────────────────────────
NIL_COL_MAP: dict[int, str] = {1: "sl_no", 2: "flt_no", 4: "origin", 5: "dest"}
NIL_DATE_ONLY: dict[str, int] = {"flt_date": 3}
NIL_DATETIME_PAIRS: dict[str, tuple[int, int]] = {
    "flight_etd_date_time": (6, 7),
    "flight_dep_date_time": (8, 9),
}

INT_COLS    = ["sl_no", "pcs"]
FLOAT_COLS  = ["grs_wgt", "chg_wgt", "volume_mc"]
STRING_COLS = ["flt_no", "awb_sfx", "origin", "dest", "uld_no", "nog",
               "shc", "chg_shc", "billing_shc", "agent", "shipper_name",
               "trm_number", "pax_freighter"]

_CARRIER_RE    = re.compile(r"^\s*carrier\s*:", re.I)
_NIL_CARRIER_RE = re.compile(r"^\s*nil\s+carrier\s*:", re.I)
_HEADER_RE      = re.compile(r"^\s*sl\.?\s*no", re.I)

_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d-%b-%y",
                 "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d")
_TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%H%M")


@dataclass
class CleanResult:
    awbs_df:       pd.DataFrame
    dropped_awbs:  list[dict] = field(default_factory=list)
    total_parsed:  int = 0
    valid_count:   int = 0
    dropped_count: int = 0
    carriers:      list[str] = field(default_factory=list)
    nil_count:     int = 0
    source_kind:   str = ""
    flt_dates:     list[date] = field(default_factory=list)  # for validation


# ── field helpers ────────────────────────────────────────────────────────────

def normalize_awb_no(value) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\D", "", str(value))
    if len(cleaned) == 11:
        return cleaned
    if len(cleaned) == 10:
        return "0" + cleaned
    return None


def _safe_str(value) -> str | None:
    if value is None:
        return None
    s = str(value).strip()
    return s if s and s.lower() not in ("nan", "none", "") else None


def _safe_int(value) -> int | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return int(float(str(value)))
    except (ValueError, TypeError):
        return None


def _safe_float(value) -> float | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    try:
        return float(value)
    except (ValueError, TypeError):
        return None


def _to_date(value) -> date | None:
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, pd.Timestamp):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none", "nat"):
        return None
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _maybe_swap(d: date | None, dayfirst: bool) -> date | None:
    if d is None or not dayfirst:
        return d
    if d.day <= 12:
        try:
            return date(d.year, d.day, d.month)
        except ValueError:
            return d
    return d


def _to_time(value) -> time:
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, pd.Timestamp):
        return value.time()
    if value is None:
        return time(0, 0)
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none"):
        return time(0, 0)
    if s.isdigit() and len(s) in (3, 4):
        s = s.zfill(4)
        try:
            return time(int(s[:2]), int(s[2:]))
        except ValueError:
            return time(0, 0)
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return time(0, 0)


def _combine_utc(date_val, time_val, dayfirst: bool) -> datetime | None:
    d = _maybe_swap(_to_date(date_val), dayfirst)
    if d is None:
        return None
    return datetime.combine(d, _to_time(time_val), tzinfo=IST).astimezone(UTC)

def _combine_ist_parts(date_val, time_val, dayfirst: bool) -> tuple[date | None, time | None]:
    """Raw IST date & time, NO UTC conversion."""
    d = _maybe_swap(_to_date(date_val), dayfirst)
    if d is None:
        return (None, None)
    return (d, _to_time(time_val))
# ── core ─────────────────────────────────────────────────────────────────────

def clean_uplift_dataframe(raw_df: pd.DataFrame, dayfirst: bool = DEFAULT_DAYFIRST,
                           source_kind: str = "") -> CleanResult:
    rows, dropped, carriers = [], [], []
    carrier = None
    in_nil = False
    total = 0
    nil_count = 0
    flt_dates: list[date] = []

    for _, raw in raw_df.iterrows():
        c0 = _safe_str(raw.iloc[0]) if len(raw) else None
        c1 = _safe_str(raw.iloc[1]) if len(raw) > 1 else None

        if (c0 and _NIL_CARRIER_RE.match(c0)) or (c1 and _NIL_CARRIER_RE.match(c1)):
            carrier = "NIL"
            in_nil = True
            if "NIL" not in carriers:
                carriers.append("NIL")
            continue

        if c0 and _CARRIER_RE.match(c0):
            carrier = _safe_str(raw.iloc[1])
            in_nil = False
            if carrier and carrier not in carriers:
                carriers.append(carrier)
            continue

        if c1 and _HEADER_RE.match(c1):
            continue

        sl_int = _safe_int(raw.iloc[1] if len(raw) > 1 else None)
        if sl_int is None:
            continue

        if in_nil:
            fdate = _to_date(raw.iloc[3]) if len(raw) > 3 else None
            rec = {"carrier": "NIL", "awb_no": None, "sl_no": sl_int}
            for idx, name in NIL_COL_MAP.items():
                if name == "sl_no":
                    continue
                rec[name] = _safe_str(raw.iloc[idx]) if len(raw) > idx else None
            for name, idx in NIL_DATE_ONLY.items():
                rec[name] = fdate
            for name, (di, ti) in NIL_DATETIME_PAIRS.items():
                dv = raw.iloc[di] if len(raw) > di else None
                tv = raw.iloc[ti] if len(raw) > ti else None
                base = name[:-len("_date_time")] if name.endswith("_date_time") else name

                d_part, t_part = _combine_ist_parts(dv, tv, dayfirst=False)   # raw IST
                rec[f"{base}_date"] = d_part
                rec[f"{base}_time"] = t_part
                rec[f"{base}_date_time_combine"] = _combine_utc(dv, tv, dayfirst=False)  # UTC
            
            # ── NEW LOGIC: Calculated Columns for NIL Rows ──
            if fdate:
                flt_dates.append(fdate)
            #     rec["month_year"] = fdate.strftime("%b-%Y") # Alternative: fdate.strftime("%m-%Y")
            #     rec["year"] = fdate.year
            # else:
            #     rec["month_year"] = None
            #     rec["year"] = None
            
            # rec["grs_wgt_mt"] = None # NIL flights don't have individual weights

            rows.append(rec)
            nil_count += 1
            total += 1
            continue

        # normal AWB row
        total += 1
        awb = normalize_awb_no(raw.iloc[4] if len(raw) > 4 else None)
        if awb is None:
            dropped.append({"reason": "invalid_awb", "carrier": carrier,
                            "sl_no": sl_int,
                            "awb_raw": raw.iloc[4] if len(raw) > 4 else None})
            continue

        rec = {"carrier": carrier, "awb_no": awb}
        for idx, name in COL_MAP.items():
            if name == "awb_no":
                continue
            val = raw.iloc[idx] if len(raw) > idx else None
            if name in INT_COLS:
                rec[name] = _safe_int(val)
            elif name in FLOAT_COLS:
                rec[name] = _safe_float(val)
            elif name in STRING_COLS:
                rec[name] = _safe_str(val)
            else:
                rec[name] = val
        for name, idx in DATE_ONLY_NO_SWAP.items():
            rec[name] = _to_date(raw.iloc[idx]) if len(raw) > idx else None
        for name, (di, ti) in DATETIME_PAIRS.items():
            dv = raw.iloc[di] if len(raw) > di else None
            tv = raw.iloc[ti] if len(raw) > ti else None
            base = name[:-len("_date_time")] if name.endswith("_date_time") else name

            d_part, t_part = _combine_ist_parts(dv, tv, dayfirst)   # raw IST
            rec[f"{base}_date"] = d_part
            rec[f"{base}_time"] = t_part
            rec[f"{base}_date_time_combine"] = _combine_utc(dv, tv, dayfirst)  # UTC

        # ── NEW LOGIC: Calculated Columns for Normal AWB Rows ──
        fdate = rec.get("flt_date")
        if fdate:
            flt_dates.append(fdate)
        #     rec["month_year"] = fdate.strftime("%b-%Y") # Outputs: "Jul-2026"
        #     rec["year"] = fdate.year
        # else:
        #     rec["month_year"] = None
        #     rec["year"] = None

        # # Safe division for Metric Tons calculation
        # if rec.get("grs_wgt") is not None:
        #     rec["grs_wgt_mt"] = rec["grs_wgt"] / 1000.0
        # else:
        #     rec["grs_wgt_mt"] = None

        rows.append(rec)

    # Fallback to empty DataFrame structure if no rows are processed
    # df_result = pd.DataFrame(rows) if rows else pd.DataFrame(columns=list(COL_MAP.values()) + ["month_year", "year", "grs_wgt_mt"])
    df_result = pd.DataFrame(rows) if rows else pd.DataFrame(columns=list(COL_MAP.values()))

    return CleanResult(
        awbs_df=df_result,
        dropped_awbs=dropped,
        total_parsed=total,
        valid_count=len(rows),
        dropped_count=len(dropped),
        carriers=carriers,
        nil_count=nil_count,
        source_kind=source_kind,
        flt_dates=flt_dates,
    )


# ── date validation ──────────────────────────────────────────────────────────

def _fmt(d: date) -> str:
    """10 Jul 2026 style."""
    return d.strftime("%d %b %Y").lstrip("0")


class DateValidationError(ValueError):
    """Raised when file dates fall outside the frontend-supplied range."""


def validate_dates(result: CleanResult, report_date: date) -> None:
    out = sorted({d for d in result.flt_dates if d != report_date})
    if out:
        shown = ", ".join(_fmt(d) for d in out[:5])
        more = f" and {len(out) - 5} more" if len(out) > 5 else ""
        raise DateValidationError(
            f"File contains flight dates that do not match the report date "
            f"{_fmt(report_date)}: {shown}{more}. "
            f"Please upload the correct report."
        )


# ── loaders ──────────────────────────────────────────────────────────────────

def _read_csv_bytes(data: bytes) -> pd.DataFrame:
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return pd.DataFrame()
    maxc = max(len(r) for r in rows)
    rows = [r + [None] * (maxc - len(r)) for r in rows]
    return pd.DataFrame(rows)


def clean_uplift_bytes(data: bytes, filename: str) -> CleanResult:
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if ext == "csv":
        return clean_uplift_dataframe(_read_csv_bytes(data),
                                      dayfirst=False, source_kind="csv")
    raw_df = pd.read_excel(io.BytesIO(data), header=None, dtype=object)
    return clean_uplift_dataframe(raw_df, dayfirst=True, source_kind="excel")


def clean_uplift_file(path: str) -> CleanResult:
    with open(path, "rb") as f:
        return clean_uplift_bytes(f.read(), path)


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "16JUL261216.xlsx"
    res = clean_uplift_file(p)
    print(f"[{res.source_kind}] parsed={res.total_parsed} valid={res.valid_count} "
          f"dropped={res.dropped_count} nil={res.nil_count} "
          f"carriers={len(res.carriers)}")
    
    # Showcase the new fields on a standard row
    normal_rows = res.awbs_df[res.awbs_df['carrier'] != 'NIL']
    if len(normal_rows):
        print("\nNormal sample row:")
        print(normal_rows.iloc[0][
            ['carrier', 'awb_no', 'flt_date', 'grs_wgt',
             'car_date', 'car_time', 'flight_etd_date', 'flight_etd_time']
        ].to_dict())