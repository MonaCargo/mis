import enum
import uuid

from sqlalchemy import Column, String, Date, DateTime, ForeignKey, UniqueConstraint, func
from sqlalchemy import Enum as SAEnum
from sqlalchemy.dialects.postgresql import UUID, JSONB
from sqlalchemy.orm import relationship


from app.db.base import Base


class PivotReportType(str, enum.Enum):
    UPLIFTING = "UPLIFTING"
    SEGREGATION = "SEGREGATION"
    BOTH = "BOTH"


class PivotAggregationType(str, enum.Enum):
    SUM = "SUM"
    COUNT = "COUNT"
    AVG = "AVG"
    MIN = "MIN"
    MAX = "MAX"


class PivotFieldType(str, enum.Enum):
    FILTERS = "FILTERS"
    COLUMNS = "COLUMNS"
    ROWS = "ROWS"
    VALUES = "VALUES"


class DigitalReportsMisPivotReport(Base):
    """Report header — ek row per saved pivot report."""

    __tablename__ = "dr_mis_pivot_reports"

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    name = Column(String(255), nullable=False)
    report_type = Column(SAEnum(PivotReportType, name="pivot_report_type"), nullable=False)
    from_date = Column(Date, nullable=False)
    to_date = Column(Date, nullable=False)
    aggregation_type = Column(
        SAEnum(PivotAggregationType, name="pivot_aggregation_type"),
        nullable=False,
        default=PivotAggregationType.SUM,
    )
    active_filters = Column(JSONB, nullable=False, default=dict)

    # "user" jisne save/update kiya — adjust FK target to your actual users table
    created_by = Column(String(255), nullable=True)   # e.g. username / employee code
    updated_by = Column(String(255), nullable=True)

    created_at = Column(DateTime(timezone=True), server_default=func.now())
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())

    fields = relationship(
        "DigitalReportsMisPivotReportField",
        back_populates="report",
        cascade="all, delete-orphan",
        lazy="selectin",
    )


class DigitalReportsMisPivotReportField(Base):
    """
    EAV table: ek row per (report, field_type).
    field_type -> FILTERS / COLUMNS / ROWS / VALUES
    value      -> JSON array of selected field/column names, e.g. ["pcs", "awb_no"]
    """

    __tablename__ = "dr_mis_pivot_report_fields"
    __table_args__ = (UniqueConstraint("report_id", "field_type", name="uq_pivot_report_field_type"),)

    id = Column(UUID(as_uuid=True), primary_key=True, default=uuid.uuid4)
    report_id = Column(
        UUID(as_uuid=True),
        ForeignKey("dr_mis_pivot_reports.id", ondelete="CASCADE"),
        nullable=False,
    )
    field_type = Column(SAEnum(PivotFieldType, name="pivot_field_type"), nullable=False)
    value = Column(JSONB, nullable=False, default=list)

    report = relationship("DigitalReportsMisPivotReport", back_populates="fields")
