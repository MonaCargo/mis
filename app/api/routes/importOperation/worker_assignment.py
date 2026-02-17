# # app/api/v1/endpoints/worker_assignment_api.py
# from datetime import date, datetime, time, timedelta
# import traceback
# from typing import List, Optional
# from zoneinfo import ZoneInfo
# from fastapi import APIRouter, Depends, HTTPException, Query, status
# from fastapi.responses import StreamingResponse
# import pytz
# from fastapi import Request
# from sqlalchemy import and_, func, or_, select
# from sqlalchemy.ext.asyncio import AsyncSession
# from app.core.dependency import require_roles, verify_token_and_get_user
# from app.db.models.importOperation.worker_assignment import WorkerAssignment
# from app.db.models.user import User
# from app.db.session import get_db
# from app.schemas.importOperation.worker_assignment import AssignDropDlvZoneRequest, PaginatedWorkerAssignmentResponse, RequestOfWorkerAssignment, ResponseOfWorkerAssignment, WorkerAssignmentExportRequest, WorkerAssignmentRequest, WorkerAssignmentResponseForWorker, WorkerAssignmentResponseForWorkerLists, WorkerAssignmentSearchRequest
# from app.schemas.user import UserListResponse, UserRead
# from app.services.importOperation.worker_assignment_service import add_drop_dlv_zone_by_assigned_worker, assign_user_to_worker_assignment, generate_excel_stream_export_worker_assignment, get_all_allowed_users_as_worker, get_all_worker_assignments_list, get_assignment_summary, get_assignment_summary_according_to_assigned_person, get_paginated_worker_assignments_data_list, get_worker_assignment_lists_by_emp_id, process_worker_assignment, search_in_worker_assignments
# from app.utils.common.get_request_ip import get_request_ip

# router = APIRouter(prefix="/worker-assignment", tags=[""])


# IST = ZoneInfo("Asia/Kolkata")
# UTC = ZoneInfo("UTC")


# def ist_to_utc_range(date_str: str):
#     date_obj = datetime.strptime(date_str, "%Y-%m-%d")

#     start_ist = datetime.combine(date_obj, time.min).replace(tzinfo=IST)
#     end_ist = datetime.combine(date_obj, time.max).replace(tzinfo=IST)

#     return start_ist.astimezone(UTC), end_ist.astimezone(UTC)


# @router.post("/process-and-save")
# async def process_worker_assignment_api(
#     req: WorkerAssignmentRequest,
#     db: AsyncSession = Depends(get_db)
# ):
#     try:
#         date_str = req.date
#         # Handle datetime -> string
#         if isinstance(date_str, datetime):
#             date_str = date_str.date().strftime("%Y-%m-%d")

#         # Handle date -> string
#         elif isinstance(date_str, date):
#             date_str = date_str.strftime("%Y-%m-%d")

#         # Already string? OK
#         elif isinstance(date_str, str):
#             pass

#         else:
#             raise HTTPException(status_code=400, detail="Invalid date format")


#     except ValueError:
#         raise HTTPException(status_code=400, detail="Invalid date format. Use YYYY-MM-DD")

#     return await process_worker_assignment(db, req)


# @router.get(
#     "/generic-search",
#     response_model=WorkerAssignmentResponseForWorkerLists,
#     description="Search worker assignments by oc_no, gp_no, temp_oc, awb, hawb"
# )
# async def search_worker_assignment(
#     type: str = Query(..., description="oc_no | gp_no | temp_oc | awb | hawb"),
#     term: str = Query(..., description="Search value"),
#     db: AsyncSession = Depends(get_db)
# ):

#     data = await search_in_worker_assignments(
#         db,
#         search_type=type,
#         search_value=term
#     )

#     return WorkerAssignmentResponseForWorkerLists(
#         status="success",
#         success=True,
#         message="Search completed",
#         data=data,
#         total=len(data),
#         your_search_type=type,
#         your_search_value=term
#     )


# # @router.get("/get-all-user-assignment-list-data-by-filter")
# # async def get_all_user_assignment_data(
# #     status: str = Query("all"),
# #     startDate: str = Query(None),
# #     endDate: str = Query(None),
# #     db: AsyncSession = Depends(get_db)
# # ):

# #     # ---------------- HELPERS ---------------- #

# #     def convert_ist_day_to_utc_range(date_str: str):
# #         """Convert YYYY-MM-DD in IST to complete UTC day range."""
# #         ist = pytz.timezone("Asia/Kolkata")
# #         d = datetime.strptime(date_str, "%Y-%m-%d")

# #         start_ist = ist.localize(d.replace(hour=0, minute=0, second=0))
# #         end_ist = ist.localize(d.replace(hour=23, minute=59, second=59, microsecond=999999))

# #         return start_ist.astimezone(pytz.UTC), end_ist.astimezone(pytz.UTC)


# #     # ---------------- MODULAR FILTERS ---------------- #

# #     def filter_dlv_zone(query, status: str):
# #         """Filter based on whether dlv_zone exists or not."""
# #         if status == "dlv_added":
# #             # Show only rows where dlv zone exists
# #             return query.where(
# #                 WorkerAssignment.drop_dlv_zone.isnot(None),
# #                 func.trim(WorkerAssignment.drop_dlv_zone) != ""
# #             )

# #         # For all other statuses → show only rows where dlv zone is empty
# #         return query.where(
# #             or_(
# #                 WorkerAssignment.drop_dlv_zone.is_(None),
# #                 func.trim(WorkerAssignment.drop_dlv_zone) == ""
# #             )
# #         )


# #     def filter_status(query, status: str):
# #         """Filter assigned/unassigned status (after dlv filter)."""
# #         if status == "assigned":
# #             return query.where(WorkerAssignment.assigned_person.isnot(None))

# #         if status == "unassigned":
# #             return query.where(WorkerAssignment.assigned_person.is_(None))

# #         # status == "all" → no assignment filter
# #         return query


# #     def filter_dates(query, startDate: str, endDate: str):
# #         """Filter on integrate_date_time / gate_pass_issued_date."""
# #         if not (startDate and endDate):
# #             return query

# #         utc_start, _ = convert_ist_day_to_utc_range(startDate)
# #         _, utc_end = convert_ist_day_to_utc_range(endDate)

# #         return query.where(
# #             or_(
# #                 WorkerAssignment.integrate_date_time.between(utc_start, utc_end),
# #                 WorkerAssignment.gate_pass_issued_date_time_combo.between(utc_start, utc_end)
# #             )
# #         )


# #     # ---------------- MAIN QUERY BUILDER ---------------- #

# #     query = select(WorkerAssignment)

# #     query = filter_dlv_zone(query, status)      # 1️⃣ First filter dlv_zone
# #     query = filter_status(query, status)        # 2️⃣ Then apply assigned/unassigned
# #     query = filter_dates(query, startDate, endDate)  # 3️⃣ Apply date filters

# #     query = query.order_by(WorkerAssignment.id.desc())

# #     result = await db.execute(query)
# #     return result.scalars().all()


