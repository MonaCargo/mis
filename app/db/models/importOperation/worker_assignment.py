# app/models/worker_assignment.py
from sqlalchemy import (
    Column, Index, Integer, String, Float, DateTime, Boolean, Text,
    UniqueConstraint, func, text
)
from app.db.base import Base


class WorkerAssignment(Base):
    __tablename__ = "import_worker_assignment"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ---- COPY OF MERGE TABLE FIELDS ----
    igp_no = Column(String(50))
    igp_print_date_time = Column(DateTime(timezone=True))
    flight_no = Column(String(20))
    awb_no = Column(String(30),index=True)
    hawb = Column(String(50),index=True)
    flight_date = Column(DateTime(timezone=True))
    no_of_pc = Column(Integer)
    weight_in_kgs = Column(Float)
    chg_wgt_in_kg = Column(Float)
    location = Column(Text)
    oc_no = Column(String(50), index=True)
    irregularity_remarks = Column(Text)
    pd_in_time = Column(DateTime(timezone=True))
    no_of_pc_recd = Column(Integer)
    verified_by = Column(String(300))
    agent_name = Column(String(500))
    customer_name = Column(String(250))
    release_zone = Column(String(100))
    is_printed = Column(Boolean, default=False)
    shc = Column(String(100))
    irr_codes = Column(String(500))
    integrate_date_time = Column(DateTime(timezone=True), index=True)

    # New fields for in worker assignment model which add new in oc merge for temp irm oc
    temp_irm_oc_no = Column(String(50),nullable=True) # it is temporary oc no. fast track oc no.
    is_temp_irm_oc = Column(Boolean, default=False)  # To identify temp IRM OCs



    # ---- EXTRA FIELDS ----
    gate_pass_no = Column(String(200), index=True)
    gate_pass_issued_date_time_combo = Column(DateTime(timezone=True), nullable=True,index=True) # here I take actual date and add our start time  
    gate_pass_end_datetime = Column(DateTime(timezone=True), nullable=True)
    from_irr_table = Column(Boolean,default=False)

    assigned_person = Column(String(100),index=True,default=None,nullable=True) # it store emp_id

    assigned_person_datetime= Column(DateTime(timezone=True))
    drop_dlv_zone = Column(String(100))
    drop_dlv_zone_datetime = Column(DateTime(timezone=True),nullable=True,default=None)


    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False )

    __table_args__ = (
        UniqueConstraint("oc_no", name="uq_import_worker_assignment_oc_no"),
         Index(
            "uq_import_worker_assignment_awb_hawb",
            "awb_no",
            func.coalesce(text("hawb"), ""),
            unique=True
        ),
    )