# shared_export_slot_and_dock.py
from __future__ import annotations
from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel

# ---------------- Seq Response ----------------
class AWBSequenceResponse(BaseModel):
    id: int
    awb_record_id: int
    seq_number: str
    dock_operation_id: Optional[int]
    seq_time: datetime
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


# ---------------- Dock Operation ----------------
class AWBDockOperationSchema(BaseModel):
    id: int
    dock_number: str
    dock_in_date_time: datetime
    dock_out_date_time: Optional[datetime] = None
    is_dock_in: bool
    is_dock_out: bool
    dock_in_by: Optional[str] = None
    dock_out_by: Optional[str] = None

    sequences: List[AWBSequenceResponse] = []         # now resolved
    # awbs: List["AWBEntryResponse"] = []               # forward reference ok

    class Config:
        from_attributes = True


# ---------------- AWB Response ----------------
class AWBEntryResponse(BaseModel):
    id: int
    export_slot_id: int
    awb_id: str
    pcs: int
    is_additional: bool = False

    sequences: List[AWBSequenceResponse] = []
    # dock_operations: List[AWBDockOperationSchema] = []

    class Config:
        from_attributes = True
