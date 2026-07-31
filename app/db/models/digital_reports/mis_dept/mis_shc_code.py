from sqlalchemy import Column, DateTime, Integer, String, func
from app.db.base import Base  

class DigitalMisShcMaster(Base):
    __tablename__ = "dr_mis_shc_master"

    id = Column(Integer, primary_key=True, index=True)
    shc = Column(String, nullable=False, index=True)  
    final_shc = Column(String, nullable=False)       



    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<DigitalMisShcMaster(shc='{self.shc}', final_shc='{self.final_shc}')>"