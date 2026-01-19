# routes/domestic_xray.py
from io import BytesIO
import math
from fastapi import APIRouter, Body, Depends, HTTPException, UploadFile, File, Form, Query,BackgroundTasks
import pandas as pd
import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from typing import List, Optional
from datetime import date, datetime
from app.core.dependency import verify_token_and_get_user
from app.db.session import get_db, async_session
from app.schemas.importOperation.worker_assignment import PaginationMetadata
from app.schemas.user import UserRead
from app.services.domesticOperation.domestic_xray_report import DomesticXrayService
from app.schemas.domesticOperation.domestic_xray_report import (
    DomesticXrayResponse,
    DomesticXrayUpdate,
    DomesticXrayUploadResponse,
    DomesticXrayFilterParams,
    DomesticXrayListResponse,
    EmployeeResponse,
    GenericSearchResultResponse,
    PdfGenerateStatusUpdate,
    EmailStatusUpdate,
    BulkActionResponse,
    # SecurityDeclarationCreate
)
from app.db.models.domesticOperation.domestic_xray_report import DomesticXray, DomesticXrayEmployee
from apscheduler.schedulers.asyncio import AsyncIOScheduler

router = APIRouter(prefix="/xray", tags=[""])



# scheduler = AsyncIOScheduler()

# @scheduler.scheduled_job("interval", minutes=10)
# async def retry_failed_emails():
#     async with async_session() as db:
#         stmt = select(DomesticXray).where(
#             DomesticXray.is_email_sent == False,
#             DomesticXray.retry_count < 3
#         )
#         result = await db.execute(stmt)
#         failed_records = result.scalars().all()

#         for record in failed_records:
#             await DomesticXrayService.background_send_email(
#                 db, record.awb_no, record.seq_num, f"static/pdfs/{record.awb_no}.pdf"
#             )

# scheduler.start()


# ========= IT IS USED FOR CONVERTING IST DAY TO UTC RANGE =================
from datetime import date, datetime, timedelta
import pytz

def convert_ist_day_to_utc_range(d: date | None):
    if not d:
        return None, None

    ist = pytz.timezone("Asia/Kolkata")

    start_ist = ist.localize(
        datetime.combine(d, datetime.min.time())
    )

    end_ist = ist.localize(
        datetime.combine(d, datetime.max.time())
    )

    return start_ist.astimezone(pytz.UTC), end_ist.astimezone(pytz.UTC)


@router.post("/upload", response_model=DomesticXrayUploadResponse)
async def upload_domestic_xray_file(
    file: UploadFile = File(..., description="Excel or CSV file to upload"),
    # cosys_report_date: date = Form(..., description="Report date (YYYY-MM-DD)"),
    # uploaded_by: str = Form(..., description="Username of uploader"),
    # header_row: int = Form(default=5, description="Row number containing headers"),
    current_user: UserRead = Depends(verify_token_and_get_user),
    db: AsyncSession = Depends(get_db)
):
    """
    Upload and process domestic x-ray report file.
    
    - **file**: Excel (.xlsx, .xls) or CSV (.csv) file
    - **cosys_report_date**: Date of the report from COSYS system
    - **uploaded_by**: Username or ID of the person uploading
    - **header_row**: Row number where headers are located (default: 5)
    
    Returns upload statistics and processed record count.
    """
    result = await DomesticXrayService.upload_and_process_file(
        db=db,
        file=file,
        # cosys_report_date=cosys_report_date,
        uploaded_by=current_user.emp_id,
        # header_row=header_row
    )
    
    return result

@router.get("/records", response_model=DomesticXrayListResponse)
async def get_domestic_xray_records(
    # awb_no: Optional[str] = Query(None, description="Filter by AWB number"),
    # destination: Optional[str] = Query(None, description="Filter by destination"),
    # agent_name: Optional[str] = Query(None, description="Filter by agent name"),
    # xray_type: Optional[str] = Query(None, description="Filter by X-ray type"),
    # uploaded_by: Optional[str] = Query(None, description="Filter by uploader"),
    start_date: Optional[date] = Query(None, description="Filter from date"),
    end_date: Optional[date] = Query(None, description="Filter to date"),
    # is_pdf_generated: Optional[bool] = Query(None, description="Filter by print status"),
    # is_email_sent: Optional[bool] = Query(None, description="Filter by email status"),
    xray_filter_status: Optional[str] = Query(None, description="Filter by X-ray filter status"),
    page: int = Query( default=1,ge=1, description="Number of records to skip"),
    # page_size: int = Query(default=600, ge=1, le=1200, description="Number of records per page"),
    page_size: int = Query(default=20, ge=1, le=1000, description="Number of records to return"),
    db: AsyncSession = Depends(get_db)   # use AsyncSession here
):
    """
    Get filtered list of domestic x-ray records with pagination.
    
    Supports multiple filter parameters and returns paginated results.
    """

    print(start_date,end_date,"-------------------------")

    utc_start, _ = convert_ist_day_to_utc_range(start_date)
    _, utc_end = convert_ist_day_to_utc_range(end_date)

    records, total = await DomesticXrayService.get_filtered_records(db, xray_filter_status,start_date=utc_start,end_date=utc_end, page=page ,
        page_size=page_size,)
    

     # -------- PAGINATION (INLINE) --------
    # current_page = (page // page_size) + 1
    total_pages = math.ceil(total / page_size) if total > 0 else 1

    pagination = PaginationMetadata(
        current_page=page,
        page_size=page_size,
        total_records=total,
        total_pages=total_pages,
        has_previous=page > 1,
        has_next=page < total_pages,
        previous_page=page - 1 if page > 1 else None,
        next_page=page + 1 if page < total_pages else None,
    )
    
    return {
        'message': 'Records fetched successfully',
        'success': True,
        'pagination': pagination,
        'data': records
    }



