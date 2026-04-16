
from fastapi import APIRouter, Body, UploadFile, File, Depends, HTTPException, status
from fastapi.responses import StreamingResponse
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.dialects.postgresql import insert
from typing import Dict, Any, Optional
from io import BytesIO
import pandas as pd
import numpy as np

from app.core.dependency import verify_token_and_get_user
from app.db.session import get_db
from app.db.models.exportOperation.export_skid_master import ExportSkidMaster
from app.utils.common.helperFunction import get_utc_now
from app.utils.exportOperation.export_skid_master_cleaner import clean_export_skid_master


from app.db.session import get_db
from app.services.exportOperation.skid_master import (
    assign_skid_to_location,
    create_new_skid_in_skid_master,
    delete_sequence_item,
    export_skid_master_to_excel,
    force_unlock_skid,
    generate_virtual_skid,
    get_skid_by_sequence,
    get_skid_recent_mapping_info,
    relocate_skid_service,
    scan_sequence_item,
    validate_and_lock_skid,
)
from app.schemas.exportOperation.skid_master import (
    AssignLocationRequest,
    AssignLocationResponse,
    CreateSkidRequest,
    DeleteSequenceResponse,
    ForceUnlockResponse,
    GenerateVirtualSkidResponse,
    RelocateRequest,
    ScanSequenceRequest,
    ScanSequenceResponse,
    SkidBySequenceResponse,
    SkidInfoResponse,
    SkidValidateAndLockRequest,
    SkidValidateAndLockResponse,
)


router = APIRouter(
    prefix="/export-skid-master",
    tags=[]
)



@router.post("/upload")
async def upload_export_skid_master(
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db)
) :

    if not file.filename:
        raise HTTPException(status_code=400, detail="File not provided")

    ext = file.filename.split(".")[-1].lower()

    if ext not in ["xlsx", "xls", "csv"]:
        raise HTTPException(
            status_code=400,
            detail="Only .xlsx, .xls, .csv allowed"
        )

    file_type = "excel" if ext in ["xlsx", "xls"] else "csv"

    try:
        file_bytes = BytesIO(await file.read())

        cleaned_df, faulty_df = clean_export_skid_master(
            file_bytes,
            file_type
        )

        if cleaned_df.empty:
            return {
                "message": "No valid records found",
                "inserted": 0,
                "already_present": 0,
                "faulty_records": len(faulty_df)
            }

        records = cleaned_df.to_dict(orient="records")

        now = get_utc_now()

        # Faster injection (no repeated function call)
        for r in records:
            r["created_at"] = now
            r["updated_at"] = now

        BATCH_SIZE = 1000
        total_received = len(records)
        total_inserted = 0

        for i in range(0, total_received, BATCH_SIZE):

            batch = records[i:i + BATCH_SIZE]

            stmt = insert(ExportSkidMaster).values(batch)

            stmt = stmt.on_conflict_do_nothing(
                constraint="uq_export_skid_no"
            )

            result = await db.execute(stmt)
            total_inserted += result.rowcount or 0

        await db.commit()

        return {
            "message": "Skid master uploaded successfully",
            "total_received": total_received,
            "inserted": total_inserted,
            "already_present": total_received - total_inserted,
            "faulty_records": len(faulty_df)
        }

    except Exception as e:
        await db.rollback()   # 🔥 VERY IMPORTANT
        raise HTTPException(
            status_code=500,
            detail=f"Processing failed: {str(e)}"
        )
    


# ============================================================= ✌️✌️✌️✌️✌️✌️ =======================================


