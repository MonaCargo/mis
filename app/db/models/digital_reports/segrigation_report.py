"""
SQLAlchemy ORM models for Segregation Import data.
  - seg_flights : one row per (flight_no, flight_date)
  - seg_awbs    : one row per (flight_id, awb_no, sfx)
"""

from datetime import datetime, date
from sqlalchemy import (
    Column, Integer, String, Date, Numeric,
    DateTime, ForeignKey, UniqueConstraint, func,
)
from sqlalchemy.orm import relationship

from app.db.base import Base


class DigitalReportImportSegFlight(Base):
    __tablename__ = "dr_imp_seg_flights"

    id              = Column(Integer, primary_key=True, autoincrement=True)
    flight_no       = Column(String(20),  nullable=False)
    flight_date     = Column(Date,         nullable=False)          # DATE — no tz (And I save date direct  (I assume that in excel or csv this date alwys comes as IST) FORMATE IN DB)
    origin          = Column(String(10))
    dest            = Column(String(10))
    ata_datetime    = Column(DateTime(timezone=True))               # UTC
    flt_doc_arrival = Column(DateTime(timezone=True))               # UTC
    last_uld_arrival= Column(DateTime(timezone=True))               # UTC
    bulk_uld_arrival= Column(DateTime(timezone=True))               # UTC
    flt_com_dat_tim = Column(DateTime(timezone=True))               # UTC
    flight_status   = Column(String(30))                            # PASSENGER / FREIGHTER
    created_at      = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    awbs = relationship("DigitalReportImportSegAwb", back_populates="flight",
                        cascade="all, delete-orphan")

    __table_args__ = (
        UniqueConstraint("flight_no", "flight_date", name="uq_dr_imp_seg_flight"),
    )


class  DigitalReportImportSegAwb(Base):
    __tablename__ = "dr_imp_seg_awbs"

    id             = Column(Integer, primary_key=True, autoincrement=True)
    flight_id      = Column(Integer, ForeignKey("dr_imp_seg_flights.id", ondelete="CASCADE"),
                            nullable=False)

    awb_no         = Column(String(11),   nullable=False)   # normalised 11-digit
    sfx            = Column(String(2),    nullable=False)   # P / A / B …
    origin         = Column(String(10))
    dest           = Column(String(10))

    # ── piece / weight (stored as-is from file, kg with 2dp) ─────────────────
    manifest_pcs   = Column(Integer)
    manifest_wgt   = Column(Numeric(12, 2))
    seg_pcs        = Column(Integer)
    seg_wgt        = Column(Numeric(12, 2))
    pcs            = Column(Integer)
    gross_wgt      = Column(Numeric(12, 2))   # kg, 2 decimal places
    chg_wgt        = Column(Numeric(12, 2))
    vol_mc         = Column(Numeric(10, 4))
    no_of_houses   = Column(Integer)

    # ── reference fields ──────────────────────────────────────────────────────
    shc            = Column(String(50))
    chg_shc        = Column(String(50))
    billing_shc    = Column(String(50))
    nog            = Column(String(100))
    consignee      = Column(String(255))
    egm_igm_no     = Column(String(50))

    # ── dates (UTC) ───────────────────────────────────────────────────────────
    awd_date       = Column(DateTime(timezone=True))
    nfd_date       = Column(DateTime(timezone=True))
    rcf_date       = Column(DateTime(timezone=True))
    do_datetime    = Column(DateTime(timezone=True))
    tfd_datetime   = Column(DateTime(timezone=True))

    updated_at     = Column(DateTime(timezone=True),
                            server_default=func.now(),
                            onupdate=func.now(),
                            nullable=False)

    flight = relationship("DigitalReportImportSegFlight", back_populates="awbs")

    __table_args__ = (
        UniqueConstraint("flight_id", "awb_no", "sfx", name="uq_dr_imp_seg_awb"),
    )