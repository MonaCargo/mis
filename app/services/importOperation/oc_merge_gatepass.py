from datetime import datetime
from typing import List
from zoneinfo import ZoneInfo
from fastapi import HTTPException
from sqlalchemy import and_, select, update
from app.db.models.importOperation.oc_report import OcReport
from app.db.models.importOperation.oc_merge_gatepass import OcMergeGatePass
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.user import User
from app.schemas.user import UserRead
from app.utils.common.helperFunction import get_utc_now

class OcMergeGatepassService:

    @staticmethod
    async def test_save_from_oc_report(db: AsyncSession) -> dict:
        try:
            # Step 1: Query required fields
            stmt = select(
                OcReport.awb_no,
                OcReport.hawb_no,
                OcReport.pcs,
                OcReport.oc_no
            ).limit(200)  # Limit for testing

            result = await db.execute(stmt)
            rows = result.all()

            if not rows:
                return {"success": False, "message": "No records found", "saved": 0}

            # Step 2–3: Map to OcMergeGatePass with dummy IGP number
            gatepass_records = []
            for i, row in enumerate(rows, start=1):
                gatepass = OcMergeGatePass(
                    igp_no=f"IGP-TEST-{str(i).zfill(4)}",
                    awb_no=row.awb_no,
                    hawb=row.hawb_no,
                    no_of_pc=row.pcs,
                    oc_no=row.oc_no
                )
                gatepass_records.append(gatepass)

            # Step 4: Bulk insert
            db.add_all(gatepass_records)
            await db.commit()

            # Step 5: Return response
            return {
                "success": True,
                "message": f"Saved {len(gatepass_records)} test records to oc_merge_gatepass",
                "saved": len(gatepass_records)
            }

        except Exception as e:
            await db.rollback()
            return {"success": False, "message": str(e), "saved": 0}

    @staticmethod
    async def get_gatepass_by_date_range(
        db: AsyncSession,
        start_date: datetime,
        end_date: datetime
    ) -> List[OcMergeGatePass]:
        """
        Get all OcMergeGatePass records within a date range
        """
        try:
            # Build query with date range filter
            query = (
                select(OcMergeGatePass)
                .where(
                    and_(
                        OcMergeGatePass.integrate_date_time >= start_date,
                        OcMergeGatePass.integrate_date_time <= end_date
                    ),
          # ❌ EXCLUDE rows where all three fields are NULL
            ~(
                (OcMergeGatePass.weight_in_kgs.is_(None)) &
                (OcMergeGatePass.chg_wgt_in_kg.is_(None)) &
                (OcMergeGatePass.location.is_(None))
            )
                )
                .order_by(OcMergeGatePass.igp_print_date_time.desc())
            )
            
            # Execute query
            result = await db.execute(query)
            gatepass_records = result.scalars().all()
            
            return gatepass_records
            
        except Exception as e:
            # Log the error and re-raise
            print(f"Error fetching gatepass records: {str(e)}")
            raise
# ---------------------------------------------------------------------------------------

    # @staticmethod
    # async def update_igp_print_status_and_datetime(db: AsyncSession, oc_numbers: list[str]) -> int:
    #     # ✅ Current IST time
    #     ist_now = datetime.now(ZoneInfo("Asia/Kolkata"))

    #     # ✅ Convert to UTC but keep tzinfo (timezone-aware)
    #     utc_now = ist_now.astimezone(ZoneInfo("UTC"))

    #     # ✅ Bulk update
    #     stmt = (
    #         update(OcMergeGatePass)
    #         .where(OcMergeGatePass.oc_no.in_(oc_numbers))
    #         .values(
    #             igp_print_date_time=utc_now,  # keep timezone-aware
    #             is_printed=True
    #         )
    #     )
    #     result = await db.execute(stmt)
    #     await db.commit()

    #     return result.rowcount
# ----------------------------------------------------------------------------------------------
    @staticmethod
    async def update_igp_print_status_and_datetime(db: AsyncSession, oc_numbers: list[str]) -> list[dict]:
        # ✅ Current IST time
        ist_now = datetime.now(ZoneInfo("Asia/Kolkata"))

        # ✅ Convert to UTC but keep tzinfo (timezone-aware)
        utc_now = ist_now.astimezone(ZoneInfo("UTC"))

        # ✅ Bulk update
        stmt = (
            update(OcMergeGatePass)
            .where(OcMergeGatePass.oc_no.in_(oc_numbers))
            .values(
                igp_print_date_time=utc_now,  # keep timezone-aware
                is_printed=True,
                updated_at=get_utc_now()  # ✅ Update the updated_at timestamp
            )
            .returning(
                OcMergeGatePass.id,
                OcMergeGatePass.oc_no,
                OcMergeGatePass.igp_no,
                OcMergeGatePass.awb_no,
                OcMergeGatePass.hawb,
                OcMergeGatePass.no_of_pc,
                OcMergeGatePass.weight_in_kgs,
                OcMergeGatePass.location,
                OcMergeGatePass.flight_no,
                OcMergeGatePass.flight_date,
                OcMergeGatePass.irregularity_remarks,
                OcMergeGatePass.pd_in_time,
                OcMergeGatePass.no_of_pc_recd,
                OcMergeGatePass.verified_by,
                OcMergeGatePass.agent_name,
                OcMergeGatePass.customer_name,
                OcMergeGatePass.release_zone,
                OcMergeGatePass.integrate_date_time,
                OcMergeGatePass.shc,
                OcMergeGatePass.igp_print_date_time,
                OcMergeGatePass.irr_codes,
                OcMergeGatePass.is_printed
            )
        )
        result = await db.execute(stmt)
        await db.commit()

        # ✅ Convert result to list of dicts
        updated_rows = [dict(row._mapping) for row in result.fetchall()]
        # sort by igp_no
        # updated_rows.sort(key=lambda x: x["igp_no"])

        return updated_rows



# ======================= Generic search for oc merge --------
    @staticmethod
    async def search_in_oc_merge_data_generic(
        db: AsyncSession,
        awb_no: str = None,
        hawb: str = None,
        oc_no: str = None,
        temp_irm_oc_no: str = None,
    ):
        # -----------------------------
        # Choose filter condition
        # -----------------------------
        if awb_no:
            filter_condition = OcMergeGatePass.awb_no == awb_no

        elif hawb:
            filter_condition = OcMergeGatePass.hawb == hawb

        elif oc_no:
            filter_condition = OcMergeGatePass.oc_no == oc_no

        elif temp_irm_oc_no:
            filter_condition = OcMergeGatePass.temp_irm_oc_no == temp_irm_oc_no

        else:
            raise HTTPException(400, "At least one search parameter required")

        # -----------------------------
        # SELECT all matching rows
        # -----------------------------
        stmt = select(OcMergeGatePass).where(filter_condition)
        result = await db.execute(stmt)
        records = result.scalars().all()   # ⭐ returns list, not just one

        if not records:
            return []   # return empty list (safe for your response_model)

        # -----------------------------
        # Attach user info for each record
        # -----------------------------
        for rec in records:
            if rec.uploaded_by:
                user_stmt = select(User).where(User.emp_id == rec.uploaded_by)
                user_res = await db.execute(user_stmt)
                user = user_res.scalars().first()

                rec.user_info = UserRead.model_validate(user) if user else None
            else:
                rec.user_info = None

        return records