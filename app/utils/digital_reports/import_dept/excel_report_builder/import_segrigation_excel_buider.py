


"""
utils/digital_reports/import_dept/seg_report_builder.py
Exact layout match to target image.

Row 1 : A=empty | B="From Date" | C:F merged="DD/MM/YYYY / HH:MM" |
        G="To Date" | H:J empty | K:N merged="DD/MM/YYYY / HH:MM" |
        O: merged yellow note
Row 2 : A:B merged "Select Date Range" | then per-date 4-col merged headers | Total (yellow)
Row 3 : "Airline Name" | "Airline Code" | sub-headers per date group + Total
Row 4+: PAX group header → PAX airlines → blank → CAO group header → CAO airlines → blank → Total

Date column colour: alternating light-blue / light-gray
Total column     : yellow
PAX group header : light green
CAO group header : light peach/salmon
Total data row   : yellow
"""

import io
from datetime import date, datetime, timezone
from zoneinfo import ZoneInfo

from openpyxl import Workbook
from openpyxl.styles import Alignment, Border, Font, PatternFill, Side
from openpyxl.utils import get_column_letter

# ── Colours (ARGB) ────────────────────────────────────────────────────────────
_C_BLUE       = "FFD9E1F2"   # light blue  — odd date columns
_C_GRAY       = "FFD6DCE4"   # light gray  — even date columns
_C_YELLOW     = "FFFFFF00"   # yellow      — Total column + Total row

_IST = ZoneInfo("Asia/Kolkata")


def _to_ist(iso_str: str) -> str:
    """
    Convert ISO datetime string (UTC-aware or naive) → IST display string.
    Output format: DD/MM/YYYY HH:MM  (matches the column header label)
    """
    try:
        dt = datetime.fromisoformat(iso_str.replace("Z", "+00:00"))
        if dt.tzinfo is None:
            dt = dt.replace(tzinfo=timezone.utc)
        return dt.astimezone(_IST).strftime("%d/%m/%Y %H:%M")
    except Exception:
        return iso_str   # fallback: show raw string if parse fails
_C_YELLOW_HDR = "FFFFD966"   # darker yellow — row-1 note bar
_C_GREEN      = "FFE2EFDA"   # light green — PAX group header
_C_PEACH      = "FFFCE4D6"   # light peach — CAO group header
_C_WHITE      = "FFFFFFFF"
_C_HDR_BLUE   = "FFD9E1F2"   # row-1 From/To date area

# ── Border ────────────────────────────────────────────────────────────────────
_THIN   = Side(style="thin")
_BORDER = Border(left=_THIN, right=_THIN, top=_THIN, bottom=_THIN)

_FONT  = "Arial"
_METRICS     = ["Flight\nCount", "AWB\nCount", "Piece\nCount", "Gross\nWgt (MT)", "Chg\nWgt (MT)"]
_METRIC_KEYS = ["flight_count", "awb_count", "pcs", "gross_wgt_mt", "chg_wgt_mt"]
_FMT_INT     = "#,##0"
_FMT_FLOAT   = "#,##0.000"

LABEL_COLS = 2   # A = Airline Name, B = Airline Code
METRIC_N   = 5   # cols per date group  ← was 4


def _s(cell, bold=False, bg=None, h_align="center", wrap=False,
        num_fmt=None, size=9, color="FF000000"):
    cell.font      = Font(name=_FONT, bold=bold, size=size, color=color)
    cell.alignment = Alignment(horizontal=h_align, vertical="center",
                                wrap_text=wrap)
    cell.border    = _BORDER
    if bg:
        cell.fill = PatternFill("solid", start_color=bg)
    if num_fmt:
        cell.number_format = num_fmt


def _merge_write(ws, r, c1, c2, value, **skw):
    """Merge c1:c2 on row r, write value to c1, style c1."""
    if c2 > c1:
        ws.merge_cells(start_row=r, start_column=c1,
                       end_row=r,   end_column=c2)
    cell = ws.cell(row=r, column=c1, value=value)
    _s(cell, **skw)
    # style the hidden merged cells too (borders look right in Excel)
    for c in range(c1 + 1, c2 + 1):
        _s(ws.cell(row=r, column=c), bg=skw.get("bg"))


