# app/utils/exclusions.py

# ------------------------------
# GLOBAL EXCLUSION RULES
# ------------------------------

# Exact location matches
import re


EXCLUDED_LOCATIONS = {
    "GF_03", "GF_05", "GF_10", "IGF_1_A", "IGF_21_A"
}

# Location prefix exclusions
EXCLUDED_LOCATION_PREFIXES = (
    "ISR",
    "IUC",
    "TDP",
    "PI",
)

# SHC exclusions
EXCLUDED_SHC = {
    "PER",
    "VAL",
    "HUM",
    "DGR",
}

# IRR codes exclusions
EXCLUDED_IRR_CODES = {
    "SSPD",
    "FDCA",
}

# ⚠️⚠️ if you want to uase this utils into get data for print from oc merge table api then check it because it return two values
def is_excluded_with_reason(location: str, shc: str, irr_codes: str):
    """
    Returns (True/False, reason_string)
    """
    # --- LOCATION CHECK ---
    if location:
        # Extract prefix by splitting on '/' or ',' (assuming location format like IGF_76_C/1 or IGF_76_C, IGF_36_B/1)
        location_parts = [
            part.strip().upper()
            for part in re.split(r"[,/]", location)  # Split by both comma and slash
            if part.strip()
        ]

        for part in location_parts:
            # Check for exact match in excluded locations
            if part in (loc.upper() for loc in EXCLUDED_LOCATIONS):
                return True, f"Location exact match: {part}"

            # Check for prefix match in excluded location prefixes
            if any(part.startswith(prefix.upper()) for prefix in EXCLUDED_LOCATION_PREFIXES):
                return True, f"Location prefix match: {part}"

    # --- SHC CHECK ---
    if shc:
        value = str(shc).strip().upper()
        if value in EXCLUDED_SHC:
            return True, f"SHC excluded: {value}"

    # --- IRR CODE CHECK ---
    if irr_codes:
        irr_list = [x.strip().upper() for x in irr_codes.split("|")]
        for code in irr_list:
            if code in EXCLUDED_IRR_CODES:
                return True, f"IRR code excluded: {code}"

    return False, None


# def is_excluded(location: str, shc: str, irr_codes: str) -> bool:
#     """
#     Returns True if the record should be excluded based on:
#     - Location
#     - SHC
#     - IRR Codes
#     """
#     # --- LOCATION CHECK ---
#     if location:
#         prefix = str(location).split("/")[0].strip().upper()

#         if prefix in EXCLUDED_LOCATIONS:
#             return True

#         if prefix.startswith(EXCLUDED_LOCATION_PREFIXES):
#             return True

#     # --- SHC CHECK ---
#     if shc:
#         if str(shc).strip().upper() in EXCLUDED_SHC:
#             return True

#     # --- IRR CODES CHECK ---
#     if irr_codes:
#         irr_list = [x.strip().upper() for x in irr_codes.split("|")]
#         if any(code in EXCLUDED_IRR_CODES for code in irr_list):
#             return True

#     return False
