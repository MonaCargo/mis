
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
from pathlib import Path
from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException
from fastapi.responses import FileResponse, JSONResponse
import numpy as np
from app.core.dependency import verify_token_and_get_user
from app.db.session import get_db
from app.services.importOperation.import_whearhoouse_inventry import ImportWhereHouseInventryService
from app.utils.importOperation.import_whearhouse_inventry import clean_airway_bill_file_advanced
from io import BytesIO
import pandas as pd
from typing import Any, Dict, Optional
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User

router = APIRouter(prefix="/import-wherehouse-inventry", tags=[""])

# @router.post("/upload")
# async def process_airway_bill_file(
#     file: UploadFile = File(...),
#     cosys_report_date: str = Form(...),
#     current_user: User = Depends(verify_token_and_get_user),
#     db: AsyncSession = Depends(get_db)
# ):
#     """
#     Process import warehouse inventry Excel file and return cleaned data for inspection
#     """
#     try:
#         # Validate filename
#         if not file.filename:
#             raise HTTPException(status_code=400, detail="No file provided")

#         # Validate and parse date
#         try:
#             report_date = datetime.strptime(cosys_report_date, '%Y-%m-%d').date()
#         except ValueError:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Invalid date format. Use YYYY-MM-DD format."
#             )

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

#         # Add this check after cleaning data
#         if not cleaned_data:
#             return {
#                 "success": False,
#                 "message": "No valid records found in the file after cleaning",
#                 "total_records_in_file": 0,
#                 "inserted_records": 0
#             }

#         # ✅ Save all records to DB with date and user info
#         save_result = await ImportWhereHouseInventryService.bulk_create_all_records_wharehouse_inventry(
#             db=db,
#             records_data=cleaned_data,
#             cosys_report_date=report_date,
#             uploaded_by=current_user.emp_id
#         )

#         if not save_result["success"]:
#             raise HTTPException(status_code=400, detail=save_result["message"])

#         return {
#             "success": True,
#             "message": save_result["message"],
#             "total_records_in_file": len(cleaned_data),
#             "inserted_records": save_result["inserted_records"],
#             "file_name": file.filename,
#             "report_date": cosys_report_date
#         }

#     except HTTPException:
#         raise
#     except ValueError as e:
#         raise HTTPException(status_code=400, detail=str(e))
#     except Exception as e:
#         raise HTTPException(
#             status_code=500,
#             detail=f"Internal server error: {str(e)}"
#         )


