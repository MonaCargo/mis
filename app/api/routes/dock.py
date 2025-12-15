from datetime import datetime
from typing import List, Optional
from fastapi import APIRouter, Depends, Query
from fastapi import APIRouter, Depends, HTTPException, status
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.export_slot_file import AWBSequenceResponse, AddAWBSequenceRequest, AddAWBSequenceResponse, ExportSlotFileListResponseForDock, ExportSlotFullResponse
from app.schemas.user import UserRead
from app.services.dock_service import DockService
from app.schemas.dock import DockInRevertResponse, DockOutRequest, DockOutResponse, DockScanRequest, DockScanResponse, RevertDockInRequest
from app.core.dependency import verify_token_and_get_user

router = APIRouter()

@router.post("/scan", response_model=DockScanResponse)
async def dock_scan_in(
    scan_data: DockScanRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),  # Get the current authenticated user
):
    """
    Route for dock scan-in
    """
    try:
        print("scan data====================================",scan_data.dict())
        print("scan data====================================",scan_data)
        # Use emp_id from request if provided, else fallback to current_user
        user_id = scan_data.emp_id or current_user.emp_id
        data = await DockService.process_dock_scan(db, scan_data, emp_id=user_id)

        return DockScanResponse(
            success=True,
            message="Dock scan successful",
            data = data
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))


@router.post("/dock-out", response_model=DockOutResponse)
async def dock_out(
    scan_data: DockOutRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    """
    Route for dock-out
    """
    print("scan_data req in dockout",scan_data)
    try:
        emp_id = scan_data.emp_id or current_user.emp_id
        data = await DockService.process_dock_out(db, scan_data, emp_id=emp_id)

        return DockOutResponse(
            success=True,
            message="Dock out successful",
            data=data
        )

    except ValueError as e:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail=str(e))
    except RuntimeError as e:
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=str(e))
    

@router.put("/awb/add-sequences", response_model=AddAWBSequenceResponse)
async def add_awb_sequences(
    request: AddAWBSequenceRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    """
    Add multiple AWBs + sequences for a specific truck/export slot.
    - Creates missing AWBs
    - Adds multiple sequence scans per AWB
    - Validates truck-in and dock-in status
    """
    # print(request,"REQ")
    data = await DockService.add_awb_sequences(db, request,emp_id=current_user.emp_id)
    return AddAWBSequenceResponse(
            success=True,
            message="AWB sequences added successfully",
            data=data
    )


@router.put(
    "/revert-dock-in",
    description="If truck is already docked in, revert it to allow fresh dock-in"
)
async def revert_dock_in(
    request: RevertDockInRequest,  # 👈 Body JSON
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """
    Revert dock-in process (update) for a truck.
    Allowed only if:
    - Truck is docked in
    - Truck is NOT docked out
    - Truck is NOT checked out
    """
    data = await DockService.revert_dock_in(
        db=db,
        token_no=request.token_no,
        truck_number=request.truck_number,
        truck_slot_from=request.truck_slot_from,
        emp_id=current_user.emp_id
    )

    return DockInRevertResponse(
            success=True,
            message="Dock in updated successfully",
            data=data

    )




# -------------------------------------------

@router.get("/by-date", response_model=ExportSlotFileListResponseForDock)
async def get_export_slots_by_date(
    date: Optional[datetime] = Query(None, description="Date (UTC, defaults to today)"),
    limit: Optional[int] = Query(None, ge=1, le=100, description="Number of records per page (optional)"),
    offset: Optional[int] = Query(None, ge=0, description="Records to skip for pagination (optional)"),
    isdockOut: Optional[bool] = Query(None, description="Filter by dock out status"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get all export slot records for a specific date (UTC).
    Defaults to today's date if not provided.
    If limit/offset are not passed → return all records.
    """
    try:
        data, pagination = await DockService.get_truck_slots_by_specific_date(
            db=db,
            date=date,
            limit=limit,
            offset=offset,
            dockOut=isdockOut
        )

        if not data:
            return {
                "success": True,
                "message": "No records found for the selected date.",
                "data": [],
                "pagination": pagination,
            }

        return {
            "success": True,
            "message": f"Fetched {len(data)} record(s) successfully for the selected date.",
            "data": data,
            "pagination": pagination,
        }

        # return {
        #     "success": True,
        #     "message": f"Fetched {len(data)} record(s) successfully for the selected date.",
        #     "data": data,
        #     "pagination": pagination,
        # }

    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Error fetching date-based data: {str(e)}")