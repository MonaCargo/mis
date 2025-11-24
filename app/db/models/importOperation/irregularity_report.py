







# models/irregularities.py
from sqlalchemy import Column, Date, Index, Integer, String, DateTime, Float, Text, text
from sqlalchemy.ext.declarative import declarative_base
import datetime

from app.db.base import Base

class Irregularity(Base):
    __tablename__ = 'irregularity_report'
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    flt_no = Column(String(30), nullable=True)
    flt_date = Column(DateTime(timezone=True), nullable=True)
    awb_no = Column(String(50), nullable=False,index=True)
    hwb_no = Column(String(100), nullable=True)
    org = Column(String(50), nullable=True)
    dest = Column(String(50), nullable=True)
    tot_pcs = Column(Integer, nullable=True)
    tot_wgt = Column(Float, nullable=True)
    uld_number = Column(String(60), nullable=True)
    seg_date = Column(DateTime(timezone=True), nullable=True)
    agt = Column(String(50), nullable=True)
    irr_code = Column(String(50), nullable=True)
    pcs = Column(Integer, nullable=True)
    open_remarks = Column(Text, nullable=True)
    irr_open_date_time = Column(DateTime(timezone=True), nullable=True)
    irr_close_date_time = Column(DateTime(timezone=True), nullable=True)
    cosys_id = Column(String(50), nullable=True)
    closing_remarks = Column(Text, nullable=True)
    performance_irr_close_open = Column(String(50), nullable=True)
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))

     # For tracing the user and report date 
    cosys_report_date = Column(Date,nullable=False, index=True)  # Here we store only Date without timezone 
    uploaded_by = Column(String, index=True,nullable=False) 

        # Create indexes
Index('idx_hwb_no', Irregularity.hwb_no)
Index('idx_awb_no', Irregularity.awb_no)

# Optional: Composite index if you frequently query by both AWB and HWB together
Index('idx_awb_hwb', Irregularity.awb_no, Irregularity.hwb_no)
