from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey
)
from sqlalchemy.sql import func
from app.db.base import Base

# This is organization whole employee/user audit log table 

class UserAuditLog(Base):
    __tablename__ = "audit_log_user"

    id = Column(Integer, primary_key=True)

    user_id = Column(Integer, ForeignKey("users.id", ondelete="CASCADE"), index=True)

    field_name = Column(String(50), nullable=False)

    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)

    changed_by = Column(String, nullable=True)   # emp_id / username
    changed_by_role = Column(String, nullable=True)

    # 🧠 Action metadata
    db_action = Column(String(20), nullable=False)  
    # CREATE | UPDATE | DELETE

    source_action = Column(String(50), nullable=False)  

    ip_address = Column(String(45), nullable=True)   # IPv4 + IPv6
    user_agent = Column(Text, nullable=True)
    device_id = Column(String(36), nullable=True)

    changed_at = Column(DateTime(timezone=True), server_default=func.now())
    created_at = Column(DateTime(timezone=True), server_default=func.now())
