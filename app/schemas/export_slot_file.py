# from pydantic import BaseModel
# from typing import Optional
# from datetime import datetime  # ✅ import from Python stdlib

# class ExportSlotFileRecord(BaseModel):
#     company_name: str
#     warehouse: str
#     zone: str
#     token_no: Optional[str]
#     # aWB_no: Optional[str]
#     awb_no: Optional[float]
#     truck_number: Optional[str]
#     pcs: Optional[int]
#     status: Optional[str]
#     remarks: Optional[str]
#     cargo_type: Optional[str]
#     rescheduled: Optional[str]
#     rescheduled_by: Optional[str]
    
#     # ✅ Use Python's datetime type
#     truck_slot_from: Optional[datetime]
#     truck_in_date_time: Optional[datetime]

#     class Config:
#         from_attributes = True



# =================== AFTER NEW STRUCTURE DISCUSSION ===================

# schemas/export_slot.py

from pydantic import BaseModel, Field
from typing import List, Optional
from datetime import datetime

from app.schemas.base import APIResponseBase, Pagination

# ✅ NEW: Schema for AWB Sequence--------------------------
class AWBSequenceSchema(BaseModel):
    """Schema for AWB sequence entries"""
    seq_number: str
    seq_time: datetime
    
    class Config:
        from_attributes = True



class AWBEntry(BaseModel):
    awb_id: str
    pcs: int
    is_additional: bool = False  # ✅ Added this field
    sequences: List[AWBSequenceSchema]  # ✅ NEW: List of sequences
    
    class Config:
        from_attributes = True


class AWBSequenceResponse(BaseModel):
    """Response schema with ID for AWB sequence"""
    id: int
    awb_record_id: int 
    seq_number: str
    seq_time: datetime
    created_at: Optional[datetime] = None
    updated_at: Optional[datetime] = None
    
    class Config:
        from_attributes = True


class AWBEntryResponse(BaseModel):
    """Response schema for AWB with sequences (includes ID)"""
    id: int
    export_slot_id: int
    awb_id: str
    pcs: int
    is_additional: bool = False
    sequences: List[AWBSequenceResponse] = []
    
    class Config:
        from_attributes = True

class ExportSlotFileRecordSchema(BaseModel):
    company_name: str
    warehouse: str
    zone: str
    token_no: Optional[str]
    truck_number: Optional[str]
    status: Optional[str]
    remarks: Optional[str]
    cargo_type: Optional[str]
    rescheduled: Optional[str]
    rescheduled_by: Optional[str]
    truck_slot_from: Optional[datetime]
    truck_in_date_time: Optional[datetime]

       # ✅ New fields
    truck_out_date_time: Optional[datetime] = None
    dock_in_date_time: Optional[datetime] = None
    dock_out_date_time: Optional[datetime] = None
    is_truck_in: bool = False
    is_truck_out: bool = False
    is_dock_in: bool = False
    is_dock_out: bool = False
    dock_number: Optional[str] = ""

    awbList: List[AWBEntry]  # ✅ Now includes sequences

    class Config:
        from_attributes = True


class ExportSlotFullResponse(BaseModel):
    id: int
    company_name: str
    warehouse: str
    zone: str
    token_no: Optional[str]
    truck_number: Optional[str]
    status: Optional[str]
    remarks: Optional[str]
    cargo_type: Optional[str]
    rescheduled: Optional[str]
    rescheduled_by: Optional[str]
    truck_slot_from: Optional[datetime]
    truck_in_date_time: Optional[datetime]
    created_at: Optional[datetime]
    updated_at: Optional[datetime]

      # ✅ New fields
    truck_out_date_time: Optional[datetime] = None
    dock_in_date_time: Optional[datetime] = None
    dock_out_date_time: Optional[datetime] = None
    is_truck_in: bool = False      # ✅ changed
    is_truck_out: bool = False     # ✅ changed
    is_dock_in: bool = False       # ✅ changed
    is_dock_out: bool = False      # ✅ changed
    dock_number: Optional[str] = ""


    truck_in_by: Optional[str] = None
    truck_out_by: Optional[str] = None
    dock_in_by: Optional[str] = None
    dock_out_by: Optional[str] = None  

       

    awbList: List[AWBEntryResponse] = Field(alias="awbs", default=[])  # ✅ Map from 'awbs' to 'awbList'


    class Config:
        from_attributes = True
        populate_by_name = True  # Allow using field name in code





# ✅ Final API response schema for the GET endpoint
class ExportSlotFileListResponse(APIResponseBase):
    data: List[ExportSlotFullResponse]
    pagination: Pagination


class ExportSlotUpdateTruckInTimeRequest(BaseModel):
    truck_number: str
    token_no: str
    truck_slot_from: datetime
    emp_id: Optional[str]= None

    class Config:
        from_attributes = True    


class ExportSlotUpdateTruckOutTimeRequest(BaseModel):
    truck_number: str
    truck_slot_from: datetime  # ISO 8601 datetime, e.g., "2025-10-26T13:30:00Z"
    token_no: str
    emp_id: Optional[str] =None

    class Config:
        from_attributes = True





# ✅ NEW: Request schemas for adding sequences


class SequenceItem(BaseModel):
    seq_number: str
    seq_time: datetime

    class Config:
        from_attributes = True




class AddAWBSequenceRequest(BaseModel):
    """Request to add a sequence to an AWB OR Add extra awb"""
    truck_slot_from: datetime
    token_no: str
    truck_number: str
    awbList: List[AWBEntry]
    
    class Config:
        from_attributes = True


class AddAWBSequenceResponse(APIResponseBase):
    """Response to add a sequence to an AWB """
   
    data: List[SequenceItem]
    # data: List[AWBSequenceResponse]
    class Config:
        from_attributes = True



class ExportSlotDownloadResponse(BaseModel):
    """Simplified response for download without aliases"""
    id: int
    company_name: str
    warehouse: str
    zone: str
    token_no: Optional[str]
    truck_number: Optional[str]
    status: Optional[str]
    # ... include all other fields you need for download ...
    
    # Use the direct relationship name
    awbs: List[AWBEntryResponse] = []

    class Config:
        from_attributes = True

























































