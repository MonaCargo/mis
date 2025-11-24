# app/schemas/auth.py
from typing import Optional
from pydantic import BaseModel, Field
from app.schemas.user import UserRead
from app.schemas.base import APIResponseBase

class LoginRequest(BaseModel):
    emp_id: str
    password: str



class AuthResponse(APIResponseBase):
    token: str | None = None
    token_type: str = "bearer" # Default token type
    user: UserRead | None = None

class LogoutResponse(APIResponseBase):
    pass

class RefreshTokenResponse(APIResponseBase):
    token: str | None = None
    token_type: str = "bearer" # Default token type
    expires_in: Optional[int] = Field(None, description="Token expiry duration in seconds")

