"""
Cleaning / parsing for the shift-worker Roster report.

clean_roster_report(file_bytes, filename) -> list[dict]

Reads the roster .xlsx (or .csv) and returns clean row dicts. Pure — no DB.

File layout:
    Row 1 : header  -> SN | Emp. Code | Emp. Name | Desg | Department |
                       Date | Shift | Present
    Row 2+: data

Each clean row dict:
    {
      "emp_code":  str,
      "emp_name":  str | None,
      "desg":      str | None,
      "department":str | None,
      "date":      datetime.date,
      "shift":     str,
      "present_status": "P" | "A" | None,
    }

Present/Absent mapping (case-insensitive):
    'Present' -> "P"
    'Absent'  -> "A"
    anything else / blank -> None   (preserves the "unknown" state, e.g. an
                                      ex-employee still listed with no marking)

Rows with no emp_code, or no parseable date, or no shift are skipped — those
are the identifying fields an attendance record cannot exist without.
"""

from __future__ import annotations

import csv
import io
from datetime import date, datetime
from typing import Optional

import openpyxl

# Column positions (0-based) from the row-1 header.
_COL_SN = 0
_COL_EMP_CODE = 1
_COL_EMP_NAME = 2
_COL_DESG = 3
_COL_DEPARTMENT = 4
_COL_DATE = 5
_COL_SHIFT = 6
_COL_PRESENT = 7

_HEADER_HINT = "emp"   # header row's Emp. Code cell contains 'Emp'

# Day-first date formats for string dates (xlsx usually gives real datetimes).
_DATE_FORMATS = (
    "%d-%m-%Y", "%d-%m-%y", "%d-%b-%Y", "%d-%b-%y",
    "%d/%m/%Y", "%d/%m/%y", "%Y-%m-%d",
    "%d-%m-%Y %H:%M:%S", "%Y-%m-%d %H:%M:%S",
)


def _clean_str(value) -> Optional[str]:
    if value is None:
        return None
    s = str(value).strip()
    return s or None


def _emp_code(value) -> Optional[str]:
    """Emp code as a clean string. Excel may give it as a float (523612.0)."""
    if value is None:
        return None
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    s = str(value).strip()
    # strip a trailing '.0' if it slipped through as text
    if s.endswith(".0") and s[:-2].isdigit():
        s = s[:-2]
    return s or None


def _to_date(value) -> Optional[date]:
    if value is None:
        return None
    if isinstance(value, datetime):
        return value.date()
    if isinstance(value, date):
        return value
    s = str(value).strip()
    if not s:
        return None
    try:
        return datetime.fromisoformat(s).date()
    except ValueError:
        pass
    for fmt in _DATE_FORMATS:
        try:
            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    return None


def _present_status(value) -> Optional[str]:
    """'Present'->'P', 'Absent'->'A', else None (case-insensitive)."""
    if value is None:
        return None
    s = str(value).strip().lower()
    if s == "present":
        return "P"
    if s == "absent":
        return "A"
    return None


def _is_header(cells: list) -> bool:
    c = cells[_COL_EMP_CODE] if len(cells) > _COL_EMP_CODE else None
    return bool(c) and _HEADER_HINT in str(c).strip().lower()


def _rows_from_xlsx(file_bytes: bytes) -> list[list]:
    wb = openpyxl.load_workbook(io.BytesIO(file_bytes), data_only=True)
    ws = wb.worksheets[0]
    return [
        [ws.cell(row=r, column=c).value for c in range(1, ws.max_column + 1)]
        for r in range(1, ws.max_row + 1)
    ]


def _rows_from_csv(file_bytes: bytes) -> list[list]:
    text = file_bytes.decode("utf-8-sig", errors="replace")
    return list(csv.reader(io.StringIO(text)))


def clean_import_roster_report(file_bytes: bytes, filename: str = "") -> list[dict]:
    name = (filename or "").lower()
    if name.endswith(".csv"):
        raw_rows = _rows_from_csv(file_bytes)
    else:
        try:
            raw_rows = _rows_from_xlsx(file_bytes)
        except Exception:
            raw_rows = _rows_from_csv(file_bytes)

    # Locate the header row, default to row 0 being header if not found.
    header_idx = 0
    for i, cells in enumerate(raw_rows):
        if _is_header(cells):
            header_idx = i
            break

    cleaned: list[dict] = []
    for cells in raw_rows[header_idx + 1:]:
        def cell(i):
            return cells[i] if i < len(cells) else None

        emp_code = _emp_code(cell(_COL_EMP_CODE))
        d = _to_date(cell(_COL_DATE))
        shift = _clean_str(cell(_COL_SHIFT))

        # An attendance record needs at least: who, when (date), which shift.
        if emp_code is None or d is None or shift is None:
            continue

        cleaned.append({
            "emp_code": emp_code,
            "emp_name": _clean_str(cell(_COL_EMP_NAME)),
            "desg": _clean_str(cell(_COL_DESG)),
            "department": _clean_str(cell(_COL_DEPARTMENT)),
            "date": d,
            "shift": shift,
            "present_status": _present_status(cell(_COL_PRESENT)),
        })

    return cleaned