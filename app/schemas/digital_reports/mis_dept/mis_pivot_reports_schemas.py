import datetime
import uuid
from typing import Dict, List, Optional

from pydantic import BaseModel, Field

from app.db.models.digital_reports.mis_dept.mis_pivot_reports import (
    PivotAggregationType,
    PivotReportType,
)


class PivotFieldsIn(BaseModel):
    """Matches PivotBuilder's 4 dropzones."""
    filters: List[str] = Field(default_factory=list)
    columns: List[str] = Field(default_factory=list)
    rows: List[str] = Field(default_factory=list)
    values: List[str] = Field(default_factory=list)


class PivotReportCreate(BaseModel):
    name: str
    report_type: PivotReportType
    from_date: datetime.date
    to_date: datetime.date
    aggregation_type: PivotAggregationType = PivotAggregationType.SUM
    active_filters: Dict[str, str] = Field(default_factory=dict)
    fields: PivotFieldsIn


class PivotReportUpdate(PivotReportCreate):
    pass


class PivotReportRename(BaseModel):
    name: str


class PivotReportListItem(BaseModel):
    id: uuid.UUID
    name: str
    report_type: PivotReportType
    from_date: datetime.date
    to_date: datetime.date
    updated_at: datetime.datetime

    class Config:
        from_attributes = True


class PivotReportDetail(BaseModel):
    id: uuid.UUID
    name: str
    report_type: PivotReportType
    from_date: datetime.date
    to_date: datetime.date
    aggregation_type: PivotAggregationType
    active_filters: Dict[str, str]
    fields: PivotFieldsIn
    created_by: Optional[str] = None
    updated_at: datetime.datetime

    class Config:
        from_attributes = True
