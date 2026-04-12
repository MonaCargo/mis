


"""
extract flight planning.py
=======
Extracts data from an Export Planning Report PDF and writes a
formatted Excel file: flight_planning_output.xlsx

Usage:
    python test.py                                  # uses default PDF path
    python test.py path/to/Flight_planning_report.pdf
"""

import re
import os
import io
from datetime import datetime

import pdfplumber
import pandas as pd



# ─────────────────────────────────────────────────────────────────────────────
# SECTION 1 — PDF EXTRACTION
# ─────────────────────────────────────────────────────────────────────────────

# Column x-boundaries calibrated against Flight_planning_report.pdf
COL_BOUNDS = [
    ("SLNO",       4,   30),
    ("AWB_NUM",   34,  115),
    ("LOCATION",  115, 180),
    ("LOC_PCS",   180, 230),
    ("GROSS_WGT", 230, 310),
    ("CHG_WGT",   310, 360),
    ("ORG",       360, 400),
    ("DES",       400, 432),
    ("SHC",       435, 500),
    ("NOG",       500, 660),
    ("PRIORITY",  660, 800),
]

_ULD_SUMMARY_COLS = [
    ("DEST_SUMMARY",  24,  65),
    ("BOOKED_WGT",    65, 200),
    ("ULD_TYPE",     200, 375),
    ("TOTAL_ULD",    375, 490),
    ("BULK_ALLOWED", 490, 560),
]

# _AWB_RE        = re.compile(r"^\d{3}-\d{7,8}P?$")
# Allow both P and A suffixes
_AWB_RE = re.compile(r"^\d{3}-\d{7,8}[PA]?$")

def _clean_awb(val):
    if not val or str(val).strip().lower() in ("", "nan", "none"):
        return None
    s = re.sub(r"\s+", "", str(val).strip())
    s = re.sub(r"-+", "-", s).replace("-", "")
    s = s.rstrip("PA")   # strip both suffixes
    if s and len(s) == 10:
        s = s.zfill(11)
    return s or None

_FLIGHT_RE = re.compile(
    r"FLIGHT\s*NUM\s*:?\s*([A-Z0-9]{2,8})\s*FLIGHT\s*DATE\s*:?\s*(\d{2}[A-Z]{3}\d{4})",
    re.IGNORECASE,
)
_SKIP_RE = re.compile(
    r"(export\s+planning\s+report|printed\s+on|^page\s+\d+"
    r"|^des\s+booked|^slno\s+awb|^total\s*:)",
    re.IGNORECASE,
)

_CONTINUATION_RE = re.compile(r"^X?\s*PER$", re.IGNORECASE)

# "LHR11119PMC5Y"  — DES BokedWgt ULDType TotalULD BulkAllowed
_SUMMARY_RE  = re.compile(r"^([A-Z]{3})(\d+)([A-Z]+)(\d+)([YN])$", re.IGNORECASE)

def _chars_to_text(chars):
    return "".join(c["text"] for c in sorted(chars, key=lambda c: c["x0"])).strip()


def _extract_cell(chars, x0, x1):
    return _chars_to_text([c for c in chars if x0 - 3 <= c["x0"] <= x1 + 3])


# def _clean_awb(val):
#     if not val or str(val).strip().lower() in ("", "nan", "none"):
#         return None
#     s = re.sub(r"\s+", "", str(val).strip())
#     s = re.sub(r"-+", "-", s).replace("-", "").rstrip("PA")
#     if s and len(s) == 10:
#         s = s.zfill(11)
#     return s or None


# def extract_flight_planning(pdf_source):
#     """Extract all AWB rows from an Export Planning Report PDF.

#     Accepts a file path (str/Path) or any file-like object.
#     Returns a pandas DataFrame ready for further processing.
#     """
#     if isinstance(pdf_source, (str, os.PathLike)):
#         if not os.path.exists(pdf_source):
#             raise FileNotFoundError(f"PDF not found: {pdf_source}")
#         source_file = os.path.basename(pdf_source)
#         pdf_input   = pdf_source
#     else:
#         _name       = getattr(pdf_source, "name", None) or "uploaded.pdf"
#         source_file = os.path.basename(str(_name))
#         pdf_input   = io.BytesIO(pdf_source.read())

#     extracted_at = datetime.now()
#     records      = []

#     flight_ctx = dict(
#         FLIGHT_NUM=None, FLIGHT_DATE=None,
#         DEST_SUMMARY=None, BOOKED_WGT=None,
#         ULD_TYPE=None, TOTAL_ULD=None, BULK_ALLOWED=None,
#     )

