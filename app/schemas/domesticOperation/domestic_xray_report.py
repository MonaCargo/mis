# # schemas/domestic_xray.py
# from pydantic import BaseModel, Field, ConfigDict,field_serializer
# from typing import List, Optional
# from datetime import datetime, date, time

# from app.schemas.base import APIResponseBase

# class DomesticXrayBase(BaseModel):
#     """Base schema for Domestic X-ray report"""
#     awb_no: str = Field(..., description="AWB Number (11 digits)")
#     seq_num: str = Field(..., description="Sequence Number (8 characters)")
#     destination: Optional[str] = Field(None, description="Destination code")
#     accp_date: Optional[datetime] = Field(None, description="Acceptance date")
#     merge_acceptance_date_time: Optional[datetime] = Field(None, description="Merged acceptance date and time")
#     accp_time: Optional[str] = Field(None, description="Acceptance time")
#     accp_pcs: Optional[int] = Field(None, description="Accepted pieces")
#     rej_pcs: Optional[int] = Field(None, description="Rejected pieces")
#     gross_weight: Optional[float] = Field(None, description="Gross weight")
#     rej_gross_weight: Optional[float] = Field(None, description="Rejected gross weight")
#     chg_weight: Optional[float] = Field(None, description="Chargeable weight")
#     shc: Optional[str] = Field(None, description="Special Handling Code")
#     name_of_goods: Optional[str] = Field(None, description="Name of goods")
#     agent_name: Optional[str] = Field(None, description="Agent name")
#     freighter_type: Optional[str] = Field(None, description="Freighter type")
#     xray_type: Optional[str] = Field(None, description="X-ray type")
#     phs_pcs: Optional[int] = Field(None, description="PHS pieces")
#     etd_pcs: Optional[int] = Field(None, description="ETD pieces")
#     eds_pcs: Optional[int] = Field(None, description="EDS pieces")
#     edd_pcs: Optional[int] = Field(None, description="EDD pieces")
#     vck_pcs: Optional[int] = Field(None, description="VCK pieces")
#     cmd_pcs: Optional[int] = Field(None, description="CMD pieces")
#     xray_date_time: Optional[datetime] = Field(None, description="X-ray date and time")
#     xray_user: Optional[str] = Field(None, description="X-ray user")
#     serial_no: Optional[str] = Field(None, description="Serial number")
#     remarks: Optional[str] = Field(None, description="Remarks")
#     # is_pdf_generated: Optional[bool] = Field(False, description="Is PDF generated")
#     # pdf_generated_date_time: Optional[datetime] = Field(None, description="PDF generated date and time")
#     # is_email_sent: Optional[bool] = Field(False, description="Is email sent")
#     # email_sent_date_time: Optional[datetime] = Field(None, description="Email sent date and time")
#     # uploaded_by: Optional[str] = Field(None, description="User who uploaded the report")

# class PaginationMetadata(BaseModel):
#     current_page: int
#     page_size: int
#     total_records: int
#     total_pages: int
#     has_previous: bool
#     has_next: bool
#     previous_page: Optional[int]
#     next_page: Optional[int]


# class DomesticXrayCreate(DomesticXrayBase):
#     """Schema for creating Domestic X-ray report"""
#     # cosys_report_date: datetime = Field(..., description="Report date from COSYS")
#     uploaded_by: str = Field(..., description="User who uploaded the report")

# class DomesticXrayUpdate(BaseModel):
#     """Schema for updating Domestic X-ray report"""
#     model_config = ConfigDict(extra='forbid')
    
#     destination: Optional[str] = None
#     remarks: Optional[str] = None
#     is_pdf_generrated: Optional[bool] = None
#     print_date_time: Optional[datetime] = None
#     is_email_sent: Optional[bool] = None
#     email_sent_date_time: Optional[datetime] = None

# class DomesticXrayResponse(DomesticXrayBase):
#     """Schema for Domestic X-ray report response"""
#     model_config = ConfigDict(from_attributes=True)
    
#     id: int
#     is_pdf_generated: bool
#     pdf_generated_date_time: Optional[datetime]
#     is_email_sent: bool
#     email_sent_date_time: Optional[datetime]
#     # cosys_report_date: datetime
#     uploaded_by: str
#     created_at: datetime
#     updated_at: datetime

#     @field_serializer('accp_time')
#     def serialize_accp_time(self, value) -> Optional[str]:
#         """Convert time object to string"""
#         if value is None:
#             return None
#         # if isinstance(value, str):
#         #     return value
#         # if isinstance(value, time):
#         #     return value.strftime('%H:%M:%S')
#         return value.strftime('%H:%M:%S')

