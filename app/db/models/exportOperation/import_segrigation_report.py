from sqlalchemy import (
    Column, Date, String, Integer, Float, BigInteger,
    DateTime, Text, Index, UniqueConstraint,
)

from app.db.base import Base



class ImportSegregationReport(Base):
    """
    Stores Import Segregation Report rows.
    Only TRM / TPV Billing SHC rows are saved.
    Keyed by (awb_no, sfx, flight_no, flight_date) to handle
    part-shipments (same AWB, different SFX or flight leg).
    Month-level upsert: all rows for a month are deleted and re-inserted
    on each upload.
    """
    __tablename__ = "import_segregation_report"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── Flight identifiers ────────────────────────────────────────────────────
    flight_no           = Column(String(20),  nullable=True)
    flight_date         = Column(DateTime(timezone=True), nullable=True)   # midnight IST → UTC

    # ── AWB ───────────────────────────────────────────────────────────────────
    awb_no              = Column(String(12),  nullable=False)
    sfx                 = Column(String(4),   nullable=True)               # P / A suffix

    # ── Arrival timestamps ────────────────────────────────────────────────────
    ata_datetime        = Column(DateTime(timezone=True), nullable=True)   # ATA_Date/Time
    flt_doc_arrival     = Column(DateTime(timezone=True), nullable=True)   # FLT DOC Arrival_Date/Time
    last_uld_arrival    = Column(DateTime(timezone=True), nullable=True)   # Last ULD Arrival Date & Time
    bulk_uld_arrival    = Column(DateTime(timezone=True), nullable=True)   # Bulk ULD Arrival Date & Time

    # ── Routing ───────────────────────────────────────────────────────────────
    org                 = Column(String(5),   nullable=True)
    dest                = Column(String(5),   nullable=True)

    # ── Weight / pieces ───────────────────────────────────────────────────────
    manifest_pcs        = Column(Integer,     nullable=True)
    manifest_wgt        = Column(Float,       nullable=True)
    seg_pcs             = Column(Integer,     nullable=True)
    seg_wgt             = Column(Float,       nullable=True)
    pcs                 = Column(Integer,     nullable=True)
    gross_wgt           = Column(Float,       nullable=True)
    chg_wgt             = Column(Float,       nullable=True)
    vol_mc              = Column(Float,       nullable=True)
    no_of_houses        = Column(Integer,     nullable=True)

    # ── SHC / billing ─────────────────────────────────────────────────────────
    shc                 = Column(String(50),  nullable=True)
    chg_shc             = Column(String(20),  nullable=True)
    billing_shc         = Column(String(10),  nullable=False)              # TRM or TPV

    # ── Cargo details ─────────────────────────────────────────────────────────
    nog                 = Column(String(100), nullable=True)
    consignee_details   = Column(String(100), nullable=True)

    # ── Key operational dates ─────────────────────────────────────────────────
    awd_date            = Column(DateTime(timezone=True), nullable=True)
    nfd_date            = Column(DateTime(timezone=True), nullable=True)
    rcf_date            = Column(DateTime(timezone=True), nullable=True)
    do_datetime         = Column(DateTime(timezone=True), nullable=True)
    tfd_datetime        = Column(DateTime(timezone=True), nullable=True)

    # ── Flight metadata ───────────────────────────────────────────────────────
    egm_igm_no          = Column(String(20),  nullable=True)
    flt_com_datetime    = Column(DateTime(timezone=True), nullable=True)
    flight_status       = Column(String(20),  nullable=True)

    # ── Upload metadata ───────────────────────────────────────────────────────
    month_uploaded      = Column(String(7),   nullable=False, index=True)  # "YYYY-MM"
    report_date = Column(Date, nullable=False, index=True)  # plain DATE, no tz (it repesent that day uploade data)
    uploaded_at         = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # Composite unique: same AWB + SFX (P/A) on same flight
        # UniqueConstraint(
        #     "awb_no", "sfx", "flight_no", "flight_date",
        #     name="uq_seg_report_awb_sfx_flight",
        # ),
        Index("ix_seg_report_month", "month_uploaded"),
        Index("ix_seg_report_awb",   "awb_no"),
        # Index("ix_seg_report_flight","flight_no", "flight_date"),
        Index("ix_flt_doc_arrival","flt_doc_arrival"),
    )

    def __repr__(self):
        return (
            f"<ImportSegregationReport "
            f"awb={self.awb_no} sfx={self.sfx} "
            f"flight={self.flight_no} billing_shc={self.billing_shc}>"
        )