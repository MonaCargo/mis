from datetime import date
from io import BytesIO
from typing import Any

from fastapi import APIRouter, HTTPException, Query, UploadFile, File, Depends
from sqlalchemy import func, select
from sqlalchemy.orm import Session
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependency import verify_token_and_get_user
from app.db.models.exportOperation.car_message import ExportAwbSkidItemSequence, ExportAwbSkidMapping, ExportCarMessageAwbMaster, ExportSkidLocationMapping
from app.db.models.exportOperation.export_location_master import ExportLocationsMaster
from app.db.models.exportOperation.export_skid_master import ExportSkidMaster
from app.db.session import get_db
from app.schemas.exportOperation.car_message import AvailableAwbForFlightBookingResponse, AvailableAwbForFlightBookingResponseList, CreateFlightBookingRequest, CreateFlightBookingResponse, CreateUldAssignmentRequest, DashboardStatsResponse, EditFlightBookingRequest, EditFlightBookingResponse, EditUldAssignmentRequest, FlightBookingByFlightResponse, FlightUldLoadingStatusResponse, RetrieveSkidFromLocationRequest, ScanItemIntoUldRequest, ScanItemIntoUldResponse, UldAssignmentDataResponse, UldAssignmentResponse, UldMasterResponse, UldVerifyForLoadingResponse
from app.schemas.user import UserRead
from app.services.exportOperation.car_message import create_flight_booking, create_uld_assignment, edit_flight_booking, edit_uld_assignment, enrich_awb_from_wh_inventory, generate_flight_date_report, get_available_awbs_for_flight_booking_dropdown, get_car_message_dashboard_stats, get_dashboard_drilldown_detail, get_flight_booking_by_flight_no_and_date, get_flight_full_detail, get_flight_uld_loading_status, get_flights_by_date, get_uld_assignment_by_flight, get_uld_master_list, get_uld_master_list_eligeble_for_assignment, retrieve_skid_from_location, save_export_car_message_awbs, scan_item_into_uld, verify_uld_for_loading
from app.utils.exportOperation.car_message import clean_car_message
from app.utils.exportOperation.wh_inventry_pdf_data_extract import extract_export_inventory


router = APIRouter(
    prefix="/car-message-awb",
    tags=[]
)


@router.post("/upload")
async def process_export_car_message_file(
    file: UploadFile = File(...),
    current_user = Depends(verify_token_and_get_user),
    db: AsyncSession = Depends(get_db)
):

    try:
        # ✅ Validate filename
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        # ✅ Detect file type
        file_extension = file.filename.split('.')[-1].lower()

        if file_extension in ("xlsx", "xls"):
            file_type = "excel"
        elif file_extension == "csv":
            file_type = "csv"
        else:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Allowed: .xlsx, .xls, .csv"
            )

        # ✅ Read file as bytes
        file_bytes = BytesIO(await file.read())

        # ✅ Clean file (returns cleaned + faulty)
        cleaned_df, faulty_df = clean_car_message(
            file_bytes,
            file_type
        )


        # ✅ Save using async ON CONFLICT service
        save_result = await save_export_car_message_awbs(
            db,
            cleaned_df,
            uploaded_by=current_user.emp_id,
        )

        return {
            "message": "File processed successfully",
            "success":True,
            **save_result,
            "faulty_rows_count": len(faulty_df),
        }

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )
    



# @router.get("/search/by-awb", summary="Search AWB by substring")
# async def search_awb(
#     q: str = Query(..., min_length=1, description="Substring to search in AWB no"),
#     db: AsyncSession = Depends(get_db),
# ):
    
    
#     async def search_awb_by_substring(
#         db: AsyncSession,
#         awb_substring: str,
#     ) -> list:
#         stmt = (
#             select(ExportCarMessageAwbMaster)
#             .where(ExportCarMessageAwbMaster.awb_no.ilike(f"%{awb_substring}%"))
#             .order_by(ExportCarMessageAwbMaster.created_at.desc())
#         )
#         result = await db.execute(stmt)
#         rows = result.scalars().all()
#         return rows

