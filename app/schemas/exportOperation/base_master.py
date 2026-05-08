from datetime import datetime

from pydantic import BaseModel, field_validator

from app.schemas.base import APIResponseBase


class UldBaseItem(BaseModel):
    base_name: str

    @field_validator("base_name")
    @classmethod
    def base_name_not_empty(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("base_name cannot be empty")
        return v


class UldBaseBulkCreateRequest(BaseModel):
    bases: list[UldBaseItem]

    @field_validator("bases")
    @classmethod
    def bases_not_empty(cls, v: list) -> list:
        if not v:
            raise ValueError("At least one base must be provided")
        return v


class UldBaseResponse(BaseModel):
    id: int
    base_name: str
    created_at: datetime
    updated_at: datetime
    created_by:str | None
    model_config = {"from_attributes": True}


class UldBaseBulkCreateResponse(APIResponseBase):
    inserted: int
    skipped: int
    skipped_names: list[str]
    data: list[UldBaseResponse]



class DropSkidAtBaseRequest(BaseModel):
    mapping_id: int
    base_id: int


class BaseMasterResponse(BaseModel):
    base_id: int
    base_name: str
    model_config = {"from_attributes": True}


class UldBaseVerifyResponse(APIResponseBase):
    is_valid: bool
    data: UldBaseResponse | None = None