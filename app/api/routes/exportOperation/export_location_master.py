# routes/export_location_master.py

from fastapi import APIRouter, UploadFile, File, Depends, HTTPException, status
from sqlalchemy import select
from sqlalchemy.dialects.postgresql import insert
from io import BytesIO
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependency import verify_token_and_get_user
from app.db.session import get_db
from app.db.models.exportOperation.export_location_master import ExportLocationsMaster
from app.schemas.exportOperation.location_master import CreateLocationRequest, ValidateLocationResponse
from app.utils.common.helperFunction import get_utc_now
from app.utils.exportOperation.export_location_master import clean_export_location_master

router = APIRouter(prefix="/export-location-master", tags=[])


@router.post("/upload")
async def upload_export_location_master(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
):
    try:
        # 🔹 Read file
        content = await file.read()
        file_bytes = BytesIO(content)

        # 🔹 Detect file type
        filename = file.filename.lower()
        if filename.endswith((".xls", ".xlsx")):
            file_type = "excel"
        elif filename.endswith(".csv"):
            file_type = "csv"
        else:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Unsupported file format. Only CSV and Excel allowed."
            )

        # 🔹 Clean Data
        df = clean_export_location_master(file_bytes, file_type)

        if df.empty:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="File contains no valid data after cleaning."
            )

        now = get_utc_now()
        records = df.to_dict(orient="records")

        data_to_insert = [
            {
                "ops_type": row["OPS TYPE"],
                "area_code": row["AREA CODE"],
                "loc": row["LOC"],
                "is_active": True,
                "created_at": now
            }
            for row in records
        ]

        # 🔥 PostgreSQL insert with ON CONFLICT DO NOTHING
        stmt = insert(ExportLocationsMaster).values(data_to_insert)

        stmt = stmt.on_conflict_do_nothing(
            index_elements=["loc"]  # because loc is unique
        )

        result = await db.execute(stmt)
        await db.commit()
        print("Committed rows to DB")

        inserted_count = result.rowcount
        duplicate_count = len(records) - inserted_count

        return {
            "success": True,
            "message": "Export location master uploaded successfully.",
            "file_name": file.filename,
            "total_rows_received": len(records),
            "total_inserted": inserted_count,
            "total_duplicates_ignored": duplicate_count
        }

    except HTTPException:
        raise

    except Exception as e:
        db.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Something went wrong: {str(e)}"
        )
    








@router.get(
    "/location/validate/{location_id}",
    response_model=ValidateLocationResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate if a location exists and is active in location master",
)
async def validate_location_route(
    location_val: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Checks location master for given location_id.
    Returns 200 + location info if valid and active.
    Returns 404 if not found.
    Returns 400 if found but inactive.
    """

    async def validate_location(
        db: AsyncSession,
        location: str,
    ) -> dict:
        """
        Validates location exists in location master and is active.
        Returns location info on success, raises 404/400 on failure.
        """
        result = await db.execute(
            select(ExportLocationsMaster).where(
                ExportLocationsMaster.loc == location_val
            )
        )
        location = result.scalar_one_or_none()

        if not location:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Location '{location}' not found.",
            )

        if not location.is_active:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Location '{location.loc}' is inactive and cannot be used.",
            )

        return {
            "success": True,
            "message": f"Location '{location.loc}' is valid and active.",
            "location": {
                "id": location.id,
                "loc": location.loc,
                "area_code": location.area_code,
                "ops_type": location.ops_type,
                "is_active": location.is_active,
            },
        }


    return await validate_location(
        db=db,
        location=location_val,
    )



# Create New location items in export location master
@router.post(
    "/locations/create",
    summary="Create a new export location",
    status_code=201,
)
async def create_location_route(
    payload: CreateLocationRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
):
    created_by = current_user.emp_id
    now = get_utc_now()

    # check duplicate loc name
    existing = await db.execute(
        select(ExportLocationsMaster.id).where(
            ExportLocationsMaster.loc == payload.loc
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Location '{payload.loc}' already exists",
        )

    # check duplicate area_code
    existing_code = await db.execute(
        select(ExportLocationsMaster.id).where(
            ExportLocationsMaster.area_code == payload.area_code
        )
    )
    if existing_code.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Area code '{payload.area_code}' already exists",
        )

    location = ExportLocationsMaster(
        ops_type="EXPORT",
        loc=payload.loc,
        area_code=payload.area_code,
        is_active=True,
        created_at=now,
        created_by=created_by,
    )
    db.add(location)
    await db.commit()
    await db.refresh(location)

    return {
        "success": True,
        "message": f"Location '{location.loc}' created successfully",
        "data": {
            "id": location.id,
            "loc": location.loc,
            "area_code": location.area_code,
            "ops_type": location.ops_type,
            "is_active": location.is_active,
        },
    }
