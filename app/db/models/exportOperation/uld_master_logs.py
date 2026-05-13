# app/models/export_uld_operation_log.py
"""
Audit log for all operations performed on Export ULD records.

Every CREATE, UPDATE, DEACTIVATE, etc. on export_uld_master should write
a row here. Logs are append-only — never updated, never deleted.
"""

from sqlalchemy import (
    Column,
    Integer,
    String,
    DateTime,
    Text,
    Index,
    ForeignKey,
)
from sqlalchemy.dialects.postgresql import JSONB

from app.db.base import Base


class ExportUldMasterOperationLogs(Base):
    __tablename__ = "export_uld_master_operation_logs"

    __table_args__ = (
        # Common query patterns: "all logs for this ULD", "all logs by this user",
        # "all logs of this action type", "recent logs"
        Index("idx_uld_oplog_uld_id", "uld_id"),
        Index("idx_uld_oplog_uld_no", "uld_no"),
        Index("idx_uld_oplog_action", "action"),
        Index("idx_uld_oplog_performed_at", "performed_at"),
    )

    id = Column(Integer, primary_key=True)

    # ── What was acted on ────────────────────────────────────────────────
    # Nullable FK because we may want to keep logs even if the ULD row is
    # ever hard-deleted (it shouldn't be, but defensive).
    uld_id = Column(
        Integer,
        ForeignKey("export_uld_master.id", ondelete="SET NULL"),
        nullable=True,
    )

    # Denormalised — survives even if uld_id is nulled. Always populated.
    uld_no = Column(String(25), nullable=False)

    # ── What happened ────────────────────────────────────────────────────
    # CREATE | UPDATE | DEACTIVATE | ACTIVATE | CREATE_FAILED |TRANSFER_CARRIER | etc.
    action = Column(String(30), nullable=False)

    # Free-form human-readable summary
    # e.g. "ULD AKE1234AI created", "Marked unavailable", "Carrier changed AI → EK"
    message = Column(Text, nullable=False)

    # ── State diff ───────────────────────────────────────────────────────
    # JSONB so we can query into it later (e.g. "find all logs where
    # is_available went from true to false")
    before_state = Column(JSONB, nullable=True)  # snapshot before change
    after_state  = Column(JSONB, nullable=True)  # snapshot after change

    # Extra context (request id, IP, reason text, etc.)
    extra_meta = Column(JSONB, nullable=True)

    # ── Who & when ───────────────────────────────────────────────────────
    performed_by = Column(String(50), nullable=True)
    performed_at = Column(DateTime(timezone=True), nullable=False)

    remarks = Column(Text, nullable=True)