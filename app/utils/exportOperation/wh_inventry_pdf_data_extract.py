# """
# pdf_read_test.py 
# ================
# Extract Import Warehouse Inventory data from PDF → Excel. -> CAR MESSAGE

# Usage:
#     python pdf_read_test.py getjobid5529279.pdf

# Requirements:
#     pip install pdfplumber openpyxl pandas
# """

# import sys
# import os
# import re
# import pdfplumber
# import pandas as pd
# from openpyxl import load_workbook
# from openpyxl.styles import Font, PatternFill, Alignment, Border, Side
# from openpyxl.utils import get_column_letter


# # ── Exact column x-boundaries (calibrated from this PDF's character positions) ─
# # Each character is ~6px wide. Boundaries derived from coordinate analysis.
# #
# #  Column     x_start   x_end    Evidence from PDF
# #  AWB_NO        9        82     "0","9","8","-","4","9"... at x=9,15,21,27,33,39...
# #  HWB_NO      100       175     HWB chars at x=104,110,116,122,128,134,140,146,152,158,164,170
# #  MH          215       235     "M" or "H" at x=222
# #  STATUS      302       345     "R","C","F" / "D","L","V" at x=306,312,318
# #  PCS         365       390     digits at x=369,375,381
# #  WGT_CHG     438       458     digits at x=443,449 (sparse - only when value present)
# #  SHC         460       500     "H","E","A","S","P","X"... at x=464,470,476,482,488,494
# #  AGENT       510       540     "S","F","S" / "A","V","C" at x=520,526,532
# #  FLT_NO      545       585     "A","I","2","3","3","3" at x=549,555,561,567,573,579
# #  FLT_DATE    595       660     "2","5","-","F","E","B","-","2","6" at x=599,605,611,617,623,629,635,641,647

# COL_BOUNDS = [
#     ("AWB_NO",    9,    82),
#     ("HWB_NO",   100,  175),
#     ("MH",       215,  235),
#     ("STATUS",   302,  345),
#     ("PCS",      365,  390),
#     ("WGT_CHG",  438,  458),
#     ("SHC",      460,  500),
#     ("AGENT",    510,  540),
#     ("FLT_NO",   545,  585),
#     ("FLT_DATE", 595,  660),
# ]

# COLUMNS = [c[0] for c in COL_BOUNDS]

# # Lines to skip
# SKIP_PHRASES = [
#     "import warehouse inventory",
#     "from date", "to date",
#     "delhi", "mumbai", "chennai", "kolkata", "bangalore", "hyderabad",
#     "awb no", "hwb no", "m/h", "status", "wgt_chg", "flt no", "flt date",
#     "agent", "shc", "grand total", "day total",
# ]


# # ── Helpers ───────────────────────────────────────────────────────────────────

# def is_valid_awb(text: str) -> bool:
#     """AWB: 3 digits hyphen 7-8 digits  e.g. 098-31662105"""
#     return bool(re.match(r"^\d{3}-\d{7,8}$", (text or "").strip()))


# def is_skip_line(text: str) -> bool:
#     t = text.strip()
#     if not t:
#         return True
#     tl = t.lower()
#     if re.search(r"\d{2}-[a-zA-Z]{3}-\d{2,4}\s+\d{2}:\d{2}", t):
#         return True
#     for phrase in SKIP_PHRASES:
#         if phrase in tl:
#             return True
#     return False


# def chars_to_text(chars: list) -> str:
#     """Join individual character dicts (sorted by x) into a string."""
#     return "".join(c["text"] for c in sorted(chars, key=lambda c: c["x0"])).strip()


# def extract_cell_from_chars(chars: list, x0: float, x1: float) -> str:
#     """Extract text from characters whose x-position falls within [x0, x1]."""
#     in_range = [c for c in chars if c["x0"] >= x0 - 3 and c["x0"] <= x1 + 3]
#     return chars_to_text(in_range)


# # ── Core extraction ───────────────────────────────────────────────────────────

# def extract_inventory_pdf(pdf_path: str) -> pd.DataFrame:
#     rows = []

#     with pdfplumber.open(pdf_path) as pdf:
#         total = len(pdf.pages)

#         for page_num, page in enumerate(pdf.pages, start=1):
#             print(f"   Page {page_num}/{total}...", end="\r")

#             # Extract individual characters with position
#             chars = page.chars  # list of dicts: text, x0, x1, top, bottom, ...

#             if not chars:
#                 continue

#             # Group chars by line (y / top position, bucketed by 3pt)
#             line_map: dict = {}
#             for ch in chars:
#                 if not ch["text"].strip():
#                     continue
#                 y_key = round(ch["top"] / 3) * 3
#                 line_map.setdefault(y_key, []).append(ch)

#             # Process lines top → bottom
#             for y_key in sorted(line_map):
#                 line_chars = line_map[y_key]
#                 line_text  = chars_to_text(line_chars)

