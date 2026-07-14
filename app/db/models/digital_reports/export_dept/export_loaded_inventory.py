from sqlalchemy import Column, Integer, String, Float, DateTime, Date
from datetime import datetime
from app.db.base import Base


class DigitalReportExportLoadedInventory(Base):
    """
    Source: Export Loaded Inventory sheet
    Combined with cargo_uplift_report for dashboard Section P.4 (Build Up)
    Shift-basis column: loaded_date_time
    """
    __tablename__ = "dr_exp_export_loaded_inventory"

    id = Column(Integer, primary_key=True, index=True)

    carrier = Column(String, nullable=True)
    awb_no = Column(String, nullable=True, index=True)
    uld_no = Column(String, nullable=True)
    status = Column(String, nullable=True)                            # TFD / RCS / PRE / RCT etc.
    loaded_date_time = Column(DateTime, nullable=True, index=True)    # <-- SHIFT BASIS (P.4)
    destination = Column(String, nullable=True)
    agent = Column(String, nullable=True)
    pcs = Column(Integer, nullable=True)
    wgt_chg = Column(Float, nullable=True)
    wgt_grs = Column(Float, nullable=True)
    volume = Column(Float, nullable=True)
    shc_code = Column(String, nullable=True)
    flt_num = Column(String, nullable=True)
    uld_wgt = Column(Float, nullable=True)

    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(Integer, nullable=True)
    report_date = Column(Date, nullable=False, index=True) # Ye batayega ki ye data kis din ka hai