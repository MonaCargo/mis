# models/domestic_xray.py
from sqlalchemy import Column, Index, Integer, String, DateTime, Float, Text, Boolean,UniqueConstraint, Time,text
from app.db.base import Base

class DomesticXray(Base):
    __tablename__ = 'domestic_xray_report'

    # In model, add composite unique constraint:
    __table_args__ = (
        UniqueConstraint('awb_no', 'xray_date_time', name='uq_awb_xray_datetime'),
    )
    
    id = Column(Integer, primary_key=True, autoincrement=True)
    seq_num = Column(String(8), unique=True, nullable=False, index=True)  # ADD THIS
    awb_no = Column(String(50), nullable=False)
    destination = Column(String(50), nullable=False)
    accp_date = Column(DateTime(timezone=True), nullable=True)
    merge_acceptance_date_time = Column(DateTime(timezone=True), nullable=True)
    accp_time = Column(Time, nullable=True)
    accp_pcs = Column(Integer, nullable=True)
    rej_pcs = Column(Integer, nullable=True)
    gross_weight = Column(Float, nullable=True)
    rej_gross_weight = Column(Float, nullable=True)
    chg_weight = Column(Float, nullable=True)
    shc = Column(String(100), nullable=True)
    name_of_goods = Column(Text, nullable=True)
    agent_name = Column(String(100), nullable=True)
    freighter_type = Column(String(50), nullable=True)
    xray_type = Column(String(50), nullable=True)
    phs_pcs = Column(Integer, nullable=True)
    etd_pcs = Column(Integer, nullable=True)
    eds_pcs = Column(Integer, nullable=True)
    edd_pcs = Column(Integer, nullable=True)
    vck_pcs = Column(Integer, nullable=True)
    cmd_pcs = Column(Integer, nullable=True)
    xray_date_time = Column(DateTime(timezone=True), nullable=False)
    xray_user = Column(String(100), nullable=False)
    serial_no = Column(String(100), nullable=True, index=True)
    remarks = Column(Text, nullable=True)
    
    # Additional fields
    is_pdf_generated = Column(Boolean, default=False, nullable=False)
    pdf_generated_date_time = Column(DateTime(timezone=True), nullable=True)
    is_email_sent = Column(Boolean, default=False, nullable=False)
    email_sent_date_time = Column(DateTime(timezone=True), nullable=True)
    email_sent_by = Column(String(100), nullable=True, index=True) # emp_id of dcsc employee 
    
    # For tracing the user and report date
    # cosys_report_date = Column(DateTime(timezone=True), nullable=False, index=True)
    uploaded_by = Column(String(100), nullable=False, index=True)

    retry_count = Column(Integer, default=0, nullable=False)
    email_error_message = Column(String(200), nullable=True)
    
    # Timestamps
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False )

# Create indexes
Index('idx_awb_no_domestic_xray', DomesticXray.awb_no)
# Index('idx_cosys_report_date_domestic_xray', DomesticXray.cosys_report_date)
Index('idx_uploaded_by_domestic_xray', DomesticXray.uploaded_by)


#  Model For Domestic Xray Emoployee

class DomesticXrayEmployee(Base):
    __tablename__ = "domestic_xray_employees"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    employee_id = Column(String(50), unique=True, nullable=False)
    employee_name = Column(String(100), nullable=False)
    xray_user_id = Column(String(50), nullable=True)
