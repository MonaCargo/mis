
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

# ── row layout (0-based raw index -> field), after the header row ───────────
COL_MAP: dict[int, str] = {
    1: "sl_no", 2: "flt_no", 3: "dest",
    6: "planning_received_mt",
    7: "planned_uld_pallet", 8: "planned_uld_container", 9: "planned_uld_bulk",
    10: "pending_uld_pallet", 11: "pending_uld_container", 12: "pending_uld_bulk",
    13: "delivered_qty_mt", 14: "pending_tonnage_mt",
}
DURATION_COLS: dict[int, str] = {25: "release_performance_d_sla", 26: "planning_performance_d_x"}
DATETIME_PAIRS: dict[str, tuple[int, int]] = {
    "flt_date_time":                (4, 5),
    "planning_date_time":           (15, 16),
    "buildup_start_date_time":      (17, 18),
    "buildup_completion_date_time": (19, 20),
    "gp_generation_date_time":      (21, 22),
    "uld_release_date_time":        (23, 24),
}

INT_COLS    = ["sl_no", "planning_received_mt", "planned_uld_pallet", "planned_uld_container",
               "planned_uld_bulk", "pending_uld_pallet", "pending_uld_container", "pending_uld_bulk"]
FLOAT_COLS  = ["delivered_qty_mt", "pending_tonnage_mt"]
STRING_COLS = ["flt_no", "dest"]

_HEADER_RE = re.compile(r"^\s*sl[_.\s]*no", re.I)
_RANGE_RE  = re.compile(r"DATE\s*:\s*(\d{2}[A-Z]{3}\d{4}).*?DATE\s*:\s*(\d{2}[A-Z]{3}\d{4})", re.I)

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
    flt_dates:       list[date] = field(default_factory=list)   # for validation
    report_from:     date | None = None                         # from header row
    report_to:       date | None = None                         # from header row


# ── field helpers (same conventions as uplift_cleaner.py) ───────────────────

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


def _combine_utc(date_val, time_val, dayfirst: bool) -> datetime | None:
    d = _maybe_swap(_to_date(date_val), dayfirst)
    if d is None:
        return None
    return datetime.combine(d, _to_time(time_val) or time(0, 0), tzinfo=IST).astimezone(UTC)


def _combine_ist_parts(date_val, time_val, dayfirst: bool) -> tuple[date | None, time | None]:
    """Raw IST date & time, NO UTC conversion — kept separate for *_date/*_time columns."""
    d = _maybe_swap(_to_date(date_val), dayfirst)
    if d is None:
        return (None, None)
    return (d, _to_time(time_val))


def _parse_duration_to_minutes(value) -> int | None:
    """'5:35' (H:MM) -> 335 minutes. Used for the D-SLA / D-X performance columns."""
    s = _safe_str(value)
    if s is None or ":" not in s:
        return None
    try:
        h, m = s.split(":", 1)
        return int(h) * 60 + int(m)
    except ValueError:
        return None


# ── core ─────────────────────────────────────────────────────────────────────