# @router.get(
#     "/get-all-user-assignment-list-data-by-filter",
#     response_model=PaginatedWorkerAssignmentResponse,
#     summary="Get paginated worker assignments with filters",
#     description="Retrieve filtered, paginated worker assignments including matrix analytics."
# )
# async def get_paginated_worker_assignments(
#     assignment_status: str = Query(default="all"),
#     startDate: Optional[str] = Query(default=None, regex=r"^\d{4}-\d{2}-\d{2}$"),
#     endDate: Optional[str] = Query(default=None, regex=r"^\d{4}-\d{2}-\d{2}$"),


#     page: int = Query(default=1, ge=1),
#     page_size: int = Query(default=10, ge=1, le=500),

#     db: AsyncSession = Depends(get_db)
# ):
#     """
#     Improved API for worker assignment pagination with strict validation.
#     """


#         # -------------------------------------------------------
#     # HELPER: Validate Date Format (YYYY-MM-DD)
#     # -------------------------------------------------------
#     def validate_date(date_str: str, field_name: str):
#         try:
#             return datetime.strptime(date_str, "%Y-%m-%d")
#         except ValueError:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Invalid {field_name}: '{date_str}'. Expected format YYYY-MM-DD."
#             )


#     # -------------------------------------------------------
#     # HELPER: Validate Status Enum
#     # -------------------------------------------------------
#     def validate_status(status_value: str):
#         # allowed = ["all", "assigned", "unassigned", "dlv_added"]
#         allowed = ["all", "assigned", "unassigned", "dlv_added", "assigned_but_not_delivered","gp_delivered"]

#         if status_value not in allowed:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail=f"Invalid status '{status_value}'. Allowed: {allowed}"
#             )
#         return status_value


#     try:
#         # -----------------------------------------------------------
#         # 1️⃣ VALIDATE STATUS
#         # -----------------------------------------------------------
#         assignment_status = validate_status(assignment_status)

#         # -----------------------------------------------------------
#         # 2️⃣ VALIDATE DATE Inputs
#         # -----------------------------------------------------------
#         if (startDate and not endDate) or (endDate and not startDate):
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Both startDate and endDate must be provided together."
#             )

#         if startDate and endDate:
#             start_dt = validate_date(startDate, "startDate")
#             end_dt = validate_date(endDate, "endDate")

#             if start_dt > end_dt:
#                 raise HTTPException(
#                     status_code=status.HTTP_400_BAD_REQUEST,
#                     detail="startDate cannot be after endDate."
#                 )

#         # -----------------------------------------------------------
#         # 3️⃣ VALIDATE PAGE / PAGE SIZE (Fail-fast)
#         # -----------------------------------------------------------
#         if page < 1:
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="Page must be >= 1"
#             )

#         if not (1 <= page_size <= 500):
#             raise HTTPException(
#                 status_code=status.HTTP_400_BAD_REQUEST,
#                 detail="page_size must be between 1 and 200"
#             )

#         # -----------------------------------------------------------
#         # 4️⃣ DELEGATE TO SERVICE LAYER
#         # -----------------------------------------------------------
#         result = await get_paginated_worker_assignments_data_list(
#             db=db,
#             model=WorkerAssignment,
#             status=assignment_status,
#             startDate=startDate,
#             endDate=endDate,
#             page=page,
#             page_size=page_size
#         )

#         return result

#     except HTTPException:
#         raise

#     except Exception as e:
#         print(f"[API ERROR] get_paginated_worker_assignments: {str(e)}")
#         raise HTTPException(
#             status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
#             detail="Unexpected error while fetching worker assignments."
#         )

# # ---------


# @router.get('/get-all-allowed-user-for-worker-assignmnet', response_model=UserListResponse)
# async def get_all_user_for_worker_assignment_by_allowed_roles(
#     db: AsyncSession = Depends(get_db)
# ):
#     # Fetch the list of workers eligible for assignment
#     workers = await get_all_allowed_users_as_worker(db)

#     # Return the workers as a response in the desired format
#     return UserListResponse(
#         success=True,
#         message="Successfully get all woker user",
#         users=[UserRead.model_validate(worker) for worker in workers],
#         total=len(workers),
#         page=1,  # Since we're not paginating, this will always be 1
#         limit=len(workers),  # Return the full list
#         totalPages=1,  # Only 1 page because we're not paginating
#         count=len(workers)  # Total count of workers
#     )


# @router.get("/get-assigned-list-of-particular-worker/{emp_id}", response_model=WorkerAssignmentResponseForWorkerLists)
# async def get_particular_worker_assignment_list(emp_id: str, db: AsyncSession = Depends(get_db)):
#     # Fetch assignments by employee ID
#     worker_assignments_list = await get_worker_assignment_lists_by_emp_id(db, emp_id)

#     # Map WorkerAssignment model to WorkerAssignmentResponse schema
#     return WorkerAssignmentResponseForWorkerLists(
#         data=[WorkerAssignmentResponseForWorker.model_validate(assignment) for assignment in worker_assignments_list],
#         total=len(worker_assignments_list),  # Total number of assignments found
#         success=True , # Operation success
#         message="Successfully get all assigned data of this user"
#     )


# @router.post("/assign-user", response_model=ResponseOfWorkerAssignment)
# async def assign_user_to_worker_assignment_route(
#     assign_request: RequestOfWorkerAssignment,
#     request: Request,
#     db: AsyncSession = Depends(get_db),
#     current_user: UserRead = Depends(verify_token_and_get_user)
# ):
#     # Validate and assign the user to the worker assignment
#     result = await assign_user_to_worker_assignment(
#       db,
#       assign_request.oc_no,
#       assign_request.emp_id,   # this used is worker which going to assigned (worker being assigned)
#       current_user_role = current_user.role,
#       changed_by = current_user.emp_id,   # this is the user which perform this action
#       ip_address=request.client.host if request.client else None,
#       user_agent = request.headers.get("user-agent"),
#       device_id= None

#     )

#     if not result:
#         raise HTTPException(status_code=404, detail="Worker assignment not found or user cannot be assigned.")

#     return ResponseOfWorkerAssignment(
#         success=True,
#         message="User successfully assigned to the worker assignment.",
#         oc_num=assign_request.oc_no,
#         emp_id= assign_request.emp_id,
#     )


# # add or assign drop dlv zone by assigned worker api ---------------------
# @router.put("/assign-drop-dlv-zone")
# async def assign_drop_dlv_zone(
#     # oc_no: str,
#     # drop_dlv_zone: str,
#     # emp_id: str = None,
#     req: AssignDropDlvZoneRequest,
#     fastApiRequest: Request,
#     current_user: User = Depends(require_roles(["imp_gp_user"])),
#     db: AsyncSession = Depends(get_db)

# ):
#     print(req,"req--------------------------------")
#     try:
#         emp_id = current_user.emp_id or req.emp_id
#         current_user_role = current_user.role

#         # Use the attributes from the 'data' object
#         oc_no = req.oc_no
#         drop_dlv_zone = req.drop_dlv_zone


#         # Validate required fields are present and not empty
#         if not oc_no or not drop_dlv_zone:
#             raise HTTPException(status_code=400, detail="All fields are required (oc_no, drop_dlv_zone).")

#         # Get IP address from request
#         ip_address = get_request_ip(fastApiRequest)

#         # Call the service layer to handle the logic

#         result = await add_drop_dlv_zone_by_assigned_worker(db, oc_no, emp_id,current_user_role, drop_dlv_zone, ip_address=ip_address,device_id=req.device_id,user_agent=fastApiRequest.headers.get("user-agent")
#  )

