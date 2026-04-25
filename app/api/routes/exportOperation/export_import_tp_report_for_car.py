# """
# export_tp_xray_router.py
# ────────────────────────
# POST /upload-and-sync-export-tp-xray

# Accepts an Export TP X-RAY report (.xlsx / .xls / .csv), cleans it,
# and upserts the AWB rows into export_car_message_awb_master.
# """

# from fastapi import APIRouter, Depends, File, UploadFile, status, HTTPException
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.core.dependency import verify_token_and_get_user
# from app.db.models.exportOperation.export_fileupload_meta_log import ExportFileUploadMetaLog
# from app.db.session import get_db
# from app.schemas.exportOperation.export_import_tp_report_for_car import ExportTpXrayUploadResponse
# from app.services.exportOperation.export_import_tp_report_for_car import process_and_sync_export_tp_xray, process_and_sync_import_tp_xray
# from app.services.export_slot_file_upload_service import get_utc_now
# from app.db.session import engine

# # router = APIRouter(tags=["Export OR IMPORT TP X-RAY"])
# router = APIRouter()

# # ── constants ─────────────────────────────────────────────────────────────
# MAX_FILE_SIZE_BYTES = 10 * 1024 * 1024          # 10 MB

# # Maps content-type → file_type string passed to the cleaning function
# CONTENT_TYPE_MAP: dict[str, str] = {
#     "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet": "excel",  # .xlsx
#     "application/vnd.ms-excel":                                           "excel",  # .xls
#     "text/csv":                                                           "csv",    # .csv
#     "application/csv":                                                    "csv",
#     "text/plain":                                                         "csv",    # some clients send .csv as text/plain
# }

# # Fallback: derive file_type from filename extension when content-type is unreliable
# EXTENSION_MAP: dict[str, str] = {
#     ".xlsx": "excel",
#     ".xls":  "excel",
#     ".csv":  "csv",
# }


# async def _write_failure_log_tp_export(filename, file_type, file_track_type, uploaded_by, now, meta, error_message):
#     try:
#         async with AsyncSession(engine) as log_session:
#             async with log_session.begin():
#                 log_session.add(ExportFileUploadMetaLog(
#                     filename=filename,
#                     file_type=file_type,
#                     uploaded_by=uploaded_by,
#                     uploaded_at=now,
#                     file_track_type=file_track_type,
#                     status="FAILED",
#                     upload_meta=meta,
#                     error_message=str(error_message)[:500],
#                     created_at=now,
#                 ))
#     except Exception as log_err:
#         print(f"⚠️ Log write failed: {log_err}")

# def _resolve_file_type(content_type: str | None, filename: str | None) -> str | None:
#     """
#     Return 'excel' or 'csv' based on content-type first, then filename extension.
#     Returns None if the file type cannot be determined or is not supported.
#     """
#     if content_type and content_type in CONTENT_TYPE_MAP:
#         return CONTENT_TYPE_MAP[content_type]

#     if filename:
#         for ext, ftype in EXTENSION_MAP.items():
#             if filename.lower().endswith(ext):
#                 return ftype

#     return None


# @router.post(
#     "/upload-sync-export-tp-xray",
#     response_model=ExportTpXrayUploadResponse,
#     status_code=status.HTTP_200_OK,
#     summary="Upload Export TP X-RAY report and sync to database",
#     description=(
#         "Accepts an Export TP X-RAY report (.xlsx, .xls, or .csv), extracts all AWB records, "
#         "then upserts them into export_car_message_awb_master. "
#         "Existing AWBs are updated with fresh X-RAY / flight data while "
#         "manual overrides and remarks are preserved. "
#         "New AWBs are created. Rows with invalid AWB numbers are skipped."
#     ),
#     responses={
#         200: {"description": "File processed and database synced successfully"},
#         400: {"description": "Invalid file type, empty report, or corrupt data"},
#         413: {"description": "File exceeds 10 MB limit"},
#         500: {"description": "Unexpected error during extraction or sync"},
#     },
# )
# async def upload_and_sync_export_tp_xray(
#     db: AsyncSession = Depends(get_db),
#     file: UploadFile = File(...),
#     current_user=Depends(verify_token_and_get_user),
# ) -> ExportTpXrayUploadResponse:
    
