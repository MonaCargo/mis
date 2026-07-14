from sqlalchemy import Column, Integer, String, Float, Date, DateTime
from datetime import datetime
from app.db.base import Base

class DigitalReportImportSegregationReport(Base):
    """
    Source: Import Segregation Report sheet (TP Section)
    Shift-basis column (used in dashboard Section - confirm with Vipul):
    ata_date_time (Actual arrival time) is used as default shift-basis field.
    NOTE: "Total Shipment Count" subtotal rows in the sheet are automatically
    dropped in the cleaner because they have no AWB No.
    """
    __tablename__ = "dr_exp_import_segregation_report"

    id = Column(Integer, primary_key=True, index=True)

    sl_no = Column(Integer, nullable=True)
    flight_no = Column(String, nullable=True, index=True)
    flight_date = Column(Date, nullable=True)
    awb_no = Column(String, nullable=True, index=True)
    sfx = Column(String, nullable=True)

    ata_date_time = Column(DateTime, nullable=True, index=True)          # <-- SHIFT BASIS (assumed)
    flt_doc_arrival_date_time = Column(DateTime, nullable=True)
    last_uld_arrival_date_time = Column(DateTime, nullable=True)
    bulk_uld_arrival_date_time = Column(DateTime, nullable=True)

    org = Column(String, nullable=True)
    dest = Column(String, nullable=True)

    manifest_pcs = Column(Integer, nullable=True)
    manifest_wgt = Column(Float, nullable=True)
    seg_pcs = Column(Integer, nullable=True)
    seg_wgt = Column(Float, nullable=True)
    pcs = Column(Integer, nullable=True)
    gross_wgt = Column(Float, nullable=True)
    chg_wgt = Column(Float, nullable=True)
    vol_mc = Column(Float, nullable=True)
    no_of_houses = Column(Integer, nullable=True)

    shc = Column(String, nullable=True)
    chg_shc = Column(String, nullable=True)
    billing_shc = Column(String, nullable=True)
    nog = Column(String, nullable=True)
    consignee_details = Column(String, nullable=True)

    awd_date = Column(DateTime, nullable=True)
    nfd_date = Column(DateTime, nullable=True)
    rcf_date = Column(DateTime, nullable=True)
    do_date_time = Column(DateTime, nullable=True)
    tfd_date_time = Column(DateTime, nullable=True)

    egm_igm_no = Column(String, nullable=True)
    flt_com_date_time = Column(DateTime, nullable=True)
    flight_status = Column(String, nullable=True)

    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(Integer, nullable=True)
    report_date = Column(Date, nullable=False, index=True)  # Ye batayega ki ye data kis din ka hai