# app/schemas/damage_report.py
import json
from pydantic import BaseModel, Field, validator
from typing import List, Optional
from datetime import datetime


class DamageReasonBase(BaseModel):
    """Base schema for damage reason"""
    reason_code: str
    reason_name: str
    description: Optional[str] = None
    is_active: bool = True


class DamageReasonCreate(DamageReasonBase):
    """Schema for creating a damage reason"""
    pass


class DamageReasonResponse(DamageReasonBase):
    """Response schema for damage reason"""
    id: int
    created_at: datetime
    updated_at: Optional[datetime]

    class Config:
        from_attributes = True


class DamageReportImageResponse(BaseModel):
    """Response schema for damage report image"""
    id: int
    report_id: int
    # worker_assignment_id:int
    emp_id:str
    device_id: Optional[str]
    image_url: str
    image_name: str
    file_size: Optional[int]
    mime_type: Optional[str]
    uploaded_at: datetime

    class Config:
        from_attributes = True


class DamageReportReasonResponse(BaseModel):
    """Response schema for damage report reason relationship"""
    id: int
    report_id: int 
    # worker_assignment_id:int
    reason_id: int 
    emp_id: str 
    device_id: Optional[str]
    reason: DamageReasonResponse
    created_at: datetime

    class Config:
        from_attributes = True


class DamageReportCreate(BaseModel):
    """Schema for creating a new damage report"""
    oc_no: str = Field(..., min_length=1, max_length=50)
    worker_assignment_id:int = Field(...,description="ID of the worker assignment")
    awb_no: str = Field(None, min_length=1, max_length=50)
    hawb: Optional[str] = Field(None, min_length=1, max_length=50)
    location: str = Field(..., min_length=1, max_length=50)
    emp_id: str = Field(..., min_length=1, max_length=50)
    device_id :Optional[str] = Field(None,description="Device ID")
    reason_ids: List[int] = Field(..., min_items=1, max_items=10)
    @validator("reason_ids", pre=True)
    def parse_reason_ids(cls, v):
        if isinstance(v, str):
            try:
                parsed = json.loads(v)
                if isinstance(parsed, list) and all(isinstance(i, int) for i in parsed):
                    return parsed
            except Exception:
                pass
            raise ValueError("reason_ids must be a JSON array of integers")
        return v

    remarks: Optional[str] = Field(None, max_length=500)
    reported_at: datetime

    class Config:
        json_schema_extra = {
            "example": {
                "oc_no": "OC-2024-001",
                "awb_no": "AWB-123456", 
                "hawb": "HAWB-7890",
                "location": "IGF_38_C/1",
                "emp_id": "EMP001",
                "reason_ids": [1, 2],  # IDs from damage_reasons table
                "remarks": "Package was found in rain-exposed area",
                "reported_at": "2024-12-31T12:00:00Z"
            }
        }


class DamageReportUpdate(BaseModel):
    """Schema for updating a damage report"""
    reason_ids: Optional[List[int]] = Field(None, min_items=1)
    remarks: Optional[str] = Field(None, max_length=500)


class DamageReportResponse(BaseModel):
    """Response schema for damage report"""
    id: int
    worker_assignment_id:int
    oc_no: str
    awb_no:str
    hawb:Optional[str]
    location: str
    # emp_id: str
    remarks: Optional[str]
    reported_at: datetime
    created_at: datetime
    updated_at: Optional[datetime]
    reasons: List[DamageReportReasonResponse] = []
    images: List[DamageReportImageResponse] = []

    class Config:
        from_attributes = True


class DamageReportSimpleResponse(BaseModel):
    """Simplified response with just reason names"""
    id: int
    worker_assignment_id:int
    oc_no: str
    location: str
    emp_id: str
    damage_reasons: List[str]  # Just the reason names
    remarks: Optional[str]
    reported_at: datetime
    created_at: datetime
    image_count: int

    class Config:
        from_attributes = True


class DamageReportListResponse(BaseModel):
    """Response schema for list of damage reports"""
    total: int
    reports: List[DamageReportResponse]


class DamageReportCreateResponse(BaseModel):
    """Response after creating damage report"""
    success: bool
    message: str
    report_id: int
    image_count: int

    class Config:
        json_schema_extra = {
            "example": {
                "success": True,
                "message": "Damage report submitted successfully",
                "report_id": 123,
                "image_count": 3
            }
        }