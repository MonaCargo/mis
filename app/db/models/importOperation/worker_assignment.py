# # app/models/worker_assignment.py
# from sqlalchemy import (
#     Column, Index, Integer, String, Float, DateTime, Boolean, Text,
#     UniqueConstraint, func, text
# )
# from app.db.base import Base


# class WorkerAssignment(Base):
#     __tablename__ = "import_worker_assignment"

#     id = Column(Integer, primary_key=True, autoincrement=True)

#     # ---- COPY OF MERGE TABLE FIELDS ----
#     igp_no = Column(String(50))
#     igp_print_date_time = Column(DateTime(timezone=True))
#     flight_no = Column(String(20))
#     awb_no = Column(String(30),index=True)
#     hawb = Column(String(50),index=True)
#     flight_date = Column(DateTime(timezone=True))
#     no_of_pc = Column(Integer)
#     weight_in_kgs = Column(Float)
#     chg_wgt_in_kg = Column(Float)
#     location = Column(Text)
#     oc_no = Column(String(50), index=True)
#     irregularity_remarks = Column(Text)
#     pd_in_time = Column(DateTime(timezone=True))
#     no_of_pc_recd = Column(Integer)
#     verified_by = Column(String(300))
#     agent_name = Column(String(500))
#     customer_name = Column(String(250))
#     release_zone = Column(String(100))
#     is_printed = Column(Boolean, default=False)
#     shc = Column(String(100))
#     irr_codes = Column(String(500))
#     integrate_date_time = Column(DateTime(timezone=True), index=True)

#     # New fields for in worker assignment model which add new in oc merge for temp irm oc
#     temp_irm_oc_no = Column(String(50),nullable=True) # it is temporary oc no. fast track oc no.
#     is_temp_irm_oc = Column(Boolean, default=False)  # To identify temp IRM OCs



#     # ---- EXTRA FIELDS ----
#     gate_pass_no = Column(String(200), index=True)
#     gate_pass_issued_date_time_combo = Column(DateTime(timezone=True), nullable=True,index=True) # here I take actual date and add our start time  
#     gate_pass_end_datetime = Column(DateTime(timezone=True), nullable=True)
#     from_irr_table = Column(Boolean,default=False)

#     assigned_person = Column(String(100),index=True,default=None,nullable=True) # it store emp_id

#     assigned_person_datetime= Column(DateTime(timezone=True))
#     drop_dlv_zone = Column(String(100))
#     drop_dlv_zone_datetime = Column(DateTime(timezone=True),nullable=True,default=None)


#     created_at = Column(DateTime(timezone=True), nullable=False)
#     updated_at = Column(DateTime(timezone=True), nullable=False )

#     __table_args__ = (
#         UniqueConstraint("oc_no", name="uq_import_worker_assignment_oc_no"),
#          Index(
#             "uq_import_worker_assignment_awb_hawb",
#             "awb_no",
#             func.coalesce(text("hawb"), ""),
#             unique=True
#         ),
#     )


# =========================================== NEW STRUCTURE two level ===========================



# 🫷🫷🫷🫷🫷=========================== NEW MULTI LEVEL STYRUCTURE ===============


# app/models/worker_assignment_header.py
from sqlalchemy import (
    Column, Float, ForeignKey, Integer, String, DateTime, Boolean, Text,
    UniqueConstraint, Index, func, text
)
from app.db.base import Base


class WorkerAssignmentHeader(Base):
    __tablename__ = "import_worker_assignment_header"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # ===============================
    # SHIPMENT IDENTITY (ALWAYS)
    # ===============================
    oc_no = Column(String(50), nullable=False)
    awb_no = Column(String(30), nullable=False)
    hawb = Column(String(50), nullable=True)  # may be NULL

    igp_no = Column(String(50))
    igp_print_date_time = Column(DateTime(timezone=True))

    # ===============================
    # TEMP IRM SUPPORT
    # ===============================
    temp_irm_oc_no = Column(String(50), nullable=True)
    is_temp_irm_oc = Column(Boolean, default=False)

    # ===============================
    # FLAGS
    # ===============================
    is_printed = Column(Boolean, default=False)
    # ⚠️
    # from_irr_table = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # 1️⃣ One OC → ONE shipment identity
        UniqueConstraint(
            "oc_no",
            name="uq_worker_assignment_header_oc_no"
        ),

         Index("idx_oc_no", "oc_no"),  # Regular index for query performance
         
        # 2️⃣ AWB + HAWB unique (NULL-safe)
        Index(
            "uq_worker_assignment_header_awb_hawb",
            "awb_no",
            func.coalesce(text("hawb"), ""),
            unique=True
        ),
    )




