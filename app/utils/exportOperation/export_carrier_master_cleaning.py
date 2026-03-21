import pandas as pd
import re
from typing import Any

def clean_carrier_excel(file_bytes: bytes) -> list[dict]:
    """
    Reads carrier Excel, cleans data, returns list of:
    {carrier_code, name, pfx_list: [str]}
    """
    df = pd.read_excel(file_bytes, dtype=str)

    # ── Normalize column names ─────────────────────────────────
    df.columns = [c.strip().lower().replace(" ", "_") for c in df.columns]
    # handles 'carrier code' → 'carrier_code'
    df.rename(columns={"carrier_code": "carrier_code"}, inplace=True)

    carriers = []
    seen_codes = set()

    for _, row in df.iterrows():
        carrier_code = str(row.get("carrier_code", "")).strip().upper()
        name = str(row.get("name", "")).strip().upper()
        raw_pfx = str(row.get("pfx", "")).strip()

        # ── Skip empty or invalid rows ─────────────────────────
        if not carrier_code or carrier_code == "NAN":
            continue
        if not name or name == "NAN":
            continue

        # ── Deduplicate carrier codes ──────────────────────────
        if carrier_code in seen_codes:
            continue
        seen_codes.add(carrier_code)

        # ── Parse pfx — split by comma, keep only numeric ─────
        pfx_list = []
        seen_pfx = set()
        if raw_pfx and raw_pfx != "NAN":
            for p in raw_pfx.split(","):
                p = p.strip()
                if re.fullmatch(r"\d+", p):       # numeric only
                    if p not in seen_pfx:          # no duplicates
                        seen_pfx.add(p)
                        pfx_list.append(p)

        carriers.append({
            "carrier_code": carrier_code,
            "name": name,
            "pfx_list": pfx_list,
        })

    return carriers