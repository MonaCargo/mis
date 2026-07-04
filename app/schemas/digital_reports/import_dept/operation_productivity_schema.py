# """
# Pydantic schemas for the Import Operations Productivity Dashboard.

# The dashboard is a flat list of metric rows grouped into sections, mirroring
# the Excel spec (Overview, P.1 Segregation, P.2 Examination, P.3 Release,
# P.4 Truck Loading, P.5 SLA). Each row carries:

#   - a stable `key` so the frontend can style / locate it
#   - `value`      : the computed number (None when the source report is not
#                    yet loaded — the frontend renders these as "—")
#   - `unit`       : how to format it (MT / count / percent / productivity)
#   - `source`     : "System" or "Manual" (from the spec's Source column)
#   - `pending`    : True when we can't compute it yet (source not loaded)
# """

# from datetime import datetime
# from enum import Enum
# from typing import Optional

# from pydantic import BaseModel


# class MetricUnit(str, Enum):
#     mt = "MT"           # tonnage, shown in metric tonnes (kg / 1000)
#     count = "count"
#     percent = "percent"
#     productivity = "productivity"
#     none = "none"


# class MetricSource(str, Enum):
#     system = "System"
#     manual = "Manual"


# class MetricRow(BaseModel):
#     key: str
#     s_no: str            # "1.A", "1", "P.1", etc. — matches the Excel S.No. column
#     description: str
#     value: Optional[float] = None
#     unit: MetricUnit = MetricUnit.none
#     source: Optional[MetricSource] = None
#     source_report: Optional[str] = None
#     pending: bool = False
#     note: Optional[str] = None


# class MetricSection(BaseModel):
#     key: str
#     title: str
#     rows: list[MetricRow]


# class ImportProductivityDashboardMeta(BaseModel):
#     from_ist: datetime      # echoed back in IST
#     to_ist: datetime
#     generated_at_ist: datetime
#     flight_count: int       # convenience denominators for the frontend
#     awb_count: int


# class ImportProductivityDashboardResponse(BaseModel):
#     meta: ImportProductivityDashboardMeta
#     sections: list[MetricSection]








# # ── TRUCK IN OUT IMPORT SCHEMA ────────────────────────────────────────────────────────

# class TruckInOutUploadResponse(BaseModel):
#     filename:       str
#     records_found:  int
#     inserted:       int
#     skipped:        int           # duplicate gp_no rows ignored
#     total_batches:  int
#     status:         str           # "success" | "failed"
#     errors:         list[str]






























"""
Pydantic schemas for the Import Operations Productivity Dashboard (shift-based).

The dashboard takes a SINGLE IST date and splits it into three shifts:
    Morning    06:00 - 14:00  (same day)
    Afternoon  14:00 - 22:00  (same day)
    Evening    22:00 - 06:00  (next day)

Each shipment is assigned to a shift by its flt_com_dat_tim (flight completion),
converted to IST. Each metric row therefore carries a value per shift plus a
day total.
"""

from datetime import date, datetime
from enum import Enum
from typing import Optional

from pydantic import BaseModel


class MetricUnit(str, Enum):
    mt = "MT"
    count = "count"
    percent = "percent"
    productivity = "productivity"
    none = "none"


class MetricSource(str, Enum):
    system = "System"
    manual = "Manual"


class ShiftValues(BaseModel):
    """One metric's value across the three shifts and the full-day total."""
    morning: Optional[float] = None
    afternoon: Optional[float] = None
    evening: Optional[float] = None
    total: Optional[float] = None


class MetricRow(BaseModel):
    key: str
    s_no: str
    description: str
    values: ShiftValues = ShiftValues()
    unit: MetricUnit = MetricUnit.none
    source: Optional[MetricSource] = None
    source_report: Optional[str] = None
    pending: bool = False
    note: Optional[str] = None


class MetricSection(BaseModel):
    key: str
    title: str
    rows: list[MetricRow]


class ShiftWindow(BaseModel):
    name: str
    start_ist: datetime
    end_ist: datetime


class ImportProductivityDashboardMeta(BaseModel):
    report_date_ist: date
    shifts: list[ShiftWindow]
    generated_at_ist: datetime
    flight_count: int
    awb_count: int


class ImportProductivityDashboardResponse(BaseModel):
    meta: ImportProductivityDashboardMeta
    sections: list[MetricSection]








# ── TRUCK IN OUT IMPORT SCHEMA ────────────────────────────────────────────────────────

class TruckInOutUploadResponse(BaseModel):
    filename:       str
    records_found:  int
    inserted:       int
    skipped:        int           # duplicate gp_no rows ignored
    total_batches:  int
    status:         str           # "success" | "failed"
    errors:         list[str]





