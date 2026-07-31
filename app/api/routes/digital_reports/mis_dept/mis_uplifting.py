import io
import os
from datetime import date, datetime
import datetime as dt
from typing import Optional
import uuid
import pandas as pd
from fastapi import APIRouter, UploadFile, File, Depends, Form, HTTPException, status, Query
from fastapi.responses import StreamingResponse
from sqlalchemy import and_, func, inspect, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.digital_reports.mis_dept.mis_agent_list import DigitalMisPdaAgent
from app.db.models.digital_reports.mis_dept.mis_flight_status_cleaned import DigitalReportsMisFlightStatus
from app.db.models.digital_reports.mis_dept.mis_flt_schedule_cleaning import DigitalReportsFlightScheduleImport
from app.db.models.digital_reports.mis_dept.mis_nog_list import DigitalMisNogMaster
from app.db.models.digital_reports.mis_dept.mis_segregation import DigitalReportsMisSegregation
from app.db.models.digital_reports.mis_dept.mis_segregation_cleaned import DigitalReportsMisSegregationCleaned
from app.db.models.digital_reports.mis_dept.mis_shc_code import DigitalMisShcMaster
from app.db.models.digital_reports.mis_dept.mis_uplifting_po import DigitalReportsMisUpliftingPo       
from app.db.models.digital_reports.mis_dept.mis_uplifting_po_cleaned import DigitalReportsMisUpliftingCleaned
from app.db.models.digital_reports.mis_dept.mis_international_code import DigitalMisInternationalCode
from app.db.models.digital_reports.mis_dept.mis_domestic_code import DigitalMisDomesticCode
from app.services.digital_reports.mis_dept.mis_flight_status_service import process_and_save_flight_status
from app.services.digital_reports.mis_dept.mis_flt_schedule_service import save_flight_schedule_df, validate_report_dates , clean_flight_schedule_bytes
from app.services.digital_reports.mis_dept.mis_segregation_service import  process_clean_and_apply_logic
from app.services.digital_reports.mis_dept.mis_uplifting_po_service import (
    save_uplift_df, 
    save_cleaned_df, 
    seed_flt_country_continent, 
    list_flt_country_continent
)

from app.utils.common.helperFunction import convert_df_utc_to_ist
from app.utils.digital_reports.mis_dept.mis_uplifting_po_cleaning import (
    clean_uplift_bytes, validate_dates, DateValidationError,
)

from app.db.session import get_db
# from app.core.deps import get_current_user 

from app.db.models.digital_reports.mis_dept.mis_pivot_reports import PivotReportType
from app.schemas.digital_reports.mis_dept.mis_pivot_reports_schemas import (
    PivotFieldsIn,
    PivotReportCreate,
    PivotReportDetail,
    PivotReportListItem,
    PivotReportRename,
    PivotReportUpdate,
)
from app.services.digital_reports.mis_dept.mis_pivot_reports_service import (
    _fields_to_schema,
    create_pivot_report,
    delete_pivot_report,
    get_pivot_report,
    list_pivot_reports,
    rename_pivot_report,
    update_pivot_report,
)
router = APIRouter()

ALLOWED_EXTENSIONS = {".xlsx", ".xls", ".csv", ".CSV"}


def _parse_date(value: str, field: str) -> date:
    """Accept YYYY-MM-DD (typical from frontend date pickers)."""
    try:
        return datetime.strptime(value.strip(), "%Y-%m-%d").date()
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid {field}: expected YYYY-MM-DD"
        )


# ==================== UPLOAD PO FILE =======================================

