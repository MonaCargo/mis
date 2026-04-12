# app/services/export_skid_service.py

from datetime import datetime, timezone, timedelta
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import select, func, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exportOperation.car_message import (
    ExportCarMessageAwbMaster,
    ExportAwbSkidMapping,
    ExportAwbSkidItemSequence,
    ExportSequenceItemUldLoading,
    ExportSkidBaseMapping,
    ExportSkidLocationMapping,
)
from app.db.models.exportOperation.export_location_master import ExportLocationsMaster
from app.db.models.exportOperation.export_skid_master import ExportSkidMaster
from app.schemas.exportOperation.skid_master import CreateSkidRequest, ScanSequenceItemInput
from app.utils.common.helperFunction import get_utc_now

# ─────────────────────────────────────────────
STALE_LOCK_HOURS = 8544 # 365 days

# don't chnage thesevalue {if chnage then first checks all connected dots}
VIRTUAL_SKID_SEQ    = "virtual_skid_seq"
VIRTUAL_SKID_PREFIX = "V"
VIRTUAL_SKID_PADDING = 8          # V0000001 … V9999999
# ─────────────────────────────────────────────


# ═════════════════════════════════════════════════════════════════════
# PUBLIC FUNCTIONS — called directly by routes
# ═════════════════════════════════════════════════════════════════════

async def generate_virtual_skid(
    db: AsyncSession,
    emp_id: str,
) -> dict:
    """
    Uses PostgreSQL DB-level sequence (virtual_skid_seq) to get the
    next value atomically — parallel-safe, no ORM locking needed.

    is_virtual_used = False on creation → marks this as an orphan
    candidate until validate-and-lock flips it to True.
    """
    skid_no = await _next_virtual_skid_no(db)

    now_utc = get_utc_now()

    new_skid = ExportSkidMaster(
        skid_no=skid_no,
        skid_type="virtual",
        is_active=True,
        is_locked=False,
        is_virtual_used=False,      # ← not yet used, orphan candidate
        created_at=now_utc,
        updated_at=now_utc,
    )
    db.add(new_skid)
    await db.flush()                # resolve new_skid.id before commit
    await db.commit()
    await db.refresh(new_skid)

    return {
        "success": True,
        "skid_id": new_skid.id,
        "skid_no": new_skid.skid_no,
        "message": f"Virtual skid {skid_no} generated successfully.",
    }

async def _get_base_drop_for_skid(
    db: AsyncSession,
    skid_id: int,
    awb_master_id: int,    # ← ADD — scope to current AWB session
) -> bool:
    """
    For new mapping — check if this skid has been dropped at base
    in any recent session by skid_id.
    Used when mapping_id does not exist yet (first scan).
    """
    result = await db.execute(
        select(ExportSkidBaseMapping.id).where(
            ExportSkidBaseMapping.skid_id == skid_id,
            ExportSkidBaseMapping.awb_master_id == awb_master_id,  # ← scope to current AWB
        )
        .order_by(ExportSkidBaseMapping.dropped_at.desc())
        .limit(1)
    )
    return result.scalar_one_or_none() is not None


async def _get_base_drop_for_mapping(
    db: AsyncSession,
    mapping_id: int,
) -> bool:
    """Returns True if skid has been dropped at base for this mapping session."""
    result = await db.execute(
        select(ExportSkidBaseMapping.id).where(
            ExportSkidBaseMapping.mapping_id == mapping_id,
        )
    )
    return result.scalar_one_or_none() is not None


# async def validate_and_lock_skid(
#     db: AsyncSession,
#     awb_master_id: int,
#     skid_no: str,
#     emp_id: str,
# ) -> dict:
#     """
#     New clean flow — no user-based lock ownership logic:

#     1. AWB exists?
#     2. Skid exists + is_active? (with_for_update — row locked for this tx)
#     3. Is skid FREE?
#        - Locked non-stale by anyone → 409 hard block
#        - Locked stale (>24h)        → auto-unlock → treat as free
#        - Not locked                 → free
#     4. Skid is free — check existing mapping:
#        - mapping(awb_master_id + skid_id) EXISTS → RESUME
#            → re-lock skid (new user/time tracked)
#            → return existing mapping_id + already scanned count
#        - NO mapping → FRESH
#            → lock skid
#            → create new mapping
#            → return new mapping_id
#     """
#     # ── 1. AWB must exist ─────────────────────────────────────────
#     await _get_awb_master(db, awb_master_id)

#     # ── 2. Skid must exist and be active ──────────────────────────
#     # with_for_update() → row-level DB lock prevents concurrent
#     # requests from reading stale lock state simultaneously
#     skid = await _get_active_skid_for_update(db, skid_no)

#     # ── 3. Is skid free? ──────────────────────────────────────────
#     now_utc = get_utc_now()

#     if skid.is_locked:
#         lock_age = now_utc - skid.locked_at

#         if lock_age <= timedelta(hours=STALE_LOCK_HOURS):
#             # Non-stale lock — hard block regardless of who owns it
#             locked_since = skid.locked_at.strftime("%d-%b-%Y %H:%M UTC")
#             raise HTTPException(
#                 status_code=status.HTTP_409_CONFLICT,
#                 # detail=(
#                 #     f"Skid '{skid_no}' is currently in use "
#                 #     f"(locked since {locked_since}). "
#                 #     "Please wait for the current session to finish."
#                 # ),
#                  detail=(
#                     f"Skid '{skid_no}' is currently in use by '{skid.locked_by_user_id}' "
#                     f"(locked since {locked_since}). "
#                     "Please wait for the current session to finish."
#                 ),
#             )

#         # Stale lock — auto-release and treat as free
#         skid.is_locked = False
#         skid.locked_at = None
#         skid.locked_by_user_id = None
#         skid.updated_at = now_utc
#         await db.flush()

#     # ── 4a. Skid is free — check for existing mapping (resume) ────
#     existing_mapping = await _get_existing_mapping(db, awb_master_id, skid.id)

#     if existing_mapping:
#         # RESUME — re-lock skid so current session is tracked
#         skid.is_locked = True
#         skid.locked_at = now_utc
#         skid.locked_by_user_id = emp_id
#         skid.updated_at = now_utc

#         if skid.skid_type == "virtual":
#             skid.is_virtual_used = True

#         await db.flush()
#         await db.commit()
#         await db.refresh(skid)

#         scanned_count = await _get_sequence_count(db, existing_mapping.id)
#         return _build_response(
#             success=True,
#             message=(
#                 f"Resuming existing session on skid '{skid_no}'. "
#                 f"{scanned_count} item(s) already scanned."
#             ),
#             is_resumed=True,
#             mapping_id=existing_mapping.id,
#             awb_master_id=awb_master_id,
#             skid=skid,
#             already_scanned_count=scanned_count,
#         )

#     # REPLACE WITH ↓
#     await db.flush()
#     await db.commit()
#     await db.refresh(skid)

#     return _build_response(
#         success=True,
#         message=f"Skid '{skid_no}' locked. You can start scanning items.",
#         is_resumed=False,
#         mapping_id=None,          # ← No mapping yet, created on first scan
#         awb_master_id=awb_master_id,
#         skid=skid,
#         already_scanned_count=0,
#     )

#     # #  ── 4b. No mapping — FRESH lock + new mapping ─────────────────
#     # skid.is_locked = True
#     # skid.locked_at = now_utc
#     # skid.locked_by_user_id = emp_id
#     # skid.updated_at = now_utc

#     # if skid.skid_type == "virtual":
#     #     skid.is_virtual_used = True

#     # await db.flush()                # persist lock before mapping insert

#     # mapping = ExportAwbSkidMapping(
#     #     awb_master_id=awb_master_id,
#     #     skid_id=skid.id,
#     #     is_virtual=(skid.skid_type == "virtual"),
#     #     virtual_skid_no=(skid.skid_no if skid.skid_type == "virtual" else None),
#     #     created_at=now_utc,
#     # )
#     # db.add(mapping)
#     # await db.flush()
#     # await db.commit()
#     # await db.refresh(mapping)
#     # await db.refresh(skid)

#     # return _build_response(
#     #     success=True,
#     #     message=f"Skid '{skid_no}' locked and mapped. You can start scanning items.",
#     #     is_resumed=False,
#     #     mapping_id=mapping.id,
#     #     awb_master_id=awb_master_id,
#     #     skid=skid,
#     #     already_scanned_count=0,
#     # )


