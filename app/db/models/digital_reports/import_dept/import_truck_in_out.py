
from datetime import datetime
from typing import Optional

from sqlalchemy import (
    DateTime,
    Index,
    Integer,
    String,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base   # your project's declarative Base


class DigitalReportImportTruckInOut(Base):
    """
    One row per Gate Pass entry in the Import Truck IN/OUT report.

    Source: COSYS export → Excel upload → cleaned by
            clean_and_parse_truck_in_out_report().

    Datetime convention
    -------------------
    All datetime columns (gp_date, time_in, time_out, created_at, updated_at)
    are stored as UTC in PostgreSQL (TIMESTAMP WITH TIME ZONE).
    Convert to IST at the API response boundary using ist_day_to_utc_range /
    utc_to_ist helpers, consistent with the rest of the DCSC backend.
    """

    __tablename__ = "dr_imp_truck_in_out"

    # ── Primary key ────────────────────────────────────────────────────────
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── Core report fields ─────────────────────────────────────────────────
    gp_no: Mapped[str] = mapped_column(
        String(20),
        nullable=False,
        comment="Gate Pass number from COSYS",
    )

    date: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        nullable=False,
        comment="Truck in out performed time (stored as UTC)",
    )

    awb_no: Mapped[Optional[str]] = mapped_column(
        String(11),
        nullable=True,
        comment="Normalized 11-digit AWB number",
    )

        # ← ADD THIS BLOCK
    awb_part: Mapped[Optional[str]] = mapped_column(
        String(3),
        nullable=True,
        comment=(
            "Part indicator extracted from COSYS AWB field. "
            "'P' = Primary, 'A'/'B'/... = split shipment parts. "
            "NULL if no indicator was present in the source."
        ),
    )

    hawb_no: Mapped[Optional[str]] = mapped_column(
        String(50),
        nullable=True,
        comment="House AWB number",
    )

    pcs: Mapped[Optional[int]] = mapped_column(
        Integer,
        nullable=True,
        comment="Number of pieces",
    )

    truck_no: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
        comment="Vehicle registration number or 'BY HAND'",
    )

    driver_name: Mapped[Optional[str]] = mapped_column(
        String(100),
        nullable=True,
    )

    mobile_no: Mapped[Optional[str]] = mapped_column(
        String(15),
        nullable=True,
        comment="Stored as string to preserve leading zeros",
    )

    time_in: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Truck IN time stored as UTC",
    )

    time_out: Mapped[Optional[datetime]] = mapped_column(
        DateTime(timezone=True),
        nullable=True,
        comment="Truck OUT time stored as UTC. NULL means truck has not exited yet.",
    )

    agent: Mapped[Optional[str]] = mapped_column(
        String(200),
        nullable=True,
        comment="Cargo agent / consignee name",
    )

    sis_user_id: Mapped[Optional[str]] = mapped_column(
        String(20),
        nullable=True,
        comment="COSYS operator user ID",
    )

    # ── Audit timestamps ───────────────────────────────────────────────────
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )

    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

    # ── Constraints & indexes ──────────────────────────────────────────────
    __table_args__ = (
        # A GP No should appear only once per upload date
        # (same GP can't have two truck movements on the same day)
        UniqueConstraint("gp_no", name="uq_dr_imp_truck_in_out_gp_no"),

        # Composite — supports WHERE awb_no=X AND awb_part='A'
        Index("ix_dr_imp_truck_in_out_awb", "awb_no", "awb_part"),  # ← was awb_no only

        Index("ix_dr_imp_truck_in_out_date", "date"),   

        # Fast lookup for trucks still inside (time_out IS NULL)
        Index("ix_dr_imp_truck_in_out_time_out", "time_out"),
    )

    def __repr__(self) -> str:
            return (
                f"<DigitalReportImportTruckInOut gp_no={self.gp_no} "
                f"awb={self.awb_no}/{self.awb_part} "   # ← add /self.awb_part
                f"in={self.time_in} out={self.time_out}>"
            )