@router.post("/uplifting/upload-PO")
async def upload_uplift_report(
    file: UploadFile = File(...),
    report_date: str = Form(...),
    uploaded_by: str | None = Form(None),
    session: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    d_rep = _parse_date(report_date, "report_date")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Empty file")

    try:
        result = clean_uplift_bytes(contents, file.filename)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Could not read file: {e}")

    try:
        validate_dates(result, d_rep)
    except DateValidationError as e:
        raise HTTPException(status_code=422, detail=str(e))

    if result.valid_count == 0:
        raise HTTPException(status_code=422, detail="No valid rows found in file")

    try:
        cleaned_inserted = await save_cleaned_df(
            session, result.awbs_df,
            report_date=d_rep, uploaded_by=uploaded_by,
        )

        inserted = await save_uplift_df(
            session, result.awbs_df,
            report_date=d_rep, uploaded_by=uploaded_by,
        )
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save records: {e}")

    return {
        "filename": file.filename,
        "source_kind": result.source_kind,
        "report_date": d_rep.isoformat(),
        "uploaded_by": uploaded_by,
        "inserted": inserted,
        "cleaned_inserted": cleaned_inserted,
        "total_parsed": result.total_parsed,
        "valid": result.valid_count,
        "dropped": result.dropped_count,
        "nil_count": result.nil_count,
        "carriers": result.carriers,
    }


# ============================== DATA DOWNLOAD RANGE ==================

@router.get("/uplifting/download-range")
async def download_uplift_excel_range(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    report_type: str | None = Query(None, description="Report or file type filter"),
    session: AsyncSession = Depends(get_db),
):
    d_from = _parse_date(from_date, "from_date")
    d_to = _parse_date(to_date, "to_date")
    
    if d_from > d_to:
        raise HTTPException(status_code=400, detail="from_date must be before to_date")

    try:
        stmt = select(DigitalReportsMisUpliftingPo).where(
            DigitalReportsMisUpliftingPo.report_date.between(d_from, d_to)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            raise HTTPException(
                status_code=404, 
                detail=f"No data found between {from_date} and {to_date}"
            )

        cols = [c.name for c in DigitalReportsMisUpliftingPo.__table__.columns if c.name != "id"]
        data = [{c: getattr(row, c) for c in cols} for row in rows]
        df = pd.DataFrame(data)

        df = convert_df_utc_to_ist(df)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Uplift")
        buffer.seek(0)

        prefix = report_type if report_type else "Cargo_Uplift"
        filename = f"{prefix}_Cleaned_{from_date}_to_{to_date}.xlsx"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error generating report: {str(e)}")


# ============================== CLEANED DATA DOWNLOAD RANGE ==================

@router.get("/uplifting/download-range-cleaned")
async def download_uplift_cleaned_range(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_db),
):
    d_from = _parse_date(from_date, "from_date")
    d_to = _parse_date(to_date, "to_date")

    if d_from > d_to:
        raise HTTPException(status_code=400, detail="from_date must be before to_date")

    try:
        stmt = select(DigitalReportsMisUpliftingCleaned).where(
            DigitalReportsMisUpliftingCleaned.report_date.between(d_from, d_to)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No cleaned data found between {from_date} and {to_date}"
            )

        exclude = {"id", "report_date", "uploaded_by", "created_at"}
        cols = [c.name for c in DigitalReportsMisUpliftingCleaned.__table__.columns if c.name not in exclude]

        data = [{c: getattr(row, c) for c in cols} for row in rows]
        df = pd.DataFrame(data)

        df = convert_df_utc_to_ist(df)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Cleaned")
        buffer.seek(0)

        filename = f"Cargo_Uplift_Cleaned_{from_date}_to_{to_date}.xlsx"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error generating cleaned report: {str(e)}")


# ======================= UPLOAD INTERNATIONAL CODE FILE ==========================

@router.post("/upload/international-codes", status_code=status.HTTP_200_OK)
async def upload_international_codes(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1]
    if ext not in ALLOWED_EXTENSIONS and ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type '{ext}'. Allowed formats: .xlsx, .xls, .csv"
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        if ext.lower() == ".csv":
            df = pd.read_csv(io.BytesIO(contents), keep_default_na=False)
        else:
            df = pd.read_excel(io.BytesIO(contents), sheet_name=0, keep_default_na=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse uploaded file: {str(e)}")

    df.columns = [str(c).strip().lower() for c in df.columns]
    required_cols = {"code", "city", "country", "continent"}

    if not required_cols.issubset(set(df.columns)):
        raise HTTPException(
            status_code=422,
            detail=f"Missing required columns. File must contain headers: {list(required_cols)}"
        )

    df['code'] = df['code'].astype(str).str.strip().str.upper()
    df = df[df['code'] != '']

    if df.empty:
        raise HTTPException(status_code=422, detail="No valid data rows found in file.")

    try:
        db_stmt = select(DigitalMisInternationalCode.code)
        db_result = await session.execute(db_stmt)
        existing_codes = set(db_result.scalars().all())

        total_file_records = len(df)
        new_records = []
        duplicate_codes = []
        seen_in_file = set()

        for _, row in df.iterrows():
            code_val = row["code"]

            if code_val in existing_codes or code_val in seen_in_file:
                duplicate_codes.append(code_val)
            else:
                seen_in_file.add(code_val)
                new_records.append(
                    DigitalMisInternationalCode(
                        code=code_val,
                        city=str(row["city"]).strip(),
                        country=str(row["country"]).strip(),
                        continent=str(row["continent"]).strip(),
                    )
                )

        if not new_records:
            raise HTTPException(
                status_code=400,
                detail=f"All {total_file_records} codes in this file already exist in the database!"
            )

        session.add_all(new_records)
        await session.commit()

        return {
            "status": "success",
            "message": f"Upload completed! {len(new_records)} new code(s) added to database.",
            "total_records_in_file": total_file_records,
            "new_codes_added": len(new_records),
            "skipped_duplicates": len(duplicate_codes),
            "filename": file.filename
        }

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process database insert: {str(e)}"
        )


# ======================== UPLOAD DOMESTIC CODE ===================================

@router.post("/upload/domestic-codes", status_code=status.HTTP_200_OK)
async def upload_domestic_codes(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1]
    if ext not in ALLOWED_EXTENSIONS and ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid file type '{ext}'. Allowed formats: .xlsx, .xls, .csv"
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        if ext.lower() == ".csv":
            raw_df = pd.read_csv(io.BytesIO(contents), keep_default_na=False)
        else:
            raw_df = pd.read_excel(io.BytesIO(contents), sheet_name=0, keep_default_na=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse uploaded file: {str(e)}")

    raw_df.columns = [str(c).strip().lower() for c in raw_df.columns]
    cleaned_rows = []
    
    if "s.no" in raw_df.columns or "airport name & city" in raw_df.columns:
        airport_col = [c for c in raw_df.columns if "airport" in c or "city" in c][0]
        code_col = "iata" if "iata" in raw_df.columns else ("code" if "code" in raw_df.columns else raw_df.columns[1])

        i = 0
        while i < len(raw_df):
            r1 = raw_df.iloc[i]
            r2 = raw_df.iloc[i+1] if i + 1 < len(raw_df) else None

            code_val = str(r1[code_col]).strip().upper() if pd.notna(r1[code_col]) else ""
            
            if code_val and code_val != "NONE":
                apt_name = str(r1[airport_col]).strip() if pd.notna(r1[airport_col]) else ""
                city_val = str(r2[airport_col]).strip() if r2 is not None and pd.notna(r2[airport_col]) else apt_name

                cleaned_rows.append({
                    "code": code_val,
                    "airport_name": apt_name,
                    "city": city_val
                })
            i += 2
    else:
        for _, r in raw_df.iterrows():
            code_val = str(r.get("code", r.get("iata", ""))).strip().upper()
            if code_val:
                cleaned_rows.append({
                    "code": code_val,
                    "airport_name": str(r.get("airport_name", r.get("airport", ""))).strip(),
                    "city": str(r.get("city", "")).strip()
                })

    if not cleaned_rows:
        raise HTTPException(status_code=422, detail="No valid domestic airport rows found in file.")

    try:
        db_stmt = select(DigitalMisDomesticCode.code)
        db_result = await session.execute(db_stmt)
        existing_codes = set(db_result.scalars().all())

        total_file_records = len(cleaned_rows)
        new_records = []
        duplicate_codes = []
        seen_in_file = set()

        for row in cleaned_rows:
            code_val = row["code"]

            if code_val in existing_codes or code_val in seen_in_file:
                duplicate_codes.append(code_val)
            else:
                seen_in_file.add(code_val)
                new_records.append(
                    DigitalMisDomesticCode(
                        code=code_val,
                        airport_name=row["airport_name"],
                        city=row["city"]
                    )
                )

        if not new_records:
            raise HTTPException(
                status_code=400,
                detail=f"All {total_file_records} domestic airport codes in this file already exist in the database!"
            )

        session.add_all(new_records)
        await session.commit()

        return {
            "status": "success",
            "message": f"Upload completed! {len(new_records)} new domestic code(s) added to database.",
            "total_records_in_file": total_file_records,
            "new_codes_added": len(new_records),
            "skipped_duplicates": len(duplicate_codes),
            "filename": file.filename
        }

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process database insert: {str(e)}"
        )


# ======================= INTERNATIONAL CODE CRUD ===========================
@router.get("/get/international-codes")
async def get_international_codes(
    search: str = Query("", description="Search term for code, city, country, or continent"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=500, description="Records per page"),
    session: AsyncSession = Depends(get_db),
):
    base_query = select(DigitalMisInternationalCode)
    count_query = select(func.count()).select_from(DigitalMisInternationalCode)
    
    if search.strip():
        search_pattern = f"%{search.strip().upper()}%"
        search_filter = or_(
            func.upper(DigitalMisInternationalCode.code).like(search_pattern),
            func.upper(DigitalMisInternationalCode.city).like(search_pattern),
            func.upper(DigitalMisInternationalCode.country).like(search_pattern),
            func.upper(DigitalMisInternationalCode.continent).like(search_pattern),
        )
        base_query = base_query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await session.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    paginated_query = base_query.order_by(DigitalMisInternationalCode.id).offset(offset).limit(limit)

    result = await session.execute(paginated_query)
    data = result.scalars().all()

    return {
        "status": "success",
        "count": len(data),
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total else 0,
        "data": [
            {
                "id": item.id,
                "code": item.code,
                "city": item.city,
                "country": item.country,
                "continent": item.continent,
            }
            for item in data
        ],
    }
@router.post("/create/international-codes", status_code=status.HTTP_201_CREATED)
async def create_international_code(
    payload: dict,
    session: AsyncSession = Depends(get_db),
):
    code_val = payload.get("code", "").strip().upper()
    if not code_val:
        raise HTTPException(status_code=400, detail="Code is required.")

    existing = await session.execute(
        select(DigitalMisInternationalCode).where(
            func.upper(DigitalMisInternationalCode.code) == code_val
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=400, 
            detail=f"International Code '{code_val}' already exists."
        )

    new_record = DigitalMisInternationalCode(
        code=code_val,
        city=payload.get("city", "").strip(),
        country=payload.get("country", "").strip(),
        continent=payload.get("continent", "").strip(),
    )
    
    session.add(new_record)
    await session.commit()
    await session.refresh(new_record)

    return {
        "status": "success",
        "message": "International code created successfully.",
        "data": {
            "id": new_record.id,
            "code": new_record.code,
            "city": new_record.city,
            "country": new_record.country,
            "continent": new_record.continent,
        }
    }


@router.put("/update/international-codes/{item_id}")
async def update_international_code(
    item_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DigitalMisInternationalCode).where(DigitalMisInternationalCode.id == item_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="International Code record not found.")

    code_val = payload.get("code", "").strip().upper()
    if not code_val:
        raise HTTPException(status_code=400, detail="Code is required.")

    record.code = code_val
    record.city = payload.get("city", "").strip()
    record.country = payload.get("country", "").strip()
    record.continent = payload.get("continent", "").strip()

    await session.commit()
    await session.refresh(record)

    return {
        "status": "success",
        "message": "International code updated successfully.",
        "data": {
            "id": record.id,
            "code": record.code,
            "city": record.city,
            "country": record.country,
            "continent": record.continent,
        }
    }


@router.delete("/delete/international-codes/{item_id}")
async def delete_international_code(
    item_id: int,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DigitalMisInternationalCode).where(DigitalMisInternationalCode.id == item_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="International Code record not found.")

    await session.delete(record)
    await session.commit()

    return {"status": "success", "message": "International code deleted successfully."}


# ======================= DOMESTIC CODE CRUD ===========================
@router.get("/get/domestic-codes")
async def get_domestic_codes(
    search: str = Query("", description="Search term for code, airport_name, or city"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=500, description="Records per page"),
    session: AsyncSession = Depends(get_db),
):
    base_query = select(DigitalMisDomesticCode)
    count_query = select(func.count()).select_from(DigitalMisDomesticCode)

    if search.strip():
        search_pattern = f"%{search.strip().upper()}%"
        search_filter = or_(
            func.upper(DigitalMisDomesticCode.code).like(search_pattern),
            func.upper(DigitalMisDomesticCode.airport_name).like(search_pattern),
            func.upper(DigitalMisDomesticCode.city).like(search_pattern),
        )
        base_query = base_query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await session.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    paginated_query = base_query.order_by(DigitalMisDomesticCode.id).offset(offset).limit(limit)

    result = await session.execute(paginated_query)
    data = result.scalars().all()

    return {
        "status": "success",
        "count": len(data),
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total else 0,
        "data": [
            {
                "id": item.id,
                "code": item.code,
                "airport_name": item.airport_name,
                "city": item.city,
            }
            for item in data
        ],
    }
@router.post("/create/domestic-codes", status_code=status.HTTP_201_CREATED)
async def create_domestic_code(
    payload: dict,
    session: AsyncSession = Depends(get_db),
):
    code_val = payload.get("code", "").strip().upper()
    if not code_val:
        raise HTTPException(status_code=400, detail="Airport code is required.")

    existing = await session.execute(
        select(DigitalMisDomesticCode).where(
            func.upper(DigitalMisDomesticCode.code) == code_val
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=400, 
            detail=f"Domestic Code '{code_val}' already exists."
        )

    airport_val = payload.get("airport_name")
    city_val = payload.get("city")

    new_record = DigitalMisDomesticCode(
        code=code_val,
        airport_name=airport_val.strip() if airport_val else None,
        city=city_val.strip() if city_val else None,
    )
    
    session.add(new_record)
    await session.commit()
    await session.refresh(new_record)

    return {
        "status": "success",
        "message": "Domestic code created successfully.",
        "data": {
            "id": new_record.id,
            "code": new_record.code,
            "airport_name": new_record.airport_name,
            "city": new_record.city,
        }
    }


@router.put("/update/domestic-codes/{item_id}")
async def update_domestic_code(
    item_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DigitalMisDomesticCode).where(DigitalMisDomesticCode.id == item_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="Domestic Code record not found.")

    code_val = payload.get("code", "").strip().upper()
    if not code_val:
        raise HTTPException(status_code=400, detail="Airport code is required.")

    airport_val = payload.get("airport_name")
    city_val = payload.get("city")

    record.code = code_val
    record.airport_name = airport_val.strip() if airport_val else None
    record.city = city_val.strip() if city_val else None

    await session.commit()
    await session.refresh(record)

    return {
        "status": "success",
        "message": "Domestic code updated successfully.",
        "data": {
            "id": record.id,
            "code": record.code,
            "airport_name": record.airport_name,
            "city": record.city,
        }
    }


@router.delete("/delete/domestic-codes/{item_id}")
async def delete_domestic_code(
    item_id: int,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DigitalMisDomesticCode).where(DigitalMisDomesticCode.id == item_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="Domestic Code record not found.")

    await session.delete(record)
    await session.commit()

    return {"status": "success", "message": "Domestic code deleted successfully."}

# ===================== UPLOAD FLIGHT STATUS REPORT =============================
@router.post("/upload-flight-status", status_code=status.HTTP_200_OK)
async def upload_flight_status_report(
    file: UploadFile = File(...),
    report_date: str = Form(..., description="Format: YYYY-MM-DD or DD-MM-YYYY"),
    uploaded_by: str | None = Form(None),
    session: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type: '{ext}'. Allowed types: .xlsx, .xls, .csv",
        )

    d_report = _parse_date(report_date, "report_date")

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        res_summary = await process_and_save_flight_status(
            session=session,
            file_bytes=contents,
            filename=file.filename or "",
            report_date=d_report,
            uploaded_by=uploaded_by,
        )
        await session.commit()
    except DateValidationError as e:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Error: {str(e)}",
        )

    return {
        "status": "success",
        "filename": file.filename,
        "summary": res_summary,
        
    }


# ============================== FLIGHT STATUS CLEANED DOWNLOAD ==================

@router.get("/download-flight-status-cleaned")
async def download_flight_status_cleaned(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_db),
):
    d_from = _parse_date(from_date, "from_date")
    d_to = _parse_date(to_date, "to_date")

    if d_from > d_to:
        raise HTTPException(status_code=400, detail="from_date must be before or equal to to_date")

    try:
        stmt = select(DigitalReportsMisFlightStatus).where(
            DigitalReportsMisFlightStatus.report_date.between(d_from, d_to)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No flight status data found between {from_date} and {to_date}"
            )

        exclude = {"id", "uploaded_by", "created_at"}
        cols = [c.name for c in DigitalReportsMisFlightStatus.__table__.columns if c.name not in exclude]

        data = [{c: getattr(row, c) for c in cols} for row in rows]
        df = pd.DataFrame(data)

        df = convert_df_utc_to_ist(df)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Flight_Status_Cleaned")
        buffer.seek(0)

        filename = f"FLIGHT_STATUS_Cleaned_{from_date}_to_{to_date}.xlsx"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Server error generating flight status report: {str(e)}"
        )