# class DomesticXrayUploadRequest(BaseModel):
#     """Schema for upload request metadata"""
#     cosys_report_date: date = Field(..., description="Report date from COSYS (YYYY-MM-DD)")
#     uploaded_by: str = Field(..., min_length=1, description="Username of uploader")
#     header_row: int = Field(default=5, ge=0, description="Row number containing headers (default: 5)")

# class DomesticXrayUploadResponse(BaseModel):
#     """Schema for upload response"""
#     success: bool
#     message: str
#     total_records: int
#     valid_records: int
#     invalid_records: int
#     duplicate_records: int
#     statistics: dict
#     upload_details: dict

# class DomesticXrayFilterParams(BaseModel):
#     """Schema for filtering domestic x-ray reports"""
#     awb_no: Optional[str] = None
#     destination: Optional[str] = None
#     agent_name: Optional[str] = None
#     start_date: Optional[date] = None
#     end_date: Optional[date] = None
#     xray_type: Optional[str] = None
#     uploaded_by: Optional[str] = None
#     is_pdf_generated: Optional[bool] = None
#     is_email_sent: Optional[bool] = None
#     # skip: int = Field(default=0, ge=0)
#     # page_size: int = Field(default=600, ge=1, le=1200)
#     # limit: int = Field(default=20, ge=1, le=1200)

# class DomesticXrayListResponse(APIResponseBase):
#     """Schema for list response with pagination"""
#     pagination: PaginationMetadata
#     data: list[DomesticXrayResponse]

# class PdfGenerateStatusUpdate(BaseModel):
#     """Schema for updating print status"""
#     is_pdf_generated: bool = True
#     pdf_generated_date_time: Optional[datetime] = None

# class EmailStatusUpdate(BaseModel):
#     """Schema for updating email status"""
#     is_email_sent: bool = True
#     email_sent_date_time: Optional[datetime] = None

# class BulkActionResponse(BaseModel):
#     """Schema for bulk action response"""
#     success: bool
#     message: str
#     affected_count: int
#     failed_ids: Optional[list[int]] = None

 
# class DomesticXrayBaseForResponse(BaseModel):
#     """Base schema for Domestic X-ray report"""
#     awb_no: str = Field(..., description="AWB Number (11 digits)")
#     seq_num: str = Field(..., description="Sequence Number (8 characters)")
#     destination: Optional[str] = Field(None, description="Destination code")
#     accp_date: Optional[datetime] = Field(None, description="Acceptance date")
#     merge_acceptance_date_time: Optional[datetime] = Field(None, description="Merged acceptance date and time")
#     accp_time: Optional[str] = Field(None, description="Acceptance time")
#     accp_pcs: Optional[int] = Field(None, description="Accepted pieces")
#     rej_pcs: Optional[int] = Field(None, description="Rejected pieces")
#     gross_weight: Optional[float] = Field(None, description="Gross weight")
#     rej_gross_weight: Optional[float] = Field(None, description="Rejected gross weight")
#     chg_weight: Optional[float] = Field(None, description="Chargeable weight")
#     shc: Optional[str] = Field(None, description="Special Handling Code")
#     name_of_goods: Optional[str] = Field(None, description="Name of goods")
#     agent_name: Optional[str] = Field(None, description="Agent name")
#     freighter_type: Optional[str] = Field(None, description="Freighter type")
#     xray_type: Optional[str] = Field(None, description="X-ray type")
#     phs_pcs: Optional[int] = Field(None, description="PHS pieces")
#     etd_pcs: Optional[int] = Field(None, description="ETD pieces")
#     eds_pcs: Optional[int] = Field(None, description="EDS pieces")
#     edd_pcs: Optional[int] = Field(None, description="EDD pieces")
#     vck_pcs: Optional[int] = Field(None, description="VCK pieces")
#     cmd_pcs: Optional[int] = Field(None, description="CMD pieces")
#     xray_date_time: Optional[datetime] = Field(None, description="X-ray date and time")
#     xray_user: Optional[str] = Field(None, description="X-ray user")
#     serial_no: Optional[str] = Field(None, description="Serial number")
#     remarks: Optional[str] = Field(None, description="Remarks")
#     is_pdf_generated: Optional[bool] = Field(False, description="Is PDF generated")
#     pdf_generated_date_time: Optional[datetime] = Field(None, description="PDF generated date and time")
#     is_email_sent: Optional[bool] = Field(False, description="Is email sent")
#     email_sent_date_time: Optional[datetime] = Field(None, description="Email sent date and time")
#     uploaded_by: Optional[str] = Field(None, description="User who uploaded the report")

