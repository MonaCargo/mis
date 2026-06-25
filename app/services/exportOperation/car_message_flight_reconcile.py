# services/exportOperation/reconcile_departed_flight_bookings.py
"""
Reconcile booked_pcs against actually-loaded pcs for DEPARTED flights.

Why: an AWB can be booked for N pcs on a flight but only M (< N) actually
get loaded onto a ULD before the flight departs. The unloaded (N - M) pcs
stay locked to that departed flight and can never be booked elsewhere.
This job, run periodically, frees them.

Per departed flight whose flight_date is in [date_from, date_to]:

  - If ANY AWB on the flight loaded > 0  (mixed / all-loaded):
        * loaded>0, booked>loaded -> cap booked_pcs = loaded   [log per AWB]
        * loaded>0, booked<=loaded -> skip (no change, no log)
        * loaded==0 -> delete the detail row (detach)           [log per AWB]
        * header stays active.

  - If EVERY AWB on the flight loaded == 0 (all-zero):
        * header.is_active = False (deactivate, do NOT hard-delete the flight)
        * delete all booking detail rows
        * release the flight's ULDs (is_available=True) and HARD-DELETE the
          ULD assignment (cascade removes its detail rows)
        * ONE flight-level log listing freed AWBs + released ULDs.

Safety:
  - Only DEPARTED flights (flight_dpt_datetime <= now) are touched; no user
    can load/edit/assign on a departed flight, so there is no race with live
    API traffic.
  - Commits PER FLIGHT — a failing flight rolls back alone; others continue.
  - Idempotent — a re-run finds capped rows already equal, detached rows
    gone, and deactivated flights excluded by the is_active filter.
  - with_for_update() on the per-flight header/detail fetch serialises two
    overlapping reconciliation runs against the same flight.
"""

from datetime import date, datetime, timedelta, timezone
from sqlalchemy import text
from sqlalchemy import select, func, delete, update
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import async_session   # 🔧 your real path to this file
from app.db.models.exportOperation.car_message import (
    ExportCarMessageAwbMaster,
    ExportFlightBookingHeader,
    ExportFlightBookingDetail,
    ExportAwbSkidItemSequence,
    ExportSequenceItemUldLoading,
    ExportUldAssignment,
    ExportUldAssignmentDetail, 
)
from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.utils.common.helperFunction import get_utc_now
from .car_message_flow_audit_log import write_car_message_flow_audit
from app.utils.common.car_message_flow_audit_utils import CarMessageFlowModule, CarMessageFlowStep
import logging
from zoneinfo import ZoneInfo


SYSTEM_ACTOR = "SYSTEM_RECONCILE"


# ══════════════════════════════════════════════════════════════════════════
# CORE SERVICE — takes a session, does the work, commits per flight.
# ══════════════════════════════════════════════════════════════════════════
async def reconcile_departed_flight_bookings(
    db: AsyncSession,
    date_from: date,
    date_to: date,
) -> dict:
    now = get_utc_now()

    summary = {
        "date_from": str(date_from),
        "date_to": str(date_to),
        "flights_examined": 0,
        "flights_mixed_reconciled": 0,
        "flights_deactivated_all_zero": 0,
        "details_capped": 0,
        "details_detached": 0,
        "flights_failed": 0,
        "errors": [],
    }

    # candidate flights: in range + active + departed
    candidates = await db.execute(
        select(ExportFlightBookingHeader.id)
        .where(
            ExportFlightBookingHeader.flight_date >= date_from,
            ExportFlightBookingHeader.flight_date <= date_to,
            ExportFlightBookingHeader.is_active == True,
            ExportFlightBookingHeader.flight_dpt_datetime <= now,  # departed only
        )
        .order_by(ExportFlightBookingHeader.id)
    )
    header_ids = [row.id for row in candidates.all()]
    summary["flights_examined"] = len(header_ids)

    for header_id in header_ids:
        try:
            result = await _reconcile_one_flight(db, header_id)
            if result["outcome"] == "DEACTIVATED":
                summary["flights_deactivated_all_zero"] += 1
            elif result["capped"] or result["detached"]:
                summary["flights_mixed_reconciled"] += 1
                summary["details_capped"] += result["capped"]
                summary["details_detached"] += result["detached"]
            await db.commit()
        except Exception as e:
            await db.rollback()
            summary["flights_failed"] += 1
            summary["errors"].append(f"flight_header_id={header_id}: {e}")
            continue

    return summary


