# app/routers/damage_report.py
from fastapi import APIRouter, Depends, File, Form, UploadFile, HTTPException, Request
from fastapi.responses import FileResponse
from sqlalchemy.ext.asyncio import AsyncSession
from typing import List, Optional
from datetime import datetime
import json
import os

from app.db.session import get_db
from app.schemas.user import UserRead
from app.services.importOperation.damage_report_service import DamageReportService
from app.schemas.importOperation.damage_report import (
    DamageReportCreate,
    DamageReportResponse,
    DamageReportListResponse,
    DamageReportCreateResponse,
    DamageReportUpdate,
    DamageReasonResponse,
    DamageReasonCreate
)
from app.core.dependency import verify_token_and_get_user  # Your auth dependency
from app.db.models.user import User  # Your user model
from app.db.models.importOperation.damage_report import DamageReport, DamageReportReason, DamageReason,DamageReportImage
from sqlalchemy import select, func

router = APIRouter(
    prefix="/damage-reports",
    tags=[""]
)


def get_user_info(request: Request, current_user: User) -> dict:
    """Extract user information for audit logging"""
    return {
        "emp_id": current_user.emp_id,
        "role": current_user.role,
        "ip_address": request.client.host if request.client else None,
        "device_id": request.headers.get("X-Device-ID"),
        "user_agent": request.headers.get("User-Agent")
    }


# ==================== DAMAGE REASON ENDPOINTS ====================

