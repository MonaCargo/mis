

# # =================== NEW STRUCTURE ======================================================


# from sqlalchemy import Boolean, Column, Float, ForeignKey, Index, Integer, String, DateTime, text
# from sqlalchemy.orm import relationship
# from app.db.base import Base


# class ExportSlotFileRecord(Base):
#     __tablename__ = "export_slot_file"

#     id = Column(Integer, primary_key=True, index=True)
#     company_name = Column(String, nullable=False)
#     warehouse = Column(String, nullable=False)
#     zone = Column(String, nullable=False)
#     token_no = Column(String, nullable=True)
#     truck_number = Column(String, nullable=False)
#     status = Column(String, nullable=True)
#     remarks = Column(String, nullable=True)
#     cargo_type = Column(String, nullable=True)
#     rescheduled = Column(String, nullable=True)
#     rescheduled_by = Column(String, nullable=True)
#     truck_slot_from = Column(DateTime(timezone=True), nullable=False)
#     truck_in_date_time = Column(DateTime(timezone=True), nullable=True)  # it is automatically created or come from frontend (⚠️see time zone handling carefully)
#     # ✅ Store in UTC
#     created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
#     updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))


#    # ✅ Corrected new fields (camelCase in Python → snake_case in DB)
#     truck_out_date_time = Column(DateTime(timezone=True), nullable=True)
#     dock_in_date_time = Column(DateTime(timezone=True), nullable=True)
#     dock_out_date_time = Column(DateTime(timezone=True), nullable=True)
#     is_truck_in = Column(Boolean,default=False,nullable=False)      
#     is_truck_out = Column(Boolean, default=False,nullable=False) 
#     is_dock_in = Column(Boolean, default=False,nullable=False)       
#     is_dock_out = Column(Boolean, default=False,nullable=False)      
#     dock_number = Column(String, nullable=True)
#    #agin new fields
#     truck_in_by = Column(String, nullable=True)      
#     truck_out_by  = Column(String, nullable=True)     
#     dock_in_by = Column(String, nullable=True)       
#     dock_out_by = Column(String, nullable=True)  

   

        

#     # One-to-many relationship
#     awbs = relationship("ExportSlotAWB", back_populates="export_slot", cascade="all, delete-orphan")


#     # create index on token_no, truck_slotFrom and truck_number (combined index )
#     __table_args__ = (
#         Index('idx_token_truckslot_trucknumber', 'token_no', 'truck_slot_from', 'truck_number'),
#     )
    



# class ExportSlotAWB(Base):
#     __tablename__ = "export_slot_awb"

#     id = Column(Integer, primary_key=True, index=True)
#     export_slot_id = Column(Integer, ForeignKey("export_slot_file.id", ondelete="CASCADE"))
#     awb_id = Column(String, nullable=False)  # ✅ CHANGED: awbid → awb_id
#     pcs = Column(Integer, nullable=False)
#     is_additional=Column(Boolean,nullable=False,default=False)

#     export_slot = relationship("ExportSlotFileRecord", back_populates="awbs")
#     sequences = relationship("AWBSequence", back_populates="awb", cascade="all, delete-orphan")
#     created_at = Column(
#         DateTime(timezone=True),
#         nullable=False
#     )
#     updated_at = Column(
#         DateTime(timezone=True),
#         nullable=False
#     )




# class AWBSequence(Base):
#     """Child table of ExportSlotAWB to track sequences"""
#     __tablename__ = "awb_sequence"

#     id = Column(Integer, primary_key=True, index=True)
#     awb_record_id = Column(Integer, ForeignKey("export_slot_awb.id", ondelete="CASCADE"), nullable=False)
#     seq_number = Column(String, nullable=False)
#     seq_time = Column(DateTime(timezone=True), nullable=False)
    
#     # Timestamps
#     created_at = Column(
#         DateTime(timezone=True), 
#         nullable=False
#     )
#     updated_at = Column(
#         DateTime(timezone=True), 
#         nullable=False
#     )

#     # Relationship back to parent AWB
#     awb = relationship("ExportSlotAWB", back_populates="sequences")

#      # ✅ CHANGED: Index also uses awb_record_id
#     __table_args__ = (
#         Index('idx_awb_record_id_seq_number', 'awb_record_id', 'seq_number'), 
#     )





