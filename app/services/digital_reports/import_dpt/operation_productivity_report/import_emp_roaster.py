"""
Persistence for the shift-worker Roster.

save_roster_report(session, rows, allow_multiple_shifts_per_day=True,
                   uploaded_by=None) -> dict

Two-step idempotent upload:

  1. Upsert EMPLOYEES (dr_imp_roster_employee) on emp_code.
     New emp_code -> inserted. Existing -> kept (emp_code is the source of
     truth; we refresh name/desg to the latest seen, which is harmless).

  2. Upsert ATTENDANCE (dr_imp_roster_attendance) on (emp_code, date, shift).
     New (emp_code,date,shift) -> inserted (a new shift is appended).
     Existing -> department / desg / present_status updated.
     This makes re-uploading the SAME file idempotent — running it twice gives
     the same result, so accidental repeat uploads are harmless.

Transaction: we do NOT open our own (the request-scoped DB dependency owns the
transaction). We execute + flush; the dependency commits.

allow_multiple_shifts_per_day:
    True  (default) -> a person may have several shifts on one day; each
                       (emp_code,date,shift) is its own row.
    False           -> enforce one shift per person per day: before upserting,
                       existing rows for (emp_code, date) with a DIFFERENT shift
                       are deleted, so the latest upload's shift wins.
"""

from __future__ import annotations

from typing import Optional

from sqlalchemy import delete, tuple_, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.digital_reports.import_dept.import_emp_roaster import (
    DigitalReportRosterEmployee as Employee,
    DigitalReportRosterAttendance as Attendance,
)


async def save_import_roster_report(
    session: AsyncSession,
    rows: list[dict],
    allow_multiple_shifts_per_day: bool = True,
    uploaded_by: Optional[str] = None,
) -> dict:
    if not rows:
        return {"employees_upserted": 0, "attendance_upserted": 0, "shifts_replaced": 0}

    # ── Step 1: upsert employees (unique on emp_code) ──────────────────────
    # De-dupe employees within this file so the insert has one row per emp_code.
    emp_by_code: dict[str, dict] = {}
    for r in rows:
        emp_by_code[r["emp_code"]] = {
            "emp_code": r["emp_code"],
            "emp_name": r.get("emp_name"),
            "desg": r.get("desg"),
        }
    emp_values = list(emp_by_code.values())

    emp_stmt = pg_insert(Employee).values(emp_values)
    emp_stmt = emp_stmt.on_conflict_do_update(
        index_elements=["emp_code"],
        set_={
            "emp_name": emp_stmt.excluded.emp_name,
            "desg": emp_stmt.excluded.desg,
        },
    )
    await session.execute(emp_stmt)

    # ── Optional: enforce one shift per person per day ─────────────────────
    shifts_replaced = 0
    if not allow_multiple_shifts_per_day:
        # For each (emp_code, date) in this upload, remove any existing rows
        # whose shift differs from the one we're about to write, so the new
        # shift replaces the old. (emp_code, date, shift) upsert then handles
        # the matching-shift rows.
        pairs = {(r["emp_code"], r["date"]) for r in rows}
        keep_keys = {(r["emp_code"], r["date"], r["shift"]) for r in rows}
        if pairs:
            existing = (await session.execute(
                select(Attendance.emp_code, Attendance.date, Attendance.shift)
                .where(tuple_(Attendance.emp_code, Attendance.date).in_(list(pairs)))
            )).all()
            to_delete = [
                (e.emp_code, e.date, e.shift)
                for e in existing
                if (e.emp_code, e.date, e.shift) not in keep_keys
            ]
            if to_delete:
                await session.execute(
                    delete(Attendance).where(
                        tuple_(Attendance.emp_code, Attendance.date, Attendance.shift)
                        .in_(to_delete)
                    )
                )
                shifts_replaced = len(to_delete)

    # ── Step 2: upsert attendance on (emp_code, date, shift) ───────────────
    att_values = [
        {
            "emp_code": r["emp_code"],
            "date": r["date"],
            "shift": r["shift"],
            "department": r.get("department"),
            "desg": r.get("desg"),
            "present_status": r.get("present_status"),
        }
        for r in rows
    ]

    # De-dupe within the file on the conflict key (last occurrence wins), so a
    # single INSERT doesn't hit "cannot affect row a second time".
    dedup: dict[tuple, dict] = {}
    for v in att_values:
        dedup[(v["emp_code"], v["date"], v["shift"])] = v
    att_values = list(dedup.values())

    att_stmt = pg_insert(Attendance).values(att_values)
    att_stmt = att_stmt.on_conflict_do_update(
        constraint="uq_roster_att_emp_date_shift",
        set_={
            "department": att_stmt.excluded.department,
            "desg": att_stmt.excluded.desg,
            "present_status": att_stmt.excluded.present_status,
        },
    )
    await session.execute(att_stmt)
    await session.commit()   # <-- add this (replaces the flush)

    # await session.flush()

    return {
        "employees_upserted": len(emp_values),
        "attendance_upserted": len(att_values),
        "shifts_replaced": shifts_replaced,
    }