async def validate_and_lock_skid(
    db: AsyncSession,
    awb_master_id: int,
    skid_no: str,
    emp_id: str,
) -> dict:
    """
    Full flow:

    1. AWB exists?
    2. Skid exists + is_active? (with_for_update)
    3. Is skid FREE?
       - Locked non-stale → 409 hard block (someone else using it)
       - Locked stale     → auto-unlock → treat as free
       - Not locked       → free
    3b. PREEMPTIVE CHECK (before any lock attempt):
       - mapping EXISTS + scanned items → 409 hard block
       - mapping EXISTS + empty         → 409 hard block (already mapped)
       - no mapping                     → proceed to fresh lock
    4. FRESH ONLY — no mapping exists:
       - lock skid
       - return mapping_id=None (mapping created on first scan)
    """

    # ── 1. AWB must exist ─────────────────────────────────────────
    await _get_awb_master(db, awb_master_id)

    # ── 2. Skid must exist and be active ──────────────────────────
    # with_for_update() → row-level DB lock prevents concurrent
    # requests from reading stale lock state simultaneously
    skid = await _get_active_skid_for_update(db, skid_no)

    # ── 3. Is skid free? ──────────────────────────────────────────
    now_utc = get_utc_now()

    if skid.is_locked:
        lock_age = now_utc - skid.locked_at

        if lock_age <= timedelta(hours=STALE_LOCK_HOURS):
            # Non-stale lock — hard block, someone else is actively using it
            locked_since = skid.locked_at.strftime("%d-%b-%Y %H:%M UTC")
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Skid '{skid_no}' is currently in use by '{skid.locked_by_user_id}' "
                    f"(locked since {locked_since}). "
                    "Please wait for the current session to finish."
                ),
            )

        # Stale lock — auto-release and treat as free
        skid.is_locked = False
        skid.locked_at = None
        skid.locked_by_user_id = None
        skid.updated_at = now_utc
        await db.flush()

    # ── 3b. PREEMPTIVE CHECK — before locking, check mapping state ─
    # Single DB call — hard block on ANY existing mapping
    existing_mapping = await _get_existing_mapping(db, awb_master_id, skid.id)

    if existing_mapping:
        scanned_count = await _get_sequence_count(db, existing_mapping.id)

        if scanned_count > 0:
            # Mapping exists + has scanned items — hard block
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Skid '{skid_no}' already has an active scanning session "
                    f"with {scanned_count} item(s) scanned under this AWB "
                    f"(mapping_id={existing_mapping.id}). "
                    "Cannot lock again. Use existing session or contact supervisor."
                ),
            )
        else:
            # Mapping exists but empty — still hard block
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Skid '{skid_no}' is already mapped to this AWB "
                    f"(mapping_id={existing_mapping.id}) but has no items scanned yet. "
                    "Cannot lock again. Contact supervisor to clear this mapping."
                ),
            )

    # ── 4. FRESH ONLY — no mapping exists at all ──────────────────
    # Only reaches here if zero mapping exists for this awb + skid
    # Lock skid — mapping created on first actual scan, not here
    skid.is_locked = True
    skid.locked_at = now_utc
    skid.locked_by_user_id = emp_id
    skid.updated_at = now_utc

    if skid.skid_type == "virtual":
        skid.is_virtual_used = True

    await db.flush()
    await db.commit()
    await db.refresh(skid)

    return _build_response(
        success=True,
        message=f"Skid '{skid_no}' locked. You can start scanning items.",
        is_resumed=False,
        mapping_id=None,        # ← No mapping yet, created on first scan
        awb_master_id=awb_master_id,
        skid=skid,
        already_scanned_count=0,
    )



# ✌️✌️PUBLIC — SCAN SEQUENCE ITEMS (single or bulk — always array)
# ═════════════════════════════════════════════════════════════════════

# ✅ Correct — per-item IST→UTC conversion
def _ist_to_utc(dt: datetime) -> datetime:
    from zoneinfo import ZoneInfo
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=ZoneInfo("Asia/Kolkata"))
    return dt.astimezone(ZoneInfo("UTC"))
    
# async def scan_sequence_item(
#     db: AsyncSession,
#     mapping_id: int,
#     awb_master_id: int,
#     sequence_nos: list[ScanSequenceItemInput], 
#     scan_by_device: str = None,   # ← ADD
#     scanned_by: str = None,       # ← ADD
#     is_final: bool = False
# ) -> dict:
#     """
#     Accepts an array of sequence_nos — single scan = array of 1.
#     All checks run BEFORE any insert (stop at first error, reject full batch).

#     Check order:
#     1. mapping exists
#     2. skid still locked and not stale (>24h → 423)
#     3. empty array guard
#     4. duplicates within the submitted batch itself
#     5. each item not already scanned on this AWB (409 on first hit)
#     6. total after insert would not exceed awb.pcs cap (400 on first hit)
#     7. bulk insert all rows in one flush
#     8. return full item list for this mapping
#     """
#     # ──> 1. Mapping must exist ─────────────────────────────────────
#     mapping = await _get_mapping(db, mapping_id)

#     # ──> 2. Skid lock must still be valid ──────────────────────────
#     await _assert_skid_still_locked(db, mapping.skid_id)

#     seq_strings = [item.sequence_no for item in sequence_nos]

#     # ──> 3. Empty array guard ──────────────────────────────────────
#     # After — only block empty if not final save:
#     if not seq_strings  and not is_final:
#     # if is_final + empty → skip all scan checks, just unlock
#         raise HTTPException(400, "sequence_nos array cannot be empty.")

#     # if not sequence_nos:
#     #     raise HTTPException(
#     #         status_code=status.HTTP_400_BAD_REQUEST,
#     #         detail="sequence_nos array cannot be empty.",
#     #     )


#     # ──> 4. Duplicates within submitted batch ──────────────────────
#     # e.g. operator scanned same barcode twice before hitting submit
#     seen = set()
#     for item in sequence_nos:
#         if item.sequence_no in seen:
#             raise HTTPException(
#                 status_code=status.HTTP_409_CONFLICT,
#                  detail=(
#                 f"Duplicate item '{item.sequence_no}' found within the submitted batch. "
#                 "Entire batch rejected. Please correct and resubmit."
#             ),
#             )
#         seen.add(item.sequence_no)

#     # ── 5. Each item must not already exist globally ─────────────
#     # sequence_no is globally unique — same item cannot be scanned
#     # twice regardless of which AWB or skid it belongs to
#     duplicate_details = []
#     existing_result = await db.execute(
#         select(
#             ExportAwbSkidItemSequence.sequence_no,
#             ExportAwbSkidItemSequence.awb_master_id,
#         ).where(
#             ExportAwbSkidItemSequence.sequence_no.in_(seq_strings),
#         )
#     )
#     already_scanned_rows = existing_result.all()

#         # NEW: separate into duplicate vs unique — don't raise, just filter
#     duplicate_seq_nos = {row.sequence_no for row in already_scanned_rows}

#     # ✅ Correct — filter objects, then re-extract strings
#     sequence_nos = [item for item in sequence_nos if item.sequence_no not in duplicate_seq_nos]
#     seq_strings = [item.sequence_no for item in sequence_nos]  # keep in sync
  

#     # Build duplicate detail message for response
#     duplicate_details = []
#     if already_scanned_rows:
#         conflict_awb_ids = list({row.awb_master_id for row in already_scanned_rows})
#         awb_result = await db.execute(
#             select(
#                 ExportCarMessageAwbMaster.id,
#                 ExportCarMessageAwbMaster.awb_no,
#             ).where(ExportCarMessageAwbMaster.id.in_(conflict_awb_ids))
#         )
#         awb_map = {row.id: row.awb_no for row in awb_result.all()}
#         duplicate_details = [
#             f"'{row.sequence_no}' (AWB: {awb_map.get(row.awb_master_id, 'unknown')})"
#             for row in already_scanned_rows
#         ]

#     # if already_scanned_rows:
#     #     # Fetch AWB nos for all conflicting items in one query
#     #     conflict_awb_ids = list({row.awb_master_id for row in already_scanned_rows})
#     #     awb_result = await db.execute(
#     #         select(
#     #             ExportCarMessageAwbMaster.id,
#     #             ExportCarMessageAwbMaster.awb_no,
#     #         ).where(ExportCarMessageAwbMaster.id.in_(conflict_awb_ids))
#     #     )
#     #     awb_map = {row.id: row.awb_no for row in awb_result.all()}

#     #     conflict_details = ", ".join(
#     #         f"'{row.sequence_no}' (AWB: {awb_map.get(row.awb_master_id, 'unknown')})"
#     #         for row in already_scanned_rows
#     #     )
#     #     raise HTTPException(
#     #         status_code=status.HTTP_409_CONFLICT,
#     #         detail=(
#     #             f"{len(already_scanned_rows)} item(s) already scanned globally: "
#     #             f"{conflict_details}. "
#     #             "Entire batch rejected."
#     #         ),
#     #     )
    

#     # ──> 6. AWB pcs cap check ──────────────────────────────────────
#     awb = await _get_awb_master(db, awb_master_id)
#     current_count = await _get_sequence_count_by_awb(db, awb_master_id)
#     incoming_count = len(sequence_nos)

