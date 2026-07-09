"""
app/common/airline_master.py

Single source of truth for airline identity and PAX / CAO (Passenger vs
Freighter) classification, shared by every import digital report.

IMPORTANT: category (PAX / CAO) ALWAYS comes from this master + the resolution
rules below — NEVER from the segregation report's flight_status column.

Public API:
    resolve_airline(flight_no, dest) -> AirlineInfo(key, name, category)
    extract_airline_code(flight_no)  -> str
    AIRLINE_MASTER, REPORT_AIRLINE_ORDER   (for report row ordering)

Both the airline-pivot segregation report and the shift-based operations
dashboard import from here, so the classification can never drift between them.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal

Category = Literal["PAX", "CAO"]


@dataclass(frozen=True)
class AirlineInfo:
    key: str        # grouping key: 'AI_DEL', 'AI_TP', 'BONDED', 'LH_CAO', a code, or 'Others'
    name: str
    category: Category


# (airline_code, airline_name, category)  category: PAX | CAO
# Source of truth: airline_name_code_and_category.xlsx (hardcoded here).
AIRLINE_MASTER: list[tuple[str, str, Category]] = [
    ("AI",  "AIR INDIA ( DELHI )",          "PAX"),   # AI/IX + dest=DEL
    ("AI",  "AIR INDIA ( TP )",             "PAX"),   # AI/IX + dest≠DEL — handled in code
    ("DR",  "AIR SHAGOON",                  "CAO"),
    ("D7",  "AIRASIA X BERHAD",             "PAX"),
    ("NH",  "ALL NIPPON AIRWAYS",           "PAX"),
    ("B2",  "BELAVIA-BELARUSIAN",           "PAX"),
    ("B3",  "BHUTAN",                       "PAX"),
    ("BG",  "BIMAN BANGLADESH",             "PAX"),
    ("BZ",  "BLUE DART",                    "PAX"),
    ("X6",  "CHALLENGE AIR CARGO",          "CAO"),
    ("CH",  "CHALLENGE AIR CARGO",          "CAO"),
    ("GI",  "CHINA CENTRAL LONG HAO",       "CAO"),
    ("MS",  "EGYPT AIR",                    "PAX"),
    ("EK",  "EMIRATES",                     "PAX"),
    ("EY",  "ETIHAD  AIRWAYS",              "PAX"),
    ("AY",  "FINNAIR",                      "PAX"),
    ("RH",  "HONG KONG AIR CARGO",          "CAO"),
    ("MR",  "HUNNU AIR",                    "PAX"),
    ("AZ",  "ITA AIRWAYS",                  "PAX"),
    ("RQ",  "KAM AIR",                      "PAX"),
    ("LH",  "LUFTHANSA",                    "PAX"),
    ("LH_CAO", "LUFTHANSA",                 "CAO"),   # LH8370 + code 3S → LH Freighter
    ("W5",  "MAHAN AIR",                    "PAX"),
    ("C6",  "MY FREIGHTER",                 "CAO"),
    ("8M",  "MYANMAR AIRWAYS",              "PAX"),
    ("6P",  "PRADHAAN AIR EXPRESS PVT LTD", "PAX"),
    ("OV",  "SALAM AIR",                    "PAX"),
    ("7L",  "SILK WAY WEST",                "CAO"),
    ("SQ",  "SINGAPORE",                    "PAX"),
    ("SH",  "SOLITAIR AVIATION SERVICE",    "CAO"),
    ("SZ",  "SOMON AIR",                    "PAX"),
    ("SG",  "SPICE JET",                    "PAX"),
    ("UL",  "SRI LANKAN",                   "PAX"),
    ("Y8",  "SUPARNA",                      "CAO"),
    ("LX",  "SWISS",                        "PAX"),
    ("XJ",  "THAI AIRASIA X",               "PAX"),
    ("TG",  "THAI AIRWAYS",                 "PAX"),
    ("HT",  "TIANJIN AIR CARGO",            "CAO"),
    ("VJ",  "VIETJET AIR",                  "PAX"),
    ("VN",  "VIETNAM",                      "PAX"),
    ("YG",  "YTO CARGO",                    "CAO"),
    ("JG",  "JIANGSU JINGDONG CARGO",       "CAO"),
    ("PXX", "PO Mail",                      "PAX"),   # flight_no carrier code starts with P
    ("TS",  "AIR TRANSAT",                  "CAO"),
    ("VG",  "FLY VAAYU",                    "CAO"),
    ("BONDED", "BONDED TRUCK",              "PAX"),   # flight_no ending in 'T' → under PAX
]

OTHERS_NAME: str = "OTHERS"
OTHERS_CATEGORY: Category = "PAX"

# Flight-number-specific overrides (checked before code resolution)
FLIGHT_NO_OVERRIDES: dict[str, AirlineInfo] = {
    "AZ0770": AirlineInfo("LH", "LUFTHANSA", "PAX"),
    "LH8370": AirlineInfo("LH_CAO", "LUFTHANSA", "CAO"),
}

AIR_INDIA_CODES = frozenset({"AI", "IX"})
LH_FREIGHTER_CODES = frozenset({"3S"})

# Fast lookup: code → (name, category)  [AI/IX and special keys handled separately]
_CODE_TO_INFO: dict[str, tuple[str, Category]] = {}
for _code, _name, _cat in AIRLINE_MASTER:
    if _code == "AI":
        continue                       # AI resolved at row level (Delhi vs TP)
    if _code in ("LH_CAO", "BONDED"):
        continue                       # resolved via special rules
    _CODE_TO_INFO.setdefault(_code, (_name, _cat))

# Ordered, de-duplicated list for report rows
REPORT_AIRLINE_ORDER: list[tuple[str, str, Category]] = []
_seen: set[tuple[str, str, Category]] = set()
for _entry in AIRLINE_MASTER:
    if _entry not in _seen:
        REPORT_AIRLINE_ORDER.append(_entry)
        _seen.add(_entry)


def extract_airline_code(flight_no: str) -> str:
    """
    Airline code from a flight number:
    - If the alphabetic carrier prefix starts with 'P' → 'PXX' (PO Mail).
    - Otherwise → first 2 characters as the IATA carrier code.
    """
    if not flight_no:
        return ""
    fn = str(flight_no).strip().upper()
    if fn and fn[0] == "P":
        return "PXX"
    return fn[:2]


def resolve_airline(flight_no: str, dest: str) -> AirlineInfo:
    """
    Resolve a flight to (key, name, category). Category always from master/rules.

    Resolution order (first match wins):
      1. flight_no ends with 'T'  → Bonded Truck (PAX)
      2. exact flight_no override → AZ0770 → LH PAX, LH8370 → LH CAO
      3. code is 3S               → Lufthansa Freighter (CAO)
      4. code is AI or IX         → Air India, split DEL vs TP
      5. code in master           → that airline
      6. otherwise                → Others (PAX)
    """
    fn = str(flight_no).strip().upper() if flight_no else ""

    if fn.endswith("T"):
        return AirlineInfo("BONDED", "BONDED TRUCK", "PAX")

    if fn in FLIGHT_NO_OVERRIDES:
        return FLIGHT_NO_OVERRIDES[fn]

    code = extract_airline_code(fn)

    if code in LH_FREIGHTER_CODES:
        return AirlineInfo("LH_CAO", "LUFTHANSA", "CAO")

    if code in AIR_INDIA_CODES:
        if str(dest).strip().upper() == "DEL":
            return AirlineInfo("AI_DEL", "AIR INDIA ( DELHI )", "PAX")
        return AirlineInfo("AI_TP", "AIR INDIA ( TP )", "PAX")

    if code in _CODE_TO_INFO:
        name, cat = _CODE_TO_INFO[code]
        return AirlineInfo(code, name, cat)

    return AirlineInfo("Others", OTHERS_NAME, OTHERS_CATEGORY)