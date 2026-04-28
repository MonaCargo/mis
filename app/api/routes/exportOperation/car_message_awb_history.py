"""
routers/awb_history.py

All AWB history routes.

Prefix  : /api/export/awb
Tags    : ["AWB History"]

Routes
------
GET  /api/export/awb/                          → list AWBs (paginated, filtered)
GET  /api/export/awb/{awb_no}/history          → full history by AWB number  ← MAIN
GET  /api/export/awb/id/{awb_id}/history       → full history by DB id
GET  /api/export/awb/{awb_no}/skids            → only skid section (lighter)
GET  /api/export/awb/{awb_no}/skids/{mapping_id}/sequences   → sequences for one skid
GET  /api/export/awb/{awb_no}/flights          → only flight section (lighter)
GET  /api/export/awb/{awb_no}/flights/{flight_header_id}/ulds → ULDs for one flight
"""

from typing import Optional

from fastapi import APIRouter, Depends, HTTPException, Query, status

from app.db.session import get_db          # your AsyncSession dependency
from app.schemas.exportOperation.car_message_awb_history import (
    AwbHistoryResponse,
    AwbListItem,
    SkidDetail,
    SequenceItem,
    FlightBookingDetail,
    UldDetail,
)
from app.services.exportOperation.car_message_awb_history import AwbHistoryService, AwbNotFoundError

router = APIRouter()


# ─────────────────────────────────────────────────────────────
# Dependency — injects service with db session
# ─────────────────────────────────────────────────────────────

async def get_service(db=Depends(get_db)) -> AwbHistoryService:
    return AwbHistoryService(db)


def _handle_not_found(e: AwbNotFoundError) -> HTTPException:
    return HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(e))


# ─────────────────────────────────────────────────────────────
# 1. LIST  —  GET /api/export/awb/
# ─────────────────────────────────────────────────────────────

@router.get(
    "/",
    response_model=list[AwbListItem],
    summary="List AWBs",
    description=(
        "Paginated list of AWBs with optional filters. "
        "Uses partial DB indexes for RCS/TFD status filters."
    ),
)
async def list_awbs(
    status: Optional[str] = Query(None, description="Filter by status e.g. RCS, TFD"),
    agent: Optional[str] = Query(None),
    origin: Optional[str] = Query(None, max_length=10),
    destination: Optional[str] = Query(None, max_length=10),
    is_ultra_fast: Optional[bool] = Query(None),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    svc: AwbHistoryService = Depends(get_service),
):
    return await svc.list_awbs(
        status=status,
        agent=agent,
        origin=origin,
        destination=destination,
        is_ultra_fast=is_ultra_fast,
        limit=limit,
        offset=offset,
    )


# ─────────────────────────────────────────────────────────────
# 2. FULL HISTORY by AWB number  —  GET /api/export/awb/{awb_no}/history
# ─────────────────────────────────────────────────────────────

@router.get(
    "/{awb_no}/history",
    response_model=AwbHistoryResponse,
    summary="Full AWB history",
    description=(
        "Returns complete lifecycle of an AWB: master info, all skids with "
        "their location/base-drop/ULD timeline and scanned sequences, plus "
        "all flight bookings with ULD details."
    ),
)
async def get_awb_history(
    awb_no: str,
    svc: AwbHistoryService = Depends(get_service),
):
    try:
        return await svc.get_awb_history(awb_no)
    except AwbNotFoundError as e:
        raise _handle_not_found(e)


# ─────────────────────────────────────────────────────────────
# 3. FULL HISTORY by DB id  —  GET /api/export/awb/id/{awb_id}/history
# ─────────────────────────────────────────────────────────────

@router.get(
    "/id/{awb_id}/history",
    response_model=AwbHistoryResponse,
    summary="Full AWB history (by internal id)",
    description="Same as /{awb_no}/history but keyed by the DB primary key.",
)
async def get_awb_history_by_id(
    awb_id: int,
    svc: AwbHistoryService = Depends(get_service),
):
    try:
        return await svc.get_awb_by_id(awb_id)
    except AwbNotFoundError as e:
        raise _handle_not_found(e)