#     # if awb.pcs is not None:
#     if awb.pcs is not None and incoming_count > 0:
#         if current_count >= awb.pcs:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=(
#                     f"AWB is already at full capacity — "
#                     f"{current_count}/{int(awb.pcs)} pcs scanned. "
#                     "Cannot scan more items."
#                 ),
#             )
#         if current_count + incoming_count > awb.pcs:
#             remaining = int(awb.pcs) - current_count
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=(
#                     f"Batch of {incoming_count} item(s) would exceed AWB capacity. "
#                     f"Only {remaining} more item(s) can be scanned "
#                     f"({current_count}/{int(awb.pcs)} pcs already done). "
#                     "Reduce batch size and resubmit."
#                 ),
#             )
        
        


#     # ──> 7. All checks passed — bulk insert IF(SEQ NO. OR AT LEAST ONE INTEM SCANNED )────────────────────────
#     if sequence_nos:

#         new_items = [
#             ExportAwbSkidItemSequence(
#                 awb_master_id=awb_master_id,
#                 mapping_id=mapping_id,
#                 sequence_no=item.sequence_no,                          # ← .sequence_no
#                 sequence_date_time=_ist_to_utc(item.sequence_date_time),  # ← per-item, converted
#                 scan_by_device=scan_by_device,   # ← ADD
#                 scanned_by=scanned_by,           # ← ADD
#             )
#             for item in sequence_nos  
#         ]
#         db.add_all(new_items)
#         await db.flush()        # resolve ids for all rows before commit
#         await db.commit()

#     # Added after db.commit() in step 7:{😎We remove this step because I want do not want to unlock the skid in this step}
#     # if is_final:
#         # await _unlock_skid(db, mapping.skid_id)    # ← new private helper for unloacked_skid


#     # ──> 8. Return full updated item list for this mapping ─────────
#     items = await _get_all_items_for_mapping(db, mapping_id)
#     total_scanned = await _get_sequence_count_by_awb(db, awb_master_id)

#     return {
#         "success": True,
#         "message": (
#                 f"{incoming_count} item(s) scanned successfully."
#                 if incoming_count > 1
#                 else f"Item '{sequence_nos[0].sequence_no}' scanned successfully."
#                 if incoming_count == 1
#                 else "No new items inserted."
#             ),
#         "inserted_count": incoming_count,
#          "skipped_duplicates": duplicate_details,  # ← NEW: list of skipped items with AWB info
#         "mapping_id": mapping_id,
#         "awb_master_id": awb_master_id,
#         "total_scanned": total_scanned,
#         "awb_total_pcs": awb.pcs,
#         "items": [
#             {
#                 "id": item.id,
#                 "sequence_no": item.sequence_no,
#                 "sequence_date_time": item.sequence_date_time,
#             }
#             for item in items
#         ],
#          "is_unlocked": False,    # ← added (is_final , we make it false because at save time not unlock skid)
#     }


async def scan_sequence_item(
    db: AsyncSession,
    mapping_id: Optional[int],
    skid_id: Optional[int],
    awb_master_id: int,
    sequence_nos: list[ScanSequenceItemInput],
    scan_by_device: str = None,
    scanned_by: str = None,
    is_final: bool = False,
) -> dict:
    """
    Accepts an array of sequence_nos — single scan = array of 1.
    All checks run BEFORE any insert (stop at first error, reject full batch).

    Check order:
    1. Get or create mapping
       - mapping_id given          → fetch it directly
       - mapping_id = None →
           ├── existing + scanned  → HARD REJECT 409
           ├── existing + empty    → DELETE old + build fresh (insert at step 7)
           └── no mapping          → build fresh (insert at step 7)
    2. Skid still locked and not stale (>STALE_LOCK_HOURS → 423)
    3. Empty array guard
    4. Duplicates within submitted batch itself
    5. Each item not already scanned globally → filter out, don't reject
    6. AWB pcs cap check
    7. Insert mapping (if new) + bulk insert items together
    8. Return full item list for this mapping
    """

    # ──> 1. Get or create mapping ──────────────────────────────────
    if mapping_id is not None:
        # Resume flow — mapping already exists
        mapping = await _get_mapping(db, mapping_id)
        is_new_mapping = False

    else:
        # Fresh entry — skid_id required
        if not skid_id:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="skid_id is required when mapping_id is not provided.",
            )

        # ── Check FIRST before any processing ──────────────────────
        existing_mapping = await _get_existing_mapping(db, awb_master_id, skid_id)

        if existing_mapping:
            scanned_count = await _get_sequence_count(db, existing_mapping.id)

            if scanned_count > 0:
                # ── HARD REJECT — already has scanned items ─────────
                raise HTTPException(
                    status_code=status.HTTP_409_CONFLICT,
                    detail=(
                        f"Skid already has {scanned_count} item(s) scanned "
                        f"under this AWB (mapping_id={existing_mapping.id}). "
                        "Use existing mapping_id to continue."
                    ),
                )
            else:
                # ── Empty mapping — delete it, create fresh below ───
                await db.delete(existing_mapping)
                await db.flush()    # ensure delete is committed before new insert

        # ── Fetch skid — needed to build new mapping object ────────
        skid_result = await db.execute(
            select(ExportSkidMaster).where(ExportSkidMaster.id == skid_id)
        )
        skid = skid_result.scalar_one_or_none()
        if not skid:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"Skid id '{skid_id}' not found.",
            )

        # ── Build new mapping object — NOT inserted yet ─────────────
        # Inserted at step 7 only if at least one item is actually saved
        now_utc = get_utc_now()
        mapping = ExportAwbSkidMapping(
            awb_master_id=awb_master_id,
            skid_id=skid_id,
            is_virtual=(skid.skid_type == "virtual"),
            virtual_skid_no=(skid.skid_no if skid.skid_type == "virtual" else None),
            mapped_by=scanned_by,   # ✅ emp_id who created the mapping
            mapped_at=now_utc,      # ✅ when mapping was created
            created_at=now_utc,
        )
        is_new_mapping = True

    # ──> 2. Skid lock must still be valid ──────────────────────────
    await _assert_skid_still_locked(db, mapping.skid_id)

    # # ──> 2.5 Base drop check — runs for ALL scans ─────────────────
    # # For existing mapping → check by mapping_id
    # # For new mapping → check by skid_id (mapping not created yet)

    # if not is_new_mapping:
    #     # existing mapping — check by mapping_id
    #     is_at_base = await _get_base_drop_for_mapping(db, mapping_id)
    # else:
    #     # new mapping — check by skid_id
    #     # skid must have a base drop record for ANY recent session
    #     is_at_base = await _get_base_drop_for_skid(db, mapping.skid_id, awb_master_id)

    # if not is_at_base:
    #     skid_no = mapping.virtual_skid_no or str(mapping.skid_id)
    #     return {
    #         "success": False,
    #         "message": (
    #             f"Skid {skid_no} has not been dropped at base yet. "
    #             "Please retrieve from location and drop at base before scanning."
    #         ),
    #         "inserted_count": 0,
    #         "skipped_duplicates": [],
    #         "mapping_id": mapping_id,
    #         "awb_master_id": awb_master_id,
    #         "total_scanned": await _get_sequence_count_by_awb(db, awb_master_id),
    #         "awb_total_pcs": (await _get_awb_master(db, awb_master_id)).pcs,
    #         "items": [],
    #         "is_unlocked": False,
    #         "reason": "NOT_AT_BASE",
    #     }
    # ──> 3. Empty array guard ──────────────────────────────────────
    seq_strings = [item.sequence_no for item in sequence_nos]

    if not seq_strings and not is_final:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="sequence_nos array cannot be empty.",
        )

    # ──> 4. Duplicates within submitted batch ──────────────────────
    # e.g. operator scanned same barcode twice before hitting submit
    seen = set()
    for item in sequence_nos:
        if item.sequence_no in seen:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=(
                    f"Duplicate item '{item.sequence_no}' found within the submitted batch. "
                    "Entire batch rejected. Please correct and resubmit."
                ),
            )
        seen.add(item.sequence_no)

    # ──> 5. Filter out globally already-scanned items ──────────────
    # sequence_no is globally unique — same item cannot be scanned
    # twice regardless of which AWB or skid it belongs to.
    # Don't raise — just skip and report in response.
    duplicate_details = []
    existing_result = await db.execute(
        select(
            ExportAwbSkidItemSequence.sequence_no,
            ExportAwbSkidItemSequence.awb_master_id,
        ).where(
            ExportAwbSkidItemSequence.sequence_no.in_(seq_strings),
        )
    )
    already_scanned_rows = existing_result.all()

    if already_scanned_rows:
        duplicate_seq_nos = {row.sequence_no for row in already_scanned_rows}

        # Filter out duplicates — keep only new items
        sequence_nos = [item for item in sequence_nos if item.sequence_no not in duplicate_seq_nos]
        seq_strings = [item.sequence_no for item in sequence_nos]  # keep in sync

        # Build duplicate detail list for response
        conflict_awb_ids = list({row.awb_master_id for row in already_scanned_rows})
        awb_result = await db.execute(
            select(
                ExportCarMessageAwbMaster.id,
                ExportCarMessageAwbMaster.awb_no,
            ).where(ExportCarMessageAwbMaster.id.in_(conflict_awb_ids))
        )
        awb_map = {row.id: row.awb_no for row in awb_result.all()}
        duplicate_details = [
            f"'{row.sequence_no}' (AWB: {awb_map.get(row.awb_master_id, 'unknown')})"
            for row in already_scanned_rows
        ]

    # ──> 6. AWB pcs cap check ──────────────────────────────────────
    awb = await _get_awb_master(db, awb_master_id)
    current_count = await _get_sequence_count_by_awb(db, awb_master_id)
    incoming_count = len(sequence_nos)

    if awb.pcs is not None and incoming_count > 0:
        if current_count >= awb.pcs:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"AWB is already at full capacity — "
                    f"{current_count}/{int(awb.pcs)} pcs scanned. "
                    "Cannot scan more items."
                ),
            )
        if current_count + incoming_count > awb.pcs:
            remaining = int(awb.pcs) - current_count
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Batch of {incoming_count} item(s) would exceed AWB capacity. "
                    f"Only {remaining} more item(s) can be scanned "
                    f"({current_count}/{int(awb.pcs)} pcs already done). "
                    "Reduce batch size and resubmit."
                ),
            )

    # ──> 7. Insert mapping (if new) + bulk insert items ────────────
    if sequence_nos:
        if is_new_mapping:
            # Only now — mapping created because at least 1 item will be saved
            db.add(mapping)
            await db.flush()        # ← get mapping.id before item insert
            mapping_id = mapping.id

        new_items = [
            ExportAwbSkidItemSequence(
                awb_master_id=awb_master_id,
                mapping_id=mapping_id,
                sequence_no=item.sequence_no,
                sequence_date_time=_ist_to_utc(item.sequence_date_time),
                scan_by_device=scan_by_device,
                scanned_by=scanned_by,
            )
            for item in sequence_nos
        ]
        db.add_all(new_items)
        await db.flush()
        await db.commit()

    elif is_new_mapping:
        # All submitted items were duplicates — don't save empty mapping
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                "All submitted items were already scanned globally. "
                "No new items saved — mapping not created."
            ),
        )

    # ──> 8. Return full updated item list for this mapping ─────────
    items = await _get_all_items_for_mapping(db, mapping_id)
    total_scanned = await _get_sequence_count_by_awb(db, awb_master_id)

    return {
        "success": True,
        "message": (
            f"{incoming_count} item(s) scanned successfully."
            if incoming_count > 1
            else f"Item '{sequence_nos[0].sequence_no}' scanned successfully."
            if incoming_count == 1
            else "No new items inserted."
        ),
        "inserted_count": incoming_count,
        "skipped_duplicates": duplicate_details,
        "mapping_id": mapping_id,
        "awb_master_id": awb_master_id,
        "total_scanned": total_scanned,
        "awb_total_pcs": awb.pcs,
        "items": [
            {
                "id": item.id,
                "sequence_no": item.sequence_no,
                "sequence_date_time": item.sequence_date_time,
            }
            for item in items
        ],
        "is_unlocked": False,
    }