def clean_flight_status_dataframe(raw_df: pd.DataFrame, dayfirst: bool = DEFAULT_DAYFIRST,
                                  source_kind: str = "") -> CleanResult:
    rows, dropped = [], []
    total = 0
    flt_dates: list[date] = []

    for _, raw in raw_df.iterrows():
        c1 = _safe_str(raw.iloc[1]) if len(raw) > 1 else None

        # skip the real header row itself, in case it's included in raw_df
        if c1 and _HEADER_RE.match(c1):
            continue

        sl_int = _safe_int(raw.iloc[1] if len(raw) > 1 else None)
        if sl_int is None:
            # blank / title / stray row -> skip, not a dropped flight
            continue

        total += 1

        flt_no = _clean_flight_no(raw.iloc[2] if len(raw) > 2 else None)
        if flt_no is None:
            dropped.append({"reason": "missing_flt_no", "sl_no": sl_int,
                            "flt_no_raw": raw.iloc[2] if len(raw) > 2 else None})
            continue

        rec = {"sl_no": sl_int, "flt_no": flt_no}
        for idx, name in COL_MAP.items():
            if name in ("sl_no", "flt_no"):
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

        for name, (di, ti) in DATETIME_PAIRS.items():
            dv = raw.iloc[di] if len(raw) > di else None
            tv = raw.iloc[ti] if len(raw) > ti else None
            base = name[:-len("_date_time")] if name.endswith("_date_time") else name

            d_part, t_part = _combine_ist_parts(dv, tv, dayfirst)   # raw IST
            rec[f"{base}_date"] = d_part
            rec[f"{base}_time"] = t_part
            rec[f"{base}_date_time_combine"] = _combine_utc(dv, tv, dayfirst)  # UTC

        # duration columns (D-SLA / D-X, "H:M") -> time object, per model's Time column
        for idx, name in DURATION_COLS.items():
            raw_dur = raw.iloc[idx] if len(raw) > idx else None
            rec[name] = _to_time(raw_dur)
        rec["release_performance_minutes"] = _parse_duration_to_minutes(raw.iloc[25] if len(raw) > 25 else None)
        rec["planning_performance_minutes"] = _parse_duration_to_minutes(raw.iloc[26] if len(raw) > 26 else None)

        # rename flt_time -> dep_time to match model's column name
        rec["dep_time"] = rec.pop("flt_time", None)

        fdate = rec.get("flt_date")
        if fdate:
            flt_dates.append(fdate)

        rows.append(rec)

    all_cols = (list(COL_MAP.values())
                + [f"{n[:-len('_date_time')]}_{s}" for n in DATETIME_PAIRS for s in ("date", "time", "date_time_combine")]
                + ["release_performance_minutes", "planning_performance_minutes"])
    df_result = pd.DataFrame(rows) if rows else pd.DataFrame(columns=all_cols)

    return CleanResult(
        flights_df=df_result,
        dropped_flights=dropped,
        total_parsed=total,
        valid_count=len(rows),
        dropped_count=len(dropped),
        source_kind=source_kind,
        flt_dates=flt_dates,
    )


# ── report date-range extraction & validation ────────────────────────────────

def _fmt(d: date) -> str:
    """10 Jul 2026 style."""
    return d.strftime("%d %b %Y").lstrip("0")


class DateValidationError(ValueError):
    """Raised when file dates fall outside the report's [from_date, to_date] window."""


def extract_report_date_range(text: str) -> tuple[date | None, date | None]:
    """Pulls the 'DATE :01JUL2026,TO,DATE :21JUL2026' row into (from_date, to_date)."""
    m = _RANGE_RE.search(text)
    if not m:
        return (None, None)
    try:
        f = datetime.strptime(m.group(1), _RANGE_DATE_FORMAT).date()
        t = datetime.strptime(m.group(2), _RANGE_DATE_FORMAT).date()
        return (f, t)
    except ValueError:
        return (None, None)


def validate_dates(result: CleanResult, report_date: date) -> None:
    """Every row's flt_date must equal report_date exactly (single-day report,
    mirrors uplift_cleaner.py's validate_dates — no range allowed)."""
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

_HEADER_MARKER = "SL_NO"


def _find_header_row(lines: list[str]) -> int:
    for i, line in enumerate(lines):
        if _HEADER_MARKER in line.upper():
            return i
    raise ValueError("Could not locate header row (looking for 'SL_NO')")


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


def clean_flight_status_bytes(data: bytes, filename: str) -> CleanResult:
    ext = (filename or "").lower().rsplit(".", 1)[-1]
    if ext == "csv":
        raw_df, (from_d, to_d) = _read_csv_bytes(data)
        result = clean_flight_status_dataframe(raw_df, dayfirst=False, source_kind="csv")
    else:
        raw_df = pd.read_excel(io.BytesIO(data), header=None, dtype=object)
        result = clean_flight_status_dataframe(raw_df, dayfirst=True, source_kind="excel")
        from_d, to_d = (None, None)  # Excel export has no text preamble to regex

    result.report_from = from_d
    result.report_to = to_d
    return result


def clean_flight_status_file(path: str) -> CleanResult:
    with open(path, "rb") as f:
        return clean_flight_status_bytes(f.read(), path)


if __name__ == "__main__":
    import sys
    p = sys.argv[1] if len(sys.argv) > 1 else "22JUL261450.CSV"
    res = clean_flight_status_file(p)
    print(f"[{res.source_kind}] parsed={res.total_parsed} valid={res.valid_count} "
          f"dropped={res.dropped_count} range={res.report_from}..{res.report_to}")

    if res.report_from and res.report_to:
        try:
            validate_dates(res, res.report_from, res.report_to)
            print("date validation: OK")
        except DateValidationError as e:
            print("date validation FAILED:", e)

    if len(res.flights_df):
        print("\nSample row:")
        print(res.flights_df.iloc[0][
            ["sl_no", "flt_no", "dest", "flt_date", "flt_time",
             "release_performance_dsla", "release_performance_minutes"]
        ].to_dict())