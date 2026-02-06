# app/models/damage_report.py
from sqlalchemy import (
    Column, Integer, String, DateTime, Text, ForeignKey, Index, Boolean
)
from sqlalchemy.orm import relationship
from sqlalchemy.sql import func
from app.db.base import Base


class DamageReason(Base):
    """
    Master table for damage reasons.
    Defines all possible damage types that can be reported.
    """
    __tablename__ = "damage_reasons"

    # 🔑 Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 📋 Reason Details
    reason_code = Column(String(50), unique=True, nullable=False, index=True)
    reason_name = Column(String(100), nullable=False)
    description = Column(Text, nullable=True)
    is_active = Column(Boolean, default=True, nullable=False)

    # ⏱️ Timestamps
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=True)

    # 🔗 Relationship to report reasons
    report_reasons = relationship(
        "DamageReportReason",
        back_populates="reason",
        cascade="all, delete-orphan"
    )

    def __repr__(self):
        return f"<DamageReason(id={self.id}, code={self.reason_code}, name={self.reason_name})>"


class DamageReport(Base):
    """
    Main damage report table storing package damage incidents.
    Tracks damage reports submitted by workers at specific locations.
    """
    __tablename__ = "damage_reports"

    # 🔑 Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)



    # 🔗 Relations & Identifiers
    # worker_assignment_id = Column(Integer, nullable=False,index=True)
    # ===============================
    # 🔗 2-Level Worker Assignment
    # ===============================

    assignment_header_id = Column(
        Integer,
        ForeignKey("import_worker_assignment_header.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    assignment_shipment_id = Column(
        Integer,
        ForeignKey("import_worker_assignment_shipment.id", ondelete="RESTRICT"),
        nullable=False,
        index=True
    )

    # status and resolved at represent the this repoert stage only. this info also saved in worker assignment table also
    status = Column(
    String(30),
    default="open",
    index=True
    )

    resolved_date_time = Column(DateTime(timezone=True), nullable=True)

    oc_no = Column(String(50), nullable=False, index=True)
    awb_no = Column(String(50), nullable=False, index=True)
    hawb = Column(String(50), nullable=True, index=True)
    location = Column(String(50), nullable=False, index=True)
   

    # 📋 Damage Details
    remarks = Column(Text, nullable=True)

    # ⏱️ Timestamps
    reported_at = Column(DateTime(timezone=True), nullable=False)   # save time
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)
    updated_at = Column(DateTime(timezone=True), onupdate=func.now(), nullable=True)

    # 🔗 Relationships
    reasons = relationship(
        "DamageReportReason",
        back_populates="report",
        cascade="all, delete-orphan",
        lazy="selectin"
    )
    
    images = relationship(
        "DamageReportImage",
        back_populates="report",
        cascade="all, delete-orphan",
        lazy="selectin"
    )

    assignment_header = relationship("WorkerAssignmentHeader")

    assignment_shipment = relationship("WorkerAssignmentShipment")


    # 📊 Composite indexes for common queries
    __table_args__ = (
        Index("idx_damage_reports_oc_location", "oc_no", "location"),
        Index("idx_damage_reports_created", "created_at"),


         Index(
        "idx_damage_reports_assignment_chain",
        "assignment_header_id",
        "assignment_shipment_id"
    ),
    )

    def __repr__(self):
        return f"<DamageReport(id={self.id}, oc_no={self.oc_no}, location={self.location})>"