#     with pdfplumber.open(pdf_input) as pdf:
#         for page in pdf.pages:
#             chars = page.chars
#             if not chars:
#                 continue

#             # Group chars into lines by y-position (3-pt buckets)
#             line_map = {}
#             for ch in chars:
#                 if not ch["text"].strip():
#                     continue
#                 y_key = round(ch["top"] / 3) * 3
#                 line_map.setdefault(y_key, []).append(ch)

#             for y_key in sorted(line_map):
#                 lc = line_map[y_key]
#                 lt = _chars_to_text(lc)

#                 # Flight header
#                 m = _FLIGHT_HDR_RE.search(lt)
#                 if m:
#                     flight_ctx = dict(
#                         FLIGHT_NUM=m.group(1).strip().upper(),
#                         FLIGHT_DATE=m.group(2).strip().upper(),
#                         DEST_SUMMARY=None, BOOKED_WGT=None,
#                         ULD_TYPE=None, TOTAL_ULD=None, BULK_ALLOWED=None,
#                     )
#                     continue

#                 # ULD summary block  (e.g. "SIN 1006 PMC 5 Y")
#                 uld_dest = _extract_cell(lc, 24, 65)
#                 uld_bulk = _extract_cell(lc, 490, 560)
#                 if re.match(r"^[A-Z]{3}$", uld_dest) and uld_bulk in ("Y", "N"):
#                     flight_ctx["DEST_SUMMARY"] = uld_dest
#                     flight_ctx["BOOKED_WGT"]   = _extract_cell(lc,  65, 200)
#                     flight_ctx["ULD_TYPE"]      = _extract_cell(lc, 200, 375)
#                     flight_ctx["TOTAL_ULD"]     = _extract_cell(lc, 375, 490)
#                     flight_ctx["BULK_ALLOWED"]  = uld_bulk
#                     continue

#                 # Skip header / footer lines
#                 if _SKIP_RE.search(lt):
#                     continue

#                 # Continuation line ("X PER") → append to last NOG
#                 if _CONTINUATION_RE.match(lt):
#                     if records:
#                         extra = _extract_cell(lc, 500, 660).strip()
#                         if extra:
#                             records[-1]["NOG"] = (
#                                 (records[-1]["NOG"] or "") + " " + extra
#                             ).strip()
#                     continue

#                 # Data row
#                 row = {col: _extract_cell(lc, x0, x1) for col, x0, x1 in COL_BOUNDS}
#                 if not _AWB_RE.match((row["AWB_NUM"] or "").strip()):
#                     continue

#                 row.update(flight_ctx)
#                 row["SOURCE_FILE"]  = source_file
#                 row["EXTRACTED_AT"] = extracted_at
#                 records.append(row)

#     if not records:
#         return pd.DataFrame()

#     df = pd.DataFrame(records)

#     # Type coercions
#     df["AWB_NUM"] = df["AWB_NUM"].apply(_clean_awb)

#     for col in ["FLIGHT_NUM", "DEST_SUMMARY", "ULD_TYPE",
#                  "LOCATION", "ORG", "DES", "SHC", "NOG", "PRIORITY"]:
#         df[col] = df[col].str.strip().replace("", None)

#     df["FLIGHT_DATE"] = pd.to_datetime(
#         df["FLIGHT_DATE"], format="%d%b%Y", errors="coerce"
#     ).dt.date

#     for col in ("SLNO", "LOC_PCS", "TOTAL_ULD"):
#         df[col] = pd.to_numeric(df[col], errors="coerce").astype("Int64")

#     for col in ("GROSS_WGT", "CHG_WGT", "BOOKED_WGT"):
#         df[col] = pd.to_numeric(df[col], errors="coerce")

#     df["BULK_ALLOWED"] = df["BULK_ALLOWED"].map({"Y": True, "N": False})

#     return df[[
#         "FLIGHT_NUM", "FLIGHT_DATE",
#         "DEST_SUMMARY", "BOOKED_WGT", "ULD_TYPE", "TOTAL_ULD", "BULK_ALLOWED",
#         "SLNO", "AWB_NUM", "LOCATION", "LOC_PCS",
#         "GROSS_WGT", "CHG_WGT", "ORG", "DES", "SHC", "NOG", "PRIORITY",
#         "SOURCE_FILE", "EXTRACTED_AT",
#     ]].reset_index(drop=True)


