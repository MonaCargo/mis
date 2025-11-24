from pydantic import BaseModel, Field, field_validator
from datetime import datetime
from typing import Optional


class OcReportBase(BaseModel):
    """Base schema for integrate data"""
    msg_id: Optional[str] = Field(None, max_length=100)
    awb_no: Optional[str] = Field(None, max_length=100)
    hawb_no: Optional[str] = Field(None, max_length=100)
    oc_no: Optional[str] = Field(None, max_length=100)
    boe_no: Optional[str] = Field(None, max_length=100)
    pcs: Optional[int] = Field(None)  # Greater than or equal to 0
    integrate_date_time: Optional[datetime] = None
    
    # @field_validator('msg_id', 'awb_no', 'hawb_no', 'oc_no', 'boe_no', mode='before')
    # @classmethod
    # def strip_whitespace(cls, v):
    #     """Strip whitespace from string fields"""
    #     if isinstance(v, str):
    #         v = v.strip()
    #         return v if v else None
    #     return v
    
    # @field_validator('integrate_date_time', mode='before')
    # @classmethod
    # def validate_datetime(cls, v):
    #     """Ensure datetime is timezone-aware UTC"""
    #     if v is None:
    #         return None
    #     if isinstance(v, datetime):
    #         # If naive, assume UTC
    #         if v.tzinfo is None:
    #             import pytz
    #             return pytz.utc.localize(v)
    #         # If already has timezone, convert to UTC
    #         return v.astimezone(pytz.utc)
    #     return v


class IntegrateDataCreate(OcReportBase):
    """Schema for creating integrate data"""
    pass


class IntegrateDataUpdate(BaseModel):
    """Schema for updating integrate data (all fields optional)"""
    msg_id: Optional[str] = Field(None, max_length=100)
    awb_no: Optional[str] = Field(None, max_length=100)
    hawb_no: Optional[str] = Field(None, max_length=100)
    oc_no: Optional[str] = Field(None, max_length=100)
    boe_no: Optional[str] = Field(None, max_length=100)
    pcs: Optional[int] = Field(None, ge=0)
    integrate_date_time: Optional[datetime] = None
    
    # @field_validator('msg_id', 'awb_no', 'hawb_no', 'oc_no', 'boe_no', mode='before')
    # @classmethod
    # def strip_whitespace(cls, v):
    #     if isinstance(v, str):
    #         v = v.strip()
    #         return v if v else None
    #     return v


class IntegrateDataResponse(OcReportBase):
    """Schema for returning integrate data"""
    id: int
    created_at: datetime
    updated_at: datetime
    
    class Config:
        from_attributes = True  # For Pydantic v2 (use orm_mode = True for v1)


class IntegrateDataList(BaseModel):
    """Schema for paginated list response"""
    total: int
    page: int
    page_size: int
    data: list[IntegrateDataResponse]


class BulkUploadResponse(BaseModel):
    """Schema for bulk upload response"""
    success: bool
    total_records: int
    inserted_records: int
    failed_records: int
    errors: Optional[list[dict]] = []
    message: str