#     rows = await search_awb_by_substring(db, q.strip())

#     if not rows:
#         return {"message": "No records found.","success":True, "data": []}

#     return {
#         "message": f"{len(rows)} record(s) found.",
#         "success":True,
#         "data": [
#             {
#                 "id": r.id,
#                 "awb_no": r.awb_no,
#                 "origin": r.origin,
#                 "destination": r.destination,
#                 "sb_no": r.sb_no,
#                 "sb_date": r.sb_date,
#                 "pcs": r.pcs,
#                 "gross_wt": r.gross_wt,
#                 "chg_wt": r.chg_wt,
#                 "nog": r.nog,
#                 "car_msg_date": r.car_msg_date,
#                 "car_msg_time": r.car_msg_time,
#                 "created_at": r.created_at,
#             }
#             for r in rows
#         ],
#     }


@router.get("/search/by-awb", summary="Search AWB by exact match")
async def search_awb(
    q: str = Query(..., min_length=1, description="AWB no to search"),
    db: AsyncSession = Depends(get_db)
):
    from collections import defaultdict

    # ── 1. AWB + scanned count ────────────────────────────────────
    stmt = (
        select(
            ExportCarMessageAwbMaster,
            func.count(ExportAwbSkidItemSequence.id).label("scanned_pcs"),
        )
        .outerjoin(
            ExportAwbSkidItemSequence,
            ExportAwbSkidItemSequence.awb_master_id == ExportCarMessageAwbMaster.id,
        )
        .where(ExportCarMessageAwbMaster.awb_no == q.strip())
        .group_by(ExportCarMessageAwbMaster.id)
    )

    result = await db.execute(stmt)
    row = result.first()

    if not row:
        return {"success": False, "message": "No records found.", "data": None}
    

    awb = row.ExportCarMessageAwbMaster
    scanned_pcs = row.scanned_pcs

    # ── 2. Fetch all sequences for this AWB ───────────────────────
    seq_stmt = (
        select(ExportAwbSkidItemSequence)
        .where(ExportAwbSkidItemSequence.awb_master_id == awb.id)
        .order_by(
            ExportAwbSkidItemSequence.mapping_id,
            ExportAwbSkidItemSequence.sequence_no,
        )
    )
    seq_result = await db.execute(seq_stmt)
    sequences = seq_result.scalars().all()

    # Group sequences by mapping_id
    seq_by_mapping = defaultdict(list)
    for s in sequences:
        seq_by_mapping[s.mapping_id].append({
            "id": s.id,
            "sequence_no": s.sequence_no,
            "sequence_date_time": s.sequence_date_time,
            "scan_by_device": s.scan_by_device,
            "scanned_by": s.scanned_by,
        })

    # ── 3. Fetch all skids mapped to this AWB ─────────────────────
    skid_stmt = (
        select(ExportAwbSkidMapping, ExportSkidMaster)
        .join(
            ExportSkidMaster,
            ExportSkidMaster.id == ExportAwbSkidMapping.skid_id,
        )
        .where(ExportAwbSkidMapping.awb_master_id == awb.id)
        .order_by(ExportAwbSkidMapping.created_at.asc())
    )
    skid_result = await db.execute(skid_stmt)
    skid_rows = skid_result.all()

    # ── 4. Fetch current locations for all skids of this AWB ──────
    skid_ids = [sr.ExportSkidMaster.id for sr in skid_rows]

    current_location_map = {}
    if skid_ids:
        loc_stmt = (
            select(ExportSkidLocationMapping, ExportLocationsMaster)
            .join(
                ExportLocationsMaster,
                ExportLocationsMaster.id == ExportSkidLocationMapping.location_id,
            )
            .where(
                ExportSkidLocationMapping.skid_id.in_(skid_ids),
                ExportSkidLocationMapping.is_current == True,
            )
        )
        loc_result = await db.execute(loc_stmt)
        loc_rows = loc_result.all()

        for lr in loc_rows:
            current_location_map[lr.ExportSkidLocationMapping.skid_id] = lr.ExportLocationsMaster.loc

    return {
        "success": True,
        "message": "Record found.",
        "data": {
            # ── AWB master info ───────────────────────────────────
            "id": awb.id,
            "awb_no": awb.awb_no,
            "origin": awb.origin,
            "destination": awb.destination,
            "sb_no": awb.sb_no,
            "sb_date": awb.sb_date,
            "hwb_no": awb.hwb_no,
            "gross_wt": awb.gross_wt,
            "volumetric_wt": awb.volumetric_wt,
            "chg_wt": awb.chg_wt,
            "nog": awb.nog,
            "shc": awb.shc,
            "car_msg_date": awb.car_msg_date,
            "car_msg_time": awb.car_msg_time,
            "car_message_datetime_combo": awb.car_message_datetime_combo,
            "uploaded_by": awb.uploaded_by,
            "created_at": awb.created_at,
            "updated_at": awb.updated_at,

            # ── pcs summary ───────────────────────────────────────
            "total_pcs": awb.pcs,
            "scanned_pcs": scanned_pcs,
            "remaining_pcs": (awb.pcs - scanned_pcs) if awb.pcs is not None else None,
            "is_complete": (scanned_pcs >= awb.pcs) if awb.pcs is not None else False,

            # ── skids with sequences nested ───────────────────────
            "skids": [
                {
                    "mapping_id": sr.ExportAwbSkidMapping.id,
                    "skid_id": sr.ExportSkidMaster.id,
                    "skid_no": sr.ExportSkidMaster.skid_no,
                    "skid_type": sr.ExportSkidMaster.skid_type,
                    "is_virtual": sr.ExportAwbSkidMapping.is_virtual,
                    "virtual_skid_no": sr.ExportAwbSkidMapping.virtual_skid_no,
                    "is_locked": sr.ExportSkidMaster.is_locked,
                    "mapped_at": sr.ExportAwbSkidMapping.created_at,
                    "scanned_count": len(seq_by_mapping[sr.ExportAwbSkidMapping.id]),
                    "sequences": seq_by_mapping[sr.ExportAwbSkidMapping.id],
                    "current_location": current_location_map.get(sr.ExportSkidMaster.id, None),
                    
                }
                for sr in skid_rows
            ],
        },
    } 