def _is_valid_awb(text: str) -> bool:
    return bool(_AWB_RE.match((text or "").strip()))


def _is_nog_continuation(line_chars: list) -> bool:
    """
    True if the line contains chars ONLY in the NOG x-zone (x >= ~500).
    This catches lines like "PER" that are a wrapped continuation of
    the previous row's NOG field.
    """
    if not line_chars:
        return False
    nog_x0, nog_x1 = COL_BOUNDS[9][1], COL_BOUNDS[9][2]   # NOG bounds
    for c in line_chars:
        if c["x0"] < nog_x0 - 10:   # char falls left of NOG zone → not continuation
            return False
    return True


def extract_flight_planning(pdf_source) -> pd.DataFrame:
    """
    Extract all AWB rows from an Export Planning Report PDF.

    Parameters
    ----------
    pdf_source : str | Path | file-like object

    Returns
    -------
    pd.DataFrame  — ready for DB insert. Empty DataFrame if no records.
    """
    import io

    if isinstance(pdf_source, (str, os.PathLike)):
        if not os.path.exists(pdf_source):
            raise FileNotFoundError(f"PDF not found: {pdf_source}")
        source_file = os.path.basename(pdf_source)
        pdf_input   = pdf_source
    else:
        _name       = getattr(pdf_source, "name", None) or "uploaded.pdf"
        source_file = os.path.basename(str(_name))
        pdf_input   = io.BytesIO(pdf_source.read())

    extracted_at = datetime.now()

    # ── Document-level fields (read once from page 1 header) ─────────────────
    flight_num   = None
    flight_date  = None
    doc_des      = None   # flight destination (not per-AWB destination)
    booked_wgt   = None
    uld_type     = None
    total_uld    = None
    bulk_allowed = None

    records      = []
    last_record  = None   # for NOG continuation merging

    with pdfplumber.open(pdf_input) as pdf:
        for page in pdf.pages:
            chars = page.chars
            if not chars:
                continue

            # ── Group chars into lines by y ───────────────────────────────
            line_map: dict = {}
            for ch in chars:
                if not ch["text"].strip():
                    continue
                y_key = round(ch["top"] / 3) * 3
                line_map.setdefault(y_key, []).append(ch)

            # ── Process lines top → bottom ────────────────────────────────
            for y_key in sorted(line_map):
                line_chars = line_map[y_key]
                line_text  = _chars_to_text(line_chars)

                # ── Skip known non-data lines ─────────────────────────────
                if _SKIP_RE.search(line_text):
                    continue

                # ── Flight header: "FLIGHTNUM:AI0161FLIGHTDATE:03APR2026" ─
                if flight_num is None:
                    m = _FLIGHT_RE.search(line_text)
                    if m:
                        flight_num  = m.group(1).strip().upper()
                        flight_date = m.group(2).strip().upper()
                        continue

                # ── Summary row: "LHR11119PMC5Y" ─────────────────────────
                if doc_des is None:
                    m = _SUMMARY_RE.match(line_text)
                    if m:
                        doc_des      = m.group(1).upper()
                        booked_wgt   = m.group(2)
                        uld_type     = m.group(3).upper()
                        total_uld    = m.group(4)
                        bulk_allowed = m.group(5).upper()
                        continue

                # ── NOG continuation line (e.g. "PER" after "CONSOLIDATION AS") ─
                if _is_nog_continuation(line_chars) and last_record is not None:
                    continuation = _extract_cell(
                        line_chars, COL_BOUNDS[9][1], COL_BOUNDS[9][2]
                    )
                    if continuation:
                        last_record["NOG"] = (
                            (last_record["NOG"] or "") + " " + continuation
                        ).strip()
                    continue

                # ── Extract all columns by x-boundary ────────────────────
                row = {
                    col: _extract_cell(line_chars, x0, x1)
                    for col, x0, x1 in COL_BOUNDS
                }

                # Only keep rows with a valid AWB number
                if not _is_valid_awb(row["AWB_NUM"]):
                    continue

                # Attach document-level fields
                row["FLIGHT_NUM"]   = flight_num
                row["FLIGHT_DATE"]  = flight_date
                row["DOC_DES"]      = doc_des
                row["BOOKED_WGT"]   = booked_wgt
                row["ULD_TYPE"]     = uld_type
                row["TOTAL_ULD"]    = total_uld
                row["BULK_ALLOWED"] = bulk_allowed
                row["SOURCE_FILE"]  = source_file
                row["EXTRACTED_AT"] = extracted_at

                records.append(row)
                last_record = row   # track for NOG continuation

    if not records:
        return pd.DataFrame()
    


    df = pd.DataFrame(records)

    # ── Type casting ──────────────────────────────────────────────────────────
    # Type coercions
    df["AWB_NUM"] = df["AWB_NUM"].apply(_clean_awb)
    
    # String columns — strip & empty → None
    for col in ["AWB_NUM", "LOCATION", "ORG", "DES", "SHC", "NOG",
                "PRIORITY", "FLIGHT_NUM", "DOC_DES",
                "ULD_TYPE", "BULK_ALLOWED"]:
        df[col] = df[col].str.strip().replace("", None)

    # ← Remove FLIGHT_DATE from the string loop above, add this instead:
    df["FLIGHT_DATE"] = pd.to_datetime(
        df["FLIGHT_DATE"], format="%d%b%Y", errors="coerce"
    ).dt.date

    # Numeric columns
    df["SLNO"]      = pd.to_numeric(df["SLNO"],      errors="coerce").astype("Int64")
    df["LOC_PCS"]   = pd.to_numeric(df["LOC_PCS"],   errors="coerce").astype("Int64")
    df["GROSS_WGT"] = pd.to_numeric(df["GROSS_WGT"], errors="coerce")
    df["CHG_WGT"]   = pd.to_numeric(df["CHG_WGT"],   errors="coerce")
    df["BOOKED_WGT"]= pd.to_numeric(df["BOOKED_WGT"],errors="coerce").astype("Int64")
    df["TOTAL_ULD"] = pd.to_numeric(df["TOTAL_ULD"], errors="coerce").astype("Int64")

    # Final column order
    df = df[[
        "SLNO", "AWB_NUM", "LOCATION", "LOC_PCS",
        "GROSS_WGT", "CHG_WGT", "ORG", "DES", "SHC", "NOG", "PRIORITY",
        "FLIGHT_NUM", "FLIGHT_DATE", "DOC_DES", "BOOKED_WGT",
        "ULD_TYPE", "TOTAL_ULD", "BULK_ALLOWED",
        "SOURCE_FILE", "EXTRACTED_AT",
    ]]

    df = df.reset_index(drop=True)
    print(df)
    return df



