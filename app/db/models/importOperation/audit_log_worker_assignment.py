# # app/models/worker_assignment_audit.py

# from sqlalchemy import (
#     Column, Integer, String, DateTime, Text, Index
# )
# from sqlalchemy.sql import func
# from app.db.base import Base


# class WorkerAssignmentAuditLog(Base):
#     __tablename__ = "audit_log_import_worker_assignment"

#     id = Column(Integer, primary_key=True, autoincrement=True)

#     # 🔗 Relation to main table
#     worker_assignment_id = Column(Integer, index=True, nullable=False)

#     # 🔍 Searchable identifiers
#     oc_no = Column(String(50), index=True, nullable=False)
#     awb_no = Column(String(30), index=True, nullable=True)
#     hawb = Column(String(50), index=True, nullable=True)

#     # 🧾 What changed
#     field_name = Column(String(100), nullable=False)
#     old_value = Column(Text, nullable=True)
#     new_value = Column(Text, nullable=True)

#     # 🧠 Action metadata
#     db_action = Column(String(20), nullable=False)  
#     # CREATE | UPDATE | DELETE

#     source_action = Column(String(50), nullable=False)  
#     # assign_user | dlv_zone_update | unassign | auto_assign | bulk_assign

#     # 👤 Actor info
#     changed_by = Column(String(100), nullable=False)  # emp_id / user_id
#     changed_by_role = Column(String(50), nullable=False)
#     ip_address = Column(String(45), nullable=True)    # IPv4 / IPv6
#     device_id = Column(String(100),nullable=True)
#     user_agent = Column(String(1024),nullable=True)


#     # ⏱️ Time

#     changed_at = Column(DateTime(timezone=True),nullable=False)

#     created_at = Column(DateTime(timezone=True),nullable=False)
    

#     __table_args__ = (
#         Index("idx_audit_log_import_worker_assignment_search", "oc_no", "awb_no", "hawb"),
#     )











# ================================== NEW ARCHITECTURE LOG VIEW  V2==========================


# app/models/worker_assignment_audit.py

from sqlalchemy import Column, Integer, String, DateTime, Text, Index, func
from app.db.base import Base


class WorkerAssignmentAuditLog(Base):
    __tablename__ = "audit_log_import_worker_assignment_v2"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 🔗 Explicit relations (NEW ARCH)
    header_id = Column(Integer, index=True, nullable=False)
    shipment_id = Column(Integer, index=True, nullable=False)

    # 🔍 Searchable identifiers (denormalized)
    oc_no = Column(String(100), index=True, nullable=False)
    awb_no = Column(String(30), index=True, nullable=True)
    hawb = Column(String(50), index=True, nullable=True)
    gate_pass_no = Column(String(200), index=True, nullable=True) # it is not used in search or process b/c it is optional

    # 🧾 What changed
    field_name = Column(String(100), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)

    # 🧠 Action metadata
    db_action = Column(String(20), nullable=False)
    source_action = Column(String(50), nullable=False)

    # 👤 Actor info
    changed_by = Column(String(100), nullable=False)
    changed_by_role = Column(String(50), nullable=False)
    ip_address = Column(String(45), nullable=True)
    device_id = Column(String(100), nullable=True)
    user_agent = Column(String(1024), nullable=True)

    # ⏱️ Time
    changed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

    # It define that for which theis shipment log happen (IRM/OC_MERGE/IRR ORIGINATED SOURCE)
    origin_source_type = Column(String(30),nullable=True,default=None)

    __table_args__ = (
        # Index(
        #     "idx_audit_log_worker_assignment_search_v2",
        #     "oc_no",
        #     "awb_no",
        #     "hawb",
        #     "gate_pass_no"
        # ),

         # Individual indexes
        Index("idx_audit_log_worker_assignment_oc", "oc_no"),
        Index("idx_audit_log_worker_assignment_header", "header_id"),

        # Composite index for awb_no + optional hawb
        Index(
            "idx_audit_log_worker_assignment_awb_hawb",
            "awb_no",
            func.coalesce("hawb", "")
        ),
    )
