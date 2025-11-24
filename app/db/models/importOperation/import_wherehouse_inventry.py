from datetime import datetime, timezone
from sqlalchemy import Column, Date, String, Integer, DateTime, Float, Text, UniqueConstraint, text, Index

from app.db.base import Base




class ImportWhereHouseInventry(Base):
    __tablename__ = 'import_wherehouse_inventry'
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    awb_no = Column(String(100), nullable=False, index=True,unique=False)
    hwb_no = Column(String(100))
    m_h = Column(String(10))  # M/H column
    origin = Column(String(100))
    destination = Column(String(100))
    warehouse_location = Column(String(200))
    status = Column(String(100))
    location_date = Column(DateTime(timezone=True),nullable=True)
    pcs = Column(Integer)
    wgt_chg = Column(Float)  
    grs_wgt = Column(Float)
    nature_of_goods = Column(Text)   

    shc = Column(String(100))
    agent = Column(String(200))
    fltno = Column(String(50))
    flt_date = Column(DateTime(timezone=True),nullable=True)
    cne_name = Column(String(200))
    cne_addr = Column(Text)

     # For tracing the user and report date 
    cosys_report_date = Column(Date,nullable=False, index=True)  # Here we store only Date without timezone 
    uploaded_by = Column(String, index=True,nullable=False) 
    
    # ✅ FIXED: Use TIMEZONE('UTC', NOW()) for UTC timestamps
    created_at = Column(
        DateTime(timezone=True), 
        server_default=text("TIMEZONE('UTC', NOW())")
    )
    updated_at = Column(
        DateTime(timezone=True), 
        server_default=text("TIMEZONE('UTC', NOW())"), 
         onupdate=lambda: datetime.now(timezone.utc) # ✅ Use Python function for updates
    )

    __table_args__ = (
        # UniqueConstraint('awb_no', 'hwb_no', name='uix_awb_hwb'),
        Index('idx_awb_status', awb_no, status),
    )

# ✅ Composite/Custom Indexes (Highly recommended)
Index('idx_awb_status', ImportWhereHouseInventry.awb_no, ImportWhereHouseInventry.status)