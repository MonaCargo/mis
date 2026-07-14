from sqlalchemy import Column, Integer, String, Float, DateTime, Date
from datetime import datetime
from app.db.base import Base


class DigitalReportImportTpXrayReport(Base):
    """
    Source: Import TP Xray Report sheet
    Combined with xray_report + export_tp_xray_report for dashboard Section P.3
    Shift-basis column: xray_date_time
    serial_no kept for future "Machine Productivity" logic -- out of scope for now (per Vipul)
    """
    __tablename__ = "dr_exp_import_tp_xray_report"

    id = Column(Integer, primary_key=True, index=True)

    sl_no = Column(Integer, nullable=True)
    awb_no = Column(String, nullable=True, index=True)
    origin = Column(String, nullable=True)
    destination = Column(String, nullable=True)
    pcs = Column(Integer, nullable=True)
    gross_wgt = Column(Float, nullable=True)
    chg_wgt = Column(Float, nullable=True)
    nog = Column(String, nullable=True)
    shc = Column(String, nullable=True)

    xray_start_date_time = Column(DateTime, nullable=True)
    xray_end_date_time = Column(DateTime, nullable=True)
    xray_type = Column(String, nullable=True)
    xray_date_time = Column(DateTime, nullable=True, index=True)    # <-- SHIFT BASIS (P.3)
    xray_user = Column(String, nullable=True)

    phs_pcs = Column(Integer, nullable=True)
    etd_pcs = Column(Integer, nullable=True)
    eds_pcs = Column(Integer, nullable=True)
    edd_pcs = Column(Integer, nullable=True)
    vck_pcs = Column(Integer, nullable=True)
    cmd_pcs = Column(Integer, nullable=True)

    rcs_rcf_rct_date_time = Column(DateTime, nullable=True)
    uplifting_date_time = Column(DateTime, nullable=True)

    flt_no = Column(String, nullable=True)
    agent_name = Column(String, nullable=True)
    serial_no = Column(String, nullable=True)   # reserved for future Machine Productivity logic
    device_model_no = Column(String, nullable=True)
    remarks= Column(String, nullable=True)
    
    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(Integer, nullable=True)
    report_date = Column(Date, nullable=False, index=True) # Ye batayega ki ye data kis din ka hai