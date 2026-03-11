# # from fastapi import APIRouter, Depends, HTTPException
# # from sqlalchemy.ext.asyncio import AsyncSession
# # from sqlalchemy.future import select
# # from passlib.context import CryptContext

# # from app.db.session import get_db
# # from app.db.models.user import User
# # from app.schemas.user import UserCreate, UserRead

# # router = APIRouter(prefix="/users", tags=["Users"])
# # pwd_context = CryptContext(schemes=["bcrypt"], deprecated="auto")

# # @router.post("/", response_model=UserRead)
# # async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
# #     result = await db.execute(select(User).where(User.email == user.email))
# #     existing_user = result.scalar_one_or_none()
# #     if existing_user:
# #         raise HTTPException(status_code=400, detail="Email already registered")

# #     hashed_pw = pwd_context.hash(user.password)
# #     new_user = User(email=user.email, hashed_password=hashed_pw)
# #     db.add(new_user)
# #     await db.commit()
# #     await db.refresh(new_user)
# #     return new_user













# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.future import select

# from app.db.session import get_db
# from app.db.models.user import User
# from app.schemas.user import UserCreate, UserRead

# router = APIRouter(prefix="/users", tags=["Users"])

# @router.post("/", response_model=UserRead)
# async def create_user(user: UserCreate, db: AsyncSession = Depends(get_db)):
#     result = await db.execute(select(User).where(User.emp_id == user.emp_id))
#     existing_user = result.scalar_one_or_none()
#     if existing_user:
#         raise HTTPException(status_code=400, detail="Employee ID already registered")

#     new_user = User(
#         emp_id=user.emp_id,
#         name=user.name,
#         password=user.password  # Plain password as per your request
#     )
#     db.add(new_user)
#     await db.commit()
#     await db.refresh(new_user)
#     return new_user







from fastapi import APIRouter, Depends, File, HTTPException, Query, Request, UploadFile
from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession
from app.core.dependency import require_roles, verify_token_and_get_user
from app.db.models.user import User
from app.db.session import get_db
from app.schemas.user import UserCreate, UserCreateResponse, UserPasswordChange, UserPasswordChangeResponse,UserReadResponse, UserListResponse, UserRead, UserStatusUpdate, UserStatusUpdateResponse
from app.services.user_service import (
    bulk_create_users,
    get_active_import_tracer,
    get_all_active_import_tracers_users,
    get_all_users_paginated,
    get_all_users_paginated_filter_apply,
    get_user_by_emp_id,
    create_user as create_user_service,
    update_user_password,
    update_user_status
)
from app.utils.common.clean_bulck_user_excel import parse_user_excel
from app.utils.common.get_request_ip import get_request_ip

router = APIRouter(prefix="", tags=["Users"])




@router.get("/get-all-active-import-tracers")
async def fetch_active_import_tracers(
    db: AsyncSession = Depends(get_db),
):
    tracers = await get_all_active_import_tracers_users(db)

    if not tracers:
        return {
            "success": True,
            "data": []
        }

    return {
        "success": True,
        "message": "Tracers retrieved successfully",
        "data": [
            {
                "emp_id": u.emp_id,
                "name": u.name,
            }
            for u in tracers
        ]
    }


# Create a new user
@router.post("/", response_model=UserCreateResponse)
async def create_user(user: UserCreate, 
                      request: Request, # this is used for getting ip it is come from fast api instance
                      db: AsyncSession = Depends(get_db),
                      current_user: User = Depends(verify_token_and_get_user)

                      ):
    existing_user = await get_user_by_emp_id(user.emp_id, db)

     # Get IP address from request
    ip_address = get_request_ip(request)
    user_agent=request.headers.get("user-agent")
    device_id = None

    if existing_user:
        raise HTTPException(status_code=400, detail="Employee ID already registered")
    new_user = await create_user_service(user,
                                          db,created_by=current_user.emp_id,
                                          changed_by_role = current_user.role,
                                          ip_address=ip_address,       # 👈 PASS HERE
                                            user_agent=user_agent,
                                            device_id=device_id)
    return UserCreateResponse(success=True, message="User created successfully",  user=UserRead.model_validate(new_user))

