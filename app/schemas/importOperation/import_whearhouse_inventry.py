from pydantic import BaseModel, ConfigDict
from typing import Optional, List
from datetime import datetime

from app.schemas.base import APIResponseBase

class ImportWhereHouseInventryBase(BaseModel):
    awb_no: str
    hwb_no: Optional[str] = None
    m_h: Optional[str] = None
    origin: Optional[str] = None
    destination: Optional[str] = None
    warehouse_location: Optional[str] = None
    status: Optional[str] = None
    location_date: Optional[datetime] = None
    pcs: Optional[int] = None
    wgt_chg: Optional[float] = None
    grs_wgt: Optional[float] = None
    nature_of_goods: Optional[str] = None
    shc: Optional[str] = None
    agent: Optional[str] = None
    fltno: Optional[str] = None
    flt_date: Optional[datetime] = None
    cne_name: Optional[str] = None
    cne_addr: Optional[str] = None

class ImportWhereHouseInventryCreate(ImportWhereHouseInventryBase):
    pass

class AirwayBillResponse(ImportWhereHouseInventryBase):
    id: str
    created_at: datetime
    updated_at: datetime

    model_config = ConfigDict(from_attributes=True)

# Response schemas using your APIResponseBase
class ImportWhereHouseInventryResponse(APIResponseBase):
    records_count: int
    file_name: str
    file_type: str

class ImportWhereHouseInventryListResponse(APIResponseBase):
    data: List[AirwayBillResponse]