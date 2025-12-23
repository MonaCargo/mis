from sqlalchemy import Boolean, Column, Index, String, Integer, Float, DateTime, Text, UniqueConstraint, func, text
from app.db.base import Base


class OcMergeGatePass(Base):
    __tablename__ = "oc_merge_gatepass"

    __table_args__ = (
        UniqueConstraint('oc_no', name='uq_oc_merge_gatepass_oc_no'),

        Index(
        'uq_awb_hawb',
        "awb_no",
        func.coalesce(text("hawb"), ''),
        unique=True
    ),  
     # Ensure unique AWB and HAWB combination for temp_oc_merge unique insertion 💀💀💀
    )


    id = Column(Integer, primary_key=True, autoincrement=True)
    igp_no = Column(String(50), nullable=False)
    igp_print_date_time = Column(DateTime(timezone=True), nullable=True) 
    flight_no = Column(String(20), nullable=True)
    awb_no = Column(String(30), nullable=False)
    hawb = Column(String(50), nullable=True,default=None)
    flight_date = Column(DateTime(timezone=True), nullable=True)
    no_of_pc = Column(Integer, nullable=True)
    weight_in_kgs = Column(Float, nullable=True) #  it is grass weight
    chg_wgt_in_kg = Column(Float, nullable=True)   # <--- NEW FIELD (NULLABLE)
    location = Column(Text, nullable=True)
    oc_no = Column(String(50), nullable=False)

    temp_irm_oc_no = Column(String(50), nullable=True) # it is temporary oc no. fast track oc no.
    is_temp_irm_oc = Column(Boolean, default=False, nullable=False)  # To identify temp IRM OCs

    irregularity_remarks = Column(Text, nullable=True)
    pd_in_time = Column(DateTime(timezone=True), nullable=True)
    no_of_pc_recd = Column(Integer, nullable=True)
    verified_by = Column(String(300), nullable=True)
    agent_name = Column(String(500), nullable=True)
    customer_name = Column(String(250), nullable=True)
    release_zone = Column(String(100), nullable=True)
    is_printed = Column(Boolean, default=False, nullable=False)
    # ✅ Add this new column
    shc = Column(String(100), nullable=True, index=True)
    irr_codes = Column(String(500), nullable=True)  # ✅ NEW FIELD
     # ✅ Add this new column
    

    created_at = Column(
        DateTime(timezone=True),
        # server_default=text("TIMEZONE('UTC', NOW())")
    )
    updated_at = Column(
        DateTime(timezone=True),
        # server_default=text("TIMEZONE('UTC', NOW())"),
        # onupdate=func.timezone('utc', func.now())  # Changed this line
    )

    # 🆕 AUDIT FIELDS (it give which process and  when is get by created at)
    uploaded_by = Column(String(100), nullable=True, default=None)  # emp_id 

    integrate_date_time = Column(DateTime(timezone=True), nullable=True,index=True)  # ✅ NEW FIELD


    
     
  
