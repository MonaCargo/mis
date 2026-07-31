from sqlalchemy import Column, Integer, String, DateTime, func
from app.db.base import Base


class DigitalMisPdaAgent(Base):
    """PDA (agent) master data — source: GFT_PDA_details.xlsx."""
    __tablename__ = "dr_mis_pda_agent"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    agent_code = Column(String(10), nullable=False, unique=True, index=True)   # PDA CODE
    agent_name = Column(String(100), nullable=False)                          # PDA Name

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<DigitalMisPdaAgent(agent_code='{self.agent_code}', agent_name='{self.agent_name}')>"
