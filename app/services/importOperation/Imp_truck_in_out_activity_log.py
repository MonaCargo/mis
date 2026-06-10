


from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.importOperation.imp_truck_in_out_module import ImportTruckInOutActivityLog
from typing import Optional, Dict, Any
import logging

logger = logging.getLogger(__name__)


def _diff(before: dict, after: dict) -> dict:
    """Compute changed fields only — keeps `changes` column readable."""
    if not before:
        return {k: {"old": None, "new": v} for k, v in (after or {}).items()}
    if not after:
        return {k: {"old": v, "new": None} for k, v in (before or {}).items()}
    return {
        k: {"old": before.get(k), "new": after.get(k)}
        for k in set(before) | set(after)
        if before.get(k) != after.get(k)
    }


async def log_activity_of_imp_truck_in_out(
    db: AsyncSession,
    event_type: str,
    entity_type: str,
    performed_by: str,
    *,
    entity_id: Optional[int] = None,
    truck_visit_id: Optional[int] = None,
    gate_pass_no: Optional[str] = None,
    truck_number: Optional[str] = None,
    queue_no: Optional[str] = None,
    token_no: Optional[str] = None,
    description: Optional[str] = None,
    reason: Optional[str] = None,
    snapshot_before: Optional[Dict[str, Any]] = None,
    snapshot_after: Optional[Dict[str, Any]] = None,
    performed_by_role: Optional[str] = "OPERATOR",
    device_id: Optional[str] = None,
    ip_address: Optional[str] = None,
    request_id: Optional[str] = None,
):
    """
    Append an activity log row to the session. 
    Caller must commit — this keeps logs atomic with the actual change.
    NEVER raises — log failures must not break business operations.
    """
    try:
        changes = None
        if snapshot_before is not None or snapshot_after is not None:
            changes = _diff(snapshot_before or {}, snapshot_after or {})

        log = ImportTruckInOutActivityLog(
            event_type=event_type,
            entity_type=entity_type,
            entity_id=entity_id,
            truck_visit_id=truck_visit_id,
            gate_pass_no=gate_pass_no,
            truck_number=truck_number,
            queue_no=queue_no,
            token_no=token_no,
            description=description,
            reason=reason,
            snapshot_before=snapshot_before,
            snapshot_after=snapshot_after,
            changes=changes,
            performed_by=performed_by or "-",
            performed_by_role=performed_by_role,
            device_id=device_id,
            ip_address=ip_address,
            request_id=request_id,
        )
        db.add(log)
    except Exception as e:
        # Logging must never break the main operation
        logger.error(f"Failed to add activity log entry: {e}", exc_info=True)