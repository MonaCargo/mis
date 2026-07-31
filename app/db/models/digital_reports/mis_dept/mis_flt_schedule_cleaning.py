import datetime as dt
from typing import Optional

from sqlalchemy import DateTime, String, Integer, Date, Time, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DigitalReportsFlightScheduleImport(Base):
    __tablename__ = "dr_mis_flight_schedule_import_cleaned"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── matches clean_flight_schedule_dataframe's flights_df output exactly ──
    flt_no: Mapped[Optional[str]] = mapped_column(String(20), index=True)   # stripped/cleaned, e.g. 7L3219, AI0102
    aircraft_type: Mapped[Optional[str]] = mapped_column(String(10))        # e.g. 777, 320, 747
    origin: Mapped[Optional[str]] = mapped_column(String(5), index=True)   # e.g. DWC, JFK, LHR
    destination: Mapped[Optional[str]] = mapped_column(String(5), index=True) # e.g. DEL
    
    time_std: Mapped[Optional[dt.time]] = mapped_column(Time)               # Scheduled Time of Departure
    time_sta: Mapped[Optional[dt.time]] = mapped_column(Time)               # Scheduled Time of Arrival
    
    avail_weight_cargo: Mapped[Optional[int]] = mapped_column(Integer)     # Cargo weight capacity in KG
    avail_weight_mail: Mapped[Optional[int]] = mapped_column(Integer)      # Mail weight capacity in KG
    
    frequency: Mapped[Optional[str]] = mapped_column(String(100))          # Operating days, e.g. WEDNESDAY TUESDAY
    flt_type: Mapped[Optional[str]] = mapped_column(String(20))           # e.g. PASSENGER / CARGO
    flt_status: Mapped[Optional[str]] = mapped_column(String(20))         # e.g. IMPORT / EXPORT

    # ── stamped on every row by caller/service, extracted from header preamble ──
    report_from: Mapped[Optional[dt.date]] = mapped_column(Date, index=True) # From header "FROM DATE : 21JUL2026"
    report_to: Mapped[Optional[dt.date]] = mapped_column(Date, index=True)   # From header "TO DATE : 22JUL2026"
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(80), index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_dr_flt_sched_no_orig_dest", "flt_no", "origin", "destination"),
        Index("ix_dr_flt_sched_report_range", "report_from", "report_to"),
    )

    def __repr__(self) -> str:
        return (f"<DigitalReportsFlightScheduleImport {self.flt_no} "
                f"{self.origin}->{self.destination}>")