# # ─────────────────────────────────────────────────────────────────────────────
# # SECTION 2 — EXCEL EXPORT
# # ─────────────────────────────────────────────────────────────────────────────

# # Style constants
# HDR_FILL   = PatternFill("solid", start_color="1F4E79")   # dark blue
# HDR_FONT   = Font(name="Arial", bold=True, color="FFFFFF", size=10)
# DATA_FONT  = Font(name="Arial", size=10)
# ALT_FILL   = PatternFill("solid", start_color="D6E4F0")   # light blue
# SUM_FILL   = PatternFill("solid", start_color="BDD7EE")   # medium blue
# SUM_FONT   = Font(name="Arial", bold=True, size=10)
# CENTER     = Alignment(horizontal="center", vertical="center", wrap_text=True)
# LEFT       = Alignment(horizontal="left",   vertical="center", wrap_text=True)
# RIGHT_ALIGN= Alignment(horizontal="right",  vertical="center")

# def _thin_border():
#     s = Side(style="thin", color="B0B0B0")
#     return Border(left=s, right=s, top=s, bottom=s)


# def _write_excel(df, output_path):
#     wb = Workbook()

#     # ── Sheet 1: Flight Summary ───────────────────────────────────────────
#     ws1 = wb.active
#     ws1.title = "Flight Summary"

#     # Title block
#     ws1.merge_cells("A1:G1")
#     ws1["A1"] = "EXPORT PLANNING REPORT — FLIGHT SUMMARY"
#     ws1["A1"].font      = Font(name="Arial", bold=True, size=13, color="1F4E79")
#     ws1["A1"].alignment = CENTER

#     ws1.merge_cells("A2:G2")
#     ws1["A2"] = f"Generated: {datetime.now().strftime('%d-%b-%Y %H:%M')}"
#     ws1["A2"].font      = Font(name="Arial", italic=True, size=9, color="595959")
#     ws1["A2"].alignment = CENTER

#     ws1.row_dimensions[1].height = 22
#     ws1.row_dimensions[2].height = 14

