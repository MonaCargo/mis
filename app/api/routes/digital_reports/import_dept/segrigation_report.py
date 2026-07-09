"""
Segregation Import upload endpoint.

POST /api/digital-reports/import/segregation/upload
"""

from typing import Optional

from fastapi import APIRouter, Depends, File, Form, HTTPException, Query, Response, UploadFile,status
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.dependency import verify_token_and_get_user
from app.db.session import get_db
from app.schemas.digital_reports.import_dept.operation_productivity_schema import ImportProductivityDashboardResponse, TruckInOutUploadResponse
from app.services.digital_reports.import_dpt.operation_productivity_report.import_emp_roaster import save_import_roster_report
from app.services.digital_reports.import_dpt.operation_productivity_report.import_pick_order import digital_report_save_pick_order_data
from app.services.digital_reports.import_dpt.operation_productivity_report.import_truck_in_out import DigitalReportImpTruckInOutService
from app.services.digital_reports.import_dpt.operation_productivity_report.operation_productivity_service import  ProductivityImportShiftService
from app.services.digital_reports.import_dpt.segrigation_report import generate_seg_report, process_seg_upload
from app.utils.digital_reports.import_dept.excel_report_builder.import_segrigation_excel_buider import build_csv, build_csv_detailed, build_excel, build_excel_detailed
from app.utils.digital_reports.import_dept.operation_productivity_report.imp_emp_roaster_cleaner import clean_import_roster_report
from app.utils.digital_reports.import_dept.operation_productivity_report.imp_pick_order_cleaner import clean_pick_order_report_data_for_digital_reports   # adjust to your project's DB dependency

router = APIRouter(
    prefix="/import",
    tags=["Digital Reports — Import — Segregation"],
)


@router.post(
    "/segrigation/upload",
    summary="Upload Segregation Import Report",
    response_description="Processing summary with insert / update / skip counts",
)
async def upload_segregation_file(
    file: UploadFile = File(..., description="CSV or Excel segregation report"),
    db: AsyncSession = Depends(get_db),
) -> JSONResponse:
    """
    Upload a Segregation Import report file (`.csv`, `.xlsx`, `.xls`).

    **Processing rules**

    - File type: only CSV and Excel accepted — anything else returns `400`.
    - **Flight** `(flight_no + flight_date)`: inserted once; re-uploads reuse the existing row.
    - **AWB** `(awb_no + sfx)` under a flight:
        - New AWB → **inserted**
        - Existing AWB, `pcs` or `gross_wgt` changed → **updated**
        - Existing AWB, no change → **skipped** (zero DB write)
    - AWBs that fail `normalize_awb_no` (not 10 or 11 digits) → **dropped**, returned in response for audit.
    - All datetimes stored as **UTC**; `flight_date` stored as plain **DATE**.
    - Weights stored in **kg**, 2 decimal places.

    **Response shape**
    ```json
    {
      "status": "success",
      "summary": {
        "total_rows_parsed": 558,
        "valid_rows_processed": 556,
        "dropped_awb_count": 2,
        "dropped_awbs": [
          {
            "reason": "invalid_awb_format",
            "original_awb": "BADVAL",
            "flight_no": "AI0158",
            "flight_date": "2026-06-21",
            "sfx": "P",
            "row_index": 42
          }
        ],
        "flights_created": 76,
        "flights_existing": 0,
        "awbs_inserted": 556,
        "awbs_updated": 0,
        "awbs_skipped": 0
      }
    }
    ```
    """
    result = await process_seg_upload(file=file, db=db)

    return JSONResponse(
        status_code=200,
        content={
            "status":  "success",
            "summary": _serialise(result),
        },
    )


# ─────────────────────────────────────────────────────────────────────────────
# Helpers
# ─────────────────────────────────────────────────────────────────────────────