#     now = get_utc_now()
#     filename = file.filename or "unknown"
#     emp_id = current_user.emp_id
#     file_type = "unknown"
#     try:
#         # ── 1. Read bytes first so empty-file check is always accurate ────────
#         file_bytes = await file.read()

#         if not file_bytes:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Uploaded file is empty.",
#             )

#         # ── 2. File-size guard ────────────────────────────────────────────────
#         if len(file_bytes) > MAX_FILE_SIZE_BYTES:
#             raise HTTPException(
#                 status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
#                 detail=f"File size {len(file_bytes) / 1_048_576:.1f} MB exceeds the 10 MB limit.",
#             )

#         # ── 3. Resolve file type (excel / csv) ────────────────────────────────
#         # content-type is checked first; filename extension is the fallback because
#         # browsers / HTTP clients sometimes send generic content-types for CSV files.
#         file_type = _resolve_file_type(file.content_type, file.filename)

#         if file_type is None:
#             raise HTTPException(status_code=400, detail="Unsupported file type")
        
#     # ── 4. Delegate to service ────────────────────────────────────────────
  
#         result = await process_and_sync_export_tp_xray(
#             file_bytes=file_bytes,
#             file_type=file_type,
#             uploaded_by=current_user.emp_id,      # adjust to your user model field
#             db=db,
#         )


#          # ✅ SUCCESS LOG (same like CAR)
#         db.add(ExportFileUploadMetaLog(
#             filename=filename,
#             file_type=file_type,
#             uploaded_by=emp_id,
#             uploaded_at=now,
#             file_track_type="EXPORT_TP_XRAY",   # 👈 IMPORTANT
#             status="SUCCESS",
#             upload_meta={
#                 "total_received": result.total_rows_in_file,
#                 "inserted": result.created,
#                 "updated": result.updated,
#                 "already_present": result.skipped,
#             },
#             error_message=None,
#             created_at=now(),
#         ))

#         await db.commit()
#         return result
    
#     # ❌ HTTP ERROR
#     except HTTPException as e:
#         await db.rollback()

#         await _write_failure_log_tp_export(
#             filename=filename,
#             file_type=file_type,
#             uploaded_by=emp_id,
#             now=now,
#             meta={
#                 "total_received": 0,
#                 "inserted": 0,
#                 "updated": 0,
#                 "already_present": 0,
#             },
#             error_message=str(e.detail),
#             file_track_type="EXPORT_TP_XRAY",
#         )
#         raise

#     # ❌ UNKNOWN ERROR
#     except Exception as e:
#         await db.rollback()

#         await _write_failure_log_tp_export(
#             filename=filename,
#             file_type=file_type,
#             uploaded_by=emp_id,
#             now=now,
#             meta={
#                 "total_received": 0,
#                 "inserted": 0,
#                 "updated": 0,
#                 "already_present": 0,
#             },
#             error_message=str(e),
#             file_track_type="EXPORT_TP_XRAY",
#         )

#         raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")






# # ========================================
# @router.post(
#     "/upload-sync-import-tp-xray",
#     response_model=ExportTpXrayUploadResponse,
#     status_code=status.HTTP_200_OK,
#     summary="Upload Import TP X-RAY report and sync to database",
#     description=(
#         "Accepts an Import TP X-RAY report (.xlsx, .xls, or .csv), extracts all AWB records, "
#         "then upserts them into export_car_message_awb_master. "
#         "Existing AWBs are updated with fresh flight/weight data while "
#         "manual overrides and remarks are preserved. "
#         "New AWBs are created. Manually created AWBs are skipped."
#     ),
#     responses={
#         200: {"description": "File processed and database synced successfully"},
#         400: {"description": "Invalid file type, empty report, or corrupt data"},
#         413: {"description": "File exceeds 10 MB limit"},
#         500: {"description": "Unexpected error during extraction or sync"},
#     },
# )
# async def upload_and_sync_import_tp_xray(
#     db: AsyncSession = Depends(get_db),
#     file: UploadFile = File(...),
#     current_user=Depends(verify_token_and_get_user),
# ) -> ExportTpXrayUploadResponse:
    
