# app/api/v1/endpoints/worker_assignment_api.py
from datetime import date, datetime, time
import traceback
from typing import List, Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
import pytz
from fastapi import Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependency import require_roles, verify_token_and_get_user
from app.db.models.importOperation.worker_assignment import WorkerAssignment
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.importOperation.worker_assignment import AssignDropDlvZoneRequest, PaginatedWorkerAssignmentResponse, RequestOfWorkerAssignment, ResponseOfWorkerAssignment, WorkerAssignmentExportRequest, WorkerAssignmentRequest, WorkerAssignmentResponseForWorker, WorkerAssignmentResponseForWorkerLists, WorkerAssignmentSearchRequest
from app.schemas.user import UserListResponse, UserRead
from app.services.importOperation.worker_assignment_service import add_drop_dlv_zone_by_assigned_worker, assign_user_to_worker_assignment, generate_excel_stream_export_worker_assignment, get_all_allowed_users_as_worker, get_all_worker_assignments_list, get_paginated_worker_assignments_data_list, get_worker_assignment_lists_by_emp_id, process_worker_assignment, search_in_worker_assignments
from app.utils.common.get_request_ip import get_request_ip

router = APIRouter(prefix="/worker-assignment", tags=[""])



IST = ZoneInfo("Asia/Kolkata")
UTC = ZoneInfo("UTC")



def ist_to_utc_range(date_str: str):
    date_obj = datetime.strptime(date_str, "%Y-%m-%d")

    start_ist = datetime.combine(date_obj, time.min).replace(tzinfo=IST)
    end_ist = datetime.combine(date_obj, time.max).replace(tzinfo=IST)

    return start_ist.astimezone(UTC), end_ist.astimezone(UTC)





