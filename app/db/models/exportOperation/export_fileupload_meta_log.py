

from sqlalchemy import JSON, Column, DateTime, Integer, String, Text

from app.db.base import Base

class ExportFileUploadMetaLog(Base):
    __tablename__ = "export_fileupload_meta_log"

    id = Column(Integer, primary_key=True)

    filename = Column(String(255), nullable=False)
    file_type = Column(String(10), nullable=False)

    file_track_type = Column(String(25), nullable=False) # which file you try to tracked like carmess excel of or onhold pdf

    uploaded_by = Column(String(20), nullable=True)
    uploaded_at = Column(DateTime(timezone=True), nullable=False)

    status = Column(String(10), nullable=False)        # SUCCESS / FAILED

    upload_meta = Column(JSON, nullable=True)          # ✅ all counts + extra info here

    error_message = Column(Text, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False)