# ===================== FLT COUNTRY AND CONTINENT ===============================

@router.post("/upload/flt-country-continent")
async def upload_flt_country_continent(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    if not file.filename.lower().endswith((".xlsx", ".xls")):
        raise HTTPException(400, "Only .xlsx/.xls files are accepted")

    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(400, "Uploaded file is empty")

    try:
        summary = await seed_flt_country_continent(file_bytes, session)
        await session.commit()
    except ValueError as e:
        await session.rollback()
        raise HTTPException(422, str(e))
    except Exception as e:
        await session.rollback()
        raise HTTPException(500, f"Failed to save master data: {e}")

    return {"status": "success", "summary": summary}

@router.get("/list/flt-country-continent")
async def get_flt_country_continent(
    search: str | None = Query(None, description="Filter by dest code or country"),
    continent: str | None = Query(None, description="Exact continent match"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=500, description="Records per page"),
    session: AsyncSession = Depends(get_db),
):
    # Note: Agar list_flt_country_continent service function DB-level pagination support karta hai,
    # toh page & limit offset service level par paas kar sakte hain. 
    # Python-level slicing ke sath:
    rows = await list_flt_country_continent(session, search=search, continent=continent)
    
    total = len(rows)
    offset = (page - 1) * limit
    paginated_rows = rows[offset : offset + limit]

    return {
        "status": "success",
        "count": len(paginated_rows),
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total else 0,
        "data": paginated_rows
    }
# ===================== UPLOAD SEGREGATION FILE =================================
@router.post("/segregation-report", status_code=status.HTTP_200_OK)
async def upload_segregation_report(
    file: UploadFile = File(...),
    report_date: str = Form(..., description="Format: YYYY-MM-DD"),
    uploaded_by: str | None = Form(None),
    session: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(status_code=400, detail=f"Unsupported file type: {ext}")

    d_report = _parse_date(report_date, "report_date")
    contents = await file.read()
    
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        summary = await process_clean_and_apply_logic(
            session=session,
            file_bytes=contents,
            filename=file.filename or "",
            report_date=d_report,
            uploaded_by=uploaded_by,
        )
        await session.commit()
        return summary

    except DateValidationError as e:
        await session.rollback()
        raise HTTPException(status_code=422, detail=str(e))
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Processing failed: {str(e)}")

@router.get("/segregation/download-report")
async def download_segregation_excel_range(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    report_type: str | None = Query(None, description="Report or file type filter"),
    session: AsyncSession = Depends(get_db),
):
    d_from = _parse_date(from_date, "from_date")
    d_to = _parse_date(to_date, "to_date")
    
    if d_from > d_to:
        raise HTTPException(status_code=400, detail="from_date must be before to_date")

    try:
        stmt = select(DigitalReportsMisSegregation).where(
            DigitalReportsMisSegregation.report_date.between(d_from, d_to)
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No segregation data found between {from_date} and {to_date}"
            )

        cols = [c.name for c in DigitalReportsMisSegregation.__table__.columns if c.name != "id"]
        data = [{c: getattr(row, c) for c in cols} for row in rows]
        df = pd.DataFrame(data)

        df = convert_df_utc_to_ist(df)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Segregation")
        buffer.seek(0)

        prefix = report_type if report_type else "Cargo_Segregation"
        filename = f"{prefix}_{from_date}_to_{to_date}.xlsx"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error generating segregation report: {str(e)}")

# ================== GET SEGREGATION REPORT ===========================
@router.get("/segregation/download-range-cleaned")
async def download_segregation_cleaned_range(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_db),
):
    d_from = _parse_date(from_date, "from_date")
    d_to = _parse_date(to_date, "to_date")

    if d_from > d_to:
        raise HTTPException(status_code=400, detail="from_date must be before to_date")

    try:
        # Segregation table query with date range filter
        stmt = (
            select(DigitalReportsMisSegregationCleaned)
            .where(DigitalReportsMisSegregationCleaned.report_date.between(d_from, d_to))
            
        )

        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No cleaned segregation data found between {from_date} and {to_date}"
            )

        # Columns to exclude from the Excel sheet
        exclude = {"id", "report_date", "uploaded_by", "created_at"}
        cols = [c.name for c in DigitalReportsMisSegregationCleaned.__table__.columns if c.name not in exclude]

        data = [{c: getattr(row, c) for c in cols} for row in rows]
        df = pd.DataFrame(data)

        df = convert_df_utc_to_ist(df)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Segregation_Cleaned")
        buffer.seek(0)

        filename = f"Cargo_Segregation_Cleaned_{from_date}_to_{to_date}.xlsx"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error generating cleaned segregation report: {str(e)}")



