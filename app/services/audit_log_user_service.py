from app.db.models.audit_log_user import UserAuditLog
from app.utils.common.helperFunction import get_utc_now


async def log_user_audit(
    db,
    *,
    user,  # ✅ FIXED: was assignment
    field_name: str,
    old_value,
    new_value,
    changed_by: str,
    changed_by_role:str,
    ip_address: str | None = None,
    user_agent: str | None = None,
    device_id: str | None = None,
    db_action: str,
    source_action: str,
):
    db.add(
        UserAuditLog(
            user_id=user.id,

            field_name=field_name,
            old_value=str(old_value) if old_value is not None else None,
            new_value=str(new_value) if new_value is not None else None,

            db_action=db_action,
            source_action=source_action,

            changed_by=changed_by,
            changed_by_role=changed_by_role,
            ip_address=ip_address,
            user_agent=user_agent,
            device_id=device_id,  # ✅ FIXED: now stored

            changed_at=get_utc_now(),
            created_at=get_utc_now(),
        )
    )
