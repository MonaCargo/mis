import datetime as dt
from typing import Optional
from sqlalchemy import String, Integer, Float, Date, DateTime, Time, Index, func
from sqlalchemy.orm import Mapped, mapped_column
from app.db.base import Base


class DigitalReportsMisSegregationCleaned(Base):
    __tablename__ = "dr_mis_segregation_cleaned"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    sl_no: Mapped[Optional[int]] = mapped_column(Integer)  # UNCOMMENTED THIS
    carrier: Mapped[Optional[str]] = mapped_column(String(10), index=True)
    flt_no: Mapped[Optional[str]] = mapped_column(String(20), index=True)
    flt_date: Mapped[Optional[dt.date]] = mapped_column(Date, index=True)
    awb_no: Mapped[Optional[str]] = mapped_column(String(15), index=True)
    awb_sfx: Mapped[Optional[str]] = mapped_column(String(5))
    
    # ata_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    # ata_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    ata_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    
    # flt_doc_arrival_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    # flt_doc_arrival_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    flt_doc_arrival_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    
    # last_uld_arrival_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    # last_uld_arrival_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    last_uld_arrival_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    
    # bulk_uld_arrival_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    # bulk_uld_arrival_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    bulk_uld_arrival_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    
    origin: Mapped[Optional[str]] = mapped_column(String(10))
    dest: Mapped[Optional[str]] = mapped_column(String(10))

    manifest_pcs: Mapped[Optional[int]] = mapped_column(Integer)
    manifest_wgt: Mapped[Optional[float]] = mapped_column(Float)
    seg_pcs: Mapped[Optional[int]] = mapped_column(Integer)
    seg_wgt: Mapped[Optional[float]] = mapped_column(Float)
    pcs: Mapped[Optional[int]] = mapped_column(Integer)
    grs_wgt: Mapped[Optional[float]] = mapped_column(Float)
    chg_wgt: Mapped[Optional[float]] = mapped_column(Float)
    volume_mc: Mapped[Optional[float]] = mapped_column(Float)
    no_of_houses: Mapped[Optional[int]] = mapped_column(Integer)

    shc: Mapped[Optional[str]] = mapped_column(String(50))
    chg_shc: Mapped[Optional[str]] = mapped_column(String(50))
    billing_shc: Mapped[Optional[str]] = mapped_column(String(50))
    nog: Mapped[Optional[str]] = mapped_column(String(255))
    consignee_details: Mapped[Optional[str]] = mapped_column(String(255)) # INCREASED FROM 20 TO 255
    
    # awd_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    # awd_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    awd_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    
    # nfd_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    # nfd_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    nfd_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    
    # rcf_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    # rcf_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    rcf_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    
    # do_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    # do_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    do_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    
    # tfd_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    # tfd_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    tfd_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    
    egm_igm_no: Mapped[Optional[str]] = mapped_column(Integer)

    # flt_com_date: Mapped[Optional[dt.date]] = mapped_column(Date)
    # flt_com_time: Mapped[Optional[dt.time]] = mapped_column(Time)
    flt_com_date_time_combine: Mapped[Optional[dt.datetime]] = mapped_column(DateTime(timezone=True))
    flight_status: Mapped[Optional[str]] = mapped_column(String(50)) # Added missing key from COL_MAP

    
    report_date: Mapped[dt.date] = mapped_column(Date, index=True, nullable=False)
    uploaded_by: Mapped[Optional[str]] = mapped_column(String(80), index=True)

    created_at: Mapped[dt.datetime] = mapped_column(DateTime(timezone=True), server_default=func.now())

    __table_args__ = (
        Index("ix_dr_seg_carrier_flt_date", "carrier", "flt_date"),
        Index("ix_dr_seg_awb_flt", "awb_no", "flt_no"),
        Index("ix_dr_seg_report_date", "report_date"),
    )