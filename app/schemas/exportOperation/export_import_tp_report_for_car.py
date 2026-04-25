from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime


# ── Response returned for each AWB row that was processed ──────────────────

class AwbSyncDetail(BaseModel):
    awb_no: str
    action: str          # "created" | "updated" | "skipped"
    reason: Optional[str] = None   # populated when action == "skipped"


# ── Top-level response ──────────────────────────────────────────────────────

class ExportTpXrayUploadResponse(BaseModel):
    message: str
    report_from_date: Optional[str] = None
    report_to_date: Optional[str] = None
    total_rows_in_file: int
    created: int
    updated: int
    skipped: int
    details: Optional[List[AwbSyncDetail]] = Field(default_factory=list)