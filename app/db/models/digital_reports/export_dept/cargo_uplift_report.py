from sqlalchemy import Column, Integer, String, Float, Date, DateTime
from datetime import datetime
from app.db.base import Base


class DigitalReportCargoUpliftReport(Base):
    """
    Source: Cargo Uplifting Report sheet
    Shift-basis column (used in dashboard Section 1.A / 1.B): uld_release_date_time
    """
    __tablename__ = "dr_exp_cargo_uplift_report"

    id = Column(Integer, primary_key=True, index=True)

                           
    sl_no = Column(Integer, nullable=True)
    flt_no = Column(String, nullable=True)
    flt_date = Column(Date, nullable=True)
    awb_no = Column(String, nullable=True, index=True)
    awb_sfx = Column(String, nullable=True)                         # AWB Sfx (P / A)
    origin = Column(String, nullable=True)
    dest = Column(String, nullable=True)
    pcs = Column(Integer, nullable=True)
    gross_wgt = Column(Float, nullable=True)                        # GRS Wg  -> Summary 1.A
    chg_wgt = Column(Float, nullable=True)                          # CHG WGT -> Summary 1.B
    volume = Column(Float, nullable=True)

    car_date_time = Column(DateTime, nullable=True)                 # CAR DATE + CAR TIME combined
    doc_date_time = Column(DateTime, nullable=True)                 # DOC DATE + DOC TIME combined
    xray_date_time = Column(DateTime, nullable=True)                # XRAY DATE + XRAY TIME combined
    rcs_rcf_rct_date_time = Column(DateTime, nullable=True)         # RCS/RCF/RCT DATE + TIME combined

    flight_etd_date_time = Column(DateTime, nullable=True)          # Flight ETD (date) + Flight ETD (time)
    flight_dep_date_time = Column(DateTime, nullable=True)          # Flight Dep (date) + Flight Dep (time)

    uld_no = Column(String, nullable=True)
    uld_release_date_time = Column(DateTime, nullable=True, index=True)  # <-- SHIFT BASIS (1.A / 1.B)

    nog = Column(String, nullable=True)
    shc = Column(String, nullable=True)
    chg_shc = Column(String, nullable=True)
    billing_shc = Column(String, nullable=True)
    agent = Column(String, nullable=True)
    shipper_name = Column(String, nullable=True)
    trm_number = Column(String, nullable=True)
    trm_date = Column(Date, nullable=True)
    passenger_freighter = Column(String, nullable=True)             # PASSENGER / FREIGHTER

    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(Integer, nullable=True)  # emp_id
    report_date = Column(Date, nullable=False, index=True) # Ye batayega ki ye data kis din ka hai