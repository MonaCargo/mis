from typing import Optional

from pydantic import BaseModel, field_validator


class ValidateLocationDetail(BaseModel):
    id: int
    loc: str
    area_code: Optional[str] = None
    ops_type: Optional[str] = None
    is_active: bool

    class Config:
        from_attributes = True


class ValidateLocationResponse(BaseModel):
    success: bool
    message: str
    location: ValidateLocationDetail

    class Config:
        from_attributes = True







class CreateLocationRequest(BaseModel):
    loc: str
    area_code: str

    @field_validator("loc")
    @classmethod
    def loc_not_empty(cls, v: str) -> str:
        v = v.strip()
        if not v:
            raise ValueError("Location name cannot be empty")
        return v

    @field_validator("area_code")
    @classmethod
    def area_code_not_empty(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("Area code cannot be empty")
        return v


class CreateLocationResponse(BaseModel):
    success: bool
    message: str
    data: dict


# ================== ULD CREATION SCHEMA

class CreateUldRequest(BaseModel):
    uld_no: str
    carrier: str

    @field_validator("uld_no")
    @classmethod
    def uld_no_not_empty(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("uld_no cannot be empty")
        return v

    @field_validator("carrier")
    @classmethod
    def carrier_not_empty(cls, v: str) -> str:
        v = v.strip().upper()
        if not v:
            raise ValueError("carrier cannot be empty")
        return v