#         if result["status"] == "success":
#             return {"message": result["message"]}
#         else:
#             raise HTTPException(status_code=400, detail=result["message"])
#     except Exception as e:
#         print("🔥 ERROR IN assign_drop_dlv_zone 🔥")
#         print(str(e))
#         traceback.print_exc()   # 👈 THIS IS THE KEY
#         raise


#     # ==========


# @router.post("/export-filtered-data",description="Export filtered worker assignments to Excel (streaming)",response_model=None)
# async def export_worker_assignments_stream(
#     request: WorkerAssignmentExportRequest,
#     db: AsyncSession = Depends(get_db)
# ):
#     """
#     Stream Excel export - handles large datasets efficiently
#     Works with async PostgreSQL via SQLAlchemy
#     """
#     try:
#         # Validate date range
#         start = datetime.strptime(request.startDate, "%Y-%m-%d").date()
#         end = datetime.strptime(request.endDate, "%Y-%m-%d").date()

#         if start > end:
#             raise HTTPException(
#                 status_code=400,
#                 detail="Start date cannot be greater than end date"
#             )

#         # Generate filename with timestamp
#         timestamp = datetime.now().strftime('%Y%m%d_%H%M%S')
#         filename = f"worker_assignments_{request.startDate}_{request.endDate}_{timestamp}.xlsx"

#         # Return streaming response
#         return StreamingResponse(
#             generate_excel_stream_export_worker_assignment(
#                 db=db,
#                 assignment_status=request.assignment_status,
#                 start_date=request.startDate,
#                 end_date=request.endDate,
#                 chunk_size=1000  # Process 1000 records at a time
#             ),
#             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#             headers={
#                 "Content-Disposition": f"attachment; filename={filename}",
#                 "Cache-Control": "no-cache"
#             }
#         )

#     except ValueError as e:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Invalid date format: {str(e)}"
#         )
#     except HTTPException:
#         raise
#     except Exception as e:
#         # # Log the error in production
#         # import logging
#         # logging.error(f"Export failed: {str(e)}", exc_info=True)
#         raise HTTPException(
#             status_code=500,
#             detail=f"Export failed: {str(e)}"
#         )


#     # ===============


# # ================== Get user assignment summury by date range ================

# @router.get("/user-assignment-summary")
# async def assignment_summary(
#     start_date: str,
#     end_date: str,
#     db: AsyncSession = Depends(get_db),
# ):
#     """
#     Date range:
#     From midnight of start_date
#     To midnight AFTER end_date (end exclusive)
#     """

#     # 1️⃣ Validate format
#     try:
#         start = datetime.strptime(start_date, "%Y-%m-%d")
#         end = datetime.strptime(end_date, "%Y-%m-%d")
#     except ValueError:
#         raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

#     # 2️⃣ Validate range
#     if start > end:
#         raise HTTPException(400, "start_date cannot be after end_date")

#     # 3️⃣ IST → UTC
#     ist = pytz.timezone("Asia/Kolkata")
#     utc = pytz.UTC

#     # Start: 20th 00:00 IST
#     start_utc = ist.localize(start).astimezone(utc)

#     # End: 31st 00:00 IST (end_date + 1)
#     end_utc = ist.localize(end + timedelta(days=1)).astimezone(utc)
#     print(start_utc,"start......")
#     print(end_utc,"end.......")
#     # 4️⃣ Pass DATETIMES (not strings)
#     data = await get_assignment_summary(db, start_utc, end_utc)


#     return {"data": data}


# # Assigned person based summary with its assigned/delivered counts
# @router.get("/user-assignment-summary-based-on-assigned-person")
# async def assignment_summary(
#     start_date: str,
#     end_date: str,
#     db: AsyncSession = Depends(get_db),
# ):
#     """
#     Date range:
#     From midnight of start_date
#     To midnight AFTER end_date (end exclusive)
#     Assigned person based summary
#     """

#     # 1️⃣ Validate format
#     try:
#         start = datetime.strptime(start_date, "%Y-%m-%d")
#         end = datetime.strptime(end_date, "%Y-%m-%d")
#     except ValueError:
#         raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

#     # 2️⃣ Validate range
#     if start > end:
#         raise HTTPException(400, "start_date cannot be after end_date")

#     # 3️⃣ IST → UTC
#     ist = pytz.timezone("Asia/Kolkata")
#     utc = pytz.UTC

#     # Start: 20th 00:00 IST
#     start_utc = ist.localize(start).astimezone(utc)

#     # End: 31st 00:00 IST (end_date + 1)
#     end_utc = ist.localize(end + timedelta(days=1)).astimezone(utc)
#     print(start_utc,"start......")
#     print(end_utc,"end.......")
#     # 4️⃣ Pass DATETIMES (not strings)
#     data = await get_assignment_summary_according_to_assigned_person(db, start_utc, end_utc)


#     return {"data": data}


# ==================================================================================================
# ==========================👌👌👌👌👌👌👌👌👌👌👌👌 NEW STRUCTURE two level ================


# app/api/v1/endpoints/worker_assignment_api.py
from datetime import date, datetime, time, timedelta
import math
import traceback
from typing import List, Optional
from zoneinfo import ZoneInfo
from fastapi import APIRouter, Body, Depends, HTTPException, Query, status
from fastapi.responses import StreamingResponse
import pytz
from fastapi import Request
from sqlalchemy import and_, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependency import require_roles, verify_token_and_get_user

# from app.db.models.importOperation.worker_assignment import WorkerAssignment
from app.db.models.importOperation.worker_assignment import WorkerAssignmentShipment
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.importOperation.worker_assignment import (
    AssignDropDlvZoneRequest,
    AssignLoadingInLiftRequest,
    AssignUnloadingFromLiftRequest,
    DropZoneUpdateRequest,
    MarkNeedTracerRequest,
    MarkShipmentFinalDeliveryRequest,
    PaginatedWorkerAssignmentResponse,
    RequestOfImprtTracerAssign,
    RequestOfWorkerAssignment,
    ResponseOfWorkerAssignment,
    WorkerAssignmentExportRequest,
    WorkerAssignmentRequest,
    WorkerAssignmentResponseForWorkerLists,
    WorkerAssignmentSearchRequest,
)
from app.schemas.user import UserListResponse, UserRead
from app.services.importOperation.worker_assignment_service import (
    add_drop_dlv_zone_by_assigned_worker,
    add_loading_in_lift_by_assigned_worker,
    add_unloading_from_lift_by_assigned_worker,
    assign_user_to_worker_assignment,
    auto_assign_pom_shipments,
    generate_ageing_report_for_worker_assignment,
    generate_excel_stream_export_worker_assignment,
    get_all_allowed_users_as_worker,
    get_all_open_damage_shipments,
    get_all_shipments_by_ton_category_value_particular_date_range,
    get_assignment_category_summary,
    get_assignment_overall_summary,
    get_assignment_summary_according_to_assigned_person,
    get_damage_shipment_summary_stats,
    get_data_at_user_based_assigned_not_dropped_at_lift_have_gatepass_no,
    get_full_damage_report_by_id_for_tracer,
    get_full__all_damage_grouped_by_shipment_for_tracer,
    get_paginated_worker_assignments_data_list,
    get_paginated_worker_assignments_with_damage_filter,
    get_particular_user_drop_shipments_details,
    get_shipment_delay_dashboard_counts,
    get_shipment_delay_details,
    get_shipments_for_final_delivery,
    get_shipments_for_loading_in_lift,
    get_shipments_for_unloading_from_lift,
    get_top_performers,
    get_worker_assignment_lists_by_emp_id,
    get_worker_shipment_details_by_empid_which_assigned_not_dropatlift,
    mark_final_delivery_by_assigned_worker,
    mark_shipment_need_tracer,
    process_worker_assignment,
    search_in_worker_assignments,
    update_drop_dlv_zone,
)
from app.services.user_service import get_active_import_tracer
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
    req: WorkerAssignmentRequest, db: AsyncSession = Depends(get_db)
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
        raise HTTPException(
            status_code=400, detail="Invalid date format. Use YYYY-MM-DD"
        )

    return await process_worker_assignment(db, req)