# app/models/worker_assignment.py

from app.db.base import Base

class WorkerAssignmentShipment(Base):
    __tablename__ = "import_worker_assignment_shipment"


    id = Column(Integer, primary_key=True, autoincrement=True)

    # ===============================
    # LINK TO SHIPMENT IDENTITY
    # ===============================
    assignment_header_id = Column(
        Integer,
        ForeignKey("import_worker_assignment_header.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    from_irr_table = Column(Boolean, default=False)

    # ===============================
    # PART SHIPMENT / EVENT DATA
    # ===============================
    no_of_pc = Column(Integer)
    no_of_pc_recd = Column(Integer)

    weight_in_kgs = Column(Float)
    chg_wgt_in_kg = Column(Float)

    flight_no = Column(String(20))
    flight_date = Column(DateTime(timezone=True))

    location = Column(Text)
    shc = Column(String(100))
    irr_codes = Column(String(500))
    irregularity_remarks = Column(Text)

    agent_name = Column(String(500))
    customer_name = Column(String(250))
    release_zone = Column(String(100))

    integrate_date_time = Column(DateTime(timezone=True), index=True)

    # ===============================
    # OPERATIONAL / ASSIGNMENT
    # ===============================
    gate_pass_no = Column(String(200), index=True)
    gate_pass_issued_date_time_combo = Column(DateTime(timezone=True))
    gate_pass_end_datetime = Column(DateTime(timezone=True))

    pd_in_time = Column(DateTime(timezone=True))
    verified_by = Column(String(300))

    assigned_person = Column(String(100), index=True)
    assigned_person_datetime = Column(DateTime(timezone=True))

    drop_dlv_zone = Column(String(100),index=True)
    drop_dlv_zone_datetime = Column(DateTime(timezone=True))

    # ===============================
    # LIFT ZONE OPERATIONS
    # ===============================

    loading_in_lift_zone = Column(String(100))
    loading_in_lift_person = Column(String(100))
    loading_in_lift_zone_datetime = Column(DateTime(timezone=True), index=True)

    unloading_from_lift_zone = Column(String(100))
    unloading_from_lift_person = Column(String(100))
    unloading_from_lift_zone_datetime = Column(DateTime(timezone=True), index=True)

    # ===============================
    # FINAL DELIVERY COLUMNS (this is lat step of shipment operation of import )
    # ===============================

    final_delivery_by_person=Column(String(30))
    final_delivery_datetime=Column(DateTime(timezone=True))
    is_final_delivered = Column(Boolean,default=False,nullable=False)


    # =========================================================================
    # It represent Damage Reeports status at WorkerAssignmentShipment level

    damage_report_status = Column(
        String(30),
        nullable=True,
        index=True
    )
    # values: open / resolved

    damage_resolve_datetime = Column(
        DateTime(timezone=True),
        nullable=True
    )

    # 🫥 ✅It is used to track when I get gatepass physically in security center
    gp_received_datetime= Column(DateTime(timezone=True))
    gp_received_by = Column(String(30), nullable=True)

    segregation_datetime = Column(DateTime(timezone=True), nullable=True) #this filed come from imp_relase_report
    boe_no = Column(String(100), nullable=True)   # 🆕 ADD THIS
    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    # truck-in truck-out datetime from imp_truck report 
    truck_in_datetime  = Column(DateTime(timezone=True), nullable=True, index=True)
    truck_out_datetime = Column(DateTime(timezone=True), nullable=True)
    truck_no = Column(String(100), nullable=True)

    __table_args__ = (
        # 🔑 for OC-merge events
        UniqueConstraint(
            "assignment_header_id",
            "integrate_date_time",
            name="uq_assignment_header_integrate_date"
        ),

        # 🔑 for IRR gate-pass events
        UniqueConstraint(
            "assignment_header_id",
            "gate_pass_no",
            name="uq_assignment_header_gate_pass"
        ),

        Index(
            "idx_worker_assignment_header_shipment_header_id",
            "assignment_header_id"
        ),

    # ===============================
    # 🚀 LIFT LOADING PERFORMANCE
    # ===============================

    Index(
        "idx_lift_loading_zone_time",
        "loading_in_lift_zone",
        "loading_in_lift_zone_datetime",
    ),

    # ===============================
    # 🚀 LIFT UNLOADING PERFORMANCE
    # ===============================

    Index(
        "idx_lift_unloading_zone_time",
        "unloading_from_lift_zone",
        "unloading_from_lift_zone_datetime",
    ),
    )


