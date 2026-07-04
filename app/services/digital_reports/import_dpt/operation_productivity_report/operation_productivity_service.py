

"""
Segregation metric computation — SHIFT-BASED.

Input: a single IST date (report_date).
Output: each segregation metric split across three shifts + a day total.

Shift windows (IST):
    Morning    [date 06:00, date 14:00)
    Afternoon  [date 14:00, date 22:00)
    Evening    [date 22:00, date+1 06:00)

A shipment is assigned to a shift by flt_com_dat_tim (FCC) converted to IST.
The union of the three shifts is exactly [date 06:00 IST, date+1 06:00 IST) —
i.e. a cargo "operating day" starts at 06:00, not midnight. Cargo whose
completion falls between 00:00 and 06:00 belongs to the PREVIOUS day's Evening
shift, which is the correct operational behaviour.

Column mapping (Segregation Report -> ORM):
    E Flight No.  -> flight.flight_no
    G AWB No      -> awb.awb_no
    N DEST        -> awb.dest
    S PCS         -> awb.pcs
    T Gross Wgt   -> awb.gross_wgt
    U CHG WGT     -> awb.chg_wgt
    K/L ULD arr.  -> flight.last_uld_arrival / flight.bulk_uld_arrival (ATW=max)
    AI FLT_COM    -> flight.flt_com_dat_tim (FCC)
"""

from datetime import date, datetime, timedelta, timezone
from decimal import Decimal
from typing import Optional

from sqlalchemy import func, select, case, distinct, literal
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.digital_reports.segrigation_report import (
    DigitalReportImportSegFlight as Flight,
    DigitalReportImportSegAwb as Awb,
)
from app.schemas.digital_reports.import_dept.operation_productivity_schema import (
    ImportProductivityDashboardResponse, ImportProductivityDashboardMeta,
    MetricSection, MetricRow, ShiftValues, ShiftWindow,
    MetricUnit, MetricSource,
)

IST = timezone(timedelta(hours=5, minutes=30))
IST_OFFSET = "+05:30"   # for AT TIME ZONE in Postgres

I2D_DESTS = {"BOM", "BLR", "MAA", "CCU", "AMD", "HYD", "COK"}
LOCAL_DEST = "DEL"

MORNING, AFTERNOON, EVENING = "morning", "afternoon", "evening"


def _kg_to_mt(kg: Optional[Decimal | float]) -> float:
    return round(float(kg or 0) / 1000.0, 3)


def _to_ist(dt: Optional[datetime]) -> Optional[datetime]:
    if dt is None:
        return None
    if dt.tzinfo is None:
        dt = dt.replace(tzinfo=timezone.utc)
    return dt.astimezone(IST)