def _date_bg(i: int) -> str:
    """Alternating light-blue / light-gray for date column groups."""
    return _C_BLUE if i % 2 == 0 else _C_GRAY


def _empty_m() -> dict:
    return {"flight_count": 0, "awb_count": 0, "pcs": 0, "gross_wgt_mt": 0.0, "chg_wgt_mt": 0.0}


def _write_4metrics(ws, row, col, metrics, bg, bold=False):
    vals = [metrics.get(k, 0) for k in _METRIC_KEYS]
    fmts = [_FMT_INT, _FMT_INT, _FMT_INT, _FMT_FLOAT, _FMT_FLOAT]
    for j, (val, fmt) in enumerate(zip(vals, fmts)):
        c = ws.cell(row=row, column=col + j, value=val)
        _s(c, bold=bold, bg=bg, num_fmt=fmt)


def build_excel(report: dict) -> bytes:
    wb  = Workbook()
    ws  = wb.active
    ws.title = "Segregation Report"

    dates     = report["dates"]          # list of ISO date strings
    n         = len(dates)
    # col where Total group starts
    TOT_START = LABEL_COLS + n * METRIC_N + 1
    LAST_COL  = TOT_START + METRIC_N - 1

    # ── ROW 1 ─────────────────────────────────────────────────────────────────
    # A1 empty
    _s(ws.cell(row=1, column=1, value=""), bg=_C_WHITE)

    # B1 "From Date"
    _s(ws.cell(row=1, column=2, value="From Date"),
       bold=True, bg=_C_HDR_BLUE)

    # C1:F1 — actual from datetime in IST  e.g. "21/06/2026 00:00"
    _merge_write(ws, 1, 3, 6, _to_ist(report["from_dt"]),
                 bold=True, bg=_C_HDR_BLUE)

    # G1 "To Date"
    _s(ws.cell(row=1, column=7, value="To Date"),
       bold=True, bg=_C_WHITE)

    # H1:J1 empty
    for c in range(8, 11):
        _s(ws.cell(row=1, column=c, value=""), bg=_C_WHITE)

    # K1:N1 — actual to datetime in IST  e.g. "21/07/2026 23:59"
    _merge_write(ws, 1, 11, 14, _to_ist(report["to_dt"]),
                 bold=True, bg=_C_HDR_BLUE)

    # O1 → LAST_COL : yellow note
    note = "Note : Maximum 31 Days Date Range ( From to TO ) is allowed to Select"
    _merge_write(ws, 1, 15, max(LAST_COL, 15), note,
                 bold=True, bg=_C_YELLOW_HDR)

    # ── ROW 2 — "Select Date Range" + date headers + Total ────────────────────
    # A2:B2 merged
    _merge_write(ws, 2, 1, 2, "Select Date Range",
                 bold=True, bg=_C_HDR_BLUE)

    for i, ds in enumerate(dates):
        d_obj     = date.fromisoformat(ds)
        label     = d_obj.strftime("%d-%m-%y")
        bg        = _date_bg(i)
        col_start = LABEL_COLS + i * METRIC_N + 1
        col_end   = col_start + METRIC_N - 1
        _merge_write(ws, 2, col_start, col_end, label,
                     bold=True, bg=bg)

    # Total header (yellow)
    _merge_write(ws, 2, TOT_START, TOT_START + METRIC_N - 1, "Total",
                 bold=True, bg=_C_YELLOW)

    # ── ROW 3 — sub-headers ───────────────────────────────────────────────────
    _s(ws.cell(row=3, column=1, value="Airline Name"),
       bold=True, bg=_C_GRAY, wrap=True)
    _s(ws.cell(row=3, column=2, value="Airline\nCode"),
       bold=True, bg=_C_GRAY, wrap=True)

    for i in range(n):
        bg        = _date_bg(i)
        col_start = LABEL_COLS + i * METRIC_N + 1
        for j, label in enumerate(_METRICS):
            c = ws.cell(row=3, column=col_start + j, value=label)
            _s(c, bold=True, bg=bg, wrap=True)

    # Total sub-headers
    for j, label in enumerate(_METRICS):
        c = ws.cell(row=3, column=TOT_START + j, value=label)
        _s(c, bold=True, bg=_C_YELLOW, wrap=True)

    # ── Helper: write one airline data row ────────────────────────────────────
    def _data_row(row_num, name, code, per_date, grand_total,
                  bg_label=None, bold=False):
        c = ws.cell(row=row_num, column=1, value=name)
        _s(c, bold=bold, bg=bg_label, h_align="left")
        c = ws.cell(row=row_num, column=2, value=code)
        _s(c, bold=bold, bg=bg_label)

        for i, ds in enumerate(dates):
            bg  = _date_bg(i)
            col = LABEL_COLS + i * METRIC_N + 1
            _write_4metrics(ws, row_num, col,
                            per_date.get(ds, _empty_m()), bg, bold)

        _write_4metrics(ws, row_num, TOT_START, grand_total, _C_YELLOW, bold)

    # ── Helper: write a group header row (PAX / CAO) ──────────────────────────
    def _group_header(row_num, name, code, per_date, grand_total, bg):
        c = ws.cell(row=row_num, column=1, value=name)
        _s(c, bold=True, bg=bg, h_align="left")
        c = ws.cell(row=row_num, column=2, value=code)
        _s(c, bold=True, bg=bg)

        for i, ds in enumerate(dates):
            col = LABEL_COLS + i * METRIC_N + 1
            _write_4metrics(ws, row_num, col,
                            per_date.get(ds, _empty_m()), bg, bold=True)

        _write_4metrics(ws, row_num, TOT_START, grand_total, _C_YELLOW, bold=True)

    # ── PAX section ───────────────────────────────────────────────────────────
    cur = 4
    pax = report["pax"]
    _group_header(cur, "Passenger Flights", "PAX",
                  pax["per_date"], pax["grand_total"], _C_GREEN)
    cur += 1

    for airline in pax["airlines"]:
        _data_row(cur,
                  airline["airline_name"],
                  airline["airline_code"],
                  airline["per_date"],
                  airline["grand_total"])
        cur += 1

    # blank separator row
    for col in range(1, LAST_COL + 1):
        _s(ws.cell(row=cur, column=col, value=""), bg=_C_WHITE)
    cur += 1

    # ── CAO section ───────────────────────────────────────────────────────────
    cao = report["cao"]
    _group_header(cur, "Freighters", "CAO",
                  cao["per_date"], cao["grand_total"], _C_PEACH)
    cur += 1

    for airline in cao["airlines"]:
        _data_row(cur,
                  airline["airline_name"],
                  airline["airline_code"],
                  airline["per_date"],
                  airline["grand_total"])
        cur += 1

    # blank separator
    for col in range(1, LAST_COL + 1):
        _s(ws.cell(row=cur, column=col, value=""), bg=_C_WHITE)
    cur += 1

    # ── Grand Total row ───────────────────────────────────────────────────────
    c = ws.cell(row=cur, column=1, value="Total")
    _s(c, bold=True, bg=_C_YELLOW, h_align="left")
    c = ws.cell(row=cur, column=2, value="")
    _s(c, bold=True, bg=_C_YELLOW)

    for i, ds in enumerate(dates):
        col = LABEL_COLS + i * METRIC_N + 1
        _write_4metrics(ws, cur, col,
                        report["per_date"].get(ds, _empty_m()),
                        _C_YELLOW, bold=True)

    _write_4metrics(ws, cur, TOT_START, report["grand_total"],
                    _C_YELLOW, bold=True)

    # ── Column widths ─────────────────────────────────────────────────────────
    ws.column_dimensions["A"].width = 22
    ws.column_dimensions["B"].width = 10
    for col in range(3, LAST_COL + 1):
        ws.column_dimensions[get_column_letter(col)].width = 10

    # ── Row heights ───────────────────────────────────────────────────────────
    ws.row_dimensions[1].height = 20
    ws.row_dimensions[2].height = 22
    ws.row_dimensions[3].height = 38

    # ── Freeze: keep label cols + first 3 header rows fixed ──────────────────
    ws.freeze_panes = "C4"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