@router.post(
    "/generate-virtual",
    response_model=GenerateVirtualSkidResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Generate a unique virtual skid number using DB sequence and create its master record",
)
async def generate_virtual_skid_route(
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Called when user selects 'Virtual Skid' and clicks Generate.
    Uses PostgreSQL nextval('virtual_skid_seq') — atomic, parallel-safe.
    Creates ExportSkidMaster row immediately so virtual skid behaves
    exactly like a real skid in all downstream flows.
    """
    return await generate_virtual_skid(
        db=db,
        emp_id=current_user.emp_id,
    )


@router.post(
    "/validate-and-lock",
    response_model=SkidValidateAndLockResponse,
    status_code=status.HTTP_200_OK,
    summary="Validate skid availability, lock it, and create AWB mapping instantly",
)
async def validate_and_lock_skid_route(
    payload: SkidValidateAndLockRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Works identically for real and virtual skids.
    Real skid  → skid_no comes from barcode scan.
    Virtual skid → skid_no auto-filled by frontend after generate-virtual call.
    """
    return await validate_and_lock_skid(
        db=db,
        awb_master_id=payload.awb_master_id,
        skid_no=payload.skid_no,
        emp_id=current_user.emp_id,
    )


@router.patch(
    "/{skid_no}/force-unlock",
    response_model=ForceUnlockResponse,
    status_code=status.HTTP_200_OK,
    summary="Manually force-unlock a skid by skid_no — for supervisor/admin use",
)
async def force_unlock_skid_route(
    skid_no: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Force unlocks any locked skid regardless of who locked it or when.
    Use when:
    - Operator forgot to save/unlock
    - Browser crashed and skid is stuck locked
    - Stale lock needs immediate manual release
    Records the emp_id of who performed the force unlock.
    """
    return await force_unlock_skid(
        db=db,
        skid_no=skid_no,
        emp_id=current_user.emp_id,
    )



# ======================================== ✌️Scanning the skid seq items ==============================

@router.post(
    "/sequence/scan",
    response_model=ScanSequenceResponse,
    # status_code=status.HTTP_201_CREATED,
    summary="Scan and persist one item sequence — called on every individual scan",
)
async def scan_sequence_item_route(
    payload: ScanSequenceRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Persists each scanned item immediately — crash safe.
    Checks (in order):
      1. Mapping exists
      2. Skid still locked and not stale (>24h → 423, force re-lock)
      3. Duplicate sequence_no on same AWB → 409
      4. Scanned count already at awb.pcs cap → 400 hard block
      5. You pass is_final True 
      6. I do not unlock skid here (in this step)
    Returns full scanned item list for this mapping after insert.

    """
    print(payload)
    return await scan_sequence_item(
        db=db,
        mapping_id=payload.mapping_id,
        awb_master_id=payload.awb_master_id,
        sequence_nos=payload.sequence_nos,

         skid_id=payload.skid_id,     

        scan_by_device=payload.scan_by_device,                  # ← ADD
        scanned_by= current_user.emp_id or payload.scanned_by,   # ← ADD (fallback to token)

        is_final=payload.is_final,  #💀💀😎⚠️ I set default TRUE in schema if not provided 
    )


@router.delete(
    "/sequence/{sequence_id}",
    response_model=DeleteSequenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Remove a wrongly scanned item — skid must still be locked",
)
async def delete_sequence_item_route(
    sequence_id: int,
    mapping_id: int,
    awb_master_id: int,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Deletes a single scanned sequence row by its id.
    mapping_id and awb_master_id passed as query params.
    Skid must still be locked — expired lock blocks deletion too.
    Returns updated full item list after deletion.
    """
    return await delete_sequence_item(
        db=db,
        sequence_id=sequence_id,
        mapping_id=mapping_id,
        awb_master_id=awb_master_id,
    )


@router.get(
    "/by-sequence/{sequence_no}",
    response_model=SkidBySequenceResponse,
    status_code=status.HTTP_200_OK,
    summary="Reverse lookup — find skid by scanning any sequence item barcode",
)
async def get_skid_by_sequence_route(
    sequence_no: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Used when user does not know or cannot scan the skid barcode
    (e.g. virtual skids — shipper's own wooden skid with no system barcode).

    User scans any item barcode that was scanned onto that skid.
    Returns skid_no + mapping_id + awb_master_id ready for assign-location call.
    """
    return await get_skid_by_sequence(
        db=db,
        sequence_no=sequence_no,
    )


@router.post(
    "/assign-location",
    response_model=AssignLocationResponse,
    status_code=status.HTTP_201_CREATED,
    summary="Assign a skid to a location after scanning is complete",
)
async def assign_skid_to_location_route(
    payload: AssignLocationRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Separate step from scanning — may be done by a different user/shift.
    Skid stays locked after this — unlock happens in a later step.

    Handles both:
    - location_id from dropdown selection
    - location_id resolved from barcode scan on frontend before calling this

    Checks:
    1. Skid exists
    2. Location exists and is_active
    3. AWB master exists
    4. Scanning session (mapping) exists for this skid + AWB
    5. Skid not already at this same location (409)
    6. Flips previous location is_current=False
    7. Creates new location mapping with is_current=True
    """
    return await assign_skid_to_location(
        db=db,
        skid_no=payload.skid_no,
        location_id=payload.location_id,
        awb_master_id=payload.awb_master_id,
        emp_id=current_user.emp_id,
    )





# ✌️ =======This used in location mapping with skid screen to validate and get recent used skid mapping =======================
@router.get(
    "/get-mapping-by-skid-no/{skid_no}",
    response_model=SkidInfoResponse,
    status_code=status.HTTP_200_OK,
    summary="Get skid info with most recent AWB mapping details",
)
async def get_skid_info_route(
    skid_no: str,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Validates skid exists in skid master.
    If exists → returns skid details + most recent AWB mapping + AWB basic info.
    If no mapping yet → returns skid details only with message.
    If skid not found → 404.
    """
    return await get_skid_recent_mapping_info(
        db=db,
        skid_no=skid_no,
    )

# Skid reloaction routes ==========================
@router.patch("/skid/{skid_id}/relocate", summary="Move skid to a new location")
async def relocate_skid(
    skid_id: int,
    # location_id: int = Body(..., embed=True),
    # mapping_id: Optional[int] = Body(None),   # ← ADD — needed for case 2 in service, optional for case 1
    # relocation_from_base: bool = Body(False),
     payload: RelocateRequest,
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Validates location that it exits or not.
    Check previous location that present or not {it must have one previous assigned location}
    If no mapping yet → returns no current location present.
    If skid not found → 404.
    ⚠️Need to add gaurd to restrict to relocate after a particular point {when skid is free or picked for base or location is free from this skid}
    """
    print(f"🤢🤢Relocate request for skid_id={skid_id} to location_id={payload.location_id} with mapping_id={payload.mapping_id} || {payload.relocation_from_base}")
    return await relocate_skid_service(
        skid_id=skid_id,
        location_id=payload.location_id,
        moved_by=current_user.emp_id,  # ← adjust to your user model field
        db=db,
        mapping_id=payload.mapping_id,
        relocation_from_base=payload.relocation_from_base,
    )




@router.post(
    "/skids/create",
    summary="Create a new physical skid",
    status_code=201,
)
async def create_skid_route(
    payload: CreateSkidRequest,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
):
    created_by = current_user.emp_id
    return await create_new_skid_in_skid_master(db=db, payload=payload, created_by=created_by)



# ====================== export excel for skid master =================

@router.get("/skid-master/download")
async def download_skid_master(db: AsyncSession = Depends(get_db)):
    buf = await export_skid_master_to_excel(db)
    return StreamingResponse(
        buf,
        media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
        headers={"Content-Disposition": "attachment; filename=skid_master.xlsx"},
    )