"""
models/export_tp_xray.py

SQLAlchemy ORM model for the Export TP X-RAY report.

Column naming convention
────────────────────────
Report column              → DB column
-------------------------------------------------
AWB NO.                    → awb_no
ORGIN                      → origin          (note: intentional typo kept from source)
DESTINATION                → destination
PCS.                       → pcs
GROSS WT                   → grs_wt
CHG WT                     → chg_wt
NOG                        → nog
SHC                        → shc
X-RAY START DATE & TIME    → xray_start_datetime
X-RAY END DATE & TIME      → xray_end_datetime
X-RAY TYPE                 → xray_type
X-RAY DT/TIME              → xray_datetime
X-RAY-USER                 → xray_user
DOC ACCPT DT/ TIME         → doc_accpt_datetime
RCS/RCF/RCT DT/TIME        → rcs_rcf_rct_datetime
UPLIFTING DT/TIME          → uplifting_datetime
FLT NO                     → flt_no
AGENT NAME                 → agent_name
DEVICE MODEL NO.           → device_model_no
(derived)                  → month_uploaded   ← "YYYY-MM" of the report FROM DATE
(derived)                  → uploaded_at      ← UTC timestamp of this upload session
(auto)                     → id               ← surrogate PK
"""

from sqlalchemy import (
    BigInteger, Column, DateTime, Integer,
    Numeric, String, Text, Index
)
from sqlalchemy.orm import DeclarativeBase
from sqlalchemy.sql import func

from app.db.base import Base


class ExportTpXray(Base):
    __tablename__ = "export_tp_xray"

    # ── Surrogate PK ──────────────────────────────────────────────────────────
    id = Column(BigInteger, primary_key=True, autoincrement=True)

    # ── Core shipment fields ──────────────────────────────────────────────────
    awb_no          = Column(String(20),  nullable=False, index=True)
    origin          = Column(String(10),  nullable=True)   # source spells it ORGIN
    destination     = Column(String(10),  nullable=True)
    pcs             = Column(Integer, nullable=True)
    grs_wt          = Column(Numeric(12, 3), nullable=True)
    chg_wt          = Column(Numeric(12, 3), nullable=True)
    nog             = Column(Text,        nullable=True)   # Nature of Goods — free text
    shc             = Column(String(50),  nullable=True)   # Special Handling Codes

    # ── X-RAY fields ──────────────────────────────────────────────────────────
    xray_start_datetime = Column(DateTime(timezone=True), nullable=True)
    xray_end_datetime   = Column(DateTime(timezone=True), nullable=True)
    xray_type           = Column(String(50),  nullable=True)
    xray_datetime       = Column(DateTime(timezone=True), nullable=True)  # X-RAY DT/TIME
    xray_user           = Column(String(100), nullable=True)

    # ── Document / operational timestamps ────────────────────────────────────
    doc_accpt_datetime  = Column(DateTime(timezone=True), nullable=True)
    rcs_rcf_rct_datetime = Column(DateTime(timezone=True), nullable=True)
    uplifting_datetime  = Column(DateTime(timezone=True), nullable=True)

    # ── Flight / agent / device ───────────────────────────────────────────────
    flt_no          = Column(String(20),  nullable=True)
    agent_name      = Column(String(200), nullable=True)
    device_model_no = Column(String(100), nullable=True)
    serial_no       = Column(String(100), nullable=True)

    # ── Upload tracking ───────────────────────────────────────────────────────
    month_uploaded  = Column(String(7),   nullable=False, index=True)
    # ^ "YYYY-MM" — used as the delete key when re-uploading the same month

    uploaded_at     = Column(
        DateTime(timezone=True),
        nullable=False,
        server_default=func.now()
    )
    uploaded_by     = Column(String(20), nullable=True)
    # ^ UTC timestamp of the upload session that inserted this row

    # ── Composite indexes for common query patterns ───────────────────────────
    __table_args__ = (
        # Fast look-up: all records for a given month
        Index("ix_export_tp_xray_month", "month_uploaded"),
        # Fast look-up: all shipments for a given AWB across months
        Index("ix_export_tp_xray_awb_month", "awb_no", "month_uploaded"),
        # Natural dedup key: true duplicate if AWB + xray_start_datetime match
        Index("ix_export_tp_xray_dedup", "awb_no", "xray_start_datetime"),
    )

    def __repr__(self) -> str:
        return (
            f"<ExportTpXray id={self.id} awb_no={self.awb_no!r} "
            f"month={self.month_uploaded!r}>"
        )
    





# ================== 🫥🫥🫥🫥 IMPORT TP EXPORT TABLE ==========================

class ImportTpXray(Base):
    __tablename__ = "import_tp_xray"

    id                   = Column(BigInteger, primary_key=True, autoincrement=True)

    awb_no               = Column(String(20),    nullable=False, index=True)
    origin               = Column(String(10),    nullable=True)
    destination          = Column(String(10),    nullable=True)
    pcs                  = Column(Integer, nullable=True)
    grs_wt               = Column(Numeric(12, 3), nullable=True)
    chg_wt               = Column(Numeric(12, 3), nullable=True)
    nog                  = Column(Text,           nullable=True)
    shc                  = Column(String(50),     nullable=True)

    xray_start_datetime  = Column(DateTime(timezone=True), nullable=True)
    xray_end_datetime    = Column(DateTime(timezone=True), nullable=True)
    xray_type            = Column(String(50),     nullable=True)
    xray_datetime        = Column(DateTime(timezone=True), nullable=True)
    xray_user            = Column(String(100),    nullable=True)

    phs_pcs              = Column(Numeric(10, 2), nullable=True)
    etd_pcs              = Column(Numeric(10, 2), nullable=True)
    eds_pcs              = Column(Numeric(10, 2), nullable=True)
    edd_pcs              = Column(Numeric(10, 2), nullable=True)
    vck_pcs              = Column(Numeric(10, 2), nullable=True)
    cmd_pcs              = Column(Numeric(10, 2), nullable=True)

    rcs_rcf_rct_datetime = Column(DateTime(timezone=True), nullable=True)
    uplifting_datetime   = Column(DateTime(timezone=True), nullable=True)
    flt_no               = Column(String(20),     nullable=True)
    agent_name           = Column(String(200),    nullable=True)
    serial_no            = Column(String(100),    nullable=True)
    device_model_no      = Column(String(100),    nullable=True)
    remarks              = Column(Text,           nullable=True)

    month_uploaded       = Column(String(7),      nullable=False, index=True)
    uploaded_at          = Column(DateTime(timezone=True), nullable=False, server_default=func.now())

    __table_args__ = (
        Index("ix_import_tp_xray_month",     "month_uploaded"),
        Index("ix_import_tp_xray_awb_month", "awb_no", "month_uploaded"),
        Index("ix_import_tp_xray_dedup",     "awb_no", "xray_start_datetime"),
    )