async def delete_sequence_item(
    db: AsyncSession,
    sequence_id: int,
    mapping_id: int,
    awb_master_id: int,
) -> dict:
    """
    Removes a wrongly scanned item.
    Skid must still be locked to allow deletion.
    Returns updated full item list after deletion.
    """
    # ── Mapping must exist ────────────────────────────────────────
    mapping = await _get_mapping(db, mapping_id)

    # ── Skid lock must still be valid ─────────────────────────────
    await _assert_skid_still_locked(db, mapping.skid_id)

    # ── Sequence item must exist and belong to this mapping ───────
    result = await db.execute(
        select(ExportAwbSkidItemSequence).where(
            ExportAwbSkidItemSequence.id == sequence_id,
            ExportAwbSkidItemSequence.mapping_id == mapping_id,
        )
    )
    item = result.scalar_one_or_none()
    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"Scanned item with id '{sequence_id}' not found "
                "under this mapping."
            ),
        )

    deleted_sequence_no = item.sequence_no
    await db.delete(item)
    await db.commit()

    # ── Return updated list ───────────────────────────────────────
    items = await _get_all_items_for_mapping(db, mapping_id)
    total_scanned = await _get_sequence_count_by_awb(db, awb_master_id)

    awb = await _get_awb_master(db, awb_master_id)

    return {
        "success": True,
        "message": f"Item '{deleted_sequence_no}' removed successfully.",
        "deleted_sequence_no": deleted_sequence_no,
        "mapping_id": mapping_id,
        "total_scanned": total_scanned,
        "awb_total_pcs": awb.pcs,
        "items": [
            {
                "id": i.id,
                "sequence_no": i.sequence_no,
                "sequence_date_time": i.sequence_date_time,
            }
            for i in items
        ],
    }


async def force_unlock_skid(
    db: AsyncSession,
    skid_no: str,
    emp_id: str,
) -> dict:
    """
    Manually unlocks a skid by skid_no — for supervisor/admin use.
    Does not check who locked it or whether lock is stale.
    Works on any locked skid regardless of state.
    Records who force-unlocked it via locked_by_user_id = None + updated_at.
    """
    # ── Skid must exist ───────────────────────────────────────────
    result = await db.execute(
        select(ExportSkidMaster)
        .where(ExportSkidMaster.skid_no == skid_no)
        .with_for_update()
    )
    skid = result.scalar_one_or_none()

    if not skid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skid '{skid_no}' not found.",
        )

    # ── Already free — nothing to do ──────────────────────────────
    if not skid.is_locked:
        return {
            "success": True,
            "message": f"Skid '{skid_no}' is already unlocked. No action taken.",
            "skid_no": skid_no,
            "skid_id": skid.id,
            "was_locked": False,
            "unlocked_by": emp_id,
        }

    # ── Force unlock ───────────────────────────────────────────────
    previously_locked_by = skid.locked_by_user_id
    previously_locked_at = skid.locked_at

    skid.is_locked = False
    skid.locked_at = None
    skid.locked_by_user_id = None
    skid.updated_at = get_utc_now()

    await db.flush()
    await db.commit()

    return {
        "success": True,
        "message": (
            f"Skid '{skid_no}' forcefully unlocked by '{emp_id}'. "
            f"Was locked by '{previously_locked_by}' "
            f"since {previously_locked_at.strftime('%d-%b-%Y %H:%M UTC')}."
        ),
        "skid_no": skid_no,
        "skid_id": skid.id,
        "was_locked": True,
        "previously_locked_by": previously_locked_by,
        "previously_locked_at": previously_locked_at,
        "unlocked_by": emp_id,
    }



# ═════════════════════════════════════════════════════════════════════
# PUBLIC — LOCATION SKID MAPPING ASSIGNMENT (and skid Relocation)
# ═════════════════════════════════════════════════════════════════════

# async def get_skid_by_sequence(
#     db: AsyncSession,
#     sequence_no: str,
# ) -> dict:
#     """
#     Reverse lookup — given any scanned sequence item barcode,
#     returns the skid it belongs to along with mapping + AWB context.

#     Used for virtual skids where user has no skid barcode
#     but holds the item barcode. Frontend calls this first,
#     gets skid_no + mapping_id + awb_master_id, then proceeds
#     to assign-location with that data.
#     """
#     # ── Find sequence item ────────────────────────────────────────
#     result = await db.execute(
#         select(ExportAwbSkidItemSequence).where(
#             ExportAwbSkidItemSequence.sequence_no == sequence_no
#         )
#     )
#     item = result.scalar_one_or_none()

#     if not item:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=(
#                 f"Sequence item '{sequence_no}' not found. "
#                 "Please check the barcode and try again."
#             ),
#         )

#     # ── Get mapping from item ─────────────────────────────────────
#     mapping = await _get_mapping(db, item.mapping_id)

#     # ── Get skid from mapping ─────────────────────────────────────
#     result = await db.execute(
#         select(ExportSkidMaster).where(
#             ExportSkidMaster.id == mapping.skid_id
#         )
#     )
#     skid = result.scalar_one_or_none()

#     if not skid:
#         raise HTTPException(
#             status_code=status.HTTP_404_NOT_FOUND,
#             detail=f"Skid not found for sequence item '{sequence_no}'.",
#         )
#     # ── Only virtual skids allowed here ───────────────────────────
#     if skid.skid_type != "virtual":
#         raise HTTPException(
#             status_code=status.HTTP_400_BAD_REQUEST,
#             detail=(
#                 f"Sequence item '{sequence_no}' belongs to a real skid '{skid.skid_no}'. "
#                 "This lookup is only for virtual skids. "
#                 "Please scan the skid barcode in Normal mode."
#             ),
#         )

#     # ── Get AWB master ────────────────────────────────────────────
#     awb = await _get_awb_master(db, item.awb_master_id)

#     # ── Get total scanned count for this skid mapping ─────────────
#     scanned_count = await _get_sequence_count(db, mapping.id)

#     return {
#         "sequence_no": sequence_no,
#         "skid_id": skid.id,
#         "skid_no": skid.skid_no,
#         "skid_type": skid.skid_type,
#         "mapping_id": mapping.id,
#         "awb_master_id": awb.id,
#         "awb_no": awb.awb_no,
#         "pcs": awb.pcs,  # total pcs in awb
#         "scanned_count": scanned_count,
#     }

