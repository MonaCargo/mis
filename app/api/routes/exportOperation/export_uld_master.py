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

import pandas as pd
from sqlalchemy import select
from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File, status
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.core.dependency import verify_token_and_get_user
from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.db.session import get_db
from app.schemas.exportOperation.car_message import UldStockRecord, UldStockSyncResponse
from app.schemas.exportOperation.location_master import CreateUldRequest
from app.services.exportOperation.uld_master_service import MultipleCarriersError, UldStockSyncService
from app.utils.common.helperFunction import get_utc_now
from app.utils.exportOperation.export_uld_master_cleaner import parse_uld_excel
from app.utils.exportOperation.extract_uld_inventry_pdf import extract_uld_stock


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
            synced_by= current_user.emp_id,  # pass the employee ID of the authenticated user
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
    return response