def _serialise(obj):
    """
    Recursively make the result dict JSON-safe.
    Converts: date → ISO string, datetime → ISO string, Decimal → float,
              any other non-serialisable type → str.
    """
    import math
    from datetime import date, datetime
    from decimal import Decimal

    if isinstance(obj, dict):
        return {k: _serialise(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_serialise(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj






# =======================================>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>>




"""
routers/digital_reports/import_dept/seg_report_router.py

GET /api/digital-reports/import/segregation/report
  ?from_dt=2026-07-01T00:00:00
  &to_dt=2026-07-07T23:59:59
  &format=xlsx          (default) | csv
"""

from datetime import datetime, timedelta, timezone, date
from zoneinfo import ZoneInfo
from decimal import Decimal





IST = ZoneInfo("Asia/Kolkata")
UTC = timezone.utc

def _parse_dt(value: str, field: str) -> datetime:
    """
    Parse ISO datetime string → UTC-aware datetime.
    Accepts:
      - "2026-07-01T00:00:00"         (naive → assumed IST → converted to UTC)
      - "2026-07-01T00:00:00+05:30"   (IST-aware → converted to UTC)
      - "2026-07-01T00:00:00Z"        (UTC-aware → kept as-is)
    """
    try:
        dt = datetime.fromisoformat(value.replace("Z", "+00:00"))
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid datetime format for '{field}'. Use ISO 8601: YYYY-MM-DDTHH:MM:SS",
        )
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=IST)
    return dt.astimezone(UTC)




def _jsonify(obj):
    """
    Make the report dict JSON-safe for JSONResponse.
    date/datetime → ISO string, Decimal → float, NaN → None.
    """
    import math
    if isinstance(obj, dict):
        return {k: _jsonify(v) for k, v in obj.items()}
    if isinstance(obj, list):
        return [_jsonify(v) for v in obj]
    if isinstance(obj, datetime):
        return obj.isoformat()
    if isinstance(obj, date):
        return obj.isoformat()
    if isinstance(obj, Decimal):
        return float(obj)
    if isinstance(obj, float) and math.isnan(obj):
        return None
    return obj


@router.get(
    "/report-montaly-segration",
    summary="Segregation Import Report — JSON (table) or file (xlsx/csv)",
    responses={
        200: {"description": "Report JSON, or Excel/CSV file"},
        400: {"description": "Invalid parameters or date range > 31 days"},
        404: {"description": "No data found (file formats only)"},
    },
)
async def download_seg_report(
    from_dt: str = Query(..., description="Start datetime ISO 8601",
                         example="2026-07-01T00:00:00"),
    to_dt: str = Query(..., description="End datetime ISO 8601",
                       example="2026-07-31T23:59:59"),
    fmt: str = Query(
        default="xlsx",
        alias="format",
        description="Output: 'json' (table data) | 'xlsx' | 'csv'",
        pattern="^(json|xlsx|csv)$",
    ),
    detailed: bool = Query(
        default=True,
        description="Include per-flight breakdown. Always true for the UI table.",
    ),
    show_zeros: bool = Query(
        default=True,
        description="If any col box have value zero then show it to empty (null) in the report. Only applicable for file formats (xlsx/csv).",
    ),
    db: AsyncSession = Depends(get_db),
):
    """
    - `format=json` → returns the full report dict (used by the React table).
      Always 200, even with no data (UI shows an empty state).
    - `format=xlsx` / `format=csv` → returns a downloadable file.
      Returns 404 if no data in range.
    - Max 31-day range enforced (400 on violation).
    - `detailed=true` includes per-flight rows under each airline.
    """
    from_datetime = _parse_dt(from_dt, "from_dt")
    to_datetime   = _parse_dt(to_dt,   "to_dt")

    try:
        report = await generate_seg_report(
            db       = db,
            from_dt  = from_datetime,
            to_dt    = to_datetime,
            detailed = detailed,
        )
    except ValueError as exc:
        raise HTTPException(status_code=400, detail=str(exc))

    # ── JSON: always 200, even when empty (UI renders "no data") ─────────────
    if fmt == "json":
        return JSONResponse(content=_jsonify(report))

    # ── File formats: 404 when there's nothing to export ─────────────────────
    # if report["grand_total"]["awb_count"] == 0:
    if report["grand_total"]["mawb_count"] == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for the range {from_dt} to {to_dt}.",
        )

    date_tag = f"{from_datetime.strftime('%Y%m%d')}_{to_datetime.strftime('%Y%m%d')}"

    if fmt == "csv":
        content    = build_csv_detailed(report,show_zeros=show_zeros) if detailed else build_csv(report,show_zeros=show_zeros)
        media_type = "text/csv"
        filename   = f"seg_import_report_{date_tag}.csv"
    else:  # xlsx
        content    = build_excel_detailed(report,show_zeros=show_zeros) if detailed else build_excel(report,show_zeros=show_zeros)
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename   = f"seg_import_report_{date_tag}.xlsx"

    return Response(
        content    = content,
        media_type = media_type,
        headers    = {
            "Content-Disposition": f'attachment; filename="{filename}"',
            "Content-Length":      str(len(content)),
        },
    )














# =======================✌️✌️✌️✌️✌️  Import Productivity dashboard Report routes ========================
"""
Import Operations Productivity Dashboard API.

GET /api/import-dashboard?from_ist=2026-06-01T00:00:00&to_ist=2026-06-29T00:00:00

Dates are interpreted as IST. `to_ist` is exclusive. Defaults to "today in IST"
(00:00 -> next 00:00) when omitted.
"""

