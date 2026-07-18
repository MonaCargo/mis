

from sqlalchemy import Column, Integer, String, DateTime, Numeric, Text,BigInteger, func , Index, Date

from app.db.base import Base


class DigitalReportExportTpXray(Base):
    
    __tablename__ = "dr_exp_tp_xray"

    # ── Surrogate PK ──────────────────────────────────────────────────────────
    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── Core operational references ───────────────────────────────────────────
    sl_no       = Column(Integer, nullable=True)
    awb_no      = Column(String(20),  nullable=False, index=True)
    origin      = Column(String(10),  nullable=False)  
    destination = Column(String(10),  nullable=False)
    
    # ── Weights & Volume ──────────────────────────────────────────────────────
    pcs         = Column(Integer, nullable=False)
    grs_wt      = Column(Numeric(12, 3), nullable=False)
    chg_wt      = Column(Numeric(12, 3), nullable=False)
    nog         = Column(Text,        nullable=True)  
    shc         = Column(String(50),  nullable=True)   

    # ── Operational Date / Time Fields ───────────────────────────────────────
    # car_msg_datetime = Column(DateTime(timezone=True), nullable=True) 
    # leo_datetime     = Column(DateTime(timezone=True), nullable=True) 
    xray_start_datetime = Column(DateTime(timezone=True), nullable=False)
    xray_end_datetime   = Column(DateTime(timezone=True), nullable=False)
    xray_type           = Column(String(50),  nullable=True) 
    xray_datetime       = Column(DateTime(timezone=True), nullable=False) 
    xray_user           = Column(String(100), nullable=True)

    # # ── Piece Status Breakdowns ───────────────────────────────────────────────
    # phs_pcs     = Column(Integer, nullable=True) 
    # etd_pcs     = Column(Integer, nullable=True) 
    # eds_pcs     = Column(Integer, nullable=True) 
    # edd_pcs     = Column(Integer, nullable=True)
    # vck_pcs     = Column(Integer, nullable=True) 
    # cmd_pcs     = Column(Integer, nullable=True) 

    # ── Handover & Logistics ─────────────────────────────────────────────────
    doc_accpt_datetime   = Column(DateTime(timezone=True), nullable=True) 
    rcs_rcf_rct_datetime = Column(DateTime(timezone=True), nullable=True) 
    uplifting_datetime   = Column(DateTime(timezone=True), nullable=True) 
    flt_no               = Column(String(20),  nullable=True)
    agent_name           = Column(String(200), nullable=True)
    serial_no            = Column(String(100), nullable=False)
    device_model_no      = Column(String(100), nullable=False)
    # remarks              = Column(Text,        nullable=True)

    # ── Upload Session Tracking ───────────────────────────────────────────────
    month_uploaded  = Column(String(7),   nullable=False, index=True)
    uploaded_at     = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    uploaded_by     = Column(String(20),  nullable=False)
    report_date = Column(Date, nullable=False, index=True)

    # ── Composite indexes for fast search optimizations ──────────────────────
    __table_args__ = (
        Index("ix_dr_exp_tp_xray_month", "month_uploaded"),
        Index("ix_dr_exp_tp_xray_awb_month", "awb_no", "month_uploaded"),
        Index("ix_dr_exp_tp_xray_dedup", "awb_no", "xray_start_datetime"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExportOperationXray id={self.id} awb_no={self.awb_no!r} "
            f"sb_no={self.sb_no!r} month={self.month_uploaded!r}>"
        )