async def get_skid_by_sequence(
    db: AsyncSession,
    sequence_no: str,
) -> dict:
    # ── Find sequence item ────────────────────────────────────────
    result = await db.execute(
        select(ExportAwbSkidItemSequence).where(
            ExportAwbSkidItemSequence.sequence_no == sequence_no
        )
    )
    item = result.scalar_one_or_none()

    if not item:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Sequence item '{sequence_no}' not found. Please check the barcode and try again.",
        )

    # ── Get mapping from item ─────────────────────────────────────
    mapping = await _get_mapping(db, item.mapping_id)

    # ── Get skid from mapping ─────────────────────────────────────
    result = await db.execute(
        select(ExportSkidMaster).where(ExportSkidMaster.id == mapping.skid_id)
    )
    skid = result.scalar_one_or_none()

    if not skid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skid not found for sequence item '{sequence_no}'.",
        )

    if skid.skid_type != "virtual":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=(
                f"Sequence item '{sequence_no}' belongs to a real skid '{skid.skid_no}'. "
                "This lookup is only for virtual skids. "
                "Please scan the skid barcode in Normal mode."
            ),
        )
    
    # ------======-----===-------

    # # ── Get AWB master ────────────────────────────────────────────
    # awb = await _get_awb_master(db, item.awb_master_id)

    # # ── Get ALL sequences for this mapping (replaces _get_sequence_count) ──
    # seq_result = await db.execute(
    #     select(ExportAwbSkidItemSequence)
    #     .where(ExportAwbSkidItemSequence.mapping_id == mapping.id)
    #     .order_by(ExportAwbSkidItemSequence.sequence_date_time.asc())
    # )
    # sequences = seq_result.scalars().all()

    # # ── Get current location for this skid ───────────────────────
    # loc_result = await db.execute(
    #     select(ExportSkidLocationMapping, ExportLocationsMaster)
    #     .join(
    #         ExportLocationsMaster,
    #         ExportLocationsMaster.id == ExportSkidLocationMapping.location_id,
    #     )
    #     .where(
    #         ExportSkidLocationMapping.skid_id == skid.id,
    #         ExportSkidLocationMapping.is_current == True,
    #     )
    # )
    # loc_row = loc_result.first()
    # current_location = loc_row.ExportLocationsMaster.loc if loc_row else None

    # return {
    #     "success": True,
    #     "message": f"Skid '{skid.skid_no}' found via sequence item '{sequence_no}'.",
    #     "skid": {
    #         "id": skid.id,
    #         "skid_no": skid.skid_no,
    #         "skid_type": skid.skid_type,
    #         "skid_wgt": skid.skid_wgt,
    #         "skid_capacity": skid.skid_capacity,
    #         "is_active": skid.is_active,
    #         "is_locked": skid.is_locked,
    #         "locked_by": skid.locked_by_user_id,
    #         "locked_at": skid.locked_at,
    #         "is_virtual_used": skid.is_virtual_used,
    #     },
    #     "mapping": {
    #         "id": mapping.id,
    #         "awb_master_id": mapping.awb_master_id,
    #         "is_virtual": mapping.is_virtual,
    #         "virtual_skid_no": mapping.virtual_skid_no,
    #         "created_at": mapping.created_at,
    #         "scanned_count": len(sequences),
    #         "current_location": current_location,
    #         "sequences": [
    #             {
    #                 "id": s.id,
    #                 "sequence_no": s.sequence_no,
    #                 "sequence_date_time": s.sequence_date_time,
    #                 "scan_by_device": s.scan_by_device,
    #                 "scanned_by": s.scanned_by,
    #             }
    #             for s in sequences
    #         ],
    #     },
    #     "awb": {
    #         "id": awb.id,
    #         "awb_no": awb.awb_no,
    #         "pcs": awb.pcs,
    #     } if awb else None,
    # }
    # -------=======------

    # ✅ CALL SHARED FUNCTION
    return await get_skid_mapping_full_info_with_action_status(
        db=db,
        mapping_id=mapping.id
    )

async def assign_skid_to_location(
    db: AsyncSession,
    skid_no: str,
    location_id: int,
    awb_master_id: int,
    emp_id: str,
) -> dict:
    """
    Maps a skid to a location after scanning is complete.
    Skid stays locked — unlock happens in a later separate step.
    Done by a different user/shift than scanning — no lock ownership check.

    Steps:
    1. Validate skid exists
    2. Validate location exists and is_active
    3. Validate AWB master exists
    4. Find mapping_id from awb_master_id + skid_id
    5. Check if skid already at this exact location → 409 warn, no duplicate
    6. Flip any existing is_current=True row for this skid → is_current=False
    7. Insert new ExportSkidLocationMapping with is_current=True
    8. Return full assignment details

    ->⚠️ no duplicate assignment” rule is enforced globally per skid, That means if the skid is already assigned to any location (regardless of AWB master), the function raises a 409 Conflict.
    """
    # ── 1. Skid must exist ────────────────────────────────────────
    skid = await _get_skid_by_no(db, skid_no)

    # ── 2. Location must exist and be active ──────────────────────
    location = await _get_active_location(db, location_id)

    # ── 3. AWB must exist ─────────────────────────────────────────
    await _get_awb_master(db, awb_master_id)

    # ── 4. Find mapping_id for this skid + AWB ────────────────────
    scan_mapping = await _get_existing_mapping_for_location_mapping(db, awb_master_id, skid.id)
    if not scan_mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=(
                f"No scanning session found for skid '{skid_no}' "
                f"under AWB master id '{awb_master_id}'. "
                "Please complete the scanning step first."
            ),
        )

    # ── 5. Already assigned to ANY location → hard block ─────────
    # Once assigned, skid is locked to that location on this screen.
    # Different screen/step handles any further movement.
    existing_loc = await _get_current_location_mapping(db, skid.id)
    if existing_loc:
        # Fetch location name for clear error message
        existing_location = await _get_active_location(db, existing_loc.location_id)
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=(
                f"Skid '{skid_no}' is already assigned to location "
                f"'{existing_location.loc}' by '{existing_loc.assigned_by}' "
                f"on {existing_loc.assigned_at.strftime('%d-%b-%Y %H:%M UTC')}. "
                "Location assignment cannot be changed here."
            ),
        )

    # ── 6. Insert new location mapping ────────────────────────────
    now_utc = get_utc_now()
    new_loc_mapping = ExportSkidLocationMapping(
        skid_id=skid.id,
        location_id=location_id,
        awb_master_id=awb_master_id,
        mapping_id=scan_mapping.id,
        assigned_at=now_utc,
        assigned_by=emp_id,
        is_current=True,
    )
    db.add(new_loc_mapping)
    await db.flush()
    await db.commit()
    await db.refresh(new_loc_mapping)

    return {
        "success": True,
        "message": (
            f"Skid '{skid_no}' successfully assigned to "
            f"location '{location.loc}'."
        ),
        "skid_location_mapping_id": new_loc_mapping.id,
        "skid_id": skid.id,
        "skid_no": skid.skid_no,
        "awb_master_id": awb_master_id,
        "mapping_id": scan_mapping.id,
        "location": {
            "id": location.id,
            "loc": location.loc,
            "area_code": location.area_code,
            "ops_type": location.ops_type,
        },
        "assigned_at": new_loc_mapping.assigned_at,
        "assigned_by": new_loc_mapping.assigned_by,
        "is_current": new_loc_mapping.is_current,
    }