@router.get("/reasons", response_model=List[DamageReasonResponse])
async def get_damage_reasons(
    active_only: bool = True,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """
    Get all available damage reasons.
    
    **Query Parameters:**
    - active_only: If true, return only active reasons (default: true)
    """
    service = DamageReportService(db)
    reasons = await service.get_all_damage_reasons(active_only=active_only)
    return reasons


@router.post("/reasons", response_model=DamageReasonResponse)
async def create_damage_reason(
    reason_data: DamageReasonCreate,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """
    Create a new damage reason (Admin only).
    
    **Required Fields:**
    - reason_code: Unique code (e.g., "WET", "TORN")
    - reason_name: Display name (e.g., "Wet", "Torn/Teared")
    - description: Optional description
    """
    service = DamageReportService(db)
    reason = await service.create_damage_reason(
        reason_code=reason_data.reason_code,
        reason_name=reason_data.reason_name,
        description=reason_data.description
    )
    return reason


@router.get("/reasons/{reason_id}", response_model=DamageReasonResponse)
async def get_damage_reason(
    reason_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """Get a specific damage reason by ID"""
    service = DamageReportService(db)
    reason = await service.get_damage_reason_by_id(reason_id)
    
    if not reason:
        raise HTTPException(status_code=404, detail="Damage reason not found")
    
    return reason


# ==================== DAMAGE REPORT ENDPOINTS ====================

# @router.post("/create", response_model=DamageReportCreateResponse)
# async def create_damage_report(
#     request: Request,
#     worker_assignment_id:int = Form(...),
#     oc_no: str = Form(...),
#     location: str = Form(...),
#     emp_id: str = Form(...),
#     device_id: str = Form(...),
#     awb_no: str = Form(...),
#     hawb: Optional[str] = Form(None),
#     reason_ids: str = Form(...),  # JSON string of integer IDs
#     reported_at: str = Form(...),  # ISO format
#     remarks: Optional[str] = Form(None),
#     images: List[UploadFile] = File(...),
#     db: AsyncSession = Depends(get_db),
#     current_user: UserRead = Depends(verify_token_and_get_user)
# ):
#     """
#     Create a new damage report with images.
    
#     **Required Fields:**
#     - oc_no: Order confirmation number
#     - location: Location code where damage occurred
#     - emp_id: Employee ID reporting the damage
#     - reason_ids: JSON array of damage reason IDs (e.g., "[1, 2, 3]")
#     - reported_at: ISO 8601 timestamp
#     - images: 1-5 image files (JPEG/PNG, max 5MB each)
    
#     **Optional Fields:**
#     - remarks: Additional comments (max 500 chars)
#     """
#     try:
#         # Parse reason_ids from JSON string
#         reason_ids_list = json.loads(reason_ids)
        
#         # Validate it's a list of integers
#         if not isinstance(reason_ids_list, list) or not all(isinstance(i, int) for i in reason_ids_list):
#             raise ValueError("reason_ids must be a JSON array of integers")
        
#         # Parse reported_at timestamp
#         reported_datetime = datetime.fromisoformat(reported_at.replace('Z', '+00:00'))
        
#         # Create report data
#         report_data = DamageReportCreate(
#             worker_assignment_id=worker_assignment_id,
#             oc_no=oc_no,
#             awb_no=awb_no,
#             hawb=hawb,
#             location=location,
#             emp_id=emp_id,
#             device_id = device_id,
#             reason_ids=reason_ids_list,
#             remarks=remarks,
#             reported_at=reported_datetime
#         )
        
#         # Get user info for audit
#         user_info = get_user_info(request, current_user)
        
#         # Create damage report
#         service = DamageReportService(db)
#         db_report, saved_images = await service.create_damage_report(
#             report_data=report_data,
#             images=images,
#             user_info=user_info
#         )
        
#         return DamageReportCreateResponse(
#             success=True,
#             message="Damage report submitted successfully",
#             report_id=db_report.id,
#             image_count=len(saved_images)
#         )
        
#     except json.JSONDecodeError:
#         raise HTTPException(status_code=400, detail="Invalid reason_ids JSON format")
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.post("/create", response_model=DamageReportCreateResponse)
async def create_damage_report(
    request: Request,
    worker_assignment_id: int = Form(...),
    oc_no: str = Form(...),
    location: str = Form(...),
    emp_id: str = Form(...),
    device_id: str = Form(...),
    awb_no: str = Form(...),
    hawb: Optional[str] = Form(None),
    reason_ids: str = Form(...),  # JSON string of integer IDs
    reported_at: str = Form(...),  # ISO format
    remarks: Optional[str] = Form(None),
    images: Optional[List[UploadFile]] = File(None),  # ✅ CHANGE: Make images optional
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """
    Create or update a damage report.
    
    **For New Reports:**
    - At least 1 damage reason required
    - At least 1 image required
    
    **For Updates:**
    - At least 1 damage reason required (can add/remove)
    - Images optional (can add new images)
    - Remarks optional (can update)
    - Must have at least one change
    
    **Required Fields:**
    - worker_assignment_id: Worker assignment ID
    - oc_no: Order confirmation number
    - awb_no: AWB number
    - location: Location code where damage occurred
    - emp_id: Employee ID reporting the damage
    - device_id: Device ID
    - reason_ids: JSON array of damage reason IDs (e.g., "[1, 2, 3]")
    - reported_at: ISO 8601 timestamp
    
    **Optional Fields:**
    - hawb: House AWB number
    - remarks: Additional comments (max 500 chars)
    - images: 0-5 image files for updates, 1-5 for new reports (JPEG/PNG, max 5MB each)
    """
    try:
        # Parse reason_ids from JSON string
        reason_ids_list = json.loads(reason_ids)
        
        # Validate it's a list of integers
        if not isinstance(reason_ids_list, list) or not all(isinstance(i, int) for i in reason_ids_list):
            raise ValueError("reason_ids must be a JSON array of integers")
        
        # Validate at least one reason
        if not reason_ids_list:
            raise HTTPException(status_code=400, detail="At least one damage reason is required")
        
        # Parse reported_at timestamp
        reported_datetime = datetime.fromisoformat(reported_at.replace('Z', '+00:00'))
        
        # Create report data
        report_data = DamageReportCreate(
            worker_assignment_id=worker_assignment_id,
            oc_no=oc_no,
            awb_no=awb_no,
            hawb=hawb,
            location=location,
            emp_id=emp_id,
            device_id=device_id,
            reason_ids=reason_ids_list,
            remarks=remarks,
            reported_at=reported_datetime
        )
        
        # Get user info for audit
        user_info = get_user_info(request, current_user)
        
        # Create/update damage report
        service = DamageReportService(db)
        db_report, saved_images = await service.create_damage_report(
            report_data=report_data,
            images=images or [],  # ✅ CHANGE: Pass empty list if None
            user_info=user_info
        )
        
        return DamageReportCreateResponse(
            success=True,
            message="Damage report submitted successfully",
            report_id=db_report.id,
            image_count=len(saved_images)
        )
        
    except json.JSONDecodeError:
        raise HTTPException(status_code=400, detail="Invalid reason_ids JSON format")
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except HTTPException:
        raise  # Re-raise HTTPException as-is
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


@router.get("/oc/{oc_no}", response_model=DamageReportListResponse)
async def get_damage_reports_by_oc(
    oc_no: str,
    location: Optional[str] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """
    Get all damage reports for a specific order confirmation.
    
    **Optional Query Parameters:**
    - location: Filter by specific location
    """
    service = DamageReportService(db)
    reports = await service.get_damage_reports_by_oc(oc_no=oc_no, location=location)
    
    return DamageReportListResponse(
        total=len(reports),
        reports=reports
    )


@router.get("/employee/{emp_id}", response_model=DamageReportListResponse)
async def get_damage_reports_by_employee(
    emp_id: str,
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """
    Get all damage reports submitted by a specific employee.
    
    **Optional Query Parameters:**
    - start_date: Filter from this date (ISO 8601)
    - end_date: Filter until this date (ISO 8601)
    """
    service = DamageReportService(db)
    reports = await service.get_damage_reports_by_employee(
        emp_id=emp_id,
        start_date=start_date,
        end_date=end_date
    )
    
    return DamageReportListResponse(
        total=len(reports),
        reports=reports
    )


@router.get("/{report_id}", response_model=DamageReportResponse)
async def get_damage_report(
    report_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """Get a specific damage report by ID"""
    service = DamageReportService(db)
    report = await service.get_damage_report_by_id(report_id)
    
@router.put("/{report_id}", response_model=DamageReportResponse)
async def update_damage_report(
    report_id: int,
    update_data: DamageReportUpdate,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """
    Update an existing damage report.
    
    **Updatable Fields:**
    - reason_ids: List of damage reason IDs
    - remarks: Additional comments
    """
    user_info = get_user_info(request, current_user)
    service = DamageReportService(db)
    
    updated_report = await service.update_damage_report(
        report_id=report_id,
        update_data=update_data,
        user_info=user_info
    )
    
    return updated_report


@router.get("/image/{image_id}")
async def get_damage_image(
    image_id: int,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """
    Get a damage report image file.
    Returns the actual image file for display/download.
    """
    stmt = select(DamageReportImage).where(DamageReportImage.id == image_id)
    result = await db.execute(stmt)
    image = result.scalar_one_or_none()
    if not image:
        raise HTTPException(status_code=404, detail="Image not found")
    if not os.path.exists(image.image_url):
        raise HTTPException(status_code=404, detail="Image file not found on server")
    return FileResponse(
        path=image.image_url,
        media_type=image.mime_type or "image/jpeg",
        filename=image.image_name
    )
@router.get("/stats/summary")
async def get_damage_report_statistics(
    start_date: Optional[datetime] = None,
    end_date: Optional[datetime] = None,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    """
    Get damage report statistics for a date range.
    Returns:
    - Total reports
    - Reports by damage type
    - Reports by location
    - Top reporters
    """
    # Base query
    stmt = select(DamageReport)
    if start_date:
        stmt = stmt.where(DamageReport.reported_at >= start_date)
    if end_date:
        stmt = stmt.where(DamageReport.reported_at <= end_date)
    result = await db.execute(stmt)
    reports = result.scalars().all()
    total_reports = len(reports)
    # Get top locations
    loc_stmt = (
        select(
            DamageReport.location,
            func.count(DamageReport.id).label('count')
        )
        .group_by(DamageReport.location)
        .order_by(func.count(DamageReport.id).desc())
        .limit(10)
    )
    if start_date:
        loc_stmt = loc_stmt.where(DamageReport.reported_at >= start_date)
    if end_date:
        loc_stmt = loc_stmt.where(DamageReport.reported_at <= end_date)
    loc_result = await db.execute(loc_stmt)
    top_locations = loc_result.all()
    # Get top reporters
    emp_stmt = (
        select(
            DamageReport.emp_id,
            func.count(DamageReport.id).label('count')
        )
        .group_by(DamageReport.emp_id)
        .order_by(func.count(DamageReport.id).desc())
        .limit(10)
    )
    if start_date:
        emp_stmt = emp_stmt.where(DamageReport.reported_at >= start_date)
    if end_date:
        emp_stmt = emp_stmt.where(DamageReport.reported_at <= end_date)
    emp_result = await db.execute(emp_stmt)
    top_reporters = emp_result.all()
    return {
        "total_reports": total_reports,
        "top_locations": [{"location": loc, "count": cnt} for loc, cnt in top_locations],
        "top_reporters": [{"emp_id": emp, "count": cnt} for emp, cnt in top_reporters],
        "date_range": {
            "start": start_date.isoformat() if start_date else None,
            "end": end_date.isoformat() if end_date else None
        }
    }