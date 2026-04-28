"""
schemas/awb_history.py

All Pydantic response models for the AWB history endpoint.
Mirrors the DB model relationships exactly:
  AwbHistoryResponse
    └── AwbInfo
    └── List[SkidDetail]
          └── SkidHistoryTimeline  (location → base → uld per cycle)
          └── List[SequenceItem]
    └── List[FlightBookingDetail]
          └── List[UldDetail]
                └── List[UldLoadedItem]   (sequence-level, lazy/on-demand)
"""

from __future__ import annotations

from datetime import date, datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict


# ─────────────────────────────────────────────
# Shared / primitives
# ─────────────────────────────────────────────

class OrmBase(BaseModel):
    model_config = ConfigDict(from_attributes=True)


# ─────────────────────────────────────────────
# AWB master
# ─────────────────────────────────────────────

class AwbInfo(OrmBase):
    id: int
    awb_no: str
    origin: Optional[str]
    destination: Optional[str]

    sb_no: Optional[str]
    sb_date: Optional[datetime]

    hwb_no: Optional[str]

    pcs: Optional[int]
    gross_wt: Optional[float]
    volumetric_wt: Optional[float]
    chg_wt: Optional[float]

    nog: Optional[str]
    shc: Optional[str]

    status: Optional[str]
    agent: Optional[str]
    xray_type: Optional[str]
    source: Optional[str]

    is_ultra_fast: bool
    is_manually_created: bool
    manual_creation_remarks: Optional[str]
    remarks: Optional[str]

    rcs_datetime: Optional[datetime]
    car_message_datetime_combo: Optional[datetime]

    uploaded_by: Optional[str]
    created_at: datetime
    updated_at: datetime


# ─────────────────────────────────────────────
# Sequences  (scanned items inside a skid)
# ─────────────────────────────────────────────

class SequenceItem(OrmBase):
    id: int
    sequence_no: str
    sequence_date_time: datetime
    scanned_by: Optional[str]
    scanned_by_name: Optional[str]
    scan_by_device: Optional[str]


# ─────────────────────────────────────────────
# Skid history timeline steps
# ─────────────────────────────────────────────

class LocationStep(OrmBase):
    """One row from export_skid_location_mapping."""
    id: int
    location_id: int
    location_name: Optional[str]       # joined from export_locations_master
    assigned_at: datetime
    assigned_by: str
    assigned_by_name: Optional[str] = None
    is_current: bool
    is_relocation: bool
    picked_at: Optional[datetime]
    picked_by: Optional[str]
    picked_by_name: Optional[str] = None
    event_type: Optional[str] = None


class BaseDropStep(OrmBase):
    """One row from export_skid_base_mapping (one per cycle)."""
    id: int
    base_id: int
    base_name: Optional[str] = None         # joined from export_base_master
    cycle_no: int
    dropped_at: datetime
    dropped_by: str
    dropped_by_name: Optional[str] = None


class UldLoadedItem(OrmBase):
    """One sequence item loaded onto a ULD (export_item_uld_loading)."""
    id: int
    sequence_id: int
    sequence_no: str                   # joined from export_awb_skid_item_sequence
    loaded_by: str
    loaded_at: datetime


class UldStep(OrmBase):
    """ULD the skid's items were loaded into for a specific flight."""
    uld_assignment_detail_id: int
    uld_id: int
    uld_no: Optional[str]             # joined from export_uld_master
    uld_type: Optional[str]
    is_closed: bool
    closed_by: Optional[str]
    closed_at: Optional[datetime]
    flight_no: str                     # joined from export_flight_booking_header
    flight_date: date
    loaded_items: list[UldLoadedItem] = []


class SkidHistoryTimeline(OrmBase):
    """
    Full lifecycle of one skid for this AWB.
    Ordered chronologically: mapped → locations → base drops → uld loads.
    """
    mapped_at: Optional[datetime]
    mapped_by: Optional[str]
    is_virtual: bool
    virtual_skid_no: Optional[str]
    is_skid_used_complete: bool
    total_cycles: int                  # max(cycle_no) from base drops

    locations: list[LocationStep] = []
    base_drops: list[BaseDropStep] = []
    uld_loads: list[UldStep] = []
    mapped_by_name: Optional[str] = None


class SkidDetail(OrmBase):
    """One skid linked to the AWB."""
    mapping_id: int                    # export_awb_skid_mapping.id
    skid_id: Optional[int]
    skid_no: Optional[str]            # joined from export_skid_master
    virtual_skid_no: Optional[str]
    is_virtual: bool
    is_skid_used_complete: bool

    # Sequences scanned into this skid for this AWB
    sequences: list[SequenceItem] = []

    # Full history timeline
    history: SkidHistoryTimeline


# ─────────────────────────────────────────────
# Flight bookings
# ─────────────────────────────────────────────

class UldDetail(OrmBase):
    """ULD assigned to a flight, with items loaded for this AWB."""
    uld_assignment_detail_id: int
    uld_id: int
    uld_no: Optional[str]
    uld_type: Optional[str]
    is_closed: bool
    closed_by: Optional[str]
    closed_at: Optional[datetime]

    # Items from this AWB loaded onto this ULD
    loaded_items: list[UldLoadedItem] = []
    loaded_pcs: int = 0               # len(loaded_items) — computed


class FlightBookingDetail(OrmBase):
    """One flight booking for this AWB."""
    flight_header_id: int
    flight_no: str
    flight_date: date
    flight_dpt_datetime: datetime
    is_active: bool
    booked_by: str
    booked_at: datetime
    booked_pcs: int                   # from export_flight_booking_detail

    ulds: list[UldDetail] = []


# ─────────────────────────────────────────────
# Top-level response
# ─────────────────────────────────────────────

class AwbHistoryResponse(OrmBase):
    awb: AwbInfo
    skids: list[SkidDetail] = []
    flights: list[FlightBookingDetail] = []

    # Convenience summary
    total_skids: int = 0
    total_flights: int = 0
    total_booked_pcs: int = 0


# ─────────────────────────────────────────────
# Lightweight list response (for search / listing)
# ─────────────────────────────────────────────

class AwbListItem(OrmBase):
    id: int
    awb_no: str
    origin: Optional[str]
    destination: Optional[str]
    status: Optional[str]
    pcs: Optional[int]
    agent: Optional[str]
    rcs_datetime: Optional[datetime]
    is_ultra_fast: bool
    created_at: datetime