from io import BytesIO
from typing import Annotated

from fastapi import APIRouter, Depends, File, HTTPException, UploadFile, status
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependency import verify_token_and_get_user
from app.db.models.exportOperation.export_fileupload_meta_log import ExportFileUploadMetaLog
from app.db.session import get_db ,engine
from app.services.exportOperation.export_transipment_import_segrigation import process_seg_tranship_to_car_message_master, upsert_export_transhipment_month, upsert_import_segregation_report_month
from app.services.export_slot_file_upload_service import get_utc_now
from app.utils.exportOperation.export_transipment_report_cleaner import clean_export_transhipment_report
from app.utils.exportOperation.import_segrigation_report_cleaning import clean_import_segregation_report


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
        detail="Only .xlsx, or .CSV files are supported.",
    )

async def _write_failure_log_segrigation_transipment_report(filename, file_type,file_track_type, uploaded_by, now, meta, error_message):
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





# ======================

@router.post(
    "/segregation-report/upload",
    summary="Upload Import Segregation Report (TRM/TPV only)",
    status_code=status.HTTP_200_OK,
)
async def upload_segregation_report(
    file: Annotated[UploadFile, File(description="Excel (.xlsx) or CSV segregation report")],
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
):
    now      = get_utc_now()
    filename = file.filename or "unknown"
    emp_id   = current_user.emp_id
    file_type = "unknown"

    # ── Detect file type ──────────────────────────────────────────────────────
    try:
        file_type = _detect_file_type(file.filename)
    except HTTPException:
        await _write_failure_log_segrigation_transipment_report(
          
            filename      = filename,
            file_type     = file_type,
              file_track_type = "IMP_SEG_REPORT",
            uploaded_by   = emp_id,
            now           = now,
            meta          = {"deleted": 0, "inserted": 0},
            error_message = "Unsupported file type",
        )
        raise

    raw_bytes  = await file.read()
    file_bytes = BytesIO(raw_bytes)

    # ── Clean ─────────────────────────────────────────────────────────────────
    try:
        df, metadata = clean_import_segregation_report(file_bytes, file_type=file_type)
    except ValueError as exc:
        await _write_failure_log_segrigation_transipment_report(
      
            filename      = filename,
            file_type     = file_type,
              file_track_type = "IMP_SEG_REPORT",
            uploaded_by   = emp_id,
            now           = now,
            meta          = {"deleted": 0, "inserted": 0},
            error_message = str(exc),
        )
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail      = str(exc),
        )

    if df.empty:
        await _write_failure_log_segrigation_transipment_report(
        
            filename      = filename,
            file_type     = file_type,
              file_track_type = "IMP_SEG_REPORT",
            uploaded_by   = emp_id,
            now           = now,
            meta          = {"deleted": 0, "inserted": 0},
            error_message = "No TRM/TPV rows found after cleaning.",
        )
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail      = "No TRM/TPV rows found after cleaning.",
        )

    # ── Save to DB ────────────────────────────────────────────────────────────
    try:
        summary = await upsert_import_segregation_report_month(db, df)

        db.add(ExportFileUploadMetaLog(
            filename        = filename,
            file_type       = file_type,
            uploaded_by     = emp_id,
            uploaded_at     = now,
            file_track_type = "IMP_SEG_REPORT",
            status          = "SUCCESS",
            upload_meta     = {
                "deleted"        : summary["deleted_rows"],
                "inserted"       : summary["inserted_rows"],
                "from_date"      : metadata.get("from_date"),
                "to_date"        : metadata.get("to_date"),
                "month_uploaded" : summary["month_uploaded"],
            },
            error_message   = None,
            created_at      = now,
        ))

        await db.commit()

    except Exception as exc:
        await db.rollback()
        await _write_failure_log_segrigation_transipment_report(
        
            filename      = filename,
            file_type     = file_type,
              file_track_type = "IMP_SEG_REPORT",  # Import segrigation report
            uploaded_by   = emp_id,
            now           = now,
            meta          = {"deleted": 0, "inserted": 0},
            error_message = str(exc),
        )
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = f"Database error: {exc}",
        )

    return {
        "status"         : "success",
        "filename"       : file.filename,
        "month_uploaded" : summary["month_uploaded"],
        "uploaded_at"    : df["uploaded_at"].iloc[0].isoformat(),
        "from_date"      : metadata.get("from_date"),
        "to_date"        : metadata.get("to_date"),
        "deleted_rows"   : summary["deleted_rows"],
        "inserted_rows"  : summary["inserted_rows"],
    }



# ================== transipment report ===============================================================


