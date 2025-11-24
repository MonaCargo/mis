import csv
from datetime import date, datetime, timezone
import io
from typing import List, Optional,AsyncGenerator
from fastapi import APIRouter, Query, UploadFile, File, Depends, HTTPException
from fastapi.responses import StreamingResponse
import pytz
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.export_slot_file import ExportSlotFileRecord
from app.db.session import get_db
from app.schemas.export_slot_file import ExportSlotFileListResponse, ExportSlotFullResponse, ExportSlotUpdateTruckInTimeRequest, ExportSlotUpdateTruckOutTimeRequest
from app.schemas.user import UserRead
from app.services.export_slot_file_upload_service import ExportSlotService, generate_csv_rows_for_download_truck_in_out_by_stream,  get_daily_summary, get_export_slots_by_date_range, get_export_slots_by_specific_date, get_export_slots_search, handle_file_upload, mark_truck_out
from app.core.dependency import verify_token_and_get_user


router = APIRouter(prefix="", tags=["Export Slot File Upload || truck"])

@router.post("/upload_export_slot_file")
async def upload_file(
    file: UploadFile = File(...), # 👈 Match the frontend field name (like here is :- file)
    db: AsyncSession = Depends(get_db)
):
    result = await handle_file_upload(file, db)  # 👈 use the correct variable
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result


