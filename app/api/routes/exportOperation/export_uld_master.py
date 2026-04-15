# from typing import Any, Dict, List

# from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
# from sqlalchemy.orm import Session

# from app.db.models.exportOperation.export_uld_master import ExportUldMaster
# from app.db.session import get_db
# from app.utils.common.helperFunction import get_utc_now
# from app.utils.exportOperation.export_uld_master_cleaner import parse_uld_excel


# router = APIRouter(prefix="/export-uld", tags=["Export ULD Master"])






# # service function to upload uld data in db
# def upsert_uld_records(db: Session, records: List[Dict[str, str]]) -> Dict[str, Any]:
#     """Insert new ULD records; skip duplicates (uld_no is unique)."""
#     now = get_utc_now()
#     inserted = 0
#     skipped = 0

#     for record in records:
#         uld_no = record["uld_no"]
#         existing = db.query(ExportUldMaster).filter_by(uld_no=uld_no).first()

#         if existing:
#             skipped += 1
#             continue

#         db.add(ExportUldMaster(
#             uld_no=uld_no,
#             carrier=record["carrier"],
#             is_active=True,
#             created_at=now,
#             updated_at=now,
#         ))
#         inserted += 1

#     db.commit()
#     return {"inserted": inserted, "skipped": skipped, "total": len(records)}



# @router.post("/upload", summary="Upload Excel to bulk insert ULD master records")
# async def upload_uld_excel(
#     file: UploadFile = File(...),
#     db: Session = Depends(get_db),
# ):
#     # Validate file type
#     if not file.filename.endswith((".xlsx", ".xls")):
#         raise HTTPException(status_code=400, detail="Only .xlsx or .xls files are accepted.")

#     file_bytes = await file.read()

#     try:
#         records = parse_uld_excel(file_bytes)
#     except ValueError as e:
#         raise HTTPException(status_code=422, detail=str(e))

#     if not records:
#         raise HTTPException(status_code=400, detail="No valid rows found in the uploaded file.")

#     result = upsert_uld_records(db, records)

#     return {
#         "message": "Upload complete.",
#         "inserted": result["inserted"],
#         "skipped_duplicates": result["skipped"],
#         "total_rows_processed": result["total"],
#     }
















import io
import math

import pandas as pd
from sqlalchemy import select
from typing import Any, Dict, List, Optional

from fastapi import APIRouter, Depends, HTTPException, Query, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.core.dependency import verify_token_and_get_user
from app.db.models.exportOperation.export_fileupload_meta_log import ExportFileUploadMetaLog
from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.db.session import get_db
from app.schemas.domesticOperation.domestic_xray_report import PaginationMetadata
from app.schemas.exportOperation.car_message import UldStockRecord, UldStockSyncResponse
from app.schemas.exportOperation.location_master import CreateUldRequest
from app.services.exportOperation.uld_master_service import MultipleCarriersError, UldStockSyncService
from app.utils.common.helperFunction import get_utc_now
from app.utils.exportOperation.export_uld_master_cleaner import parse_uld_excel
from app.utils.exportOperation.extract_uld_inventry_pdf import extract_uld_stock

from app.db.session import engine

router = APIRouter(prefix="/export-uld", tags=["Export ULD Master"])


async def upsert_uld_records(db: AsyncSession, records: List[Dict[str, str]]) -> Dict[str, Any]:
    now = get_utc_now()

    rows = [
        {
            "uld_no": r["uld_no"],
            "carrier": r["carrier"],
            "is_active": True,
            "created_at": now,
            "updated_at": now,
        }
        for r in records
    ]

    stmt = insert(ExportUldMaster).values(rows)
    stmt = stmt.on_conflict_do_nothing(index_elements=["uld_no"])  # skip duplicates at DB level

    result = await db.execute(stmt)
    await db.commit()

    inserted = result.rowcount
    skipped = len(rows) - inserted

    return {"inserted": inserted, "skipped": skipped, "total": len(rows)}