# ====================== flt_schedule report =========================
@router.post("/flight-schedule/upload-report")
async def upload_flight_schedule_report(
    file: UploadFile = File(...),
    report_date: str = Form(...),
    uploaded_by: str | None = Form(None),
    session: AsyncSession = Depends(get_db),
):
    """
    Uploads and processes the Flight Schedule Import Report (e.g. 24JUL261459.CSV).
    Enforces validation:
    - report_date == report_to
    - report_from == report_date - 1 day (N-1)
    """
    ext = os.path.splitext(file.filename or "")[1].lower()
    if ext not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Unsupported file type: {ext}",
        )

    d_rep = _parse_date(report_date, "report_date")

    contents = await file.read()
    if not contents:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Empty file provided",
        )

    # 1. Parse raw bytes
    try:
        result = clean_flight_schedule_bytes(contents, file.filename)
    except Exception as e:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail=f"Could not read or parse file: {e}",
        )

    # 2. Validate extracted header dates against selected report_date
    try:
        validate_report_dates(
            report_date=d_rep,
            report_from=result.report_from,
            report_to=result.report_to,
        )
    except DateValidationError as e:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(e),
        )

    if result.valid_count == 0:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail="No valid flight schedule rows found in file",
        )

    # 3. Persist cleaned records to database
    try:
        inserted_count = await save_flight_schedule_df(
            session=session,
            df=result.flights_df,
            report_from=result.report_from,
            report_to=result.report_to,
            uploaded_by=uploaded_by,
        )
        await session.commit()
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=f"Failed to save flight schedule records: {e}",
        )

    return {
        "filename": file.filename,
        "source_kind": result.source_kind,
        "report_date": d_rep.isoformat(),
        "report_from": result.report_from.isoformat() if result.report_from else None,
        "report_to": result.report_to.isoformat() if result.report_to else None,
        "uploaded_by": uploaded_by,
        "inserted": inserted_count,
        "total_parsed": result.total_parsed,
        "valid": result.valid_count,
        "dropped": result.dropped_count,
    }