@router.post("/process-and-save")
async def process_worker_assignment_api(
    req: WorkerAssignmentRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        date_str = req.date
        # Handle datetime -> string
        if isinstance(date_str, datetime):
            date_str = date_str.date().strftime("%Y-%m-%d")

        # Handle date -> string
        elif isinstance(date_str, date):
            date_str = date_str.strftime("%Y-%m-%d")

        # Already string? OK
        elif isinstance(date_str, str):
            pass

        else:
            raise HTTPException(status_code=400, detail="Invalid date format")


    except ValueError:
        raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

    return await process_worker_assignment(db, req)


@router.get(
    "/generic-search",
    response_model=WorkerAssignmentResponseForWorkerLists,
    description="Search worker assignments by oc_no, gp_no, temp_oc, awb, hawb"
)
async def search_worker_assignment(
    type: str = Query(..., description="oc_no | gp_no | temp_oc | awb | hawb"),
    term: str = Query(..., description="Search value"),
    db: AsyncSession = Depends(get_db)
):

    data = await search_in_worker_assignments(
        db,
        search_type=type,
        search_value=term
    )

    return WorkerAssignmentResponseForWorkerLists(
        status="success",
        success=True,
        message="Search completed",
        data=data,
        total=len(data),
        your_search_type=type,
        your_search_value=term
    )



















# @router.get("/get-all-user-assignment-list-data-by-filter")
# async def get_all_user_assignment_data(
#     status: str = Query("all"),
#     startDate: str = Query(None),
#     endDate: str = Query(None),
#     db: AsyncSession = Depends(get_db)
# ):

#     # ---------------- HELPERS ---------------- #

#     def convert_ist_day_to_utc_range(date_str: str):
#         """Convert YYYY-MM-DD in IST to complete UTC day range."""
#         ist = pytz.timezone("Asia/Kolkata")
#         d = datetime.strptime(date_str, "%Y-%m-%d")

#         start_ist = ist.localize(d.replace(hour=0, minute=0, second=0))
#         end_ist = ist.localize(d.replace(hour=23, minute=59, second=59, microsecond=999999))

#         return start_ist.astimezone(pytz.UTC), end_ist.astimezone(pytz.UTC)


#     # ---------------- MODULAR FILTERS ---------------- #

#     def filter_dlv_zone(query, status: str):
#         """Filter based on whether dlv_zone exists or not."""
#         if status == "dlv_added":
#             # Show only rows where dlv zone exists
#             return query.where(
#                 WorkerAssignment.drop_dlv_zone.isnot(None),
#                 func.trim(WorkerAssignment.drop_dlv_zone) != ""
#             )

#         # For all other statuses → show only rows where dlv zone is empty
#         return query.where(
#             or_(
#                 WorkerAssignment.drop_dlv_zone.is_(None),
#                 func.trim(WorkerAssignment.drop_dlv_zone) == ""
#             )
#         )


#     def filter_status(query, status: str):
#         """Filter assigned/unassigned status (after dlv filter)."""
#         if status == "assigned":
#             return query.where(WorkerAssignment.assigned_person.isnot(None))

#         if status == "unassigned":
#             return query.where(WorkerAssignment.assigned_person.is_(None))

#         # status == "all" → no assignment filter
#         return query


#     def filter_dates(query, startDate: str, endDate: str):
#         """Filter on integrate_date_time / gate_pass_issued_date."""
#         if not (startDate and endDate):
#             return query

#         utc_start, _ = convert_ist_day_to_utc_range(startDate)
#         _, utc_end = convert_ist_day_to_utc_range(endDate)

#         return query.where(
#             or_(
#                 WorkerAssignment.integrate_date_time.between(utc_start, utc_end),
#                 WorkerAssignment.gate_pass_issued_date_time_combo.between(utc_start, utc_end)
#             )
#         )


#     # ---------------- MAIN QUERY BUILDER ---------------- #

#     query = select(WorkerAssignment)

#     query = filter_dlv_zone(query, status)      # 1️⃣ First filter dlv_zone
#     query = filter_status(query, status)        # 2️⃣ Then apply assigned/unassigned
#     query = filter_dates(query, startDate, endDate)  # 3️⃣ Apply date filters

#     query = query.order_by(WorkerAssignment.id.desc())

#     result = await db.execute(query)
#     return result.scalars().all()




@router.get(
    "/get-all-user-assignment-list-data-by-filter",
    response_model=PaginatedWorkerAssignmentResponse,
    summary="Get paginated worker assignments with filters",
    description="Retrieve filtered, paginated worker assignments including matrix analytics."
)
async def get_paginated_worker_assignments(
    assignment_status: str = Query(default="all"),
    startDate: Optional[str] = Query(default=None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    endDate: Optional[str] = Query(default=None, regex=r"^\d{4}-\d{2}-\d{2}$"),


    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=200),

    db: AsyncSession = Depends(get_db)
):
    """
    Improved API for worker assignment pagination with strict validation.
    """



        # -------------------------------------------------------
    # HELPER: Validate Date Format (YYYY-MM-DD)
    # -------------------------------------------------------
    def validate_date(date_str: str, field_name: str):
        try:
            return datetime.strptime(date_str, "%Y-%m-%d")
        except ValueError:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid {field_name}: '{date_str}'. Expected format YYYY-MM-DD."
            )


    # -------------------------------------------------------
    # HELPER: Validate Status Enum
    # -------------------------------------------------------
    def validate_status(status_value: str):
        # allowed = ["all", "assigned", "unassigned", "dlv_added"]
        allowed = ["all", "assigned", "unassigned", "dlv_added", "assigned_but_not_delivered"]

        if status_value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{status_value}'. Allowed: {allowed}"
            )
        return status_value


    try:
        # -----------------------------------------------------------
        # 1️⃣ VALIDATE STATUS
        # -----------------------------------------------------------
        assignment_status = validate_status(assignment_status)

        # -----------------------------------------------------------
        # 2️⃣ VALIDATE DATE Inputs
        # -----------------------------------------------------------
        if (startDate and not endDate) or (endDate and not startDate):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Both startDate and endDate must be provided together."
            )

        if startDate and endDate:
            start_dt = validate_date(startDate, "startDate")
            end_dt = validate_date(endDate, "endDate")

            if start_dt > end_dt:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="startDate cannot be after endDate."
                )

        # -----------------------------------------------------------
        # 3️⃣ VALIDATE PAGE / PAGE SIZE (Fail-fast)
        # -----------------------------------------------------------
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="Page must be >= 1"
            )

        if not (1 <= page_size <= 200):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="page_size must be between 1 and 200"
            )

        # -----------------------------------------------------------
        # 4️⃣ DELEGATE TO SERVICE LAYER
        # -----------------------------------------------------------
        result = await get_paginated_worker_assignments_data_list(
            db=db,
            model=WorkerAssignment,
            status=assignment_status,
            startDate=startDate,
            endDate=endDate,
            page=page,
            page_size=page_size
        )

        return result

    except HTTPException:
        raise

    except Exception as e:
        print(f"[API ERROR] get_paginated_worker_assignments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while fetching worker assignments."
        )

# ---------








@router.get('/get-all-allowed-user-for-worker-assignmnet', response_model=UserListResponse)
async def get_all_user_for_worker_assignment_by_allowed_roles(
    db: AsyncSession = Depends(get_db)
):
    # Fetch the list of workers eligible for assignment
    workers = await get_all_allowed_users_as_worker(db)
    
    # Return the workers as a response in the desired format
    return UserListResponse(
        success=True,   
        message="Successfully get all woker user",
        users=[UserRead.model_validate(worker) for worker in workers],
        total=len(workers),
        page=1,  # Since we're not paginating, this will always be 1
        limit=len(workers),  # Return the full list
        totalPages=1,  # Only 1 page because we're not paginating
        count=len(workers)  # Total count of workers
    )


