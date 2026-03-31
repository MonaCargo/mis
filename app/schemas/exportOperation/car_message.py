# schemas/export_car_message_awb.py

from pydantic import BaseModel, field_validator
from datetime import date, datetime
from typing import Optional

from app.schemas.base import APIResponseBase


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




class AvailableAwbForFlightBookingResponse(BaseModel):
    awb_master_id: int
    awb_no: str
    origin: str
    destination: str
    total_pcs: int
    booked_pcs: int
    remaining_pcs: int
    agent: Optional[str] = None
    rcs_datetime: Optional[datetime] = None

    class Config:
        from_attributes = True   # Pydantic v2

class AvailableAwbForFlightBookingResponseList(APIResponseBase):
    data : list[AvailableAwbForFlightBookingResponse]

    class Config:
        from_attributes = True   # Pydantic v2



# ================ ✌️Flight booking  Create route schema ==============================

class FlightBookingAwbItem(BaseModel):
    awb_master_id: int
    booked_pcs: int

    @field_validator("booked_pcs")
    @classmethod
    def pcs_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("booked_pcs must be at least 1")
        return v


class CreateFlightBookingRequest(BaseModel):
    flight_no: str
    flight_date: date
    flight_dpt_datetime: datetime
    awbs: list[FlightBookingAwbItem]

    @field_validator("flight_no")
    @classmethod
    def flight_no_not_empty(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("flight_no cannot be empty")
        return v

    @field_validator("awbs")
    @classmethod
    def awbs_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one AWB must be selected")
        return v


# ── Response ───────────────────────────────────────────────────
class FlightBookingDetailResponse(BaseModel):
    awb_master_id: int
    awb_no: str
    booked_pcs: int
    total_pcs: Optional[int]
   
    class Config:
        from_attributes = True   # Pydantic v2


class CreateFlightBookingResponse(APIResponseBase):
    header_id: int
    flight_no: str
    flight_date: date
    flight_dpt_datetime:datetime
    total_awbs: int
    total_pcs: int
    details: list[FlightBookingDetailResponse]


# -==----==---= EDIT flight booking ======

class EditFlightAwbItem(BaseModel):
    detail_id: Optional[int] = None      # None = new AWB to add
    awb_master_id: int
    booked_pcs: int

    @field_validator("booked_pcs")
    @classmethod
    def pcs_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("booked_pcs must be at least 1")
        return v


class EditFlightBookingRequest(BaseModel):
    flight_no: Optional[str] = None         # editable
    flight_date: Optional[date] = None      # editable
    flight_dpt_datetime: Optional[datetime] = None  # editable
    awbs: list[EditFlightAwbItem]           # full updated list
    removed_detail_ids: list[int] = []      # detail ids to delete

class FlightBookingHeaderResponse(BaseModel):
    header_id: int
    flight_no: str
    flight_date: date
    flight_dpt_datetime: datetime
    total_awbs: int
    total_pcs: int
    details: list[FlightBookingDetailResponse]
    class Config:
        from_attributes = True   # Pydantic v2

class FlightBookingDetailWithAwbResponse(BaseModel):
    detail_id: int
    awb_master_id: int
    awb_no: str
    origin: str
    destination: str
    total_pcs: int
    booked_pcs: int                    # booked in THIS flight
    booked_in_other_flights: int       # booked in other flights
    remaining_pcs: int                 # available across all flights
    agent: Optional[str] = None
    rcs_datetime: Optional[datetime] = None
    class Config:
        from_attributes = True   # Pydantic v2


class FlightBookingByFlightResponse(BaseModel):
    header_id: int
    flight_no: str
    flight_date: date
    flight_dpt_datetime: datetime
    booked_by: str
    booked_at: datetime
    total_awbs: int
    total_pcs: int                     # total pcs booked in this flight
    details: list[FlightBookingDetailWithAwbResponse]
    class Config:
        from_attributes = True   # Pydantic v2



class EditFlightAwbItem(BaseModel):
    detail_id: Optional[int] = None
    awb_master_id: int
    booked_pcs: int

    @field_validator("booked_pcs")
    @classmethod
    def pcs_must_be_positive(cls, v: int) -> int:
        if v < 1:
            raise ValueError("booked_pcs must be at least 1")
        return v


class EditFlightBookingRequest(BaseModel):
    awbs: list[EditFlightAwbItem]
    removed_detail_ids: list[int] = []

    @field_validator("awbs")
    @classmethod
    def awbs_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one AWB must be present")
        return v


class EditFlightBookingResponse(BaseModel):
    success: bool
    message: str
    data: FlightBookingByFlightResponse

    # ===end ====


#========================✌️ ULD ASSIGNMENT CREATE AND EDIT SCHEMA =====================================

 # ── ULD Master response ────────────────────────────────────────
class UldMasterResponse(BaseModel):
    uld_id: int
    uld_no: str
    carrier: str
    model_config = {"from_attributes": True}


# ── Create ─────────────────────────────────────────────────────
class CreateUldAssignmentRequest(BaseModel):
    flight_header_id: int
    uld_ids: list[int]

    @field_validator("uld_ids")
    @classmethod
    def ulds_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one ULD must be selected")
        if len(v) != len(set(v)):
            raise ValueError("Duplicate ULD ids in request")
        return v


# ── Edit ───────────────────────────────────────────────────────
class EditUldAssignmentRequest(BaseModel):
    uld_ids_to_add: list[int] = []
    uld_detail_ids_to_remove: list[int] = []

    @field_validator("uld_ids_to_add")
    @classmethod
    def no_duplicate_adds(cls, v: list) -> list:
        if len(v) != len(set(v)):
            raise ValueError("Duplicate ULD ids in add list")
        return v


# ── Detail response ────────────────────────────────────────────
class UldAssignmentDetailResponse(BaseModel):
    detail_id: int
    uld_id: int
    uld_no: str
    carrier: str
    model_config = {"from_attributes": True}


# ── Full assignment response ───────────────────────────────────
class UldAssignmentResponse(BaseModel):
    success: bool
    message: str
    data: "UldAssignmentDataResponse"


class UldAssignmentDataResponse(BaseModel):
    assignment_id: int
    flight_header_id: int
    flight_no: str
    flight_date: date  
    flight_dpt_datetime: datetime
    total_ulds: int
    assigned_by: str
    assigned_at: datetime
    ulds: list[UldAssignmentDetailResponse]
    model_config = {"from_attributes": True}


UldAssignmentResponse.model_rebuild() # forward references

# === END =========




# ============= 👌SKID RETRIVAL =====================================
class RetrieveSkidFromLocationRequest(BaseModel):
    mapping_id: int



# ======================== ✌️✌️ EXPORT ULD/PALLET LOADING BY SCANNING FROM BASE ===================    
# ── Verify ULD ─────────────────────────────────────────────
class UldVerifyForLoadingResponse(APIResponseBase):
    uld_assignment_detail_id: int
    uld_id: int
    uld_no: str
    carrier: str
    already_loaded: int   # items already scanned into this ULD


# ── Scan item into ULD ─────────────────────────────────────
class ScanItemIntoUldRequest(BaseModel):
    uld_assignment_detail_id: int
    sequence_nos: list[str]

    @field_validator("sequence_nos")
    @classmethod
    def validate_sequence_nos(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one sequence_no required")
        return [s.strip() for s in v if s.strip()]

class ScanItemResult(BaseModel):
    sequence_no: str
    awb_no: str
    success: bool
    message: str   # ✅ per item result — success or reason for failure

class ScanItemIntoUldResponse(APIResponseBase):
    uld_no: str
    total_submitted: int
    total_loaded: int
    total_failed: int
    results: list[ScanItemResult]
    
# class ScanItemIntoUldResponse(APIResponseBase):
#     sequence_id: int
#     sequence_no: str
#     awb_no: str
#     uld_no: str
#     loaded_by: str
#     loaded_at: datetime


# ── Loading status ─────────────────────────────────────────
class LoadedSequenceItem(BaseModel):
    sequence_id: int
    sequence_no: str
    awb_master_id: int
    awb_no: str
    loaded_by: str
    loaded_at: datetime


class UldLoadingStatusItem(BaseModel):
    uld_assignment_detail_id: int
    uld_id: int
    uld_no: str
    carrier: str
    loaded_count: int
    sequences: list[LoadedSequenceItem] = []   # ← ADD

class AwbLoadingStatusItem(BaseModel):
    awb_master_id: int
    awb_no: str
    booked_pcs: int
    loaded_pcs: int
    pending_pcs: int

class SequenceWithLoadingStatus(BaseModel):
    sequence_id: int
    sequence_no: str
    awb_master_id: int
    awb_no: str
    mapping_id: int
    sequence_date_time: datetime
    scanned_by: Optional[str] = None
    scan_by_device: Optional[str] = None
    is_loaded: bool
    uld_assignment_detail_id: Optional[int] = None
    loaded_by: Optional[str] = None
    loaded_at: Optional[datetime] = None
    is_eligible_to_load: bool          # ← ADD
    ineligible_reason: Optional[str] = None   # ← ADD


class FlightUldLoadingStatusResponse(APIResponseBase):
    flight_header_id: int
    flight_no: str
    flight_date: date
    flight_dpt_datetime: datetime
    total_to_load: int
    total_loaded: int
    total_pending: int

     # scan level summary
    total_scanned: int                          # ← ADD: How many pieces scanned during skid scanning at warehouse
    total_loaded_sequences: int                 # ← ADD: Same count from sequence perspective
    total_pending_sequences: int                # ← ADD

    is_fully_loaded: bool
    ulds: list[UldLoadingStatusItem]
    awbs: list[AwbLoadingStatusItem]
    all_sequences: list[SequenceWithLoadingStatus]   # ← ADD {all included which load in uld or not {all to attahed with that flights}}






    # ============================== DASHBOAERD SUMMARY SCHEMA ==============================

class AwbDaySummary(BaseModel):
    total_awbs: int
    total_pcs: int
    total_gross_wt: float | None

class ScanningDaySummary(BaseModel):
    # same day AWBs scanning
    scanned_awbs: int
    scanned_pcs: int
    unscanned_awbs: int
    unscanned_pcs: int
    # other day AWBs scanned on selected date
    others_scanned_awbs: int
    others_scanned_pcs: int

class SkidDaySummary(BaseModel):
    total_skids_used: int
    skids_at_location: int
    skids_not_at_location: int

class DashboardStatsResponse(APIResponseBase):
    date: date
    awb_summary: AwbDaySummary
    scanning_summary: ScanningDaySummary
    skid_summary: SkidDaySummary