class ProductivityImportShiftService:
    """Computes segregation dashboard metrics for a single IST date, split by shift."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── Shift window helpers ────────────────────────────────────────────────
    def _shift_windows(self, d: date) -> list[ShiftWindow]:
        base = datetime(d.year, d.month, d.day, tzinfo=IST)
        return [
            ShiftWindow(name=MORNING,   start_ist=base.replace(hour=6),  end_ist=base.replace(hour=14)),
            ShiftWindow(name=AFTERNOON, start_ist=base.replace(hour=14), end_ist=base.replace(hour=22)),
            ShiftWindow(name=EVENING,   start_ist=base.replace(hour=22), end_ist=base.replace(hour=6) + timedelta(days=1)),
        ]

    def _fcc_ist(self):
        """flt_com_dat_tim expressed in IST wall-clock as a SQL expression.

        Postgres stores timestamptz in UTC; `AT TIME ZONE 'interval'` returns the
        local wall-clock timestamp (naive) for that offset. We use a fixed +05:30
        offset because IST has no DST.
        """
        return func.timezone(IST_OFFSET, Flight.flt_com_dat_tim)

    def _shift_label(self):
        """SQL CASE mapping FCC(IST) hour -> shift name. Evening spans midnight."""
        hour = func.extract("hour", self._fcc_ist())
        return case(
            ((hour >= 6) & (hour < 14), literal(MORNING)),
            ((hour >= 14) & (hour < 22), literal(AFTERNOON)),
            else_=literal(EVENING),   # 22:00-23:59 and 00:00-05:59
        )

    def _day_window_utc(self, d: date) -> tuple[datetime, datetime]:
        """The operating-day bounds in UTC: [date 06:00 IST, date+1 06:00 IST)."""
        start_ist = datetime(d.year, d.month, d.day, 6, 0, tzinfo=IST)
        end_ist = start_ist + timedelta(days=1)
        return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)

    # ── Main entry ──────────────────────────────────────────────────────────
    async def build(self, report_date: date) -> ImportProductivityDashboardResponse:
        day_start_utc, day_end_utc = self._day_window_utc(report_date)
        # Restrict to the operating day; shift label handles the 3-way split.
        rng = (
            (Flight.flt_com_dat_tim >= day_start_utc)
            & (Flight.flt_com_dat_tim < day_end_utc)
        )

        totals = await self._segregation_totals(rng)
        seg_perf = await self._segregation_sla(rng)

        sections = [
            self._overview_section(totals),
            self._segregation_section(totals),
            self._sla_section(seg_perf),
        ]

        meta = ImportProductivityDashboardMeta(
            report_date_ist=report_date,
            shifts=self._shift_windows(report_date),
            generated_at_ist=datetime.now(IST),
            flight_count=int(totals["flight_count"][ "total"]),
            awb_count=int(totals["awb_count"]["total"]),
        )
        return ImportProductivityDashboardResponse(meta=meta, sections=sections)

    # ── Aggregates, grouped by shift ────────────────────────────────────────
    async def _segregation_totals(self, rng) -> dict:
        shift = self._shift_label()
        dest = func.upper(func.trim(Awb.dest))

        stmt = (
            select(
                shift.label("shift"),
                func.coalesce(func.sum(Awb.gross_wgt), 0).label("gross_kg"),
                func.coalesce(func.sum(Awb.chg_wgt), 0).label("chg_kg"),
                func.coalesce(func.sum(Awb.pcs), 0).label("pcs"),
                func.count(distinct(Flight.id)).label("flight_count"),
                func.count(distinct(Awb.awb_no)).label("awb_count"),
                func.coalesce(func.sum(
                    case((dest == LOCAL_DEST, Awb.gross_wgt), else_=0)), 0).label("local_kg"),
                func.coalesce(func.sum(
                    case((dest.in_(I2D_DESTS), Awb.gross_wgt), else_=0)), 0).label("i2d_kg"),
                func.coalesce(func.sum(
                    case((~dest.in_(I2D_DESTS | {LOCAL_DEST}), Awb.gross_wgt), else_=0)), 0).label("i2i_kg"),
            )
            .select_from(Awb)
            .join(Flight, Awb.flight_id == Flight.id)
            .where(rng)
            .group_by(shift)
        )
        rows = (await self.session.execute(stmt)).all()

        # Initialise every metric with a zeroed ShiftValues-style dict.
        def blank():
            return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}

        out = {
            "gross_mt": blank(), "chg_mt": blank(), "pcs": blank(),
            "flight_count": blank(), "awb_count": blank(),
            "local_mt": blank(), "i2d_mt": blank(), "i2i_mt": blank(),
        }
        for r in rows:
            sh = r.shift
            out["gross_mt"][sh] = _kg_to_mt(r.gross_kg)
            out["chg_mt"][sh] = _kg_to_mt(r.chg_kg)
            out["pcs"][sh] = float(r.pcs)
            out["flight_count"][sh] = float(r.flight_count)
            out["awb_count"][sh] = float(r.awb_count)
            out["local_mt"][sh] = _kg_to_mt(r.local_kg)
            out["i2d_mt"][sh] = _kg_to_mt(r.i2d_kg)
            out["i2i_mt"][sh] = _kg_to_mt(r.i2i_kg)

        # Totals. Weight/pcs sum across shifts; distinct counts must be
        # recomputed day-wide (a flight/AWB could appear in two shifts).
        for key in ("gross_mt", "chg_mt", "pcs", "local_mt", "i2d_mt", "i2i_mt"):
            out[key]["total"] = round(sum(out[key][s] for s in (MORNING, AFTERNOON, EVENING)), 3)

        day_counts = await self._day_distinct_counts(rng)
        out["flight_count"]["total"] = float(day_counts["flight_count"])
        out["awb_count"]["total"] = float(day_counts["awb_count"])
        return out

    async def _day_distinct_counts(self, rng) -> dict:
        """Day-wide distinct flight / AWB counts (not summed across shifts)."""
        stmt = (
            select(
                func.count(distinct(Flight.id)).label("flight_count"),
                func.count(distinct(Awb.awb_no)).label("awb_count"),
            )
            .select_from(Awb)
            .join(Flight, Awb.flight_id == Flight.id)
            .where(rng)
        )
        r = (await self.session.execute(stmt)).one()
        return {"flight_count": int(r.flight_count), "awb_count": int(r.awb_count)}

    # ── SLA performance, per shift ──────────────────────────────────────────
    async def _segregation_sla(self, rng) -> dict:
        shift = self._shift_label()
        atw = func.greatest(Flight.last_uld_arrival, Flight.bulk_uld_arrival)
        gross_kg = func.coalesce(func.sum(Awb.gross_wgt), 0)

        per_flight = (
            select(
                Flight.id.label("fid"),
                shift.label("shift"),
                atw.label("atw"),
                Flight.flt_com_dat_tim.label("fcc"),
                gross_kg.label("gross_kg"),
            )
            .select_from(Flight)
            .join(Awb, Awb.flight_id == Flight.id)
            .where(rng)
            .group_by(Flight.id, shift, atw, Flight.flt_com_dat_tim)
        ).subquery()

        tier_hours = case(
            (per_flight.c.gross_kg <= 10000, 4),
            (per_flight.c.gross_kg <= 20000, 6),
            else_=8,
        )
        elapsed_hours = func.extract("epoch", per_flight.c.fcc - per_flight.c.atw) / 3600.0
        is_success = case(
            (
                (per_flight.c.atw.isnot(None))
                & (per_flight.c.fcc.isnot(None))
                & (elapsed_hours <= tier_hours),
                1,
            ),
            else_=0,
        )

        stmt = (
            select(
                per_flight.c.shift.label("shift"),
                func.count().label("total"),
                func.coalesce(func.sum(is_success), 0).label("success"),
            )
            .select_from(per_flight)
            .group_by(per_flight.c.shift)
        )
        rows = (await self.session.execute(stmt)).all()

        def pct(success, total):
            return round(success / total * 100.0, 1) if total else None

        out = {
            MORNING: {"total": 0, "success": 0, "pct": None},
            AFTERNOON: {"total": 0, "success": 0, "pct": None},
            EVENING: {"total": 0, "success": 0, "pct": None},
        }
        day_total = day_success = 0
        for r in rows:
            out[r.shift] = {"total": int(r.total), "success": int(r.success), "pct": pct(int(r.success), int(r.total))}
            day_total += int(r.total)
            day_success += int(r.success)
        out["total"] = {"total": day_total, "success": day_success, "pct": pct(day_success, day_total)}
        return out

    # ── Section builders ────────────────────────────────────────────────────
    @staticmethod
    def _sv(d: dict) -> ShiftValues:
        return ShiftValues(
            morning=d[MORNING], afternoon=d[AFTERNOON],
            evening=d[EVENING], total=d["total"],
        )

    def _overview_section(self, t: dict) -> MetricSection:
        sys, man = MetricSource.system, MetricSource.manual
        rows = [
            MetricRow(key="import_tonnage_gross", s_no="1.A", description="Import Tonnage (Gross Wgt)",
                      values=self._sv(t["gross_mt"]), unit=MetricUnit.mt, source=sys, source_report="Segregation Report"),
            MetricRow(key="import_tonnage_chg", s_no="1.B", description="Import Tonnage (Chg Wgt)",
                      values=self._sv(t["chg_mt"]), unit=MetricUnit.mt, source=sys, source_report="Segregation Report"),
            MetricRow(key="delivery_tonnage_gross", s_no="1.C", description="Delivery Tonnage (Gross Wgt)",
                      pending=True, unit=MetricUnit.mt, source=sys, source_report="Import Release Report",
                      note="Needs Release Report"),
            MetricRow(key="import_tonnage_del", s_no="1", description="Import Tonnage",
                      values=self._sv(t["local_mt"]), unit=MetricUnit.mt, source=sys,
                      source_report="Segregation Report", note="DEST = DEL"),
            MetricRow(key="import_tp_i2i", s_no="2", description="Import TP - I2I",
                      values=self._sv(t["i2i_mt"]), unit=MetricUnit.mt, source=sys, source_report="Segregation Report"),
            MetricRow(key="import_tp_i2d", s_no="3", description="Import TP - I2D",
                      values=self._sv(t["i2d_mt"]), unit=MetricUnit.mt, source=sys, source_report="Segregation Report"),
            MetricRow(key="onrole_manpower_wha", s_no="4", description="On Role Manpower (WHA)",
                      pending=True, unit=MetricUnit.count, source=man, source_report="Roster", note="Needs Roster"),
            MetricRow(key="onfloor_manpower_wha", s_no="5", description="On Floor Manpower (WHA)",
                      pending=True, unit=MetricUnit.count, source=man, source_report="Roster", note="Needs Roster"),
            MetricRow(key="onrole_productivity", s_no="6", description="On Role Productivity",
                      pending=True, unit=MetricUnit.productivity, source=man, source_report="Roster",
                      note="(Gross MT / On Role WHA) * 30"),
            MetricRow(key="onfloor_productivity", s_no="7", description="On Floor Productivity",
                      pending=True, unit=MetricUnit.productivity, source=man, source_report="Roster",
                      note="(Gross MT / On Floor WHA) * 30"),
        ]
        return MetricSection(key="overview", title="Import Dash Board", rows=rows)

    def _segregation_section(self, t: dict) -> MetricSection:
        sys, man = MetricSource.system, MetricSource.manual
        rows = [
            MetricRow(key="seg_flight_count", s_no="1", description="Flight Count",
                      values=self._sv(t["flight_count"]), unit=MetricUnit.count, source=sys, source_report="Segregation Report"),
            MetricRow(key="seg_awb_count", s_no="2", description="Airway Bill Count",
                      values=self._sv(t["awb_count"]), unit=MetricUnit.count, source=sys, source_report="Segregation Report"),
            MetricRow(key="seg_piece_count", s_no="3", description="Piece Count",
                      values=self._sv(t["pcs"]), unit=MetricUnit.count, source=sys, source_report="Segregation Report"),
            MetricRow(key="seg_gross_wgt", s_no="4", description="Weight (Gross Wgt)",
                      values=self._sv(t["gross_mt"]), unit=MetricUnit.mt, source=sys, source_report="Segregation Report"),
            MetricRow(key="seg_onfloor_manpower", s_no="5", description="On Floor Manpower (WHA)",
                      pending=True, unit=MetricUnit.count, source=man, source_report="Roster", note="Needs Roster"),
            MetricRow(key="seg_onfloor_productivity", s_no="6", description="On Floor Productivity",
                      pending=True, unit=MetricUnit.productivity, source=man, source_report="Roster",
                      note="(Gross MT / On Floor WHA) * 30"),
        ]
        return MetricSection(key="segregation", title="P.1  Segregation", rows=rows)

    def _sla_section(self, seg: dict) -> MetricSection:
        sys = MetricSource.system
        vals = ShiftValues(
            morning=seg[MORNING]["pct"], afternoon=seg[AFTERNOON]["pct"],
            evening=seg[EVENING]["pct"], total=seg["total"]["pct"],
        )
        rows = [
            MetricRow(key="sla_seg_performance", s_no="1", description="Segregation Performance",
                      values=vals, pending=seg["total"]["pct"] is None,
                      unit=MetricUnit.percent, source=sys, source_report="Segregation Report",
                      note=f"{seg['total']['success']}/{seg['total']['total']} flights within SLA (day)"),
            MetricRow(key="sla_release_performance", s_no="2", description="Release Performance",
                      pending=True, unit=MetricUnit.percent, source=sys, source_report="Release Report"),
            MetricRow(key="sla_truckout_performance", s_no="3", description="Truck Out Performance",
                      pending=True, unit=MetricUnit.percent, source=sys, source_report="Import Truck Slot Mgt"),
            MetricRow(key="sla_online_gp", s_no="4", description="Online Gate Pass",
                      pending=True, unit=MetricUnit.percent, source=sys, source_report="Import Release Report"),
        ]
        return MetricSection(key="sla", title="P.5  SLA", rows=rows)