#                 if is_skip_line(line_text):
#                     continue

#                 # Extract each column by x-boundary
#                 row = {
#                     col: extract_cell_from_chars(line_chars, x0, x1)
#                     for col, x0, x1 in COL_BOUNDS
#                 }

#                 # Only keep rows with a valid AWB number
#                 if not is_valid_awb(row["AWB_NO"]):
#                     continue

#                 rows.append(row)

#     print()  # newline after progress
#     df = pd.DataFrame(rows, columns=COLUMNS)

#     # ── Type cleanup ──────────────────────────────────────────────────────────
#     df.replace("", pd.NA, inplace=True)

#     df["AWB_NO"]  = df["AWB_NO"].str.strip()
#     df["HWB_NO"]  = df["HWB_NO"].str.strip()
#     df["MH"]      = df["MH"].str.upper().str.strip()
#     df["STATUS"]  = df["STATUS"].str.upper().str.strip()
#     df["PCS"]     = pd.to_numeric(df["PCS"],     errors="coerce")
#     df["WGT_CHG"] = pd.to_numeric(df["WGT_CHG"], errors="coerce")
#     df["FLT_DATE"]= pd.to_datetime(df["FLT_DATE"], format="%d-%b-%y", errors="coerce")

#     df.reset_index(drop=True, inplace=True)
#     return df

































"""
export_inventory_extractor.py
==============================
Extracts Export Warehouse Inventory PDF → pandas DataFrame only.
No Excel output. Ready for DB pipeline.

Usage (standalone):
    python export_inventory_extractor.py getjobid5584045-export.pdf

Usage (as module):
    from export_inventory_extractor import extract_export_inventory
    df = extract_export_inventory("getjobid5584045-export.pdf")

DataFrame columns returned:
    CARRIER   | str  | Airline carrier code (e.g. AI, EK, LH)
    AWB       | str  | Air Waybill number (e.g. 098-30383500)
    STATUS    | str  | RCS / RCT / RCF / PRE / TFD
    DATETIME  | datetime | Receipt datetime (e.g. 2026-03-12 08:06:00)
    DESTN     | str  | Destination airport code (e.g. LHR, JFK)
    AGENT     | str  | Agent code (nullable)
    PCS       | int  | Pieces count
    WGT_CHG   | float| Chargeable weight (kg)
    WGT_GRS   | float| Gross weight (kg)
    VOL_MC    | float| Volume in cubic meters
    SHC_CODE  | str  | Special handling codes (e.g. GEN, VUN ELI, TRM PER)
    SOURCE_FILE| str | Original PDF filename (for traceability)
    EXTRACTED_AT | datetime | When this row was extracted
"""

import re
import os
import sys
from datetime import datetime

import pdfplumber
import pandas as pd


# ── Column x-boundaries (calibrated from character coordinate analysis) ────────
# Each tuple: (column_name, x_start, x_end)
# Based on actual PDF character positions — do not change unless PDF layout changes.
COL_BOUNDS = [
    ("AWB",       9,   82),
    ("STATUS",  148,  175),
    ("DATE",    193,  252),
    ("TIME",    253,  290),
    ("DESTN",   300,  330),
    ("AGENT",   344,  375),
    ("PCS",     390,  425),
    ("WGT_CHG", 450,  495),
    ("WGT_GRS", 510,  550),
    ("VOL_MC",  558,  595),
    ("SHC_CODE",593,  650),
]

# AWB format: 3digits-7or8digits with optional trailing P (e.g. 098-30329202P)
_AWB_RE = re.compile(r"^\d{3}-\d{7,8}P?$")

# Carrier header line pattern (no space between "Carrier" and code e.g. "CarrierAI")
_CARRIER_RE = re.compile(r"^Carrier\s*([A-Z0-9]{1,4})$", re.IGNORECASE)

