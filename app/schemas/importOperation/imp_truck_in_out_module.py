from pydantic import BaseModel, Field
from datetime import datetime
from typing import Any, List, Optional


class GatePassCheckRequest(BaseModel):
    gate_pass_no: str = Field(..., max_length=100, description="Gate pass number to validate")
    current_truck_visit_id: Optional[int] = None


# class GatePassCheckResponse(BaseModel):
#     valid: bool
#     message: str
#     gate_pass_no: Optional[str] = None
#     agent: Optional[str] = None
#     consignee: Optional[str] = None
#     pcs: Optional[int] = None
#     grg_wt: Optional[float] = None
#     issued_date: Optional[datetime] = None
#     gate_pass_released_by: Optional[str] = None

class GatePassCheckResponse(BaseModel):
    valid: bool
    message: str
    gate_pass_no: Optional[str] = None
    agent: Optional[str] = None
    consignee: Optional[str] = None
    pcs: Optional[int] = None    # it represent available pcs for booking
    total_pcs:Optional[int] = None
    grg_wt: Optional[float] = None
    issued_date: Optional[datetime] = None
    gate_pass_released_by: Optional[str] = None
    # NEW
    final_delivery_datetime: Optional[datetime] = None
    final_delivery_by_person: Optional[str] = None
    
    unloading_from_lift_zone_datetime: datetime | None = None

    gate_pass_end_datetime: Optional[datetime] = None
    drop_dlv_zone: Optional[str] = None
    lift_out_zone: Optional[str] = None    
    dlv_zone_from_irr: Optional[str] = None     
    is_hold:bool = False
    Info:Optional[str] = None



class TruckStagingRequest(BaseModel):
    truck_number: str = Field(..., max_length=20)
    driver_name: Optional[str] = None
    driver_contact: Optional[str] = None
    gate_pass_no: str = Field(..., max_length=100)


class TruckStagingResponse(BaseModel):
    success: bool
    message: str
    id: int
    truck_number: str
    gate_pass_no: str
    driver_name: Optional[str] = None
    driver_contact: Optional[str] = None


# Add to existing SaveStagingToTruckVisitResponse:
class SaveStagingToTruckVisitResponse(BaseModel):
    success: bool
    truck_visit_id: int
    truck_number: str
    token_number: str
    queue_no: Optional[str] = None      # ← new
    is_queued: bool = False             # ← new
    assigned_gate_passes: List[str]
    message: str

# New schemas:
class PromoteQueueRequest(BaseModel):
    truck_visit_id: int
    emp_id: str
    device_id: Optional[str] = None

class PromoteQueueResponse(BaseModel):
    success: bool
    truck_visit_id: int
    queue_no: Optional[str]
    truck_number: str
    token_no: Optional[str]
    truck_in_date_time: str
    message: str

class CancelQueueRequest(BaseModel):
    truck_visit_id: int
    emp_id: str
    remarks: Optional[str] = None

class CancelQueueResponse(BaseModel):
    success: bool
    truck_visit_id: int
    queue_no: Optional[str]
    truck_number: str
    message: str

class QueueSearchResponse(BaseModel):
    success: bool
    truck_visit_id: int
    queue_no: Optional[str]
    truck_number: str
    driver_name: Optional[str]
    driver_contact: Optional[str]
    token_no: Optional[str]
    queued_at: Optional[datetime]
    queued_by: Optional[str]
    status: str
    gate_passes: List[dict]

class GatePassReassignRequest(BaseModel):
    gate_pass_no: str
    from_truck_visit_id: int
    to_truck_visit_id: int
    emp_id: str
    remarks: Optional[str] = None


class GatePassReassignResponse(BaseModel):
    success: bool
    gate_pass_no: str
    from_truck_visit_id: int
    to_truck_visit_id: int
    remaining_pcs: int
    message: str

class GatePassOutRequest(BaseModel):
    truck_visit_id: int
    gate_pass_no: str
    loaded_pcs: int
    emp_id: str
    device_id: Optional[str] = None


class GatePassOutResponse(BaseModel):
    success: bool
    truck_visit_id: int
    gate_pass_no: str
    loaded_pcs: int
    remaining_pcs: int
    status: str
    message: str


class TruckOutRequest(BaseModel):
    truck_visit_id: int
    emp_id: str
    device_id: Optional[str] = None


class TruckOutResponse(BaseModel):
    success: bool
    truck_visit_id: int
    truck_number: str | None = None   
    message: str



class GatePassDetail(BaseModel):
    gate_pass_no: str
    awb: Optional[str] = None
    hawb: Optional[str] = None
    pcs: int
    pcs_remaining: int
    pcs_loaded: int
    assigned_time: datetime
    assigned_by: str
    gate_pass_out_time: Optional[datetime] = None
    gate_pass_out_by: Optional[str] = None
    assigned_truck_visit_id: int
    is_active_assignment: bool
    


class TruckListItem(BaseModel):
    truck_visit_id: int
    truck_number: str
    driver_name: Optional[str]
    driver_contact: Optional[str]
    truck_in_date_time: Optional[datetime] = None
    truck_out_date_time: Optional[datetime] = None
    token_no : Optional[str]
    status: Optional[str] = None
    gate_passes: List[GatePassDetail]



class TruckListResponse(BaseModel):
    success: bool
    count: int
    date: str
    trucks: List[TruckListItem]
    message: str




