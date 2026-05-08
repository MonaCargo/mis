
from fastapi import HTTPException
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exportOperation.car_message import ExportAwbSkidItemSequence, ExportAwbSkidMapping, ExportCarMessageAwbMaster, ExportFlightBookingDetail, ExportFlightBookingHeader, ExportSequenceItemUldLoading, ExportSkidBaseMapping, ExportSkidLocationMapping, ExportUldAssignment, ExportUldAssignmentDetail
from app.db.models.exportOperation.export_base_master import ExportBaseMaster
from app.db.models.exportOperation.export_skid_master import ExportSkidMaster
from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.schemas.exportOperation.base_master import UldBaseBulkCreateRequest, UldBaseBulkCreateResponse, UldBaseResponse, UldBaseVerifyResponse
from app.schemas.exportOperation.car_message import ScanItemIntoUldResponse, ScanItemResult
from app.services.exportOperation.car_message_flow_audit_log import write_car_message_flow_audit
from app.utils.common.car_message_flow_audit_utils import CarMessageFlowModule, CarMessageFlowStep
from app.utils.common.helperFunction import get_utc_now

async def bulk_create_uld_bases(
    db: AsyncSession,
    payload: UldBaseBulkCreateRequest,
    current_user,
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
                    created_by =current_user.emp_id
                )
            )

    if to_insert:
        db.add_all(to_insert)
        await db.commit()
        for obj in to_insert:
            await db.refresh(obj)
    

    created_count = len(to_insert)
    skipped_count = len(skipped_names)

    if created_count and skipped_count:
        message = f"{created_count} base(s) created, {skipped_count} skipped (already exist)"
    elif created_count:
        message = f"{created_count} base(s) created successfully"
    elif skipped_count:
        message = f"{skipped_count} base(s) skipped (already exist)"
    else:
        message = "No data processed"

    return UldBaseBulkCreateResponse(
        success=True,
         message=message,
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


#👌🤢 Drop at base=======================================
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
    retrieved_check = await db.execute(
        select(ExportSkidLocationMapping)
        .where(
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

    # ✅ CHANGED — Check 2: block double-drop in SAME cycle only
    # (dropped_at must be AFTER last retrieval picked_at)
    already_this_cycle = await db.execute(
        select(ExportSkidBaseMapping.id).where(
            ExportSkidBaseMapping.mapping_id == mapping_id,
            ExportSkidBaseMapping.dropped_at >= retrieved_location.picked_at,
        )
    )
    if already_this_cycle.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=(
                f"Skid {mapping.skid_no} already dropped at base for this cycle. "
                "Complete ULD scanning or relocate before dropping again."
            ),
        )

    # ── Check 3: base exists ───────────────────────────────────
    base = await db.get(ExportBaseMaster, base_id)
    if not base:
        raise HTTPException(
            status_code=404,
            detail=f"Base id {base_id} not found",
        )

    # ✅ ADD — calculate next cycle_no
    cycle_result = await db.execute(
        select(func.coalesce(func.max(ExportSkidBaseMapping.cycle_no), 0)).where(
            ExportSkidBaseMapping.mapping_id == mapping_id
        )
    )
    next_cycle_no = (cycle_result.scalar() or 0) + 1

    # ── Insert base mapping ────────────────────────────────────
    base_mapping = ExportSkidBaseMapping(
        mapping_id=mapping_id,
        skid_id=mapping.skid_id,
        awb_master_id=mapping.awb_master_id,
        base_id=base_id,
        cycle_no=next_cycle_no,          # ✅ ADD
        dropped_by=dropped_by,
        dropped_at=now,
        created_at=now,
    )
    db.add(base_mapping)

    # ✅ REMOVED — is_skid_used_complete=True (moves to ULD scan auto-complete)
    # ✅ REMOVED — skid unlock (moves to ULD scan auto-complete)

    # ── Audit log ──────────────────────────────────────────────
    await write_car_message_flow_audit(
        db=db,
        awb_reference_id=mapping.awb_master_id,
        flight_reference_id=None,
        module=CarMessageFlowModule.BASE_DROP,
        flow_step=CarMessageFlowStep.BASE_DROP,
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
            "cycle_no": next_cycle_no,           # ✅ ADD
            "summary": (
                f"Skid {mapping.skid_no} dropped at base "
                f"{base.base_name} (cycle {next_cycle_no}) by {dropped_by}"
            ),
        },
    )

    await db.commit()

    return {
        "success": True,
        "message": f"Skid {mapping.skid_no} dropped at base {base.base_name} (cycle {next_cycle_no})",
        "data": {
            "mapping_id": mapping_id,
            "skid_id": mapping.skid_id,
            "skid_no": mapping.skid_no,
            "is_virtual": mapping.is_virtual,
            "virtual_skid_no": mapping.virtual_skid_no,
            "awb_master_id": mapping.awb_master_id,
            "base_id": base_id,
            "base_name": base.base_name,
            "cycle_no": next_cycle_no,           # ✅ ADD
            "dropped_by": dropped_by,
            "dropped_at": now,
        },
    }

# async def drop_skid_at_base(
#     db: AsyncSession,
#     mapping_id: int,
#     base_id: int,
#     dropped_by: str,
# ) -> dict:

#     now = get_utc_now()

#     # ── Fetch mapping with skid info ───────────────────────────
#     mapping_result = await db.execute(
#         select(
#             ExportAwbSkidMapping.id.label("mapping_id"),
#             ExportAwbSkidMapping.skid_id,
#             ExportAwbSkidMapping.awb_master_id,
#             ExportAwbSkidMapping.is_virtual,
#             ExportAwbSkidMapping.virtual_skid_no,
#             ExportSkidMaster.skid_no,
#         )
#         .join(
#             ExportSkidMaster,
#             ExportAwbSkidMapping.skid_id == ExportSkidMaster.id,
#         )
#         .where(ExportAwbSkidMapping.id == mapping_id)
#     )
#     mapping = mapping_result.mappings().one_or_none()

#     if not mapping:
#         raise HTTPException(
#             status_code=404,
#             detail=f"Mapping id {mapping_id} not found",
#         )

#     # ── Check 1: skid must be retrieved from location first ────
#     # retrieved = is_current=False + picked_at set
#     retrieved_check = await db.execute(
#         select(ExportSkidLocationMapping).where(
#             ExportSkidLocationMapping.skid_id == mapping.skid_id,
#             ExportSkidLocationMapping.is_current == False,
#             ExportSkidLocationMapping.picked_at.isnot(None),
#             ExportSkidLocationMapping.picked_by.isnot(None),
#         )
#         .order_by(ExportSkidLocationMapping.picked_at.desc())
#         .limit(1)
#     )
#     retrieved_location = retrieved_check.scalar_one_or_none()

#     if not retrieved_location:
#         raise HTTPException(
#             status_code=400,
#             detail=(
#                 f"Skid {mapping.skid_no} must be retrieved from its location "
#                 "before dropping at base"
#             ),
#         )

#     # ── Check 2: skid not already at base for this mapping ─────
#     existing_base = await db.execute(
#         select(ExportSkidBaseMapping.id).where(
#             ExportSkidBaseMapping.mapping_id == mapping_id,
#         )
#     )
#     if existing_base.scalar_one_or_none():
#         raise HTTPException(
#             status_code=400,
#             detail=f"Skid {mapping.skid_no} already dropped at base for this session",
#         )

#     # ── Check 3: base exists ───────────────────────────────────
#     base = await db.get(ExportBaseMaster, base_id)
#     if not base:
#         raise HTTPException(
#             status_code=404,
#             detail=f"Base id {base_id} not found",
#         )

#     # ── Insert base mapping ────────────────────────────────────
#     base_mapping = ExportSkidBaseMapping(
#         mapping_id=mapping_id,
#         skid_id=mapping.skid_id,
#         awb_master_id=mapping.awb_master_id,
#         base_id=base_id,
#         dropped_by=dropped_by,
#         dropped_at=now,
#         created_at=now,
#     )
#     db.add(base_mapping)

#     # ── Free the skid — mark mapping as complete ───────────────
#     await db.execute(
#         update(ExportAwbSkidMapping)
#         .where(ExportAwbSkidMapping.id == mapping_id)
#         .values(is_skid_used_complete=True)
#     )

#     # ── Free + unlock skid in master ───────────────────────────
#     await db.execute(
#         update(ExportSkidMaster)
#         .where(ExportSkidMaster.id == mapping.skid_id)
#         .values(
#             is_locked=False,
#             locked_at=None,
#             locked_by_user_id=None,
#             updated_at=now,
#         )
#     )

#     # ── Audit log ──────────────────────────────────────────────
#     await write_car_message_flow_audit(
#         db=db,
#         awb_reference_id=mapping.awb_master_id,
#         flight_reference_id=None,
#         module=CarMessageFlowModule.BASE_DROP,      # ← was LOCATION_MAPPING
#         flow_step=CarMessageFlowStep.BASE_DROP,     # ← was STEP_LOCATION_MAPPING
#         record_id=mapping_id,
#         action="UPDATE",
#         performed_by=dropped_by,
#         changes={
#             "event": "SKID_DROPPED_AT_BASE",
#             "mapping_id": mapping_id,
#             "skid_id": mapping.skid_id,
#             "skid_no": mapping.skid_no,
#             "is_virtual": mapping.is_virtual,
#             "virtual_skid_no": mapping.virtual_skid_no,
#             "base_id": base_id,
#             "base_name": base.base_name,
#             "summary": (
#                 f"Skid {mapping.skid_no} dropped at base "
#                 f"{base.base_name} by {dropped_by}"
#             ),
#         },
#     )

#     await db.commit()

#     return {
#         "success": True,
#         "message": f"Skid {mapping.skid_no} successfully dropped at base {base.base_name}",
#         "data": {
#             "mapping_id": mapping_id,
#             "skid_id": mapping.skid_id,
#             "skid_no": mapping.skid_no,
#             "is_virtual": mapping.is_virtual,
#             "virtual_skid_no": mapping.virtual_skid_no,
#             "awb_master_id": mapping.awb_master_id,
#             "base_id": base_id,
#             "base_name": base.base_name,
#             "dropped_by": dropped_by,
#             "dropped_at": now,
#         },
#     }

# 🤢Ulgtra fast scan and load
async def ultra_fast_scan_and_load(
    db: AsyncSession,
    flight_header_id: int,
    uld_assignment_detail_id: int,
    awb_master_id: int,
    sequence_nos: list[str],
    loaded_by: str,
) -> ScanItemIntoUldResponse:

    now = get_utc_now()

    # ── verify flight ──────────────────────────────────────────
    flight = await db.get(ExportFlightBookingHeader, flight_header_id)
    if not flight or not flight.is_active:
        raise HTTPException(status_code=404, detail="Flight not found")
    if flight.flight_dpt_datetime <= now:
        raise HTTPException(status_code=400, detail="Flight has already departed")

    # ── verify AWB is ultra-fast ───────────────────────────────
    awb = await db.get(ExportCarMessageAwbMaster, awb_master_id)
    if not awb:
        raise HTTPException(status_code=404, detail="AWB not found")
    if not awb.is_ultra_fast:
        raise HTTPException(status_code=400, detail=f"AWB {awb.awb_no} is not marked as ultra-fast")

    # ── verify AWB booked on this flight ──────────────────────
    booking_result = await db.execute(
        select(ExportFlightBookingDetail.booked_pcs).where(
            ExportFlightBookingDetail.flight_header_id == flight_header_id,
            ExportFlightBookingDetail.awb_master_id == awb_master_id,
        )
    )
    booked_pcs = booking_result.scalar_one_or_none()
    if booked_pcs is None:
        raise HTTPException(status_code=400, detail=f"AWB {awb.awb_no} not booked on this flight")

    # ── verify ULD belongs to this flight ─────────────────────
    uld_result = await db.execute(
        select(ExportUldMaster.uld_no)
        .join(ExportUldAssignmentDetail,
              ExportUldAssignmentDetail.uld_id == ExportUldMaster.id)
        .join(ExportUldAssignment,
              ExportUldAssignmentDetail.assignment_id == ExportUldAssignment.id)
        .where(
            ExportUldAssignmentDetail.id == uld_assignment_detail_id,
            ExportUldAssignment.flight_header_id == flight_header_id,
            ExportUldAssignment.is_active == True,
        )
    )
    uld_no = uld_result.scalar_one_or_none()
    if not uld_no:
        raise HTTPException(status_code=400, detail="ULD does not belong to this flight")

    # ── get system skid + base directly by name ────────────────
    skid_result = await db.execute(
        select(ExportSkidMaster.id).where(
            ExportSkidMaster.skid_no == "ULTRAFAST-SYSTEM-SKID"
        )
    )
    system_skid_id = skid_result.scalar_one_or_none()

    base_result = await db.execute(
        select(ExportBaseMaster.id).where(
            ExportBaseMaster.base_name == "ULTRAFAST-AUTO-BASE"
        )
    )
    system_base_id = base_result.scalar_one_or_none()

    if not system_skid_id or not system_base_id:
        raise HTTPException(
            status_code=500,
            detail="Ultra-fast system skid or base not seeded in DB",
        )

    # ── get or create virtual mapping for this AWB ─────────────
    mapping_result = await db.execute(
        select(ExportAwbSkidMapping.id).where(
            ExportAwbSkidMapping.awb_master_id == awb_master_id,
            ExportAwbSkidMapping.skid_id == system_skid_id,
            ExportAwbSkidMapping.is_virtual == True,
        )
    )
    mapping_id = mapping_result.scalar_one_or_none()

    if not mapping_id:
        new_mapping = ExportAwbSkidMapping(
            awb_master_id=awb_master_id,
            skid_id=system_skid_id,
            is_virtual=True,
            virtual_skid_no="ULTRAFAST",
            mapped_by=loaded_by,
            mapped_at=now,
            created_at=now,
        )
        db.add(new_mapping)
        await db.flush()
        mapping_id = new_mapping.id

    # ── get or create base drop for this mapping ───────────────
    base_check = await db.execute(
        select(ExportSkidBaseMapping.id).where(
            ExportSkidBaseMapping.mapping_id == mapping_id,
        )
    )
    if not base_check.scalar_one_or_none():
        db.add(ExportSkidBaseMapping(
            mapping_id=mapping_id,
            skid_id=system_skid_id,
            awb_master_id=awb_master_id,
            base_id=system_base_id,
            cycle_no=1,
            dropped_by="ULTRAFAST-AUTO",
            dropped_at=now,
            created_at=now,
        ))
        await db.flush()

    # ── already loaded count for cap check ─────────────────────
    loaded_count_result = await db.execute(
        select(func.count(ExportSequenceItemUldLoading.id)).where(
            ExportSequenceItemUldLoading.flight_header_id == flight_header_id,
            ExportSequenceItemUldLoading.awb_master_id == awb_master_id,
        )
    )
    already_loaded_count = loaded_count_result.scalar() or 0

    # ── fetch already scanned sequence_nos ────────────────────
    existing_seqs_result = await db.execute(
        select(
            ExportAwbSkidItemSequence.sequence_no,
            ExportAwbSkidItemSequence.id.label("sequence_id"),
        ).where(ExportAwbSkidItemSequence.sequence_no.in_(sequence_nos))
    )
    existing_seq_map = {
        row.sequence_no: row.sequence_id
        for row in existing_seqs_result.mappings().all()
    }

    # ── already loaded sequence ids ────────────────────────────
    already_loaded_ids: set[int] = set()
    if existing_seq_map:
        loaded_ids_result = await db.execute(
            select(ExportSequenceItemUldLoading.sequence_id).where(
                ExportSequenceItemUldLoading.sequence_id.in_(
                    list(existing_seq_map.values())
                )
            )
        )
        already_loaded_ids = {row.sequence_id for row in loaded_ids_result.all()}

    # ── process each barcode ───────────────────────────────────
    to_insert_seqs: list[ExportAwbSkidItemSequence] = []
    results: list[ScanItemResult] = []
    in_memory_loaded = already_loaded_count
    seen_in_batch: set[str] = set()

    for seq_no in sequence_nos:

        # duplicate in batch
        if seq_no in seen_in_batch:
            results.append(ScanItemResult(
                sequence_no=seq_no, awb_no=awb.awb_no,
                success=False, message="Duplicate in batch",
            ))
            continue
        seen_in_batch.add(seq_no)

        # already exists in DB
        if seq_no in existing_seq_map:
            seq_id = existing_seq_map[seq_no]
            msg = "Already loaded into ULD" if seq_id in already_loaded_ids \
                else "Sequence already scanned — contact supervisor"
            results.append(ScanItemResult(
                sequence_no=seq_no, awb_no=awb.awb_no,
                success=False, message=msg,
            ))
            continue

        # booked_pcs cap
        if in_memory_loaded >= booked_pcs:
            results.append(ScanItemResult(
                sequence_no=seq_no, awb_no=awb.awb_no,
                success=False,
                message=f"AWB fully loaded — {in_memory_loaded}/{booked_pcs} pcs done",
            ))
            continue

        # all good
        to_insert_seqs.append(ExportAwbSkidItemSequence(
            awb_master_id=awb_master_id,
            mapping_id=mapping_id,
            sequence_no=seq_no,
            sequence_date_time=now,
            scanned_by=loaded_by,
            scan_by_device="ULTRAFAST-ULD-GATE",
        ))
        results.append(ScanItemResult(
            sequence_no=seq_no, awb_no=awb.awb_no,
            success=True, message=f"Loaded into ULD {uld_no}",
        ))
        in_memory_loaded += 1

    # ── bulk insert sequences then loading rows ────────────────
    if to_insert_seqs:
        db.add_all(to_insert_seqs)
        await db.flush()

        db.add_all([
            ExportSequenceItemUldLoading(
                flight_header_id=flight_header_id,
                uld_assignment_detail_id=uld_assignment_detail_id,
                sequence_id=seq_obj.id,
                awb_master_id=awb_master_id,
                mapping_id=mapping_id,
                loaded_by=loaded_by,
                loaded_at=now,
                created_at=now,
            )
            for seq_obj in to_insert_seqs
        ])
        await db.flush()

        # auto complete if cap reached
        if in_memory_loaded >= booked_pcs:
            await db.execute(
                update(ExportAwbSkidMapping)
                .where(ExportAwbSkidMapping.id == mapping_id)
                .values(is_skid_used_complete=True)
            )

        await db.commit()

    total_loaded = sum(1 for r in results if r.success)
    total_failed = len(results) - total_loaded

    return ScanItemIntoUldResponse(
        success=True,
        message=f"{total_loaded} loaded, {total_failed} failed",
        uld_no=uld_no,
        total_submitted=len(sequence_nos),
        total_loaded=total_loaded,
        total_failed=total_failed,
        results=results,
    )







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