#  ============================================================
async def get_skid_recent_mapping_info(
    db: AsyncSession,
    skid_no: str,
) -> dict:
    """
    1. Validate skid exists in skid master
    2. If exists → find most recent mapping for this skid
    3. If mapping found → return mapping + AWB basic info
    4. If no mapping → return skid info only with message
    """

    # ── 1. Validate skid exists ───────────────────────────────────
    result = await db.execute(
        select(ExportSkidMaster).where(
            ExportSkidMaster.skid_no == skid_no
            
        )
    )
    skid = result.scalar_one_or_none()

    if not skid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skid '{skid_no}' not found. Please check the barcode.",
        )

    # ── 2. Find most recent mapping for this skid ─────────────────
    mapping_result = await db.execute(
        select(ExportAwbSkidMapping)
        .where(ExportAwbSkidMapping.skid_id == skid.id,
            #    ExportAwbSkidMapping.is_skid_used_complete == False,
               )
        .order_by(ExportAwbSkidMapping.created_at.desc())
        
        .limit(1)
    )
    mapping = mapping_result.scalar_one_or_none()

    # ── 3. No mapping found — return skid info only ───────────────
    if not mapping:
        return {
            "success": False,
            "message": f"Skid '{skid_no}' found but not mapped to any AWB yet.",
            "skid": {
                "id": skid.id,
                "skid_no": skid.skid_no,
                "skid_type": skid.skid_type,
                "skid_wgt": skid.skid_wgt,
                "skid_capacity": skid.skid_capacity,
                "is_active": skid.is_active,
                "is_locked": skid.is_locked,
                "locked_by": skid.locked_by_user_id,
                "locked_at": skid.locked_at,
                "is_virtual_used": skid.is_virtual_used,
            },
            "mapping": None,
            "awb": None,
        }

    # ── 4. Mapping found — fetch AWB info ─────────────────────────
    awb_result = await db.execute(
        select(ExportCarMessageAwbMaster).where(
            ExportCarMessageAwbMaster.id == mapping.awb_master_id
        )
    )
    awb = awb_result.scalar_one_or_none()

    # ── 5. Get scanned items count for this mapping ────────────────
    # scanned_count = await _get_sequence_count(db, mapping.id)
    
    # ── 5. Get all scanned sequences for this mapping ─────────────
    seq_result = await db.execute(
        select(ExportAwbSkidItemSequence)
        .where(ExportAwbSkidItemSequence.mapping_id == mapping.id)
        .order_by(ExportAwbSkidItemSequence.sequence_date_time.asc())
    )
    sequences = seq_result.scalars().all()



    # ── 6. Get current location for this skid ────────────────────
    loc_result = await db.execute(
        select(ExportSkidLocationMapping, ExportLocationsMaster)
        .join(
            ExportLocationsMaster,
            ExportLocationsMaster.id == ExportSkidLocationMapping.location_id,
        )
        .where(
            ExportSkidLocationMapping.skid_id == skid.id,
            ExportSkidLocationMapping.is_current == True,
        )
    )
    loc_row = loc_result.first()
    location_mapping = loc_row.ExportSkidLocationMapping if loc_row else None
    current_location = loc_row.ExportLocationsMaster.loc if loc_row else None

        # 7 ── Get loaded in uld pcs count (VERY IMPORTANT) ─────────────
    loaded_result = await db.execute(
        select(func.count(ExportSequenceItemUldLoading.id))
        .where(ExportSequenceItemUldLoading.mapping_id == mapping.id)
    )
    loaded_count = loaded_result.scalar() or 0
    scanned_count = len(sequences)
    remaining_pcs = scanned_count - loaded_count

     # ── Get last location (retrieval time) ─────────────
    base_result = await db.execute(
    select(ExportSkidBaseMapping)
    .where(ExportSkidBaseMapping.mapping_id == mapping.id)
    .order_by(ExportSkidBaseMapping.dropped_at.desc())
    .limit(1)
    )
    last_base = base_result.scalar_one_or_none()

    last_base_drop_at = last_base.dropped_at if last_base else None

    # last_retrieved_at = location_mapping.picked_at if location_mapping else None
    # last_retrieved_at = (
    # location_mapping.picked_at if location_mapping and location_mapping.picked_at else None
    # )

    retrieval_result = await db.execute(
    select(ExportSkidLocationMapping.picked_at)
    .where(
        ExportSkidLocationMapping.skid_id == skid.id,
        ExportSkidLocationMapping.picked_at.isnot(None),
    )
    .order_by(ExportSkidLocationMapping.picked_at.desc())
    .limit(1)
    )

    last_retrieved_at = retrieval_result.scalar_one_or_none()

    is_at_base = (
        last_base_drop_at is not None
        and last_retrieved_at is not None
        and last_base_drop_at >= last_retrieved_at
    )

    if mapping.is_skid_used_complete:
        allowed_action = "COMPLETE"
    
    # 🟢 NEW CASE — never placed anywhere
    elif current_location is None and last_retrieved_at is None:
        allowed_action = "NEW_ASSIGN"

    elif current_location:
        allowed_action = "RELOCATE_OR_RETRIEVE"
    
    # 🔵 PARTIAL LOAD → return to location
    elif remaining_pcs > 0 and loaded_count > 0 and not is_at_base:
        allowed_action = "RETURN_TO_LOCATION"

    elif not is_at_base:
        allowed_action = "DROP_AT_BASE"

    elif remaining_pcs > 0:
        allowed_action = "SCAN_INTO_ULD"

    else:
        allowed_action = "COMPLETE"

    # -------🤮

    return {
        "success": True,
        "message": f"Skid '{skid_no}' found with active AWB mapping.",
        "skid": {
            "id": skid.id,
            "skid_no": skid.skid_no,
            "skid_type": skid.skid_type,
            "skid_wgt": skid.skid_wgt,
            "skid_capacity": skid.skid_capacity,
            "is_active": skid.is_active,
            "is_locked": skid.is_locked,
            "locked_by": skid.locked_by_user_id,
            "locked_at": skid.locked_at,
            "is_virtual_used": skid.is_virtual_used,
        },
        "mapping": {
            "id": mapping.id,
            "awb_master_id": mapping.awb_master_id,
            "is_virtual": mapping.is_virtual,
            "virtual_skid_no": mapping.virtual_skid_no,
            "created_at": mapping.created_at,
            "scanned_count": len(sequences),   # ← derived from list, no separate query needed
    "current_location": current_location,

# -----🤮
     "loaded_count": loaded_count,
    "remaining_pcs": remaining_pcs,
     "is_fully_loaded": remaining_pcs == 0,
    "is_at_base": is_at_base,
    "allowed_action": allowed_action,


    "sequences": [
        {
            "id": s.id,
            "sequence_no": s.sequence_no,
            "sequence_date_time": s.sequence_date_time,
            "scan_by_device": s.scan_by_device,
            "scanned_by": s.scanned_by,
        }
        for s in sequences
    ],
        },
        "awb": {
            "id": awb.id,
            "awb_no": awb.awb_no,
            "pcs": awb.pcs,
        } if awb else None,
    }

# =================== skid relocation service 🤢 --------------

async def relocate_skid_service(
    skid_id: int,
    location_id: int,
    moved_by: str,
    db: AsyncSession,
    mapping_id: Optional[int] = None,   # ✅ ADD — required for post-base case
    relocation_from_base: bool = False,
):
    now = datetime.now(timezone.utc)

    # ── validate location exists ───────────────────────────────
    new_location = await db.get(ExportLocationsMaster, location_id)
    if not new_location:
        raise HTTPException(status_code=404, detail="Location not found")

    # ── CASE 1 — Normal relocation (location → location) ───────
    # skid has is_current=True location row
    current_result = await db.execute(
        select(ExportSkidLocationMapping).where(
            ExportSkidLocationMapping.skid_id == skid_id,
            ExportSkidLocationMapping.is_current == True,
        )
    )
    current_loc = current_result.scalar_one_or_none()

    if current_loc:
        # same location guard
        if current_loc.location_id == location_id:
            raise HTTPException(
                status_code=400,
                detail="Skid is already at this location",
            )

        # close old location
        current_loc.is_current = False
        current_loc.picked_at = now
        current_loc.picked_by = moved_by
        current_loc.is_relocation = True

        # create new location row
        db.add(ExportSkidLocationMapping(
            skid_id=skid_id,
            location_id=location_id,
            awb_master_id=current_loc.awb_master_id,
            mapping_id=current_loc.mapping_id,
            assigned_at=now,
            assigned_by=moved_by,
            is_current=True,
            is_relocation=False,
        ))

        await db.commit()
        return {
            "success": True,
            "case": "LOCATION_TO_LOCATION",
            "message": f"Skid relocated to {new_location.loc}",
            "new_location": new_location.loc,
        }

   
    # ── CASE 2 — Post-base relocation (base → location) ────────
    # skid has no is_current=True — was retrieved and dropped at base
    if relocation_from_base:
        if not mapping_id:
            raise HTTPException(
                status_code=400,
                detail=(
                    "Skid has no current location. "
                    "If relocating after base drop, provide mapping_id."
                ),
            )

        # validate mapping belongs to this skid
        mapping = await db.get(ExportAwbSkidMapping, mapping_id)
        if not mapping or mapping.skid_id != skid_id:
            raise HTTPException(
                status_code=400,
                detail="mapping_id does not belong to this skid",
            )

        # ── get last retrieval time ────────────────────────────────
        last_retrieval_result = await db.execute(
            select(ExportSkidLocationMapping.picked_at)
            .where(
                ExportSkidLocationMapping.mapping_id == mapping_id,
                ExportSkidLocationMapping.picked_at.isnot(None),
            )
            .order_by(ExportSkidLocationMapping.picked_at.desc())
            .limit(1)
        )
        last_retrieval_at = last_retrieval_result.scalar_one_or_none()

        if not last_retrieval_at:
            raise HTTPException(
                status_code=400,
                detail="Skid not retrieved yet — cannot relocate",
            )

        # ── base drop must exist AFTER last retrieval (current cycle)
        valid_base = await db.execute(
            select(ExportSkidBaseMapping.id).where(
                ExportSkidBaseMapping.mapping_id == mapping_id,
                ExportSkidBaseMapping.dropped_at >= last_retrieval_at,
            )
        )
        if not valid_base.scalar_one_or_none():
            raise HTTPException(
                status_code=400,
                detail="Skid not dropped at base for current cycle — drop at base first",
            )

        # ── must have remaining pcs ────────────────────────────────
        total = await db.scalar(
            select(func.count(ExportAwbSkidItemSequence.id)).where(
                ExportAwbSkidItemSequence.mapping_id == mapping_id,
            )
        ) or 0

        loaded = await db.scalar(
            select(func.count(ExportSequenceItemUldLoading.id))
            .join(
                ExportAwbSkidItemSequence,
                ExportSequenceItemUldLoading.sequence_id == ExportAwbSkidItemSequence.id,
            )
            .where(ExportAwbSkidItemSequence.mapping_id == mapping_id)
        ) or 0

        if loaded >= total:
            raise HTTPException(
                status_code=400,
                detail="All pcs already loaded — skid complete, relocation not needed",
            )

        # ── create fresh location row for remaining pcs ────────────
        db.add(ExportSkidLocationMapping(
            skid_id=skid_id,
            location_id=location_id,
            awb_master_id=mapping.awb_master_id,
            mapping_id=mapping_id,
            assigned_at=now,
            assigned_by=moved_by,
            is_current=True,
            is_relocation=True,
        ))

        await db.commit()

        return {
            "success": True,
            "case": "BASE_TO_LOCATION",
            "message": f"Remaining {total - loaded} pcs relocated to {new_location.loc}",
            "new_location": new_location.loc,
            "remaining_pcs": total - loaded,
        }
    # ── FINAL CATCH-ALL ──────────────────────────────────────────
    raise HTTPException(
        status_code=400, 
        detail="Skid has no current location and relocation_from_base was not specified."
    )

