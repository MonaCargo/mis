# app/api/routes/appConfig/app_config.py

from fastapi import APIRouter, Depends, Request
from sqlalchemy.ext.asyncio import AsyncSession
from pydantic import BaseModel
from typing import Optional
from app.core.dependency import require_roles, verify_token_and_get_user
from app.db.session import get_db
from app.services.app_config.app_config_service import AppConfigService

router = APIRouter()


class UpdateConfigRequest(BaseModel):
    value: str
    changed_by: str
    change_reason: Optional[str] = None

class CreateConfigRequest(BaseModel):
    module: str
    key: str
    value: str
    data_type: str          # int | decimal | string | boolean
    label: Optional[str] = None
    description: Optional[str] = None
    unit: Optional[str] = None
    created_by: str


@router.post("/create")
async def create_config(
    request_body: CreateConfigRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_roles(["super_admin"]))
):
    """Create a new config entry."""
    return await AppConfigService.create(
        db=db,
        module=request_body.module,
        key=request_body.key,
        value=request_body.value,
        data_type=request_body.data_type,
        label=request_body.label,
        description=request_body.description,
        unit=request_body.unit,
        created_by= current_user.emp_id or request_body.created_by
    )


@router.get("/{module}")
async def get_module_config(
    module: str,
    db: AsyncSession = Depends(get_db),
):
    """Get all active config for a module."""
    return await AppConfigService.get_by_module(db, module)


@router.get("/{module}/{key}")
async def get_single_config(
    module: str,
    key: str,
    db: AsyncSession = Depends(get_db)
):
    """Get single config value with cast."""
    value = await AppConfigService.get_value(db, module, key)
    return {"module": module, "key": key, "cast_value": value}


@router.put("/{module}/{key}")
async def update_config(
    module: str,
    key: str,
    request_body: UpdateConfigRequest,
    request: Request,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(require_roles(["super_admin","management"]))
):
    """Update a config value — logs old/new automatically."""
    ip = request.client.host if request.client else None
    return await AppConfigService.update_value(
        db=db,
        module=module,
        key=key,
        new_value=request_body.value,
        changed_by=current_user.emp_id or request_body.changed_by,
        change_reason=request_body.change_reason,
        ip_address=ip
    )


@router.get("/{module}/logs/all")
async def get_config_logs(
    module: str,
    key: str = None,
    limit: int = 50,
    db: AsyncSession = Depends(get_db),
    current_user = Depends(verify_token_and_get_user)
):
    """Get change history for a module (optionally filtered by key)."""
    return await AppConfigService.get_logs(db, module, key, limit)