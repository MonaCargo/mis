
# Auth and Role-Based Access Control Middleware

import logging
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, OAuth2PasswordBearer
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.user import User
from typing import List
from app.db.session import get_db
from app.services.user_service import get_user_by_emp_id
from app.utils.auth_helper import decode_access_token

# oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/login")
oauth2_scheme  = HTTPBearer()
logger = logging.getLogger(__name__)

# ✅ Auth Middleware: Verify token and return current user
async def verify_token_and_get_user(token: str = Depends(oauth2_scheme), db: AsyncSession = Depends(get_db)):
    print("token",token)
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    
    logger.info(f"Received token: {token.credentials}")

    # Extract the actual token string from HTTPBearer object
    token_string = token.credentials
    logger.info(f"Received token: {token_string}")
    payload = decode_access_token(token_string)

    # print(payload,"=============================")
    if not payload:
        raise credentials_exception

    emp_id = payload.get("emp_id")
    if not emp_id:
        raise credentials_exception

    
    user = await get_user_by_emp_id(emp_id, db)
     # ✅ Add this check — ensures user is valid and active
    if not user or not getattr(user, "is_active", True):
        raise credentials_exception

    return user

def require_roles(required_roles: List[str]):
    async def role_checker(current_user: User = Depends(verify_token_and_get_user)):
        if current_user.role not in required_roles:
            raise HTTPException(
                status_code=status.HTTP_403_FORBIDDEN,
                detail=f"Operation requires one of the roles: {', '.join(required_roles)}",
            )
        return current_user
    return role_checker