# ============================ GET CLEAN FLT SCHEDULE REPORT=======================

@router.get("/flight-schedule/download-range-cleaned")
async def download_flight_schedule_cleaned_range(
    from_date: str = Query(..., description="YYYY-MM-DD"),
    to_date: str = Query(..., description="YYYY-MM-DD"),
    session: AsyncSession = Depends(get_db),
):
    d_from = _parse_date(from_date, "from_date")
    d_to = _parse_date(to_date, "to_date")

    if d_from > d_to:
        raise HTTPException(status_code=400, detail="from_date must be before to_date")

    try:
        # Fetch records that overlap with the selected date range
        stmt = select(DigitalReportsFlightScheduleImport).where(
            DigitalReportsFlightScheduleImport.report_from <= d_to,
            DigitalReportsFlightScheduleImport.report_to >= d_from,
        )
        result = await session.execute(stmt)
        rows = result.scalars().all()

        if not rows:
            raise HTTPException(
                status_code=404,
                detail=f"No cleaned flight schedule data found between {from_date} and {to_date}"
            )

        # Exclude internal metadata columns
        exclude = {"id", "created_at"}
        cols = [c.name for c in DigitalReportsFlightScheduleImport.__table__.columns if c.name not in exclude]

        data = [{c: getattr(row, c) for c in cols} for row in rows]
        df = pd.DataFrame(data)

        df = convert_df_utc_to_ist(df)

        buffer = io.BytesIO()
        with pd.ExcelWriter(buffer, engine="openpyxl") as writer:
            df.to_excel(writer, index=False, sheet_name="Flight Schedule Cleaned")
        buffer.seek(0)

        filename = f"Flight_Schedule_Cleaned_{from_date}_to_{to_date}.xlsx"

        return StreamingResponse(
            buffer,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Access-Control-Expose-Headers": "Content-Disposition",
            },
        )
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Server error generating flight schedule report: {str(e)}")


# ======================= UPLOAD PDA AGENT FILE ==========================

@router.post("/upload/pda-agents", status_code=status.HTTP_200_OK)
async def upload_pda_agents(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1]
    if ext not in ALLOWED_EXTENSIONS and ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed formats: .xlsx, .xls, .csv"
        )

    contents = await file.read()
    if not contents:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        if ext.lower() == ".csv":
            df = pd.read_csv(io.BytesIO(contents), keep_default_na=False)
        else:
            df = pd.read_excel(io.BytesIO(contents), sheet_name=0, keep_default_na=False)
    except Exception as e:
        raise HTTPException(status_code=400, detail=f"Failed to parse uploaded file: {str(e)}")

    df.columns = [str(c).strip().lower() for c in df.columns]
    df = df.rename(columns={"pda code": "agent_code", "pda name": "agent_name"})
    required_cols = {"agent_code", "agent_name"}

    if not required_cols.issubset(set(df.columns)):
        raise HTTPException(
            status_code=422,
            detail=f"Missing required columns. File must contain headers: {list(required_cols)}"
        )

    df['agent_code'] = df['agent_code'].astype(str).str.strip().str.upper()
    df = df[df['agent_code'] != '']

    if df.empty:
        raise HTTPException(status_code=422, detail="No valid data rows found in file.")

    try:
        db_stmt = select(DigitalMisPdaAgent.agent_code)
        db_result = await session.execute(db_stmt)
        existing_codes = set(db_result.scalars().all())

        total_file_records = len(df)
        new_records = []
        duplicate_codes = []
        seen_in_file = set()

        for _, row in df.iterrows():
            code_val = row["agent_code"]

            if code_val in existing_codes or code_val in seen_in_file:
                duplicate_codes.append(code_val)
            else:
                seen_in_file.add(code_val)
                new_records.append(
                    DigitalMisPdaAgent(
                        agent_code=code_val,
                        agent_name=str(row["agent_name"]).strip(),
                    )
                )

        if not new_records:
            raise HTTPException(
                status_code=400,
                detail=f"All {total_file_records} agents in this file already exist in the database!"
            )

        session.add_all(new_records)
        await session.commit()

        return {
            "status": "success",
            "message": f"Upload completed! {len(new_records)} new agent(s) added to database.",
            "total_records_in_file": total_file_records,
            "new_codes_added": len(new_records),
            "skipped_duplicates": len(duplicate_codes),
            "filename": file.filename
        }

    except HTTPException:
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(
            status_code=500,
            detail=f"Failed to process database insert: {str(e)}"
        )


# ======================= PDA AGENT CRUD ===========================
@router.get("/get/pda-agents")
async def get_pda_agents(
    search: str = Query("", description="Search term for agent_code or agent_name"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=500, description="Records per page"),
    session: AsyncSession = Depends(get_db),
):
    base_query = select(DigitalMisPdaAgent)
    count_query = select(func.count()).select_from(DigitalMisPdaAgent)

    if search.strip():
        search_pattern = f"%{search.strip().upper()}%"
        search_filter = or_(
            func.upper(DigitalMisPdaAgent.agent_code).like(search_pattern),
            func.upper(DigitalMisPdaAgent.agent_name).like(search_pattern),
        )
        base_query = base_query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await session.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    paginated_query = base_query.order_by(DigitalMisPdaAgent.id).offset(offset).limit(limit)

    result = await session.execute(paginated_query)
    data = result.scalars().all()

    return {
        "status": "success",
        "count": len(data),
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total else 0,
        "data": [
            {
                "id": item.id,
                "agent_code": item.agent_code,
                "agent_name": item.agent_name,
            }
            for item in data
        ],
    }