@router.post("/upload", summary="Upload Excel to bulk insert ULD master records")
async def upload_uld_excel(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only .xlsx or .xls files are accepted.")

    file_bytes = await file.read()

    try:
        records = parse_uld_excel(file_bytes)
    except ValueError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if not records:
        raise HTTPException(status_code=400, detail="No valid rows found in the uploaded file.")

    result = await upsert_uld_records(db, records)

    return {
        "message": "Upload complete.",
        "inserted": result["inserted"],
        "skipped_duplicates": result["skipped"],
        "total_rows_processed": result["total"],
    }



@router.post(
    "/new-uld/create",
    summary="Create a new ULD",
    status_code=201,
)
async def create_uld(
    payload: CreateUldRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
):
    # check duplicate
    existing = await db.execute(
        select(ExportUldMaster).where(ExportUldMaster.uld_no == payload.uld_no.strip().upper())
    )
    if existing.scalar_one_or_none():
        raise HTTPException(status_code=400, detail=f"ULD '{payload.uld_no}' already exists")

    now = get_utc_now()
    uld = ExportUldMaster(
        uld_no=payload.uld_no.strip().upper(),
        carrier=payload.carrier.strip().upper(),
        is_active=True,
        created_at=now,
        updated_at=now,
        created_by=current_user.emp_id, 
    )
    db.add(uld)
    await db.commit()
    await db.refresh(uld)

    return {
        "success": True,
        "message": f"ULD '{uld.uld_no}' created successfully",
        "data": {
            "uld_id": uld.id,
            "uld_no": uld.uld_no,
            "carrier": uld.carrier,
        }
    }



# ======================== 🤢🤮

async def _write_uld_failure_log(filename, uploaded_by, now, error_message):
    try:
        async with AsyncSession(engine) as log_session:
            async with log_session.begin():
                log_session.add(ExportFileUploadMetaLog(
                    filename=filename,
                    file_type="pdf",
                    uploaded_by=uploaded_by,
                    uploaded_at=now,
                    file_track_type="ULD_INVENTRY_PDF",
                    status="FAILED",
                    upload_meta={
                        "total_in_pdf": 0,
                        "inserted": 0,
                        "updated": 0,
                    },
                    error_message=str(error_message)[:500],
                    created_at=now,
                ))
    except Exception as log_err:
        print(f"⚠️ ULD log write failed: {log_err}")



MAX_FILE_SIZE = 10 * 1024 * 1024  # 10 MB
@router.post(
"/upload-and-sync-by-inventry-pdf",
response_model=UldStockSyncResponse,
status_code=status.HTTP_200_OK,
summary="Upload ULD stock PDF and sync to database",
description=(
    "Accepts a ULD stock PDF, extracts all ULD records from it, "
    "then upserts them into export_uld_master. "
    "Existing ULDs are marked available and refreshed. "
    "New ULDs are created. ULDs not in this PDF are left untouched."
),
responses={
    200: {"description": "PDF processed and database synced successfully"},
    400: {"description": "Invalid file, empty PDF, or mixed carriers"},
    413: {"description": "File exceeds 10 MB limit"},
    500: {"description": "Unexpected error during extraction or sync"},
},
)
async def upload_and_sync_uld_stock(
    db: AsyncSession = Depends(get_db),
    file: UploadFile = File(...),
    current_user = Depends(verify_token_and_get_user),
) -> UldStockSyncResponse:
    
    now = get_utc_now()
    filename = file.filename or "unknown"

    # ✅ Capture primitive immediately — avoids lazy load on expired session
    emp_id = current_user.emp_id
    try:
        # ── 1. Validate file type ─────────────────────────────────────────────────
        if not (file.filename or "").lower().endswith(".pdf"):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Only PDF files are allowed.",
            )

        # ── 2. Read & validate file size ──────────────────────────────────────────
        contents = await file.read()
        if len(contents) > MAX_FILE_SIZE:
            raise HTTPException(
                status_code=status.HTTP_413_REQUEST_ENTITY_TOO_LARGE,
                detail="File too large. Maximum allowed size is 10 MB.",
            )


        # ── 3. Extract records from PDF ───────────────────────────────────────────
        try:
            df = extract_uld_stock(io.BytesIO(contents))
        except Exception as exc:
        
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="Failed to extract data from the PDF.",
            ) from exc

        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="No valid ULD records found in the uploaded PDF.",
            )

        

        # ── 4. Convert DataFrame rows → UldStockRecord objects ────────────────────
        records: list[UldStockRecord] = []
        for row in df.where(pd.notnull(df), None).to_dict(orient="records"):
            # Normalize datetime/Timestamp fields to ISO strings for Pydantic
            normalized = {
                k: v.isoformat() if hasattr(v, "isoformat") else v
                for k, v in row.items()
            }
            records.append(UldStockRecord(**normalized))

        # ── 5. Sync into DB ───────────────────────────────────────────────────────
        service = UldStockSyncService(db=db)

        try:
            response = await service.sync(
                records=records,
                synced_by= emp_id,  # pass the employee ID of the authenticated user
            )
        except MultipleCarriersError as exc:
        
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=str(exc),
            ) from exc
        except Exception as exc:
        
            raise HTTPException(
                status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
                detail="An unexpected error occurred during ULD stock synchronization.",
            ) from exc
        # return response
        # ── 6. Write success log ──────────────────────────────────────────
        db.add(ExportFileUploadMetaLog(
            filename=filename,
            file_type="pdf",
            uploaded_by=emp_id,
            uploaded_at=now,
            file_track_type="ULD_INVENTRY_PDF",
            status="SUCCESS",
            upload_meta={
                 "carrier":        response.carrier,
                "total_in_pdf": response.total_received,
                "inserted":     response.total_created,
                "updated":      response.total_updated,
            },
            error_message=None,
            created_at=now,
        ))
        await db.commit()

        return response

    except HTTPException as e:
        try:
            await db.rollback()
        except Exception:
            pass
        await _write_uld_failure_log(
            filename=filename,
            uploaded_by=emp_id,
            now=now,
            error_message=e.detail if isinstance(e.detail, str) else str(e.detail),
        )
        raise

    except Exception as e:
        try:
            await db.rollback()
        except Exception:
            pass
        await _write_uld_failure_log(
            filename=filename,
            uploaded_by=emp_id,
            now=now,
            error_message=str(e),
        )
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Processing failed: {str(e)}",
        )