async def _reconcile_one_flight(db: AsyncSession, header_id: int) -> dict:
    """Reconcile one flight. Does NOT commit — caller commits."""

    now = get_utc_now()

    # lock header — re-check still active + departed
    header = (
        await db.execute(
            select(ExportFlightBookingHeader)
            .where(ExportFlightBookingHeader.id == header_id)
            .with_for_update()
        )
    ).scalar_one_or_none()

    if not header or not header.is_active:
        return {"outcome": "SKIPPED", "capped": 0, "detached": 0}

    # lock detail rows
    details = (
        await db.execute(
            select(ExportFlightBookingDetail)
            .where(ExportFlightBookingDetail.flight_header_id == header_id)
            .with_for_update()
        )
    ).scalars().all()

    if not details:
        return {"outcome": "SKIPPED", "capped": 0, "detached": 0}

    awb_ids = [d.awb_master_id for d in details]

    # awb_no map for readable logs
    awb_no_result = await db.execute(
        select(ExportCarMessageAwbMaster.id, ExportCarMessageAwbMaster.awb_no)
        .where(ExportCarMessageAwbMaster.id.in_(awb_ids))
    )
    awb_no_map = {row.id: row.awb_no for row in awb_no_result.all()}

    # loaded_pcs per AWB on THIS flight (sequence-join, this flight only)
    loaded_result = await db.execute(
        select(
            ExportAwbSkidItemSequence.awb_master_id,
            func.count(ExportSequenceItemUldLoading.id).label("loaded_pcs"),
        )
        .join(
            ExportSequenceItemUldLoading,
            ExportSequenceItemUldLoading.sequence_id == ExportAwbSkidItemSequence.id,
        )
        .where(
            ExportSequenceItemUldLoading.flight_header_id == header_id,
            ExportAwbSkidItemSequence.awb_master_id.in_(awb_ids),
        )
        .group_by(ExportAwbSkidItemSequence.awb_master_id)
    )
    loaded_by_awb = {
        row.awb_master_id: row.loaded_pcs
        for row in loaded_result.mappings().all()
    }
    total_loaded = sum(loaded_by_awb.values())

    # ── CASE A: all-zero -> deactivate flight ────────────────────────────
    if total_loaded == 0:
        await _deactivate_all_zero_flight(db, header, details, awb_no_map, now)
        return {"outcome": "DEACTIVATED", "capped": 0, "detached": 0}

    # ── CASE B: mixed -> cap + detach, per-AWB logs ──────────────────────
    capped = 0
    detached = 0
    for d in details:
        loaded = loaded_by_awb.get(d.awb_master_id, 0)
        awb_no = awb_no_map.get(d.awb_master_id, "UNKNOWN")

        if loaded == 0:
            # snapshot BEFORE delete
            old_pcs = d.booked_pcs
            detail_id = d.id
            awb_master_id = d.awb_master_id
            await db.delete(d)
            await write_car_message_flow_audit(
                db=db,
                awb_reference_id=awb_master_id,
                flight_reference_id=header_id,
                module=CarMessageFlowModule.RECONCILIATION,
                flow_step=CarMessageFlowStep.RECONCILIATION,
                record_id=detail_id,
                action="UPDATE",
                performed_by=SYSTEM_ACTOR,
                changes={
                    "event": "BOOKING_RECONCILED",
                    "reason": "ZERO_LOADED_DETACHED",
                    "flight_no": header.flight_no,
                    "flight_date": str(header.flight_date),
                    "awb_no": awb_no,
                    "booked_pcs_before": old_pcs,
                    "booked_pcs_after": 0,
                    "loaded_pcs": 0,
                    "freed_pcs": old_pcs,
                },
            )
            detached += 1

        elif d.booked_pcs > loaded:
            old_pcs = d.booked_pcs
            d.booked_pcs = loaded
            await write_car_message_flow_audit(
                db=db,
                awb_reference_id=d.awb_master_id,
                flight_reference_id=header_id,
                module=CarMessageFlowModule.RECONCILIATION,
                flow_step=CarMessageFlowStep.RECONCILIATION,
                record_id=d.id,
                action="UPDATE",
                performed_by=SYSTEM_ACTOR,
                changes={
                    "event": "BOOKING_RECONCILED",
                    "reason": "CAPPED_TO_LOADED",
                    "flight_no": header.flight_no,
                    "flight_date": str(header.flight_date),
                    "awb_no": awb_no,
                    "booked_pcs_before": old_pcs,
                    "booked_pcs_after": loaded,
                    "loaded_pcs": loaded,
                    "freed_pcs": old_pcs - loaded,
                },
            )
            capped += 1
        # else booked_pcs <= loaded -> no change, no log

    return {"outcome": "MIXED", "capped": capped, "detached": detached}


