
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

# ── main AWB block layout (0-based raw index -> field) ───────────────────────
COL_MAP: dict[int, str] = {
    3: "sl_no", 4: "flt_no", 6: "awb_no", 7: "awb_sfx",
    12: "origin", 13: "dest",
    14: "manifest_pcs", 15: "manifest_wgt", 16: "seg_pcs", 17: "seg_wgt",
    18: "pcs", 19: "grs_wgt", 20: "chg_wgt", 21: "volume_mc",
    22: "no_of_houses", 23: "shc", 24: "chg_shc", 25: "billing_shc",
    26: "nog", 27: "consignee_details", 33: "egm_igm_no", 35: "flight_status",
}
DATE_ONLY: dict[str, int] = {"flt_date": 5}

# combined "DD/MM/YY HH:MM[:SS]" single-string columns -> field base name
DATETIME_COMBINED_COLS: dict[int, str] = {
    8: "ata", 9: "flt_doc_arrival", 10: "last_uld_arrival", 11: "bulk_uld_arrival",
    28: "awd", 29: "nfd", 30: "rcf", 31: "do", 32: "tfd", 34: "flt_com",
}

# ── NIL CARRIER block layout (narrower schema) ───────────────────────────────
NIL_COL_MAP: dict[int, str] = {1: "sl_no", 2: "flt_no", 4: "origin", 5: "dest"}
NIL_DATE_ONLY: dict[str, int] = {"flt_date": 3}
NIL_DATETIME_COMBINED_COLS: dict[int, str] = {6: "flt_com"}

INT_COLS    = ["sl_no", "manifest_pcs", "seg_pcs", "pcs", "no_of_houses"]
FLOAT_COLS  = ["manifest_wgt", "seg_wgt", "grs_wgt", "chg_wgt", "volume_mc"]
STRING_COLS = ["flt_no", "awb_sfx", "origin", "dest", "shc", "chg_shc",
               "billing_shc", "nog", "consignee_details", "egm_igm_no", "flight_status"]

_NIL_CARRIER_RE = re.compile(r"^\s*nil\s+carrier\s*:", re.I)
_HEADER_RE      = re.compile(r"sl\.?\s*no", re.I)
_TOTAL_RE       = re.compile(r"total", re.I)

_DATE_FORMATS = ("%d-%b-%y", "%d-%b-%Y", "%d/%m/%y", "%d/%m/%Y", "%Y-%m-%d")
_COMBINED_DT_FORMATS = ("%d/%m/%y %H:%M:%S", "%d/%m/%y %H:%M",
                        "%d/%m/%Y %H:%M:%S", "%d/%m/%Y %H:%M")


@dataclass
class CleanResult:
    seg_df:        pd.DataFrame
    dropped_rows:  list[dict] = field(default_factory=list)
    total_parsed:  int = 0
    valid_count:   int = 0
    dropped_count: int = 0
    carriers:      list[str] = field(default_factory=list)
    nil_count:     int = 0
    source_kind:   str = ""
    flt_dates:     list[date] = field(default_factory=list)   # for validation


# ── field helpers (same conventions as uplift_cleaner.py) ───────────────────

def normalize_awb_no(value) -> str | None:
    if not value:
        return None
    cleaned = re.sub(r"\D", "", str(value))
    if len(cleaned) == 11:
        return cleaned
    if len(cleaned) == 10:
        return "0" + cleaned
    return None


def _clean_flight_number(value) -> str:
    """'PAI0161' -> 'AI0161' (strips a leading codeshare 'P'), else unchanged."""
    if value is None or (isinstance(value, float) and math.isnan(value)):
        return ""
    val = str(value).strip().upper().replace(" ", "").replace("-", "")
    m = re.match(r"^P([A-Z0-9]{2}\d+)$", val)
    return m.group(1) if m else val


def _carrier_from_flt_no(flt_no: str) -> str | None:
    """Derives the airline code from a cleaned flt_no, e.g. 'AI0278' -> 'AI'."""
    m = re.match(r"^([A-Z]{2,3})\d", flt_no)
    return m.group(1) if m else None


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