#     now = get_utc_now()
#     filename = file.filename or "unknown"
#     emp_id = current_user.emp_id
#     file_type = "unknown"
#     try:
 
#         # ── 1. Read & empty-file guard ────────────────────────────────────────
#         file_bytes = await file.read()
    
#         if not file_bytes:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Uploaded file is empty.",
#             )
    
#         # ── 2. File-size guard ────────────────────────────────────────────────
#         if len(file_bytes) > MAX_FILE_SIZE_BYTES:
#             raise HTTPException(
#                 status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
#                 detail=f"File size {len(file_bytes) / 1_048_576:.1f} MB exceeds the 10 MB limit.",
#             )
    
#         # ── 3. Resolve file type ──────────────────────────────────────────────
#         file_type = _resolve_file_type(file.content_type, file.filename)
    
#         if file_type is None:
#             raise HTTPException(status_code=400, detail="Unsupported file type")
    
#     # ── 4. Delegate to service ────────────────────────────────────────────
 
#         result = await process_and_sync_import_tp_xray(
#             file_bytes=file_bytes,
#             file_type=file_type,
#             uploaded_by=current_user.emp_id,
#             db=db,
#         )
#         response = result   # or build manually if needed
#             # ── 4. SUCCESS LOG ───────────────────────────
#         db.add(ExportFileUploadMetaLog(
#             filename=filename,
#             file_type=file_type,
#             uploaded_by=emp_id,
#             uploaded_at=now,
#             file_track_type="IMPORT_TP_XRAY",   # 🔥 ONLY CHANGE
#             status="SUCCESS",
#             upload_meta={
#                 "total_received": response.total_rows_in_file,
#                 "inserted": response.created,
#                 "updated": response.updated,
#                 "already_present": response.skipped,
#             },
#             error_message=None,
#             created_at=now,
#         ))

#         await db.commit()
#         return response
 
#     # ❌ HTTP ERROR
#     except HTTPException as e:
#         await db.rollback()

#         await _write_failure_log_tp_export(   # reuse same function
#             filename=filename,
#             file_type=file_type,
#             uploaded_by=emp_id,
#             now=now,
#             meta={
#                 "total_received": 0,
#                 "inserted": 0,
#                 "updated": 0,
#                 "already_present": 0,
#             },
#             error_message=str(e.detail),
#             file_track_type="IMPORT_TP_XRAY",   # 🔥 CHANGE HERE ALSO
#         )
#         raise


#     # ❌ UNKNOWN ERROR
#     except Exception as e:
#         await db.rollback()

#         await _write_failure_log_tp_export(
#             filename=filename,
#             file_type=file_type,
#             uploaded_by=emp_id,
#             now=now,
#             meta={
#                 "total_received": 0,
#                 "inserted": 0,
#                 "updated": 0,
#                 "already_present": 0,
#             },
#             error_message=str(e),
#             file_track_type="IMPORT_TP_XRAY",   # 🔥 CHANGE HERE ALSO
#         )

#         raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")






# =================== 🫥 SAVING IMPORT AND EXPORT TP DATA IN BUFFER TABLE ===============================




"""
routes/export_tp_xray_router.py

FastAPI router — Upload & persist the Export TP X-RAY report.

Endpoints
─────────
POST /export-tp-xray/upload
    Accepts a .xlsx or .csv file upload.
    Cleans the data, then replaces the month's records in Postgres.
    Returns a summary of what was deleted / inserted.

GET  /export-tp-xray/
    List all records (paginated, optional month filter).

GET  /export-tp-xray/{awb_no}
    All records for a specific AWB number across all months.
"""

from __future__ import annotations

from io import BytesIO
from typing import Annotated, Optional

from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile, status
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependency import verify_token_and_get_user
from app.db.models.exportOperation.export_fileupload_meta_log import ExportFileUploadMetaLog
from app.db.session import get_db
from app.services.exportOperation.export_import_tp_report_for_car import process_both_tp_to_car_message_master, upsert_export_tp_xray_month_data, upsert_import_tp_xray_month_data
from app.services.export_slot_file_upload_service import get_utc_now
from app.utils.exportOperation.export_tp_report_cleaning import clean_export_tp_xray
from app.utils.exportOperation.import_tp_report_cleaning import clean_import_tp_xray
from app.db.session import engine