# ─────────────────────────────────────────────────────────────
# 4. SKIDS only  —  GET /api/export/awb/{awb_no}/skids
# ─────────────────────────────────────────────────────────────

@router.get(
    "/{awb_no}/skids",
    response_model=list[SkidDetail],
    summary="AWB skid details",
    description=(
        "Returns only the skid section for an AWB. "
        "Each skid includes its full history timeline and scanned sequences. "
        "Use this when you only need skid info (lighter than /history)."
    ),
)
async def get_awb_skids(
    awb_no: str,
    svc: AwbHistoryService = Depends(get_service),
):
    try:
        awb = await svc._fetch_awb(awb_no)
        return await svc._build_skid_details(awb.id)
    except AwbNotFoundError as e:
        raise _handle_not_found(e)


# ─────────────────────────────────────────────────────────────
# 5. SEQUENCES for one skid  —  GET /api/export/awb/{awb_no}/skids/{mapping_id}/sequences
# ─────────────────────────────────────────────────────────────

@router.get(
    "/{awb_no}/skids/{mapping_id}/sequences",
    response_model=list[SequenceItem],
    summary="Scanned sequences for one skid mapping",
    description=(
        "Returns all scanned item sequences for a specific skid mapping. "
        "Used when the user clicks 'Sequences' on a skid card."
    ),
)
async def get_skid_sequences(
    awb_no: str,
    mapping_id: int,
    svc: AwbHistoryService = Depends(get_service),
):
    try:
        awb = await svc._fetch_awb(awb_no)
        grouped = await svc._fetch_sequences_grouped(awb.id, [mapping_id])
        seqs = grouped.get(mapping_id, [])
        return [SequenceItem.model_validate(s) for s in seqs]
    except AwbNotFoundError as e:
        raise _handle_not_found(e)


# ─────────────────────────────────────────────────────────────
# 6. FLIGHTS only  —  GET /api/export/awb/{awb_no}/flights
# ─────────────────────────────────────────────────────────────

@router.get(
    "/{awb_no}/flights",
    response_model=list[FlightBookingDetail],
    summary="AWB flight bookings",
    description=(
        "Returns only the flight booking section for an AWB. "
        "Includes ULDs and loaded items per flight. "
        "Use this when the user clicks the 'Flights' section."
    ),
)
async def get_awb_flights(
    awb_no: str,
    svc: AwbHistoryService = Depends(get_service),
):
    try:
        awb = await svc._fetch_awb(awb_no)
        return await svc._build_flight_details(awb.id)
    except AwbNotFoundError as e:
        raise _handle_not_found(e)


# ─────────────────────────────────────────────────────────────
# 7. ULDs for one flight  —  GET /api/export/awb/{awb_no}/flights/{flight_header_id}/ulds
# ─────────────────────────────────────────────────────────────

@router.get(
    "/{awb_no}/flights/{flight_header_id}/ulds",
    response_model=list[UldDetail],
    summary="ULDs for one flight (AWB-scoped)",
    description=(
        "Returns ULD details for a specific flight, filtered to items "
        "belonging to this AWB only. Used for the ULD drill-down panel."
    ),
)
async def get_flight_ulds(
    awb_no: str,
    flight_header_id: int,
    svc: AwbHistoryService = Depends(get_service),
):
    try:
        awb = await svc._fetch_awb(awb_no)
        uld_map = await svc._fetch_ulds_for_flights(awb.id, [flight_header_id])
        return uld_map.get(flight_header_id, [])
    except AwbNotFoundError as e:
        raise _handle_not_found(e)
    



@router.get(
    "/{awb_no}/flights/{flight_header_id}/ulds/{uld_assignment_detail_id}/sequences",
    summary="Sequences for single ULD",
    description="Returns all sequence items loaded inside a specific ULD",
)
async def get_uld_sequences(
    awb_no: str,
    flight_header_id: int,
    uld_assignment_detail_id: int,
    svc: AwbHistoryService = Depends(get_service),
):
    try:
        awb = await svc._fetch_awb(awb_no)

        return await svc._get_uld_sequences_of_single_flight(
            awb.id,
            flight_header_id,
            uld_assignment_detail_id,
        )

    except AwbNotFoundError as e:
        raise _handle_not_found(e)