#     model_config = ConfigDict(from_attributes=True)
    
#     # Add serializer for accp_time
#     @field_serializer('accp_time')
#     def serialize_accp_time(self, value: Optional[time]) -> Optional[str]:
#         """Convert time object to string"""
#         if value is None:
#             return None
#         if isinstance(value, str):
#             return value
#         return value.strftime('%H:%M:%S')


# class GenericSearchResultResponse(APIResponseBase):
#     """Schema for generic search result"""
#     data: List[DomesticXrayBaseForResponse]
#     your_search_type: str
#     your_search_value: str
#     total : int
#     status: str

    
# # class SecurityDeclarationCreate(BaseModel):
# #     regulated_entity_ids: List[str] = Field(..., example=["IN/RA/000017-01", "IN/RA/000006-05"])
# #     awb_no: str = Field(..., example="098-76099744")
# #     contents: str = Field(..., example="CONSOLIDATED GO")
# #     consolidation: str = Field(..., example="Y")
# #     origin: str = Field(..., example="ZRH")
# #     destination: str = Field(..., example="AMD")
# #     transit_points: str = Field(..., example="ZRH-DEL-AMD")
# #     security_status:  List[str]  = Field(..., example=["SPX",'SHR'])
# #     screening_method: str = Field(..., example="XRY")
# #     other_screening: Optional[str] = Field(default="N.A", example="N.A")
# #     screener_name: str = Field(..., example="9629 XRAY SCREENER 20")
# #     issued_date: date = Field(..., example="2025-12-18")
# #     issued_time: str = Field(..., example="1417")
# #     additional_info: Optional[str] = Field(default=None, example="")

# #     class Config:
# #         schema_extra = {
# #             "example": {
# #                 "regulated_entity_ids": ["IN/RA/000017-01", "IN/RA/000006-05"],
# #                 "awb_no": "098-76099744",
# #                 "contents": "CONSOLIDATED GO",
# #                 "consolidation": "Y",
# #                 "origin": "ZRH",
# #                 "destination": "AMD",
# #                 "transit_points": "ZRH-DEL-AMD",
# #                 "security_status": ["SPX","SHR"],
# #                 "screening_method": "XRY",
# #                 "other_screening": "N.A",
# #                 "screener_name": "9629 XRAY SCREENER 20",
# #                 "issued_date": "2025-12-18",
# #                 "issued_time": "1417",
# #                 "additional_info": ""
# #             }
# #         }


# # schemas.py

# class EmployeeCreate(BaseModel):
#     employee_id: str
#     employee_name: str
#     xray_user_id: str | None

# class EmployeeResponse(BaseModel):
#     model_config = ConfigDict(from_attributes=True)  # This is REQUIRED for model_validate()

#     employee_id: str
#     employee_name: str
#     xray_user_id: str | None


# schemas/domestic_xray.py
from pydantic import BaseModel, Field, ConfigDict, model_validator
from typing import Dict, List, Literal, Optional, Any
from datetime import datetime, date, time

from app.schemas.base import APIResponseBase

class DomesticXrayBase(BaseModel):
    """Base schema for Domestic X-ray report"""
    awb_no: str = Field(..., description="AWB Number (11 digits)")
    seq_num: str = Field(..., description="Sequence Number (8 characters)")
    destination: Optional[str] = Field(None, description="Destination code")
    accp_date: Optional[datetime] = Field(None, description="Acceptance date")
    merge_acceptance_date_time: Optional[datetime] = Field(None, description="Merged acceptance date and time")
    accp_time: Optional[str] = Field(None, description="Acceptance time")
    accp_pcs: Optional[int] = Field(None, description="Accepted pieces")
    rej_pcs: Optional[int] = Field(None, description="Rejected pieces")
    gross_weight: Optional[float] = Field(None, description="Gross weight")
    rej_gross_weight: Optional[float] = Field(None, description="Rejected gross weight")
    chg_weight: Optional[float] = Field(None, description="Chargeable weight")
    shc: Optional[str] = Field(None, description="Special Handling Code")
    name_of_goods: Optional[str] = Field(None, description="Name of goods")
    agent_name: Optional[str] = Field(None, description="Agent name")
    freighter_type: Optional[str] = Field(None, description="Freighter type")
    xray_type: Optional[str] = Field(None, description="X-ray type")
    phs_pcs: Optional[int] = Field(None, description="PHS pieces")
    etd_pcs: Optional[int] = Field(None, description="ETD pieces")
    eds_pcs: Optional[int] = Field(None, description="EDS pieces")
    edd_pcs: Optional[int] = Field(None, description="EDD pieces")
    vck_pcs: Optional[int] = Field(None, description="VCK pieces")
    cmd_pcs: Optional[int] = Field(None, description="CMD pieces")
    xray_date_time: Optional[datetime] = Field(None, description="X-ray date and time")
    xray_user: Optional[str] = Field(None, description="X-ray user")
    serial_no: Optional[str] = Field(None, description="Serial number")
    remarks: Optional[str] = Field(None, description="Remarks")
    
    @model_validator(mode='before')
    @classmethod
    def convert_time_to_string(cls, data: Any) -> Any:
        """Convert time objects to strings before validation"""
        if isinstance(data, dict):
            if 'accp_time' in data and data['accp_time'] is not None:
                if isinstance(data['accp_time'], time):
                    data['accp_time'] = data['accp_time'].strftime('%H:%M:%S')
        else:
            # Handle SQLAlchemy model objects
            if hasattr(data, 'accp_time') and data.accp_time is not None:
                if isinstance(data.accp_time, time):
                    data.accp_time = data.accp_time.strftime('%H:%M:%S')
        return data

