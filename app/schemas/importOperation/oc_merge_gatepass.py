from pydantic import BaseModel
from typing import Optional
from datetime import datetime
from typing import List



from app.schemas.base import APIResponseBase
from app.schemas.user import UserRead

class OcMergeGatePassCreate(BaseModel):
    igp_no: str
    flight_no: str
    igp_print_date_time:Optional[datetime]
    awb_no: str
    # hawb: str
    hawb: Optional[str] = None
    flight_date: Optional[datetime]
    no_of_pc: Optional[int]
    weight_in_kgs: Optional[float]
    chg_wgt_in_kg : Optional[float]
    location: Optional[str]
    oc_no: str
    temp_irm_oc_no: Optional[str]
    irregularity_remarks: Optional[str]
    pd_in_time: Optional[datetime]
    no_of_pc_recd: Optional[int]
    verified_by: Optional[str]
    agent_name: Optional[str]
    customer_name: Optional[str]
    integrate_date_time: Optional[datetime] = None  # ✅ NEW FIELD
    

    class Config:
        from_attributes = True




class OcMergeGatePassResponse(OcMergeGatePassCreate):
    id: int
    class Config:
        from_attributes = True


class OcMergeGatePassListResponse(APIResponseBase):
    data: List[OcMergeGatePassResponse]
    execution_time: Optional[float] = None
    igp_range: Optional[str] = None
    total_processed: Optional[int] = None

class MarkPrintedRequest(BaseModel):
    oc_nos: List[str]


# ---------------------for search schema------------------

class OCMergeGatePassGenericSearchResponse(BaseModel):
    igp_no: str
    flight_no: str
    igp_print_date_time:Optional[datetime]
    awb_no: str
    # hawb: str
    hawb: Optional[str] = None
    flight_date: Optional[datetime]
    no_of_pc: Optional[int]
    weight_in_kgs: Optional[float]
    chg_wgt_in_kg : Optional[float]
    location: Optional[str]
    oc_no: str
    temp_irm_oc_no: Optional[str]
    irregularity_remarks: Optional[str]
    pd_in_time: Optional[datetime]
    no_of_pc_recd: Optional[int]
    verified_by: Optional[str]
    agent_name: Optional[str]
    customer_name: Optional[str]
    integrate_date_time: Optional[datetime] = None  # ✅ NEW FIELD
    uploaded_by:Optional[str]
    irr_codes:Optional[str]
    shc:Optional[str]
    is_printed:bool
    user_info: Optional[UserRead] = None
    

class OCMergeGatePassGenericSearchResponseList(APIResponseBase):
    data:List[OCMergeGatePassGenericSearchResponse]