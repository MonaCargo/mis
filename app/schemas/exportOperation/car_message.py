# schemas/export_car_message_awb.py

from pydantic import BaseModel
from datetime import datetime
from typing import Optional


class ExportCarMessageAwbCreate(BaseModel):
    awb_no: str
    origin: str
    destination: str

    sb_no: Optional[str]
    sb_date: Optional[datetime]
    hwb_no: Optional[str]

    pcs: Optional[int]
    
    gross_wt: Optional[float]
    volumetric_wt: Optional[float]
    chg_wt: Optional[float]

    nog: Optional[str]
    shc: Optional[str]

    car_msg_date: Optional[datetime]
    car_msg_time: Optional[str]


class ExportCarMessageAwbResponse(ExportCarMessageAwbCreate):
    id: int

    class Config:
        from_attributes = True   # Pydantic v2