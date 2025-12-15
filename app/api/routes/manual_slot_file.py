from fastapi import APIRouter, UploadFile, File, HTTPException, Depends,Query
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from sqlalchemy.orm import selectinload
from io import BytesIO
from typing import Optional
from datetime import datetime, timedelta
from app.db.models.manual_slot import ExportManualSlotFileRecord
from app.db.models.export_slot_file import ExportSlotAWB  # reuse AWB model if same structure
from app.db.session import get_db
from app.services.export_manual_slot_service import handle_manual_file_upload, mark_truck_in
from app.core.dependency import verify_token_and_get_user
from app.schemas.user import UserRead
from app.schemas.manulal_slot import ExportManualSlotFileListResponse, ExportManualSlotFileRecordResponse, TruckInRequest
from app.services.export_manual_slot_service import get_export_manual_slots_by_date



router = APIRouter()

@router.post("/upload_manual_slot_file")
async def upload_manual_file(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    result = await handle_manual_file_upload(file, db)
    if result.get("status") == "error":
        raise HTTPException(status_code=400, detail=result.get("message"))
    return result



@router.get("/export_manual_slots", response_model=ExportManualSlotFileListResponse)
async def get_export_manual_slots(
    date: Optional[datetime] = Query(None, description="Filter by specific date (IST). If omitted, defaults to today."),
    limit: Optional[int] = Query(None, description="Max number of records to return"),
    offset: Optional[int] = Query(None, description="Records offset for pagination"),
    truck_out_only: bool = Query(False, description="Filter only records where truck_out is True"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    try:
        data, pagination = await get_export_manual_slots_by_date(
            db=db,
            date=date,
            limit=limit,
            offset=offset,
            truck_out_only=truck_out_only,
        )
        return {"data": data, "pagination": pagination}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))
    

@router.put("/truck_in")
async def put_manual_slot_truck_in(
    request: TruckInRequest,
    current_user: UserRead = Depends(verify_token_and_get_user),
    db: AsyncSession = Depends(get_db),
):
    """
    PUT API to mark a truck as 'in' for a manual slot record.
    """
    print()
    try:
        record = await mark_truck_in(
            db=db,
            token_no=request.token_no,
            tc_no=request.tc_no,
            emp_id=request.emp_id,  # assuming UserRead has `id`
            truck_number=request.truck_number,
            truck_in_device = request.truck_in_device
        )

        # if not record:
        #     raise HTTPException(
        #         status_code=404,
        #         detail=f"No record found with token_no={request.token_no} and tc_no={request.tc_no}",
        #     )

        print("Record after truck in:", record)
        
        if not record:
            return {
            "success": False,
            "message": "No eligible slot data found for truck mark-in.",
            "data": []
        }

        return {
            "success": True,
            "message": "Truck marked in successfully.",
            # "record": record,
            "data": {
                "truck_in_time": record.truck_in_date_time,
                "id": record.id
            }
         }

        # return record
    except RuntimeError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Unexpected error: {str(e)}")
    