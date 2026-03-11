from typing import Optional

from pydantic import BaseModel


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