async def _deactivate_all_zero_flight(
    db: AsyncSession,
    header: ExportFlightBookingHeader,
    details: list,
    awb_no_map: dict,
    now,
):
    """
    All AWBs loaded 0 on a departed flight:
      - snapshot freed AWBs for the log,
      - release ULDs (is_available=True) + HARD-DELETE the ULD assignment,
      - deactivate header, delete all detail rows,
      - ONE flight-level log (freed AWBs + released ULDs).
    Does NOT commit — caller commits.
    """
    header_id = header.id

    # snapshot freed AWBs BEFORE deleting details
    freed_awbs = [
        {
            "awb_master_id": d.awb_master_id,
            "awb_no": awb_no_map.get(d.awb_master_id, "UNKNOWN"),
            "freed_pcs": d.booked_pcs,
        }
        for d in details
    ]
    total_freed_pcs = sum(d.booked_pcs for d in details)

    # ── ULD assignment: capture info, release ULDs, then HARD-DELETE ──────
    released_ulds = []
    assignment = (
        await db.execute(
            select(ExportUldAssignment).where(
                ExportUldAssignment.flight_header_id == header_id,
                ExportUldAssignment.is_active == True,
            )
        )
    ).scalar_one_or_none()

    if assignment:
        uld_info_result = await db.execute(
            select(
                ExportUldAssignmentDetail.uld_id,
                ExportUldMaster.uld_no,
                ExportUldMaster.carrier,
            )
            .join(ExportUldMaster, ExportUldAssignmentDetail.uld_id == ExportUldMaster.id)
            .where(ExportUldAssignmentDetail.assignment_id == assignment.id)
        )
        uld_rows = uld_info_result.mappings().all()
        uld_ids = [r.uld_id for r in uld_rows]
        released_ulds = [
            {"uld_id": r.uld_id, "uld_no": r.uld_no, "carrier": r.carrier}
            for r in uld_rows
        ]

        if uld_ids:
            await db.execute(
                update(ExportUldMaster)
                .where(ExportUldMaster.id.in_(uld_ids))
                .values(is_available=True)
            )

        # hard-delete assignment -> cascade removes ExportUldAssignmentDetail
        await db.delete(assignment)

    # deactivate header
    header.is_active = False
    header.updated_at = now

    # remove all booked AWBs
    await db.execute(
        delete(ExportFlightBookingDetail).where(
            ExportFlightBookingDetail.flight_header_id == header_id
        )
    )

    # ONE flight-level log
    await write_car_message_flow_audit(
        db=db,
        awb_reference_id=None,
        flight_reference_id=header_id,
        module=CarMessageFlowModule.RECONCILIATION,
        flow_step=CarMessageFlowStep.RECONCILIATION,
        record_id=header_id,
        action="UPDATE",
        performed_by=SYSTEM_ACTOR,
        changes={
            "event": "FLIGHT_DEACTIVATED_ALL_ZERO",
            "reason": "ALL_LOADED_ZERO_AND_DEPARTED",
            "flight_no": header.flight_no,
            "flight_date": str(header.flight_date),
            "total_freed_pcs": total_freed_pcs,
            "freed_awbs": freed_awbs,
            "released_ulds": released_ulds,
            "uld_count": len(released_ulds),
        },
    )



# ===================================================================
logger = logging.getLogger("reconcile")

RECONCILE_WINDOW_DAYS = 1
_ADVISORY_LOCK_KEY = 778421900001   # unique to THIS job; auto_assign must not reuse it
IST = ZoneInfo("Asia/Kolkata") 

async def run_reconcile_job():
    today =  datetime.now(IST).date()
    date_from = today - timedelta(days=RECONCILE_WINDOW_DAYS)
    date_to = today

    async with async_session() as db: 
        got_lock = await db.scalar(
            text("SELECT pg_try_advisory_lock(:k)"), {"k": _ADVISORY_LOCK_KEY}
        )
        if not got_lock:
            logger.info("reconcile: another run holds the lock — skipping this tick")
            print("reconcile schedualr running")
            return

        try:
            summary = await reconcile_departed_flight_bookings(
                db=db, date_from=date_from, date_to=date_to,
            )
            logger.info("reconcile summary: %s", summary)
            print("reconcile schedualr running")
            return summary
        except Exception:
            logger.exception("reconcile job failed")
            raise
        finally:
            await db.execute(
                text("SELECT pg_advisory_unlock(:k)"), {"k": _ADVISORY_LOCK_KEY}
            )
