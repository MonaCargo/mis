
from fastapi import APIRouter, Depends, File, HTTPException, Query, UploadFile
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependency import verify_token_and_get_user
from app.db.session import get_db
from app.schemas.exportOperation.carrier_master import CarrierBulkUploadResponse
from app.schemas.user import UserRead
from app.services.exportOperation.carrier_master import bulk_upload_carriers_from_excel, verify_carrier_from_flight_no


router = APIRouter(prefix="/export-carrier-master", tags=[])
@router.post(
    "/carrier-master/bulk-upload",
    response_model=CarrierBulkUploadResponse,
    summary="Bulk upload carriers from Excel",
    status_code=201,
)
async def upload_carriers(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files allowed")

    file_bytes = await file.read()
    return await bulk_upload_carriers_from_excel(db=db, file_bytes=file_bytes)






@router.get(
    "/carrier-master/verify-flight-no",
    summary="Verify carrier code from flight number",
)
async def verify_flight_no_carrier(
    flight_no: str = Query(..., description="e.g. AI420, 6E101"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    return await verify_carrier_from_flight_no(db=db, flight_no=flight_no)