# #    ============================
# # This is the structure if we send gull response with all availble nested data (relationship)
# #   ExportSlotFullResponse
# #   └─ awbList: List[AWBEntryResponse]
# #        └─ sequences: List[AWBSequenceResponse] 












# -------------------------------------------- partial awb seq scanning --------------------------------------------






# from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, DateTime, text
# from sqlalchemy.orm import relationship
# from app.db.base import Base


# class ExportSlotFileRecord(Base):
#     """Truck-level tracking"""
#     __tablename__ = "export_slot_file"

#     id = Column(Integer, primary_key=True, index=True)
#     company_name = Column(String, nullable=False)
#     warehouse = Column(String, nullable=False)
#     zone = Column(String, nullable=False)
#     token_no = Column(String, nullable=True)
#     truck_number = Column(String, nullable=False)
#     status = Column(String, nullable=True)
#     remarks = Column(String, nullable=True)
#     cargo_type = Column(String, nullable=True)
#     rescheduled = Column(String, nullable=True)
#     rescheduled_by = Column(String, nullable=True)
#     truck_slot_from = Column(DateTime(timezone=True), nullable=False)
    
#     # Truck-level: Gate operations
#     truck_in_date_time = Column(DateTime(timezone=True), nullable=True)
#     truck_out_date_time = Column(DateTime(timezone=True), nullable=True)
#     is_truck_in = Column(Boolean, default=False, nullable=False)
#     is_truck_out = Column(Boolean, default=False, nullable=False)
#     truck_in_by = Column(String, nullable=True)
#     truck_out_by = Column(String, nullable=True)
    
#     # Truck-level: Current dock status (for availability module)
#     current_dock_number = Column(String, nullable=True)
#     current_dock_in_date_time = Column(DateTime(timezone=True), nullable=True)
#     current_dock_out_date_time = Column(DateTime(timezone=True), nullable=True)
#     current_is_dock_in = Column(Boolean, default=False, nullable=False)
#     current_is_dock_out = Column(Boolean, default=False, nullable=False)
#     current_dock_in_by = Column(String, nullable=True)
#     current_dock_out_by = Column(String, nullable=True)
    
#     created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
#     updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))
    
#     awbs = relationship("ExportSlotAWB", back_populates="export_slot", cascade="all, delete-orphan")
    
#     __table_args__ = (
#         Index('idx_token_truckslot_trucknumber', 'token_no', 'truck_slot_from', 'truck_number'),
#         Index('idx_dock_availability', 'current_dock_number', 'current_is_dock_in'),
#     )


# class ExportSlotAWB(Base):
#     """AWB-level tracking - Summary level"""
#     __tablename__ = "export_slot_awb"

#     id = Column(Integer, primary_key=True, index=True)
#     export_slot_id = Column(Integer, ForeignKey("export_slot_file.id", ondelete="CASCADE"))
#     awb_id = Column(String, nullable=False)
#     pcs = Column(Integer, nullable=False)  # Total pieces for this AWB
#     is_additional = Column(Boolean, nullable=False, default=False)
    
#     created_at = Column(DateTime(timezone=True), nullable=False)
#     updated_at = Column(DateTime(timezone=True), nullable=False)
    
#     export_slot = relationship("ExportSlotFileRecord", back_populates="awbs")
#     sequences = relationship("AWBSequence", back_populates="awb", cascade="all, delete-orphan")
#     dock_operations = relationship("AWBDockOperation", back_populates="awb", cascade="all, delete-orphan")
    
#     __table_args__ = (
#         Index('idx_export_slot_awb', 'export_slot_id', 'awb_id'),
#     )


# class AWBDockOperation(Base):
#     """Tracks each dock operation for an AWB (supports split unloading)"""
#     __tablename__ = "awb_dock_operation"

#     id = Column(Integer, primary_key=True, index=True)
#     awb_record_id = Column(Integer, ForeignKey("export_slot_awb.id", ondelete="CASCADE"), nullable=False)
    
#     # Dock operation details
#     dock_number = Column(String, nullable=False)
    
#     dock_in_date_time = Column(DateTime(timezone=True), nullable=False)
#     dock_out_date_time = Column(DateTime(timezone=True), nullable=True)
#     is_dock_in = Column(Boolean, default=True, nullable=False)
#     is_dock_out = Column(Boolean, default=False, nullable=False)
    
