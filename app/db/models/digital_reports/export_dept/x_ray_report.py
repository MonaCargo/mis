from sqlalchemy import Column, Integer, String, Float, Date, DateTime
from datetime import datetime
from app.db.base import Base


class DigitalReportXrayReport(Base):
    """
    Source: X Ray Report sheet
    Combined with export_tp_xray_report + import_tp_xray_report for dashboard Section P.3
    Shift-basis column: xray_date_time
    """
    __tablename__ = "dr_exp_xray_report"

    id = Column(Integer, primary_key=True, index=True)

    sl_no = Column(Integer, nullable=True)
    awb_no = Column(String, nullable=True, index=True)              # -> P.3 #Airway Bill Count
    sb_no = Column(String, nullable=True)
    sb_date = Column(Date, nullable=True)
    origin = Column(String, nullable=True)
    destination = Column(String, nullable=True)
    pcs = Column(Integer, nullable=True)                            # -> P.3 #Piece Count
    gross_wgt = Column(Float, nullable=True)
    chg_wgt = Column(Float, nullable=True)
    nog = Column(String, nullable=True)
    shc = Column(String, nullable=True)

    car_msg_date_time = Column(DateTime, nullable=True)
    leo_date_time = Column(DateTime, nullable=True)
    xray_start_date_time = Column(DateTime, nullable=True)          # XRAY_START_DT
    xray_end_date_time = Column(DateTime, nullable=True)            # XRAY_END_DT
    xray_type = Column(String, nullable=True)                       # X-RAY TYPE
    xray_date_time = Column(DateTime, nullable=True, index=True)    # <-- SHIFT BASIS (P.3), X-RAY DT/TIME
    xray_user = Column(String, nullable=True)                       # X-RAY-USER

    phs_pcs = Column(Integer, nullable=True)
    etd_pcs = Column(Integer, nullable=True)
    eds_pcs = Column(Integer, nullable=True)
    edd_pcs = Column(Integer, nullable=True)
    vck_pcs = Column(Integer, nullable=True)
    cmd_pcs = Column(Integer, nullable=True)

    doc_accept_date_time = Column(DateTime, nullable=True)          # DOC ACCPT DT/TIME
    rcs_rcf_rct_date_time = Column(DateTime, nullable=True)         # RCS/RCF/RCT DT/TIME
    uplifting_date_time = Column(DateTime, nullable=True)           # UPLIFTING DT/TIME

    flt_no = Column(String, nullable=True)
    agent_name = Column(String, nullable=True)
    serial_no = Column(String, nullable=True)
    device_model = Column(String, nullable=True)
    remarks = Column(String, nullable=True)

    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(Integer, nullable=True)
    report_date = Column(Date, nullable=False, index=True) # Ye batayega ki ye data kis din ka hai