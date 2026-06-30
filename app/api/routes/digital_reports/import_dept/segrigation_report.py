"""
routers/digital_reports/import_dept/seg_import_router.py

Segregation Import upload endpoint.

POST /api/digital-reports/import/segregation/upload
"""

from fastapi import APIRouter, Depends, File, HTTPException, Query, Response, UploadFile
from fastapi.responses import JSONResponse
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db
from app.services.digital_reports.import_dpt.segrigation_report import generate_seg_report, process_seg_upload
from app.utils.digital_reports.import_dept.excel_report_builder.import_segrigation_excel_buider import build_csv, build_csv_detailed, build_excel, build_excel_detailed   # adjust to your project's DB dependency

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

from datetime import datetime, timezone, date
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
    if report["grand_total"]["awb_count"] == 0:
        raise HTTPException(
            status_code=404,
            detail=f"No data found for the range {from_dt} to {to_dt}.",
        )

    date_tag = f"{from_datetime.strftime('%Y%m%d')}_{to_datetime.strftime('%Y%m%d')}"

    if fmt == "csv":
        content    = build_csv_detailed(report) if detailed else build_csv(report)
        media_type = "text/csv"
        filename   = f"seg_import_report_{date_tag}.csv"
    else:  # xlsx
        content    = build_excel_detailed(report) if detailed else build_excel(report)
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