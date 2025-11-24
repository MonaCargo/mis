#  this is used as a base schema for API responses (only in responses)
# app/schemas/base.py
from pydantic import BaseModel, ConfigDict

class APIResponseBase(BaseModel):
    success: bool
    message: str
   
    model_config = ConfigDict(
        extra="allow",
        from_attributes=True
    )   
   

# ✅ Pagination metadata schema
class Pagination(BaseModel):
    total: int
    limit: int
    offset: int
