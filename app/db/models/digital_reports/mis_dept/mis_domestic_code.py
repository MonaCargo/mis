from sqlalchemy import Column, Integer, String, DateTime, func
from app.db.base import Base

class DigitalMisDomesticCode(Base):
    __tablename__ = "dr_mis_domestic_codes"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    code = Column(String(10), nullable=False, index=True)         # Code (e.g., 'AMD', 'AGX')
    # icao = Column(String(10), nullable=True, index=True)          # e.g., 'VAAH', 'VOAT'
    airport_name = Column(String(150), nullable=False)            # e.g., 'Ahmedabad Airport'
    city = Column(String(100), nullable=False, index=True)        # e.g., 'Ahmedabad'
    
    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<DigitalMisDomesticCode(code='{self.code}', city='{self.city}')>"