from sqlalchemy import Column, Integer,Boolean, String,DateTime, func, text
from app.db.base import Base

class User(Base):
    __tablename__ = "users"

    id = Column(Integer, primary_key=True, index=True)
    emp_id = Column(String, unique=True, index=True) 
    name = Column(String(60))                 # ✅ no comma
    password = Column(String)                 # ✅ no comma
    role = Column(String, default="user")     # ✅ no comma
    is_active = Column(Boolean,nullable=False,server_default=text("TRUE")) # by default active

     # 🔥 Track who created this user
    created_by = Column(String, nullable=True, default=None)

       # ✅ NEW: Timestamp columns  (⚠️confirm timezone handling with your DB)
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())