# async def relocate_skid_service(
#     skid_id: int,
#     location_id: int,
#     moved_by: str,
#     db: AsyncSession,
# ):
#     # ── 1. Find the current active location row ───────────────────
#     current_stmt = (
#         select(ExportSkidLocationMapping)
#         .where(
#             ExportSkidLocationMapping.skid_id == skid_id,
#             ExportSkidLocationMapping.is_current == True,
#         )
#     )
#     result = await db.execute(current_stmt)
#     current_loc = result.scalar_one_or_none()

#     if not current_loc:
#         raise HTTPException(
#             status_code=400,
#             detail="Skid has no current location.First assign location then re-locate.",
#         )
#     # ── Guard: same location check ────────────────────────────────
#     if current_loc.location_id == location_id:
#         raise HTTPException(
#             status_code=400,
#             detail="Skid is already allocated to this location.",
#         )

#     now = datetime.now(timezone.utc)

#     # ── 2. Close old location row ─────────────────────────────────
#     current_loc.is_current = False
#     current_loc.picked_at = now
#     current_loc.picked_by = moved_by
#     current_loc.is_relocation = True 

#     # ── 3. Validate new location exists ──────────────────────────
#     loc_stmt = select(ExportLocationsMaster).where(ExportLocationsMaster.id == location_id)
#     loc_result = await db.execute(loc_stmt)
#     new_location = loc_result.scalar_one_or_none()

#     if not new_location:
#         raise HTTPException(status_code=404, detail="Location not found")

#     # ── 4. Insert new current location row ───────────────────────
#     new_loc = ExportSkidLocationMapping(
#         skid_id=skid_id,
#         location_id=location_id,
#         awb_master_id=current_loc.awb_master_id,
#         mapping_id=current_loc.mapping_id,
#         assigned_at=now,
#         assigned_by=moved_by,
#         is_current=True,
#         is_relocation=False,  # ← fresh current, default anyway
#     )
#     db.add(new_loc)
#     await db.commit()

#     return {
#         "success": True,
#         "message": f"Skid moved to {new_location.loc} successfully.",
#         "previous_location_id": current_loc.location_id,
#         "new_location": new_location.loc,
#     }


# ═════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS — SCAN SPECIFIC
# ═════════════════════════════════════════════════════════════════════

async def _get_mapping(
    db: AsyncSession,
    mapping_id: int,
) -> ExportAwbSkidMapping:

    result = await db.execute(
        select(ExportAwbSkidMapping).where(
            ExportAwbSkidMapping.id == mapping_id
        )
    )
    mapping = result.scalar_one_or_none()
    if not mapping:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Mapping id '{mapping_id}' not found. Please re-lock the skid.",
        )
    return mapping

# 🤮🤢
async def get_skid_mapping_full_info_with_action_status(
    db: AsyncSession,
    mapping_id: int,
) -> dict:
    """
    Shared logic: returns full skid + mapping + allowed_action
    Used by:
    - get by skid_no (get_skid_recent_mapping_info | /get-mapping-by-skid-no)
    - get by sequence (//by-seq)
    """
    # ── get mapping ─────────────────────────────
    mapping = await db.get(ExportAwbSkidMapping, mapping_id)

    if not mapping:
        raise HTTPException(404, "Mapping not found")

    # ── get skid ────────────────────────────────
    skid = await db.get(ExportSkidMaster, mapping.skid_id)

    # ── get awb ─────────────────────────────────
    awb = await db.get(ExportCarMessageAwbMaster, mapping.awb_master_id)

    # ── sequences ───────────────────────────────
    seq_result = await db.execute(
        select(ExportAwbSkidItemSequence)
        .where(ExportAwbSkidItemSequence.mapping_id == mapping.id)
        .order_by(ExportAwbSkidItemSequence.sequence_date_time.asc())
    )
    sequences = seq_result.scalars().all()

    # ── current location ────────────────────────
    loc_result = await db.execute(
        select(ExportSkidLocationMapping, ExportLocationsMaster)
        .join(ExportLocationsMaster,
              ExportLocationsMaster.id == ExportSkidLocationMapping.location_id)
        .where(
            ExportSkidLocationMapping.skid_id == skid.id,
            ExportSkidLocationMapping.is_current == True,
        )
    )
    loc_row = loc_result.first()
    current_location = loc_row.ExportLocationsMaster.loc if loc_row else None

    # ── loaded / remaining ──────────────────────
    loaded = await db.scalar(
        select(func.count(ExportSequenceItemUldLoading.id))
        .where(ExportSequenceItemUldLoading.mapping_id == mapping.id)
    ) or 0

    scanned = len(sequences)
    remaining = scanned - loaded

    # ── base / retrieval ────────────────────────
    last_base = await db.scalar(
        select(ExportSkidBaseMapping.dropped_at)
        .where(ExportSkidBaseMapping.mapping_id == mapping.id)
        .order_by(ExportSkidBaseMapping.dropped_at.desc())
        .limit(1)
    )

    last_retrieval = await db.scalar(
        select(ExportSkidLocationMapping.picked_at)
        .where(
            ExportSkidLocationMapping.skid_id == skid.id,
            ExportSkidLocationMapping.picked_at.isnot(None),
        )
        .order_by(ExportSkidLocationMapping.picked_at.desc())
        .limit(1)
    )

    is_at_base = (
        last_base is not None and
        last_retrieval is not None and
        last_base >= last_retrieval
    )

    # ── allowed_action (same logic) ─────────────
    if mapping.is_skid_used_complete:
        action = "COMPLETE"

    elif current_location is None and last_retrieval is None:
        action = "NEW_ASSIGN"

    elif current_location:
        action = "RELOCATE_OR_RETRIEVE"

    elif remaining > 0 and loaded > 0 and not is_at_base:
        action = "RETURN_TO_LOCATION"

    elif not is_at_base:
        action = "DROP_AT_BASE"

    elif remaining > 0:
        action = "SCAN_INTO_ULD"

    else:
        action = "COMPLETE"

    # ── return ─────────────────────────────────
    return {
        "success": True,
        "message": f"Skid '{skid.skid_no}' fetched successfully",  # ✅ ADD
        "skid": {
            "id": skid.id,
            "skid_no": skid.skid_no,
        "skid_type": skid.skid_type,
           "skid_wgt": skid.skid_wgt, 
        "skid_capacity": skid.skid_capacity,
                     # ✅ ADD
        "is_active": skid.is_active,            # ✅ ADD
        "is_locked": skid.is_locked,            # ✅ ADD
        "is_virtual_used": skid.is_virtual_used, # ✅ ADD
        "locked_by": skid.locked_by_user_id,   # ✅ ADD
         "locked_at": skid.locked_at,           # ✅ ADD

        },
        "mapping": {
            "id": mapping.id,
            "awb_master_id": mapping.awb_master_id,
            "scanned_count": scanned,
            "is_virtual": mapping.is_virtual,       # ✅ ADD
            "virtual_skid_no": mapping.virtual_skid_no,
            "loaded_count": loaded,

            "is_fully_loaded": remaining == 0,

            "remaining_pcs": remaining,
            "current_location": current_location,
            "created_at": mapping.created_at,
            "is_at_base": is_at_base,
            "allowed_action": action,

            "sequences": [
    {
        "id": s.id,
        "sequence_no": s.sequence_no,
        "sequence_date_time": s.sequence_date_time,
        "scan_by_device": s.scan_by_device,
        "scanned_by": s.scanned_by,
    }
    for s in sequences
],
        },

        "awb": {
            "id": awb.id,
            "awb_no": awb.awb_no,
            "pcs": awb.pcs,
        } if awb else None,
    }

async def _assert_skid_still_locked(
    db: AsyncSession,
    skid_id: int,
) -> None:
    """
    Blocks scan if skid lock has expired (>24h stale).
    User must go back and re-lock via validate-and-lock.
    """
    result = await db.execute(
        select(ExportSkidMaster).where(ExportSkidMaster.id == skid_id)
    )
    skid = result.scalar_one_or_none()

    if not skid or not skid.is_locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                "Skid is no longer locked. "
                "Please go back and re-lock the skid before scanning."
            ),
        )

    now_utc = get_utc_now()
    lock_age = now_utc - skid.locked_at

    if lock_age > timedelta(hours=STALE_LOCK_HOURS):
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail=(
                f"Skid lock expired after {STALE_LOCK_HOURS}h of inactivity. "
                "Please go back and re-lock the skid to continue scanning."
            ),
        )


# This is used to unlock the skid
async def _unlock_skid(
    db: AsyncSession,
    skid_id: int,
) -> None:
    """
    Unlocks skid after final save.
    Uses with_for_update() — prevents race condition if two
    requests try to unlock the same skid simultaneously.
    """
    result = await db.execute(
        select(ExportSkidMaster)
        .where(ExportSkidMaster.id == skid_id)
        .with_for_update()
    )
    skid = result.scalar_one_or_none()

    if skid:
        skid.is_locked = False
        skid.locked_at = None
        skid.locked_by_user_id = None
        skid.updated_at = get_utc_now()
        await db.flush()
        await db.commit()



async def _get_sequence_count_by_awb(
    db: AsyncSession,
    awb_master_id: int,
) -> int:
    """
    Total scanned items across ALL skids/mappings for this AWB.
    Used for pcs cap check and response totals.
    """
    result = await db.execute(
        select(func.count(ExportAwbSkidItemSequence.id)).where(
            ExportAwbSkidItemSequence.awb_master_id == awb_master_id
        )
    )
    return result.scalar_one() or 0