#     # Summary header row
#     summary_cols = [
#         "Flight No.", "Flight Date", "Destination",
#         "Booked Wgt (kg)", "ULD Type", "Total ULDs", "Bulk Allowed",
#     ]
#     for col_idx, label in enumerate(summary_cols, 1):
#         cell = ws1.cell(row=4, column=col_idx, value=label)
#         cell.font      = HDR_FONT
#         cell.fill      = HDR_FILL
#         cell.alignment = CENTER
#         cell.border    = _thin_border()

#     ws1.row_dimensions[4].height = 20

#     # One summary row per unique flight
#     summary = df[["FLIGHT_NUM","FLIGHT_DATE","DEST_SUMMARY",
#                    "BOOKED_WGT","ULD_TYPE","TOTAL_ULD","BULK_ALLOWED"]].drop_duplicates()

#     for r_idx, (_, row) in enumerate(summary.iterrows(), 5):
#         vals = [
#             row["FLIGHT_NUM"],
#             str(row["FLIGHT_DATE"]),
#             row["DEST_SUMMARY"],
#             row["BOOKED_WGT"],
#             row["ULD_TYPE"],
#             int(row["TOTAL_ULD"]) if pd.notna(row["TOTAL_ULD"]) else "",
#             "Yes" if row["BULK_ALLOWED"] else "No",
#         ]
#         fill = ALT_FILL if r_idx % 2 == 0 else PatternFill()
#         for c_idx, val in enumerate(vals, 1):
#             cell = ws1.cell(row=r_idx, column=c_idx, value=val)
#             cell.font      = DATA_FONT
#             cell.fill      = fill
#             cell.alignment = CENTER
#             cell.border    = _thin_border()

#     # Column widths for Sheet 1
#     for col, width in zip("ABCDEFG", [14, 14, 14, 18, 12, 12, 14]):
#         ws1.column_dimensions[col].width = width

#     # ── Sheet 2: AWB Detail ───────────────────────────────────────────────
#     ws2 = wb.create_sheet("AWB Detail")

#     detail_headers = [
#         "Sl No", "AWB Number", "Location", "Pcs",
#         "Gross Wgt (kg)", "Chg Wgt (kg)", "Origin", "Destination",
#         "SHC", "Nature of Goods", "Priority",
#         "Flight No.", "Flight Date",
#     ]
#     detail_keys = [
#         "SLNO", "AWB_NUM", "LOCATION", "LOC_PCS",
#         "GROSS_WGT", "CHG_WGT", "ORG", "DES",
#         "SHC", "NOG", "PRIORITY",
#         "FLIGHT_NUM", "FLIGHT_DATE",
#     ]

#     # Title
#     ws2.merge_cells(f"A1:{get_column_letter(len(detail_headers))}1")
#     ws2["A1"] = "EXPORT PLANNING REPORT — AWB DETAIL"
#     ws2["A1"].font      = Font(name="Arial", bold=True, size=13, color="1F4E79")
#     ws2["A1"].alignment = CENTER
#     ws2.row_dimensions[1].height = 22

#     # Header row
#     for c_idx, label in enumerate(detail_headers, 1):
#         cell = ws2.cell(row=2, column=c_idx, value=label)
#         cell.font      = HDR_FONT
#         cell.fill      = HDR_FILL
#         cell.alignment = CENTER
#         cell.border    = _thin_border()
#     ws2.row_dimensions[2].height = 20

#     # Data rows
#     data_start_row = 3
#     for r_idx, (_, row) in enumerate(df.iterrows(), data_start_row):
#         fill = ALT_FILL if r_idx % 2 == 0 else PatternFill()
#         for c_idx, key in enumerate(detail_keys, 1):
#             val = row[key]
#             # Convert pandas NA / NaT / None to empty string
#             if val is None or (isinstance(val, float) and pd.isna(val)):
#                 val = ""
#             elif hasattr(val, "item"):   # numpy int/float → Python native
#                 val = val.item()
#             cell = ws2.cell(row=r_idx, column=c_idx, value=val)
#             cell.font   = DATA_FONT
#             cell.fill   = fill
#             cell.border = _thin_border()
#             # Right-align numeric columns
#             if key in ("SLNO", "LOC_PCS", "GROSS_WGT", "CHG_WGT"):
#                 cell.alignment = RIGHT_ALIGN
#             else:
#                 cell.alignment = LEFT