class PaginationMetadata(BaseModel):
    current_page: int
    page_size: int
    total_records: int
    total_pages: int
    has_previous: bool
    has_next: bool
    previous_page: Optional[int]
    next_page: Optional[int]


class DomesticXrayCreate(DomesticXrayBase):
    """Schema for creating Domestic X-ray report"""
    uploaded_by: str = Field(..., description="User who uploaded the report")

class DomesticXrayUpdate(BaseModel):
    """Schema for updating Domestic X-ray report"""
    model_config = ConfigDict(extra='forbid')
    
    destination: Optional[str] = None
    remarks: Optional[str] = None
    is_pdf_generrated: Optional[bool] = None
    print_date_time: Optional[datetime] = None
    is_email_sent: Optional[bool] = None
    email_sent_date_time: Optional[datetime] = None

class DomesticXrayResponse(DomesticXrayBase):
    """Schema for Domestic X-ray report response"""
    model_config = ConfigDict(from_attributes=True)
    
    id: int
    is_pdf_generated: bool
    pdf_generated_date_time: Optional[datetime]
    is_email_sent: bool
    email_sent_date_time: Optional[datetime]
    uploaded_by: str
    created_at: datetime
    updated_at: datetime

class DomesticXrayUploadRequest(BaseModel):
    """Schema for upload request metadata"""
    cosys_report_date: date = Field(..., description="Report date from COSYS (YYYY-MM-DD)")
    uploaded_by: str = Field(..., min_length=1, description="Username of uploader")
    header_row: int = Field(default=5, ge=0, description="Row number containing headers (default: 5)")

class DomesticXrayUploadResponse(BaseModel):
    """Schema for upload response"""
    success: bool
    message: str
    total_records: int
    valid_records: int
    invalid_records: int
    duplicate_records: int
    statistics: dict
    upload_details: dict

class DomesticXrayFilterParams(BaseModel):
    """Schema for filtering domestic x-ray reports"""
    awb_no: Optional[str] = None
    destination: Optional[str] = None
    agent_name: Optional[str] = None
    start_date: Optional[date] = None
    end_date: Optional[date] = None
    xray_type: Optional[str] = None
    uploaded_by: Optional[str] = None
    is_pdf_generated: Optional[bool] = None
    is_email_sent: Optional[bool] = None

class DomesticXrayListResponse(APIResponseBase):
    """Schema for list response with pagination"""
    pagination: PaginationMetadata
    data: list[DomesticXrayResponse]

class PdfGenerateStatusUpdate(BaseModel):
    """Schema for updating print status"""
    is_pdf_generated: bool = True
    pdf_generated_date_time: Optional[datetime] = None

class EmailStatusUpdate(BaseModel):
    """Schema for updating email status"""
    is_email_sent: bool = True
    email_sent_date_time: Optional[datetime] = None

class BulkActionResponse(BaseModel):
    """Schema for bulk action response"""
    success: bool
    message: str
    affected_count: int
    failed_ids: Optional[list[int]] = None

 
