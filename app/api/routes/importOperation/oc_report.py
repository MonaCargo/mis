

from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile
from app.api import routes
from app.core.dependency import verify_token_and_get_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.importOperation.oc_report import BulkUploadResponse
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.importOperation.oc_report_service import OcReportService



router = APIRouter(prefix="/oc-report", tags=[])

@router.post("/upload", response_model=BulkUploadResponse)
async def upload_oc_report_file(
    file: UploadFile = File(...),
    cosys_report_date: str = Form(...),  # Add this parameter
    current_user: User = Depends(verify_token_and_get_user), 
    db: AsyncSession = Depends(get_db),

):
    """
    Upload CSV or Excel file and bulk insert OC report data
    """
    # Validate file type
    if not (file.filename.endswith('.csv') or 
            file.filename.endswith('.CSV') or 
            file.filename.endswith('.xlsx') or 
            file.filename.endswith('.xls')):
        raise HTTPException(
            status_code=400,
            detail="Invalid file type. Only CSV and Excel files are supported.",
            # message="Invalid file type. Only CSV and Excel files are supported."
        )
    
    # Determine file type
    file_type = "csv" if file.filename.lower().endswith('.csv') else "excel"

        # Validate and parse date
    try:
        report_date = datetime.strptime(cosys_report_date, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD format."
        )
    
    # Process and save
    result = await OcReportService.bulk_create_from_file_oc_report(
        db=db,
        file=file.file,
        file_type=file_type,
        cosys_report_date=report_date,  # Pass the date
        emp_id=current_user.emp_id
    )
    
    if not result.success:
        raise HTTPException(status_code=400, detail=result.message)
    
    return result

@router.get("/{report_id}")
async def get_oc_report(
    report_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get OC report by ID
    """
    try:
        # print(report_id,"kkkkkkkkkkkkkkkkkk")
        report = await OcReportService.get_by_id(db, report_id)
        if not report:
            raise HTTPException(
                status_code=404,
                detail=f"OC report with ID {report_id} not found"
            )
        return report
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")