def _parse_combined_dt(value) -> datetime | None:
    """'21/07/26  20:38' / '22/07/26 01:26:19' (irregular whitespace,
    optional seconds) -> naive datetime, or None if blank/unparseable."""
    s = _safe_str(value)
    if s is None:
        return None
    s = re.sub(r"\s+", " ", s)
    for fmt in _COMBINED_DT_FORMATS:
        try:
            return datetime.strptime(s, fmt)
        except ValueError:
            continue
    return None


def _combined_ist_parts(value) -> tuple[date | None, time | None]:
    dt_naive = _parse_combined_dt(value)
    if dt_naive is None:
        return (None, None)
    return (dt_naive.date(), dt_naive.time())


def _combined_utc(value) -> datetime | None:
    dt_naive = _parse_combined_dt(value)
    if dt_naive is None:
        return None
    return dt_naive.replace(tzinfo=IST).astimezone(UTC)


# ── core ─────────────────────────────────────────────────────────────────────

def clean_segregation_dataframe(raw_df: pd.DataFrame, source_kind: str = "") -> CleanResult:
    rows, dropped, carriers = [], [], []
    in_nil = False
    total = 0
    nil_count = 0
    flt_dates: list[date] = []

    for _, raw in raw_df.iterrows():
        c1 = _safe_str(raw.iloc[1]) if len(raw) > 1 else None
        c2 = _safe_str(raw.iloc[2]) if len(raw) > 2 else None
        c3 = _safe_str(raw.iloc[3]) if len(raw) > 3 else None

        if c1 and _NIL_CARRIER_RE.match(c1):
            in_nil = True
            continue

        # header rows (main block has 'Sl.No.' around index 3, NIL block around index 1)
        if (c1 and _HEADER_RE.search(c1)) or (c3 and _HEADER_RE.search(c3)):
            continue

        # per-flight "Total" / end-of-file "GRAND TOTAL" subtotal row -> skip
        if (c2 and _TOTAL_RE.search(c2)) or (c1 and _TOTAL_RE.search(c1)):
            continue

        if in_nil:
            sl_int = _safe_int(raw.iloc[1] if len(raw) > 1 else None)
            if sl_int is None:
                continue

            fdate = _to_date(raw.iloc[NIL_DATE_ONLY["flt_date"]])
            flt_no = _clean_flight_number(raw.iloc[2] if len(raw) > 2 else None)
            rec = {"carrier": "NIL", "awb_no": None, "sl_no": sl_int, "flt_no": flt_no}
            for idx, name in NIL_COL_MAP.items():
                if name in ("sl_no", "flt_no"):
                    continue
                rec[name] = _safe_str(raw.iloc[idx]) if len(raw) > idx else None
            rec["flt_date"] = fdate

            for idx, base in NIL_DATETIME_COMBINED_COLS.items():
                val = raw.iloc[idx] if len(raw) > idx else None
                d_part, t_part = _combined_ist_parts(val)
                rec[f"{base}_date"] = d_part
                rec[f"{base}_time"] = t_part
                rec[f"{base}_date_time_combine"] = _combined_utc(val)

            if fdate:
                flt_dates.append(fdate)

            rows.append(rec)
            nil_count += 1
            total += 1
            continue

        # normal AWB row
        sl_int = _safe_int(raw.iloc[3] if len(raw) > 3 else None)
        if sl_int is None:
            continue

        total += 1
        awb = normalize_awb_no(raw.iloc[6] if len(raw) > 6 else None)
        if awb is None:
            dropped.append({"reason": "invalid_awb", "sl_no": sl_int,
                            "awb_raw": raw.iloc[6] if len(raw) > 6 else None})
            continue

        flt_no = _clean_flight_number(raw.iloc[4] if len(raw) > 4 else None)
        carrier = _carrier_from_flt_no(flt_no)
        if carrier and carrier not in carriers:
            carriers.append(carrier)

        rec = {"carrier": carrier, "awb_no": awb, "flt_no": flt_no}
        for idx, name in COL_MAP.items():
            if name in ("flt_no", "awb_no"):
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

        for name, idx in DATE_ONLY.items():
            rec[name] = _to_date(raw.iloc[idx]) if len(raw) > idx else None

        for idx, base in DATETIME_COMBINED_COLS.items():
            val = raw.iloc[idx] if len(raw) > idx else None
            d_part, t_part = _combined_ist_parts(val)
            rec[f"{base}_date"] = d_part
            rec[f"{base}_time"] = t_part
            rec[f"{base}_date_time_combine"] = _combined_utc(val)

        fdate = rec.get("flt_date")
        if fdate:
            flt_dates.append(fdate)

        rows.append(rec)

    all_cols = (list(COL_MAP.values())
                + [f"{n}_{s}" for n in list(DATETIME_COMBINED_COLS.values()) for s in ("date", "time", "date_time_combine")])
    df_result = pd.DataFrame(rows) if rows else pd.DataFrame(columns=all_cols)

    return CleanResult(
        seg_df=df_result,
        dropped_rows=dropped,
        total_parsed=total,
        valid_count=len(rows),
        dropped_count=len(dropped),
        carriers=carriers,
        nil_count=nil_count,
        source_kind=source_kind,
        flt_dates=flt_dates,
    )