@router.get("/search", response_model=ExportSlotFileListResponse)
async def search_export_slots(
    truck_number: Optional[str] = Query(None, description="Exact truck number"),
    token_no: Optional[str] = Query(None, description="Exact token number"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Number of records per page (optional)"),
    offset: Optional[int] = Query(None, ge=0, description="Records to skip for pagination (optional)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Search export slot records by truck_number OR token_no (exact match).
    - One of truck_number or token_no must be provided.
    - If both provided, priority is truck_number.
    """
    if not (truck_number or token_no):
        raise HTTPException(status_code=400, detail="Please provide either truck number or token number")

    try:
        data, pagination = await get_export_slots_search(
            db=db,
            truck_number=truck_number,
            token_no=token_no,
            limit=limit,
            offset=offset,
        )

        return {
            "success": True,
            "message": f"Fetched {len(data)} record(s) successfully.",
            "data": data,
            "pagination": pagination,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching data: {str(e)}")


@router.get("/by-date", response_model=ExportSlotFileListResponse)
async def get_export_slots_by_date(
    date: Optional[datetime] = Query(None, description="Date (UTC, defaults to today)"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Number of records per page (optional)"),
    offset: Optional[int] = Query(None, ge=0, description="Records to skip for pagination (optional)"),
    istruckOut: Optional[bool] = Query(None, description="Filter by truck out status"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all export slot records for a specific date (UTC).
    Defaults to today's date if not provided.
    If limit/offset are not passed → return all records.
    """
    try:
        data, pagination = await get_export_slots_by_specific_date(
            db=db,
            date=date,
            limit=limit,
            offset=offset,
            truckOut=istruckOut
        )

        return {
            "success": True,
            "message": f"Fetched {len(data)} record(s) successfully for the selected date.",
            "data": data,
            "pagination": pagination,
        }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching date-based data: {str(e)}")




@router.get("/truck_in_with_date_range", response_model=ExportSlotFileListResponse)
async def export_slots_date_range(
    start_date: datetime = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: datetime = Query(..., description="End date in YYYY-MM-DD format"),
    limit: int = Query(20, ge=1, le=100, description="Number of records per page"),
    offset: int = Query(0, ge=0, description="Records to skip for pagination"),
    db: AsyncSession = Depends(get_db),
):
    """
    Fetch export slots between start_date and end_date (inclusive).
     Retrieves all records where isTruckIn is true within a given date range.
    Pagination supported.
    """

    if start_date > end_date:
        raise HTTPException(status_code=400, detail="start_date must be before end_date")

    data, pagination = await get_export_slots_by_date_range(
        db=db, start_date=start_date, end_date=end_date, limit=limit, offset=offset
    )

    return {
        "success": True,
        "message": f"Fetched {len(data)} record(s) successfully.",
        "data": data,
        "pagination": pagination,
    }

# ============================================================================================



@router.get("/download_truck_in_out_csv")
async def download_export_slots_csv(
    start_date: datetime = Query(..., description="Start date (YYYY-MM-DD or ISO format)"),
    end_date: datetime = Query(..., description="End date (YYYY-MM-DD or ISO format)"),
    db: AsyncSession = Depends(get_db),
):
    """
    Stream CSV download for export slots.
    Handles large datasets efficiently (up to 40,000+ rows).
    Each AWB gets its own row with parent slot information.
    """
    
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date must be before or equal to end_date"
        )
    
    # 🔧 FIX: Convert IST dates to UTC range
    ist_tz = pytz.timezone("Asia/Kolkata")
    
    # If dates are naive (no timezone), assume they're IST dates
    if start_date.tzinfo is None:
        start_date = ist_tz.localize(start_date.replace(hour=0, minute=0, second=0))
    if end_date.tzinfo is None:
        end_date = ist_tz.localize(end_date.replace(hour=23, minute=59, second=59))
    
    # Convert to UTC for database query
    start_date_utc = start_date.astimezone(pytz.UTC)
    end_date_utc = end_date.astimezone(pytz.UTC)
    
    # Generate filename with date range
    filename = f"truck_report_{start_date.strftime('%Y%m%d')}_{end_date.strftime('%Y%m%d')}.csv"
    
    return StreamingResponse(
        generate_csv_rows_for_download_truck_in_out_by_stream(db, start_date_utc, end_date_utc),
        media_type="text/csv",
        headers={
            "Content-Disposition": f"attachment; filename={filename}",
            "Cache-Control": "no-cache"
        }
    )










# =============================================================================================================
@router.post("/update_truck_in_time")
async def update_truck_in_time(
    request: ExportSlotUpdateTruckInTimeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),  # Get the current authenticated user
):
    service = ExportSlotService()

    print("🚚 Marking truck in:", request.truck_number, request.token_no, request.truck_slot_from)
    
    unresolved_slots = await service.get_unresolved_truck_ins(db, request.truck_number)
    print("⚠️ Unresolved slots:", unresolved_slots)
    if unresolved_slots:
        # Build structured response for unresolved slots
        unresolved_data = [
            {
                "truck_slot_from": slot_from.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ"),
                "truck_number": request.truck_number,
                "id": id,
                "is_truck_in": is_truck_in,
                "is_truck_out": is_truck_out,
            }
            for slot_from, id, is_truck_in, is_truck_out in unresolved_slots
        ]
        return {
            "success": False,
            "message": "Truck has unresolved mark-ins. Please mark out first.",
            "data": unresolved_data
        }
    # if unresolved_slots:
    #     return {
    #         "success": False,
    #         "message": "Truck has unresolved mark-ins. Please mark out first.",
    #         "data": [slot.strftime("%d-%b-%Y %H:%M") for slot in unresolved_slots]
    #     }

   # If emp_id is passed in the request, use it, else use the emp_id from the authenticated user (middleware)
    emp_id = request.emp_id if request.emp_id else current_user.emp_id
    print('--------------------------------',emp_id)
    slot_record = await service.mark_truck_in(
        db, request.truck_number, request.token_no, request.truck_slot_from, emp_id
    )
    if not slot_record:
        return {
            "success": False,
            "message": "No eligible slot data found for truck mark-in.",
            "data": []
        }

    return {
        "success": True,
        "message": "Truck marked in successfully.",
        "data": {
            "truck_in_time": slot_record.truck_in_date_time.strftime("%d-%b-%Y %H:%M"),
            "id": slot_record.id
        }
    }






@router.post("/update_truck_out_time")
async def update_truck_out_time(
    request: ExportSlotUpdateTruckOutTimeRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    emp_id = request.emp_id if request.emp_id else current_user.emp_id

    slot_record, message = await mark_truck_out(db, request.truck_number, request.truck_slot_from, emp_id)

    if not slot_record:
        return {
            "success": False,
            "message": message,
            "data": []
        }

    return {
        "success": True,
        "message": message,
        "data": {
            "truck_out_time": slot_record.truck_out_date_time.strftime("%d-%b-%Y %H:%M"),
            "id": slot_record.id
        }
    }


@router.get("/daily_summary")
async def daily_summary(
    summary_date: date = Query(default=date.today(), description="Date for summary in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db)
):
    summary = await get_daily_summary(db, summary_date)

    return {
        "status_code": 200,
        "success":True,
        "message": f"Summary for {summary_date.strftime('%d-%b-%Y')}",
        "summary": summary
    }