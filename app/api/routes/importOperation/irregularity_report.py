



# # router.py
# from datetime import datetime
# from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

# from app.core.dependency import verify_token_and_get_user
# from app.db.models.user import User
# from app.db.session import get_db
# from app.services.importOperation.irregularity_report import IrregularitiesService
# from sqlalchemy.ext.asyncio import AsyncSession


# router = APIRouter(prefix="/irregularity_report", tags=[])

# @router.post("/upload")
# async def upload_irregularities_file(
#     file: UploadFile = File(...),
#     cosys_report_date: str = Form(...),  # Add this parameter
#     current_user: User = Depends(verify_token_and_get_user), 
#     db: AsyncSession = Depends(get_db)
# ):
#     """
#     Upload and process irregularities file (CSV or Excel).
#     File type is automatically detected from the file extension.
#     """
#     if not file.filename:
#         raise HTTPException(status_code=400, detail="No file provided")

#     filename = file.filename.lower()
#     if filename.endswith(".csv"):
#         file_type = "csv"
#     elif filename.endswith((".xlsx", ".xls")):
#         file_type = "excel"
#     else:
#         raise HTTPException(
#             status_code=400,
#             detail="Unsupported file type. Allowed: .csv, .xlsx, .xls"
#         )


#         # Validate and parse date
#     try:
#         report_date = datetime.strptime(cosys_report_date, '%Y-%m-%d').date()
#     except ValueError:
#         raise HTTPException(
#             status_code=400,
#             detail="Invalid date format. Use YYYY-MM-DD format."
#         )
    
    
#     try:
#         # Read file content
#         file_bytes = await file.read()

#         # Process uploaded file using static method (synchronous cleaning)
#         result = IrregularitiesService.process_uploaded_file(
#             file_bytes,
#             file.filename,
#             file_type,
#             cosys_report_date=report_date,  # Pass the date
#             emp_id=current_user.emp_id
#             )

#         if not result["success"]:
#             raise HTTPException(status_code=400, detail=result["message"])

#         # Save all cleaned records to DB (async)
#         save_result = await IrregularitiesService.delete_all_old_and_save_irregularities_filedata_to_db(
#             db,
#             records=result["all_records"]  # Now this key exists
#         )

#         return {
#             "message": result["message"],
#             "records_count": result["records_count"],
#             "sample_records": result["sample_records"],
#             "columns": result["columns"],
#             "db_save_result": save_result  # Return the full dict, not len()
#         }

#     except HTTPException:
#         raise
#     except Exception as e:
#         raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")








# ===========================================================================================

from datetime import datetime
from fastapi import APIRouter, Depends, File, Form, HTTPException, UploadFile

from app.core.dependency import verify_token_and_get_user
from app.db.models.user import User
from app.db.session import get_db
from app.services.importOperation.irregularity_report import IrregularitiesService
from sqlalchemy.ext.asyncio import AsyncSession


router = APIRouter(prefix="/irregularity_report", tags=[])

@router.post("/upload")
async def upload_irregularities_file(
    file: UploadFile = File(...),
    cosys_report_date: str = Form(...),
    current_user: User = Depends(verify_token_and_get_user), 
    db: AsyncSession = Depends(get_db)
):
    """
    Upload and process irregularities file (CSV or Excel).
    File type is automatically detected from the file extension.
    """
    if not file.filename:
        raise HTTPException(status_code=400, detail="No file provided")

    filename = file.filename.lower()
    if filename.endswith(".csv"):
        file_type = "csv"
    elif filename.endswith((".xlsx", ".xls")):
        file_type = "excel"
    else:
        raise HTTPException(
            status_code=400,
            detail="Unsupported file type. Allowed: .csv, .xlsx, .xls"
        )

    # Validate and parse date
    try:
        report_date = datetime.strptime(cosys_report_date, '%Y-%m-%d').date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD format."
        )
    
    try:
        # Read file content
        file_bytes = await file.read()

        # Single service call that handles both processing and saving
        result = await IrregularitiesService.delete_all_old_and_bulk_create_from_file(
            db=db,
            file=file_bytes,
            file_type=file_type,
            cosys_report_date=report_date,
            uploaded_by=current_user.emp_id
        )

        if not result["success"]:
            raise HTTPException(status_code=400, detail=result["message"])

        return {
            "message": result["message"],
            "records_count": result["total_records"],
            "inserted_records": result["inserted_records"],
            "sample_records": result.get("sample_records", []),
            "success": result["success"]
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")