@router.post("/upload")
async def process_airway_bill_file(
    file: UploadFile = File(...),
    cosys_report_date: str = Form(...),
    current_user: User = Depends(verify_token_and_get_user),
    db: AsyncSession = Depends(get_db)
) -> Dict[str, Any]:
    """
    Process import warehouse inventory Excel file and return cleaned data for inspection.
    Also identifies and reports any faulty rows found during processing.
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

        # ✅ Clean + Normalize (now returns tuple: records and faulty_df)
        cleaned_data, faulty_df = clean_airway_bill_file_advanced(file_bytes, file_type)

            # ✅ Log faulty records to file
        if not faulty_df.empty:
            log_faulty_records(faulty_df, file.filename)

        # Prepare faulty rows information
        row_indices = [(i + 8) for i in faulty_df.index.tolist()]
        faulty_rows_info = None
        if not faulty_df.empty:
            faulty_rows_info = {
                "count": len(faulty_df),
                "row_indices": row_indices,
                "row_values": faulty_df.to_dict(orient="records"),
                "summary": f"{len(faulty_df)} faulty row(s) detected and excluded from processing"
            }

        # Check if any valid records exist after cleaning
        if not cleaned_data:
            return {
                "success": False,
                "message": "No valid records found in the file after cleaning",
                "total_records_in_file": 0,
                "inserted_records": 0,
                "faulty_rows_removed_before_insertion": faulty_rows_info,
                "file_name": file.filename,
                "report_date": cosys_report_date
            }

        # ✅ Save all valid records to DB with date and user info
        save_result = await ImportWhereHouseInventryService.bulk_create_all_records_wharehouse_inventry(
            db=db,
            records_data=cleaned_data,
            cosys_report_date=report_date,
            uploaded_by=current_user.emp_id
        )

        if not save_result["success"]:
            raise HTTPException(status_code=400, detail=save_result["message"])

        # ✅ Return comprehensive response including faulty rows info
        response = {
            "success": True,
            "message": save_result["message"],
            "total_records_in_file": len(cleaned_data),
            "inserted_records": save_result["inserted_records"],
            "file_name": file.filename,
            "report_date": cosys_report_date
        }

        # Add faulty rows information if any were found
        if faulty_rows_info:
            response["faulty_rows"] = faulty_rows_info
            response["message"] = f"{save_result['message']}. Note: {faulty_rows_info['summary']}"

        return response

    except HTTPException:
        raise
    except ValueError as e:
        raise HTTPException(status_code=400, detail=str(e))
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Internal server error: {str(e)}"
        )




# Define log directory
LOG_DIR = Path("logs")
LOG_DIR.mkdir(exist_ok=True)

def log_faulty_records(faulty_df: pd.DataFrame, file_name: str) -> None:
    """
    Log faulty records to a date-specific log file with detailed information.
    
    Args:
        faulty_df: DataFrame containing faulty records
        file_name: Name of the uploaded file
    """
    if faulty_df.empty:
        return
    
    # Get current date for log filename
    current_date = datetime.now().strftime('%Y-%m-%d')
    log_file_path = LOG_DIR / f"log_{current_date}.txt"
    
    # Get current timestamp
    current_time = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    row_indices = [(i + 8) for i in faulty_df.index.tolist()]
    # Prepare log entry
    log_entry = []
    log_entry.append("=" * 100)
    log_entry.append("WAREHOUSE INVENTORY - FAULTY RECORDS DETECTED")
    log_entry.append("=" * 100)
    log_entry.append(f"Timestamp: {current_time}")
    log_entry.append(f"File Name: {file_name}")
    log_entry.append(f"Total Faulty Records: {len(faulty_df)}")
    log_entry.append(f"Faulty Row Indices: {faulty_df.index.tolist()}")
    log_entry.append("-" * 100)
    log_entry.append("\nRECORD DETAILS:")
    log_entry.append("-" * 100)
    
    # Add each faulty record with details
    for idx, (row_idx, row_data) in enumerate(faulty_df.iterrows(), 1):
        log_entry.append(f"\n[Faulty Record #{idx}]")
        log_entry.append(f"Original Row Index: {row_idx+8}")
        log_entry.append("Values:")
        
        # Format each column and its value
        for col, val in row_data.items():
            # Handle None/NaN values
            if pd.isna(val):
                val_str = "NULL"
            else:
                val_str = str(val)
            log_entry.append(f"  - {col}: {val_str}")
        
        log_entry.append("-" * 50)
    
    log_entry.append("\n" + "=" * 100 + "\n\n")
    
    # Write to log file (append mode)
    with open(log_file_path, 'a', encoding='utf-8') as f:
        f.write('\n'.join(log_entry))
    
    print(f"📝 Faulty records logged to: {log_file_path}")


router.get("/faulty-logs/{date}")
async def get_faulty_logs(
    date: str,
    current_user: User = Depends(verify_token_and_get_user)
) -> Dict[str, Any]:
    """
    Retrieve faulty records log for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format
    
    Returns:
        Log file content or error message
    """
    try:
        # Validate date format
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD format."
            )
        
        log_file_path = LOG_DIR / f"log_{date}.txt"
        
        if not log_file_path.exists():
            return {
                "success": False,
                "message": f"No faulty records log found for date: {date}",
                "date": date
            }
        
        # Read log file content
        with open(log_file_path, 'r', encoding='utf-8') as f:
            log_content = f.read()
        
        return {
            "success": True,
            "date": date,
            "log_content": log_content,
            "file_path": str(log_file_path)
        }
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error retrieving log: {str(e)}"
        )


@router.get("/faulty-logs/{date}/download")
async def download_faulty_logs(
    date: str,
    # current_user: User = Depends(verify_token_and_get_user)
):
    """
    Download faulty records log file for a specific date.
    
    Args:
        date: Date in YYYY-MM-DD format
    
    Returns:
        FileResponse: Log file for download
    """
    try:
        # Validate date format
        try:
            datetime.strptime(date, '%Y-%m-%d')
        except ValueError:
            raise HTTPException(
                status_code=400,
                detail="Invalid date format. Use YYYY-MM-DD format."
            )
        
        log_file_path = LOG_DIR / f"log_{date}.txt"
        
        if not log_file_path.exists():
            raise HTTPException(
                status_code=404,
                detail=f"No faulty records log found for date: {date}"
            )
        
        # Return file for download
        return FileResponse(
            path=str(log_file_path),
            filename=f"warehouse_inventory_faulty_records_{date}.txt",
            media_type="text/plain",
            headers={
                "Content-Disposition": f"attachment; filename=warehouse_inventory_faulty_records_{date}.txt"
            }
        )
    
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Error downloading log: {str(e)}")