# ============== ULD MASTER DATA TO SHOW IN WEB TABLE WITH FILTER AND PAGINATION ==============


@router.get("/get-uld-master-list-with-pagination", summary="Get ULD master list with filters and pagination")
async def get_uld_master_list(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),

    # filters
    carrier:      Optional[str]  = Query(None, description="Carrier code e.g. AI, LH, EK | all"),
    is_available: Optional[bool] = Query(None, description="true | false"),
    is_active:    Optional[bool] = Query(None, description="true | false"),

    # pagination
    page:      int = Query(1,  ge=1,         description="Page number"),
    page_size: int = Query(20, ge=1, le=100, description="Records per page"),
):
    # ✅ call via class
    records, total = await UldStockSyncService.get_filtered_uld_master(
        db=db,
        carrier=carrier,
        is_available=is_available,
        is_active=is_active,
        page=page,
        page_size=page_size,
    )

    total_pages = math.ceil(total / page_size) if total > 0 else 1

    pagination = PaginationMetadata(
        current_page=page,
        page_size=page_size,
        total_records=total,
        total_pages=total_pages,
        has_previous=page > 1,
        has_next=page < total_pages,
        previous_page=page - 1 if page > 1 else None,
        next_page=page + 1 if page < total_pages else None,
    )

    data = [
        {
            "id":           r.id,
            "uld_no":       r.uld_no,
            "uld_type":     r.uld_type,
            "carrier":      r.carrier,
            "is_available": r.is_available,
            "is_active":    r.is_active,
            "created_by":   r.created_by,
            "updated_by":   r.updated_by,
            "created_at":   r.created_at.isoformat() if r.created_at else None,
            "updated_at":   r.updated_at.isoformat() if r.updated_at else None,
        }
        for r in records
    ]

    return {
        "success":    True,
        "message":    "ULD master records fetched successfully",
        "pagination": pagination,
        "data":       data,
    }


@router.get("/uld-master/carriers")
async def get_uld_carriers(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
):
    """Returns distinct carrier codes — use this to populate the carrier dropdown."""
    carriers = await UldStockSyncService.get_distinct_carriers(db)
    return {
        "success":  True,
        "carriers": carriers,
    }