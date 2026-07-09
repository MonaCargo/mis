"""
ORM models for the shift-worker Roster.

TWO tables, separating stable identity from per-shift attendance:

  roster_employee    — persistent master, one row per person ever seen.
                       Source of truth is emp_code (unique). Never deleted;
                       every new emp_code in an upload is added here.

  roster_attendance  — one row per (emp_code, date, shift) attendance event.
                       Unique on (emp_code, date, shift) so uploads UPSERT:
                       new rows are appended, existing ones update their
                       changeable fields (department, present_status). This
                       makes re-uploading the same file idempotent (safe against
                       accidental repeat uploads).

Present/Absent is stored three-way as present_status:
    "P"  -> file said Present (case-insensitive)
    "A"  -> file said Absent
    NULL -> anything else / blank (e.g. ex-employee still listed, unmarked)
This preserves the "unknown" state instead of forcing every blank to Absent.

date is a plain DATE (no time); the shift name carries the time-of-day meaning.
"""

from datetime import date, datetime
from typing import Optional

from sqlalchemy import (
    Integer, String, Date, DateTime, ForeignKey, UniqueConstraint, Index, func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.db.base import Base


class DigitalReportRosterEmployee(Base):
    """Persistent employee master. Source of truth = emp_code."""

    __tablename__ = "dr_imp_roster_employee"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    emp_code: Mapped[str] = mapped_column(
        String(20), nullable=False, unique=True, index=True,
        comment="Employee code — unique natural key / source of truth.",
    )
    emp_name: Mapped[Optional[str]] = mapped_column(String(150), nullable=True)
    desg: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="Designation (CA / CO / WHA ...).",
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    attendance: Mapped[list["DigitalReportRosterAttendance"]] = relationship(
        back_populates="employee", cascade="all, delete-orphan",
    )

    def __repr__(self) -> str:
        return f"<DigitalReportRosterEmployee {self.emp_code} {self.emp_name!r}>"


class DigitalReportRosterAttendance(Base):
    """One attendance record per employee, per date, per shift."""

    __tablename__ = "dr_imp_roster_attendance"

    id: Mapped[int] = mapped_column(Integer, primary_key=True, autoincrement=True)

    # Link to the master. We also keep emp_code denormalized for easy upsert /
    # querying without a join.
    emp_code: Mapped[str] = mapped_column(
        String(20), ForeignKey("dr_imp_roster_employee.emp_code", ondelete="CASCADE"),
        nullable=False, index=True,
    )

    # date is a plain DATE — attendance is day+shift, not time-of-day based.
    date: Mapped[date] = mapped_column(Date, nullable=False)
    shift: Mapped[str] = mapped_column(
        String(20), nullable=False, comment="Morning / Afternoon / Evening.",
    )

    # Changeable per upload:
    department: Mapped[Optional[str]] = mapped_column(String(50), nullable=True)
    desg: Mapped[Optional[str]] = mapped_column(
        String(20), nullable=True, comment="Designation snapshot on this shift.",
    )
    present_status: Mapped[Optional[str]] = mapped_column(
        String(1), nullable=True,
        comment='"P"=Present, "A"=Absent, NULL=unknown/blank.',
    )

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(), nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), server_default=func.now(),
        onupdate=func.now(), nullable=False,
    )

    employee: Mapped["DigitalReportRosterEmployee"] = relationship(back_populates="attendance")

    __table_args__ = (
        # The upsert key: one attendance record per person per date per shift.
        # This is what makes re-uploads idempotent and lets the same person
        # appear in multiple shifts on one day (different shift => different row).
        UniqueConstraint("emp_code", "date", "shift", name="uq_roster_att_emp_date_shift"),
        # Fast dashboard queries: "who was present in <dept> on <date>/<shift>".
        Index("ix_roster_att_date_shift_dept", "date", "shift", "department"),
    )

    def __repr__(self) -> str:
        return (
            f"<DigitalReportRosterAttendance {self.emp_code} {self.date} {self.shift} "
            f"{self.department} {self.present_status}>"
        )