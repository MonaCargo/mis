from typing import Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.base import APIResponseBase
from app.schemas.export_slot_file import ExportSlotFullResponse



class DockScanRequest(BaseModel):
    """Request schema for dock scan"""
    token_no: str
    truck_number: str
    truck_slot_from: datetime
    dock_number:str
    emp_id: Optional[str] = None  # Optional field
    
    class Config:
        from_attributes = True

class DockScanRead(BaseModel):
    truck_number:str
    is_dock_in: bool 
    is_dock_out:bool
    dock_out_date_time:Optional[datetime]
    dock_in_date_time: Optional[datetime] = None
    dock_number: Optional[str] = None
      

class DockScanResponse(APIResponseBase):
    """Response schema for dock scan"""
    data:DockScanRead
   
class DockOutResponse(APIResponseBase):
    """Response schema for dock scan"""
    data:DockScanRead

class RevertDockInRequest(BaseModel):
    token_no: str
    truck_number: str
    truck_slot_from: datetime
    
    class Config:
        from_attributes = True    

class DockInRevertResponse(APIResponseBase):
    "Response schema when revert the dock in process "    
    data:ExportSlotFullResponse

    class Config:
        from_attributes = True