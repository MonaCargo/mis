







# # app/models/import_release_report.py==================================================

# from sqlalchemy import Column, Integer, String, DateTime, Float, Text, Index, Boolean
# from sqlalchemy.sql import text
# from app.db.base import Base


# class ImportReleaseReport(Base):
#     __tablename__ = "import_release_report"

#     # Primary Key
#     id = Column(Integer, primary_key=True, index=True)
    
#     # Date and Agent Information
#     date = Column(DateTime(timezone=True), nullable=True)
#     agent = Column(String(255), nullable=True, index=True)
    
#     # Consignee Information
#     consignee = Column(String(500), nullable=True, index=True)
#     consignee_address = Column(Text, nullable=True)
#     state = Column(String(100), nullable=True)
    
#     # Consolidator and AWB Details
#     consolidator = Column(String(255), nullable=True)
#     awb = Column(String(50), nullable=False, index=True)
#     hwb = Column(String(50), nullable=True, index=True)
    
#     # BOE and OC Numbers
#     boe_num = Column(String(50), nullable=True, index=True)
#     oc_num = Column(String(50), nullable=True, index=True)
    
#     # Origin and Shipment Details
#     org = Column(String(10), nullable=True)
#     pcs = Column(Integer, nullable=True)
#     grg_wt = Column(Float, nullable=True)
#     chg_wt = Column(Float, nullable=True)
#     nog = Column(String(500), nullable=True)
#     shc = Column(String(100), nullable=True)
    
#     # Flight Information
#     flight_no = Column(String(20), nullable=True, index=True)
#     flight_date = Column(DateTime(timezone=True), nullable=True, index=True)
    
#     # Segregation Details (Store both individual and combined)
#     segregation_date = Column(DateTime(timezone=True), nullable=True)
#     segregation_time = Column(String(20), nullable=True)
#     segregation_datetime = Column(DateTime(timezone=True), nullable=True, index=True)  # Combined
    
#     # DO and SDO Numbers
#     do_num = Column(String(50), nullable=True)
#     sdo_num = Column(String(50), nullable=True)
    
#     # Integration and System Details
#     integration_mode = Column(String(50), nullable=True)
#     cosys_id = Column(String(50), nullable=True)
    
#     # Pick Order Details
#     pick_order_recd_datetime = Column(DateTime(timezone=True), nullable=True)
#     pick_order_end_datetime = Column(DateTime(timezone=True), nullable=True)
    
#     # Gate Pass Information (Store both individual and combined)
#     gate_pass_no = Column(String(50), nullable=True, index=True)
#     gate_pass_issued_date = Column(DateTime(timezone=True), nullable=True)
#     gate_pass_issued_time = Column(String(20), nullable=True)
#     gate_pass_issued_datetime = Column(DateTime(timezone=True), nullable=True, index=True)  # Combined
#     gate_pass_recd_datetime = Column(DateTime(timezone=True), nullable=True)
#     gate_pass_end_datetime = Column(DateTime(timezone=True), nullable=True)
#     gate_pass_released_by = Column(String(255), nullable=True)
    
#     # Delivery Details
#     actual_dlv_datetime = Column(DateTime(timezone=True), nullable=True)
#     truck_load_datetime = Column(DateTime(timezone=True), nullable=True)
#     ata = Column(DateTime(timezone=True), nullable=True)
#     flight_complete_datetime = Column(DateTime(timezone=True), nullable=True)
    
#     # Delivered To Information
#     delivered_to = Column(String(255), nullable=True)
#     dlv_id_typ = Column(String(50), nullable=True)
#     dlv_id_no = Column(String(50), nullable=True)
    
#     # CHA Details
#     cha_id = Column(String(50), nullable=True)
    
#     # Manual BOE Entry Details
#     manually_boe_user = Column(String(255), nullable=True)
#     manually_boe_datetime = Column(DateTime(timezone=True), nullable=True)
#     manual_boe_approval_user = Column(String(255), nullable=True)
#     manual_boe_approval_datetime = Column(DateTime(timezone=True), nullable=True)
    
#     # Manual OC Entry Details
#     manually_oc_user = Column(String(255), nullable=True)
#     manually_oc_datetime = Column(DateTime(timezone=True), nullable=True)
#     manual_oc_approval_user = Column(String(255), nullable=True)
#     manual_oc_approval_datetime = Column(DateTime(timezone=True), nullable=True)
    
#     # Delivery Zone and Contact
#     dlv_zone = Column(String(100), nullable=True)
#     mobile_number = Column(String(20), nullable=True)
    
#     # Online/Counter Flag
#     online_counter = Column(String(20), nullable=True)
    
#     # Location Pieces
#     location_pcs = Column(String(255), nullable=True)
    
#     # Timestamps (UTC)
#     created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
#     updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))
    
