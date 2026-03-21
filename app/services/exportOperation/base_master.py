
from fastapi import HTTPException
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exportOperation.car_message import ExportAwbSkidMapping, ExportSkidBaseMapping, ExportSkidLocationMapping
from app.db.models.exportOperation.export_base_master import ExportBaseMaster
from app.db.models.exportOperation.export_skid_master import ExportSkidMaster
from app.schemas.exportOperation.base_master import UldBaseBulkCreateRequest, UldBaseBulkCreateResponse, UldBaseResponse, UldBaseVerifyResponse
from app.services.exportOperation.car_message_flow_audit_log import write_car_message_flow_audit
from app.utils.common.car_message_flow_audit_utils import CarMessageFlowModule, CarMessageFlowStep
from app.utils.common.helperFunction import get_utc_now

async def bulk_create_uld_bases(
    db: AsyncSession,
    payload: UldBaseBulkCreateRequest,
) -> UldBaseBulkCreateResponse:

    now = get_utc_now()
    incoming_names = [item.base_name for item in payload.bases]

    # ── Check which base_names already exist ───────────────────
    existing_result = await db.execute(
        select(ExportBaseMaster.base_name).where(
            ExportBaseMaster.base_name.in_(incoming_names)
        )
    )
    existing_names = {row.base_name for row in existing_result.mappings().all()}

    # ── Separate new vs duplicate ──────────────────────────────
    to_insert = []
    skipped_names = []

    for item in payload.bases:
        if item.base_name in existing_names:
            skipped_names.append(item.base_name)
        else:
            to_insert.append(
                ExportBaseMaster(
                    base_name=item.base_name,
                    created_at=now,
                    updated_at=now,
                )
            )

    if to_insert:
        db.add_all(to_insert)
        await db.commit()
        for obj in to_insert:
            await db.refresh(obj)

    return UldBaseBulkCreateResponse(
        success=True,
        message=f"{len(to_insert)} base(s) inserted, {len(skipped_names)} skipped (already exist)",
        inserted=len(to_insert),
        skipped=len(skipped_names),
        skipped_names=skipped_names,
        data=[UldBaseResponse.model_validate(obj) for obj in to_insert],
    )

# ====================✌️✌️ Drop at base ==========================================

async def get_base_master_list(db: AsyncSession) -> list[dict]:
    result = await db.execute(
        select(
            ExportBaseMaster.id.label("base_id"),
            ExportBaseMaster.base_name,
        ).order_by(ExportBaseMaster.base_name)
    )
    return [dict(row) for row in result.mappings().all()]