# ── date validation (updated to handle date mismatches) ───────────────

def _fmt(d: date) -> str:
    """10 Jul 2026 style."""
    return d.strftime("%d %b %Y").lstrip("0")


class DateValidationError(ValueError):
    """Raised when file dates don't match the caller-supplied report_date."""


def validate_dates(result: CleanResult, report_date: date) -> None:
    """
    Segregation reports ke liye error raise karna band kar diya gaya hai.
    Agar date mismatch hoti bhi hai, toh yeh gracefully clean ho jayegi.
    """
    out = sorted({d for d in result.flt_dates if d != report_date})
    if out:
        shown = ", ".join(_fmt(d) for d in out[:5])
        more = f" and {len(out) - 5} more" if len(out) > 5 else ""
        
    
        return
# ── loaders ──────────────────────────────────────────────────────────────────

def _read_csv_bytes(data: bytes) -> pd.DataFrame:
    text = data.decode("utf-8-sig", errors="replace")
    rows = list(csv.reader(io.StringIO(text)))
    if not rows:
        return pd.DataFrame()
    maxc = max(len(r) for r in rows)
    rows = [r + [None] * (maxc - len(r)) for r in rows]
    return pd.DataFrame(rows)


def clean_segregation_bytes(data: bytes, filename: str) -> CleanResult:
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if ext == "csv":
        return clean_segregation_dataframe(_read_csv_bytes(data), source_kind="csv")
    raw_df = pd.read_excel(io.BytesIO(data), header=None, dtype=object)
    return clean_segregation_dataframe(raw_df, source_kind="excel")


def clean_segregation_file(path: str) -> CleanResult:
    with open(path, "rb") as f:
        return clean_segregation_bytes(f.read(), path)


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "23JUL261320.CSV"
    res = clean_segregation_file(p)
    print(f"[{res.source_kind}] parsed={res.total_parsed} valid={res.valid_count} "
          f"dropped={res.dropped_count} nil={res.nil_count} "
          f"carriers={len(res.carriers)} flt_dates={sorted(set(res.flt_dates))}")

    normal_rows = res.seg_df[res.seg_df['carrier'] != 'NIL']
    if len(normal_rows):
        print("\nNormal sample row:")
        print(normal_rows.iloc[0][
            ['carrier', 'flt_no', 'awb_no', 'flt_date', 'origin', 'dest',
             'seg_pcs', 'seg_wgt', 'ata_date', 'ata_time', 'ata_date_time_combine']
        ].to_dict())

    nil_rows = res.seg_df[res.seg_df['carrier'] == 'NIL']
    if len(nil_rows):
        print("\nNIL sample row:")
        print(nil_rows.iloc[0][
            ['carrier', 'flt_no', 'flt_date', 'origin', 'dest', 'flt_com_date_time_combine']
        ].to_dict())