class TruckSearchResultItem(BaseModel):
    gp_no: str
    gp_status: Optional[str] = None
    awb: Optional[str] = None
    hawb: Optional[str] = None
    pcs: Optional[int] = None
    pcs_remaining: Optional[int] = None
    pcs_loaded: Optional[int] = None
    weight_kgs: Optional[float] = None
    chg_weight_kgs: Optional[float] = None
    agent: Optional[str] = None
    consignee: Optional[str] = None
    gp_issued_datetime: Optional[datetime] = None
    gp_end_datetime: Optional[datetime] = None
    drop_dlv_zone: Optional[str] = None
    final_delivery_datetime: Optional[datetime] = None
    truck_visit_id: Optional[int] = None
    truck_no: Optional[str] = None
    token: Optional[str] = None
    queue_no: Optional[str] = None
    queued_at: Optional[datetime] = None  
    driver: Optional[str] = None
    driver_contact: Optional[str] = None
    truck_status: Optional[str] = None
    truck_in: Optional[datetime] = None
    truck_out: Optional[datetime] = None
    assigned_time: Optional[datetime] = None
    assigned_by: Optional[str] = None
    is_active: Optional[bool] = None
    dlv_zone_from_irr: Optional[str] = None   # ← NEW FIELD

class TruckSearchResponse(BaseModel):
    success: bool
    count: int
    results: List[TruckSearchResultItem]









class QueueStatusMessage(BaseModel):
    type: str        # "trucked_in" | "cancelled"
    title: str
    detail: str

class TruckSearchResponse(BaseModel):
    success: bool
    count: int
    results: List[TruckSearchResultItem]
    queue_status_message: Optional[QueueStatusMessage] = None




class QueuedTruckListItem(BaseModel):
    truck_visit_id: int
    truck_number: str
    driver_name: Optional[str]
    driver_contact: Optional[str]
    token_no: Optional[str]
    status: Optional[str] = None
    queue_no: Optional[str] = None
    queued_at: Optional[datetime] = None
    queued_by: Optional[str] = None
    gate_passes: List[GatePassDetail]

class QueuedTruckListResponse(BaseModel):
    success: bool
    count: int
    date: str
    trucks: List[QueuedTruckListItem]
    message: str



class TruckOutSearchGatePass(BaseModel):
    gate_pass_no: str
    awb: Optional[str] = None
    hawb: Optional[str] = None
    pcs: int
    pcs_loaded: int
    pcs_remaining: int
    agent: Optional[str] = None
    consignee: Optional[str] = None
    assigned_time: Optional[datetime] = None
    assigned_by_name: Optional[str] = None  
    assigned_by: Optional[str] = None
    gate_pass_out_time: Optional[datetime] = None
    gate_pass_out_by: Optional[str] = None
    gate_pass_out_by_name: Optional[str] = None
    is_active_assignment: bool

    final_delivery_datetime: Optional[datetime] = None
    storage_charge: Optional[float] = None
    challan_no: Optional[str] = None


class TruckOutSearchResponse(BaseModel):
    success: bool
    truck_visit_id: int
    truck_number: str | None =None
    visit_type: str                           # ← NEW: "TRUCK" | "BY_HAND"
    driver_name: Optional[str]
    driver_contact: Optional[str]
    token_no: Optional[str]
    status: str
    queued_at: Optional[datetime] = None  
    truck_in_date_time: Optional[datetime]
    truck_out_date_time: Optional[datetime]
    truck_in_by: Optional[str]
    truck_in_by_name: Optional[str]
    truck_out_by: Optional[str]
    truck_out_by_name: Optional[str]
    workflow_status: str
    pending_gp_count: int
    completed_gp_count: int
    gate_passes: List[Any]
    message: str



#  ================== add more gp to trucks =========================

class AddMoreGpItem(BaseModel):
    gate_pass_no: str


class AddMoreGpRequest(BaseModel):
    truck_visit_id: int
    gate_passes: List[AddMoreGpItem]
    emp_id: str
    remarks: Optional[str] = None


class AddMoreGpResultItem(BaseModel):
    gate_pass_no: str
    success: bool
    message: str
    pcs_assigned: Optional[int] = None


class AddMoreGpResponse(BaseModel):
    success: bool
    truck_visit_id: int
    truck_number: str | None = None
    added_count: int
    skipped_count: int
    results: List[AddMoreGpResultItem]
    message: str   


class TruckCounts(BaseModel):
    pending: int
    out: int


class TruckListResponseforListType(BaseModel):
    success: bool
    date: str
    list_type: str
    count: int
    counts: TruckCounts                # ← NEW
    trucks: List[Any]                  # or your TruckItem type
    message: str


class ByHandPickupRequest(BaseModel):
    person_name: str = Field(..., min_length=1, max_length=100)
    person_contact: Optional[str] = Field(None, max_length=20)
    gate_pass_nos: List[str] = Field(..., min_items=1)
    emp_id: str
    device_id: Optional[str] = None
    remarks: Optional[str] = None


class ByHandPickupResponse(BaseModel):
    success: bool
    truck_visit_id: int
    token_no: str
    person_name: str
    visit_type: str
    assigned_gate_passes: List[str]
    message: str




class SaveGpChargeRequest(BaseModel):
    truck_visit_id: int
    gate_pass_no: str
    storage_charge: float
    challan_no: str
    remarks: Optional[str] = None
    emp_id: Optional[str] = None

class CcTruckOutRequest(BaseModel):
    truck_visit_id: int
    process_truck_out: bool          # the Yes/No
    emp_id: Optional[str] = None
    device_id: Optional[str] = None

class CcClearChargesRequest(BaseModel):
    truck_visit_id: int
    emp_id: Optional[str] = None



class ConfirmGpCompleteRequest(BaseModel):
    truck_visit_id: int
    gate_pass_no: str