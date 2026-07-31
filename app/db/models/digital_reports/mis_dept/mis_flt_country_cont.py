from sqlalchemy import Column, Integer, String, DateTime, func
from app.db.base import Base


class DigitalMisFltCountryContinent(Base):
    """Destination-code -> Country -> Continent master data
    (source: Flt_Country___Continent.xlsx, sheet 'Flight Master Data')."""
    __tablename__ = "dr_mis_flt_country_continent"

    id = Column(Integer, primary_key=True, index=True, autoincrement=True)
    dest = Column(String(10), nullable=False, unique=True, index=True)   # e.g. 'JFK', 'LHR'
    country = Column(String(100), nullable=False, index=True)            # e.g. 'USA', 'United Kingdom'
    continent = Column(String(50), nullable=False, index=True)           # e.g. 'Americas', 'Domestic'

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), server_default=func.now())

    def __repr__(self):
        return f"<FltCountryContinent(dest='{self.dest}', country='{self.country}', continent='{self.continent}')>"