#     # Composite Indexes
#     __table_args__ = (
#         Index('idx_awb_hwb', 'awb', 'hwb'),
#         Index('idx_awb_boe', 'awb', 'boe_num'),
#         Index('idx_awb_oc', 'awb', 'oc_num'),
#         Index('idx_flight_date', 'flight_no', 'flight_date'),
#         Index('idx_segregation_datetime', 'segregation_datetime'),
#         Index('idx_gate_pass_issued_datetime', 'gate_pass_issued_datetime'),
#     )


    




from datetime import datetime, timezone
from sqlalchemy import Column, Date, String, Integer, Float, DateTime, Text, Index, UniqueConstraint, text

from app.db.base import Base


def utc_now():
    """Return current UTC time for onupdate"""
    return datetime.now(timezone.utc)


class IrrReport(Base):
    __tablename__ = 'irr_report'
    
    # Primary Key
    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    
    # Date/Time Fields (all UTC timezone-aware)
    date = Column(DateTime(timezone=True), nullable=True)
    flight_date = Column(DateTime(timezone=True), nullable=True)
    segregation_date = Column(DateTime(timezone=True), nullable=True)
    pick_order_recd_date_time = Column(DateTime(timezone=True), nullable=True)
    pick_order_end_date_time = Column(DateTime(timezone=True), nullable=True)
    gate_pass_issued_date = Column(DateTime(timezone=True), nullable=True)
    gate_pass_recd_date_time = Column(DateTime(timezone=True), nullable=True)
    gate_pass_end_date_time = Column(DateTime(timezone=True), nullable=True)
    actual_dlv_date_time = Column(DateTime(timezone=True), nullable=True)
    truck_load_date_time = Column(DateTime(timezone=True), nullable=True)
    ata = Column(DateTime(timezone=True), nullable=True)
    flight_complete_date_time = Column(DateTime(timezone=True), nullable=True)
    manually_boe_date_time = Column(DateTime(timezone=True), nullable=True)
    manual_boe_approval_date_time = Column(DateTime(timezone=True), nullable=True)
    manually_oc_date_time = Column(DateTime(timezone=True), nullable=True)
    manual_oc_approval_date_time = Column(DateTime(timezone=True), nullable=True)
    
    # Time-only fields (stored as String since they don't have dates)
    segregation_time = Column(String(20), nullable=True)
    gate_pass_issued_time = Column(String(20), nullable=True)
    
    # String Fields
    agent = Column(String(200), nullable=True)
    consignee = Column(String(600), nullable=True)
    consignee_address = Column(Text, nullable=True)
    state = Column(String(100), nullable=True)
    consolidator = Column(String(300), nullable=True)
    awb = Column(String(100), nullable=True, index=True)
    hwb = Column(String(100), nullable=True, index=True)
    boe_num = Column(String(100), nullable=True, index=True)
    oc_num = Column(String(100), nullable=True, index=True)
    org = Column(String(200), nullable=True)
    nog = Column(String(200), nullable=True)
    shc = Column(String(100), nullable=True)
    flight_no = Column(String(50), nullable=True)
    do_num = Column(String(100), nullable=True)
    sdo_num = Column(String(100), nullable=True)
    integration_mode = Column(String(100), nullable=True)
    cosys_id = Column(String(100), nullable=True)
    gate_pass_no = Column(String(100), nullable=True)
    gate_pass_released_by = Column(String(200), nullable=True)
    delivered_to = Column(String(200), nullable=True)
    dlv_id_typ = Column(String(50), nullable=True)
    dlv_id_no = Column(String(100), nullable=True)
    cha_id = Column(String(100), nullable=True)
    manually_boe_user = Column(String(200), nullable=True)
    manual_boe_approval_user = Column(String(200), nullable=True)
    manually_oc_user = Column(String(200), nullable=True)
    manual_oc_approval_user = Column(String(200), nullable=True)
    dlv_zone = Column(String(100), nullable=True)
    mobile_number = Column(String(20), nullable=True)
    online_counter = Column(String(50), nullable=True)
    location_pcs = Column(Text, nullable=True)
    
    # Numeric Fields
    pcs = Column(Integer, nullable=True)
    grg_wt = Column(Float, nullable=True)
    chg_wt = Column(Float, nullable=True)
    
    # For tracing the user and report date 
    cosys_report_date = Column(Date,nullable=False, index=True)  # Here we store only Date without timezone 
    uploaded_by = Column(String, index=True,nullable=False) 


    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))

    __table_args__ = (
        UniqueConstraint('oc_num', name='uq_irr_report_oc_num'),
       
    )

# Composite indexes for better query performance
Index('idx_irr_awb_date', IrrReport.awb, IrrReport.date)
Index('idx_irr_hwb_date', IrrReport.hwb, IrrReport.date)
Index('idx_irr_boe_oc', IrrReport.boe_num, IrrReport.oc_num)
Index('idx_irr_flight_date', IrrReport.flight_no, IrrReport.flight_date)
Index('idx_irr_consolidator_date', IrrReport.consolidator, IrrReport.date)











