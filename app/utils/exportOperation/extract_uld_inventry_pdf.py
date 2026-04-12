# --------------------------------------------------------------
"""
uld_stock_extractor.py
======================
Extracts ULD Stock Summary PDF → pandas DataFrame.
No Excel output. Ready for DB pipeline.

Usage (standalone):
    python uld_stock_extractor.py getjobid5717823-1-5.pdf

Usage (as module):
    from uld_stock_extractor import extract_uld_stock
    df = extract_uld_stock("getjobid5717823-1-5.pdf")

DataFrame columns returned:
    SL_NO        | int      | Serial number within each ULD-type section
    ULD_TYPE     | str      | ULD type code (e.g. PAG, PAJ, PAV, PKC, PLA, PLB, PMC)
    ULD_NUMBER   | str      | Full ULD number (e.g. PAG03580AI)
    CARRIER      | str      | Carrier code from PDF header "Carrier : AI" — same for all rows
    DATETIME     | datetime | ULD date and time (e.g. 2026-03-26 13:59:00)
    SOURCE_FILE  | str      | Original PDF filename (for traceability)
    EXTRACTED_AT | datetime | When this row was extracted
"""

import re
import os
import sys
from datetime import datetime

import pdfplumber
import pandas as pd


# ── Column x-boundaries (calibrated from character coordinate analysis) ────────
# PDF layout (all pages share same column layout):
#   SL_NO      : x ~189–215  (1–3 digit number, right-aligned around x=201)
#   ULD_NUMBER : x ~279–345  (e.g. PAG03580AI, always starts at x=279)
#   DATETIME   : x ~396–500  (DD-MON-YYYY HH:MM)
COL_BOUNDS = [
    ("SL_NO",      180, 220),
    ("ULD_NUMBER", 270, 360),
    ("DATE",       390, 463),   # DD-MON-YYYY ends at ~x=462
    ("TIME",       466, 500),   # HH:MM starts at ~x=468
]

# ULD Number pattern: 3-letter type + digits + 1-2 letter carrier code
# e.g. PAG03580AI, PAG15786R7, PAJ0308IC, PKC11338R7, PLA25164R9
_ULD_RE = re.compile(r"^[A-Z]{3}\d+[A-Z0-9]{1,3}$")

# ULD Type header line: "ULDType:PAG"  (chars are concatenated, no spaces)
_ULD_TYPE_RE = re.compile(r"ULDType:?\s*([A-Z]{3})", re.IGNORECASE)

# Carrier header line on page 1: "Carrier:AI" (chars concatenated by line parser)
# Matches both "Carrier:AI" and "Carrier : AI" after concatenation
_CARRIER_HDR_RE = re.compile(r"Carrier\s*:\s*([A-Z0-9]{1,4})", re.IGNORECASE)

# Lines to skip (headers, footers, column titles, summary lines)
# Note: "Carrier" line is NOT skipped — we read it first, then skip it
_SKIP_RE = re.compile(
    r"(ULDStockSummary|SL\.No\.|ULDNumber|ULDDateandTime|No\.OfULD:|Date\s*:)",
    re.IGNORECASE,
)


# ── Internal helpers ──────────────────────────────────────────────────────────

def _chars_to_text(chars: list) -> str:
    """Join chars sorted by x0 into a stripped string."""
    return "".join(
        c["text"] for c in sorted(chars, key=lambda c: c["x0"])
    ).strip()


def _extract_cell(chars: list, x0: float, x1: float) -> str:
    """Extract text from chars whose x0 falls within [x0-3, x1+3]."""
    return _chars_to_text(
        [c for c in chars if x0 - 3 <= c["x0"] <= x1 + 3]
    )


def _is_valid_uld(text: str) -> bool:
    """Return True if text looks like a ULD number."""
    return bool(_ULD_RE.match((text or "").strip()))


# ── Main extractor ────────────────────────────────────────────────────────────

