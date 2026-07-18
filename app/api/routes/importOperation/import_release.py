# from fastapi import APIRouter, Depends, File, HTTPException, UploadFile
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.db.session import get_db
# # from app.schemas.importOperation.irr_schemas import BulkUploadResponse
# from app.services.importOperation.import_release_service import IrrReportService


# router = APIRouter(prefix="/import-release", tags=[""])




# @router.post("/upload")
# async def upload_irr_report_file(
#     file: UploadFile = File(...),
#     db: AsyncSession = Depends(get_db)
# ):
#     """
#     Upload CSV or Excel file and bulk insert Import Release Report data
#     """
#     # Validate file type
#     if not (file.filename.endswith('.csv') or 
#             file.filename.endswith('.CSV') or 
#             file.filename.endswith('.xlsx') or 
#             file.filename.endswith('.xls')):
#         raise HTTPException(
#             status_code=400,
#             detail="Invalid file type. Only CSV and Excel files are supported."
#         )
    
#     file_type = "csv" if file.filename.lower().endswith('.csv') else "excel"
    
#     # Call the correct service method
#     result = await IrrReportService.delete_all_old_and_processfile_and_save_irr_data(
#         db=db,
#         file=file.file,
#         file_type=file_type
#     )
    
#     if not result.get('success', False):
#         raise HTTPException(status_code=400, detail="Failed to process file or save data")
    
#     return result






# ==========================================================================




from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, Form
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime
from app.core.dependency import verify_token_and_get_user
from app.db.session import get_db
from app.services.importOperation.import_release_service import IrrReportService

from app.db.models.user import User

router = APIRouter(prefix="/import-release", tags=[""])

@router.post("/upload")
async def upload_irr_report_file(
    file: UploadFile = File(...),
    cosys_report_date: str = Form(...),  # Add this parameter
    current_user: User = Depends(verify_token_and_get_user),  # Add this dependency
    db: AsyncSession = Depends(get_db)
):
    """
    Upload CSV or Excel file and bulk insert Import Release Report data
    """
    # Validate file type
    if not (
        # file.filename.endswith('.csv') or 
        #     file.filename.endswith('.CSV') or 
            file.filename.endswith('.xlsx') or 
            file.filename.endswith('.xls')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only Excel files are supported."
        )
    
    # Validate and parse date
    try:
        report_date = datetime.strptime(cosys_report_date, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD format."
        )
    
    file_type = "csv" if file.filename.lower().endswith('.csv') else "excel"
    
    # Call the service method with date and user info
    result = await IrrReportService.delete_all_old_and_processfile_and_save_irr_data(
        db=db,
        file=file.file,
        file_type=file_type,
        cosys_report_date=report_date,  # Pass the date
        uploaded_by=current_user.emp_id  # Pass the user ID
    )
    
    if not result.get('success', False):
        raise HTTPException(status_code=400, detail=result.get('message', 'Failed to process file or save data'))
    
    return result