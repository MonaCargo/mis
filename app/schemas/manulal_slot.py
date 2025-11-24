from datetime import datetime
from typing import Optional, List
from pydantic import BaseModel


class ExportManualSlotFileRecordBase(BaseModel):
    # Shipment metadata
    date: str
    time: str
    merge_datetime: datetime

    tc_no: str
    awb: str
    pcs: int
    agent_name: str     # Agent Namr equivalent to company name in export slot
    user: str

    # Truck/Dock timestamps (always UTC)
    truck_in_date_time: Optional[datetime] = None
    truck_out_date_time: Optional[datetime] = None
    dock_in_date_time: Optional[datetime] = None
    dock_out_date_time: Optional[datetime] = None

    # Status flags
    is_truck_in: bool = False
    is_truck_out: bool = False
    is_dock_in: bool = False
    is_dock_out: bool = False

    # Dock/Truck info
    dock_number: Optional[str] = None
    truck_in_by: Optional[str] = None
    truck_out_by: Optional[str] = None
    dock_in_by: Optional[str] = None
    dock_out_by: Optional[str] = None

    token_number: str
    truck_number: Optional[str] = None


class ExportManualSlotFileRecordResponse(ExportManualSlotFileRecordBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True   # allows SQLAlchemy model → Pydantic conversion


class Pagination(BaseModel):
    total: int
    limit: int
    offset: int


class ExportManualSlotFileListResponse(BaseModel):
    data: List[ExportManualSlotFileRecordResponse]
    pagination: Pagination


class TruckInRequest(BaseModel):
    token_no: str
    tc_no: str
    truck_number: str
    emp_id: str