router = APIRouter()


# ────────────────────────────────────────────────────────────────────────────
# Helper
# ────────────────────────────────────────────────────────────────────────────

def _detect_file_type(filename: str) -> str:
    name = (filename or "").lower()
    if name.endswith(".xlsx") or name.endswith(".xls"):
        return "excel"
    if name.endswith(".csv"):
        return "csv"
    raise HTTPException(
        status_code=status.HTTP_415_UNSUPPORTED_MEDIA_TYPE,
        detail="Only .xlsx, .xls, or .csv files are supported.",
    )

async def _write_failure_log_tp_report(filename, file_type,file_track_type, uploaded_by, now, meta, error_message):
    try:
        async with AsyncSession(engine) as log_session:
            async with log_session.begin():
                log_session.add(ExportFileUploadMetaLog(
                    filename=filename,
                    file_type=file_type,
                    uploaded_by=uploaded_by,
                    uploaded_at=now,
                    file_track_type=file_track_type,
                    status="FAILED",
                    upload_meta=meta,
                    error_message=str(error_message)[:500],
                    created_at=now,
                ))
    except Exception as log_err:
        print(f"⚠️ Log write failed: {log_err}")

# ────────────────────────────────────────────────────────────────────────────
# POST /export-tp-xray/upload
# ────────────────────────────────────────────────────────────────────────────

