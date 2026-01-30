from datetime import datetime,timezone

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