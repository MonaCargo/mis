



"""
services/uld_stock_service.py    OR   uld_master_service.py
"""

from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.schemas.exportOperation.car_message import UldStockRecord, UldStockSyncResponse, UldSyncResult


# Identifies this automated process as the creator when no user is logged in
SYSTEM_ACTOR = "stock_sync_by_system"


class MultipleCarriersError(ValueError):
    """Raised when a single payload contains records for more than one carrier."""


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

        await self._db.commit()

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