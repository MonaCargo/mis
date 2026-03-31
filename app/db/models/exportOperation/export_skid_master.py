


from sqlalchemy import Boolean, Column, Integer, String, DateTime, Float,Index, UniqueConstraint
from app.db.base import Base
from sqlalchemy.orm import relationship

# ✌️SkidMaster model=============================
class ExportSkidMaster(Base):
    __tablename__ = "export_skid_master"

    __table_args__ = (
        Index("idx_export_skid_no", "skid_no"),
        Index("idx_export_skid_type", "skid_type"),
        UniqueConstraint(
            "skid_no",
            name="uq_export_skid_no"
        ),
    )

    id = Column(Integer, primary_key=True)

    # 🔹 Unique skid number (barcode scanned)
    skid_no = Column(String(50),nullable=False)

    # 🔹 Weight of empty skid (kg)
    skid_wgt = Column(Float, nullable=True)

    # 🔹 Maximum allowed capacity (kg or pcs based on your logic)
    skid_capacity = Column(Float, nullable=True)

    # 🔹 Type (virtual/real) {real menas mad or buy by us and virtual means not our made skid}
    skid_type = Column(String(30), nullable=False)

    # 🔹 Remarks
    remarks = Column(String(255), nullable=True)

    # 🔹 Active / inactive skid
    is_active = Column(Boolean, default=True, nullable=False)

    # 🔥 skid Locking fields
    is_locked = Column(Boolean, default=False, nullable=False)
    locked_at = Column(DateTime(timezone=True), nullable=True)
    locked_by_user_id = Column(String, nullable=True)

    #🔥 This used to identified those skid no. which generated but not used by user (is_vitual_used =TRUE, menase used)
    # we make it defalt true but when generate vskdNo. thenmake it false  and during validate and lock time it used then make it true 
    is_virtual_used   =  Column(Boolean, default=True, nullable=False)

    created_at = Column(
        DateTime(timezone=True),
        nullable=False
    )

    created_by = Column(String(20), nullable=True)

    updated_at = Column(
        DateTime(timezone=True),
        nullable=False
    )
