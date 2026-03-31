# app/schemas/export_skid_schema.py

# =================================== ✌️✌️✌️✌️✌️✌️✌️ ==================================================

from pydantic import BaseModel, field_validator
from typing import List, Optional
from datetime import datetime


# ──────────────────────────────────────────────────────────────
# SHARED
# ──────────────────────────────────────────────────────────────

class SkidInfoResponse(BaseModel):
    id: int
    skid_no: str
    skid_type: str
    skid_wgt: Optional[float] = None
    skid_capacity: Optional[float] = None

    class Config:
        from_attributes = True


# ──────────────────────────────────────────────────────────────
# GENERATE VIRTUAL SKID
# ──────────────────────────────────────────────────────────────

class GenerateVirtualSkidResponse(BaseModel):
    success: bool
    skid_id: int
    skid_no: str        # e.g. V00000001
    message: str


# ──────────────────────────────────────────────────────────────
# VALIDATE AND LOCK
# ──────────────────────────────────────────────────────────────

class SkidValidateAndLockRequest(BaseModel):
    awb_master_id: int
    skid_no: str        # scanned barcode OR auto-filled virtual skid_no


class SkidValidateAndLockResponse(BaseModel):
    success: bool
    message: str
    is_resumed: bool    # True → user resuming their own locked skid

    mapping_id: Optional[int] = None
    awb_master_id: int
    skid_id: int

    skid_info: SkidInfoResponse
    locked_at: datetime
    already_scanned_count: int   # > 0 only on resume




class ForceUnlockResponse(BaseModel):
    success: bool
    message: str
    skid_no: str
    skid_id: int
    was_locked: bool
    previously_locked_by: Optional[str] = None
    previously_locked_at: Optional[datetime] = None
    unlocked_by: str





# ──────────────────────────────────────────────────────────────
# 😊😊SCAN SEQUENCE ITEM  (single or bulk — always sent as array)
# ──────────────────────────────────────────────────────────────
class ScanSequenceItemInput(BaseModel):
    sequence_no: str
    sequence_date_time: datetime  # IST from frontend, converted to UTC in service


class ScanSequenceRequest(BaseModel):
    mapping_id: Optional[int]  = None            # from validate-and-lock response
    skid_id: Optional[int] = None   
    awb_master_id: int           # for duplicate check + pcs cap check
    sequence_nos: list[ScanSequenceItemInput]      # always array — single scan = array of 1
    is_final: bool = True    # ← added, default True so existing calls 

    scan_by_device: Optional[str] = None             # ← ADD
    scanned_by: Optional[str] = None                 # ← ADD (emp id, optional override)


class ScannedItemResponse(BaseModel):
    id: int
    sequence_no: str
    sequence_date_time: datetime
    scan_by_device: Optional[str] = None   # ← ADD
    scanned_by: Optional[str] = None       # ← ADD

    class Config:
        from_attributes = True


class ScanSequenceResponse(BaseModel):
    success: bool
    message: str

    inserted_count: int                       # how many were inserted this call
    mapping_id: Optional[int] 
    awb_master_id: int
    skipped_duplicates: list[str] = []   # ← ADD (list of "'{seq}' (AWB: xxx)" strings)
    total_scanned: int                        # count across full AWB after insert
    awb_total_pcs: Optional[float]            # awb.pcs for frontend progress X / Y
    items: list[ScannedItemResponse]          # full list for this mapping after insert
    is_unlocked: bool = False    # ← added, True only when is_final=True


# ──────────────────────────────────────────────────────────────
# DELETE SEQUENCE ITEM (wrong scan correction)
# ──────────────────────────────────────────────────────────────

class DeleteSequenceResponse(BaseModel):
    success: bool
    message: str
    deleted_sequence_no: str
    mapping_id: int
    total_scanned: int      # updated count after deletion
    items: list[ScannedItemResponse]  # updated full list after deletion





# ──────────────────────────────────────────────────────────────
# LOCATION ASSIGNMENT
# ──────────────────────────────────────────────────────────────