@router.post(
    "/export-tp-xray-file/upload",
    summary="Upload Export TP X-RAY report",
    status_code=status.HTTP_200_OK,
)
async def upload_xray_report(
    file: Annotated[UploadFile, File(description="Excel (.xlsx) or CSV report file")],
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Upload a monthly Export TP X-RAY report.

    - Detects file type from extension.
    - Cleans / normalises the data.
    - **Deletes** all existing rows for the report's month (derived from FROM DATE).
    - **Inserts** the fresh dataset.
    - Returns counts of deleted and inserted rows.

    Re-uploading the same month's file is safe and intentional — it replaces
    the previous data with the latest version.
    """
   

    now        = get_utc_now()                             # ✅ ADD
    filename   = file.filename or "unknown"                # ✅ ADD
    emp_id     = current_user.emp_id                       # ✅ ADD
    file_type  = "unknown"                                 # ✅ ADD — safe default for error log

        # ── Detect file type ─────────────────────────────────────────────────────
    try:
        file_type = _detect_file_type(file.filename)       # ✅ MOVE inside try
    except HTTPException:
        # Log unsupported file type then re-raise
        await _write_failure_log_tp_report(
            filename=filename,
            file_type=file_type,
            uploaded_by=emp_id,
            now=now,
            meta={"deleted": 0, "inserted": 0},
            error_message="Unsupported file type",
            file_track_type="EXPORT_TP_XRAY",
        )
        raise

    raw_bytes = await file.read()
    file_bytes = BytesIO(raw_bytes)


    # ── Clean ────────────────────────────────────────────────────────────────
    try:
        df, metadata = clean_export_tp_xray(file_bytes, file_type=file_type)
    except ValueError as exc:
        await _write_failure_log_tp_report(                # ✅ ADD failure log
            filename=filename,
            file_type=file_type,
            uploaded_by=emp_id,
            now=now,
            meta={"deleted": 0, "inserted": 0},
            error_message=str(exc),
            file_track_type="EXPORT_TP_XRAY",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    if df.empty:
        await _write_failure_log_tp_report(                # ✅ ADD failure log
            filename=filename,
            file_type=file_type,
            uploaded_by=emp_id,
            now=now,
            meta={"deleted": 0, "inserted": 0},
            error_message="No valid data rows found after cleaning (Empty).",
            file_track_type="EXPORT_TP_XRAY",
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid data rows found after cleaning.",
        )

    # ── Persist ──────────────────────────────────────────────────────────────
    try:
        summary = await upsert_export_tp_xray_month_data(db, df)
        # ✅ ADD — success log (before commit, same transaction)
        db.add(ExportFileUploadMetaLog(
            filename=filename,
            file_type=file_type,
            uploaded_by=emp_id,
            uploaded_at=now,
            file_track_type="EXPORT_TP_XRAY",
            status="SUCCESS",
            upload_meta={
                "deleted": summary["deleted_rows"],
                "inserted": summary["inserted_rows"],
                 "from_date"     : metadata.get("from_date"),
                "to_date"       : metadata.get("to_date"),
                "month_uploaded": summary["month_uploaded"],
            },
            error_message=None,
            created_at=now,
        ))

        await db.commit()
    except Exception as exc:
        await db.rollback()

        await _write_failure_log_tp_report(                # ✅ ADD failure log
            filename=filename,
            file_type=file_type,
            uploaded_by=emp_id,
            now=now,
            meta={"deleted": 0, "inserted": 0},
            error_message=str(exc),
            file_track_type="EXPORT_TP_XRAY",
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )

    return {
        "status"        : "success",
        "filename"      : file.filename,
        "month_uploaded": summary["month_uploaded"],
        "uploaded_at"   : df["uploaded_at"].iloc[0].isoformat(),
        "from_date"     : metadata.get("from_date"),
        "to_date"       : metadata.get("to_date"),
        "carrier"       : metadata.get("carrier"),
        "deleted_rows"  : summary["deleted_rows"],
        "inserted_rows" : summary["inserted_rows"],
    }






# APPEND this route at the bottom of the router file

@router.post(
    "/import-tp-xray-file/upload",
    summary="Upload Import TP X-RAY report",
    status_code=status.HTTP_200_OK,
)
async def upload_import_xray_report(
    file: Annotated[UploadFile, File(description="Excel (.xlsx) or CSV report file")],
    db: AsyncSession = Depends(get_db),
     current_user=Depends(verify_token_and_get_user), 
):
    
    now       = get_utc_now()                              # ✅ ADD
    filename  = file.filename or "unknown"                 # ✅ ADD
    emp_id    = current_user.emp_id                        # ✅ ADD
    file_type = "unknown"                                  # ✅ ADD — safe default
    
    # ── Detect file type ─────────────────────────────────────────────────────
    try:
        file_type = _detect_file_type(file.filename)
    except HTTPException:
        await _write_failure_log_tp_report(
            filename=filename,
            file_type=file_type,
            uploaded_by=emp_id,
            now=now,
            meta={"deleted": 0, "inserted": 0},
            error_message="Unsupported file type",
            file_track_type="IMPORT_TP_XRAY",              # ✅ ONLY DIFFERENCE
        )
        raise

    raw_bytes  = await file.read()
    file_bytes = BytesIO(raw_bytes)


    # ── Clean ────────────────────────────────────────────────────────────────
    try:
        df, metadata = clean_import_tp_xray(file_bytes, file_type=file_type)
    except ValueError as exc:
        await _write_failure_log_tp_report(
            filename=filename,
            file_type=file_type,
            uploaded_by=emp_id,
            now=now,
            meta={"deleted": 0, "inserted": 0},
            error_message=str(exc),
            file_track_type="IMPORT_TP_XRAY",              # ✅ ONLY DIFFERENCE
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(exc),
        )

    if df.empty:
        await _write_failure_log_tp_report(
            filename=filename,
            file_type=file_type,
            uploaded_by=emp_id,
            now=now,
            meta={"deleted": 0, "inserted": 0},
            error_message="No valid data rows found after cleaning.",
            file_track_type="IMPORT_TP_XRAY",              # ✅ ONLY DIFFERENCE
        )
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid data rows found after cleaning.",
        )

    try:
        summary = await upsert_import_tp_xray_month_data(db, df)
        # ✅ ADD — success log in same transaction
        db.add(ExportFileUploadMetaLog(
            filename=filename,
            file_type=file_type,
            uploaded_by=emp_id,
            uploaded_at=now,
            file_track_type="IMPORT_TP_XRAY",              # ✅ ONLY DIFFERENCE
            status="SUCCESS",
            upload_meta={
                "deleted": summary["deleted_rows"],
                "inserted": summary["inserted_rows"],
                "from_date"   : metadata.get("from_date"),
                "to_date"     : metadata.get("to_date"),
                "month_uploaded": summary["month_uploaded"],
            },
            error_message=None,
            created_at=now,
        ))


        await db.commit()
    except Exception as exc:
        await db.rollback()
        await _write_failure_log_tp_report(
            filename=filename,
            file_type=file_type,
            uploaded_by=emp_id,
            now=now,
            meta={"deleted": 0, "inserted": 0},
            error_message=str(exc),
            file_track_type="IMPORT_TP_XRAY",              # ✅ ONLY DIFFERENCE
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Database error: {exc}",
        )

    return {
        "status"        : "success",
        "filename"      : file.filename,
        "month_uploaded": summary["month_uploaded"],
        "uploaded_at"   : df["uploaded_at"].iloc[0].isoformat(),
        "from_date"     : metadata.get("from_date"),
        "to_date"       : metadata.get("to_date"),
        "carrier"       : metadata.get("carrier"),
        "deleted_rows"  : summary["deleted_rows"],
        "inserted_rows" : summary["inserted_rows"],
    }







# 🫥================== ✅Process and save in car message table from export tp xray table ✅=============🫥
# ======================================================================================================









@router.post(
    "/car-message/process/{month_uploaded}",
    summary="Process Import TP + Export TP into Car Message Master",
    status_code=status.HTTP_200_OK,
)
async def process_both_tp_month_to_car_master(
    month_uploaded: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Example:
        POST /car-message/process/2026-03

    Flow:
    -----
    STEP 1 → Process Import TP first

    STEP 2 → Process Export TP second

    STEP 3 → Save both into:

        export_car_message_awb_master

    Important:
    ----------
    - same month_uploaded used for both
    - same master table
    - one button triggers both processes
    - first car message datetime never changes
    """

    # basic validation
    if len(month_uploaded) != 7 or "-" not in month_uploaded:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month_uploaded must be in format YYYY-MM (example: 2026-03)",
        )

    try:
        summary = await process_both_tp_to_car_message_master(
            db=db,
            month_uploaded=month_uploaded,
            emp_id=current_user.emp_id,
        )

        await db.commit()

        return {
            "status": "success",
            "message": f"Import + Export TP month {month_uploaded} processed successfully",
            **summary,
        }

    except Exception as exc:
        await db.rollback()

        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(exc)}",
        )
    










