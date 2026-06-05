# app/services/appConfig/app_config_service.py

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select
from datetime import datetime, timezone
from fastapi import HTTPException, Request
from app.db.models.app_config.app_config import AppConfig, AppConfigLog


# ── Cast utility ─────────────────────────────────────────────────────────────

def cast_config_value(value: str, data_type: str):
    try:
        if data_type == "int":
            return int(value)
        elif data_type == "decimal":
            return float(value)
        elif data_type == "boolean":
            return value.strip().lower() in ("true", "1", "yes")
        else:
            return value
    except (ValueError, TypeError):
        return value


def validate_config_value(value: str, data_type: str) -> bool:
    try:
        if data_type == "int":
            int(value)
        elif data_type == "decimal":
            float(value)
        elif data_type == "boolean":
            if value.strip().lower() not in ("true", "false", "1", "0", "yes", "no"):
                return False
        return True
    except (ValueError, TypeError):
        return False


# ── Service ───────────────────────────────────────────────────────────────────

class AppConfigService:

    @staticmethod
    def _serialize(config: AppConfig) -> dict:
        return {
            "id":           config.id,
            "module":       config.module,
            "key":          config.key,
            "value":        config.value,
            "cast_value":   cast_config_value(config.value, config.data_type),
            "data_type":    config.data_type,
            "label":        config.label,
            "description":  config.description,
            "unit":         config.unit,
            "is_active":    config.is_active,
            "updated_by":   config.updated_by,
            "updated_at":   config.updated_at,
        }

    @staticmethod
    async def get_by_module(db: AsyncSession, module: str) -> list[dict]:
        stmt = select(AppConfig).where(
            AppConfig.module == module.upper(),
            AppConfig.is_active == True
        ).order_by(AppConfig.key)
        result = await db.execute(stmt)
        configs = result.scalars().all()
        return [AppConfigService._serialize(c) for c in configs]

    @staticmethod
    async def get_value(db: AsyncSession, module: str, key: str):
        """Get cast value directly — use this in services."""
        stmt = select(AppConfig).where(
            AppConfig.module == module.upper(),
            AppConfig.key == key,
            AppConfig.is_active == True
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()
        if not config:
            raise HTTPException(status_code=404, detail=f"Config not found: {module}.{key}")
        return cast_config_value(config.value, config.data_type)


    @staticmethod
    async def update_value(
        db: AsyncSession,
        module: str,
        key: str,
        new_value: str,
        changed_by: str,
        change_reason: str = None,
        ip_address: str = None
    ) -> dict:
        stmt = select(AppConfig).where(
            AppConfig.module == module.upper(),
            AppConfig.key == key
        )
        result = await db.execute(stmt)
        config = result.scalar_one_or_none()

        if not config:
            raise HTTPException(status_code=404, detail=f"Config not found: {module}.{key}")

        if not validate_config_value(new_value, config.data_type):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid value '{new_value}' for type '{config.data_type}'"
            )

        old_value = config.value

        try:
            # Both in same transaction — atomic
            config.value      = new_value
            config.updated_by = changed_by
            config.updated_at = datetime.now(timezone.utc)

            log = AppConfigLog(
                config_id=config.id,
                module=config.module,
                key=config.key,
                old_value=old_value,
                new_value=new_value,
                data_type=config.data_type,
                change_reason=change_reason,
                changed_by=changed_by,
                changed_at=datetime.now(timezone.utc),
                ip_address=ip_address
            )
            db.add(log)

            # Single commit — both save or neither saves
            await db.commit()
            await db.refresh(config)
            return AppConfigService._serialize(config)

        except Exception as e:
            await db.rollback()    # ← explicit rollback on any error
            raise HTTPException(
                status_code=500,
                detail=f"Failed to update config: {str(e)}"
            )

    @staticmethod
    async def get_logs(
        db: AsyncSession,
        module: str,
        key: str = None,
        limit: int = 50
    ) -> list[dict]:
        stmt = select(AppConfigLog).where(
            AppConfigLog.module == module.upper()
        )
        if key:
            stmt = stmt.where(AppConfigLog.key == key)
        stmt = stmt.order_by(AppConfigLog.changed_at.desc()).limit(limit)
        result = await db.execute(stmt)
        logs = result.scalars().all()
        return [
            {
                "id":            l.id,
                "module":        l.module,
                "key":           l.key,
                "old_value":     l.old_value,
                "new_value":     l.new_value,
                "data_type":     l.data_type,
                "change_reason": l.change_reason,
                "changed_by":    l.changed_by,
                "changed_at":    l.changed_at,
                "ip_address":    l.ip_address,
            }
            for l in logs
        ]
    
    @staticmethod
    async def create(
        db: AsyncSession,
        module: str,
        key: str,
        value: str,
        data_type: str,
        label: str = None,
        description: str = None,
        unit: str = None,
        created_by: str = None
    ) -> dict:
        # Validate data_type
        if data_type not in ("int", "decimal", "string", "boolean"):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid data_type '{data_type}'. Must be int | decimal | string | boolean"
            )

        # Validate value matches data_type
        if not validate_config_value(value, data_type):
            raise HTTPException(
                status_code=400,
                detail=f"Invalid value '{value}' for data_type '{data_type}'"
            )

        # Check for duplicate
        existing_stmt = select(AppConfig).where(
            AppConfig.module == module.upper(),
            AppConfig.key == key
        )
        existing_result = await db.execute(existing_stmt)
        existing = existing_result.scalar_one_or_none()

        if existing:
            raise HTTPException(
                status_code=409,
                detail=f"Config already exists: {module.upper()}.{key}. Use PUT to update it."
            )

        config = AppConfig(
            module=module.upper(),
            key=key,
            value=value,
            data_type=data_type,
            label=label,
            description=description,
            unit=unit,
            is_active= True,
            updated_by=created_by
        )
        try:
            db.add(config)
            await db.flush()

            # Log the creation
            log = AppConfigLog(
                config_id=config.id,
                module=config.module,
                key=config.key,
                old_value=None,          # None = newly created
                new_value=value,
                data_type=data_type,
                change_reason="Initial creation",
                changed_by=created_by or "SYSTEM",
                changed_at=datetime.now(timezone.utc),
                ip_address=None
            )
            db.add(log)
            await db.commit()
            await db.refresh(config)

            return AppConfigService._serialize(config)
        except Exception as e:
            await db.rollback()   # rolls back both config and log
            raise HTTPException(
                status_code=500,
                detail=f"Failed to create config: {str(e)}"
            )