@router.get(
    "/generic-search",
    # response_model=WorkerAssignmentResponseForWorkerLists,
    description="Search worker assignments by oc_no, gp_no, temp_oc, awb, hawb",
)
async def search_worker_assignment(
    type: str = Query(..., description="oc_no | gp_no | temp_oc | awb | hawb"),
    term: str = Query(..., description="Search value"),
    db: AsyncSession = Depends(get_db),
):

    data = await search_in_worker_assignments(db, search_type=type, search_value=term)

    return {
        "status": "success",
        "success": True,
        "message": "Search completed",
        "data": data,
        "total": len(data),
        "your_search_type": type,
        "your_search_value": term,
    }


@router.get(
    "/get-all-user-assignment-list-data-by-filter",
    # response_model=PaginatedWorkerAssignmentResponse,
    summary="Get paginated worker assignments with filters",
    description="Retrieve filtered, paginated worker assignments including matrix analytics.",
)
async def get_paginated_worker_assignments(
    assignment_status: str = Query(default="all"),
    startDate: Optional[str] = Query(default=None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    endDate: Optional[str] = Query(default=None, regex=r"^\d{4}-\d{2}-\d{2}$"),
    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=500),
    db: AsyncSession = Depends(get_db),
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
                detail=f"Invalid {field_name}: '{date_str}'. Expected format YYYY-MM-DD.",
            )

    # -------------------------------------------------------
    # HELPER: Validate Status Enum
    # -------------------------------------------------------
    def validate_status(status_value: str):
        # allowed = ["all", "assigned", "unassigned", "dlv_added"]
        allowed = [
            "all",
            "assigned",
            "unassigned",
            "dlv_added",
            "assigned_but_not_delivered",
     
            "gp_generated", # those who have gatepass no. irrespective of gate pass enddate time present or not
            "gp_delivered", # those who have gatepass end date time


        ]

        if status_value not in allowed:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail=f"Invalid status '{status_value}'. Allowed: {allowed}",
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
                detail="Both startDate and endDate must be provided together.",
            )

        if startDate and endDate:
            start_dt = validate_date(startDate, "startDate")
            end_dt = validate_date(endDate, "endDate")

            if start_dt > end_dt:
                raise HTTPException(
                    status_code=status.HTTP_400_BAD_REQUEST,
                    detail="startDate cannot be after endDate.",
                )

        # -----------------------------------------------------------
        # 3️⃣ VALIDATE PAGE / PAGE SIZE (Fail-fast)
        # -----------------------------------------------------------
        if page < 1:
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST, detail="Page must be >= 1"
            )

        if not (1 <= page_size <= 500):
            raise HTTPException(
                status_code=status.HTTP_400_BAD_REQUEST,
                detail="page_size must be between 1 and 200",
            )

        # -----------------------------------------------------------
        # 4️⃣ DELEGATE TO SERVICE LAYER
        # -----------------------------------------------------------
        result = await get_paginated_worker_assignments_data_list(
            db=db,
            model=WorkerAssignmentShipment,
            status=assignment_status,
            startDate=startDate,
            endDate=endDate,
            page=page,
            page_size=page_size,
        )

        return result

    except HTTPException:
        raise

    except Exception as e:
        print(f"[API ERROR] get_paginated_worker_assignments: {str(e)}")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail="Unexpected error while fetching worker assignments.",
        )


# # ---------


@router.get(
    "/get-all-allowed-user-for-worker-assignmnet", response_model=UserListResponse
)
async def get_all_user_for_worker_assignment_by_allowed_roles(
    db: AsyncSession = Depends(get_db),
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
        count=len(workers),  # Total count of workers
    )


# GET ALL LIKST OF ASSIGNED shipment to particular workers=======================================
@router.get(
    "/get-assigned-list-of-particular-worker/{emp_id}",
    summary="Get assigned shipments for a worker",
    response_model=WorkerAssignmentResponseForWorkerLists,
)
async def get_particular_worker_assignment_list(
    emp_id: str, db: AsyncSession = Depends(get_db)
):
    # Fetch assignments by employee ID
    worker_assignments_list = await get_worker_assignment_lists_by_emp_id(db, emp_id)

    # Map WorkerAssignment model to WorkerAssignmentResponse schema
    return WorkerAssignmentResponseForWorkerLists(
        data=worker_assignments_list,
        total=len(worker_assignments_list),  # Total number of assignments found
        success=True,  # Operation success
        message="Successfully get all assigned data of this user",
    )