# @router.post(
#     "/export-car-message/process/{month_uploaded}",
#     summary="Process Export TP month data into Car Message AWB Master",
#     status_code=status.HTTP_200_OK,
# )
# async def process_export_tp_month_to_car_master(
#     month_uploaded: str,
#     db: AsyncSession = Depends(get_db),
#     current_user = Depends(verify_token_and_get_user), 
# ):
#     """
#     Example:
#         POST /export-car-message-awb-master/process/2026-03


#     Purpose:
#     --------
#     Reads export_tp_xray data for the given month_uploaded
#     and saves/upserts grouped AWB data into:


#         export_car_message_awb_master


#     Rules handled by service:
#     -------------------------
#     - group by AWB
#     - sum pcs / gross_wt / chg_wt
#     - first occurrence for origin / destination / nog / shc
#     - first xray_start_datetime → car message datetime
#     - convert UTC → IST for car_msg_date + car_msg_time
#     - ON CONFLICT update for existing AWB
#     - first CAR message datetime never changes
#     """


#     # basic validation
#     if len(month_uploaded) != 7 or "-" not in month_uploaded:
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail="month_uploaded must be in format YYYY-MM (example: 2026-03)",
#         )


#     try:
#         summary = await process_export_tp_to_car_message_master(
#             db=db,
#             month_uploaded=month_uploaded,
#             emp_id = current_user.emp_id,
#         )


#         await db.commit()


#         return {
#             "status": "success",
#             "message": f"Export TP month {month_uploaded} processed successfully",
#             **summary,
#         }


#     except Exception as exc:
#         await db.rollback()


#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail=f"Processing failed: {str(exc)}",
#         )