# Lines to skip
_SKIP_RE = re.compile(
    r"(export\s+warehouse\s+inventory|from\s+date|to\s+date|"
    r"^awbstatustime|^count:|^total:|delhi|mumbai|chennai|"
    r"kolkata|bangalore|hyderabad)",
    re.IGNORECASE,
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _chars_to_text(chars: list) -> str:
    """Join chars sorted by x into a string."""
    return "".join(
        c["text"] for c in sorted(chars, key=lambda c: c["x0"])
    ).strip()


def _extract_cell(chars: list, x0: float, x1: float) -> str:
    """Extract text from chars whose x0 falls within [x0-3, x1+3]."""
    return _chars_to_text(
        [c for c in chars if x0 - 3 <= c["x0"] <= x1 + 3]
    )


def _is_valid_awb(text: str) -> bool:
    return bool(_AWB_RE.match((text or "").strip()))


# ── Main extractor ────────────────────────────────────────────────────────────

def extract_export_inventory(pdf_source) -> pd.DataFrame:
    """
    Extract all AWB rows from an Export Warehouse Inventory PDF.

    Parameters
    ----------
    pdf_source : str | Path | file-like object
        File path string/Path  OR  any file-like object with .read()
        e.g. FastAPI UploadFile.file, SpooledTemporaryFile, BytesIO.

    Returns
    -------
    pd.DataFrame  -  ready for DB insert. Empty DataFrame if no records.

    Raises
    ------
    FileNotFoundError  - if path string given but file does not exist.
    """
    import io

    if isinstance(pdf_source, (str, os.PathLike)):
        # ── File path supplied ─────────────────────────────────────────────
        if not os.path.exists(pdf_source):
            raise FileNotFoundError(f"PDF not found: {pdf_source}")
        source_file = os.path.basename(pdf_source)
        pdf_input   = pdf_source
    else:
        # ── File-like object: SpooledTemporaryFile, BytesIO, UploadFile.file
        _name       = getattr(pdf_source, "name", None) or "uploaded.pdf"
        source_file = os.path.basename(str(_name))
        pdf_input   = io.BytesIO(pdf_source.read())   # read once, wrap for seek

    extracted_at    = datetime.now()
    records         = []
    current_carrier = None

    with pdfplumber.open(pdf_input) as pdf:
        for page in pdf.pages:
            chars = page.chars
            if not chars:
                continue

            # ── Group characters into lines by y-position ──────────────────
            line_map: dict = {}
            for ch in chars:
                if not ch["text"].strip():
                    continue
                y_key = round(ch["top"] / 3) * 3
                line_map.setdefault(y_key, []).append(ch)

            # ── Process each line top → bottom ─────────────────────────────
            for y_key in sorted(line_map):
                line_chars = line_map[y_key]
                line_text  = _chars_to_text(line_chars)

                # Detect carrier header  e.g. "CarrierAI" or "Carrier EK"
                m = _CARRIER_RE.match(line_text)
                if m:
                    current_carrier = m.group(1).strip().upper()
                    continue

                # Skip non-data lines
                if _SKIP_RE.search(line_text):
                    continue

                # Extract each column by x-boundary
                row = {
                    col: _extract_cell(line_chars, x0, x1)
                    for col, x0, x1 in COL_BOUNDS
                }

                # Only keep rows with a valid AWB number
                if not _is_valid_awb(row["AWB"]):
                    continue

                row["CARRIER"]      = current_carrier
                row["SOURCE_FILE"]  = source_file
                row["EXTRACTED_AT"] = extracted_at
                records.append(row)

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # ── Type casting ──────────────────────────────────────────────────────────

    # String columns — strip whitespace, empty string → None
    for col in ["AWB", "CARRIER", "STATUS", "DESTN", "AGENT", "SHC_CODE"]:
        df[col] = df[col].str.strip().replace("", None)

    # Combine DATE + TIME → DATETIME
    df["DATETIME"] = pd.to_datetime(
        df["DATE"].str.strip() + " " + df["TIME"].str.strip(),
        format="%d-%b-%y %H:%M",
        errors="coerce",
    )
    df.drop(columns=["DATE", "TIME"], inplace=True)

    # Numeric columns
    df["PCS"]     = pd.to_numeric(df["PCS"],     errors="coerce").astype("Int64")
    df["WGT_CHG"] = pd.to_numeric(df["WGT_CHG"], errors="coerce")
    df["WGT_GRS"] = pd.to_numeric(df["WGT_GRS"], errors="coerce")
    df["VOL_MC"]  = pd.to_numeric(df["VOL_MC"],  errors="coerce")

    # Final column order
    df = df[[
        "CARRIER", "AWB", "STATUS", "DATETIME",
        "DESTN", "AGENT", "PCS", "WGT_CHG", "WGT_GRS",
        "VOL_MC", "SHC_CODE", "SOURCE_FILE", "EXTRACTED_AT",
    ]]


    df['AWB'] = clean_awb_field(df['AWB'])
    df['AWB'] = df['AWB'].apply(lambda x: x.zfill(11) if x and len(x) == 10 else x)
    df = df.reset_index(drop=True)
    # df.to_csv(f"clean_{source_file}.csv",index=False)
    return df


def clean_awb_field(awb_series: pd.Series) -> pd.Series:
    """Clean AWB — remove spaces, dash, trailing P"""
    import re as _re

    def _clean(val):
        if not val or str(val).strip().lower() == "nan":
            return None
        s = _re.sub(r"\s+", "", str(val).strip())   # remove all whitespace
        s = _re.sub(r"-+",   "-", s)                # collapse double dashes
        s = s.replace("-", "")                       # remove dash
        s = s.rstrip("P")                            # remove trailing P
        return s if s else None

    return awb_series.apply(_clean)


