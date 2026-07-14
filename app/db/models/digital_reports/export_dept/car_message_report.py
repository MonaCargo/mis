from sqlalchemy import Column, Integer, String, Float, Date, DateTime
from datetime import datetime
from app.db.base import Base


class DigitalReportCarMessageReport(Base):
    """
    Source: Car Message Report sheet
    Shift-basis column (used in dashboard Section P.1): car_msg_date_time
    """
    __tablename__ = "dr_exp_car_message_report"

    id = Column(Integer, primary_key=True, index=True)

    sl_no = Column(Integer, nullable=True)
    awb_no = Column(String, nullable=True, index=True)              # -> P.1 #Airway Bill Count
    origin = Column(String, nullable=True)
    destination = Column(String, nullable=True)
    sb_no = Column(String, nullable=True)
    sb_date = Column(Date, nullable=True)
    hwb_no = Column(String, nullable=True)
    pcs = Column(Integer, nullable=True)                            # -> P.1 #Piece Count
    gross_wgt = Column(Float, nullable=True)                        # -> P.1 #Weight (Gross Wgt)
    volumetric_wgt = Column(Float, nullable=True)                   # VOLUMETRIC WT
    chg_wgt = Column(Float, nullable=True)                          # CHG WT
    nog = Column(String, nullable=True)
    shc = Column(String, nullable=True)

    car_msg_date_time = Column(DateTime, nullable=True, index=True)  # <-- SHIFT BASIS (P.1)

    uploaded_at = Column(DateTime, default=datetime.utcnow)
    uploaded_by = Column(Integer, nullable=True)
    report_date = Column(Date, nullable=False, index=True) # Ye batayega ki ye data kis din ka hai