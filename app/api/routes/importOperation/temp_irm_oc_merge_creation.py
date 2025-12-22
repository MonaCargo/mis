from fastapi import APIRouter, Depends, File, UploadFile, HTTPException, Form
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from typing import Optional

from app.db.session import get_db
from app.db.models.user import User
from app.services.importOperation.temp_irm_oc_creation_service import FastTrackIrmTemporaryOcMergeService
from app.schemas.importOperation.temp_irm_oc_merge_creation import FastTrackIRMOCMergeUploadResponse
from app.core.dependency import verify_token_and_get_user

router = APIRouter(prefix="/fast-track-temp-irm_oc_merge", tags=[""])


@router.post("/upload-and-process", response_model=FastTrackIRMOCMergeUploadResponse)
async def upload_fast_track_file(
    file: UploadFile = File(...),
    current_user: User = Depends(verify_token_and_get_user),
    db: AsyncSession = Depends(get_db),
):
    """
    Upload Excel file with AWB/HAWB data for fast-track processing.
    Creates temporary OC numbers (9XXXXXXXXX) for immediate processing.
    """
    # Validate file type
    if not (file.filename.endswith('.xlsx') or 
            file.filename.endswith('.xls') or
            file.filename.endswith('.csv') or
            file.filename.endswith('.CSV')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only Excel (.xlsx, .xls) and CSV files are supported."
        )
    
    # Determine file type
    file_type = "csv" if file.filename.lower().endswith('.csv') else "excel"
    
    # Process and save
    result = await FastTrackIrmTemporaryOcMergeService.bulk_create_from_file(
        db=db,
        file=file.file,
        file_type=file_type,
        uploaded_by=current_user.emp_id
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    
    return result

























# @router.post("/link-actual-oc")
# async def link_actual_oc(
#     awb_no: str = Form(...),
#     hawb: Optional[str] = Form(None),
#     actual_oc_no: str = Form(...),
#     oc_data: dict = Form(...),  # JSON string of OC data
#     current_user: User = Depends(verify_token_and_get_user),
#     db: AsyncSession = Depends(get_db),
# ):
#     """
#     Link an actual OC number to an existing fast-track record.
#     Called when the actual OC is created in the system.
#     """
#     result = await FastTrackIrmTemporaryOcMergeService.link_actual_oc(
#         db=db,
#         awb_no=awb_no,
#         hawb=hawb,
#         actual_oc_no=actual_oc_no,
#         oc_data=oc_data,
#         updated_by=current_user.emp_id
#     )
    
#     if not result["success"]:
#         raise HTTPException(status_code=400, detail=result["message"])
    
#     return result


# @router.get("/pending", response_model=PendingRecordsResponse)
# async def get_pending_fast_track_records(
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(verify_token_and_get_user),
# ):
#     """
#     Get all fast-track records that are waiting for actual OC linking.
#     """
#     result = await FastTrackIrmTemporaryOcMergeService.get_pending_records(db=db)
#     return result


# @router.get("/by-oc/{oc_no}", response_model=FastTrackRecordResponse)
# async def get_by_oc_number(
#     oc_no: str,
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(verify_token_and_get_user),
# ):
#     """
#     Get gatepass record by OC number (handles both temporary and actual OC).
#     """
#     result = await FastTrackIrmTemporaryOcMergeService.get_by_oc_number(db=db, oc_no=oc_no)
    
#     if not result:
#         raise HTTPException(status_code=404, detail=f"OC {oc_no} not found")
    
#     return result


# @router.get("/validate-oc/{oc_no}")
# async def validate_oc_number(oc_no: str):
#     """
#     Validate OC number format and identify if it's temporary or actual.
#     """
#     return FastTrackIrmTemporaryOcMergeService.validate_oc_format(oc_no)