@router.post(
    "/import/upload/imp-truck-in-out",
    response_model=TruckInOutUploadResponse,
    summary="Upload Import Truck IN/OUT report",
    description=(
        "Upload route for the Import Truck IN/OUT report."
        "Accepts the COSYS **Import Truck IN/OUT** Excel or CSV export. "
        "Parses, cleans, converts all timestamps to UTC, and inserts into "
        "`dr_imp_truck_in_out` in batches of 600 rows.\n\n"
        "Duplicate `gp_no` rows are silently skipped (ON CONFLICT DO NOTHING).\n\n"

        "(useful for re-uploads of the same date)."
    ),
)
async def upload_imp_truck_in_out(
    file: UploadFile = File(
        ...,
        description="COSYS Import Truck IN/OUT export (.xlsx, .csv)"
    ),
   
    db: AsyncSession = Depends(get_db),
):
    result = await DigitalReportImpTruckInOutService.upload(
        file=file,
        db=db,

    )

    if result["status"] == "failed":
        return JSONResponse(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            content=result,
        )

    return result




# ---------->>>>>
IST = timezone(timedelta(hours=5, minutes=30))
@router.get("/import/operation-productivity", response_model=ImportProductivityDashboardResponse)
async def get_import_dashboard(
    report_date: Optional[date] = Query(
        None,
        description="IST calendar date. Operating day = 06:00 IST that day to 06:00 IST next day. Defaults to yesterday IST.",
    ),
    db: AsyncSession = Depends(get_db),
) -> ImportProductivityDashboardResponse:
    if report_date is None:
        report_date = (datetime.now(IST) - timedelta(days=1)).date()
 
    service = ProductivityImportShiftService(db)
    return await service.build(report_date)






@router.post("/import/pick-order/upload")
async def upload_pick_order(
    file: UploadFile = File(...),
    report_date: date = Form(..., description="Operator-selected report day (YYYY-MM-DD)."),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
) -> dict:
    
    _ALLOWED_EXT = (".xlsx", ".xls",".csv")
    if not file.filename or not file.filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx, .xls or .csv file.")
 
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
 
    # Parse / clean (pure, no DB).
    try:
        rows = clean_pick_order_report_data_for_digital_reports(file_bytes,file.filename or "",report_date=report_date)
    except Exception as exc:  # noqa: BLE001 — surface a clean 400 to the client
        raise HTTPException(status_code=400, detail=f"Couldn't read the report: {exc}") from exc
 
    if not rows:
        raise HTTPException(status_code=400, detail="No data rows found in the report.")
 
    # Atomic replace for this report_date.
    summary = await digital_report_save_pick_order_data(
        db=db,
        report_date=report_date,
        rows=rows,
        uploaded_by=current_user.emp_id,   # set from auth when available
    )
    return {
        "status": "ok",
        "message": (
            f"Saved {summary['inserted']} rows for {summary['report_date']} "
            f"(replaced {summary['deleted']})."
        ),
        **summary,
    }







# ===========================Import Roaster Upload route =========================
@router.post("/import-roaster-report/upload")
async def upload_roster(
    file: UploadFile = File(...),
    allow_multiple_shifts_per_day: bool = Form(True),
    db: AsyncSession = Depends(get_db),
    # uploaded_by: str = Depends(current_user),   # wire to your auth if available
) -> dict:
    _ALLOWED_EXT = (".xlsx", ".xls", ".csv")
    if not file.filename or not file.filename.lower().endswith(_ALLOWED_EXT):
        raise HTTPException(status_code=400, detail="Please upload an .xlsx, .xls or .csv file.")
 
    file_bytes = await file.read()
    if not file_bytes:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")
 
    # Parse / clean (pure, no DB).
    try:
        rows = clean_import_roster_report(file_bytes, file.filename or "")
    except Exception as exc:  # noqa: BLE001
        raise HTTPException(status_code=400, detail=f"Couldn't read the roster: {exc}") from exc
 
    if not rows:
        raise HTTPException(status_code=400, detail="No valid roster rows found in the file.")
 
    # Upsert (employees + attendance), idempotent.
    summary = await save_import_roster_report(
        session=db,
        rows=rows,
        allow_multiple_shifts_per_day=allow_multiple_shifts_per_day,
        uploaded_by=None,   # set from auth when available
    )
    return {
        "status": "ok",
        "message": (
            f"Roster saved: {summary['attendance_upserted']} attendance rows, "
            f"{summary['employees_upserted']} employees"
            + (f", {summary['shifts_replaced']} shift(s) replaced"
               if summary.get("shifts_replaced") else "")
            + "."
        ),
        **summary,
    }
 