class DomesticXrayBaseForResponse(BaseModel):
    """Base schema for Domestic X-ray report"""
    awb_no: str = Field(..., description="AWB Number (11 digits)")
    seq_num: str = Field(..., description="Sequence Number (8 characters)")
    destination: Optional[str] = Field(None, description="Destination code")
    accp_date: Optional[datetime] = Field(None, description="Acceptance date")
    merge_acceptance_date_time: Optional[datetime] = Field(None, description="Merged acceptance date and time")
    accp_time: Optional[str] = Field(None, description="Acceptance time")
    accp_pcs: Optional[int] = Field(None, description="Accepted pieces")
    rej_pcs: Optional[int] = Field(None, description="Rejected pieces")
    gross_weight: Optional[float] = Field(None, description="Gross weight")
    rej_gross_weight: Optional[float] = Field(None, description="Rejected gross weight")
    chg_weight: Optional[float] = Field(None, description="Chargeable weight")
    shc: Optional[str] = Field(None, description="Special Handling Code")
    name_of_goods: Optional[str] = Field(None, description="Name of goods")
    agent_name: Optional[str] = Field(None, description="Agent name")
    freighter_type: Optional[str] = Field(None, description="Freighter type")
    xray_type: Optional[str] = Field(None, description="X-ray type")
    phs_pcs: Optional[int] = Field(None, description="PHS pieces")
    etd_pcs: Optional[int] = Field(None, description="ETD pieces")
    eds_pcs: Optional[int] = Field(None, description="EDS pieces")
    edd_pcs: Optional[int] = Field(None, description="EDD pieces")
    vck_pcs: Optional[int] = Field(None, description="VCK pieces")
    cmd_pcs: Optional[int] = Field(None, description="CMD pieces")
    xray_date_time: Optional[datetime] = Field(None, description="X-ray date and time")
    xray_user: Optional[str] = Field(None, description="X-ray user")
    serial_no: Optional[str] = Field(None, description="Serial number")
    remarks: Optional[str] = Field(None, description="Remarks")
    is_pdf_generated: Optional[bool] = Field(False, description="Is PDF generated")
    pdf_generated_date_time: Optional[datetime] = Field(None, description="PDF generated date and time")
    is_email_sent: Optional[bool] = Field(False, description="Is email sent")
    email_sent_date_time: Optional[datetime] = Field(None, description="Email sent date and time")
    uploaded_by: Optional[str] = Field(None, description="User who uploaded the report")
    email_sent_by: Optional[str] = Field(None, description="User who sent email")
    
    model_config = ConfigDict(from_attributes=True)
    
    @model_validator(mode='before')
    @classmethod
    def convert_time_to_string(cls, data: Any) -> Any:
        """Convert time objects to strings before validation"""
        if isinstance(data, dict):
            if 'accp_time' in data and data['accp_time'] is not None:
                if isinstance(data['accp_time'], time):
                    data['accp_time'] = data['accp_time'].strftime('%H:%M:%S')
        else:
            # Handle SQLAlchemy model objects
            if hasattr(data, 'accp_time') and data.accp_time is not None:
                if isinstance(data.accp_time, time):
                    data.accp_time = data.accp_time.strftime('%H:%M:%S')
        return data


class GenericSearchResultResponse(APIResponseBase):
    """Schema for generic search result"""
    data: List[DomesticXrayBaseForResponse]
    your_search_type: str
    your_search_value: str
    total : int
    status: str

class EmployeeCreate(BaseModel):
    employee_id: str
    employee_name: str
    xray_user_id: str | None

class EmployeeResponse(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    employee_id: str
    employee_name: str
    xray_user_id: str | None



# ======== Export related -----------

class XrayExportFilters(BaseModel):
    xray_filter_status: Optional[str] = "all"
    startDate: Optional[str]
    endDate: Optional[str]

class XrayExportRequest(BaseModel):
    export_type: Literal["FILTER", "SELECTED"]
    filters: Optional[XrayExportFilters] = None
    selected_ids: Optional[List[int]] = None



# ===============================
# OVERALL SUMMARY
# ===============================
class OverallEmailStats(BaseModel):
    total: int
    email_sent: int
    email_not_sent: int


# ===============================
# AIRLINE SUMMARY
# ===============================
class AirlineEmailStats(BaseModel):
    total: int
    email_sent: int
    email_not_sent: int


# ===============================
# DATE RANGE
# ===============================
class StatisticsDateRange(BaseModel):
    start_date: Optional[str]
    end_date: Optional[str]

class UserEmailSummary(BaseModel):
    emp_id: str
    name: str
    email_sent_count: int


# ===============================
# MAIN RESPONSE SCHEMA
# ===============================
class DomesticXrayStatisticsResponse(BaseModel):
    overall_summary: OverallEmailStats
    airline_summary: Dict[str, AirlineEmailStats]
    user_email_summary:List[UserEmailSummary]
