# app/services/importOperation/shipment_hold_service.py
import traceback
from datetime import date
from typing import Optional

from fastapi import HTTPException
from sqlalchemy import select, or_, and_
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.importOperation.import_shipment_hold import ImportShipmentHold
from app.db.models.importOperation.worker_assignment import (
    WorkerAssignmentHeader,
    WorkerAssignmentShipment,
)
from app.utils.common.helperFunction import ist_day_to_utc_range
from app.utils.common.helperFunction import get_utc_now


VALID_HOLD_TYPES = {"AWB_HAWB", "OC", "BOE", "GP"}


# roles allowed to release a hold
RELEASE_HOLD_ROLES = {"super_admin"}



# put this outside the class, top-level in the same file
async def assert_not_on_hold(db, shipment, header):
    held = (await db.execute(
        select(ImportShipmentHold.id).where(
            ImportShipmentHold.is_active == True,
            or_(
                and_(ImportShipmentHold.hold_type == "OC",
                     ImportShipmentHold.oc_no == header.oc_no),
                and_(ImportShipmentHold.hold_type == "AWB_HAWB",
                     ImportShipmentHold.awb_no == header.awb_no,
                     ImportShipmentHold.hawb == (header.hawb or "")),
                and_(ImportShipmentHold.hold_type == "BOE",
                     ImportShipmentHold.boe_no == shipment.boe_no),
                and_(ImportShipmentHold.hold_type == "GP",
                     ImportShipmentHold.gate_pass_no == shipment.gate_pass_no),
            )
        ).limit(1)
    )).first()

    if held:
        raise HTTPException(423, "Shipment is on hold. Operation not allowed.")
    