@router.post("/create/pda-agents", status_code=status.HTTP_201_CREATED)
async def create_pda_agent(
    payload: dict,
    session: AsyncSession = Depends(get_db),
):
    code_val = payload.get("agent_code", "").strip().upper()
    if not code_val:
        raise HTTPException(status_code=400, detail="Agent code is required.")

    existing = await session.execute(
        select(DigitalMisPdaAgent).where(
            func.upper(DigitalMisPdaAgent.agent_code) == code_val
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=400,
            detail=f"PDA Agent Code '{code_val}' already exists."
        )

    new_record = DigitalMisPdaAgent(
        agent_code=code_val,
        agent_name=payload.get("agent_name", "").strip(),
    )

    session.add(new_record)
    await session.commit()
    await session.refresh(new_record)

    return {
        "status": "success",
        "message": "PDA agent created successfully.",
        "data": {
            "id": new_record.id,
            "agent_code": new_record.agent_code,
            "agent_name": new_record.agent_name,
        }
    }


@router.put("/update/pda-agents/{item_id}")
async def update_pda_agent(
    item_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DigitalMisPdaAgent).where(DigitalMisPdaAgent.id == item_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="PDA Agent record not found.")

    code_val = payload.get("agent_code", "").strip().upper()
    if not code_val:
        raise HTTPException(status_code=400, detail="Agent code is required.")

    record.agent_code = code_val
    record.agent_name = payload.get("agent_name", "").strip()

    await session.commit()
    await session.refresh(record)

    return {
        "status": "success",
        "message": "PDA agent updated successfully.",
        "data": {
            "id": record.id,
            "agent_code": record.agent_code,
            "agent_name": record.agent_name,
        }
    }


@router.delete("/delete/pda-agents/{item_id}")
async def delete_pda_agent(
    item_id: int,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DigitalMisPdaAgent).where(DigitalMisPdaAgent.id == item_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="PDA Agent record not found.")

    await session.delete(record)
    await session.commit()

    return {"status": "success", "message": "PDA agent deleted successfully."}


@router.post("/upload/shc-master", status_code=status.HTTP_200_OK)
async def upload_shc_master(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1]
    if ext not in ALLOWED_EXTENSIONS and ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed formats: .xlsx, .xls, .csv"
        )

    contents = await file.read()
    filename = file.filename.lower()

    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents))
    elif filename.endswith((".xls", ".xlsx")):
        df = pd.read_excel(io.BytesIO(contents))
    else:
        raise HTTPException(status_code=400, detail="Only CSV, XLS, XLSX files are supported.")

    df.columns = [str(c).strip().upper() for c in df.columns]

    shc_col = next((c for c in df.columns if c in ("SHC", "SHC CODE", "SHC_CODE")), None)
    final_shc_col = next((c for c in df.columns if c in ("FINAL SHC", "FINAL_SHC")), None)

    if not shc_col:
        raise HTTPException(status_code=400, detail="Missing required column: SHC (or SHC CODE)")
    if not final_shc_col:
        raise HTTPException(status_code=400, detail="Missing required column: FINAL SHC")

    # Fetch existing (shc, final_shc) combinations from DB
    db_result = await session.execute(
        select(DigitalMisShcMaster.shc, DigitalMisShcMaster.final_shc)
    )
    existing_combos = {(r[0], r[1]) for r in db_result.fetchall()}

    seen_in_file = set()
    inserted = 0
    skipped = 0

    for idx, row in df.iterrows():
        shc_val = str(row[shc_col]).strip().upper() if pd.notna(row[shc_col]) else ""
        if not shc_val:
            continue

        final_shc_val = str(row[final_shc_col]).strip().upper() if pd.notna(row[final_shc_col]) else ""

        combo = (shc_val, final_shc_val)

        if combo in existing_combos or combo in seen_in_file:
            skipped += 1
            continue

        seen_in_file.add(combo)
        new_record = DigitalMisShcMaster(
            shc=shc_val,
            final_shc=final_shc_val,
        )
        session.add(new_record)
        inserted += 1

    await session.commit()

    return {
        "message": f"Successfully processed. Inserted: {inserted}, Skipped duplicates: {skipped}",
        "inserted_count": inserted,
        "skipped_count": skipped,
    }

# ======================= SHC MASTER CRUD ===========================
@router.get("/get/shc-master")
async def get_shc_master(
    search: str = Query("", description="Search term for shc or final_shc"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=500, description="Records per page"),
    session: AsyncSession = Depends(get_db),
):
    base_query = select(DigitalMisShcMaster)
    count_query = select(func.count()).select_from(DigitalMisShcMaster)

    if search.strip():
        search_pattern = f"%{search.strip().upper()}%"
        search_filter = or_(
            func.upper(DigitalMisShcMaster.shc).like(search_pattern),
            func.upper(DigitalMisShcMaster.final_shc).like(search_pattern),
        )
        base_query = base_query.where(search_filter)
        count_query = count_query.where(search_filter)

    total_result = await session.execute(count_query)
    total = total_result.scalar()

    offset = (page - 1) * limit
    paginated_query = base_query.order_by(DigitalMisShcMaster.id).offset(offset).limit(limit)

    result = await session.execute(paginated_query)
    data = result.scalars().all()

    return {
        "status": "success",
        "count": len(data),
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total else 0,
        "data": [
            {
                "id": item.id,
                "shc": item.shc,
                "final_shc": item.final_shc,
            }
            for item in data
        ],
    }
