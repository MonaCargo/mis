from typing import Optional

from pydantic import BaseModel

from app.schemas.base import APIResponseBase

class CarrierBulkUploadResponse(APIResponseBase):
    inserted: int
    skipped: int
    skipped_codes: list[str]
    pfx_skipped_non_numeric: dict[str, list[str]]  # carrier_code → bad pfx values