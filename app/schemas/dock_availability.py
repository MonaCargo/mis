from pydantic import BaseModel, Field
from datetime import datetime
from typing import Optional

class DockBase(BaseModel):
    dock_no: str = Field(..., max_length=50, regex=r"^DOC-\d{2}$")
    is_dock_occupied: Optional[bool] = False
    dock_in_time: Optional[datetime] = None

class DockCreate(DockBase):
    pass

class DockUpdate(BaseModel):
    is_dock_occupied: Optional[bool] = None
    dock_in_time: Optional[datetime] = None

class DockResponse(DockBase):
    id: int
    created_at: datetime
    updated_at: datetime

    class Config:
        from_attributes = True