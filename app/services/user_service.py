from http.client import HTTPException
from typing import List, Optional, Tuple
from sqlalchemy import asc, desc, func, or_
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.future import select
from app.db.models.user import User
from app.services.audit_log_user_service import log_user_audit
from app.utils.auth_helper import hash_password

async def get_user_by_emp_id(emp_id: str, db: AsyncSession):
    result = await db.execute(select(User).where(User.emp_id == emp_id))
    return result.scalar_one_or_none()




# # ✅ Add pagination support here (get users with pagination)
# async def get_all_users_paginated(db: AsyncSession, page: int, page_size: int):
#     offset = (page - 1) * page_size

#     # Fetch paginated users
#     users_query = await db.execute(
#         select(User)
#         .offset(offset)
#         .limit(page_size)
#     )
#     users = users_query.scalars().all()

#     # Fetch total count for metadata
#     total_query = await db.execute(select(func.count(User.id)))
#     total_count = total_query.scalar()

#     # Return both users and total count
#     return users, total_count


async def get_all_users_paginated(
    db: AsyncSession,
    page: int,
    limit: int,
    search: Optional[str] = None,
    sort: str = "createdAt",
    order: str = "desc"
) -> Tuple[List[User], int]:
    """
    Get paginated users with search, sort, and order functionality
    """
    offset = (page - 1) * limit
    
    # Base query
    query = select(User)
    
    # ✅ Apply search filter - FIXED: Now both are string columns
    if search:
        # Both name and emp_id are string columns now, so we can use ILIKE for both
        search_filter = or_(
            User.name.ilike(f"%{search}%"),
            # User.emp_id.ilike(f"%{search}%")  # ✅ Changed from == to ILIKE for string search
            User.emp_id == search # Exact match for emp_id
        )
        query = query.where(search_filter)
    
   # ✅ Validate and apply sorting
    allowed_sort_fields = {"name", "emp_id", "createdAt", "updatedAt"}
    if sort not in allowed_sort_fields:
        sort = "createdAt"  # Default to createdAt if invalid field
    
    # ✅ Fixed: Map sort field to actual column (consistent with allowed_sort_fields)
    sort_column_mapping = {
        "name": User.name,
        "emp_id": User.emp_id,
        "createdAt": User.created_at,
        "updatedAt": User.updated_at
    }
    sort_column = sort_column_mapping.get(sort, User.created_at)
    
    # ✅ Apply order
    if order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    # ✅ Apply pagination
    query = query.offset(offset).limit(limit)
    
    # Execute query for users
    users_result = await db.execute(query)
    users = users_result.scalars().all()
    
    # ✅ Get total count (with same filters)
    count_query = select(func.count(User.id))
    
    # Apply same search filter to count query
    if search:
        count_query = count_query.where(search_filter)
    
    total_result = await db.execute(count_query)
    total_count = total_result.scalar()
    
    return users, total_count



async def create_user(user_data, db: AsyncSession,created_by,
                      changed_by_role:str,
                      ip_address: str | None = None,
    user_agent: str | None = None,
    device_id: str | None = None,
                      ):
    print(f"Password raw value (repr): {repr(user_data.password)}")
    print(f"Password length (chars): {len(user_data.password)}")
    print(f"Password length (bytes): {len(user_data.password.encode('utf-8'))}")
    hashed_pwd = hash_password(user_data.password)  # ✅ Hash the password

    new_user = User(
        emp_id=user_data.emp_id,
        name=user_data.name,
        password=hashed_pwd,
        role=user_data.role,
        created_by=created_by

    )
    db.add(new_user)
    await db.flush()  # 🔥 IMPORTANT (so ID is available)

    # 🧾 AUDIT LOG
    # 🧾 AUDIT LOG (CORRECT)
    await log_user_audit(
        db=db,
        user=new_user,
        field_name="user",
        old_value=None,
        new_value=f"User {new_user.emp_id} created",
        changed_by=created_by,
        changed_by_role = changed_by_role,
        ip_address=ip_address,
        user_agent=user_agent,
        device_id=device_id,
        db_action="CREATE",
        source_action="user_create",
    )

  
    await db.commit()
    await db.refresh(new_user)
    return new_user



async def update_user_status(emp_id: str, is_active: bool, db: AsyncSession):
    result = await db.execute(select(User).where(User.emp_id == emp_id))
    user = result.scalar_one_or_none()
    
    if not user:
        return None

    user.is_active = is_active
    await db.commit()
    await db.refresh(user)
    return user



async def get_all_users_paginated_filter_apply(
    db: AsyncSession,
    page: int,
    limit: int,
    search: Optional[str] = None,
    role: Optional[str] = None,
    is_active: Optional[bool] = None,
    sort: str = "createdAt",
    order: str = "desc"
) -> Tuple[List[User], int]:
    """
    Get paginated users with search, filters, sort, and order functionality
    """
    offset = (page - 1) * limit
    
    # Base query
    query = select(User)
    
    # ✅ Apply search filter
    if search:
        search_filter = or_(
            User.name.ilike(f"%{search}%"),
            User.emp_id == search  # Exact match for emp_id
        )
        query = query.where(search_filter)
    
    # ✅ Apply role filter
    if role:
        query = query.where(User.role == role)
    
    # ✅ Apply status filter
    if is_active is not None:
        query = query.where(User.is_active == is_active)
    
    # ✅ Validate and apply sorting
    allowed_sort_fields = {"name", "emp_id", "createdAt", "updatedAt"}
    if sort not in allowed_sort_fields:
        sort = "createdAt"  # Default to createdAt if invalid field
    
    # ✅ Map sort field to actual column
    sort_column_mapping = {
        "name": User.name,
        "emp_id": User.emp_id,
        "createdAt": User.created_at,
        "updatedAt": User.updated_at
    }
    sort_column = sort_column_mapping.get(sort, User.created_at)
    
    # ✅ Apply order
    if order == "desc":
        query = query.order_by(desc(sort_column))
    else:
        query = query.order_by(asc(sort_column))
    
    # ✅ Apply pagination
    query = query.offset(offset).limit(limit)
    
    # Execute query for users
    users_result = await db.execute(query)
    users = users_result.scalars().all()
    
    # ✅ Get total count (with same filters)
    count_query = select(func.count(User.id))
    
    # Apply same filters to count query
    if search:
        search_filter = or_(
            User.name.ilike(f"%{search}%"),
            User.emp_id == search
        )
        count_query = count_query.where(search_filter)
    if role:
        count_query = count_query.where(User.role == role)
    if is_active is not None:
        count_query = count_query.where(User.is_active == is_active)
    
    total_result = await db.execute(count_query)
    total_count = total_result.scalar()
    
    return users, total_count





async def update_user_password(emp_id: str, new_password: str, db: AsyncSession):
    """
    Update/change the password of a user by emp_id.
    Returns the updated user object or None if not found.
    """

    # Fetch the user
    new_password = new_password.strip()  # 🔥 ensure trimmed
    
    result = await db.execute(select(User).where(User.emp_id == emp_id))
    user = result.scalar_one_or_none()

    if not user:
        return None
    
    # Extra backend check (security)
    if len(new_password) < 6:
        raise HTTPException(status_code=400, detail="Password must be at least 6 characters.")
    if len(new_password) > 12:
        raise HTTPException(status_code=400, detail="Password cannot exceed 12 characters.")
    if " " in new_password:
        raise HTTPException(status_code=400, detail="Password cannot contain spaces.")

    # Hash the new password
    hashed_pwd = hash_password(new_password)

    # Update password field
    user.password = hashed_pwd

    # Save changes
    await db.commit()
    await db.refresh(user)

    return user