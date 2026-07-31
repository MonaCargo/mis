
 
import datetime as dt
from typing import Optional
from sqlalchemy import Float
from sqlalchemy import String, Integer, Numeric, Date, DateTime, Index, Time, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column
from app.db.base import Base
 
class DigitalReportsMisUpliftingPo(Base):
    __tablename__ = "dr_mis_uplifting_po"
 
    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)
 
    # ── stamped on every row by the service ─────────────────────────────
    
    # ── identity / grouping ─────────────────────────────────────────────
    carrier:    Mapped[Optional[str]] = mapped_column(String(10), index=True) # "NIL" for nil block
    # sl_no:      Mapped[Optional[int]] = mapped_column(Integer)
    flt_no:     Mapped[Optional[str]] = mapped_column(String(20), index=True)
    line_flight_freighter: Mapped[Optional[str]] = mapped_column(String(50))
    flt_dest: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    flt_dest_country: Mapped[Optional[str]] = mapped_column(String(100), index=True)
    flt_dest_continents: Mapped[Optional[str]] = mapped_column(String(50), index=True)
    month_year: Mapped[Optional[str]] = mapped_column(String(15), index=True) # Stores "Jul-2026"
    # year:       Mapped[Optional[int]] = mapped_column(Integer, index=True)      # Stores 2026
    flt_date:   Mapped[Optional[dt.date]] = mapped_column(Date, index=True)
    awb_no:   Mapped[Optional[str]] = mapped_column(String(15), index=True) # optional , In NIL carrier no val present
    awb_sfx:  Mapped[Optional[str]] = mapped_column(String(5))
    origin:   Mapped[Optional[str]] = mapped_column(String(5))
    awb_dest_country:    Mapped[Optional[str]] = mapped_column(String(60), index=True)
    awb_dest_continents: Mapped[Optional[str]] = mapped_column(String(30), index=True)
    dest:     Mapped[Optional[str]] = mapped_column(String(5))
    tp_type:  Mapped[Optional[str]] = mapped_column(String(20), nullable=True, index=True) 
    
 
    # ── quantities (Numeric = exact, no float drift) ────────────────────
    pcs:       Mapped[Optional[int]]   = mapped_column(Integer)
    grs_wgt:   Mapped[Optional[float]] = mapped_column(Float)
    grs_wgt_mt: Mapped[Optional[float]] = mapped_column(Float) 
    chg_wgt:   Mapped[Optional[float]] = mapped_column(Float)
    volume_mc: Mapped[Optional[float]] = mapped_column(Float)
 
    # ── date + time, stored SEPARATELY (already converted IST->UTC in cleaner) ──
    car_date:               Mapped[Optional[dt.date]] = mapped_column(Date)
    car_time:               Mapped[Optional[dt.time]] = mapped_column(Time)
    doc_date:                Mapped[Optional[dt.date]] = mapped_column(Date)
    doc_time:                Mapped[Optional[dt.time]] = mapped_column(Time)
    xray_date:               Mapped[Optional[dt.date]] = mapped_column(Date)
    xray_time:               Mapped[Optional[dt.time]] = mapped_column(Time)
    rcs_date:                Mapped[Optional[dt.date]] = mapped_column(Date)
    rcs_time:                Mapped[Optional[dt.time]] = mapped_column(Time)
    flight_etd_date:         Mapped[Optional[dt.date]] = mapped_column(Date)
    flight_etd_time:         Mapped[Optional[dt.time]] = mapped_column(Time)
    flight_dep_date:         Mapped[Optional[dt.date]] = mapped_column(Date)
    flight_dep_time:         Mapped[Optional[dt.time]] = mapped_column(Time)

    #___ Combinate dates saved in UTC
    car_date_time_combine:          Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    doc_date_time_combine:          Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    xray_date_time_combine:         Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    rcs_date_time_combine:          Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    flight_etd_date_time_combine:   Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    flight_dep_date_time_combine:   Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    uld_release_date_time_combine:  Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
 
    # ── ULD ─────────────────────────────────────────────────────────────
    uld_no:            Mapped[Optional[str]] = mapped_column(String(20))
    uld_release_date:  Mapped[Optional[dt.date]] = mapped_column(Date)
    uld_release_time:  Mapped[Optional[dt.time]] = mapped_column(Time)
 
    # ── descriptive ─────────────────────────────────────────────────────
    nog:          Mapped[Optional[str]] = mapped_column(String(150))
    nog_1: Mapped[Optional[str]] = mapped_column(String(255))
    nog_2: Mapped[Optional[str]] = mapped_column(String(255))
    shc:          Mapped[Optional[str]] = mapped_column(String(30))
    chg_shc:      Mapped[Optional[str]] = mapped_column(String(30))
    final_shc:      Mapped[Optional[str]] = mapped_column(String(100))
    billing_shc:  Mapped[Optional[str]] = mapped_column(String(30))
    agent:        Mapped[Optional[str]] = mapped_column(String(20))
    agent_name: Mapped[Optional[str]] = mapped_column(String(100))
    shipper_name: Mapped[Optional[str]] = mapped_column(String(150))
    trm_number:   Mapped[Optional[str]] = mapped_column(Integer)
    trm_date:     Mapped[Optional[dt.date]] = mapped_column(Date)
    pax_freighter: Mapped[Optional[str]] = mapped_column(String(15))

    report_date:  Mapped[dt.date] = mapped_column(Date, index=True)   # DATE, no tz; used as identifier key
    uploaded_by:  Mapped[Optional[str]] = mapped_column(String(80), index=True)
 
 
 
 
    created_at: Mapped[dt.datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now()
    )
 
    __table_args__ = (
        Index("ix_dr_uplift_carrier_flt_date", "carrier", "flt_date"),
        Index("ix_dr_uplift_awb_flt", "awb_no", "flt_no"),
        Index("ix_dr_uplift_month_year", "month_year"),
    )
 
    def __repr__(self) -> str:
        return (f"<DigitalReportsMisUpliftingPo {self.carrier} {self.flt_no} "
                f"{self.awb_no or 'NIL'} {self.flt_date}>")
 













