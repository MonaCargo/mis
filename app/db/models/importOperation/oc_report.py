


from datetime import datetime, timezone
from sqlalchemy import Column, Date, String, Integer, DateTime, Text, Index, func, text

from app.db.base import Base


class OcReport(Base):
    __tablename__ = 'oc_report'
    
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    msg_id = Column(String(400), nullable=True)
    awb_no = Column(String(100), nullable=True, index=True)
    hawb_no = Column(String(100), nullable=True,index=True)
    oc_no = Column(String(100), nullable=False,unique=True)
    boe_no = Column(String(100), nullable=True)
    pcs = Column(Integer, nullable=True)
    integrate_date_time = Column(DateTime(timezone=True), nullable=False)

   
    
        # ✅ Use CURRENT_TIMESTAMP AT TIME ZONE 'UTC' for explicit UTC
  # ✅ Use func.now() - SQLAlchemy's database-agnostic UTC function
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))

     # For tracing the user and report date 
    cosys_report_date = Column(Date,nullable=False, index=True) # Here we store only Date without timezone (which come from frontend IST date only)

    uploaded_by = Column(String, index=True,nullable=False) 

# ✅ Composite indexes for better query performance
Index('idx_awb_integrate_date', OcReport.awb_no, OcReport.integrate_date_time)
Index('idx_msg_id_awb', OcReport.msg_id, OcReport.awb_no)


Index('idx_oc_no', OcReport.oc_no)
Index('idx_integrate_date_time', OcReport.integrate_date_time)