class DamageReportReason(Base):
    """
    Junction table linking damage reports to their reasons.
    Allows many-to-many relationship between reports and reasons.
    """
    __tablename__ = "damage_report_reasons"

    # 🔑 Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 🔗 Foreign Keys
    report_id = Column(
        Integer,
        ForeignKey("damage_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    reason_id = Column(
        Integer,
        ForeignKey("damage_reasons.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )

    emp_id = Column(String(10), nullable=False, index=True)
    device_id = Column(String(50), nullable=True, index=True)


    # ⏱️ Timestamp
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 🔗 Relationships
    report = relationship("DamageReport", back_populates="reasons")
    reason = relationship("DamageReason", back_populates="report_reasons")

    # 📊 Unique constraint and indexes
    __table_args__ = (
        Index("idx_damage_report_reasons_report", "report_id"),
        Index("idx_damage_report_reasons_reason", "reason_id"),
        Index("idx_damage_report_reasons_unique", "report_id", "reason_id", unique=True),
    )

    def __repr__(self):
        return f"<DamageReportReason(report_id={self.report_id}, reason_id={self.reason_id})>"


class DamageReportImage(Base):
    """
    Storage table for damage report images.
    Each report can have multiple images (up to 5).
    """
    __tablename__ = "damage_report_images"

    # 🔑 Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 🔗 Foreign Key to damage report
    report_id = Column(
        Integer,
        ForeignKey("damage_reports.id", ondelete="CASCADE"),
        nullable=False,
        index=True
    )
    
    emp_id = Column(String(10), nullable=False, index=True)
    device_id = Column(String(50), nullable=True, index=True)
    # 🖼️ Image Details
    image_url = Column(Text, nullable=False)
    image_name = Column(String(255), nullable=False)
    file_size = Column(Integer, nullable=True)
    mime_type = Column(String(50), nullable=True)

    # ⏱️ Timestamp
    uploaded_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 🔗 Relationship back to report
    report = relationship("DamageReport", back_populates="images")

    __table_args__ = (
        Index("idx_damage_images_report_id", "report_id"),
    )

    def __repr__(self):
        return f"<DamageReportImage(id={self.id}, report_id={self.report_id}, name={self.image_name})>"


class DamageReportAuditLog(Base):
    """
    Audit trail for damage reports.
    Tracks all changes and access to damage reports for compliance.
    """
    __tablename__ = "audit_log_damage_reports"

    # 🔑 Primary Key
    id = Column(Integer, primary_key=True, autoincrement=True)

    # 🔗 Relation to damage report
    damage_report_id = Column(Integer, index=True, nullable=False)

    # ✅ NEW
    assignment_header_id = Column(Integer, index=True, nullable=False)
    assignment_shipment_id = Column(Integer, index=True, nullable=False)

    # 🔍 Searchable identifiers
    oc_no = Column(String(50), index=True, nullable=False)
    location = Column(String(1000), index=True, nullable=False)

    # 🧾 What changed
    field_name = Column(String(100), nullable=True)
    old_value = Column(Text, nullable=True)
    new_value = Column(Text, nullable=True)

    # 🧠 Action metadata
    db_action = Column(String(20), nullable=False)
    # CREATE | UPDATE | DELETE | VIEW

    source_action = Column(String(50), nullable=False)
    # report_created | report_updated | report_deleted | reason_added | reason_removed | image_added | image_deleted

    # 👤 Actor info
    changed_by = Column(String(100), nullable=False)
    changed_by_role = Column(String(50), nullable=False)
    ip_address = Column(String(45), nullable=True)
    device_id = Column(String(100), nullable=True)
    user_agent = Column(String(1024), nullable=True)

    # 📝 Additional context
    description = Column(Text, nullable=True)

    # ⏱️ Timestamps
    changed_at = Column(DateTime(timezone=True), nullable=False)
    created_at = Column(DateTime(timezone=True), server_default=func.now(), nullable=False)

    # 📊 Composite indexes
    __table_args__ = (
        Index("idx_audit_damage_reports_search", "oc_no", "location", "changed_at"),
        Index("idx_audit_damage_reports_actor", "changed_by", "changed_at"),
        Index("idx_audit_damage_reports_action", "db_action", "source_action"),
    )

    def __repr__(self):
        return f"<DamageReportAuditLog(id={self.id}, report_id={self.damage_report_id}, action={self.db_action})>"