@router.get("/get-assigned-list-of-particular-worker/{emp_id}", response_model=WorkerAssignmentResponseForWorkerLists)
async def get_particular_worker_assignment_list(emp_id: str, db: AsyncSession = Depends(get_db)):
    # Fetch assignments by employee ID
    worker_assignments_list = await get_worker_assignment_lists_by_emp_id(db, emp_id)
    
    # Map WorkerAssignment model to WorkerAssignmentResponse schema
    return WorkerAssignmentResponseForWorkerLists(
        data=[WorkerAssignmentResponseForWorker.model_validate(assignment) for assignment in worker_assignments_list],
        total=len(worker_assignments_list),  # Total number of assignments found 
        success=True , # Operation success
        message="Successfully get all assigned data of this user"
    )



@router.post("/assign-user", response_model=ResponseOfWorkerAssignment)
async def assign_user_to_worker_assignment_route(
    assign_request: RequestOfWorkerAssignment, 
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):
    # Validate and assign the user to the worker assignment
    result = await assign_user_to_worker_assignment(
      db,
      assign_request.oc_no, 
      assign_request.emp_id,   # this used is worker which going to assigned (worker being assigned)
      current_user_role = current_user.role,
      changed_by = current_user.emp_id,   # this is the user which perform this action
      ip_address=request.client.host if request.client else None,
      user_agent = request.headers.get("user-agent"),
      device_id= None

    )

    if not result:
        raise HTTPException(status_code=404, detail="Worker assignment not found or user cannot be assigned.")
    
    return ResponseOfWorkerAssignment(
        success=True,
        message="User successfully assigned to the worker assignment.",
        oc_num=assign_request.oc_no,
        emp_id= assign_request.emp_id, 
    )





# add or assign drop dlv zone by assigned worker api ---------------------
@router.put("/assign-drop-dlv-zone")
async def assign_drop_dlv_zone(
    # oc_no: str, 
    # drop_dlv_zone: str, 
    # emp_id: str = None, 
    req: AssignDropDlvZoneRequest,
    fastApiRequest: Request, 
    current_user: User = Depends(require_roles(["imp_gp_user"])),
    db: AsyncSession = Depends(get_db)

):
    print(req,"req--------------------------------")
    try:
        emp_id = current_user.emp_id or req.emp_id
        current_user_role = current_user.role
        
        # Use the attributes from the 'data' object
        oc_no = req.oc_no
        drop_dlv_zone = req.drop_dlv_zone
      

        # Validate required fields are present and not empty
        if not oc_no or not drop_dlv_zone:
            raise HTTPException(status_code=400, detail="All fields are required (oc_no, drop_dlv_zone).")
        
        # Get IP address from request
        ip_address = get_request_ip(fastApiRequest)
        
        # Call the service layer to handle the logic

        result = await add_drop_dlv_zone_by_assigned_worker(db, oc_no, emp_id,current_user_role, drop_dlv_zone, ip_address=ip_address,device_id=req.device_id,user_agent=fastApiRequest.headers.get("user-agent")
 )
        
        if result["status"] == "success":
            return {"message": result["message"]}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        print("🔥 ERROR IN assign_drop_dlv_zone 🔥")
        print(str(e))
        traceback.print_exc()   # 👈 THIS IS THE KEY
        raise



    # ==========




@router.post("/export-filtered-data",description="Export filtered worker assignments to Excel (streaming)",response_model=None)
async def export_worker_assignments_stream(
    request: WorkerAssignmentExportRequest,
    db: AsyncSession = Depends(get_db)
):
    """
    Stream Excel export - handles large datasets efficiently
    Works with async PostgreSQL via SQLAlchemy
    """
    try:
        # Validate date range
        start = datetime.strptime(request.startDate, "%Y-%m-%d").date()
        end = datetime.strptime(request.endDate, "%Y-%m-%d").date()
        
        if start > end:
            raise HTTPException(
                status_code=400,
                detail="Start date cannot be greater than end date"
            )
        
        # Generate filename with timestamp
        timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
        filename = f"worker_assignments_{request.startDate}_{request.endDate}_{timestamp}.xlsx"
        
        # Return streaming response
        return StreamingResponse(
            generate_excel_stream_export_worker_assignment(
                db=db,
                assignment_status=request.assignment_status,
                start_date=request.startDate,
                end_date=request.endDate,
                chunk_size=1000  # Process 1000 records at a time
            ),
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-cache"
            }
        )
        
    except ValueError as e:
        raise HTTPException(
            status_code=400, 
            detail=f"Invalid date format: {str(e)}"
        )
    except HTTPException:
        raise
    except Exception as e:
        # # Log the error in production
        # import logging
        # logging.error(f"Export failed: {str(e)}", exc_info=True)
        raise HTTPException(
            status_code=500, 
            detail=f"Export failed: {str(e)}"
        )