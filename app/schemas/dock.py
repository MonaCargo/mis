from typing import List, Optional
from datetime import datetime
from pydantic import BaseModel, Field
from app.schemas.base import APIResponseBase
from app.schemas.export_slot_file import AWBEntryResponse, AWBSequenceResponse, ExportSlotFullResponse
from app.schemas.shared_export_slot_and_dock import AWBDockOperationSchema




class DockScanRequest(BaseModel):
    """Request schema for dock scan"""
    token_no: str
    truck_number: str
    truck_slot_from: datetime
    current_dock_number:str
    current_dock_in_by_device:str = None # it used to store thins info temporary that wghen forts scan save and dock operation created then I fill this info that by which device this dock locked.

    emp_id: Optional[str] = None  # Optional field
    
    class Config:
        from_attributes = True

class DockOutRequest(BaseModel):
    """Request schema for dock out"""
    token_no: str
    truck_number: str
    truck_slot_from: datetime
    dock_number:str
    dock_out_by_device:Optional[str] = None

    emp_id: Optional[str] = None  # Optional field
    
    class Config:
        from_attributes = True

# class DockScanRead(BaseModel):
#     truck_number:str
#     is_dock_in: bool 
#     is_dock_out:bool
#     dock_out_date_time:Optional[datetime]
#     dock_in_date_time: Optional[datetime] = None
#     dock_number: Optional[str] = None


class DockScanRead(BaseModel):
    truck_number: str
    current_is_dock_in: bool
    current_is_dock_out: bool
    current_dock_in_date_time: Optional[datetime] = None
    current_dock_out_date_time: Optional[datetime] = None
    current_dock_number: Optional[str] = None
    current_dock_in_by_device: Optional[str] = None

class Config:
    from_attributes = True


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
