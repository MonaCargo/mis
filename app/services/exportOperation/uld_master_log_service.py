# app/utils/exportOperation/uld_oplog.py
"""
Helper to write entries to export_uld_operation_log.

Service code stays clean — one function call per audit event.
The helper does NOT commit — it adds to the current transaction so
the log is written atomically with the main operation.
"""

from datetime import datetime, timezone
from typing import Optional, Any, Dict

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.db.models.exportOperation.uld_master_logs import ExportUldMasterOperationLogs




# ── Action constants (use these so typos don't fragment your log table) ─────
class UldAction:
    CREATE         = "CREATE"
    CREATE_FAILED  = "CREATE_FAILED"
    UPDATE         = "UPDATE"
    DEACTIVATE     = "DEACTIVATE"
    ACTIVATE       = "ACTIVATE"
    MARK_AVAILABLE = "MARK_AVAILABLE"
    MARK_UNAVAILABLE = "MARK_UNAVAILABLE"
    CHANGE_CARRIER = "CHANGE_CARRIER"


def uld_snapshot(row: ExportUldMaster) -> Dict[str, Any]:
    """Serialise a ULD row to a dict suitable for the JSONB column."""
    return {
        "id": row.id,
        "uld_no": row.uld_no,
        "carrier": row.carrier,
        "uld_type": row.uld_type,
        "is_active": row.is_active,
        "is_available": row.is_available,
    }


async def write_uld_log(
    db: AsyncSession,
    *,
    action: str,
    uld_no: str,
    message: str,
    uld_id: Optional[int] = None,
    before_state: Optional[Dict[str, Any]] = None,
    after_state: Optional[Dict[str, Any]] = None,
    extra_meta: Optional[Dict[str, Any]] = None,
    performed_by: Optional[str] = None,
    remarks: Optional[str] = None,
) -> None:
    """
    Append one entry to the operation log.

    Does NOT commit — the caller's commit flushes everything together so the
    log row and the data change land atomically.
    """
    entry = ExportUldMasterOperationLogs(
        uld_id=uld_id,
        uld_no=uld_no,
        action=action,
        message=message,
        before_state=before_state,
        after_state=after_state,
        extra_meta=extra_meta,
        performed_by=performed_by,
         remarks=remarks,
        performed_at=datetime.now(timezone.utc),
    )
    db.add(entry)