async def _get_all_items_for_mapping(
    db: AsyncSession,
    mapping_id: int,
) -> list[ExportAwbSkidItemSequence]:
    """
    Returns all scanned items for this specific skid mapping,
    ordered by scan time ascending (oldest first).
    """
    result = await db.execute(
        select(ExportAwbSkidItemSequence)
        .where(ExportAwbSkidItemSequence.mapping_id == mapping_id)
        .order_by(ExportAwbSkidItemSequence.sequence_date_time.asc())
    )
    return result.scalars().all()





# ═════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS for skid master
# ═════════════════════════════════════════════════════════════════════

# 😎used for getting virtual seq no.
async def _next_virtual_skid_no(db: AsyncSession) -> str:
    """
    Ensures PostgreSQL sequence exists, then fetches next value atomically.

    CREATE SEQUENCE IF NOT EXISTS is a no-op after the first call —
    no migration file needed, no performance concern.

    nextval() is atomic at DB engine level — no two concurrent requests
    ever get the same number even under heavy parallel load.
    Gaps on rollback are possible but uniqueness is always guaranteed.
    """
    try:
        # Create sequence if it does not exist — safe no-op on every
        # subsequent call since IF NOT EXISTS is handled by PostgreSQL
        await db.execute(text(f"""
            CREATE SEQUENCE IF NOT EXISTS {VIRTUAL_SKID_SEQ}
            START WITH 1
            INCREMENT BY 1
            MINVALUE 1
            MAXVALUE 99999999
            NO CYCLE
        """))

        # nextval() — atomic, parallel-safe, guaranteed unique
        result = await db.execute(
            text(f"SELECT nextval('{VIRTUAL_SKID_SEQ}')")
        )
        next_val = result.scalar_one()

        return f"{VIRTUAL_SKID_PREFIX}{str(next_val).zfill(VIRTUAL_SKID_PADDING)}"

    except Exception as e:
        raise Exception(f"Failed to generate virtual skid number: {str(e)}")
    

# async def _next_virtual_skid_no(db: AsyncSession) -> str:
#     """
#     Calls PostgreSQL nextval() on virtual_skid_seq.

#     Atomic at DB engine level — no two concurrent requests ever get
#     the same value even under heavy parallel load.
#     Gaps are possible on rollback but uniqueness is always guaranteed.

#     Migration required (run once):
#         CREATE SEQUENCE virtual_skid_seq START 1 INCREMENT 1 NO CYCLE;
#     """
#     result = await db.execute(text("SELECT nextval('virtual_skid_seq')"))
#     next_val = result.scalar_one()
#     return f"{VIRTUAL_SKID_PREFIX}{str(next_val).zfill(VIRTUAL_SKID_PADDING)}"


async def _get_awb_master(
    db: AsyncSession,
    awb_master_id: int,
) -> ExportCarMessageAwbMaster:

    result = await db.execute(
        select(ExportCarMessageAwbMaster).where(
            ExportCarMessageAwbMaster.id == awb_master_id
        )
    )
    awb = result.scalar_one_or_none()
    if not awb:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"AWB master with id '{awb_master_id}' not found.",
        )
    return awb


# 💀It used ready=d and immidiate update thwen used {it lock it on row upto update completion}
async def _get_active_skid_for_update(
    db: AsyncSession,
    skid_no: str,
) -> ExportSkidMaster:
    """
    Fetches skid with SELECT FOR UPDATE — acquires a row-level DB lock.
    This prevents two concurrent requests from reading the same skid
    state simultaneously and both deciding it is free.
    Lock is held until the transaction commits or rolls back.
    """
    result = await db.execute(
        select(ExportSkidMaster)
        .where(ExportSkidMaster.skid_no == skid_no)
        .with_for_update()
    )
    skid = result.scalar_one_or_none()

    if not skid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skid '{skid_no}' not found. Please check the barcode.",
        )
    if not skid.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Skid '{skid_no}' is inactive/retired and cannot be used.",
        )
    return skid


# This is usefull for read only meand after read not chnage immidiatte
async def _get_active_skid(
    db: AsyncSession,
    skid_no: str,
) -> ExportSkidMaster:

    result = await db.execute(
        select(ExportSkidMaster)
        .where(
            ExportSkidMaster.skid_no == skid_no)
    )
    skid = result.scalar_one_or_none()

    if not skid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skid '{skid_no}' not found. Please check the barcode.",
        )
    if not skid.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Skid '{skid_no}' is inactive/retired and cannot be used.",
        )
    return skid


async def _get_existing_mapping(
    db: AsyncSession,
    awb_master_id: int,
    skid_id: int,
) -> Optional[ExportAwbSkidMapping]:

    result = await db.execute(
        select(ExportAwbSkidMapping).where(
            ExportAwbSkidMapping.awb_master_id == awb_master_id,
            ExportAwbSkidMapping.skid_id == skid_id,
            # 😂
            # ExportAwbSkidMapping.is_skid_used_complete == False,
        )
    )
    return result.scalar_one_or_none()


async def _get_existing_mapping_for_location_mapping(
    db: AsyncSession,
    awb_master_id: int,
    skid_id: int,
) -> Optional[ExportAwbSkidMapping]:

    result = await db.execute(
        select(ExportAwbSkidMapping).where(
            ExportAwbSkidMapping.awb_master_id == awb_master_id,
            ExportAwbSkidMapping.skid_id == skid_id,
            # 😂
            ExportAwbSkidMapping.is_skid_used_complete == False,
        )
    )
    return result.scalar_one_or_none()


async def _get_sequence_count(
    db: AsyncSession,
    mapping_id: int,
) -> int:

    result = await db.execute(
        select(func.count(ExportAwbSkidItemSequence.id)).where(
            ExportAwbSkidItemSequence.mapping_id == mapping_id
        )
    )
    return result.scalar_one() or 0


def _build_response(
    success: bool,
    message: str,
    is_resumed: bool,
    mapping_id: Optional[int],
    awb_master_id: int,
    skid: ExportSkidMaster,
    already_scanned_count: int,
) -> dict:
    return {
        "success": success,
        "message": message,
        "is_resumed": is_resumed,
        "mapping_id": mapping_id,
        "awb_master_id": awb_master_id,
        "skid_id": skid.id,
        "skid_info": {
            "id": skid.id,
            "skid_no": skid.skid_no,
            "skid_type": skid.skid_type,
            "skid_wgt": skid.skid_wgt,
            "skid_capacity": skid.skid_capacity,
        },
        "locked_at": skid.locked_at,
        "already_scanned_count": already_scanned_count,
    }





# ═════════════════════════════════════════════════════════════════════
# PRIVATE HELPERS — LOCATION SKID MAPPING SPECIFIC
# ═════════════════════════════════════════════════════════════════════

async def _get_skid_by_no(
    db: AsyncSession,
    skid_no: str,
) -> ExportSkidMaster:
    result = await db.execute(
        select(ExportSkidMaster).where(
            ExportSkidMaster.skid_no == skid_no
        )
    )
    skid = result.scalar_one_or_none()
    if not skid:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Skid '{skid_no}' not found.",
        )
    return skid


async def _get_active_location(
    db: AsyncSession,
    location_id: int,
) -> ExportLocationsMaster:
    result = await db.execute(
        select(ExportLocationsMaster).where(
            ExportLocationsMaster.id == location_id
        )
    )
    location = result.scalar_one_or_none()
    if not location:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"Location id '{location_id}' not found.",
        )
    if not location.is_active:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Location '{location.loc}' is inactive and cannot be used.",
        )
    return location


async def _get_current_location_mapping(
    db: AsyncSession,
    skid_id: int,
) -> Optional[ExportSkidLocationMapping]:
    """
    Returns the current active location mapping for a skid.
    Only one row should ever have is_current=True per skid.
    """
    result = await db.execute(
        select(ExportSkidLocationMapping).where(
            ExportSkidLocationMapping.skid_id == skid_id,
            ExportSkidLocationMapping.is_current == True,
        )
    )
    return result.scalar_one_or_none()







# ====== create new skid master entry

async def create_new_skid_in_skid_master(
    db: AsyncSession,
    payload: CreateSkidRequest,
    created_by: str,
) -> dict:

    now = get_utc_now()

    # check duplicate skid_no
    existing = await db.execute(
        select(ExportSkidMaster.id).where(
            ExportSkidMaster.skid_no == payload.skid_no
        )
    )
    if existing.scalar_one_or_none():
        raise HTTPException(
            status_code=400,
            detail=f"Skid '{payload.skid_no}' already exists",
        )

    skid = ExportSkidMaster(
        skid_no=payload.skid_no,
        skid_type="real",           # ← fixed — physical only from this form
        is_active=True,
        is_locked=False,
        is_virtual_used=True,       # real skid — always True
        created_at=now,
        updated_at=now,
        created_by=created_by,
    )
    db.add(skid)
    await db.commit()
    await db.refresh(skid)

    return {
        "success": True,
        "message": f"Skid '{skid.skid_no}' created successfully",
        "data": {
            "id": skid.id,
            "skid_no": skid.skid_no,
            "skid_type": skid.skid_type,
            "is_active": skid.is_active,
        },
    }