# class SkidBySequenceResponse(BaseModel):
#     sequence_no: str
#     skid_id: int
#     skid_no: str
#     skid_type: str          # "real" or "virtual" — frontend can show label
#     mapping_id: int
#     awb_master_id: int
#     awb_no: str
#     pcs:Optional[int] = None
#     scanned_count: int      # how many items on this skid total


# Virtual skid mapping location ------------------------

class SkidInfo(BaseModel):
    id: int
    skid_no: str
    skid_type: str
    skid_wgt: Optional[float] = None
    skid_capacity: Optional[float] = None
    is_active: bool
    is_locked: bool
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    is_virtual_used: bool


class SequenceItem(BaseModel):
    id: int
    sequence_no: str
    sequence_date_time: Optional[datetime] = None
    scan_by_device: Optional[str] = None
    scanned_by: Optional[str] = None


class MappingInfo(BaseModel):
    id: int
    awb_master_id: int
    is_virtual: bool
    virtual_skid_no: Optional[str] = None
    created_at: Optional[datetime] = None
    scanned_count: int
    current_location: Optional[str] = None
    sequences: list[SequenceItem] = []


class AwbInfo(BaseModel):
    id: int
    awb_no: str
    pcs: Optional[int] = None


# ── Main response ─────────────────────────────────────────────────
class SkidBySequenceResponse(BaseModel):
    success: bool
    message: str
    skid: SkidInfo
    mapping: Optional[MappingInfo] = None
    awb: Optional[AwbInfo] = None
# ====================

class AssignLocationRequest(BaseModel):
    skid_no: str                # scanned barcode or typed — works for both real/virtual
    location_id: int            # from dropdown select OR scanned location barcode
    awb_master_id: int          # which AWB context this assignment belongs to


class LocationInfoResponse(BaseModel):
    id: int
    loc: str
    area_code: str
    ops_type: str

    class Config:
        from_attributes = True


class AssignLocationResponse(BaseModel):
    success: bool
    message: str

    skid_location_mapping_id: int
    skid_id: int
    skid_no: str
    awb_master_id: int
    mapping_id: int              # scanning session mapping_id

    location: LocationInfoResponse
    assigned_at: datetime
    assigned_by: str
    is_current: bool
   

#    ==========================================================

# ═════════════════════════════════════════════════════════════════════
# SCHEMA — Skid info with recent mapping present 
# ═════════════════════════════════════════════════════════════════════

class SkidInfoSkidDetail(BaseModel):
    id: int
    skid_no: str
    skid_type: str
    skid_wgt: Optional[float] = None
    skid_capacity: Optional[float] = None
    is_active: bool
    is_locked: bool
    locked_by: Optional[str] = None
    locked_at: Optional[datetime] = None
    is_virtual_used: Optional[bool] = None

    class Config:
        from_attributes = True

class SkidInfoSequenceDetail(BaseModel):
    id: int
    sequence_no: str
    sequence_date_time: datetime
    scan_by_device: Optional[str] = None
    scanned_by: Optional[str] = None

    class Config:
        from_attributes = True


class SkidInfoMappingDetail(BaseModel):
    id: int
    awb_master_id: int
    is_virtual: Optional[bool] = None
    virtual_skid_no: Optional[str] = None
    created_at: Optional[datetime] = None
    scanned_count: int
    current_location: Optional[str] = None          # ← added
    sequences: List[SkidInfoSequenceDetail] = []    # ← added

    class Config:
        from_attributes = True


class SkidInfoAwbDetail(BaseModel):
    id: int
    awb_no: str
    pcs: Optional[int] = None
    wgt: Optional[float] = None
    dest: Optional[str] = None
    org: Optional[str] = None

    class Config:
        from_attributes = True


class SkidInfoResponse(BaseModel):
    success: bool
    message: str
    skid: SkidInfoSkidDetail
    mapping: Optional[SkidInfoMappingDetail] = None
    awb: Optional[SkidInfoAwbDetail] = None

    class Config:
        from_attributes = True







# Cretae new skid items in skid mstaer

class CreateSkidRequest(BaseModel):
    skid_no: str

    @field_validator("skid_no")
    @classmethod
    def skid_no_not_empty(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("Skid number cannot be empty")
        return v


class CreateSkidResponse(BaseModel):
    success: bool
    message: str
    data: dict