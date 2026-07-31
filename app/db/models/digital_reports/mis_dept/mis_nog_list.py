from sqlalchemy import Column, Integer, String, DateTime
from sqlalchemy.sql import func
from app.db.base import Base

class DigitalMisNogMaster(Base):
    __tablename__ = "dr_mis_nog_master"

    id = Column(Integer, primary_key=True, index=True)
    nog = Column(String, nullable=False, index=True)   # e.g., CONSOLIDATED
    nog_1 = Column(String, nullable=True)                          # e.g., CONSOL
    nog_2 = Column(String, nullable=True)                          # e.g., CONSOL

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<DigitalMisNogMaster(nog='{self.nog}', nog_1='{self.nog_1}', nog_2='{self.nog_2}')>"