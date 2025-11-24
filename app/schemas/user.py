from typing import List, Optional
from pydantic import BaseModel, Field

from app.schemas.base import APIResponseBase

class UserCreate(BaseModel):
    # emp_id: int
    emp_id: str =  Field(..., min_length=1, max_length=8)  # Add length constraints
    name: str
    password: str
    role: str | None = None

class UserRead(BaseModel):
    id: int
    # emp_id: int
    emp_id: str
    name: str
    role: str
    is_active:bool

    class Config:
        from_attributes = True 


class UserReadResponse(APIResponseBase):
    user:UserRead


# ✅ Request model for updating a user
class UserUpdate(BaseModel):
    name: Optional[str] = None
    password: Optional[str] = None
    role: Optional[str] = None
    is_active:Optional[bool]

    class Config:
        from_attributes = True

    


# ✅ Response model for single user creation
class UserCreateResponse(APIResponseBase):
    user: UserRead



# ✅ Response model for user list
class UserListResponse(APIResponseBase):
  
    users: List[UserRead]
    total: int  # This was missing
    page: int
    limit: int
    totalPages: int  # This was missing
    count: int  # This was missing


    
class UserStatusUpdate(BaseModel):
    is_active: bool

class UserStatusUpdateResponse(APIResponseBase):
    user: "UserRead"  # reference to your existing read schema