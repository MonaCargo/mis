from sqlalchemy import Column, Integer, String, DateTime, func
from app.db.base import Base

class DigitalMisInternationalCode(Base):
    __tablename__ = "dr_mis_international_codes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)      # e.g., 'RAI', 'JNB'
    city = Column(String(100), nullable=False)                 # e.g., 'Cape Town'
    country = Column(String(100), nullable=False, index=True)  # e.g., 'South Africa'
    continent = Column(String(50), nullable=False)             # e.g., 'Africa'
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<InternationalCode(code='{self.code}', city='{self.city}', country='{self.country}')>"