#     dock_in_by = Column(String, nullable=True)
#     dock_out_by = Column(String, nullable=True)
    
#     created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
#     updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))
    
#     # Relationships
#     awb = relationship("ExportSlotAWB", back_populates="dock_operations")
#     sequences = relationship("AWBSequence", back_populates="dock_operation")  # ✅ NEW: Link sequences to dock
    
#     __table_args__ = (
#         Index('idx_awb_dock_operation', 'awb_record_id', 'dock_number'),
#         Index('idx_dock_date', 'dock_number', 'dock_in_date_time'),
#     )


# class AWBSequence(Base):
#     """✅ UPDATED: Track sequences with dock operation link"""
#     __tablename__ = "awb_sequence"

#     id = Column(Integer, primary_key=True, index=True)
#     awb_record_id = Column(Integer, ForeignKey("export_slot_awb.id", ondelete="CASCADE"), nullable=False)
#     dock_operation_id = Column(Integer, ForeignKey("awb_dock_operation.id", ondelete="SET NULL"), nullable=True)  # ✅ NEW
    
#     seq_number = Column(String, nullable=False)
#     seq_time = Column(DateTime(timezone=True), nullable=False)
    
#     created_at = Column(DateTime(timezone=True), nullable=False)
#     updated_at = Column(DateTime(timezone=True), nullable=False)
    
#     # Relationships
#     awb = relationship("ExportSlotAWB", back_populates="sequences")
#     dock_operation = relationship("AWBDockOperation", back_populates="sequences")  # ✅ NEW
    
#     __table_args__ = (
#         Index('idx_awb_record_id_seq_number', 'awb_record_id', 'seq_number'),
#         Index('idx_dock_operation_seq', 'dock_operation_id', 'seq_number'),  # ✅ NEW
#     )




# ===================================================== 😎This is third approach with l;ink table multi awb ==== ==============


from sqlalchemy import Boolean, Column, ForeignKey, Index, Integer, String, DateTime, text
from sqlalchemy.orm import relationship
from app.db.base import Base


# ----------------------------------------------------
# 1) TRUCK-LEVEL: Slot File Parent (Current Live State)
# ----------------------------------------------------
class ExportSlotFileRecord(Base):
    __tablename__ = "export_slot_file"

    id = Column(Integer, primary_key=True, index=True)
    company_name = Column(String, nullable=False)
    warehouse = Column(String, nullable=False)
    zone = Column(String, nullable=False)
    token_no = Column(String, nullable=True)
    truck_number = Column(String, nullable=False)
    status = Column(String, nullable=True)
    remarks = Column(String, nullable=True)
    cargo_type = Column(String, nullable=True)
    rescheduled = Column(String, nullable=True)
    rescheduled_by = Column(String, nullable=True)
    truck_slot_from = Column(DateTime(timezone=True), nullable=False)

    # Gate status
    truck_in_date_time = Column(DateTime(timezone=True))
    truck_out_date_time = Column(DateTime(timezone=True))
    is_truck_in = Column(Boolean, default=False)
    is_truck_out = Column(Boolean, default=False)
    truck_in_by = Column(String)
    truck_out_by = Column(String)

    truck_in_device = Column(String,nullable=True,default=None) #❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌
    truck_out_device = Column(String,nullable=True,default=None) #❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌

    # Last dock info (when any user add dock no. not scan any thing and revert then I know what last fully completed dock happen ::::: postpond for now)

    # 📌 Current Dock Live Status (NOT history)
    current_dock_number = Column(String)
    current_dock_in_date_time = Column(DateTime(timezone=True))
    current_dock_out_date_time = Column(DateTime(timezone=True))
    current_is_dock_in = Column(Boolean, default=False)
    current_is_dock_out = Column(Boolean, default=False)
    current_dock_in_by = Column(String)
    current_dock_out_by = Column(String)
    current_dock_in_by_device = Column(String,nullable=True, default=None)

    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))

    # One truck has multiple AWBs
    awbs = relationship("ExportSlotAWB", back_populates="export_slot", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_token_truckslot_trucknumber', 'token_no', 'truck_slot_from', 'truck_number'),
        Index('idx_dock_availability', 'current_dock_number', 'current_is_dock_in'),
    )