#👌 Drop at base=======================================
async def drop_skid_at_base(
    db: AsyncSession,
    mapping_id: int,
    base_id: int,
    dropped_by: str,
) -> dict:

    now = get_utc_now()

    # ── Fetch mapping with skid info ───────────────────────────
    mapping_result = await db.execute(
        select(
            ExportAwbSkidMapping.id.label("mapping_id"),
            ExportAwbSkidMapping.skid_id,
            ExportAwbSkidMapping.awb_master_id,
            ExportAwbSkidMapping.is_virtual,
            ExportAwbSkidMapping.virtual_skid_no,
            ExportSkidMaster.skid_no,
        )
        .join(
            ExportSkidMaster,
            ExportAwbSkidMapping.skid_id == ExportSkidMaster.id,
        )
        .where(ExportAwbSkidMapping.id == mapping_id)
    )
    mapping = mapping_result.mappings().one_or_none()

    if not mapping:
        raise HTTPException(
            status_code=404,
            detail=f"Mapping id {mapping_id} not found",
        )

    # ── Check 1: skid must be retrieved from location first ────
    # retrieved = is_current=False + picked_at set
    retrieved_check = await db.execute(
        select(ExportSkidLocationMapping).where(
            ExportSkidLocationMapping.skid_id == mapping.skid_id,
            ExportSkidLocationMapping.is_current == False,
            ExportSkidLocationMapping.picked_at.isnot(None),
            ExportSkidLocationMapping.picked_by.isnot(None),
        )
        .order_by(ExportSkidLocationMapping.picked_at.desc())
        .limit(1)
    )
    retrieved_location = retrieved_check.scalar_one_or_none()

    if not retrieved_location:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Skid {mapping.skid_no} must be retrieved from its location "
                "before dropping at base"
            ),
        )

    # ── Check 2: skid not already at base for this mapping ─────
    existing_base = await db.execute(
        select(ExportSkidBaseMapping.id).where(
            ExportSkidBaseMapping.mapping_id == mapping_id,
        )
    )
    if existing_base.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Skid {mapping.skid_no} already dropped at base for this session",
        )

    # ── Check 3: base exists ───────────────────────────────────
    base = await db.get(ExportBaseMaster, base_id)
    if not base:
        raise HTTPException(
            status_code=404,
            detail=f"Base id {base_id} not found",
        )

    # ── Insert base mapping ────────────────────────────────────
    base_mapping = ExportSkidBaseMapping(
        mapping_id=mapping_id,
        skid_id=mapping.skid_id,
        awb_master_id=mapping.awb_master_id,
        base_id=base_id,
        dropped_by=dropped_by,
        dropped_at=now,
        created_at=now,
    )
    db.add(base_mapping)

    # ── Free the skid — mark mapping as complete ───────────────
    await db.execute(
        update(ExportAwbSkidMapping)
        .where(ExportAwbSkidMapping.id == mapping_id)
        .values(is_skid_used_complete=True)
    )

    # ── Free + unlock skid in master ───────────────────────────
    await db.execute(
        update(ExportSkidMaster)
        .where(ExportSkidMaster.id == mapping.skid_id)
        .values(
            is_locked=False,
            locked_at=None,
            locked_by_user_id=None,
            updated_at=now,
        )
    )

    # ── Audit log ──────────────────────────────────────────────
    await write_car_message_flow_audit(
        db=db,
        awb_reference_id=mapping.awb_master_id,
        flight_reference_id=None,
        module=CarMessageFlowModule.BASE_DROP,      # ← was LOCATION_MAPPING
        flow_step=CarMessageFlowStep.BASE_DROP,     # ← was STEP_LOCATION_MAPPING
        record_id=mapping_id,
        action="UPDATE",
        performed_by=dropped_by,
        changes={
            "event": "SKID_DROPPED_AT_BASE",
            "mapping_id": mapping_id,
            "skid_id": mapping.skid_id,
            "skid_no": mapping.skid_no,
            "is_virtual": mapping.is_virtual,
            "virtual_skid_no": mapping.virtual_skid_no,
            "base_id": base_id,
            "base_name": base.base_name,
            "summary": (
                f"Skid {mapping.skid_no} dropped at base "
                f"{base.base_name} by {dropped_by}"
            ),
        },
    )

    await db.commit()

    return {
        "success": True,
        "message": f"Skid {mapping.skid_no} successfully dropped at base {base.base_name}",
        "data": {
            "mapping_id": mapping_id,
            "skid_id": mapping.skid_id,
            "skid_no": mapping.skid_no,
            "is_virtual": mapping.is_virtual,
            "virtual_skid_no": mapping.virtual_skid_no,
            "awb_master_id": mapping.awb_master_id,
            "base_id": base_id,
            "base_name": base.base_name,
            "dropped_by": dropped_by,
            "dropped_at": now,
        },
    }






async def verify_uld_base_by_name(
    db: AsyncSession,
    base_name: str,
) -> UldBaseVerifyResponse:

    result = await db.execute(
        select(ExportBaseMaster).where(
            ExportBaseMaster.base_name == base_name.strip().upper()
        )
    )
    base = result.scalar_one_or_none()

    if not base:
        return UldBaseVerifyResponse(
            success=False,
            message=f"Base '{base_name}' not found",
            is_valid=False,
            data=None,
        )

    return UldBaseVerifyResponse(
        success=True,
        message=f"Base '{base.base_name}' is valid",
        is_valid=True,
        data=UldBaseResponse.model_validate(base),
    )