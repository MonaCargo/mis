# models/export_car_message_awb_master.py

from sqlalchemy import Boolean, Column, Date, ForeignKey, Integer, String, DateTime, Float, Text, UniqueConstraint,Index
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

         # ✅ Partial index — only indexes RCS rows, skips all null/other status rows
    Index(
        "idx_awb_rcs_status",
        "status",
        postgresql_where=(Column("status") == "RCS")
    ),
    )

    id = Column(Integer, primary_key=True, index=True)

    awb_no = Column(String(11), index=True, nullable=False)

    origin = Column(String(10), nullable=True)
    destination = Column(String(10), nullable=True)

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

    # These fields come from pdf extraction
    status = Column(String(50), nullable=True)
    agent = Column(String(50), nullable=True)
    vol_mc = Column(Float, nullable=True)
    rcs_datetime = Column(
        DateTime(timezone=True),
        nullable=True,
        index=True
    )

    # This is set to true when AWB is marked for ultra-fast processing (bypassing some normal checks and flows)
    is_ultra_fast = Column(Boolean, nullable=False, default=False)


    is_ultra_fast_marked_by = Column(String(20), nullable=True)  # emp_id of user who marked this AWB as ultra-fast, null if not marked or auto-marked
    is_ultra_fast_marked_at = Column(DateTime(timezone=True), nullable=True)


    is_manually_created= Column(Boolean, nullable=False, default=False)  # True if created manually via API, False if created via PDF upload
    manual_created_by = Column(String(20), nullable=True)  # emp_id of user who manually created this AWB, null if created via PDF upload

    remarks = Column(Text, nullable=True)  # any manual remarks or notes about this AWB

    manual_creation_remarks = Column(Text, nullable=True)  # remarks specifically for manually created AWBs (e.g. reason for manual creation)

    manual_pcs = Column(Integer, nullable=True)  # manually entered pcs count (if any)
    
    
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

    mapped_by = Column(String(20), nullable=True)  # ✅ emp_id who linked skid to AWB
    mapped_at  =  Column(DateTime(timezone=True), nullable=True) # when emp/user mapping created

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



# ====================== ✌️✌️ FLIGHT BOOKING HEADER =========================================

class ExportFlightBookingHeader(Base):
    __tablename__ = "export_flight_booking_header"

    __table_args__ = (
        # Same flight not booked twice on same date
        UniqueConstraint("flight_no", "flight_date", name="uq_flight_per_date"),
        Index("idx_flight_header_date", "flight_date"),
    )

    id = Column(Integer, primary_key=True)

    flight_no = Column(String(20), nullable=False)
    flight_date = Column(Date, nullable=False)  # 😎 this is saved as ist date
    flight_dpt_datetime = Column(DateTime(timezone=True), nullable=False)  # stored as UTC {b/c it have time}

    booked_by = Column(String(20), nullable=False)      # emp_id
    booked_at = Column(DateTime(timezone=True), nullable=False)

    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    details = relationship("ExportFlightBookingDetail", backref="header")


class ExportFlightBookingDetail(Base):
    __tablename__ = "export_flight_booking_detail"

    __table_args__ = (
        # One AWB only once per flight header
        UniqueConstraint("flight_header_id", "awb_master_id", name="uq_awb_per_flight"),
        Index("idx_flight_detail_awb", "awb_master_id"),
        # In ExportFlightBookingDetail.__table_args__
    Index(
        "idx_flight_detail_awb_header",
        "awb_master_id",
        "flight_header_id"       # covers the join to header for is_active check
    ),

    )

    id = Column(Integer, primary_key=True)

    flight_header_id = Column(
        Integer,
        ForeignKey("export_flight_booking_header.id"),
        nullable=False
    )

    awb_master_id = Column(
        Integer,
        ForeignKey("export_car_message_awb_master.id"),
        nullable=False
    )

    # Pcs being booked in THIS flight for this AWB
    booked_pcs = Column(Integer, nullable=False)

    awb = relationship("ExportCarMessageAwbMaster", backref="flight_details")



# =======================✌️✌️  ULD BOOKING MODELS =================================

