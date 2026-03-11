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
















from typing import Any, Dict, List

from fastapi import APIRouter, Depends, HTTPException, UploadFile, File
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert

from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.db.session import get_db
from app.utils.common.helperFunction import get_utc_now
from app.utils.exportOperation.export_uld_master_cleaner import parse_uld_excel


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