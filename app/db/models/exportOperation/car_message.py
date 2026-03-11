# models/export_car_message_awb_master.py

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String, DateTime, Float, UniqueConstraint,Index
from sqlalchemy.sql import func
from app.db.base import Base
from sqlalchemy.orm import relationship

class ExportCarMessageAwbMaster(Base):
    __tablename__ = "export_car_message_awb_master"

    __table_args__ = (
        #  UNIQUE constraint
        UniqueConstraint(
            "awb_no",
            name="uq_awb_car_msg"
        ),

        #Composite index for fast lookup
        Index(
            "idx_awb_car_msg",
            "awb_no"
        ),
        Index(
            "idx_car_message_date_time_combo",
            "car_message_datetime_combo"
        ),
    )

    id = Column(Integer, primary_key=True, index=True)

    awb_no = Column(String(11), index=True, nullable=False)

    origin = Column(String(10), nullable=False)
    destination = Column(String(10), nullable=False)

    sb_no = Column(String(50), nullable=True)
    sb_date = Column(DateTime, nullable=True)

    hwb_no = Column(String(50), nullable=True)

    pcs = Column(Integer, nullable=True)
    gross_wt = Column(Float, nullable=True)
    volumetric_wt = Column(Float, nullable=True)
    chg_wt = Column(Float, nullable=True)

    nog = Column(String(200), nullable=True)
    shc = Column(String(50), nullable=True)

    # ✅ Correct types
    car_msg_date = Column(Date, nullable=True)
    car_msg_time = Column(String(20), nullable=True)

    uploaded_by = Column(String(20), nullable=True)

    # ✅ UTC combo datetime
    car_message_datetime_combo = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )


    created_at = Column(DateTime(timezone=True),nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)
 


# ✌️ AWB AND SKID MAPPING TABLES
class ExportAwbSkidMapping(Base):
    __tablename__ = "export_awb_skid_mapping"

    __table_args__ = (
    # 💀💀 check this {mapping unique by skid id and awb master id for if any scaniing goining then resume again that skid }
    UniqueConstraint(
            "awb_master_id",
            "skid_id",
            name="uq_awb_per_skid"
        ),)
   

    id = Column(Integer, primary_key=True)

    awb_master_id = Column(
        Integer,
        ForeignKey("export_car_message_awb_master.id"),
        nullable=False
    )

    skid_id = Column(
        Integer,
        ForeignKey("export_skid_master.id"),
        nullable=True
    )

    virtual_skid_no = Column(String(50), nullable=True)
    is_virtual = Column(Boolean, default=False)

    is_skid_used_complete = Column(Boolean, nullable=False, default=False) 

    created_at = Column(DateTime(timezone=True),
                        server_default=func.now(),
                        nullable=False)

    # 🔥 Relationships
    awb = relationship("ExportCarMessageAwbMaster", backref="skid_mapping")
    skid = relationship("ExportSkidMaster", backref="awb_mappings")
    

# -----------------------
class ExportAwbSkidItemSequence(Base):
    __tablename__ = "export_awb_skid_item_sequence"

    __table_args__ = (
        UniqueConstraint("sequence_no", name="uq_unique_sequence"),
        Index("idx_awb_sequence", "awb_master_id"),
    )

    id = Column(Integer, primary_key=True)

    awb_master_id = Column(
        Integer,
        ForeignKey("export_car_message_awb_master.id"),
        nullable=False
    )

    scan_by_device = Column(String(100), nullable=True)   # ← ADD
    scanned_by = Column(String(20), nullable=True)           # ← ADD (emp id)

    mapping_id = Column(
        Integer,
        ForeignKey("export_awb_skid_mapping.id"),
        nullable=False
    )

    sequence_no = Column(String(50), nullable=False)
    sequence_date_time = Column(DateTime(timezone=True),nullable=False)


    awb = relationship("ExportCarMessageAwbMaster", backref="items")
    mapping = relationship("ExportAwbSkidMapping", backref="items")




# ✌️EXPORT skid location mapping Table--------------------------- 
class ExportSkidLocationMapping(Base):
    __tablename__ = "export_skid_location_mapping"

    __table_args__ = (
        # Fast lookup — current location of a skid
        Index("idx_skid_loc_current", "skid_id", "is_current"),

        # AWB + date range search
        Index("idx_skid_loc_awb_date", "awb_master_id", "assigned_at"),

        # Location + date search
        Index("idx_skid_loc_location_date", "location_id", "assigned_at"),

        # Narrow search — AWB + location
        Index("idx_skid_loc_awb_location", "awb_master_id", "location_id"),
    )

    id = Column(Integer, primary_key=True)

    skid_id = Column(
        Integer,
        ForeignKey("export_skid_master.id"),
        nullable=False,
    )

    location_id = Column(
        Integer,
        ForeignKey("export_locations_master.id"),
        nullable=False,
    )

    awb_master_id = Column(
        Integer,
        ForeignKey("export_car_message_awb_master.id"),
        nullable=False,
    )

    # Links to the scanning session — gives item count context without extra joins
    mapping_id = Column(
        Integer,
        ForeignKey("export_awb_skid_mapping.id"),
        nullable=False,
    )

    assigned_at = Column(DateTime(timezone=True), nullable=False)
    assigned_by = Column(String, nullable=False)    # emp_id

    # True = current location of skid
    # False = historical (skid has moved to another location since)
    # Only ONE row per skid should ever have is_current=True at a time
    is_current = Column(Boolean, default=True, nullable=False)

    # this tell that this location is current or relocated (true menas relocated or it is history not current)
    is_relocation = Column(Boolean, default=False, nullable=False)

    # when any one remove this (or pick this skid from location then it add this )
    picked_at = Column(DateTime(timezone=True), nullable=True)
    picked_by = Column(String, nullable=True)  

    # ── Relationships ─────────────────────────────────────────────
    skid = relationship("ExportSkidMaster", backref="location_mappings")
    location = relationship("ExportLocationsMaster", backref="skid_mappings")
    awb = relationship("ExportCarMessageAwbMaster", backref="skid_locations")
    mapping = relationship("ExportAwbSkidMapping", backref="location_assignments")





#     | Table                         | FK                                      | Relationship |
# | ----------------------------- | --------------------------------------- | ------------ |
# | export_awb_skid_mapping       | awb_master_id → awb_master.id           | awb          |
# | export_awb_skid_mapping       | skid_id → export_skid_master.id         | skid         |
# | export_awb_skid_item_sequence | mapping_id → export_awb_skid_mapping.id | mapping      |
