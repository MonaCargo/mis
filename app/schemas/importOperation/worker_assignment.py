# app/schemas/worker_assignment_schema.py
from typing import Any, List, Optional
from pydantic import BaseModel, Field
from datetime import date, datetime

from app.schemas.base import APIResponseBase

class WorkerAssignmentRequest(BaseModel):
    date: date  # format YYYY-MM-DD from frontend


class WorkerAssignmentResponseForWorker(BaseModel):
    id: int
    igp_no: Optional[str]= None
    temp_irm_oc_no: Optional[str]= None
    is_temp_irm_oc: Optional[bool]= False

    # igp_print_date_time: Optional[datetime]
    # flight_no: Optional[str]
    awb_no: Optional[str]
    hawb: Optional[str]
    # flight_date: Optional[datetime]
    no_of_pc: Optional[int]
    weight_in_kgs: Optional[float]
    chg_wgt_in_kg: Optional[float]
    
    location: Optional[str]
    oc_no: str
    irregularity_remarks: Optional[str]
    # pd_in_time: Optional[datetime]
    # no_of_pc_recd: Optional[int]
    # verified_by: Optional[str]
    agent_name: Optional[str]
    customer_name: Optional[str]
    release_zone: Optional[str]
    # is_printed: Optional[bool]
    shc: Optional[str]
    irr_codes: Optional[str]
    integrate_date_time: Optional[datetime]
    gate_pass_no: Optional[str]
    gate_pass_issued_date_time_combo: Optional[datetime]
    gate_pass_end_datetime: Optional[datetime]
    from_irr_table: bool
    assigned_person: Optional[str]
    assigned_person_datetime: Optional[datetime]
    drop_dlv_zone: Optional[str]
    drop_dlv_zone_datetime: Optional[datetime]
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True

class WorkerAssignmentResponseForWorkerLists(APIResponseBase):
    data: List[WorkerAssignmentResponseForWorker] 
    total: int

    class Config:
        from_attributes = True



class RequestOfWorkerAssignment(BaseModel):
    oc_no: str  # The OC number
    emp_id: str  # The employee ID to assign


class ResponseOfWorkerAssignment(APIResponseBase):
   oc_num:str
   emp_id:str


# Define the structure of the request body
class AssignDropDlvZoneRequest(BaseModel):
    oc_no: str = Field(..., description="Order/OC number identifying the assignment")
    drop_dlv_zone: str = Field(..., description="New drop delivery zone code to assign")
    device_id:Optional[str]
    # emp_id can be optional if taken from auth token
    emp_id: Optional[str] = Field(
        default=None,
        description="Employee ID (optional)"
    )



# =======================================================================================

class WorkerAssignmentSearchRequest(BaseModel):
    search_type: str = Field(..., description="oc | gp | temp_oc | awb | hawb")
    search_value: str = Field(..., description="Value to search")



class PaginationMetadata(BaseModel):
    """Pagination metadata"""
    current_page: int
    page_size: int
    total_records: int
    total_pages: int
    has_previous: bool
    has_next: bool
    previous_page: Optional[int]
    next_page: Optional[int]


class MatrixCounts(BaseModel):
    """Matrix counts for worker assignments"""
    pure_oc_merge_count: int
    temp_irm_count: int
    gp_alloted_count: int


class FiltersApplied(BaseModel):
    """Applied filters information"""
    status: str
    start_date: Optional[str]
    end_date: Optional[str]


class PaginatedWorkerAssignmentResponse(APIResponseBase):
    """Complete paginated response"""
    data: List[WorkerAssignmentResponseForWorker] # Replace with your WorkerAssignment schema
    pagination: PaginationMetadata
    matrix_counts: MatrixCounts
    filters_applied: FiltersApplied

    class Config:
        from_attributes = True


class WorkerAssignmentExportRequest(BaseModel):
    assignment_status: str = Field(default="all", description="all | assigned | unassigned | dlv_added | assigned_but_not_delivered")
    startDate: str = Field(..., description="Start date in YYYY-MM-DD format")
    endDate: str = Field(..., description="End date in YYYY-MM-DD format")

class WorkerAssignmentExportResponse(APIResponseBase):
    message: str
    total_records: int
    max_limit_of_data_export: int