@router.get("/all-awb-data", summary="Get all AWB master records")
async def get_all_awb(
    db: AsyncSession = Depends(get_db),
):
    stmt = (
        select(ExportCarMessageAwbMaster)
        .order_by(ExportCarMessageAwbMaster.created_at.desc())
    )

    result = await db.execute(stmt)
    rows = result.scalars().all()

    if not rows:
        return {
            "success": True,
            "message": "No records found.",
            "data": [],
        }

    return {
        "success": True,
        "message": f"{len(rows)} record(s) found.",
        "data": [
            {
                "id": r.id,
                "awb_no": r.awb_no,
                "origin": r.origin,
                "destination": r.destination,
                "sb_no": r.sb_no,
                "sb_date": r.sb_date,
                "pcs": r.pcs,
                "gross_wt": r.gross_wt,
                "chg_wt": r.chg_wt,
                "nog": r.nog,
                "car_msg_date": r.car_msg_date,
                "car_msg_time": r.car_msg_time,
                "created_at": r.created_at,
            }
            for r in rows
        ],
    }







# =========== ✌️ UPLOAD CAR message pdf wh inventry for fligh booking page ===================

@router.post("/wh-inventry-pdf/upload-extract-and-save")
async def upload_inventory_pdf(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename.lower().endswith(".pdf"):
        raise HTTPException(status_code=400, detail="Only PDF files allowed")

    contents = await file.read()  # ← read once here

    if len(contents) > 10 * 1024 * 1024:
        raise HTTPException(status_code=400, detail="File too large (Max 10MB)")

    # ✅ Wrap already-read bytes in BytesIO — do NOT use file.file again
    import io
    df = extract_export_inventory(io.BytesIO(contents))

    if df.empty:
        raise HTTPException(status_code=400, detail="No valid records found")

    print(df.head(3))

    result = await enrich_awb_from_wh_inventory(db, df)


    return {
        "success": True,
        "message": "PDF processed successfully.",
        "total_in_pdf":    result["total_in_pdf"],
        "matched_updated": result["matched"],
        "not_found_count": result["not_found_count"],
        "not_found_awbs":  result["not_found"],
    }




# ======✌️ Get those awb which is allowed to select in flight booking screen dropdown 
@router.get(
    "/flight-booking/available-awbs",
    response_model=AvailableAwbForFlightBookingResponseList,
    summary="AWBs available for flight booking",
)
async def get_available_awbs(
    db: AsyncSession = Depends(get_db),
):
    try:
        data =  await get_available_awbs_for_flight_booking_dropdown(
            db=db,
        )

        return AvailableAwbForFlightBookingResponseList(
            success=True,
            message="Get all valid and availble awb for flight booking",
            data = data
        )
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    


# ✌️======Create new flight booking =============== 
@router.post(
    "/flight-booking/create",
    response_model=CreateFlightBookingResponse,
    summary="Create a new flight booking",
    status_code=201
)
async def create_booking(
    payload: CreateFlightBookingRequest,
    db: AsyncSession = Depends(get_db),
    current_user:UserRead= Depends(verify_token_and_get_user),
):
    
    return await create_flight_booking(db=db, payload=payload, booked_by=current_user.emp_id)




# Edit flight booking 
@router.get(
    "/flight-booking/by-flt-no-and-date",
    response_model=FlightBookingByFlightResponse,
    summary="Get flight booking by flight number and date",
)
async def get_booking_by_flight(
    flight_no: str = Query(..., description="e.g. AI101"),
    flight_date: date = Query(..., description="e.g. 2026-03-16"),
    db: AsyncSession = Depends(get_db),
):
    return await get_flight_booking_by_flight_no_and_date(
        db=db,
        flight_no=flight_no,
        flight_date=flight_date,
    )


# ✌️ Edit flight booking--------=====
@router.patch(
    "/flight-booking/{header_id}/edit",
    response_model=EditFlightBookingResponse,
    summary="Edit an existing flight booking",
)
async def edit_booking(
    header_id: int,
    payload: EditFlightBookingRequest,
    db: AsyncSession = Depends(get_db),
     current_user:UserRead= Depends(verify_token_and_get_user),
   
):
    return await edit_flight_booking(
        db=db,
        header_id=header_id,
        payload=payload,
        edited_by=current_user.emp_id,
    )

# =================== ✌️ ULD ASSIGNMENT ✌️ ========================================

@router.get("/uld-assignment/uld-master", response_model=list[UldMasterResponse])
async def get_uld_master(db: AsyncSession = Depends(get_db)):
    return await get_uld_master_list(db=db)


@router.get("/uld-assignment/uld-master/eligible-for-uld-assignment", response_model=list[UldMasterResponse])
async def get_uld_master(db: AsyncSession = Depends(get_db)):
    return await get_uld_master_list_eligeble_for_assignment(db=db)


@router.get("/uld-assignment/by-flight", response_model=UldAssignmentDataResponse | None, description="GET CREATED ULD ASSIGNMENT BY FLIGHT NO. AND FLIGHT DATE")
async def get_assignment_by_flight(
    flight_no: str = Query(...),
    flight_date: date = Query(...),
    db: AsyncSession = Depends(get_db),
):
    return await get_uld_assignment_by_flight(
        db=db,
        flight_no=flight_no,
        flight_date=flight_date,
    )


@router.post("/uld-assignment/create", response_model=UldAssignmentResponse, status_code=201)
async def create_assignment(
    payload: CreateUldAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user:UserRead= Depends(verify_token_and_get_user),
):
    
    return await create_uld_assignment(db=db, payload=payload, assigned_by=current_user.emp_id)


@router.patch("/uld-assignment/{assignment_id}/edit", response_model=UldAssignmentResponse)
async def edit_assignment(
    assignment_id: int,
    payload: EditUldAssignmentRequest,
    db: AsyncSession = Depends(get_db),
    current_user:UserRead= Depends(verify_token_and_get_user),
):
  
    return await edit_uld_assignment(
        db=db,
        assignment_id=assignment_id,
        payload=payload,
        edited_by=current_user.emp_id,
    )


# ========================= ✌️ Skid retrival from location ==============================


@router.get(
"/flight-booking/get-all-flight/by-date",
summary="Get all booked flights on a particular date",
)
async def get_flights_by_date_route(
    flight_date: date = Query(..., description="e.g. 2026-03-16"),
    db: AsyncSession = Depends(get_db),
):
    return await get_flights_by_date(db=db, flight_date=flight_date)


@router.get(
    "/flight-booking/{header_id}/full-flight-detail",
    summary="Get full flight detail — AWBs + skids + sequences + ULDs",
)
async def get_flight_full_detail_route(
    header_id: int,
    db: AsyncSession = Depends(get_db),
):
    return await get_flight_full_detail(db=db, header_id=header_id)

@router.patch(
    "/skid/retrieve",
    summary="Retrieve skid from its current location by mapping id",
)
async def retrieve_skid(
    payload: RetrieveSkidFromLocationRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
):
    return await retrieve_skid_from_location(
        db=db,
        mapping_id=payload.mapping_id,
        retrieved_by=current_user.emp_id,
    )





# ===============👌👌 EXPORT ULD/PALLET LOADING BY SCANNING SEQUENCE [LAST STEP OF PROCESS]====================

# ── 1. Verify ULD ──────────────────────────────────────────
@router.get(
    "/flight/{flight_header_id}/uld-loading/verify-uld",
    response_model=UldVerifyForLoadingResponse,
    summary="Verify ULD belongs to flight before scanning",
)
async def verify_uld_for_loading_route(
    flight_header_id: int,
    uld_no: str = Query(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    return await verify_uld_for_loading(db=db, flight_header_id=flight_header_id, uld_no=uld_no)


# ── 2. Scan item into ULD ──────────────────────────────────
@router.post(
    "/flight/{flight_header_id}/uld-loading/scan-item",
    response_model=ScanItemIntoUldResponse,
    summary="Scan item barcode into selected ULD",
    status_code=201,
)
async def scan_item_into_uld_route(
    flight_header_id: int,
    payload: ScanItemIntoUldRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    return await scan_item_into_uld(
        db=db,
        flight_header_id=flight_header_id,
        payload=payload,
        loaded_by=current_user.emp_id,
    )


# ── 3. Get loading status ──────────────────────────────────
@router.get(
    "/flight/{flight_header_id}/uld-loading/status",
    response_model=FlightUldLoadingStatusResponse,
    summary="Get ULD loading status for flight",
)
async def get_loading_status_route(
    flight_header_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    return await get_flight_uld_loading_status(db=db, flight_header_id=flight_header_id)









# ======================================= car message report related ====================


@router.get(
    "/flight-date-report",
    summary="Download full flight report by date as Excel",
)
async def download_flight_date_report(
    # flight_date: date = Query(..., description="e.g. 2026-03-20"),
    from_date: date = Query(..., description="e.g. 2026-03-20"),
    to_date: date = Query(..., description="e.g. 2026-03-25"),
    db: AsyncSession = Depends(get_db),
):
    return await generate_flight_date_report(db=db, from_date=from_date,to_date=to_date)





@router.get(
    "/dashboard/stats",
    # response_model=DashboardStatsResponse,
    summary="Get dashboard stats for a selected IST date",
)
async def get_dashboard_stats_route(
    report_date: date = Query(..., description="IST date e.g. 2026-03-20"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    return await get_car_message_dashboard_stats(db=db, report_date=report_date)



@router.get(
    "/dashboard/drilldown/detail",
    summary="Get drilldown detail for a dashboard stat box",
)
async def get_dashboard_detail_route(
    report_date: date = Query(..., description="IST date e.g. 2026-03-20"),
    detail_type: str = Query(
        ...,
        description="all_awbs | rcs_awbs | non_rcs_awbs | scanned_awbs | used_skids"
    ),
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    return await get_dashboard_drilldown_detail(
        db=db,
        report_date=report_date,
        detail_type=detail_type,
    )
