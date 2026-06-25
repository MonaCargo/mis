# app/services/auth_service.py
from sqlalchemy.ext.asyncio import AsyncSession
from app.services.user_service import get_user_by_emp_id
from app.utils.auth_helper import verify_password, create_access_token
from app.utils.common.helperFunction import get_utc_now

async def authenticate_user(emp_id: str, password: str, db: AsyncSession):
    user = await get_user_by_emp_id(emp_id, db)
    if not user:
        return None, None, "User not found"
        # ⛔ Block inactive user login
    if not user.is_active:
        return None, None, "User is inactive. Contact Administrator."
        
    if not verify_password(password, user.password):
        return None, None, "Invalid credentials"
    

    # 🆕 Stamp session presence on successful login
    now = get_utc_now()
    user.last_login_at = now
    user.last_active_at = now      # seed activity so they're "fresh" immediately
    user.last_logout_at = None     # clear any previous logout → derives as logged in
    await db.commit()


    token = create_access_token(data={"emp_id": user.emp_id, "role": user.role})
    return token, user, "Login successful"
