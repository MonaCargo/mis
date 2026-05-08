from sqlalchemy import (
    BigInteger, Column, DateTime, Float, Index,
    Integer, String, UniqueConstraint,
)

from app.db.base import Base


class ExportTranshipmentReport(Base):
    """
    Stores Export Transhipment Report rows (TRM / TPV Billing SHC only).

    Unique key: (awb_no, flight_no, flight_date, trm_no)
    Month-level upsert: all rows for month_uploaded are deleted and
    re-inserted on each upload.
    """
    __tablename__ = "export_transhipment_report"

    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── AWB ───────────────────────────────────────────────────────────────────
    awb_no               = Column(String(12),  nullable=False)

    # ── Pieces / weight ───────────────────────────────────────────────────────
    pcs                  = Column(Integer,     nullable=True)
    gross_wgt            = Column(Float,       nullable=True)
    rec_pcs              = Column(Integer,     nullable=True)
    received_wgt         = Column(Float,       nullable=True)
    received_chg_wgt     = Column(Float,       nullable=True)

    # ── SHC / billing ─────────────────────────────────────────────────────────
    shc                  = Column(String(50),  nullable=True)
    billing_shc          = Column(String(10),  nullable=False)   # TRM or TPV

    # ── Cargo details ─────────────────────────────────────────────────────────
    commodity            = Column(String(100), nullable=True)
    org                  = Column(String(5),   nullable=True)
    des                  = Column(String(5),   nullable=True)

    # ── DOC acceptance ────────────────────────────────────────────────────────
    doc_datetime         = Column(DateTime(timezone=True), nullable=True)   # DOC DATE & TIME

    # ── Export TP segment ─────────────────────────────────────────────────────
    exp_tp_seg_flight_no = Column(String(20),  nullable=True)               # EXP TP SEG FLIGHT No.
    exp_tp_flight_date   = Column(DateTime(timezone=True), nullable=True)   # EXP TP FLIGHT DATE (midnight IST→UTC)
    exp_tp_seg_datetime  = Column(DateTime(timezone=True), nullable=True)   # EXP TP SEG No DATE AND TIME

    # ── TRM ───────────────────────────────────────────────────────────────────
    trm_no               = Column(Integer,     nullable=True)               # TRM NO (numeric ID)
    trm_date             = Column(DateTime(timezone=True), nullable=True)   # TRM DATE (midnight IST→UTC)

    # ── X-Ray (merged DATE + TIME) ────────────────────────────────────────────
    xray_datetime        = Column(DateTime(timezone=True), nullable=True)   # XRAY DATETIME

    # ── Ramp transfer ─────────────────────────────────────────────────────────
    ramp_transfer_datetime = Column(DateTime(timezone=True), nullable=True) # RAMP TRANSFER DATE/TIME
    ramp_transfer_remark   = Column(String(200), nullable=True)
    ramp_transfer_user     = Column(String(100), nullable=True)

    # ── Flight ────────────────────────────────────────────────────────────────
    airline_cd           = Column(String(5),   nullable=True)
    flight_no            = Column(String(20),  nullable=True)
    flight_date          = Column(DateTime(timezone=True), nullable=True)   # midnight IST→UTC
    uld_load             = Column(DateTime(timezone=True), nullable=True)   # ULD LOAD
    departure_datetime   = Column(DateTime(timezone=True), nullable=True)   # DEPARTURE DATE & TIME

    # ── Upload metadata ───────────────────────────────────────────────────────
    month_uploaded       = Column(String(7),   nullable=False, index=True)  # "YYYY-MM"
    uploaded_at          = Column(DateTime(timezone=True), nullable=False)

    __table_args__ = (
        # Same AWB can appear on multiple TRM numbers (part-shipment legs)
        # UniqueConstraint(
        #     "awb_no", "flight_no", "flight_date", "trm_no",
        #     name="uq_export_trship_awb_flight_trm",
        # ),
        Index("ix_export_trship_month",   "month_uploaded"),
        Index("ix_export_trship_awb",     "awb_no"),
        Index("ix_export_doc_datetime",  "doc_datetime"),
        # Index("ix_export_trship_trm",     "trm_no"),
    )

    def __repr__(self):
        return (
            f"<ExportTranshipmentReport "
            f"awb={self.awb_no} flight={self.flight_no} "
            f"trm_no={self.trm_no} billing_shc={self.billing_shc}>"
        )