class ImportShipmentHoldService:
    """Create / release / list shipment holds."""

    def __init__(self, db: AsyncSession):
        self.db = db

 

    # =====================================================
    # Internal: resolve assignment_header_id if shipment exists
    # =====================================================
    async def _resolve_header_id(
        self,
        hold_type: str,
        awb_no: Optional[str],
        hawb: Optional[str],
        oc_no: Optional[str],
        boe_no: Optional[str],
        gate_pass_no: Optional[str],
    ) -> Optional[int]:

        # AWB+HAWB or OC → header-level lookup
        if hold_type == "AWB_HAWB" and awb_no:
            res = await self.db.execute(
                select(WorkerAssignmentHeader.id).where(
                    WorkerAssignmentHeader.awb_no == awb_no,
                    WorkerAssignmentHeader.hawb == (hawb or ""),
                )
            )
            return res.scalar_one_or_none()

        if hold_type == "OC" and oc_no:
            res = await self.db.execute(
                select(WorkerAssignmentHeader.id).where(
                    WorkerAssignmentHeader.oc_no == oc_no
                )
            )
            return res.scalar_one_or_none()

        # GP or BOE → shipment-level lookup, take its header_id
        if hold_type == "GP" and gate_pass_no:
            res = await self.db.execute(
                select(WorkerAssignmentShipment.assignment_header_id).where(
                    WorkerAssignmentShipment.gate_pass_no == gate_pass_no
                )
            )
            return res.scalars().first()

        if hold_type == "BOE" and boe_no:
            res = await self.db.execute(
                select(WorkerAssignmentShipment.assignment_header_id).where(
                    WorkerAssignmentShipment.boe_no == boe_no
                )
            )
            return res.scalars().first()

        return None

    # =====================================================
    # CREATE HOLD
    # =====================================================
    async def create_hold(
        self,
        hold_type: str,
        awb_no: Optional[str],
        hawb: Optional[str],
        oc_no: Optional[str],
        boe_no: Optional[str],
        gate_pass_no: Optional[str],
        reason: Optional[str],
        user_info: dict,
    ) -> ImportShipmentHold:

        role = user_info.get("role")
        # if role not in CREATE_HOLD_ROLES:
        #     raise HTTPException(403, "Not allowed to place a hold")

        # ---- validate hold_type ----
        if hold_type not in VALID_HOLD_TYPES:
            raise HTTPException(
                400, f"hold_type must be one of {sorted(VALID_HOLD_TYPES)}"
            )

        # ---- validate the matching identifier is present ----
        if hold_type == "AWB_HAWB" and not awb_no:
            raise HTTPException(400, "awb_no required for AWB_HAWB hold")
        if hold_type == "OC" and not oc_no:
            raise HTTPException(400, "oc_no required for OC hold")
        if hold_type == "BOE" and not boe_no:
            raise HTTPException(400, "boe_no required for BOE hold")
        if hold_type == "GP" and not gate_pass_no:
            raise HTTPException(400, "gate_pass_no required for GP hold")

        # normalize
        awb_no = awb_no.strip() if awb_no else None
        hawb = hawb.strip() if hawb else None
        oc_no = oc_no.strip() if oc_no else None
        boe_no = boe_no.strip() if boe_no else None
        gate_pass_no = gate_pass_no.strip() if gate_pass_no else None

        try:
            # ---- duplicate active-hold guard (same identity) ----
            dup_filter = None
            if hold_type == "AWB_HAWB":
                dup_filter = and_(
                    ImportShipmentHold.hold_type == "AWB_HAWB",
                    ImportShipmentHold.awb_no == awb_no,
                    ImportShipmentHold.hawb == hawb,
                )
            elif hold_type == "OC":
                dup_filter = and_(
                    ImportShipmentHold.hold_type == "OC",
                    ImportShipmentHold.oc_no == oc_no,
                )
            elif hold_type == "BOE":
                dup_filter = and_(
                    ImportShipmentHold.hold_type == "BOE",
                    ImportShipmentHold.boe_no == boe_no,
                )
            elif hold_type == "GP":
                dup_filter = and_(
                    ImportShipmentHold.hold_type == "GP",
                    ImportShipmentHold.gate_pass_no == gate_pass_no,
                )

            existing = (await self.db.execute(
                select(ImportShipmentHold).where(
                    ImportShipmentHold.is_active == True,
                    dup_filter,
                )
            )).scalars().first()

            if existing:
                raise HTTPException(
                    400, "An active hold already exists for this identifier"
                )

            # ---- best-effort resolve header_id ----
            header_id = await self._resolve_header_id(
                hold_type, awb_no, hawb, oc_no, boe_no, gate_pass_no
            )

            row = ImportShipmentHold(
                hold_type=hold_type,
                awb_no=awb_no,
                hawb=hawb,
                oc_no=oc_no,
                boe_no=boe_no,
                gate_pass_no=gate_pass_no,
                assignment_header_id=header_id,
                is_active=True,
                reason=reason,
                held_by=user_info.get("emp_id"),
                held_datetime=get_utc_now(),
                created_at=get_utc_now(),
                updated_at=get_utc_now(),
            )
            self.db.add(row)
            await self.db.commit()
            await self.db.refresh(row)
            return row

        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            traceback.print_exc()
            raise HTTPException(500, f"Failed to create hold: {str(e)}")

    # =====================================================
    # RELEASE HOLD
    # =====================================================
    async def release_hold(
        self,
        hold_id: int,
        release_reason: Optional[str],
        user_info: dict,
    ) -> ImportShipmentHold:

        # role = user_info.get("role")
        # if role not in RELEASE_HOLD_ROLES:
        #     raise HTTPException(403, "Only super_admin can release a hold")

        try:
            row = (await self.db.execute(
                select(ImportShipmentHold).where(
                    ImportShipmentHold.id == hold_id
                )
            )).scalar_one_or_none()

            if not row:
                raise HTTPException(404, "Hold not found")

            if not row.is_active:
                raise HTTPException(400, "Hold is already released")

            row.is_active = False
            row.released_by = user_info.get("emp_id")
            row.released_datetime = get_utc_now()
            row.release_reason = release_reason
            row.updated_at = get_utc_now()
            self.db.add(row)

            await self.db.commit()
            await self.db.refresh(row)
            return row

        except HTTPException:
            await self.db.rollback()
            raise
        except Exception as e:
            await self.db.rollback()
            traceback.print_exc()
            raise HTTPException(500, f"Failed to release hold: {str(e)}")

    # =====================================================
    # LIST HOLDS  (query_type: hold / released / all)
    # =====================================================
    async def list_holds(
        self,
        query_type: str = "hold",
        start_date: Optional[date] = None,
        end_date: Optional[date] = None,
    ) -> list[ImportShipmentHold]:

        stmt = select(ImportShipmentHold)

        # active / released filter
        if query_type == "hold":
            stmt = stmt.where(ImportShipmentHold.is_active == True)
        elif query_type == "released":
            stmt = stmt.where(ImportShipmentHold.is_active == False)
        elif query_type == "all":
            pass
        else:
            raise HTTPException(
                400, "query_type must be 'hold', 'released', or 'all'"
            )

        # optional IST date range on held_datetime
        if start_date and end_date:
            utc_start, _ = ist_day_to_utc_range(start_date)
            _, utc_end = ist_day_to_utc_range(end_date)
            stmt = stmt.where(
                ImportShipmentHold.held_datetime >= utc_start,
                ImportShipmentHold.held_datetime < utc_end,
            )

        stmt = stmt.order_by(ImportShipmentHold.held_datetime.desc())

        rows = (await self.db.execute(stmt)).scalars().all()
        return rows