from fastapi import APIRouter, Depends, Query
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependency import verify_token_and_get_user
from app.db.session import get_db
from app.schemas.exportOperation.base_master import DropSkidAtBaseRequest, UldBaseBulkCreateRequest, UldBaseBulkCreateResponse, UldBaseVerifyResponse
from app.schemas.user import UserRead
from app.services.exportOperation.base_master import bulk_create_uld_bases, drop_skid_at_base, get_base_master_list, verify_uld_base_by_name

router = APIRouter(prefix="/export-base-master", tags=[])

@router.post(
    "/uld-base/bulk-create",
    response_model=UldBaseBulkCreateResponse,
    summary="Bulk create ULD base locations",
    status_code=201,
)
async def bulk_create_bases(
    payload: UldBaseBulkCreateRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    return await bulk_create_uld_bases(db=db, payload=payload)





@router.get(
    "/base/list",
    summary="Get all bases for selection",
)
async def get_bases(db: AsyncSession = Depends(get_db)):
    return await get_base_master_list(db=db)


@router.post(
    "/skid/drop-at-base",
    summary="Drop skid at base after retrieval from location",
)
async def drop_at_base(
    payload: DropSkidAtBaseRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
):
   
    return await drop_skid_at_base(
        db=db,
        mapping_id=payload.mapping_id,
        base_id=payload.base_id,
        dropped_by=current_user.emp_id,
    )


@router.get(
    "/uld-base/verify",
    response_model=UldBaseVerifyResponse,
    summary="Verify ULD base by name",
)
async def verify_uld_base(
    base_name: str = Query(..., description="Base name to verify"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    return await verify_uld_base_by_name(db=db, base_name=base_name)