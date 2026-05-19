from sqlalchemy import Column, Integer, ForeignKey, DateTime, String, UniqueConstraint, Index
from sqlalchemy.dialects.postgresql import JSONB
from sqlalchemy.sql import func
from app.db.base import Base


class ExportLoadingSheetForm(Base):
    """
    Current state of the loading sheet form for a Flight + ULD combo.
    Stores a COMPLETE snapshot of the form at last save — operational
    data + user-input fields together.
    """
    __tablename__ = "export_loading_sheet_form"

    __table_args__ = (
        UniqueConstraint(
            "flight_header_id",
            "uld_assignment_detail_id",
            name="uq_loading_sheet_per_flight_uld"
        ),
        Index(
            "idx_loading_sheet_flight_uld",
            "flight_header_id",
            "uld_assignment_detail_id"
        ),
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

    # FULL snapshot of form at save time (operational + user input)
    form_data = Column(JSONB, nullable=False, default=dict)

    # Audit columns
    created_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    updated_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now(), onupdate=func.now())

    created_by = Column(String(20), nullable=False)
    updated_by = Column(String(20), nullable=False)





# ========================== 🫥Log of export uld loading sheet form changes ==================

class ExportLoadingSheetFormHistoryLog(Base):
    """
    Append-only audit log of every save to the loading sheet form.
    Each save creates a new row. Nothing is ever overwritten or deleted.

    Used for:
    - Tracing 'what did the form look like at 14:32 yesterday?'
    - Identifying who changed what and when
    - Forensic analysis if data discrepancies arise
    """
    __tablename__ = "export_loading_sheet_form_history_log"

    __table_args__ = (
        Index(
            "idx_loading_sheet_hist_flight_uld",
            "flight_header_id",
            "uld_assignment_detail_id",
        ),
        Index(
            "idx_loading_sheet_hist_saved_at",
            "saved_at",
        ),
        Index(
            "idx_loading_sheet_hist_form_id",
            "loading_sheet_form_id",
        ),
    )

    id = Column(Integer, primary_key=True)

    # Link back to the live form row (so you can find all history for a form)
    loading_sheet_form_id = Column(
        Integer,
        ForeignKey("export_loading_sheet_form.id"),
        nullable=False,
    )

    # Denormalized for fast filtering without joins
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

    # FULL snapshot at this exact save moment
    form_data = Column(JSONB, nullable=False)

    # API snapshot — what the GET API returned RIGHT BEFORE this save
    # (useful to see exactly what was loaded and what the user changed)
    api_snapshot = Column(JSONB, nullable=True)

    # Save metadata
    saved_at = Column(DateTime(timezone=True), nullable=False, server_default=func.now())
    saved_by = Column(String(20), nullable=False)

    # Save type — distinguish first save, subsequent saves, auto-saves, etc.
    save_type = Column(String(20), nullable=False, default="manual")
    # values: "manual" (user clicked Save), "auto" (auto-save), "first" (initial save), etc.