def extract_uld_stock(pdf_source) -> pd.DataFrame:
    """
    Extract all ULD rows from a ULD Stock Summary PDF.

    The carrier code is read once from the document header line
    "Carrier : AI" on page 1 and applied to every row — it is a
    document-level attribute, not per-ULD.

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
        if not os.path.exists(pdf_source):
            raise FileNotFoundError(f"PDF not found: {pdf_source}")
        source_file = os.path.basename(pdf_source)
        pdf_input   = pdf_source
    else:
        _name       = getattr(pdf_source, "name", None) or "uploaded.pdf"
        source_file = os.path.basename(str(_name))
        pdf_input   = io.BytesIO(pdf_source.read())

    extracted_at     = datetime.now()
    records          = []
    current_uld_type = None
    carrier          = None   # read once from page-1 header; same for all rows

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

                # ── Carrier header (page 1 only, but safe to check all pages)
                # "Carrier : AI" — the carrier code sits at x~117-130, far left of "Date"
                # We detect the line by text, then extract only the left portion by x-bound
                if carrier is None and "Carrier" in line_text:
                    # Extract chars in the Carrier label+value zone only (x < 200)
                    carrier_chars = [c for c in line_chars if c["x0"] < 200]
                    carrier_text  = _chars_to_text(carrier_chars)
                    m = _CARRIER_HDR_RE.search(carrier_text)
                    if m:
                        carrier = m.group(1).strip().upper()
                        continue   # this line is a header — don't process as data

                # ── ULD Type header e.g. "ULDType:PAG"
                m = _ULD_TYPE_RE.search(line_text)
                if m:
                    current_uld_type = m.group(1).strip().upper()
                    continue

                # ── Skip non-data lines
                if _SKIP_RE.search(line_text):
                    continue

                # ── Extract each column by x-boundary
                row = {
                    col: _extract_cell(line_chars, x0, x1)
                    for col, x0, x1 in COL_BOUNDS
                }

                # Only keep rows with a valid ULD number
                if not _is_valid_uld(row["ULD_NUMBER"]):
                    continue

                row["ULD_TYPE"]     = current_uld_type
                row["CARRIER"]      = carrier          # document-level, not per-ULD
                row["SOURCE_FILE"]  = source_file
                row["EXTRACTED_AT"] = extracted_at
                records.append(row)

    if not records:
        return pd.DataFrame()

    df = pd.DataFrame(records)

    # ── Type casting ──────────────────────────────────────────────────────────

    # String columns — strip & empty → None
    for col in ["ULD_NUMBER", "ULD_TYPE", "CARRIER"]:
        df[col] = df[col].str.strip().replace("", None)

    # Serial number
    df["SL_NO"] = pd.to_numeric(df["SL_NO"], errors="coerce").astype("Int64")

    # Combine DATE + TIME → DATETIME
    df["DATETIME"] = pd.to_datetime(
        df["DATE"].str.strip() + " " + df["TIME"].str.strip(),
        format="%d-%b-%Y %H:%M",
        errors="coerce",
    )
    df.drop(columns=["DATE", "TIME"], inplace=True)

    # Final column order
    df = df[[
        "SL_NO", "ULD_TYPE", "ULD_NUMBER", "CARRIER",
        "DATETIME", "SOURCE_FILE", "EXTRACTED_AT",
    ]]

    df = df.reset_index(drop=True)
    return df


# ── CLI entry point ───────────────────────────────────────────────────────────

if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python uld_stock_extractor.py <path_to_pdf>")
        sys.exit(1)

    pdf_path = sys.argv[1]
    df = extract_uld_stock(pdf_path)

    if df.empty:
        print("No ULD records extracted.")
    else:
        print(f"\nExtracted {len(df)} ULD records.\n")
        print(df.to_string(index=False))

        csv_path = os.path.splitext(os.path.basename(pdf_path))[0] + "_extracted.csv"
        df.to_csv(csv_path, index=False)
        print(f"\nSaved to: {csv_path}")