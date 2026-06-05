# app/db/models/appConfig/app_config.py

from sqlalchemy import Boolean, Column, Integer, String, DateTime, Text, UniqueConstraint, text
from app.db.base import Base


class AppConfig(Base):
    __tablename__ = "app_config"

    id          = Column(Integer, primary_key=True, index=True)
    module      = Column(String(50), nullable=False)   # IMPORT | EXPORT | DOMESTIC | INTERNATIONAL | GLOBAL
    key         = Column(String(100), nullable=False)  # storage_free_hours | overtime_rate | ...
    value       = Column(Text, nullable=False)          # always stored as string
    data_type   = Column(String(20), nullable=False)   # int | decimal | string | boolean
    label       = Column(String(200), nullable=True)   # "Free storage window (hours)"
    description = Column(Text, nullable=True)           # longer explanation
    unit        = Column(String(50), nullable=True)    # hours | INR | minutes | null
    is_active = Column(Boolean, default=True, nullable=False)      # Y | N — soft disable without delete
    created_at  = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at  = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))
    updated_by  = Column(String(100), nullable=True)

    __table_args__ = (
        UniqueConstraint("module", "key", name="uq_app_config_module_key"),
    )


class AppConfigLog(Base):
    __tablename__ = "app_config_log"

    id            = Column(Integer, primary_key=True, index=True)
    config_id     = Column(Integer, nullable=False, index=True)   # no FK — keep logs even if config deleted
    module        = Column(String(50), nullable=False)
    key           = Column(String(100), nullable=False)
    old_value     = Column(Text, nullable=True)
    new_value     = Column(Text, nullable=False)
    data_type     = Column(String(20), nullable=False)
    change_reason = Column(String(250), nullable=True)        # optional reason from admin
    changed_by    = Column(String(20), nullable=False)
    changed_at    = Column(DateTime(timezone=True), server_default=text("NOW()"))
    ip_address    = Column(String(50), nullable=True)  # request IP for audit