@router.post("/create/shc-master", status_code=status.HTTP_201_CREATED)
async def create_shc_master(
    payload: dict,
    session: AsyncSession = Depends(get_db),
):
    shc_val = payload.get("shc", "").strip().upper()
    if not shc_val:
        raise HTTPException(status_code=400, detail="SHC code is required.")

    existing = await session.execute(
        select(DigitalMisShcMaster).where(
            func.upper(DigitalMisShcMaster.shc) == shc_val
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=400,
            detail=f"SHC Code '{shc_val}' already exists."
        )

    new_record = DigitalMisShcMaster(
        shc=shc_val,
        final_shc=payload.get("final_shc", "").strip().upper(),
    )

    session.add(new_record)
    await session.commit()
    await session.refresh(new_record)

    return {
        "status": "success",
        "message": "SHC record created successfully.",
        "data": {
            "id": new_record.id,
            "shc": new_record.shc,
            "final_shc": new_record.final_shc,
        }
    }


@router.put("/update/shc-master/{item_id}")
async def update_shc_master(
    item_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DigitalMisShcMaster).where(DigitalMisShcMaster.id == item_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="SHC record not found.")

    shc_val = payload.get("shc", "").strip().upper()
    if not shc_val:
        raise HTTPException(status_code=400, detail="SHC code is required.")

    record.shc = shc_val
    record.final_shc = payload.get("final_shc", "").strip().upper()

    await session.commit()
    await session.refresh(record)

    return {
        "status": "success",
        "message": "SHC record updated successfully.",
        "data": {
            "id": record.id,
            "shc": record.shc,
            "final_shc": record.final_shc,
        }
    }


@router.delete("/delete/shc-master/{item_id}")
async def delete_shc_master(
    item_id: int,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DigitalMisShcMaster).where(DigitalMisShcMaster.id == item_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="SHC record not found.")

    await session.delete(record)
    await session.commit()

    return {"status": "success", "message": "SHC record deleted successfully."}

@router.post("/upload/nog-master", status_code=status.HTTP_200_OK)
async def upload_nog_master(
    file: UploadFile = File(...),
    session: AsyncSession = Depends(get_db),
):
    ext = os.path.splitext(file.filename or "")[1]
    if ext not in ALLOWED_EXTENSIONS and ext.lower() not in ALLOWED_EXTENSIONS:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid file type '{ext}'. Allowed formats: .xlsx, .xls, .csv"
        )

    contents = await file.read()
    filename = file.filename.lower()

    if filename.endswith(".csv"):
        df = pd.read_csv(io.BytesIO(contents))
    elif filename.endswith((".xls", ".xlsx")):
        df = pd.read_excel(io.BytesIO(contents))
    else:
        raise HTTPException(status_code=400, detail="Only CSV, XLS, XLSX files are supported.")

    df.columns = [str(c).strip().upper() for c in df.columns]

    nog_col = next((c for c in df.columns if c in ("NOG", "NOG CODE", "NOG_CODE")), None)
    nog1_col = next((c for c in df.columns if c in ("NOG 1", "NOG_1", "NOG-1")), None)
    nog2_col = next((c for c in df.columns if c in ("NOG 2", "NOG_2", "NOG-2")), None)

    if not nog_col:
        raise HTTPException(status_code=400, detail="Missing required column: NOG")

    # Fetch existing (nog, nog_1, nog_2) combinations from DB
    db_result = await session.execute(
        select(DigitalMisNogMaster.nog, DigitalMisNogMaster.nog_1, DigitalMisNogMaster.nog_2)
    )
    existing_combos = {(r[0], r[1], r[2]) for r in db_result.fetchall()}

    seen_in_file = set()
    inserted = 0
    skipped = 0

    for idx, row in df.iterrows():
        nog_val = str(row[nog_col]).strip().upper() if pd.notna(row[nog_col]) else ""
        if not nog_val:
            continue

        nog1_val = str(row[nog1_col]).strip() if nog1_col and pd.notna(row[nog1_col]) else ""
        nog2_val = str(row[nog2_col]).strip() if nog2_col and pd.notna(row[nog2_col]) else ""

        combo = (nog_val, nog1_val, nog2_val)

        if combo in existing_combos or combo in seen_in_file:
            skipped += 1
            continue

        seen_in_file.add(combo)
        new_record = DigitalMisNogMaster(
            nog=nog_val,
            nog_1=nog1_val,
            nog_2=nog2_val,
        )
        session.add(new_record)
        inserted += 1

    await session.commit()

    return {
        "message": f"Successfully processed. Inserted: {inserted}, Skipped duplicates: {skipped}",
        "inserted_count": inserted,
        "skipped_count": skipped,
    }
# ======================= NOG MASTER CRUD ===========================
@router.get("/get/nog-master")
async def get_nog_master(
    search: str = Query("", description="Search term for nog, nog_1 or nog_2"),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(20, ge=1, le=500, description="Records per page"),
    session: AsyncSession = Depends(get_db),
):
    base_query = select(DigitalMisNogMaster)
    count_query = select(func.count()).select_from(DigitalMisNogMaster)

    if search.strip():
        search_pattern = f"%{search.strip().upper()}%"
        search_filter = or_(
            func.upper(DigitalMisNogMaster.nog).like(search_pattern),
            func.upper(DigitalMisNogMaster.nog_1).like(search_pattern),
            func.upper(DigitalMisNogMaster.nog_2).like(search_pattern),
        )
        base_query = base_query.where(search_filter)
        count_query = count_query.where(search_filter)

    # total count (for search results OR full table)
    total_result = await session.execute(count_query)
    total = total_result.scalar()

    # apply pagination
    offset = (page - 1) * limit
    paginated_query = base_query.order_by(DigitalMisNogMaster.id).offset(offset).limit(limit)

    result = await session.execute(paginated_query)
    data = result.scalars().all()

    return {
        "status": "success",
        "count": len(data),
        "total": total,
        "page": page,
        "limit": limit,
        "total_pages": (total + limit - 1) // limit if total else 0,
        "data": [
            {
                "id": item.id,
                "nog": item.nog,
                "nog_1": item.nog_1,
                "nog_2": item.nog_2,
            }
            for item in data
        ],
    }


@router.post("/create/nog-master", status_code=status.HTTP_201_CREATED)
async def create_nog_master(
    payload: dict,
    session: AsyncSession = Depends(get_db),
):
    nog_val = payload.get("nog", "").strip().upper()
    if not nog_val:
        raise HTTPException(status_code=400, detail="NOG code is required.")

    existing = await session.execute(
        select(DigitalMisNogMaster).where(
            func.upper(DigitalMisNogMaster.nog) == nog_val
        )
    )
    if existing.scalars().first():
        raise HTTPException(
            status_code=400,
            detail=f"NOG '{nog_val}' already exists."
        )

    new_record = DigitalMisNogMaster(
        nog=nog_val,
        nog_1=payload.get("nog_1", "").strip(),
        nog_2=payload.get("nog_2", "").strip(),
    )

    session.add(new_record)
    await session.commit()
    await session.refresh(new_record)

    return {
        "status": "success",
        "message": "NOG record created successfully.",
        "data": {
            "id": new_record.id,
            "nog": new_record.nog,
            "nog_1": new_record.nog_1,
            "nog_2": new_record.nog_2,
        }
    }


