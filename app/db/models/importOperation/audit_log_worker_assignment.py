# app/models/worker_assignment_audit.py

from sqlalchemy import (
    Column, Integer, String, DateTime, Text, Index
)
from sqlalchemy.sql import func
from app.db.base import Base


class WorkerAssignmentAuditLog(Base):
    __tablename__ = "audit_log_import_worker_assignment"

    id = Column(Integer, primary_key=True, autoincrement=True)

    # 🔗 Relation to main table
    worker_assignment_id = Column(Integer, index=True, nullable=False)

    # 🔍 Searchable identifiers
    oc_no = Column(String(50), index=True, nullable=False)
    awb_no = Column(String(30), index=True, nullable=True)
    hawb = Column(String(50), index=True, nullable=True)

    # 🧾 What changed
    field_name = Column(String(100), nullable=False)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)

    # 🧠 Action metadata
    db_action = Column(String(20), nullable=False)  
    # CREATE | UPDATE | DELETE

    source_action = Column(String(50), nullable=False)  
    # assign_user | dlv_zone_update | unassign | auto_assign | bulk_assign

    # 👤 Actor info
    changed_by = Column(String(100), nullable=False)  # emp_id / user_id
    changed_by_role = Column(String(50), nullable=False)
    ip_address = Column(String(45), nullable=True)    # IPv4 / IPv6
    device_id = Column(String(100),nullable=True)
    user_agent = Column(String(1024),nullable=True)


    # ⏱️ Time

    changed_at = Column(DateTime(timezone=True),nullable=False)

    created_at = Column(DateTime(timezone=True),nullable=False)
    

    __table_args__ = (
        Index("idx_audit_log_import_worker_assignment_search", "oc_no", "awb_no", "hawb"),
    )
