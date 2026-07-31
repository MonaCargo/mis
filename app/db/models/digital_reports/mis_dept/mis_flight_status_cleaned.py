import datetime as dt
from typing import Optional

from sqlalchemy import String, Integer, Float, Date, DateTime, Time, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DigitalReportsMisFlightStatus(Base):
    __tablename__ = "dr_mis_flight_status_cleaned"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── everything below matches flight_status_cleaner.py's flights_df exactly ──
    # sl_no:  Mapped[Optional[int]] = mapped_column(Integer)
    flt_no: Mapped[Optional[str]] = mapped_column(String(20), index=True)   # dash stripped, e.g. AI0143
    dest:   Mapped[Optional[str]] = mapped_column(String(5), index=True)
    flt_date: Mapped[Optional[dt.date]] = mapped_column(Date, index=True)
    dep_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    planning_received_mt:  Mapped[Optional[int]] = mapped_column(Integer)
    planned_uld_pallet:    Mapped[Optional[int]]   = mapped_column(Integer)
    planned_uld_container: Mapped[Optional[int]]   = mapped_column(Integer)
    planned_uld_bulk:      Mapped[Optional[int]]   = mapped_column(Integer)
    pending_uld_pallet:    Mapped[Optional[int]]   = mapped_column(Integer)
    pending_uld_container: Mapped[Optional[int]]   = mapped_column(Integer)
    pending_uld_bulk:      Mapped[Optional[int]]   = mapped_column(Integer)
    delivered_qty_mt:      Mapped[Optional[float]] = mapped_column(Float)
    pending_tonnage_mt:    Mapped[Optional[float]] = mapped_column(Float)
    planning_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    planning_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    planning_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))

    buildup_start_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    buildup_start_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    buildup_start_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))

    buildup_completion_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    buildup_completion_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    buildup_completion_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))

    gp_generation_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    gp_generation_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    gp_generation_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))

    uld_release_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    uld_release_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    uld_release_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))

    release_performance_d_sla:     Mapped[Optional[dt.time]] = mapped_column(Time)   # raw "5:35"
    planning_performance_d_x:      Mapped[Optional[dt.time]] = mapped_column(Time)   # raw "0:0"
    # release_performance_minutes:  Mapped[Optional[int]] = mapped_column(Integer)
    # planning_performance_minutes: Mapped[Optional[int]] = mapped_column(Integer)

    # ── stamped on every row by the caller/service, not part of cleaner output ──
    report_date: Mapped[dt.date] = mapped_column(Date, index=True)
    # report_from: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    # report_to: Mapped[dt.date | None] = mapped_column(Date, nullable=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(80), index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_dr_flight_status_flt_no_flt_date", "flt_no", "flt_date"),
        Index("ix_dr_flight_status_report_date",  "report_date"),
    )

    def __repr__(self) -> str:
        return (f"<DigitalReportsMisFlightStatus {self.flt_no} "
                f"{self.dest} {self.flt_date}>")