@router.put("/update/nog-master/{item_id}")
async def update_nog_master(
    item_id: int,
    payload: dict,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DigitalMisNogMaster).where(DigitalMisNogMaster.id == item_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="NOG record not found.")

    nog_val = payload.get("nog", "").strip().upper()
    if not nog_val:
        raise HTTPException(status_code=400, detail="NOG code is required.")

    record.nog = nog_val
    record.nog_1 = payload.get("nog_1", "").strip()
    record.nog_2 = payload.get("nog_2", "").strip()

    await session.commit()
    await session.refresh(record)

    return {
        "status": "success",
        "message": "NOG record updated successfully.",
        "data": {
            "id": record.id,
            "nog": record.nog,
            "nog_1": record.nog_1,
            "nog_2": record.nog_2,
        }
    }


@router.delete("/delete/nog-master/{item_id}")
async def delete_nog_master(
    item_id: int,
    session: AsyncSession = Depends(get_db),
):
    result = await session.execute(
        select(DigitalMisNogMaster).where(DigitalMisNogMaster.id == item_id)
    )
    record = result.scalars().first()
    if not record:
        raise HTTPException(status_code=404, detail="NOG record not found.")

    await session.delete(record)
    await session.commit()

    return {"status": "success", "message": "NOG record deleted successfully."}


# ================= uplifting pivot====================================
@router.get("/uplifting/pivot-fields")
async def get_uplifting_pivot_data(
    from_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_db),
):
    try:
        mapper = inspect(DigitalReportsMisUpliftingPo)

        exclude_cols = {"id", "created_at", "report_date", "uploaded_by"}
        fields = [column.key for column in mapper.attrs if column.key not in exclude_cols]

        stmt = select(DigitalReportsMisUpliftingPo)

        # 🔹 Apply date range filter on report_date
        filters = []
        if from_date:
            filters.append(DigitalReportsMisUpliftingPo.report_date >= from_date)
        if to_date:
            filters.append(DigitalReportsMisUpliftingPo.report_date <= to_date)
        if filters:
            stmt = stmt.where(and_(*filters))

        stmt = stmt.limit(1000)

        result = await session.execute(stmt)
        rows = result.scalars().all()

        data = [{field: getattr(row, field) for field in fields} for row in rows]

        return {
            "status": "success",
            "total_records": len(data),
            "fields": fields,
            "data": data
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch uplifting pivot fields: {str(e)}"
        )


# ================= segregation pivot====================================
@router.get("/segregation/pivot-fields")
async def get_segregation_pivot_data(
    from_date: date | None = Query(None, description="Start date (YYYY-MM-DD)"),
    to_date: date | None = Query(None, description="End date (YYYY-MM-DD)"),
    session: AsyncSession = Depends(get_db),
):
    try:
        mapper = inspect(DigitalReportsMisSegregation)

        exclude_cols = {"id", "created_at", "report_date", "uploaded_by"}
        fields = [column.key for column in mapper.attrs if column.key not in exclude_cols]

        stmt = select(DigitalReportsMisSegregation)

        # 🔹 Apply date range filter on report_date
        filters = []
        if from_date:
            filters.append(DigitalReportsMisSegregation.report_date >= from_date)
        if to_date:
            filters.append(DigitalReportsMisSegregation.report_date <= to_date)
        if filters:
            stmt = stmt.where(and_(*filters))

        stmt = stmt.limit(1000)

        result = await session.execute(stmt)
        rows = result.scalars().all()

        data = [{field: getattr(row, field) for field in fields} for row in rows]

        return {
            "status": "success",
            "total_records": len(data),
            "fields": fields,
            "data": data
        }

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail=f"Failed to fetch segregation pivot fields: {str(e)}"
        )


# ====================== Pivot Report ==============================




def _to_detail(report, fields: PivotFieldsIn) -> PivotReportDetail:
    return PivotReportDetail(
        id=report.id,
        name=report.name,
        report_type=report.report_type,
        from_date=report.from_date,
        to_date=report.to_date,
        aggregation_type=report.aggregation_type,
        active_filters=report.active_filters,
        fields=fields,
        created_by=report.created_by,
        updated_at=report.updated_at,
    )


# ==================== LIST SAVED PIVOT REPORTS ==============================

@router.get("/pivot-reports/list", response_model=list[PivotReportListItem])
async def list_pivot_reports_route(
    report_type: Optional[PivotReportType] = Query(None),
    session: AsyncSession = Depends(get_db),
    # current_user=Depends(get_current_user),
):
    reports = await list_pivot_reports(session, report_type=report_type)
    return reports


# ==================== CREATE (SAVE NEW) PIVOT REPORT =========================

@router.post("/pivot-reports/create", response_model=PivotReportDetail)
async def create_pivot_report_route(
    payload: PivotReportCreate,
    session: AsyncSession = Depends(get_db),
    # current_user=Depends(get_current_user),
):
    try:
        report = await create_pivot_report(
            session, payload, created_by=None  
        )
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to save report: {e}")

    return _to_detail(report, payload.fields)


# ==================== GET SINGLE PIVOT REPORT (reopen in PivotBuilder) ======

@router.get("/pivot-reports/{report_id}", response_model=PivotReportDetail)
async def get_pivot_report_route(
    report_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    # current_user=Depends(get_current_user),
):
    report = await get_pivot_report(session, report_id)
    return _to_detail(report, _fields_to_schema(report.fields))


# ==================== UPDATE EXISTING PIVOT REPORT ===========================

@router.put("/pivot-reports/{report_id}/update", response_model=PivotReportDetail)
async def update_pivot_report_route(
    report_id: uuid.UUID,
    payload: PivotReportUpdate,
    session: AsyncSession = Depends(get_db),
    # current_user=Depends(get_current_user),
):
    try:
        report = await update_pivot_report(
            session, report_id, payload, updated_by=None  
        )
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to update report: {e}")

    return _to_detail(report, payload.fields)


# ==================== RENAME PIVOT REPORT =====================================

@router.patch("/pivot-reports/{report_id}/rename", response_model=PivotReportListItem)
async def rename_pivot_report_route(
    report_id: uuid.UUID,
    payload: PivotReportRename,
    session: AsyncSession = Depends(get_db),
    # current_user=Depends(get_current_user),
):
    try:
        report = await rename_pivot_report(
            session, report_id, payload.name, updated_by=None  
        )
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to rename report: {e}")

    return report


# ==================== DELETE PIVOT REPORT =====================================

@router.delete("/pivot-reports/{report_id}/delete")
async def delete_pivot_report_route(
    report_id: uuid.UUID,
    session: AsyncSession = Depends(get_db),
    # current_user=Depends(get_current_user),
):
    try:
        await delete_pivot_report(session, report_id)
        await session.commit()
    except HTTPException:
        await session.rollback()
        raise
    except Exception as e:
        await session.rollback()
        raise HTTPException(status_code=500, detail=f"Failed to delete report: {e}")

    return {"detail": "Report deleted"}