@router.post("/generate-pdf")
async def generate_pdf(payload: dict, background_tasks: BackgroundTasks, db: AsyncSession = Depends(get_db)):
    result = await DomesticXrayService.generate_and_save_pdf(payload, db)

    # Trigger background email+delete
    if result["success"]:
        background_tasks.add_task(
            DomesticXrayService.background_send_email,
            db, result["awb_no"], result["doc_no"], result["pdf_path"]
        )

    return result


@router.post("/generate-pdf-send-mail-batch")
async def generate_security_pdf_batch_route(
    background_tasks: BackgroundTasks,
    start_date: str ,
    end_date: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Generate PDFs and send emails for all records in date range
    where PDF and email are not yet processed.
    """
    # start_date = date_range.get("start_date")
    # end_date = date_range.get("end_date")

    try:
         start_dt = datetime.fromisoformat(start_date) 
         end_dt = datetime.fromisoformat(end_date) 
    except ValueError: 
        return {"success": False, "message": "Invalid date format. Use ISO format YYYY-MM-DD or YYYY-MM-DDTHH:MM:SS"}

    records = await DomesticXrayService.fetch_pending_records(db, start_dt, end_dt)
    results = []

    total_pdf_generated = 0
    total_email_queued = 0
    total_skipped_record = 0

    for record in records:
        if (record.awb_no.startswith("098") or record.awb_no.startswith("775")):
            res = await DomesticXrayService.generate_and_save_pdf(record, db)
            if res.get("success"):
                total_pdf_generated += 1
                background_tasks.add_task(
                    DomesticXrayService.background_send_email,
                    db, res["awb_no"], res["doc_no"], res["pdf_path"]
                )
                res["email_status"] = {
                    "queued": True, "awb_no": res["awb_no"], "doc_no": res["doc_no"]
                    }
                total_email_queued += 1
            else:
                res["email_status"] = {"queued": False}
            results.append(res)

        else:
            total_skipped_record += 1
            results.append({
                "success": False,
                "awb_no": record.awb_no,
                "message": "Skipped - AWB number not eligible for processing"
            })

    return {
        "success": True,
        "message": f" Successfully Processed {len(records)} records",
         "total_pdf_generated": total_pdf_generated, 
         "total_email_queued": total_email_queued,
        "total_skipped_record": total_skipped_record,
         "results": results
        }


@router.get(
    "/generic-search",
    response_model=GenericSearchResultResponse,
    description="Search domestic XRAY records by awb_no or seq_num",
)
async def search_domestic_xray_api(
    type: str = Query(..., description="awb_no | seq_num"),
    term: str = Query(..., description="Search value"),
    db: AsyncSession = Depends(get_db),
):
    data = await DomesticXrayService.search_domestic_xray(
        db=db,
        search_type=type,
        search_value=term,
    )

    return GenericSearchResultResponse(
        status="success",
        success=True,
        message="Search completed",
        data=data,
        total=len(data),
        your_search_type=type,
        your_search_value=term,
    )



@router.get("/records/{record_id}", response_model=DomesticXrayResponse)
def get_domestic_xray_by_id(
    record_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Get a specific domestic x-ray record by ID.
    """
    record = DomesticXrayService.get_by_id(db, record_id)
    
    if not record:
        raise HTTPException(status_code=404, detail="Record not found")
    
    return record

@router.get("/records/awb/{awb_no}", response_model=List[DomesticXrayResponse])
def get_domestic_xray_by_awb(
    awb_no: str,
    db: AsyncSession = Depends(get_db)
):
    """
    Get all records for a specific AWB number.
    """
    records = DomesticXrayService.get_by_awb(db, awb_no)
    
    if not records:
        raise HTTPException(status_code=404, detail="No records found for this AWB")
    
    return records

@router.patch("/records/{record_id}", response_model=DomesticXrayResponse)
def update_domestic_xray_record(
    record_id: int,
    update_data: DomesticXrayUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update a domestic x-ray record.
    
    Only specified fields will be updated.
    """
    record = DomesticXrayService.update_record(db, record_id, update_data)
    return record

@router.post("/records/pdf-generate-status", response_model=BulkActionResponse)
def update_print_status(
    record_ids: List[int],
    status_update: PdfGenerateStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update print status for multiple records.
    
    - **record_ids**: List of record IDs to update
    - **print_date_time**: Print timestamp (optional, defaults to current time)
    """
    result = DomesticXrayService.update_print_status(db, record_ids, status_update)
    return result

@router.post("/records/email-status", response_model=BulkActionResponse)
def update_email_status(
    record_ids: List[int],
    status_update: EmailStatusUpdate,
    db: AsyncSession = Depends(get_db)
):
    """
    Update email status for multiple records.
    
    - **record_ids**: List of record IDs to update
    - **is_email_sent**: Email sent status (default: true)
    - **email_sent_date_time**: Email sent timestamp (optional, defaults to current time)
    """
    result = DomesticXrayService.update_email_status(db, record_ids, status_update)
    return result

@router.delete("/records/{record_id}")
def delete_domestic_xray_record(
    record_id: int,
    db: AsyncSession = Depends(get_db)
):
    """
    Delete a specific domestic x-ray record.
    """
    success = DomesticXrayService.delete_record(db, record_id)
    
    return {
        'success': success,
        'message': f'Record {record_id} deleted successfully'
    }

@router.get("/statistics")
def get_statistics(
    start_date: Optional[date] = Query(None, description="Statistics from date"),
    end_date: Optional[date] = Query(None, description="Statistics to date"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get statistics for domestic x-ray reports.
    
    Returns counts, distributions, and other aggregate data.
    """
    stats = DomesticXrayService.get_statistics(db, start_date, end_date)
    return stats

@router.get("/destinations")
def get_unique_destinations(db: AsyncSession = Depends(get_db)):
    """
    Get list of unique destinations.
    """
    
    destinations = db.query(DomesticXray.destination)\
        .filter(DomesticXray.destination.isnot(None))\
        .distinct()\
        .order_by(DomesticXray.destination)\
        .all()
    
    return {'destinations': [d[0] for d in destinations]}

@router.get("/agents")
def get_unique_agents(db: AsyncSession = Depends(get_db)):
    """
    Get list of unique agent names.
    """
    
    agents = db.query(DomesticXray.agent_name)\
        .filter(DomesticXray.agent_name.isnot(None))\
        .distinct()\
        .order_by(DomesticXray.agent_name)\
        .all()
    
    return {'agents': [a[0] for a in agents]}

@router.get("/xray-types")
def get_xray_types(db: AsyncSession = Depends(get_db)):
    """
    Get list of unique X-ray types.
    """
    
    xray_types = db.query(DomesticXray.xray_type)\
        .filter(DomesticXray.xray_type.isnot(None))\
        .distinct()\
        .order_by(DomesticXray.xray_type)\
        .all()
    
    return {'xray_types': [x[0] for x in xray_types]}



# =================== Domestic Xray Employee Routes ===================
# routes.py

@router.post("/upload-xray-employee-file")
async def upload_employee_file(file: UploadFile = File(...), db: AsyncSession = Depends(get_db)):
    contents = await file.read()
    df = pd.read_excel(BytesIO(contents))

    # Select & rename columns
    df = df.iloc[:, 1:4]
    df = df.rename(columns={
        'COD_STF_IDE': 'employee_id',
        'NAM_STF': 'employee_name',
        'COD_STF_INI': 'xray_user_id'
    })

    # Clean xray_user_id
    df['xray_user_id'] = df['xray_user_id'].apply(DomesticXrayService.clean_xray_user_id)

    # Bulk insert
    employees = await DomesticXrayService.bulk_create_employees(db, df)
    return {"inserted": len(employees)}


@router.get("/domestic-employees", response_model=List[EmployeeResponse])
async def list_employees(db: AsyncSession = Depends(get_db)):
    return await DomesticXrayService.get_domestic_xray_employees(db)  # Return directly, no dict wrapper

@router.get("/{user_id}", response_model=EmployeeResponse)
async def get_employee(user_id: str, db: AsyncSession = Depends(get_db)):
    emp = await DomesticXrayService.get_domestic_employee_by_user_id(db, user_id)
    if not emp:
        raise HTTPException(status_code=404, detail="Employee not found")
    return emp

