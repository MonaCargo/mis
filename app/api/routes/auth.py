



# app/api/auth_router.py
from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.schemas.auth import LoginRequest,LogoutResponse, AuthResponse
from app.services.auth_service import authenticate_user
from app.core.dependency import verify_token_and_get_user
from app.utils.common.helperFunction import get_utc_now

router = APIRouter(prefix="", tags=["Auth"])

@router.post("/login", response_model=AuthResponse)
async def login(request: LoginRequest, db: AsyncSession = Depends(get_db)):
    print("Login request received for emp_id:", request.emp_id)
    print("Authenticating user...", request.password)
    token, user, message = await authenticate_user(request.emp_id, request.password, db)
    if not token:
        return AuthResponse(success=False, message=message)
    return AuthResponse(success=True, message=message, token=token, token_type="bearer", user=user)



@router.post("/logout", response_model=LogoutResponse)
async def logout(
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user),
):
    # Stamp logout time on the user row.
    # Idempotent — calling twice just restamps; user stays "logged out".
    current_user.last_logout_at = get_utc_now()
    await db.commit()

    return LogoutResponse(
        success=True,
        message="Logout successful",
    )