# Get a user by emp_id
@router.get("/{emp_id}", response_model=UserReadResponse)
async def read_user(emp_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_emp_id(emp_id, db)
    print (user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserReadResponse(
        success=True,
        message="User fetched successfully",
        user=UserRead.model_validate(user)
    )    


# Update user status (is Active)
@router.put("/{emp_id}/status", response_model=UserStatusUpdateResponse)
async def update_user_status_api(
    emp_id: str,  # coming from the URL
    status_data: UserStatusUpdate,  # contains only is_active
    db: AsyncSession = Depends(get_db)
):
    user = await update_user_status(emp_id, status_data.is_active, db)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")

    return UserStatusUpdateResponse(
        success=True,
        message="User status updated successfully",
        user=UserRead.model_validate(user)
    )





# ✅ Get all users (paginated with filters)
@router.get("/", response_model=UserListResponse, summary="Get all users with pagination and filters")
async def read_all_users(
    db: AsyncSession = Depends(get_db),
    page: int = Query(1, ge=1, description="Page number"),
    limit: int = Query(10, description="Number of users per page (max 20)", ge=1, le=100),
    search: str | None = Query(None, description="Search users by name or emp_id"),
    role: str | None = Query(None, description="Filter by role"),
    is_active: str | None = Query(None, description="Filter by active status (true/false)"),
    sort: str | None = Query("createdAt", description="Sort users by field (name, createdAt, updatedAt)"),
    order: str = Query("desc", description="Sort order (asc/desc)", regex="^(asc|desc)$"),
    current_user: User = Depends(require_roles(["super_admin","admin"]))
):
    try:
        print("something happen-------------------")
        # ✅ Enforce maximum allowed limit manually
        max_limit = 20
        if limit > max_limit:
            limit = max_limit
        # ✅ Convert is_active string to boolean if provided
        is_active_bool = None
        if is_active is not None:
            if is_active.lower() == 'true':
                is_active_bool = True
            elif is_active.lower() == 'false':
                is_active_bool = False
            else:
                raise HTTPException(
                    status_code=400, 
                    detail="is_active must be 'true' or 'false'"
                )

        # # ✅ Validate role if provided
        # if role:
        #     valid_roles = ["admin", "user", "manager", "editor", "security"] #⚠️⚠️⚠️⚠️
        #     if role not in valid_roles:
        #         raise HTTPException(
        #             status_code=400,
        #             detail=f"Invalid role. Must be one of: {', '.join(valid_roles)}"
        #         )

        users, total_count = await get_all_users_paginated_filter_apply(
            db=db,
            page=page,
            limit=limit,
            search=search,
            role=role,
            is_active=is_active_bool,
            sort=sort,
            order=order
        )

        # ✅ Calculate total pages
        total_pages = (total_count + limit - 1) // limit

        return UserListResponse(
            success=True,
            message="Users retrieved successfully",
            users=[UserRead.model_validate(u) for u in users],
            total=total_count,
            page=page,
            limit=limit,
            totalPages=total_pages,
            count=len(users)
        )

    except HTTPException:
        raise
    except Exception as e:
        # logger.error(f"Error fetching users: {str(e)}")
        raise HTTPException(
            status_code=500,
            detail="Internal server error while fetching users"
        )


# Update/change user password
@router.put("/{emp_id}/change-password", response_model=UserPasswordChangeResponse, summary="Update user password")
async def update_user_password_api(
    emp_id: str,
    password_data: UserPasswordChange,
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(require_roles(["super_admin"]))
):
    updated = await update_user_password(emp_id, password_data.password, db)

    if not updated:
        raise HTTPException(status_code=404, detail="User not found")

    return UserPasswordChangeResponse(
        success=True,
        message="Password updated successfully",
        emp_id=emp_id
    )




# ==================== bulk upload

# @router.post("/bulk-upload", summary="Bulk upload users via Excel")
# async def bulk_upload_users(
#     request: Request,
#     file: UploadFile = File(...),
#     db: AsyncSession = Depends(get_db),
#     current_user: User = Depends(verify_token_and_get_user),
# ):
#     if not file.filename.endswith((".xlsx", ".xls")):
#         raise HTTPException(status_code=400, detail="Only Excel files allowed")

#     users = parse_user_excel(file.file)

#     created_users = await bulk_create_users(
#         users=users,
#         db=db,
#         created_by=current_user.emp_id,
#         changed_by_role=current_user.role,
#         ip_address=get_request_ip(request),
#         user_agent=request.headers.get("user-agent"),
#         device_id=None,
#     )

#     return {
#         "success": True,
#         "message": f"{len(created_users)} users created successfully",
#     }


@router.post("/bulk-upload", summary="Bulk upload users via Excel")
async def bulk_upload_users(
    request: Request,
    file: UploadFile = File(...),
    db: AsyncSession = Depends(get_db),
    current_user: User = Depends(verify_token_and_get_user),
):
    if not file.filename.endswith((".xlsx", ".xls")):
        raise HTTPException(status_code=400, detail="Only Excel files allowed")

    users = parse_user_excel(file.file)

    created_users,skipped_users = await bulk_create_users(
        users=users,
        db=db,
        created_by=current_user.emp_id,
        changed_by_role=current_user.role,
        ip_address=get_request_ip(request),
        user_agent=request.headers.get("user-agent"),
        device_id=None,
    )

    return {
        "success": True,
        "created_count": len(created_users),
        "skipped_count": len(skipped_users),
        "skipped_emp_ids": skipped_users,  # so frontend knows exactly who was skipped
        "message": f"{len(created_users)} users created, {len(skipped_users)} already existed and were skipped.",
    }


# Get a user by emp_id
@router.get("/{emp_id}", response_model=UserReadResponse)
async def read_user(emp_id: str, db: AsyncSession = Depends(get_db)):
    user = await get_user_by_emp_id(emp_id, db)
    print (user)
    if not user:
        raise HTTPException(status_code=404, detail="User not found")
    
    return UserReadResponse(
        success=True,
        message="User fetched successfully",
        user=UserRead.model_validate(user)
    ) 


