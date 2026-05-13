



"""
services/uld_stock_service.py    OR   uld_master_service.py
"""

from datetime import datetime, timezone
from itertools import islice
from operator import and_
from typing import Optional

from fastapi import HTTPException, status
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from app.db.models.exportOperation.export_carrier_master import ExportCarrierMaster
from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.schemas.exportOperation.car_message import UldInventoryRecord, UldStockRecord, UldStockSyncResponse, UldSyncResult
from app.schemas.exportOperation.uld_master import ExportUldCreate
from app.services.exportOperation.uld_master_log_service import UldAction, uld_snapshot, write_uld_log
from app.services.export_slot_file_upload_service import get_utc_now
from app.utils.exportOperation.validator.uld_pattern_validator import validate_uld_no


# Identifies this automated process as the creator when no user is logged in
SYSTEM_ACTOR = "stock_sync_by_system"
FETCH_CHUNK_SIZE = 500

class MultipleCarriersError(ValueError):
    """Raised when a single payload contains records for more than one carrier."""

def _chunked(iterable, size: int):
    it = iter(iterable)
    while chunk := list(islice(it, size)):
        yield chunk

class UldStockSyncService:

    def __init__(self, db: AsyncSession) -> None:
        self._db = db

    async def sync(
        self,
        records: list[UldStockRecord],
        synced_by: Optional[str] = None,          # pass current_user.username when auth is ready
    ) -> UldStockSyncResponse:
        carrier = self._assert_single_carrier(records)

        actor = synced_by or SYSTEM_ACTOR         # fallback to system label if no user

        results: list[UldSyncResult] = []
        created = 0
        updated = 0

        for record in records:
            action = await self._upsert_uld(record, actor=actor)
            results.append(UldSyncResult(uld_number=record.ULD_NUMBER, action=action))
            if action == "created":
                created += 1
            else:
                updated += 1

        # await self._db.commit()
        await self._db.flush()  # ✅ changed from commit() — route owns the commit

        return UldStockSyncResponse(
            carrier=carrier,
            total_received=len(records),
            total_created=created,
            total_updated=updated,
            results=results,
        )

    @staticmethod
    def _assert_single_carrier(records: list[UldStockRecord]) -> str:
        carriers = {r.CARRIER for r in records if r.CARRIER}
        if len(carriers) > 1:
            raise MultipleCarriersError(
                f"Payload contains records for multiple carriers: "
                f"{', '.join(sorted(carriers))}. "
                "Each sync request must be for a single carrier."
            )
        if not carriers:
            raise ValueError("No valid carrier code found in the payload.")
        return carriers.pop()

    async def _upsert_uld(
        self,
        record: UldStockRecord,
        actor: str,
    ) -> str:
        now = datetime.now(tz=timezone.utc)

        result = await self._db.execute(
            select(ExportUldMaster).where(
                ExportUldMaster.uld_no == record.ULD_NUMBER
            )
        )
        existing: Optional[ExportUldMaster] = result.scalar_one_or_none()

        if existing:
            # Only update fields that the PDF owns — never touch created_at / created_by
            existing.uld_type    = record.ULD_TYPE      # type can change between PDFs
            existing.is_available = True
            existing.updated_at  = now
            existing.updated_by  = actor
            return "updated"

        self._db.add(ExportUldMaster(
            uld_no      = record.ULD_NUMBER,
            uld_type    = record.ULD_TYPE,
            carrier     = record.CARRIER,
            is_active   = True,
            is_available= True,
            created_at  = now,          # set once, never touched again
            created_by  = actor,        # "uld_stock_sync" or a real username
            updated_at  = now,
            updated_by  = actor,
        ))
        return "created"
    

    # ── new: all-carrier CSV/Excel inventory sync ─────────────────────────────
 
    async def sync_all_carrier_inventory_file(
        self,
        records: list[UldInventoryRecord],
        synced_by: Optional[str] = None,
    ) -> UldStockSyncResponse:
        """
        Handles all-carrier CSV/Excel inventory file.
        Multiple carriers in one file is expected and valid.
        Fetches existing ULDs in chunks of 500 to avoid oversized IN clauses.
        Existing ULD → is_available = True + refresh fields.
        New ULD      → INSERT with is_available = True.
        """
        actor       = synced_by or SYSTEM_ACTOR
        now         = datetime.now(tz=timezone.utc)
        uld_numbers = [r.uld_number for r in records]
 
        # ── chunked fetch ─────────────────────────────────────────────────────
        existing: dict[str, ExportUldMaster] = {}
        for chunk in _chunked(uld_numbers, FETCH_CHUNK_SIZE):
            result = await self._db.execute(
                select(ExportUldMaster).where(ExportUldMaster.uld_no.in_(chunk))
            )
            existing.update({row.uld_no: row for row in result.scalars().all()})
 
        # ── single-pass upsert ────────────────────────────────────────────────
        created = updated = 0
 
        for rec in records:
            if rec.uld_number in existing:
                obj              = existing[rec.uld_number]
                obj.is_available = True
                obj.carrier      = rec.carrier_code
                obj.updated_at   = now
                obj.updated_by   = actor
                updated += 1
            else:
                self._db.add(ExportUldMaster(
                    uld_no       = rec.uld_number,
                    carrier      = rec.carrier_code,
                    is_active    = True,
                    is_available = True,
                    created_at   = now,
                    created_by   = actor,
                    updated_at   = now,
                    updated_by   = actor,
                ))
                created += 1
 
        await self._db.flush()
 
        return UldStockSyncResponse(
            carrier        = "MULTI",
            total_received = len(records),
            total_created  = created,
            total_updated  = updated,
            results        = [],
        )
 







    # =============== 🤮🫥SERVICE FOR ULD TO SHOW IN TABLE =====================================
    @staticmethod
    async def get_filtered_uld_master(      # ✅ inside class, correct indent
        db: AsyncSession,
        carrier: Optional[str],
        is_available: Optional[bool],
        is_active: Optional[bool],
        page: int,
        page_size: int,
    ) -> tuple[list[ExportUldMaster], int]:

        query       = select(ExportUldMaster)
        count_query = select(func.count()).select_from(ExportUldMaster)

        conditions = []

        if carrier and carrier != "all":
            conditions.append(ExportUldMaster.carrier == carrier.upper())

        if is_available is not None:
            conditions.append(ExportUldMaster.is_available == is_available)

        if is_active is not None:
            conditions.append(ExportUldMaster.is_active == is_active)

        # NEW CODE (Fixed)
        if conditions:
            query       = query.where(*conditions)
            count_query = count_query.where(*conditions)

        total_result = await db.execute(count_query)
        total        = total_result.scalar() or 0

        offset = (page - 1) * page_size
        query  = query.order_by(ExportUldMaster.updated_at.desc()).offset(offset).limit(page_size)

        result  = await db.execute(query)
        records = result.scalars().all()

        return list(records), total

    @staticmethod
    async def get_distinct_carriers(db: AsyncSession) -> list[str]:  # ✅ inside class
        result = await db.execute(
            select(ExportUldMaster.carrier).distinct().order_by(ExportUldMaster.carrier)
        )
        return [row[0] for row in result.fetchall() if row[0]]
    



    # =========================😎😎😎😎 New create ULD with defined pattern ==================================

    # ─────────────────────────────────────────────────────────────────────────────
    # Internal helpers
    # ─────────────────────────────────────────────────────────────────────────────
    async def _get_uld_by_id(db: AsyncSession, uld_id: int) -> ExportUldMaster:
        """Fetch a ULD row by id or raise 404."""
        result = await db.execute(
            select(ExportUldMaster).where(ExportUldMaster.id == uld_id)
        )
        row = result.scalar_one_or_none()
        if not row:
            raise HTTPException(
                status_code=status.HTTP_404_NOT_FOUND,
                detail=f"ULD with id '{uld_id}' not found.",
            )
        return row
    
    @staticmethod
    async def _get_uld_by_no(db: AsyncSession, uld_no: str) -> Optional[ExportUldMaster]:
        """Fetch a ULD row by uld_no (case-insensitive normalised)."""
        result = await db.execute(
            select(ExportUldMaster).where(
                ExportUldMaster.uld_no == uld_no.strip().upper()
            )
        )
        return result.scalar_one_or_none()
    
    
    # ----------------

    @staticmethod
    # ─────────────────────────────────────────────────────────────────────────────
    # CREATE
    # ─────────────────────────────────────────────────────────────────────────────
    async def create_export_uld_or_container_based_on_defined_patterns(
        db: AsyncSession,
        payload: ExportUldCreate,
        actor: Optional[str] = None,
    ) -> dict:
        """
        Create a new Export ULD record.
    
        Validates the uld_no against the allowed patterns, auto-derives uld_type
        from the matched pattern, and ensures uniqueness.
    
        Returns the created ULD details.
        """
        # ── Re-validate uld_no (defence-in-depth, even though schema validated) ──
        result = validate_uld_no(payload.uld_no)
        if not result.is_valid:
            raise HTTPException(
                status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
                detail={
                    "message": result.reason,
                    "suggestions": result.suggestions,
                },
            )
    
        derived_type = result.uld_type  # guaranteed non-None when is_valid
    
        # ── If client supplied uld_type, verify it matches the pattern ──────────
        if payload.uld_type and payload.uld_type.strip().upper() != derived_type:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=(
                    f"Supplied uld_type '{payload.uld_type}' does not match "
                    f"the pattern-derived type '{derived_type}'."
                ),
            )
        
        # ── Carrier must exist and be active in export_carrier_master ──────────
        carrier_result = await db.execute(
            select(ExportCarrierMaster.id).where(
                ExportCarrierMaster.carrier_code == payload.carrier,
                ExportCarrierMaster.is_active.is_(True),
            )
        )
        print(carrier_result,"carrier-result")
        if carrier_result.scalar_one_or_none() is None:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Carrier '{payload.carrier}' is not registered or inactive.",
            )
    
        # ── Uniqueness pre-check (DB unique index is still source of truth) ─────
        existing = await UldStockSyncService._get_uld_by_no(db, payload.uld_no)
        if existing:
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"ULD '{payload.uld_no}' already exists.",
            )
    
        # ── Build & insert ──────────────────────────────────────────────────────
        now = get_utc_now()
        row = ExportUldMaster(
            uld_no=payload.uld_no,
            carrier=payload.carrier,
            uld_type=derived_type,
            is_active=True,
            is_available=True,
            created_at=now,
            updated_at=now,
            created_by=actor,
            updated_by=actor,
        )
    
        try:
            db.add(row)

            await db.flush()  # populates row.id without committing
 
            # ── Audit log lives in the SAME transaction ─────────────────────────
            await write_uld_log(
                db,
                action=UldAction.CREATE,
                uld_id=row.id,
                uld_no=row.uld_no,
                message=(
                    f"ULD '{row.uld_no}' created with type '{row.uld_type}' "
                    f"for carrier '{row.carrier}'."
                ),
                before_state=None,
                after_state=uld_snapshot(row),
                performed_by=actor,
                remarks=payload.remarks,
            )

            await db.commit()
            await db.refresh(row)
        except IntegrityError:
            await db.rollback()
            raise HTTPException(
                status_code=status.HTTP_409_CONFLICT,
                detail=f"ULD '{payload.uld_no}' already exists.",
            )
    
        return {
            "success": True,
            "message": f"ULD '{row.uld_no}' created successfully.",
            "item": {
                "id": row.id,
                "uld_no": row.uld_no,
                "carrier": row.carrier,
                "uld_type": row.uld_type,
                "is_active": row.is_active,
                "is_available": row.is_available,
                "created_at": row.created_at,
                "updated_at": row.updated_at,
                "created_by": row.created_by,
                "updated_by": row.updated_by,
            },
        }
    
    