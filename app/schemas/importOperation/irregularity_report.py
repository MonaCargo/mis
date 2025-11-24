

# from pydantic import BaseModel, Field
# from datetime import datetime
# from typing import Optional

# from app.schemas.base import APIResponseBase

# class FlightIrregularityCreate(BaseModel):
#     flt_no: Optional[str] = None
#     flt_date: Optional[datetime] = None
#     awb_number:  str 
#     hwb_num: Optional[str] = None
#     org: Optional[str] = None
#     dest: Optional[str] = None
#     tot_pcs: Optional[int] = None
#     tot_wgt: Optional[float] = None
#     uld_number: Optional[str] = None
#     seg_date: Optional[datetime] = None
#     agt: Optional[str] = None
#     irr_code: Optional[str] = None
#     pcs: Optional[int] = None
#     open_remarks: Optional[str] = None
#     irr_open_datetime: Optional[datetime] = None
#     irr_close_datetime: Optional[datetime] = None
#     cosys_id: Optional[str] = None
#     closing_remarks: Optional[str] = None
#     performance: Optional[str] = None