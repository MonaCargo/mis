import uuid
from typing import List, Optional

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.digital_reports.mis_dept.mis_pivot_reports import (
    DigitalReportsMisPivotReport,
    DigitalReportsMisPivotReportField,
    PivotFieldType,
    PivotReportType,
)
from app.schemas.digital_reports.mis_dept.mis_pivot_reports_schemas import (
    PivotFieldsIn,
    PivotReportCreate,
    PivotReportUpdate,
)

FIELD_TYPE_ORDER = [
    PivotFieldType.FILTERS,
    PivotFieldType.COLUMNS,
    PivotFieldType.ROWS,
    PivotFieldType.VALUES,
]


def _fields_to_schema(fields: List[DigitalReportsMisPivotReportField]) -> PivotFieldsIn:
    mapping = {f.field_type.value: f.value for f in fields}
    return PivotFieldsIn(
        filters=mapping.get("FILTERS", []),
        columns=mapping.get("COLUMNS", []),
        rows=mapping.get("ROWS", []),
        values=mapping.get("VALUES", []),
    )


async def _upsert_fields(
    session: AsyncSession, report_id: uuid.UUID, fields_in: PivotFieldsIn
) -> None:
    field_map = {
        PivotFieldType.FILTERS: fields_in.filters,
        PivotFieldType.COLUMNS: fields_in.columns,
        PivotFieldType.ROWS: fields_in.rows,
        PivotFieldType.VALUES: fields_in.values,
    }

    result = await session.execute(
        select(DigitalReportsMisPivotReportField).where(
            DigitalReportsMisPivotReportField.report_id == report_id
        )
    )
    existing_rows = {row.field_type: row for row in result.scalars().all()}

    for field_type, values in field_map.items():
        if field_type in existing_rows:
            existing_rows[field_type].value = values
        else:
            session.add(
                DigitalReportsMisPivotReportField(
                    report_id=report_id, field_type=field_type, value=values
                )
            )


async def create_pivot_report(
    session: AsyncSession, payload: PivotReportCreate, created_by: Optional[str]
) -> DigitalReportsMisPivotReport:
    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Report name cannot be empty")

    report = DigitalReportsMisPivotReport(
        name=payload.name.strip(),
        report_type=payload.report_type,
        from_date=payload.from_date,
        to_date=payload.to_date,
        aggregation_type=payload.aggregation_type,
        active_filters=payload.active_filters,
        created_by=created_by,
    )
    session.add(report)
    await session.flush()  # report.id chahiye field rows insert karne se pehle
    await _upsert_fields(session, report.id, payload.fields)
    # NOTE: commit router karega (jaisa upload_uplift_report route karta hai)
    return report


async def list_pivot_reports(
    session: AsyncSession, report_type: Optional[PivotReportType] = None
) -> List[DigitalReportsMisPivotReport]:
    stmt = select(DigitalReportsMisPivotReport)
    if report_type:
        stmt = stmt.where(DigitalReportsMisPivotReport.report_type == report_type)
    stmt = stmt.order_by(DigitalReportsMisPivotReport.updated_at.desc())

    result = await session.execute(stmt)
    return result.scalars().all()


async def get_pivot_report(
    session: AsyncSession, report_id: uuid.UUID
) -> DigitalReportsMisPivotReport:
    result = await session.execute(
        select(DigitalReportsMisPivotReport).where(
            DigitalReportsMisPivotReport.id == report_id
        )
    )
    report = result.scalar_one_or_none()
    if not report:
        raise HTTPException(status_code=404, detail="Report not found")
    return report


async def update_pivot_report(
    session: AsyncSession,
    report_id: uuid.UUID,
    payload: PivotReportUpdate,
    updated_by: Optional[str],
) -> DigitalReportsMisPivotReport:
    report = await get_pivot_report(session, report_id)

    if not payload.name.strip():
        raise HTTPException(status_code=400, detail="Report name cannot be empty")

    report.name = payload.name.strip()
    report.report_type = payload.report_type
    report.from_date = payload.from_date
    report.to_date = payload.to_date
    report.aggregation_type = payload.aggregation_type
    report.active_filters = payload.active_filters
    report.updated_by = updated_by

    await _upsert_fields(session, report.id, payload.fields)
    # NOTE: commit router karega
    return report


async def rename_pivot_report(
    session: AsyncSession, report_id: uuid.UUID, name: str, updated_by: Optional[str]
) -> DigitalReportsMisPivotReport:
    if not name.strip():
        raise HTTPException(status_code=400, detail="Report name cannot be empty")

    report = await get_pivot_report(session, report_id)
    report.name = name.strip()
    report.updated_by = updated_by
    # NOTE: commit router karega
    return report


async def delete_pivot_report(session: AsyncSession, report_id: uuid.UUID) -> None:
    report = await get_pivot_report(session, report_id)
    await session.delete(report)  # cascades to field rows
    # NOTE: commit router karega
