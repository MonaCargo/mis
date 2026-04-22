from typing import List, Optional
from pydantic import BaseModel, Field, field_validator

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
    created_by: Optional[int] = None   # 👈 added this

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





class UserPasswordChange(BaseModel):
    password: str = Field(..., min_length=4, max_length=200)
    
    @field_validator("password", mode="before")
    def strip_password(cls, v):
        if isinstance(v, str):
            v = v.strip()   # 🔥 remove leading/trailing spaces
        return v

    @field_validator("password")
    def validate_password(cls, v):
        if " " in v:
            raise ValueError("Password cannot contain spaces in between.")
        if len(v) < 6:
            raise ValueError("Password must be at least 6 characters.")
        if len(v) > 12:
            raise ValueError("Password cannot exceed 12 characters.")
        return v

    

class UserPasswordChangeResponse(APIResponseBase):
    emp_id:str
 

class UpdateUserRoleRequest(BaseModel):
    user_id: int
    role: str