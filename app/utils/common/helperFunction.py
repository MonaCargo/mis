from datetime import datetime,timezone

import pytz

from app.utils.common.enums import OriginSourceType


def get_utc_now() -> datetime:
    """Returns current UTC time with timezone info"""
    return datetime.now(timezone.utc)


# -----------------------------------

def detect_origin_source(header, shipment) -> OriginSourceType:
    """
    Detect where this shipment originated from.
    Priority:
    1. IRR
    2. IRM
    3. OC_MERGE (default)
    """

    if shipment.from_irr_table:
        return OriginSourceType.IRR

    if header.is_temp_irm_oc or header.temp_irm_oc_no:
        return OriginSourceType.IRM

    return OriginSourceType.OC_MERGE






# It is used to return UTC date time range based on one IST date string like (2026-02-03)
def convert_ist_day_to_utc_range_helper(date_str: str):
    if not date_str:
        return None, None

    ist = pytz.timezone("Asia/Kolkata")

    d = datetime.strptime(date_str, "%Y-%m-%d")

    start_ist = ist.localize(
        d.replace(hour=0, minute=0, second=0)
    )

    end_ist = ist.localize(
        d.replace(hour=23, minute=59, second=59, microsecond=999999)
    )

    return (
        start_ist.astimezone(pytz.UTC),
        end_ist.astimezone(pytz.UTC)
    )






import pytz
from datetime import datetime, date as date_type

# def ist_day_to_utc_range(d):
#     """IST calendar day → (utc_start, utc_end). Accepts 'YYYY-MM-DD' str or a date."""
#     ist = pytz.timezone("Asia/Kolkata")
#     if isinstance(d, str):
#         d = datetime.strptime(d, "%Y-%m-%d")
#     elif isinstance(d, date_type):
#         d = datetime(d.year, d.month, d.day)
#     start_ist = ist.localize(d.replace(hour=0, minute=0, second=0, microsecond=0))
#     end_ist = ist.localize(d.replace(hour=23, minute=59, second=59, microsecond=999999))
#     return start_ist.astimezone(pytz.UTC), end_ist.astimezone(pytz.UTC)

def ist_day_to_utc_range(date_str: str):
    if not date_str:
        return None, None

    ist = pytz.timezone("Asia/Kolkata")
    d = datetime.strptime(date_str, "%Y-%m-%d")

    start_ist = ist.localize(d.replace(hour=0, minute=0, second=0))
    end_ist = ist.localize(d.replace(hour=23, minute=59, second=59, microsecond=999999))

    return start_ist.astimezone(pytz.UTC), end_ist.astimezone(pytz.UTC)