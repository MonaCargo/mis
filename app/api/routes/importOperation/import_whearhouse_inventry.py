
# # app/routes/import_release.py
# from datetime import datetime
# from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
# from fastapi.responses import JSONResponse
# import numpy as np
# from app.db.session import get_db
# from app.services.importOperation.import_whearhoouse_inventry import ImportWhereHouseInventryService
# from app.utils.importOperation.import_whearhouse_inventry import clean_airway_bill_file_advanced
# # from app.services.import_release_service import process_import_release_data
# from io import BytesIO
# import pandas as pd
# from typing import Optional
# from sqlalchemy.ext.asyncio import AsyncSession

# router = APIRouter(prefix="/import-wherehouse-inventry", tags=[])






# @router.post("/upload")
# async def process_airway_bill_file(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
#     """
#     Process Airway Bill Excel/CSV file and return cleaned data for inspection
#     """
#     try:
#         # Validate filename
#         if not file.filename:
#             raise HTTPException(status_code=400, detail="No file provided")

#         # Determine file type
#         file_extension = file.filename.split('.')[-1].lower()
#         file_type = "excel" if file_extension in ("xlsx", "xls") else "csv" if file_extension == "csv" else None

#         if not file_type:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Unsupported file type. Allowed: .xlsx, .xls, .csv"
#             )

#         # Read uploaded file to bytes
#         file_bytes = BytesIO(await file.read())

#         # Clean + Normalize
#         cleaned_data = clean_airway_bill_file_advanced(file_bytes, file_type)


#         # ✅ Check duplicate AWB numbers inside uploaded file
#         # awb_list = [row["awb_no"] for row in cleaned_data if row.get("awb_no")]
#         # duplicate_awbs = [awb for awb in set(awb_list) if awb_list.count(awb) > 1]

#                 # ✅ Save all records to DB
#         saved_count = await  ImportWhereHouseInventryService.delete_all_old_and_bulk_create_all_records(db, cleaned_data)

#         return {
#                 "success": True,
#                 "message": f"✅ Saved {saved_count} records to Warehouse Inventory (cleared old data)",
#                 "total_records_in_file": len(cleaned_data),
#                 # "duplicate_awbs": duplicate_awbs,
#                 "file_name": file.filename
#             }

#     except HTTPException:
#         raise
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Internal server error: {str(e)}"
#         )


# ============================================================================================  






from datetime import datetime
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import JSONResponse
import numpy as np
from app.core.dependency import verify_token_and_get_user
from app.db.session import get_db
from app.services.importOperation.import_whearhoouse_inventry import ImportWhereHouseInventryService
from app.utils.importOperation.import_whearhouse_inventry import clean_airway_bill_file_advanced
from io import BytesIO
import pandas as pd
from typing import Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User

router = APIRouter(prefix="/import-wherehouse-inventry", tags=[])

@router.post("/upload")
async def process_airway_bill_file(
    file: UploadFile = File(...),
    cosys_report_date: str = Form(...),
    current_user: User = Depends(verify_token_and_get_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Process import warehouse inventry Excel file and return cleaned data for inspection
    """
    try:
        # Validate filename
        if not file.filename:
            raise HTTPException(status_code=400, detail="No file provided")

        # Validate and parse date
        try:
            report_date = datetime.strptime(cosys_report_date, '%Y-%m-%d').date()
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD format."
            )

        # Determine file type
        file_extension = file.filename.split('.')[-1].lower()
        file_type = "excel" if file_extension in ("xlsx", "xls") else "csv" if file_extension == "csv" else None

        if not file_type:
            raise HTTPException(
                status_code=400,
                detail="Unsupported file type. Allowed: .xlsx, .xls, .csv"
            )

        # Read uploaded file to bytes
        file_bytes = BytesIO(await file.read())

        # Clean + Normalize
        cleaned_data = clean_airway_bill_file_advanced(file_bytes, file_type)

        # Add this check after cleaning data
        if not cleaned_data:
            return {
                "success": False,
                "message": "No valid records found in the file after cleaning",
                "total_records_in_file": 0,
                "inserted_records": 0
            }

        # ✅ Save all records to DB with date and user info
        save_result = await ImportWhereHouseInventryService.bulk_create_all_records_wharehouse_inventry(
            db=db,
            records_data=cleaned_data,
            cosys_report_date=report_date,
            uploaded_by=current_user.emp_id
        )

        if not save_result["success"]:
            raise HTTPException(status_code=400, detail=save_result["message"])

        return {
            "success": True,
            "message": save_result["message"],
            "total_records_in_file": len(cleaned_data),
            "inserted_records": save_result["inserted_records"],
            "file_name": file.filename,
            "report_date": cosys_report_date
        }

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )