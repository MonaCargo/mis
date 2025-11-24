from sqlalchemy import Boolean, Column, Integer, String, DateTime, text
from app.db.base import Base
from sqlalchemy.sql import func


class ExportManualSlotFileRecord(Base):
    __tablename__ = "export_manual_slot_file"

    id = Column(Integer, primary_key=True, index=True)

    # Shipment metadata
    date = Column(String, nullable=False)          # raw string date
    time = Column(String, nullable=False)          # raw string time
    merge_datetime = Column(DateTime(timezone=True), nullable=False)      # combined string datetime

    tc_no = Column(String, nullable=False)
    awb = Column(String, nullable=False)
    pcs = Column(Integer, nullable=False)
    agent_name = Column(String, nullable=False)
    user = Column(String, nullable=False)

    # Truck/Dock timestamps (always UTC)
    truck_in_date_time = Column(DateTime(timezone=True), nullable=True)
    truck_out_date_time = Column(DateTime(timezone=True), nullable=True)
    dock_in_date_time = Column(DateTime(timezone=True), nullable=True)
    dock_out_date_time = Column(DateTime(timezone=True), nullable=True)

    # Status flags
    is_truck_in = Column(Boolean, default=False, nullable=False)
    is_truck_out = Column(Boolean, default=False, nullable=False)
    is_dock_in = Column(Boolean, default=False, nullable=False)
    is_dock_out = Column(Boolean, default=False, nullable=False)

    # Dock/Truck info
    dock_number = Column(String, nullable=True)
    truck_in_by = Column(String, nullable=True)
    truck_out_by = Column(String, nullable=True)
    dock_in_by = Column(String, nullable=True)
    dock_out_by = Column(String, nullable=True)

    token_number = Column(String, nullable=False)
    truck_number = Column(String, nullable=True,default= None)

    # Audit fields (explicit UTC default)
    created_at = Column(
        DateTime(timezone=True),
        # server_default=text("TIMEZONE('UTC', NOW())")
    )
    updated_at = Column(
        DateTime(timezone=True),
        # server_default=text("TIMEZONE('UTC', NOW())"),
        # onupdate=func.timezone('utc', func.now())  # Changed this line
    )