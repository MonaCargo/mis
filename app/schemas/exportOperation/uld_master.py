# app/schemas/export_uld.py
"""
Pydantic schemas for Export ULD endpoints.
"""

from datetime import datetime
from typing import Optional, List

from pydantic import BaseModel, Field, field_validator, ConfigDict

from app.utils.exportOperation.validator.uld_pattern_validator import validate_uld_no


# Allowed carrier codes – kept here as a simple whitelist.
# Move to DB / config if it needs to be dynamic.
# ALLOWED_CARRIERS = {
#     "AI", "LH", "EK", "QR", "SQ", "BA", "TK", "CX",
# }


class ExportUldCreate(BaseModel):
    """Body of POST /export-ulds"""

    uld_no: str = Field(..., min_length=4, max_length=25, description="ULD number, e.g. AKE1234AI")
    carrier: str = Field(..., min_length=2, max_length=20, description="Carrier code, e.g. AI")
    remarks: Optional[str] = Field(None, max_length=500)  

    # uld_type is optional in the request – if supplied we still verify it
    # matches the pattern-derived type. Otherwise we derive it on the server.
    uld_type: Optional[str] = Field(None, max_length=10)

    @field_validator("uld_no")
    @classmethod
    def _validate_uld_no(cls, v: str) -> str:
        normalised = v.strip().upper()
        result = validate_uld_no(normalised)
        if not result.is_valid:
            # Surfaced as a 422 with a clear message
            raise ValueError(result.reason or "Invalid ULD number.")
        return normalised

    @field_validator("carrier")
    @classmethod
    def _validate_carrier(cls, v: str) -> str:
        normalised = v.strip().upper()
        # if normalised not in ALLOWED_CARRIERS:
        #     raise ValueError(
        #         f"Carrier '{normalised}' is not allowed. "
        #         f"Allowed: {', '.join(sorted(ALLOWED_CARRIERS))}."
        #     )
        return normalised


class ExportUldUpdate(BaseModel):
    """Body of PATCH /export-ulds/{id} – all fields optional."""

    is_active: Optional[bool] = None
    is_available: Optional[bool] = None
    carrier: Optional[str] = Field(None, min_length=2, max_length=20)

    @field_validator("carrier")
    @classmethod
    def _validate_carrier(cls, v: Optional[str]) -> Optional[str]:
        if v is None:
            return v
        normalised = v.strip().upper()
        # if normalised not in ALLOWED_CARRIERS:
        #     raise ValueError(f"Carrier '{normalised}' is not allowed.")
        return normalised


class ExportUldRead(BaseModel):
    """Response shape for a single ULD record."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    uld_no: str
    carrier: str
    uld_type: Optional[str]
    is_active: bool
    is_available: bool
    created_at: datetime
    updated_at: datetime
    created_by: Optional[str] = None
    updated_by: Optional[str] = None


class ExportUldListResponse(BaseModel):
    """Paginated list response."""

    items: List[ExportUldRead]
    total: int
    page: int
    page_size: int




class ChangeCarrierBody(BaseModel):
    carrier: str = Field(..., min_length=2, max_length=20)
    remarks: Optional[str] = Field(None, max_length=500)