# ── CSV (unchanged logic) ─────────────────────────────────────────────────────
def build_csv(report: dict) -> bytes:
    import csv
    buf = io.StringIO()
    w   = csv.writer(buf)
    w.writerow(["airline_type","airline_code","airline_name","date",
                "flight_count","awb_count","pcs","gross_wgt_mt","chg_wgt_mt"])
    for gk in ("pax","cao"):
        for airline in report[gk]["airlines"]:
            for ds, m in airline["per_date"].items():
                w.writerow([airline["airline_type"], airline["airline_code"],
                            airline["airline_name"], ds,
                            m["flight_count"], m["awb_count"],
                            m["pcs"], m["gross_wgt_mt"], m["chg_wgt_mt"]])
    return buf.getvalue().encode("utf-8-sig")


# ═════════════════════════════════════════════════════════════════════════════
# DETAILED FORMAT — 3-level: group → airline → individual flights
# ═════════════════════════════════════════════════════════════════════════════

_C_AIRLINE_ROW = "FFD9E1F2"   # light blue  — airline rows
_C_FLIGHT_ROW  = "FFE2EFDA"   # light green — individual flight rows


def build_excel_detailed(report: dict) -> bytes:
    """
    Detailed export: each airline is followed by its individual flight rows.

    Layout per the target image:
      SN | Airline Name | Code | <date groups> | Total
      1     Passenger Flights   PAX      ← group header (peach)
      1.1     Air India         AI       ← airline row (blue)
      1.1(a)    AI1234                    ← flight row (green)
      1.1(b)    AI2345                    ← flight row (green)
      ...
      2     Freighters          CAO      ← group header (peach)
      ...
      Total                              ← grand total (peach)

    Column A = SN (hierarchical), B = Airline Name / flight no, C = Code.
    Data columns shift right by 1 vs the simple format (extra SN column).
    """
    wb = Workbook()
    ws = wb.active
    ws.title = "Segregation Detailed"

    dates = report["dates"]
    n     = len(dates)

    # 3 label columns now: SN | Airline Name | Code
    LBL = 3
    TOT_START = LBL + n * METRIC_N + 1
    LAST_COL  = TOT_START + METRIC_N - 1

    # ── ROW 1 — From/To datetime header ───────────────────────────────────────
    _s(ws.cell(row=1, column=1, value=""), bg=_C_WHITE)
    _s(ws.cell(row=1, column=2, value="From Date"), bold=True, bg=_C_HDR_BLUE)
    _merge_write(ws, 1, 3, 6, _to_ist(report["from_dt"]), bold=True, bg=_C_HDR_BLUE)
    _s(ws.cell(row=1, column=7, value="To Date"), bold=True, bg=_C_WHITE)
    for c in range(8, 11):
        _s(ws.cell(row=1, column=c, value=""), bg=_C_WHITE)
    _merge_write(ws, 1, 11, 14, _to_ist(report["to_dt"]), bold=True, bg=_C_HDR_BLUE)
    note = "Note : Maximum 31 Days Date Range ( From to TO ) is allowed to Select"
    _merge_write(ws, 1, 15, max(LAST_COL, 15), note, bold=True, bg=_C_YELLOW_HDR)

    # ── ROW 2 — SN/Name/Code labels + date headers + Total ────────────────────
    _s(ws.cell(row=2, column=1, value="SN"), bold=True, bg=_C_HDR_BLUE)
    _merge_write(ws, 2, 2, 3, "Select Date Range", bold=True, bg=_C_HDR_BLUE)

    for i, ds in enumerate(dates):
        d_obj = date.fromisoformat(ds)
        bg = _date_bg(i)
        col_start = LBL + i * METRIC_N + 1
        _merge_write(ws, 2, col_start, col_start + METRIC_N - 1,
                     d_obj.strftime("%d-%m-%y"), bold=True, bg=bg)
    _merge_write(ws, 2, TOT_START, TOT_START + METRIC_N - 1, "Total",
                 bold=True, bg=_C_YELLOW)

    # ── ROW 3 — sub-headers ───────────────────────────────────────────────────
    _s(ws.cell(row=3, column=1, value="SN"), bold=True, bg=_C_GRAY, wrap=True)
    _s(ws.cell(row=3, column=2, value="Airline Name"), bold=True, bg=_C_GRAY, wrap=True)
    _s(ws.cell(row=3, column=3, value="Airline\nCode"), bold=True, bg=_C_GRAY, wrap=True)

    for i in range(n):
        bg = _date_bg(i)
        col_start = LBL + i * METRIC_N + 1
        for j, label in enumerate(_METRICS):
            _s(ws.cell(row=3, column=col_start + j, value=label),
               bold=True, bg=bg, wrap=True)
    for j, label in enumerate(_METRICS):
        _s(ws.cell(row=3, column=TOT_START + j, value=label),
           bold=True, bg=_C_YELLOW, wrap=True)

    # ── Row writer (3 label cols, then metrics) ──────────────────────────────
    def _row(row_num, sn, name, code, per_date, grand_total, bg, bold=False,
             name_align="center"):
        _s(ws.cell(row=row_num, column=1, value=sn),   bold=bold, bg=bg)
        _s(ws.cell(row=row_num, column=2, value=name), bold=bold, bg=bg, h_align=name_align)
        _s(ws.cell(row=row_num, column=3, value=code), bold=bold, bg=bg)
        for i, ds in enumerate(dates):
            col = LBL + i * METRIC_N + 1
            _write_4metrics(ws, row_num, col, per_date.get(ds, _empty_m()), bg, bold)
        _write_4metrics(ws, row_num, TOT_START, grand_total, _C_YELLOW, bold)

    # ── Build body ────────────────────────────────────────────────────────────
    cur = 4

    def _write_section(group_label, group_code, group_key, sn_group):
        nonlocal cur
        grp = report[group_key]

        # Group header (peach)
        _row(cur, sn_group, group_label, group_code,
             grp["per_date"], grp["grand_total"], _C_PEACH, bold=True)
        cur += 1

        # Each airline → airline row (blue) then its flights (green)
        for ai, airline in enumerate(grp["airlines"], start=1):
            sn_airline = f"{sn_group}.{ai}"
            _row(cur, sn_airline, airline["airline_name"], airline["airline_code"],
                 airline["per_date"], airline["grand_total"], _C_AIRLINE_ROW, bold=True)
            cur += 1

            for fi, flight in enumerate(airline.get("flights", [])):
                sn_flight = f"{sn_airline}({chr(97 + fi)})"   # a, b, c …
                _row(cur, sn_flight, flight["flight_no"], "",
                     flight["per_date"], flight["grand_total"],
                     _C_FLIGHT_ROW, bold=False)
                cur += 1

    _write_section("Passenger Flights", "PAX", "pax", 1)
    _write_section("Freighters",        "CAO", "cao", 2)

    # ── Grand Total row (peach) ──────────────────────────────────────────────
    _row(cur, "", "Total", "", report["per_date"], report["grand_total"],
         _C_PEACH, bold=True)

    # ── Widths / heights / freeze ────────────────────────────────────────────
    ws.column_dimensions["A"].width = 8
    ws.column_dimensions["B"].width = 24
    ws.column_dimensions["C"].width = 8
    for col in range(4, LAST_COL + 1):
        ws.column_dimensions[get_column_letter(col)].width = 10
    ws.row_dimensions[3].height = 38
    ws.freeze_panes = "D4"

    buf = io.BytesIO()
    wb.save(buf)
    buf.seek(0)
    return buf.read()


def build_csv_detailed(report: dict) -> bytes:
    """Flat CSV with a flight_no column for the detailed export."""
    import csv
    buf = io.StringIO()
    w = csv.writer(buf)
    w.writerow(["airline_type", "airline_code", "airline_name", "flight_no",
                "date", "flight_count", "awb_count", "pcs",
                "gross_wgt_mt", "chg_wgt_mt"])
    for gk in ("pax", "cao"):
        for airline in report[gk]["airlines"]:
            for flight in airline.get("flights", []):
                for ds, m in flight["per_date"].items():
                    w.writerow([airline["airline_type"], airline["airline_code"],
                                airline["airline_name"], flight["flight_no"], ds,
                                m["flight_count"], m["awb_count"], m["pcs"],
                                m["gross_wgt_mt"], m["chg_wgt_mt"]])
    return buf.getvalue().encode("utf-8-sig")