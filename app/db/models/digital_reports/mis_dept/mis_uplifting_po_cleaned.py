

import datetime as dt
from typing import Optional
from sqlalchemy import Float
from sqlalchemy import String, Integer, Numeric, Date, DateTime, Time, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DigitalReportsMisUpliftingCleaned(Base):
    __tablename__ = "dr_mis_uplifting_po_cleaned"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # ── stamped on every row by the caller/service, not part of cleaner output ──
    

    # ── everything below matches CLEANED_COLUMNS / seg_cleaner.py exactly ──
    carrier:  Mapped[Optional[str]] = mapped_column(String(10), index=True)
    sl_no:    Mapped[Optional[int]] = mapped_column(Integer)
    flt_no:   Mapped[Optional[str]] = mapped_column(String(20), index=True)
    flt_date: Mapped[Optional[dt.date]] = mapped_column(Date, index=True)
    awb_no:   Mapped[Optional[str]] = mapped_column(String(15), index=True)
    awb_sfx:  Mapped[Optional[str]] = mapped_column(String(5))
    origin:   Mapped[Optional[str]] = mapped_column(String(5))
    dest:     Mapped[Optional[str]] = mapped_column(String(5))

    pcs:       Mapped[Optional[int]]   = mapped_column(Integer)
    grs_wgt: Mapped[Optional[float]] = mapped_column(Float)
    chg_wgt:   Mapped[Optional[float]] = mapped_column(Float)
    volume_mc: Mapped[Optional[float]] = mapped_column(Float)

    car_date:         Mapped[Optional[dt.date]] = mapped_column(Date)
    car_time:         Mapped[Optional[dt.time]] = mapped_column(Time)
    doc_date:         Mapped[Optional[dt.date]] = mapped_column(Date)
    doc_time:         Mapped[Optional[dt.time]] = mapped_column(Time)
    xray_date:        Mapped[Optional[dt.date]] = mapped_column(Date)
    xray_time:        Mapped[Optional[dt.time]] = mapped_column(Time)
    rcs_date:         Mapped[Optional[dt.date]] = mapped_column(Date)
    rcs_time:         Mapped[Optional[dt.time]] = mapped_column(Time)
    flight_etd_date:  Mapped[Optional[dt.date]] = mapped_column(Date)
    flight_etd_time:  Mapped[Optional[dt.time]] = mapped_column(Time)
    flight_dep_date:  Mapped[Optional[dt.date]] = mapped_column(Date)
    flight_dep_time:  Mapped[Optional[dt.time]] = mapped_column(Time)
    uld_no: Mapped[Optional[str]] = mapped_column(String(20))
    uld_release_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    uld_release_time: Mapped[Optional[dt.time]] = mapped_column(Time)

    nog:          Mapped[Optional[str]] = mapped_column(String(150))
    shc:          Mapped[Optional[str]] = mapped_column(String(30))
    chg_shc:      Mapped[Optional[str]] = mapped_column(String(30))
    billing_shc:  Mapped[Optional[str]] = mapped_column(String(30))
    agent:        Mapped[Optional[str]] = mapped_column(String(20))
    shipper_name: Mapped[Optional[str]] = mapped_column(String(150))
    trm_number:   Mapped[Optional[str]] = mapped_column(Integer)
    trm_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    pax_freighter: Mapped[Optional[str]] = mapped_column(String(15))

    
    

    
    

    report_date: Mapped[dt.date] = mapped_column(Date, index=True)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(80), index=True)

    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )

    __table_args__ = (
        Index("ix_dr_uplift_cleaned_carrier_flt_date", "carrier", "flt_date"),
        Index("ix_dr_uplift_cleaned_report_date", "report_date"),
    )

    def __repr__(self) -> str:
        return (f"<DigitalReportsMisUpliftingCleaned {self.carrier} "
                f"{self.flt_no} {self.awb_no or 'NIL'} {self.flt_date}>")