# Assign operator or user to the shipment======================================================
@router.post("/assign-user", response_model=ResponseOfWorkerAssignment)
async def assign_user_to_worker_assignment_route(
    assign_request: RequestOfWorkerAssignment,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    # 🔥 Log what we received
    print("=" * 80)
    print("✅ REQUEST PASSED VALIDATION")
    print(f"📥 Parsed data: {assign_request.model_dump()}")
    print("=" * 80)
    result = await assign_user_to_worker_assignment(
        db=db,
        header_id=assign_request.header_id,
        shipment_id=assign_request.shipment_id,
        oc_no=assign_request.oc_no,
        emp_id=assign_request.emp_id,
        current_user_role=current_user.role,
        changed_by=current_user.emp_id,
        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
        device_id=None,
    )

    return ResponseOfWorkerAssignment(
        success=True,
        message="User successfully assigned to the shipment.",
        oc_num=assign_request.oc_no,
        emp_id=assign_request.emp_id,
    )


# add or assign drop dlv zone by assigned worker api ================================
@router.put("/assign-drop-dlv-zone")
async def assign_drop_dlv_zone(
    # oc_no: str,
    # drop_dlv_zone: str,
    # emp_id: str = None,
    req: AssignDropDlvZoneRequest,
    fastApiRequest: Request,
    current_user: User = Depends(require_roles(["imp_gp_user","imp_tracer"])),
    db: AsyncSession = Depends(get_db),
):
    print(req, "req--------------------------------")
    try:
        emp_id = current_user.emp_id or req.emp_id
        current_user_role = current_user.role

        # Use the attributes from the 'data' object
        oc_no = req.oc_no
        drop_dlv_zone = req.drop_dlv_zone

        # Validate required fields are present and not empty
        if not oc_no or not drop_dlv_zone:
            raise HTTPException(
                status_code=400,
                detail="All fields are required (oc_no, drop_dlv_zone).",
            )

        # ─────────────────────────────────────────────
        # 3️⃣ Metadata
        # ─────────────────────────────────────────────
        ip_address = get_request_ip(fastApiRequest)
        user_agent = fastApiRequest.headers.get("user-agent")

        # Call the service layer to handle the logic

        result = await add_drop_dlv_zone_by_assigned_worker(
            db=db,
            header_id=req.header_id,
            shipment_id=req.shipment_id,
            oc_no=req.oc_no,
            emp_id=emp_id,
            current_user_role=current_user_role,
            drop_dlv_zone=req.drop_dlv_zone,
            ip_address=ip_address,
            device_id=req.device_id,
            user_agent=user_agent,
        )

        if result["status"] == "success":
            return {"message": result["message"], "success": True}
        else:
            raise HTTPException(status_code=400, detail=result["message"])
    except Exception as e:
        print("🔥 ERROR IN assign_drop_dlv_zone 🔥")
        print(str(e))
        traceback.print_exc()  # 👈 THIS IS THE KEY
        raise


# === END =======


#👌 =========== Export route for user assignment data =============================
# @router.post(
#     "/export-filtered-data",
#     description="Export worker assignments (shipment-based) to Excel (streaming)"
# )
# async def export_worker_assignments_stream(
#     request: WorkerAssignmentExportRequest,
#     db = Depends(get_db)
# ):
#     try:
#         start = datetime.strptime(request.startDate, "%Y-%m-%d")
#         end = datetime.strptime(request.endDate, "%Y-%m-%d")

#         if start > end:
#             raise HTTPException(400, "Start date cannot be greater than end date")

#         timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")
#         filename = f"worker_assignments_{timestamp}.xlsx"

#         return StreamingResponse(
#             generate_excel_stream_export_worker_assignment(
#                 db=db,
#                 assignment_status=request.assignment_status,
#                 start_date=request.startDate,
#                 end_date=request.endDate,
#                 chunk_size=1000
#             ),
#             media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
#             headers={
#                 "Content-Disposition": f"attachment; filename={filename}",
#                 "Cache-Control": "no-cache"
#             }
#         )

#     except ValueError as e:
#         raise HTTPException(400, f"Invalid date format: {e}")

@router.post(
    "/export-filtered-data",
    description="Export worker assignments (streaming excel)"
)
async def export_worker_assignments_stream(
    request: WorkerAssignmentExportRequest,
    db: AsyncSession = Depends(get_db)
):
    try:
        start = datetime.strptime(request.startDate, "%Y-%m-%d")
        end = datetime.strptime(request.endDate, "%Y-%m-%d")

        if start > end:
            raise HTTPException(400, "Start date cannot be greater than end date")

        report_type = request.report_type.upper()

        timestamp = datetime.now().strftime("%Y%m%d_%H%M%S")

        filename = f"operator_{report_type.lower()}_{timestamp}.xlsx"


        # ✅ REPORT SWITCH
        if report_type == "DEFAULT":

            generator = generate_excel_stream_export_worker_assignment(
                db=db,
                assignment_status=request.assignment_status,
                start_date=request.startDate,
                end_date=request.endDate,
            )

        elif report_type == "AGEING":

            generator = generate_ageing_report_for_worker_assignment(
                db=db,
                assignment_status=request.assignment_status,
                start_date=request.startDate,
                end_date=request.endDate,
            )

        else:
            raise HTTPException(400, "Invalid report type")


        return StreamingResponse(
            generator,
            media_type="application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
            headers={
                "Content-Disposition": f"attachment; filename={filename}",
                "Cache-Control": "no-cache"
            }
        )

    except ValueError as e:
        raise HTTPException(400, f"Invalid date format: {e}")



#👌 =========================  USER / WORKER ASSIGNMENT SUMMARY ============================

@router.get("/user-assignment-summary-based-workers")
async def assignment_summary(
    start_date: str,
    end_date: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Shipment-based operator summary (NEW structure)
    Date range:
    From start_date 00:00 IST
    To end_date + 1 day 00:00 IST (exclusive)
    """

    # 1️⃣ Validate date format
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(400, "start_date cannot be after end_date")

    # 2️⃣ IST → UTC conversion
    ist = pytz.timezone("Asia/Kolkata")
    utc = pytz.UTC

    start_utc = ist.localize(start).astimezone(utc)
    end_utc = ist.localize(end + timedelta(days=1)).astimezone(utc)

    # 3️⃣ Fetch summary
    data = await get_assignment_summary_according_to_assigned_person(
        db=db,
        start_utc=start_utc,
        end_utc=end_utc,
    )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "data": data
    }



@router.get("/assignment-category-summary")
async def assignment_category_summary(
    start_date: str,
    end_date: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Shipment-based category summary (NEW structure)
    """

    # 1️⃣ Validate dates
    try:
        start = datetime.strptime(start_date, "%Y-%m-%d")
        end = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

    if start > end:
        raise HTTPException(400, "start_date cannot be after end_date")

    # 2️⃣ IST → UTC
    ist = pytz.timezone("Asia/Kolkata")
    utc = pytz.UTC

    start_utc = ist.localize(start).astimezone(utc)
    end_utc = ist.localize(end + timedelta(days=1)).astimezone(utc)

    # 3️⃣ Fetch summary
    category_summary = await get_assignment_category_summary(
        db=db,
        start_utc=start_utc,
        end_utc=end_utc,
    )

    overall_summary = await get_assignment_overall_summary(
        db=db,
        start_utc=start_utc,
        end_utc=end_utc
    )

    damage_summary = await get_damage_shipment_summary_stats(
    db=db,
    start_utc=start_utc,
    end_utc=end_utc,
)
    

    return {
        "start_date": start_date,
        "end_date": end_date,
        "overall": overall_summary,
        "by_category": category_summary,
        "damage_shipment_stats":damage_summary
    }


# Assigned and not droped at lift user level counts (which have gatepass no. only those data taken here)
@router.get("/assigned_not-dropped-at-lift/by-worker")
async def get_not_dropped_at_lift_by_worker(
    start_date: str = Query(..., example="2026-01-01"),
    end_date: str = Query(..., example="2026-01-31"),
    db: AsyncSession = Depends(get_db),
):
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

    if start_date > end_date:
        raise HTTPException(400, "start_date cannot be after end_date")

    return await get_data_at_user_based_assigned_not_dropped_at_lift_have_gatepass_no(
        db=db,
        start_date=start_date,   # ✅ STRING
        end_date=end_date,       # ✅ STRING
    )



@router.get("/assigned_not-dropped-at-lift/by-worker/emp_id/details")
async def get_worker_shipment_details(
    emp_id: str,  # ✅ String because it's stored as string in DB
    start_date: str = Query(..., example="2026-01-01"),
    end_date: str = Query(..., example="2026-01-31"),
    page: int = Query(1, ge=1, description="Page number"),
    page_size: int = Query(30, ge=1, le=100, description="Items per page"),
    db: AsyncSession = Depends(get_db),
):
    """
    Drill-down: Get detailed shipment list for a specific worker
    Used when user clicks on a worker's count
    Path param is emp_id (e.g., "EMP001")
    """
    try:
        datetime.strptime(start_date, "%Y-%m-%d")
        datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(400, "Invalid date format. Use YYYY-MM-DD")

    if start_date > end_date:
        raise HTTPException(400, "start_date cannot be after end_date")

    return await get_worker_shipment_details_by_empid_which_assigned_not_dropatlift(
        db=db,
        emp_id=emp_id,  # ✅ Pass emp_id directly
        start_date=start_date,
        end_date=end_date,
        page=page,
        page_size=page_size,
    )
# =================================================================
#======== Get time based (delayed in assigned or unassigned and drop dlv zone added time) shipment data
@router.get(
    "/shipment-delay/dashboard/counts",
    summary="Shipment SLA dashboard (counts only)",
)
async def shipment_delay_dashboard(
    lookback_days: int = Query(3, ge=1, le=20),
    db: AsyncSession = Depends(get_db),
):
    return await get_shipment_delay_dashboard_counts(
        db=db,
        lookback_days=lookback_days,
    )


@router.get(
    "/shipment-delay/details",
    summary="Shipment SLA delayed shipments (paginated)",
)
async def shipment_delay_details(
    sla_type: str = Query(
        ...,
        description="NOT_ASSIGNED_15_MIN | ASSIGNED_NOT_DELIVERED_30_MIN",
    ),
    lookback_days: int = Query(3, ge=1, le=20),
    limit: int = Query(20, ge=1, le=200),
    offset: int = Query(0, ge=0),
    db: AsyncSession = Depends(get_db),
):
    return await get_shipment_delay_details(
        db=db,
        sla_type=sla_type,
        lookback_days=lookback_days,
        limit=limit,
        offset=offset,
    )


@router.get("/shipments/by-ton-category-value")
async def get_shipments_by_ton(
    start_date: str,
    end_date: str,
    ton_category: str,
    db: AsyncSession = Depends(get_db),
):
    """
    Drill-down API for TON category
    """
    print("++++++++++++++++++++++++++++++++++++++++++++++++")
    print(ton_category)
    print(start_date)
    print(end_date)

    # def normalize_ton_category(value: str) -> str:
    #     """
    #     Convert frontend ton formats to DB format.
    #     Example:
    #     5_TON  -> 5 TON
    #     5-ton  -> 5 TON
    #     5_ton  -> 5 TON
    #     5 ton  -> 5 TON
    #     """
    #     # return value
    #     if not value:
    #         return value

    #     return (
    #     value
    #     .replace("_", " ")
    #     .replace("-", " ")
    #     .strip()
    #     .upper()
    #     )

    def normalize_ton_category(value: str) -> str:
        """
        Convert frontend ton formats to DB format.
        Example:
        5_TON  -> 5 Ton
        5-ton  -> 5 Ton
        5_ton  -> 5 Ton
        5 ton  -> 5 Ton
        """
        if not value:
            return value

        # Normalize separators and casing
        normalized = (
            value.replace("_", " ")
                .replace("-", " ")
                .strip()
                .lower()
        )

        # Split into parts (e.g., ["5", "ton"])
        parts = normalized.split()

        # If the last part is 'ton', capitalize it properly
        if parts and parts[-1] == "ton":
            parts[-1] = "Ton"

        return " ".join(parts)


    narmalizeTonCategory = normalize_ton_category(ton_category)
    print("++++++++++++++++++++++++++++++++++++++++++++++++")
    print(narmalizeTonCategory)
    print(start_date)
    print(end_date)

    data = await get_all_shipments_by_ton_category_value_particular_date_range(
        db,
        start_date,
        end_date,
        ton_category=narmalizeTonCategory
    )

    return {
        "success": True,
        "count": len(data),
        "data": data,
    }


# Get the details of particulart operator/worker that how many data drop(5/3/10 ton) on paerticular date range (for operator daily summary view) 
@router.get("/particular-user-drop-shipments-details")
async def get_user_drop_shipments_api(
    emp_id: str = Query(..., description="Employee ID"),
    start_date: str = Query(..., example="2026-01-20"),
    end_date: str = Query(..., example="2026-01-25"),
    db: AsyncSession = Depends(get_db),
):
    """
    Get dropped shipments of a user in date range (IST based)
    """

    # -------------------------------
    # Basic validation
    # -------------------------------
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be greater than end_date",
        )

    data = await get_particular_user_drop_shipments_details(
        db=db,
        emp_id=emp_id,
        start_date=start_date,
        end_date=end_date,
    )

    return {
        "status": "success",
        "emp_id": emp_id,
        "start_date": start_date,
        "end_date": end_date,
        "count": data["total_records"],
        "count_metrics": data["count_metrics"],
        "data": data["full_data"],
    }
















# ============================ LIFT LOADING AND UNLOADING RELATED SERVICES ==========================================


@router.get("/shipments/for-loading-in-lift")
async def get_for_loading(
    start_date: str = Query(...,example="2026-01-30"),
    end_date: str = Query(...,example="2026-01-30"),
    drop_dlv_zone_term: str = Query(..., example="5 Ton"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Shipments ready to be LOADED in lift
    """
    
    # ============================
    # ✅ Date Format Validation
    # ============================

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="start_date must be in YYYY-MM-DD format",

        )

    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="end_date must be in YYYY-MM-DD format",

        )

    # ============================
    # ✅ Date Range Validation
    # ============================

    if end_dt < start_dt:
        raise HTTPException(
            status_code=400,
            detail="end_date must be greater than or equal to start_date",

        )

    return await get_shipments_for_loading_in_lift(
        db=db,
        drop_dlv_zone_term=drop_dlv_zone_term,
        user=current_user,
        start_date=start_date,
        end_date=end_date,
    )



@router.get("/shipments/for-unloading-from-lift")
async def get_for_unloading(
    start_date: str = Query(...,example="2026-01-30"),
    end_date: str = Query(...,example="2026-01-30"),
    drop_dlv_zone_term: str = Query(..., example="5 Ton"),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Shipments ready to be UNLOADED from lift
    """
        # ============================
    # ✅ Date Format Validation
    # ============================

    print(drop_dlv_zone_term,"drop_dlv_zone_term")

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="start_date must be in YYYY-MM-DD format",
       
        )

    try:
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="end_date must be in YYYY-MM-DD format",

        )

    # ============================
    # ✅ Date Range Validation
    # ============================

    if end_dt < start_dt:
        raise HTTPException(
            status_code=400,
            detail="end_date must be greater than or equal to start_date",

        )
    print(drop_dlv_zone_term,"unloading_from_lift_zone")

    return await get_shipments_for_unloading_from_lift(
        db=db,
        drop_dlv_zone_term=drop_dlv_zone_term,
        user=current_user,
        start_date=start_date,
        end_date=end_date
    )



@router.put("/add-loading-in-lift")
async def assign_loading_in_lift(
    req: AssignLoadingInLiftRequest,
    fastApiRequest: Request,
    current_user: User = Depends(require_roles(["imp_sec_ll","super_admin"])),
    db: AsyncSession = Depends(get_db),
):
    try:
        emp_id = current_user.emp_id
        current_user_role = current_user.role

        print(req,"======================================")

        # Validate
        if not req.oc_no or not req.loading_in_lift_zone:
            raise HTTPException(
                status_code=400,
                detail="oc_no and loading_in_lift_zone are required",
            )

        # Metadata
        ip_address = get_request_ip(fastApiRequest)
        user_agent = fastApiRequest.headers.get("user-agent")

        # Call service
        result = await add_loading_in_lift_by_assigned_worker(
            db=db,
            header_id=req.header_id,
            shipment_id=req.shipment_id,
            oc_no=req.oc_no,
            emp_id=emp_id,
            current_user_role=current_user_role,
            loading_in_lift_zone=req.loading_in_lift_zone,
            ip_address=ip_address,
            device_id=req.device_id,
            user_agent=user_agent,
        )

        if result["status"] == "success":
            return {"message": result["message"], "success": True}

        raise HTTPException(400, result["message"])

    except Exception as e:
        print("🔥 ERROR IN assign_loading_in_lift 🔥")
        traceback.print_exc()
        raise

@router.put("/add-unloading-from-lift")
async def assign_unloading_from_lift(
    req: AssignUnloadingFromLiftRequest,
    fastApiRequest: Request,
    current_user: User = Depends(require_roles(["imp_sec_ul","super_admin"])),
    db: AsyncSession = Depends(get_db),
):
    try:
        emp_id = current_user.emp_id
        current_user_role = current_user.role

        # Validate
        if not req.oc_no or not req.unloading_from_lift_zone:
            raise HTTPException(
                status_code=400,
                detail="oc_no and unloading_from_lift_zone are required",
            )

        # Metadata
        ip_address = get_request_ip(fastApiRequest)
        user_agent = fastApiRequest.headers.get("user-agent")

        # Call service
        result = await add_unloading_from_lift_by_assigned_worker(
            db=db,
            header_id=req.header_id,
            shipment_id=req.shipment_id,
            oc_no=req.oc_no,
            emp_id=emp_id,
            current_user_role=current_user_role,
            unloading_from_lift_zone=req.unloading_from_lift_zone,
            ip_address=ip_address,
            device_id=req.device_id,
            user_agent=user_agent,
        )

        if result["status"] == "success":
            return {"message": result["message"], "success": True}

        raise HTTPException(400, result["message"])

    except Exception as e:
        print("🔥 ERROR IN assign_unloading_from_lift 🔥")
        traceback.print_exc()
        raise




# @router.get("/shipments/for-final-delivery")
# async def get_for_final_delivery(
#     start_date: str = Query(..., example="2026-01-25"),
#     end_date: str = Query(..., example="2026-01-26"),
#     drop_dlv_zone_term: str = Query(..., example="5 Ton"),
#     db: AsyncSession = Depends(get_db),
#     current_user=Depends(verify_token_and_get_user),
# ):
#     """
#     Shipments ready for FINAL DELIVERY
#     """

#     # ✅ Date validation (reuse your earlier logic)
#     from datetime import datetime
#     from fastapi import HTTPException

#     try:
#         start_dt = datetime.strptime(start_date, "%Y-%m-%d")
#         end_dt = datetime.strptime(end_date, "%Y-%m-%d")
#     except ValueError:
#         raise HTTPException(
#             400, "Date must be YYYY-MM-DD"
#         )

#     if end_dt < start_dt:
#         raise HTTPException(
#             400, "end_date must be >= start_date"
#         )

#     return await get_shipments_for_final_delivery(
#         db=db,
#         drop_dlv_zone_term=drop_dlv_zone_term,
#         user=current_user,
#         start_date=start_date,
#         end_date=end_date,
#     )

@router.get("/shipments/for-final-delivery")
async def get_final_delivery_shipments(

    startDate: str = Query(..., example="2026-01-24"),
    endDate: str = Query(..., example="2026-01-24"),

    status: str = Query("all", example="all"),

    page: int = Query(1, ge=1),
    page_size: int = Query(10, ge=1, le=501,),

    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Get shipments for final delivery (paginated)
    """

    records, total = await get_shipments_for_final_delivery(
        db=db,
        start_date=startDate,
        end_date=endDate,
        status=status,
        page=page,
        page_size=page_size,
        user=current_user,
    )

    # Pagination meta
    total_pages = math.ceil(total / page_size) if total else 1

    pagination = {
        "current_page": page,
        "page_size": page_size,
        "total_records": total,
        "total_pages": total_pages,
        "has_previous": page > 1,
        "has_next": page < total_pages,
        "previous_page": page - 1 if page > 1 else None,
        "next_page": page + 1 if page < total_pages else None,
    }

    return {
        "success": True,
        "message": "Final delivery records fetched",
        "pagination": pagination,
        "data": records,
    }



@router.put("/mark-final-delivery")
async def mark_final_delivery(
    req: MarkShipmentFinalDeliveryRequest,
    fastApiRequest: Request,
    current_user: User = Depends(require_roles(["imp_sec_fd"])),
    db: AsyncSession = Depends(get_db),
):
    try:
        emp_id = current_user.emp_id
        role = current_user.role

        # Metadata
        ip_address = get_request_ip(fastApiRequest)
        user_agent = fastApiRequest.headers.get("user-agent")

        result = await mark_final_delivery_by_assigned_worker(
            db=db,
            header_id=req.header_id,
            shipment_id=req.shipment_id,
            oc_no=req.oc_no,

            emp_id=emp_id,
            current_user_role=role,

            ip_address=ip_address,
            device_id=req.device_id,
            user_agent=user_agent,
        )

        if result["status"] == "success":
            return {"success": True, "message": result["message"]}

        raise HTTPException(400, result["message"])

    except Exception:
        traceback.print_exc()
        raise

# -----------------------------------------------------------------------------------------------
# ========================== 😎 Import Tracer related api and routes  ===============================


@router.get(
    "/tracer/get-damage-worker-assignment-list",
    summary="Get paginated worker assignments having damage reports.",
    description="Retrieve paginated worker assignments filtered by damage status. It will see to import shift incharge web screen",
)
async def get_damage_worker_assignments(
    assignment_status: str = Query(
        default="damage_all",
        description="all | damage_in_progress |damage_open | damage_resolved"
    ),

    startDate: Optional[str] = Query(
        default=None,
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),

    endDate: Optional[str] = Query(
        default=None,
        regex=r"^\d{4}-\d{2}-\d{2}$"
    ),

    page: int = Query(default=1, ge=1),
    page_size: int = Query(default=10, ge=1, le=500),

    db: AsyncSession = Depends(get_db),
):
    """
    API for paginated damage-related worker assignments.
    """

    # -----------------------------
    # VALIDATE STATUS
    # -----------------------------
    allowed_status = [
        "all",
        "damage_open",
        "damage_in_progress",
        "damage_resolved"
    ]

    if assignment_status not in allowed_status:
        raise HTTPException(
            status_code=400,
            detail=f"Invalid status. Allowed: {allowed_status}"
        )

    # -----------------------------
    # VALIDATE DATES
    # -----------------------------
    def validate_date(val: str, name: str):
        try:
            return datetime.strptime(val, "%Y-%m-%d")
        except Exception:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid {name}. Format: YYYY-MM-DD"
            )

    if (startDate and not endDate) or (endDate and not startDate):
        raise HTTPException(
            status_code=400,
            detail="startDate and endDate must be together"
        )

    if startDate and endDate:
        s = validate_date(startDate, "startDate")
        e = validate_date(endDate, "endDate")

        if s > e:
            raise HTTPException(
                status_code=400,
                detail="startDate cannot be after endDate"
            )

    # -----------------------------
    # SERVICE CALL
    # -----------------------------
    try:

        result = await get_paginated_worker_assignments_with_damage_filter(
            db=db,
            status=assignment_status,
            startDate=startDate,
            endDate=endDate,
            page=page,
            page_size=page_size,
        )

        return result

    except HTTPException:
        raise

    except Exception as e:



        traceback.print_exc()   # 🔥 full stacktrace

        raise HTTPException(
            status_code=500,
            detail=f"Damage API Error: {str(e)}"
        )

@router.get("/{report_id}/full",
    summary="get all damage report data by damage_report_id  ")
async def get_damage_report_full_details(
    report_id: int,
    db: AsyncSession = Depends(get_db),
):

    data = await get_full_damage_report_by_id_for_tracer(db, report_id)

    if not data:
        raise HTTPException(
            status_code=404,
            detail="Damage report not found"
        )

    return {
        "success": True,
        "message": "Damage report fetched successfully",
        "data": data
    }

@router.get("/by-shipment/full-damage-report")
async def get_damage_reports_by_shipment(

    header_id: int,
    shipment_id: int,
    oc_no: str,

    db: AsyncSession = Depends(get_db)
):

    return await get_full__all_damage_grouped_by_shipment_for_tracer(
        db,
        header_id,
        shipment_id,
        oc_no
    )

# This is used in tracer assignmnet data
@router.get("/get-all-not-resolved-damages")
async def fetch_all_open_damages(
    db: AsyncSession = Depends(get_db),
):
    data = await get_all_open_damage_shipments(db)

    return {
        "success": True,
        "message": "Open damage shipments fetched",
        "data": data
    }



@router.post("/assign-shipment-to-import-tracer", response_model=ResponseOfWorkerAssignment)
async def assign_tracer_to_worker_assignment_route(
    assign_request: RequestOfImprtTracerAssign,   # no emp_id needed
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    try:
        # ─────────────────────────────────────────────
        # 1️⃣ Get Active Tracer
        # ─────────────────────────────────────────────
        tracer = await get_active_import_tracer(db)

        if not tracer:
            raise HTTPException(
                status_code=404,
                detail="No active import tracer found"
            )

        tracer_emp_id = tracer.emp_id

        # ─────────────────────────────────────────────
        # 2️⃣ Assign Using Existing Service
        # ─────────────────────────────────────────────
        await assign_user_to_worker_assignment(
            db=db,
            header_id=assign_request.header_id,
            shipment_id=assign_request.shipment_id,
            oc_no=assign_request.oc_no,

            # 🔥 AUTO EMP ID (Of traacer)
            emp_id=tracer_emp_id,

            current_user_role=current_user.role,
            changed_by=current_user.emp_id,

            ip_address=request.client.host if request.client else None,
            user_agent=request.headers.get("user-agent"),
            device_id=assign_request.device_id,
        )

        return ResponseOfWorkerAssignment(
            success=True,
            message="Tracer successfully assigned",
            oc_num=assign_request.oc_no,
            emp_id=tracer_emp_id,
        )

    except HTTPException:
        raise

    except Exception as e:
        raise HTTPException(
            status_code=500,
            detail="Failed to assign tracer"
        )


# IT will mark the shipment which have damage report and not resolved yet to need tracer and then only those shipment will come in tracer dashboard for assignmnet (IT ONLY CHANGE THE DAMAGE AND SHIPMENT LEVEL STATUS TO NEED-TRACER)
@router.post("/mark-need-tracer")
async def mark_need_tracer(
    request: MarkNeedTracerRequest,
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user)
):

    shipment = await mark_shipment_need_tracer(
        db=db,
        header_id=request.header_id,
        shipment_id=request.shipment_id,
        oc_no=request.oc_no,
        device_id=request.device_id,
        changed_by=current_user.emp_id,
        role=current_user.role,
    )

    return {
        "success": True,
        "message": "Shipment marked as NEED_TRACER successfully",
        "shipment_id": shipment.id,
        "damage_report_status": shipment.damage_report_status
    }





# 👌============================ AUTO ASSIGN POM OC SHIPMENT TO PERTICULAR EMPLOYEE =====================

@router.post("/auto-assign-pom")
async def auto_assign_pom_api(
    date: date = Query(..., description="IST date (same logic as process-and-save)"),
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),
):
    result = await auto_assign_pom_shipments(
        db=db,
        process_date=date, # IST date letter I chnage it to utc date range in service layer
        assigned_by=current_user.emp_id,
    )

    return {
        "success": True,
        "date": str(date),
        "stats": result,
    }







# ================================================================================

@router.put("/drop-zone-update")
async def update_drop_zone_api(
    request: Request,
      payload: DropZoneUpdateRequest = Body(...),
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
):
    allowed_ids = ["521546", "518399", "523250", "518339","523556"]

    if current_user.emp_id not in allowed_ids:
        raise HTTPException(
            status_code=403,
            detail="You are not authorized to access this resource"
        )
    
    # Convert empty string to None here
    drop_zone_val = payload.drop_dlv_zone if payload.drop_dlv_zone and payload.drop_dlv_zone.strip() != "" else None

    return await update_drop_dlv_zone(

        db=db,

        header_id=payload.header_id,
        shipment_id=payload.shipment_id,
        oc_no=payload.oc_no,

        emp_id=current_user.emp_id,
        current_user_role=current_user.role,

        drop_dlv_zone=drop_zone_val,

        ip_address=request.client.host if request.client else None,
        user_agent=request.headers.get("user-agent"),
    )


# =================================== SUMMARY DASHBOARD WORKER ASSIGNMENT ===================================
@router.get(
    "/top-performer/in-date-range",
    description="start_date and end_date must be in format: YYYY-MM-DD"
)
async def get_top_performer_worker(
    start_date: str = Query(...),
    end_date: str = Query(...),

    limit: int = Query(10, ge=1, le=150),

    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    """
    Get top performing operators in date range
    """

    # ================================
    # 1️⃣ VALIDATE FORMAT
    # ================================

    try:
        start_dt = datetime.strptime(start_date, "%Y-%m-%d")
        end_dt = datetime.strptime(end_date, "%Y-%m-%d")
    except ValueError:
        raise HTTPException(
            status_code=400,
            detail="Invalid date format. Use YYYY-MM-DD"
        )

    # ================================
    # 2️⃣ VALIDATE ORDER
    # ================================

    # String compare is safe for YYYY-MM-DD
    if start_date > end_date:
        raise HTTPException(
            status_code=400,
            detail="start_date cannot be after end_date"
        )

    # ================================
    # 3️⃣ VALIDATE RANGE (<= 32 days)
    # ================================

    date_diff = (end_dt - start_dt).days

    if date_diff > 32:
        raise HTTPException(
            status_code=400,
            detail="Date range cannot exceed 32 days"
        )

    # ================================
    # 4️⃣ CALL SERVICE (PASS STRING)
    # ================================

    data = await get_top_performers(
        db=db,
        start_date=start_date,   # ✅ still string
        end_date=end_date,       # ✅ still string
        limit=limit
    )

    return {
        "start_date": start_date,
        "end_date": end_date,
        "count": len(data),
        "data": data
    }