class ExportUldAssignment(Base):
    __tablename__ = "export_uld_assignment"

    __table_args__ = (
        # one active assignment per flight
        UniqueConstraint("flight_header_id", name="uq_uld_assignment_per_flight"),
        Index("idx_uld_assignment_flight", "flight_header_id"),
    )

    id = Column(Integer, primary_key=True)

    flight_header_id = Column(
        Integer,
        ForeignKey("export_flight_booking_header.id"),
        nullable=False,
    )

    assigned_by = Column(String(20), nullable=False)
    assigned_at = Column(DateTime(timezone=True), nullable=False)
    is_active = Column(Boolean, default=True, nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    flight_header = relationship("ExportFlightBookingHeader", backref="uld_assignment")
    details = relationship(
        "ExportUldAssignmentDetail",
        backref="assignment",
        cascade="all, delete-orphan",
    )

class ExportUldAssignmentDetail(Base):
    __tablename__ = "export_uld_assignment_detail"

    __table_args__ = (
        # same ULD not twice on same assignment
        UniqueConstraint("assignment_id", "uld_id", name="uq_uld_per_assignment"),
        Index("idx_uld_detail_assignment", "assignment_id"),
        Index("idx_uld_detail_uld", "uld_id"),
    )

    id = Column(Integer, primary_key=True)

    assignment_id = Column(
        Integer,
        ForeignKey("export_uld_assignment.id"),
        nullable=False,
    )

    uld_id = Column(
        Integer,
        ForeignKey("export_uld_master.id"),
        nullable=False,
    )

    created_at = Column(DateTime(timezone=True), nullable=False)

    # ULD CLOSING FIELDS (ULD CLOSED FOR THAT PARTICULAR FLIGHTS)
    is_closed = Column(Boolean, default=False, nullable=False)
    closed_by = Column(String(20), nullable=True)
    closed_at = Column(DateTime(timezone=True), nullable=True)


    uld = relationship("ExportUldMaster", backref="assignment_details")



# ============================= 👌 Skid base Mapping table ==================================

class ExportSkidBaseMapping(Base):
    __tablename__ = "export_skid_base_mapping"

    __table_args__ = (
        # ✅ one base drop per mapping session — not per skid
        # mapping_id is unique per skid use (one AWB+skid session)
        # so same skid can appear multiple times across different sessions
        # UniqueConstraint(
        #     "mapping_id",
        #     name="uq_skid_base_per_mapping"
        # ),

        #🤢 Now allows multiple base drops per mapping (one per cycle)
        UniqueConstraint(
            "mapping_id",
            "cycle_no",
            name="uq_skid_base_per_mapping_cycle"
        ),

        Index("idx_skid_base_mapping_id", "mapping_id"),
        Index("idx_skid_base_skid_id", "skid_id"),
        Index("idx_skid_base_awb", "awb_master_id"),
        Index("idx_skid_base_base_id", "base_id"),
        Index("idx_skid_base_dropped_at", "dropped_at"),
    )

    id = Column(Integer, primary_key=True)

    # mapping id created based on skid and awb mapping
    mapping_id = Column(
        Integer,
        ForeignKey("export_awb_skid_mapping.id"),
        nullable=False,
    )

    skid_id = Column(
        Integer,
        ForeignKey("export_skid_master.id"),
        nullable=False,
    )

    awb_master_id = Column(
        Integer,
        ForeignKey("export_car_message_awb_master.id"),
        nullable=False,
    )

    base_id = Column(
        Integer,
        ForeignKey("export_base_master.id"),
        nullable=False,
    )

    dropped_by = Column(String(20), nullable=False)
    dropped_at = Column(DateTime(timezone=True), nullable=False)

    created_at = Column(DateTime(timezone=True), nullable=False)

     #🤢 ✅ ADD — cycle number for repeated base drops on same mapping
    cycle_no = Column(Integer, nullable=False, default=1)

    # ── Relationships ──────────────────────────────────────────
    mapping = relationship("ExportAwbSkidMapping", backref="base_mapping")
    skid = relationship("ExportSkidMaster", backref="base_mappings")
    awb = relationship("ExportCarMessageAwbMaster", backref="base_mappings")
    base = relationship("ExportBaseMaster", backref="skid_mappings")




# =========== ✌️✌️✌️PUT ON ULD / PALLET AFTER TAKING FROM BASE ===================================

class ExportSequenceItemUldLoading(Base):
    __tablename__ = "export_item_uld_loading"

    __table_args__ = (
        UniqueConstraint("sequence_id", name="uq_item_uld_loading"),
        Index("idx_item_uld_flight", "flight_header_id"),
        Index("idx_item_uld_detail", "uld_assignment_detail_id"),
        Index("idx_item_uld_sequence", "sequence_id"),
    )

    id = Column(Integer, primary_key=True)

    flight_header_id = Column(
        Integer,
        ForeignKey("export_flight_booking_header.id"),
        nullable=False,
    )
    uld_assignment_detail_id = Column(
        Integer,
        ForeignKey("export_uld_assignment_detail.id"),
        nullable=False,
    )
    sequence_id = Column(
        Integer,
        ForeignKey("export_awb_skid_item_sequence.id"),
        nullable=False,
    )

    # denormalized for fast lookup without joins
    awb_master_id = Column(Integer, nullable=False)
    mapping_id = Column(Integer, nullable=False)

    loaded_by = Column(String(20), nullable=False)
    loaded_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), nullable=False)

















#     | Table                         | FK                                      | Relationship |
# | ----------------------------- | --------------------------------------- | ------------ |
# | export_awb_skid_mapping       | awb_master_id → awb_master.id           | awb          |
# | export_awb_skid_mapping       | skid_id → export_skid_master.id         | skid         |
# | export_awb_skid_item_sequence | mapping_id → export_awb_skid_mapping.id | mapping      |