@router.post(
    "/export-transhipment-report/upload",
    summary="Upload Export Transhipment Report (TRM/TPV only)",
    status_code=status.HTTP_200_OK,
)
async def upload_export_transhipment_report(
    file: Annotated[UploadFile, File(description=" (.xlsx or .CSV) transhipment report")],
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
):
    now       = get_utc_now()
    filename  = file.filename or "unknown"
    emp_id    = current_user.emp_id
    file_type = "unknown"
 
    # ── Detect file type ──────────────────────────────────────────────────────
    try:
        file_type = _detect_file_type(file.filename)
    except HTTPException:
        await _write_failure_log_segrigation_transipment_report(
        
            filename      = filename,
            file_type     = file_type,
            file_track_type= "EXP_TRANS_REPORT",
            uploaded_by   = emp_id,
            now           = now,
            meta          = {"deleted": 0, "inserted": 0},
            error_message = "Unsupported file type",
        )
        raise
 
    # This report is Excel-only
    # if file_type != "excel":
    #     await _write_failure_log_segrigation_transipment_report(
    #         db,
    #         filename      = filename,
    #         file_type     = file_type,
    #         file_track_type= "EXP_TRANS_REPORT",
    #         uploaded_by   = emp_id,
    #         now           = now,
    #         meta          = {"deleted": 0, "inserted": 0},
    #         error_message = "Only (.xlsx or .CSV) files are supported for this report.",
    #     )
    #     raise HTTPException(
    #         status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
    #         detail      = "Only (.xlsx or .CSV) files are supported for this report.",
    #     )
 
    raw_bytes  = await file.read()
    file_bytes = BytesIO(raw_bytes)
 
    # ── Clean ─────────────────────────────────────────────────────────────────
    try:
        df, metadata = clean_export_transhipment_report(file_bytes, file_type=file_type)
    except ValueError as exc:
        await _write_failure_log_segrigation_transipment_report(
            
            filename      = filename,
            file_type     = file_type,
            file_track_type= "EXP_TRANS_REPORT",
            uploaded_by   = emp_id,
            now           = now,
            meta          = {"deleted": 0, "inserted": 0},
            error_message = str(exc),
        )
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail      = str(exc),
        )
 
    if df.empty:
        await _write_failure_log_segrigation_transipment_report(
            filename      = filename,
            file_type     = file_type,
            file_track_type= "EXP_TRANS_REPORT",
            uploaded_by   = emp_id,
            now           = now,
            meta          = {"deleted": 0, "inserted": 0},
            error_message = "No TRM/TPV rows found after cleaning.",
        )
        raise HTTPException(
            status_code = status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail      = "No TRM/TPV rows found after cleaning.",
        )
 
    # ── Save to DB ────────────────────────────────────────────────────────────
    try:
        summary = await upsert_export_transhipment_month(db, df)
 
        db.add(ExportFileUploadMetaLog(
            filename        = filename,
            file_type       = file_type,
            uploaded_by     = emp_id,
            uploaded_at     = now,
            file_track_type = "EXP_TRANS_REPORT",
            status          = "SUCCESS",
            upload_meta     = {
                "deleted"        : summary["deleted_rows"],
                "inserted"       : summary["inserted_rows"],
                "from_date"      : str(metadata.get("from_date", "")),
                "to_date"        : str(metadata.get("to_date", "")),
                "month_uploaded" : summary["month_uploaded"],
            },
            error_message   = None,
            created_at      = now,
        ))
 
        await db.commit()
 
    except Exception as exc:
        await db.rollback()
        await _write_failure_log_segrigation_transipment_report(
        
            filename      = filename,
            file_type     = file_type,
            file_track_type= "EXP_TRANS_REPORT",
            uploaded_by   = emp_id,
            now           = now,
            meta          = {"deleted": 0, "inserted": 0},
            error_message = str(exc),
        )
        raise HTTPException(
            status_code = status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail      = f"Database error: {exc}",
        )
 
    return {
        "status"         : "success",
        "filename"       : file.filename,
        "month_uploaded" : summary["month_uploaded"],
        "uploaded_at"    : df["uploaded_at"].iloc[0].isoformat(),
        "from_date"      : str(metadata.get("from_date", "")),
        "to_date"        : str(metadata.get("to_date", "")),
        "deleted_rows"   : summary["deleted_rows"],
        "inserted_rows"  : summary["inserted_rows"],
    }





# === 🫥🫥 Imp Segrigation and Exp transipment two month process ========================


@router.post(
    "/seg-tranship/car-message/process/{month_uploaded}",
    summary="Process Import Segregation + Export Transhipment into Car Message Master",
    status_code=status.HTTP_200_OK,
)
async def process_seg_tranship_to_car_master(
    month_uploaded: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Example:
        POST /seg-tranship/car-message/process/2026-05
 
    Automatically includes previous month (2026-04) as well.
 
    Flow per month (prev first, current second):
        1. ImportSegregationReport  → source: IMP_SEGRATION
        2. ExportTranshipmentReport → source: EXP_TRANSHIP
 
    All results upsert into export_car_message_awb_master.
    Current month processes last so it wins on AWB conflict.
    """
    # Validate format
    try:
        from datetime import datetime
        datetime.strptime(month_uploaded, "%Y-%m")
    except ValueError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="month_uploaded must be in format YYYY-MM (example: 2026-05)",
        )
 
    try:
        summary = await process_seg_tranship_to_car_message_master(
            db=db,
            month_uploaded=month_uploaded,
            emp_id=current_user.emp_id,
        )
 
        await db.commit()
 
        return {
            "status" : "success",
            "message": (
                f"Segregation + Transhipment for "
                f"{summary['months_processed'][0]} and "
                f"{summary['months_processed'][1]} processed successfully"
            ),
            **summary,
        }
 
    except Exception as exc:
        await db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(exc)}",
        )