# # app/schemas/import_release_report.py

# from pydantic import BaseModel, Field
# from datetime import datetime
# from typing import Optional

# from app.schemas.base import APIResponseBase


# class ImportReleaseReportBase(BaseModel):
#     date: Optional[datetime] = None
#     agent: Optional[str] = None
#     consignee: Optional[str] = None
#     consignee_address: Optional[str] = None
#     state: Optional[str] = None
#     consolidator: Optional[str] = None
#     awb: str
#     hwb: Optional[str] = None
#     boe_num: Optional[str] = None
#     oc_num: Optional[str] = None
#     org: Optional[str] = None
#     pcs: Optional[int] = None
#     grg_wt: Optional[float] = None
#     chg_wt: Optional[float] = None
#     nog: Optional[str] = None
#     shc: Optional[str] = None
#     flight_no: Optional[str] = None
#     flight_date: Optional[datetime] = None
#     segregation_date: Optional[datetime] = None
#     segregation_time: Optional[str] = None
#     segregation_datetime: Optional[datetime] = None
#     do_num: Optional[str] = None
#     sdo_num: Optional[str] = None
#     integration_mode: Optional[str] = None
#     cosys_id: Optional[str] = None
#     pick_order_recd_datetime: Optional[datetime] = None
#     pick_order_end_datetime: Optional[datetime] = None
#     gate_pass_no: Optional[str] = None
#     gate_pass_issued_date: Optional[datetime] = None
#     gate_pass_issued_time: Optional[str] = None
#     gate_pass_issued_datetime: Optional[datetime] = None # new field added
#     gate_pass_recd_datetime: Optional[datetime] = None
#     gate_pass_end_datetime: Optional[datetime] = None
#     gate_pass_released_by: Optional[str] = None
#     actual_dlv_datetime: Optional[datetime] = None
#     truck_load_datetime: Optional[datetime] = None
#     ata: Optional[datetime] = None
#     flight_complete_datetime: Optional[datetime] = None
#     delivered_to: Optional[str] = None
#     dlv_id_typ: Optional[str] = None
#     dlv_id_no: Optional[str] = None
#     cha_id: Optional[str] = None
#     manually_boe_user: Optional[str] = None
#     manually_boe_datetime: Optional[datetime] = None
#     manual_boe_approval_user: Optional[str] = None
#     manual_boe_approval_datetime: Optional[datetime] = None
#     manually_oc_user: Optional[str] = None
#     manually_oc_datetime: Optional[datetime] = None
#     manual_oc_approval_user: Optional[str] = None
#     manual_oc_approval_datetime: Optional[datetime] = None
#     dlv_zone: Optional[str] = None
#     mobile_number: Optional[str] = None
#     online_counter: Optional[str] = None
#     location_pcs: Optional[str] = None


# class ImportReleaseReportCreate(ImportReleaseReportBase):
#     pass


# class ImportReleaseReportResponse(ImportReleaseReportBase):
#     id: int
#     created_at: datetime
#     updated_at: datetime

#     class Config:
#         from_attributes = True


# class FileUploadResponse(APIResponseBase):
#     total_records: int
#     processed_records: int
#     failed_records: int
#     errors: Optional[list] = None

















