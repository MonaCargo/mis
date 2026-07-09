
from typing import Optional

from fastapi import APIRouter, Depends, UploadFile, File, Form, HTTPException, Query
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date, datetime
from app.db.session import get_db  
from sqlalchemy import insert
import pandas as pd
import os
from app.services.digital_reports.customer_care_dpt.xray_customer_care_service import MISReportService, XrayPerformanceCalculator 

router = APIRouter(
    # prefix="/mis",
    # tags=["X-Ray Reports Upload"]
)

# =========================================================================
#  EXPORT NORMAL UPLOAD API
# =========================================================================
@router.post("/upload/export-xray")
async def upload_export_xray(
    file: UploadFile = File(...),
    target_date: date = Form(..., description="Target execution date in YYYY-MM-DD format"),
    delete_previous: bool = Form(False, description="If True, clears previous database entries for this date"),
    db: AsyncSession = Depends(get_db)
):
    
    if not file.filename.endswith(('.csv', '.CSV')):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
        
    return await MISReportService.process_export_normal(
        file=file, 
        target_date=target_date, 
        delete_previous=delete_previous, 
        db=db,
        uploaded_by="System_User"
    )


# =========================================================================
# EXPORT TRANSHIPMENT (TP) UPLOAD API
# =========================================================================
@router.post("/upload/export-tp-xray")
async def upload_export_tp_xray(
    file: UploadFile = File(...),
    target_date: date = Form(..., description="Target execution date in YYYY-MM-DD format"),
    delete_previous: bool = Form(False, description="If True, clears previous database entries for this date"),
    db: AsyncSession = Depends(get_db)
):
   
    if not file.filename.endswith(('.csv','.CSV')):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
        
    return await MISReportService.process_export_tp(
        file=file, 
        target_date=target_date, 
        delete_previous=delete_previous, 
        db=db,
        uploaded_by="System_User"
    )


# =========================================================================
# IMPORT DIGITAL REPORT UPLOAD API
# =========================================================================
@router.post("/upload/import-xray")
async def upload_import_xray(
    file: UploadFile = File(...),
    target_date: date = Form(..., description="Target execution date in YYYY-MM-DD format"),
    delete_previous: bool = Form(False, description="If True, clears previous database entries for this date"),
    db: AsyncSession = Depends(get_db)
):
   
    if not file.filename.endswith(('.csv','.CSV')):
        raise HTTPException(status_code=400, detail="Only CSV files are supported.")
        
    return await MISReportService.process_import_digital(
        file=file, 
        target_date=target_date, 
        delete_previous=delete_previous, 
        db=db,
        uploaded_by="System_User"
    )


@router.get("/xray-performance-range")
async def get_xray_performance_range(
    report_date: date = Query(..., description="The operational date to generate report for"),
    db: AsyncSession = Depends(get_db),
):
    # CHANGE THIS LINE to use XrayPerformanceCalculator:
    report_payload = await XrayPerformanceCalculator.get_single_operational_day_report(db, report_date)
    return {
        "success": True,
        "data": report_payload
    }


@router.post("/upload/xray-performance")
async def upload_xray_report(
    file: UploadFile,
      db: AsyncSession = Depends(get_db)):
    result = await MISReportService.process_and_save_xray_performance_report(file, db)
    
    return result
@router.get("/xray/performance/monthly")
async def get_monthly_xray_performance_report(
    report_month: Optional[str] = Query(None, description="Filter by a specific month (Format: YYYY-MM)"),
    
    db: AsyncSession = Depends(get_db)
):
   
    result = await MISReportService.get_monthly_xray_performance_report(
        db=db,
        
        report_month=report_month
    )
    return result