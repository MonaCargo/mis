# from sqlalchemy import Column, Integer, String, DateTime,Float, func, text
# from app.db.base import Base


# class ExportSlotFileRecord(Base):
#     __tablename__ = "export_slot_file"

#     id = Column(Integer, primary_key=True, index=True)
#     company_name = Column(String, nullable=False)
#     warehouse = Column(String, nullable=False)
#     zone = Column(String, nullable=False)
#     token_no = Column(String)
#     awb_no = Column(Float)
#     truck_number = Column(String)
#     pcs = Column(Integer)
#     status = Column(String)
#     remarks = Column(String)
#     cargo_type = Column(String)
#     rescheduled = Column(String)
#     rescheduled_by = Column(String)
#     truck_slot_from = Column(DateTime)          # ✅ Use DateTime
#     truck_in_date_time = Column(DateTime)       # ✅ Use DateTime

      
#     # ✅ NEW: Timestamp columns
#   # Automatically set timestamp on insert and update without timezone SQL (⚠️confirm timezone handling with your DB)
#     created_at = Column(DateTime(timezone=True), server_default=func.now())
#     updated_at = Column(DateTime(timezone=True), server_default=func.now(), onupdate=func.now())



# =================== NEW STRUCTURE ======================================================


from sqlalchemy import Boolean, Column, Float, ForeignKey, Index, Integer, String, DateTime, text
from sqlalchemy.orm import relationship
from app.db.base import Base


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
    truck_in_date_time = Column(DateTime(timezone=True), nullable=True)  # it is automatically created or come from frontend (⚠️see time zone handling carefully)
    # ✅ Store in UTC
    created_at = Column(DateTime(timezone=True), server_default=text("NOW()"))
    updated_at = Column(DateTime(timezone=True), server_default=text("NOW()"), onupdate=text("NOW()"))


   # ✅ Corrected new fields (camelCase in Python → snake_case in DB)
    truck_out_date_time = Column(DateTime(timezone=True), nullable=True)
    dock_in_date_time = Column(DateTime(timezone=True), nullable=True)
    dock_out_date_time = Column(DateTime(timezone=True), nullable=True)
    is_truck_in = Column(Boolean,default=False,nullable=False)      
    is_truck_out = Column(Boolean, default=False,nullable=False) 
    is_dock_in = Column(Boolean, default=False,nullable=False)       
    is_dock_out = Column(Boolean, default=False,nullable=False)      
    dock_number = Column(String, nullable=True)
   #agin new fields
    truck_in_by = Column(String, nullable=True)      
    truck_out_by  = Column(String, nullable=True)     
    dock_in_by = Column(String, nullable=True)       
    dock_out_by = Column(String, nullable=True)  

   

        

    # One-to-many relationship
    awbs = relationship("ExportSlotAWB", back_populates="export_slot", cascade="all, delete-orphan")


    # create index on token_no, truck_slotFrom and truck_number (combined index )
    __table_args__ = (
        Index('idx_token_truckslot_trucknumber', 'token_no', 'truck_slot_from', 'truck_number'),
    )
    



class ExportSlotAWB(Base):
    __tablename__ = "export_slot_awb"

    id = Column(Integer, primary_key=True, index=True)
    export_slot_id = Column(Integer, ForeignKey("export_slot_file.id", ondelete="CASCADE"))
    awb_id = Column(String, nullable=False)  # ✅ CHANGED: awbid → awb_id
    pcs = Column(Integer, nullable=False)
    is_additional=Column(Boolean,nullable=False,default=False)

    export_slot = relationship("ExportSlotFileRecord", back_populates="awbs")
    sequences = relationship("AWBSequence", back_populates="awb", cascade="all, delete-orphan")
    created_at = Column(
        DateTime(timezone=True),
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True),
        nullable=False
    )




class AWBSequence(Base):
    """Child table of ExportSlotAWB to track sequences"""
    __tablename__ = "awb_sequence"

    id = Column(Integer, primary_key=True, index=True)
    awb_record_id = Column(Integer, ForeignKey("export_slot_awb.id", ondelete="CASCADE"), nullable=False)
    seq_number = Column(String, nullable=False)
    seq_time = Column(DateTime(timezone=True), nullable=False)
    
    # Timestamps
    created_at = Column(
        DateTime(timezone=True), 
        nullable=False
    )
    updated_at = Column(
        DateTime(timezone=True), 
        nullable=False
    )

    # Relationship back to parent AWB
    awb = relationship("ExportSlotAWB", back_populates="sequences")

     # ✅ CHANGED: Index also uses awb_record_id
    __table_args__ = (
        Index('idx_awb_record_id_seq_number', 'awb_record_id', 'seq_number'), 
    )





#    ============================
# This is the structure if we send gull response with all availble nested data (relationship)
#   ExportSlotFullResponse
#   └─ awbList: List[AWBEntryResponse]
#        └─ sequences: List[AWBSequenceResponse] 