# ----------------------------------------------------
# 2) AWB Summary Table (AWB inside Truck)
# ----------------------------------------------------
class ExportSlotAWB(Base):
    __tablename__ = "export_slot_awb"

    id = Column(Integer, primary_key=True, index=True)
    export_slot_id = Column(Integer, ForeignKey("export_slot_file.id", ondelete="CASCADE"))
    awb_id = Column(String, nullable=False)
    pcs = Column(Integer, nullable=False)
    is_additional = Column(Boolean, default=False)

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    export_slot = relationship("ExportSlotFileRecord", back_populates="awbs")

    # 🔥 MANY-TO-MANY with dock session
    dock_operations = relationship(
        "AWBDockOperation",
        secondary="export_dock_operation_awb_link",
        back_populates="awbs"
    )

    # Scan sequences
    sequences = relationship("AWBSequence", back_populates="awb", cascade="all, delete-orphan")

    __table_args__ = (
        Index('idx_export_slot_awb', 'export_slot_id', 'awb_id'),
    )


# ----------------------------------------------------
# 3) Dock Operation Session (Can have multiple AWBs)
# ----------------------------------------------------
class AWBDockOperation(Base):
    __tablename__ = "export_awb_dock_operation"

    id = Column(Integer, primary_key=True, index=True)
    dock_number = Column(String, nullable=False)
    dock_in_date_time = Column(DateTime(timezone=True), nullable=False)
    dock_out_date_time = Column(DateTime(timezone=True))
    is_dock_in = Column(Boolean, default=True)
    is_dock_out = Column(Boolean, default=False)
    dock_in_by = Column(String)
    dock_out_by = Column(String)
    export_slot_id = Column(Integer, ForeignKey("export_slot_file.id", ondelete="CASCADE"), nullable=False)  # 🔥 ADD THIS

    dock_in_by_device = Column(String,nullable=True,default=None) #❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌
    dock_out_by_device = Column(String,nullable=True,default=None) #❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌❌

    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))

    # 🔥 Multiple AWBs inside same dock session
    awbs = relationship(
        "ExportSlotAWB",
        secondary="export_dock_operation_awb_link",
        back_populates="dock_operations"
    )

    # All scanned pieces for session
   # In AWBDockOperation
    sequences = relationship(
        "AWBSequence",
        back_populates="dock_operation",
        cascade="all, delete-orphan"
    )


    __table_args__ = (
        Index('idx_export_dock_date', 'dock_number', 'dock_in_date_time'),
    )


# ----------------------------------------------------
# 4) Link Table → Dock Session <-> AWB Mapping
# ----------------------------------------------------
class DockOperationAWBLink(Base):
    __tablename__ = "export_dock_operation_awb_link"

    id = Column(Integer, primary_key=True, index=True)
    dock_operation_id = Column(Integer, ForeignKey("export_awb_dock_operation.id", ondelete="CASCADE"))
    awb_record_id = Column(Integer, ForeignKey("export_slot_awb.id", ondelete="CASCADE"))


# ----------------------------------------------------
# 5) Sequence / Scan Table (Every single scan event)
# ----------------------------------------------------
class AWBSequence(Base):
    __tablename__ = "export_awb_sequence"

    id = Column(Integer, primary_key=True, index=True)
    awb_record_id = Column(Integer, ForeignKey("export_slot_awb.id", ondelete="CASCADE"))
    dock_operation_id = Column(Integer, ForeignKey("export_awb_dock_operation.id", ondelete="SET NULL"))

    seq_number = Column(String, nullable=False)
    seq_time = Column(DateTime(timezone=True), nullable=False)

    # 🧍 Who scanned + 📱 Device used
    scanned_by_user = Column(String, nullable=True)
    scanned_by_device = Column(String, nullable=True)

    created_at = Column(DateTime(timezone=True), nullable=False)
    updated_at = Column(DateTime(timezone=True), nullable=False)

    awb = relationship("ExportSlotAWB", back_populates="sequences")
    dock_operation = relationship("AWBDockOperation", back_populates="sequences")

    __table_args__ = (
        Index('idx_export_awb_record_id_seq_number', 'awb_record_id', 'seq_number'),
        Index('idx_export_dock_operation_seq', 'dock_operation_id', 'seq_number'),
    )