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

DEFAULT_DAYFIRST = True

# ── row layout (0-based raw index -> field), after header row ─────────────
COL_MAP: dict[int, str] = {
    2: "flt_no",
    3: "aircraft_type",
    4: "origin",
    5: "destination",
    6: "time_std",
    7: "time_sta",
    8: "avail_weight_cargo",
    9: "avail_weight_mail",
    10: "frequency",
    11: "flt_type",
    12: "flt_status",
}

INT_COLS   = ["avail_weight_cargo", "avail_weight_mail"]
STRING_COLS = ["flt_no", "aircraft_type", "origin", "destination", "frequency", "flt_type", "flt_status"]
TIME_COLS   = ["time_std", "time_sta"]

_HEADER_RE = re.compile(r"^\s*flight\s*no", re.I)

# ── FIX: Flexible Regex for multi-space & varying separators ──────────────────
_RANGE_RE = re.compile(
    r"FROM\s+DATE\s*:\s*,?\s*([0-9A-Za-z]+)\s*,?\s*TO\s+DATE\s*:\s*,?\s*([0-9A-Za-z]+)", 
    re.I
)

_DATE_FORMATS = ("%d/%m/%Y", "%d-%m-%Y", "%d-%b-%Y", "%d-%b-%y",
                 "%d/%m/%y", "%d-%m-%y", "%Y-%m-%d")
_TIME_FORMATS = ("%H:%M:%S", "%H:%M", "%H%M")
_RANGE_DATE_FORMAT = "%d%b%Y"


@dataclass
class CleanResult:
    flights_df:      pd.DataFrame
    dropped_flights:  list[dict] = field(default_factory=list)
    total_parsed:    int = 0
    valid_count:     int = 0
    dropped_count:   int = 0
    source_kind:     str = ""
    report_from:     date | None = None   # from header row
    report_to:       date | None = None   # from header row


# ── field helpers ────────────────────────────────────────────────────────────

def _clean_flight_no(value) -> str | None:
    if not value:
        return None
    s = str(value).strip().upper()
    if not s or s == "NAN":
        return None
    return s.replace("-", "").replace(" ", "")


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


def _to_time(value) -> time | None:
    if isinstance(value, time):
        return value
    if isinstance(value, datetime):
        return value.time()
    if isinstance(value, pd.Timestamp):
        return value.time()
    if value is None:
        return None
    s = str(value).strip()
    if not s or s.lower() in ("nan", "none"):
        return None
    if s.isdigit() and len(s) in (3, 4):
        s = s.zfill(4)
        try:
            return time(int(s[:2]), int(s[2:]))
        except ValueError:
            return None
    for fmt in _TIME_FORMATS:
        try:
            return datetime.strptime(s, fmt).time()
        except ValueError:
            continue
    return None


# ── core ─────────────────────────────────────────────────────────────────────

def clean_flight_schedule_dataframe(raw_df: pd.DataFrame, dayfirst: bool = DEFAULT_DAYFIRST,
                                   source_kind: str = "") -> CleanResult:
    rows, dropped = [], []
    total = 0

    for _, raw in raw_df.iterrows():
        c2 = _safe_str(raw.iloc[2]) if len(raw) > 2 else None

        # skip header row if included
        if c2 and _HEADER_RE.match(c2):
            continue

        flt_no = _clean_flight_no(c2)
        if flt_no is None:
            # blank / title / summary row
            continue

        total += 1

        rec = {"flt_no": flt_no}
        for idx, name in COL_MAP.items():
            if name == "flt_no":
                continue
            val = raw.iloc[idx] if len(raw) > idx else None
            
            if name in INT_COLS:
                rec[name] = _safe_int(val)
            elif name in TIME_COLS:
                rec[name] = _to_time(val)
            elif name in STRING_COLS:
                rec[name] = _safe_str(val)
            else:
                rec[name] = val

        rows.append(rec)

    all_cols = list(COL_MAP.values())
    df_result = pd.DataFrame(rows) if rows else pd.DataFrame(columns=all_cols)

    return CleanResult(
        flights_df=df_result,
        dropped_flights=dropped,
        total_parsed=total,
        valid_count=len(rows),
        dropped_count=len(dropped),
        source_kind=source_kind,
    )


# ── report date-range extraction & validation ────────────────────────────────

def _fmt(d: date) -> str:
    """10 Jul 2026 style."""
    return d.strftime("%d %b %Y").lstrip("0")


class DateValidationError(ValueError):
    """Raised when file dates fall outside the report's [from_date, to_date] window."""


def extract_report_date_range(text: str) -> tuple[date | None, date | None]:
    """Extracts 'FROM DATE :,21JUL2026,TO DATE  :,22JUL2026' into (from_date, to_date)."""
    m = _RANGE_RE.search(text)
    if not m:
        return (None, None)
    try:
        # FIX: Added .upper() and .strip() for robust date parsing
        from_str = m.group(1).strip().upper()
        to_str = m.group(2).strip().upper()
        
        f = datetime.strptime(from_str, _RANGE_DATE_FORMAT).date()
        t = datetime.strptime(to_str, _RANGE_DATE_FORMAT).date()
        return (f, t)
    except ValueError:
        return (None, None)


# ── loaders ──────────────────────────────────────────────────────────────────

_HEADER_MARKER = "FLIGHT NO."


def _find_header_row(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if _HEADER_MARKER in line.upper():
            return i
    raise ValueError(f"Could not locate header row (looking for '{_HEADER_MARKER}')")


def _read_csv_bytes(data: bytes) -> tuple[pd.DataFrame, tuple[date | None, date | None]]:
    text = data.decode("utf-8-sig", errors="replace")
    date_range = extract_report_date_range(text)

    lines = text.splitlines(keepends=True)
    header_idx = _find_header_row(lines)

    rows = list(csv.reader(io.StringIO(text)))[header_idx:]
    if not rows:
        return pd.DataFrame(), date_range
    maxc = max(len(r) for r in rows)
    rows = [r + [None] * (maxc - len(r)) for r in rows]
    return pd.DataFrame(rows), date_range


def clean_flight_schedule_bytes(data: bytes, filename: str) -> CleanResult:
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if ext == "csv":
        raw_df, (from_d, to_d) = _read_csv_bytes(data)
        result = clean_flight_schedule_dataframe(raw_df, dayfirst=False, source_kind="csv")
    else:
        raw_df = pd.read_excel(io.BytesIO(data), header=None, dtype=object)
        
        # Convert Excel content to text string to extract date range if needed
        excel_text = " ".join(raw_df.astype(str).values.flatten())
        from_d, to_d = extract_report_date_range(excel_text)
        
        result = clean_flight_schedule_dataframe(raw_df, dayfirst=True, source_kind="excel")

    result.report_from = from_d
    result.report_to = to_d
    return result


def clean_flight_schedule_file(path: str) -> CleanResult:
    with open(path, "rb") as f:
        return clean_flight_schedule_bytes(f.read(), path)


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "24JUL261459.CSV"
    res = clean_flight_schedule_file(p)
    print(f"[{res.source_kind}] parsed={res.total_parsed} valid={res.valid_count} "
          f"dropped={res.dropped_count} range={res.report_from}..{res.report_to}")

    if len(res.flights_df):
        print("\nSample row:")
        print(res.flights_df.iloc[0].to_dict())