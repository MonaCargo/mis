from pydantic import BaseModel, Field
from typing import List, Optional, Dict, Any
from datetime import datetime
from app.schemas.base import APIResponseBase




class FastTrackIRMOCMergeUploadResponse(APIResponseBase):
    total_records: int
    inserted_records: int
    failed_records: int
    errors: List[Dict[str, Any]]
    sample_temp_ocs: Optional[List[str]] = None







