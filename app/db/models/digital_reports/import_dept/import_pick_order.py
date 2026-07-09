"""
ORM model for the Import Pick Order (Examination) report.

Source: COSYS "PICK ORDER REPORT" Excel → cleaned by
        clean_pick_order_report() → saved by save_pick_order_report().

Datetime convention
-------------------
The four event datetimes (rfe, ffe, poe_start, poe_end) come from the Excel as
IST wall-clock and are stored as UTC (TIMESTAMP WITH TIME ZONE), consistent with
the rest of the DCSC backend. Convert to IST only at the response boundary.

report_date
-----------
A plain DATE (no time) the operator selects at upload time. It tags every row
of that upload so the data can be traced to, and re-replaced for, a given
report day. Re-uploading the same report_date deletes the old rows first
(atomic replace).
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Integer, String, Date, DateTime, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base


class DigitalReportImportPickOrder(Base):
    __tablename__ = "dr_imp_pick_order"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── report tracing key (operator-selected upload date) ─────────────────
    report_date: Mapped[date] = mapped_column(
        Date, nullable=False,
        comment="Operator-selected report day (plain DATE). Tags this upload.(it saved as IST date in DB because from frontend it comes as IST date and I save it as IST date in DB)",
    )

    # ── core fields ────────────────────────────────────────────────────────
    awb_no: Mapped[Optional[str]] = mapped_column(
        String(11), nullable=False,
        comment="Normalized 11-digit AWB (space stripped, last 11 digits).",
    )
    hawb_no: Mapped[Optional[str]] = mapped_column(
        String(50), nullable=True,
        comment="House AWB number (raw from report).",
    )
    pcs_for_examination: Mapped[Optional[int]] = mapped_column(
        Integer, nullable=False, comment="Pcs for Examination.",
    )

    # ── event datetimes (stored UTC) ───────────────────────────────────────
    rfe_datetime: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="RFE date & time (UTC).",
    )
    ffe_datetime: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="FFE date & time (UTC).",
    )
    poe_start_datetime: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="POE start date & time (UTC).",
    )
    poe_end_datetime: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True), nullable=True, comment="POE end date & time (UTC).",
    )

    # ── audit ──────────────────────────────────────────────────────────────
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(100), nullable=True)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )

    __table_args__ = (
        # Fast delete/query of a whole report day (the re-upload replace path).
        Index("ix_dr_imp_pick_order_report_date", "report_date"),
        # Supports per-day AWB lookups.
        Index("ix_dr_imp_pick_order_awb_date", "awb_no", "report_date"),
    )

    def __repr__(self) -> str:
        return (
            f"<DigitalReportImportPickOrder awb={self.awb_no} "
            f"pcs={self.pcs_for_examination} report_date={self.report_date}>"
        )