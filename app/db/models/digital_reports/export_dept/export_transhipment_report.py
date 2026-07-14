from sqlalchemy import Column, Integer, String, Float, Date, DateTime
from datetime import datetime
from app.db.base import Base


class DigitalReportExportTranshipmentReport(Base):
    """
    Source: Export Transhipment Report sheet (TP Section)
    Shift-basis column (used in dashboard Section - confirm with Vipul):
    doc_date_time is used as default shift-basis field.
    NOTE: uld_load and xray_time are stored as String because the source
    sheet only has bare time text (e.g. "20:26") in those cells, not a
    full date+time value.
    """
    __tablename__ = "dr_exp_export_transhipment_report"

    id = Column(Integer, primary_key=True, index=True)

    sl_no = Column(Integer, nullable=True)
    awb_no = Column(String, nullable=True, index=True)
    pcs = Column(Integer, nullable=True)
    gross_wgt = Column(Float, nullable=True)
    rec_pcs = Column(Integer, nullable=True)
    received_wgt = Column(Float, nullable=True)
    received_chg_wgt = Column(Float, nullable=True)

    shc = Column(String, nullable=True)
    billing_shc = Column(String, nullable=True)
    commodity = Column(String, nullable=True)
    org = Column(String, nullable=True)
    des = Column(String, nullable=True)

    doc_date_time = Column(DateTime, nullable=True, index=True)          # <-- SHIFT BASIS (assumed)

    exp_tp_seg_flight_no = Column(String, nullable=True)
    exp_tp_flight_date = Column(Date, nullable=True)
    exp_tp_seg_no_date_time = Column(DateTime, nullable=True)

    trm_no = Column(Integer, nullable=True)
    trm_date = Column(Date, nullable=True)

    xray_date = Column(Date, nullable=True)
    xray_time = Column(String, nullable=True)
    xray_date_time = Column(DateTime, nullable = True) # Ye naya combined column

    ramp_transfer_date_time = Column(DateTime, nullable=True)
    ramp_transfer_remark = Column(String, nullable=True)
    ramp_transfer_user = Column(String, nullable=True)

    airline_cd = Column(String, nullable=True)
    flight_no = Column(String, nullable=True)
    flight_date = Column(Date, nullable=True)
    uld_load = Column(String, nullable=True)
    departure_date_time = Column(DateTime, nullable=True)

    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(Integer, nullable=True)
    report_date = Column(Date, nullable=False, index=True)  # Ye batayega ki ye data kis din ka hai