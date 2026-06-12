
import traceback
from typing import Optional
from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.importOperation.worker_assignment import ImportLocationPickup
from app.db.models.importOperation.worker_assignment import (
    WorkerAssignmentHeader,
    WorkerAssignmentShipment,
)
from app.utils.common.helperFunction import get_utc_now



class ImportLocationPickupService:
    """Async service for per-location pickup flag operations."""

    def __init__(self, db: AsyncSession):
        self.db = db

    # =====================================================
    # Internal: fetch shipment + header, validate oc_no
    # =====================================================
    async def _get_shipment_and_header(
        self,
        assignment_shipment_id: int,
        oc_no: Optional[str] = None,
    ):
        # Fetch shipment
        shipment_result = await self.db.execute(
            select(WorkerAssignmentShipment).where(
                WorkerAssignmentShipment.id == assignment_shipment_id
            )
        )
        shipment = shipment_result.scalar_one_or_none()
        if not shipment:
            raise HTTPException(400, "Invalid assignment_shipment_id")

        # Fetch header manually (no relationship)
        header_result = await self.db.execute(
            select(WorkerAssignmentHeader).where(
                WorkerAssignmentHeader.id == shipment.assignment_header_id
            )
        )
        header = header_result.scalar_one_or_none()
        if not header:
            raise HTTPException(400, "Shipment header missing")

        # Validate oc_no against header (don't trust client) — only when provided
        if oc_no is not None and oc_no != header.oc_no:
            raise HTTPException(
                status_code=400,
                detail="OC number does not match shipment header",
            )

        return shipment, header

    # =====================================================
    # PICK  (imp_tracer / imp_gp_user)
    # =====================================================
    async def pick_location(
        self,
        assignment_shipment_id: int,
        oc_no: str,
        location: str,
        user_info: dict,
    ) -> ImportLocationPickup:

        role = user_info.get("role")

        emp_id = user_info.get("emp_id")
        device_id = user_info.get("device_id")

        shipment, header = await self._get_shipment_and_header(
            assignment_shipment_id, oc_no
        )

        try:
            # Look for an existing row for this (shipment, location)
            existing_result = await self.db.execute(
                select(ImportLocationPickup).where(
                    ImportLocationPickup.assignment_shipment_id
                    == assignment_shipment_id,
                    ImportLocationPickup.location == location,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing is None:
                # First pick → insert
                row = ImportLocationPickup(
                    assignment_shipment_id=assignment_shipment_id,
                    assignment_header_id=shipment.assignment_header_id,
                    location=location,
                    is_picked=True,
                    picked_by=emp_id,
                    picked_datetime=get_utc_now(),
                    device_id=device_id,
                    created_at=get_utc_now(),
                    updated_at=get_utc_now(),
                )
                self.db.add(row)

            elif existing.is_picked:
                # Already picked → idempotent success, no change
                return existing

            else:
                # Was unpicked by admin → re-pick: flip back, refresh picker,
                # clear unpick history
                existing.is_picked = True
                existing.picked_by = emp_id
                existing.picked_datetime = get_utc_now()
                existing.device_id = device_id
                existing.unpicked_by = None
                existing.unpicked_datetime = None
                existing.updated_at = get_utc_now()
                self.db.add(existing)
                row = existing

            await self.db.commit()
            await self.db.refresh(row)
            return row

        except HTTPException:
            raise
        except Exception as e:
            await self.db.rollback()
            traceback.print_exc()
            raise HTTPException(500, f"Failed to pick location: {str(e)}")

    # =====================================================
    # UNPICK  (super_admin only)
    # =====================================================
    async def unpick_location(
        self,
        assignment_shipment_id: int,
        location: str,
        user_info: dict,
    ) -> ImportLocationPickup:


        emp_id = user_info.get("emp_id")

        try:
            existing_result = await self.db.execute(
                select(ImportLocationPickup).where(
                    ImportLocationPickup.assignment_shipment_id
                    == assignment_shipment_id,
                    ImportLocationPickup.location == location,
                )
            )
            existing = existing_result.scalar_one_or_none()

            if existing is None:
                raise HTTPException(404, "No pickup record for this location")

            if not existing.is_picked:
                raise HTTPException(400, "Location is already unpicked")

            # Flip to unpicked, record admin + time.
            # Keep picked_by / picked_datetime intact as history.
            existing.is_picked = False
            existing.unpicked_by = emp_id
            existing.unpicked_datetime = get_utc_now()
            existing.updated_at = get_utc_now()
            self.db.add(existing)

            await self.db.commit()
            await self.db.refresh(existing)
            return existing

        except HTTPException:
            raise
        except Exception as e:
            await self.db.rollback()
            traceback.print_exc()
            raise HTTPException(500, f"Failed to unpick location: {str(e)}")