#     # Totals row using Excel formulas
#     total_row = data_start_row + len(df)
#     ws2.cell(row=total_row, column=1, value="TOTAL").font      = SUM_FONT
#     ws2.cell(row=total_row, column=1).fill      = SUM_FILL
#     ws2.cell(row=total_row, column=1).alignment = CENTER
#     ws2.cell(row=total_row, column=1).border    = _thin_border()

#     for c_idx, key in enumerate(detail_keys, 1):
#         cell = ws2.cell(row=total_row, column=c_idx)
#         cell.fill   = SUM_FILL
#         cell.font   = SUM_FONT
#         cell.border = _thin_border()
#         if key in ("LOC_PCS", "GROSS_WGT", "CHG_WGT"):
#             col_letter = get_column_letter(c_idx)
#             cell.value     = f"=SUM({col_letter}{data_start_row}:{col_letter}{total_row - 1})"
#             cell.alignment = RIGHT_ALIGN
#         else:
#             cell.alignment = LEFT

#     # Freeze header rows and set column widths for Sheet 2
#     ws2.freeze_panes = "A3"
#     col_widths = [7, 16, 12, 7, 15, 15, 9, 13, 18, 28, 12, 13, 13]
#     for c_idx, width in enumerate(col_widths, 1):
#         ws2.column_dimensions[get_column_letter(c_idx)].width = width

#     # Auto-filter on header row
#     ws2.auto_filter.ref = (
#         f"A2:{get_column_letter(len(detail_headers))}{total_row - 1}"
#     )

#     # ── Sheet 3: Raw Data ─────────────────────────────────────────────────
#     ws3 = wb.create_sheet("Raw Data")

#     raw_cols = list(df.columns)
#     for c_idx, col in enumerate(raw_cols, 1):
#         cell = ws3.cell(row=1, column=c_idx, value=col)
#         cell.font      = HDR_FONT
#         cell.fill      = HDR_FILL
#         cell.alignment = CENTER
#         cell.border    = _thin_border()
#     ws3.row_dimensions[1].height = 18

#     for r_idx, (_, row) in enumerate(df.iterrows(), 2):
#         for c_idx, col in enumerate(raw_cols, 1):
#             val = row[col]
#             if val is None or (isinstance(val, float) and pd.isna(val)):
#                 val = ""
#             elif hasattr(val, "item"):
#                 val = val.item()
#             cell = ws3.cell(row=r_idx, column=c_idx, value=val)
#             cell.font      = DATA_FONT
#             cell.alignment = LEFT
#             cell.border    = _thin_border()

#     ws3.freeze_panes = "A2"
#     for c_idx in range(1, len(raw_cols) + 1):
#         ws3.column_dimensions[get_column_letter(c_idx)].width = 18

#     wb.save(output_path)
#     return output_path


# # ─────────────────────────────────────────────────────────────────────────────
# # SECTION 3 — MAIN
# # ─────────────────────────────────────────────────────────────────────────────

# def main():
#     # Resolve PDF path from CLI arg or use default
#     pdf_path = sys.argv[1] if len(sys.argv) > 1 else "Flight_planning_report.pdf"

#     print(f"[1/3] Extracting data from: {pdf_path}")
#     df = extract_flight_planning(pdf_path)

#     if df.empty:
#         print("ERROR: No records extracted. Check the PDF path and format.")
#         sys.exit(1)

#     print(f"      ✓ {len(df)} AWB rows extracted")

#     # Print a quick preview to console
#     print("\n[2/3] Extracted data preview:")
#     preview_cols = ["FLIGHT_NUM", "FLIGHT_DATE", "SLNO", "AWB_NUM",
#                     "LOCATION", "LOC_PCS", "GROSS_WGT", "CHG_WGT",
#                     "ORG", "DES", "SHC", "NOG"]
#     with pd.option_context("display.max_columns", None, "display.width", 200):
#         print(df[preview_cols].to_string(index=False))

#     print(f"\n      Totals → LOC_PCS: {df['LOC_PCS'].sum()}  "
#           f"GROSS_WGT: {df['GROSS_WGT'].sum()}  "
#           f"CHG_WGT: {df['CHG_WGT'].sum()}")

#     # Save Excel in the same directory as this script (always writable)
#     script_dir  = os.path.dirname(os.path.abspath(__file__))
#     output_path = os.path.join(script_dir, "flight_planning_output.xlsx")

#     print(f"\n[3/3] Writing Excel file: {output_path}")
#     _write_excel(df, output_path)
#     print(f"      ✓ Done — {output_path}")

#     return df


# if __name__ == "__main__":
#     main()