



# """
# Segregation metric computation — SHIFT-BASED.

# Input: a single IST date (report_date).
# Output: each segregation metric split across three shifts + a day total.

# Shift windows (IST):
#     Morning    [date 06:00, date 14:00)
#     Afternoon  [date 14:00, date 22:00)
#     Evening    [date 22:00, date+1 06:00)

# A shipment is assigned to a shift by flt_com_dat_tim (FCC) converted to IST.
# The union of the three shifts is exactly [date 06:00 IST, date+1 06:00 IST) —
# i.e. a cargo "operating day" starts at 06:00, not midnight. Cargo whose
# completion falls between 00:00 and 06:00 belongs to the PREVIOUS day's Evening
# shift, which is the correct operational behaviour.

# Column mapping (Segregation Report -> ORM):
#     E Flight No.  -> flight.flight_no
#     G AWB No      -> awb.awb_no
#     N DEST        -> awb.dest
#     S PCS         -> awb.pcs
#     T Gross Wgt   -> awb.gross_wgt
#     U CHG WGT     -> awb.chg_wgt
#     K/L ULD arr.  -> flight.last_uld_arrival / flight.bulk_uld_arrival (ATW=max)
#     AI FLT_COM    -> flight.flt_com_dat_tim (FCC)
# """

# from datetime import date, datetime, timedelta, timezone
# from decimal import Decimal
# from typing import Optional

# from sqlalchemy import func, select, case, distinct, literal
# from sqlalchemy.ext.asyncio import AsyncSession


# from app.db.models.digital_reports.segrigation_report import (
#     DigitalReportImportSegFlight as Flight,
#     DigitalReportImportSegAwb as Awb,
# )
# from app.services.digital_reports.import_dpt.operation_productivity_report.common_airline_utils import resolve_airline
# from app.schemas.digital_reports.import_dept.operation_productivity_schema import (
#     ImportProductivityDashboardResponse, ImportProductivityDashboardMeta,
#     MetricSection, MetricRow, ShiftValues, ShiftWindow,
#     MetricUnit, MetricSource,
# )

# IST = timezone(timedelta(hours=5, minutes=30))
# IST_ZONE_NAME = "Asia/Kolkata"   # named zone — unambiguous, unlike the "+05:30" text offset

# I2D_DESTS = {"BOM", "BLR", "MAA", "CCU", "AMD", "HYD", "COK"}
# LOCAL_DEST = "DEL"

# MORNING, AFTERNOON, EVENING = "morning", "afternoon", "evening"


# def _kg_to_mt(kg: Optional[Decimal | float]) -> float:
#     return round(float(kg or 0) / 1000.0, 3)


# def _to_ist(dt: Optional[datetime]) -> Optional[datetime]:
#     if dt is None:
#         return None
#     if dt.tzinfo is None:
#         dt = dt.replace(tzinfo=timezone.utc)
#     return dt.astimezone(IST)


# class ProductivityImportShiftService:
#     """Computes segregation dashboard metrics for a single IST date, split by shift."""

#     def __init__(self, session: AsyncSession):
#         self.session = session

#     # ── Shift window helpers ────────────────────────────────────────────────
#     def _shift_windows(self, d: date) -> list[ShiftWindow]:
#         base = datetime(d.year, d.month, d.day, tzinfo=IST)
#         return [
#             ShiftWindow(name=MORNING,   start_ist=base.replace(hour=6),  end_ist=base.replace(hour=14)),
#             ShiftWindow(name=AFTERNOON, start_ist=base.replace(hour=14), end_ist=base.replace(hour=22)),
#             ShiftWindow(name=EVENING,   start_ist=base.replace(hour=22), end_ist=base.replace(hour=6) + timedelta(days=1)),
#         ]
    
#     def _fcc_ist(self):
#         """flt_com_dat_tim expressed in IST wall-clock as a SQL expression.

#         Uses the NAMED zone 'Asia/Kolkata'. Do NOT use a text offset like
#         '+05:30' here: Postgres interprets that as a POSIX-style zone where the
#         sign is inverted, so it subtracts 5:30 instead of adding it and every
#         row lands in the wrong shift.
#         """
#         return func.timezone(IST_ZONE_NAME, Flight.flt_com_dat_tim)

    
#     def _shift_label(self):
#         """SQL CASE mapping FCC(IST) hour -> shift name. Evening spans midnight."""
#         hour = func.extract("hour", self._fcc_ist())
#         return case(
#             ((hour >= 6) & (hour < 14), literal(MORNING)),
#             ((hour >= 14) & (hour < 22), literal(AFTERNOON)),
#             else_=literal(EVENING),   # 22:00-23:59 and 00:00-05:59
#         )
 
#     def _day_window_utc(self, d: date) -> tuple[datetime, datetime]:
#         """The operating-day bounds in UTC: [date 06:00 IST, date+1 06:00 IST)."""
#         start_ist = datetime(d.year, d.month, d.day, 6, 0, tzinfo=IST)
#         end_ist = start_ist + timedelta(days=1)
#         return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)
 
#     # ── Main entry ──────────────────────────────────────────────────────────
#     async def build(self, report_date: date) -> ImportProductivityDashboardResponse:
#         day_start_utc, day_end_utc = self._day_window_utc(report_date)
#         # Restrict to the operating day; shift label handles the 3-way split.
#         rng = (
#             (Flight.flt_com_dat_tim >= day_start_utc)
#             & (Flight.flt_com_dat_tim < day_end_utc)
#         )
 
#         totals = await self._segregation_totals(rng)
#         seg_perf = await self._segregation_sla(rng)
#         flight_cats = await self._flight_count_by_category(rng)
#         awb_cats = await self._awb_metrics_by_category(rng)
 
#         # Release (irr_report) metrics — computed by a separate service that
#         # buckets by gate_pass_issued_date. Returns per-shift metric dicts.
#         release = await ReleaseShiftService(self.session).compute(report_date)
#         # Truck IN/OUT metrics — buckets by time_in; SLA joins to release.
#         truck = await TruckShiftService(self.session).compute(report_date)
#         # Pick Order (Examination) metrics — buckets by POE start (configurable).
#         pick_order = await PickOrderShiftService(self.session).compute(report_date)
 
#         sections = [
#             self._overview_section(totals, release),
#             self._segregation_section(totals, flight_cats, awb_cats),
#             self._examination_section(pick_order),
#             self._release_section(release, truck),
#             self._sla_section(seg_perf, release, truck),
#         ]
 
#         meta = ImportProductivityDashboardMeta(
#             report_date_ist=report_date,
#             shifts=self._shift_windows(report_date),
#             generated_at_ist=datetime.now(IST),
#             flight_count=int(totals["flight_count"][ "total"]),
#             awb_count=int(totals["awb_count"]["total"]),
#         )
#         return ImportProductivityDashboardResponse(meta=meta, sections=sections)
 
#     # ── Aggregates, grouped by shift ────────────────────────────────────────
#     async def _segregation_totals(self, rng) -> dict:
#         shift = self._shift_label()
#         dest = func.upper(func.trim(Awb.dest))
 
#         stmt = (
#             select(
#                 shift.label("shift"),
#                 func.coalesce(func.sum(Awb.gross_wgt), 0).label("gross_kg"),
#                 func.coalesce(func.sum(Awb.chg_wgt), 0).label("chg_kg"),
#                 func.coalesce(func.sum(Awb.pcs), 0).label("pcs"),
#                 func.count(distinct(Flight.id)).label("flight_count"),
#                 func.count(distinct(Awb.awb_no)).label("awb_count"),
#                 func.coalesce(func.sum(
#                     case((dest == LOCAL_DEST, Awb.gross_wgt), else_=0)), 0).label("local_kg"),
#                 func.coalesce(func.sum(
#                     case((dest.in_(I2D_DESTS), Awb.gross_wgt), else_=0)), 0).label("i2d_kg"),
#                 func.coalesce(func.sum(
#                     case((~dest.in_(I2D_DESTS | {LOCAL_DEST}), Awb.gross_wgt), else_=0)), 0).label("i2i_kg"),
#                 # Same DEL / I2I / I2D split, but on CHARGE weight (for Summary "b").
#                 func.coalesce(func.sum(
#                     case((dest == LOCAL_DEST, Awb.chg_wgt), else_=0)), 0).label("local_chg_kg"),
#                 func.coalesce(func.sum(
#                     case((dest.in_(I2D_DESTS), Awb.chg_wgt), else_=0)), 0).label("i2d_chg_kg"),
#                 func.coalesce(func.sum(
#                     case((~dest.in_(I2D_DESTS | {LOCAL_DEST}), Awb.chg_wgt), else_=0)), 0).label("i2i_chg_kg"),
#             )
#             .select_from(Awb)
#             .join(Flight, Awb.flight_id == Flight.id)
#             .where(rng)
#             .group_by(shift)
#         )
#         rows = (await self.session.execute(stmt)).all()
 
#         # Initialise every metric with a zeroed ShiftValues-style dict.
#         def blank():
#             return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}
 
#         out = {
#             "gross_mt": blank(), "chg_mt": blank(), "pcs": blank(),
#             "flight_count": blank(), "awb_count": blank(),
#             "local_mt": blank(), "i2d_mt": blank(), "i2i_mt": blank(),
#             "local_chg_mt": blank(), "i2d_chg_mt": blank(), "i2i_chg_mt": blank(),
#         }
#         for r in rows:
#             sh = r.shift
#             out["gross_mt"][sh] = _kg_to_mt(r.gross_kg)
#             out["chg_mt"][sh] = _kg_to_mt(r.chg_kg)
#             out["pcs"][sh] = float(r.pcs)
#             out["flight_count"][sh] = float(r.flight_count)
#             out["awb_count"][sh] = float(r.awb_count)
#             out["local_mt"][sh] = _kg_to_mt(r.local_kg)
#             out["i2d_mt"][sh] = _kg_to_mt(r.i2d_kg)
#             out["i2i_mt"][sh] = _kg_to_mt(r.i2i_kg)
#             out["local_chg_mt"][sh] = _kg_to_mt(r.local_chg_kg)
#             out["i2d_chg_mt"][sh] = _kg_to_mt(r.i2d_chg_kg)
#             out["i2i_chg_mt"][sh] = _kg_to_mt(r.i2i_chg_kg)
 
#         # Totals. Weight/pcs sum across shifts; distinct counts must be
#         # recomputed day-wide (a flight/AWB could appear in two shifts).
#         for key in ("gross_mt", "chg_mt", "pcs", "local_mt", "i2d_mt", "i2i_mt",
#                     "local_chg_mt", "i2d_chg_mt", "i2i_chg_mt"):
#             out[key]["total"] = round(sum(out[key][s] for s in (MORNING, AFTERNOON, EVENING)), 3)
 
#         day_counts = await self._day_distinct_counts(rng)
#         out["flight_count"]["total"] = float(day_counts["flight_count"])
#         out["awb_count"]["total"] = float(day_counts["awb_count"])
#         return out
 
#     async def _day_distinct_counts(self, rng) -> dict:
#         """Day-wide distinct flight / AWB counts (not summed across shifts)."""
#         stmt = (
#             select(
#                 func.count(distinct(Flight.id)).label("flight_count"),
#                 func.count(distinct(Awb.awb_no)).label("awb_count"),
#             )
#             .select_from(Awb)
#             .join(Flight, Awb.flight_id == Flight.id)
#             .where(rng)
#         )
#         r = (await self.session.execute(stmt)).one()
#         return {"flight_count": int(r.flight_count), "awb_count": int(r.awb_count)}
 
#     async def _flight_count_by_category(self, rng) -> dict:
#         """
#         Distinct flight count per shift, split into Passenger (PAX) and
#         Freighter (CAO) using the shared airline master.
 
#         A flight is one physical departure; its PAX/CAO category is stable
#         regardless of per-AWB dest, so we classify each distinct flight once
#         by its flight_no. We pull (flight_no, dest, shift) for the distinct
#         flights and count per shift × category in Python — mirroring how the
#         existing segregation report classifies.
 
#         Returns:
#             {
#               "total":      {morning, afternoon, evening, total},   # both cats
#               "passenger":  {...same shape...},
#               "freighter":  {...same shape...},
#             }
#         """
#         shift = self._shift_label()
#         stmt = (
#             select(
#                 Flight.id,
#                 Flight.flight_no,
#                 Flight.dest,
#                 shift.label("shift"),
#             )
#             .select_from(Flight)
#             .where(rng)
#             .distinct()
#         )
#         rows = (await self.session.execute(stmt)).all()
 
#         def blank_counts():
#             return {MORNING: 0, AFTERNOON: 0, EVENING: 0, "total": 0}
 
#         out = {
#             "total": blank_counts(),
#             "passenger": blank_counts(),
#             "freighter": blank_counts(),
#         }
#         # A flight id could in theory appear under one shift only (its FCC is a
#         # single instant), so counting rows == counting distinct flights here.
#         for r in rows:
#             info = resolve_airline(r.flight_no or "", r.dest or "")
#             bucket = "passenger" if info.category == "PAX" else "freighter"
#             sh = r.shift
#             out[bucket][sh] += 1
#             out["total"][sh] += 1
 
#         for grp in ("total", "passenger", "freighter"):
#             out[grp]["total"] = out[grp][MORNING] + out[grp][AFTERNOON] + out[grp][EVENING]
#         return out
 
#     async def _awb_metrics_by_category(self, rng) -> dict:
#         """
#         AWB-level metrics (MAWB / HAWB / Piece / Gross / Charge) per shift,
#         split into Passenger (PAX) and Freighter (CAO).
 
#         WHY THIS SHAPE:
#         The PAX/CAO category is decided by the airline master via
#         resolve_airline(flight_no, dest) — that is Python logic, so the split
#         cannot be done purely in SQL. To stay efficient we do as much as
#         possible in ONE SQL pass, then fold flight_no -> category in Python.
 
#         SQL step (one query):
#           Group by (shift, flight_no, awb_no) and aggregate the AWB's numbers.
#           Grouping down to awb_no means each MAWB is one row per shift/flight —
#           so counting rows gives the distinct MAWB count, and SUM(no_of_houses)
#           gives HAWB, SUM(pcs)/SUM(weights) give the rest. (An AWB that was
#           split into several DB rows under the same flight is collapsed here.)
 
#         Python step:
#           For each (shift, flight_no, awb_no) row, resolve the flight to
#           PAX/CAO once and add its numbers into that bucket. flight_no is all
#           we need for the category (dest only matters for the Air-India
#           Delhi/TP split, which this dashboard does not use).
 
#         Returns a dict keyed by metric, each holding total/passenger/freighter,
#         each of those a {morning, afternoon, evening, total} dict:
#             {
#               "mawb":  {"total": {...}, "passenger": {...}, "freighter": {...}},
#               "hawb":  {...},
#               "pcs":   {...},
#               "gross_mt": {...},   # already converted to MT
#               "chg_mt":   {...},   # already converted to MT
#             }
#         """
#         shift = self._shift_label()
 
#         # ── SQL: one row per (shift, flight_no, awb_no) with that AWB's totals ──
#         stmt = (
#             select(
#                 shift.label("shift"),
#                 Flight.flight_no.label("flight_no"),
#                 Flight.dest.label("dest"),
#                 Awb.awb_no.label("awb_no"),
#                 func.coalesce(func.sum(Awb.pcs), 0).label("pcs"),
#                 func.coalesce(func.sum(Awb.gross_wgt), 0).label("gross_kg"),
#                 func.coalesce(func.sum(Awb.chg_wgt), 0).label("chg_kg"),
#                 func.coalesce(func.sum(Awb.no_of_houses), 0).label("houses"),
#             )
#             .select_from(Awb)
#             .join(Flight, Awb.flight_id == Flight.id)
#             .where(rng)
#             .group_by(shift, Flight.flight_no, Flight.dest, Awb.awb_no)
#         )
#         rows = (await self.session.execute(stmt)).all()
 
#         # ── prepare zeroed accumulators ──
#         def blank():
#             return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}
 
#         def blank_group():
#             return {"total": blank(), "passenger": blank(), "freighter": blank()}
 
#         metrics = {
#             "mawb": blank_group(),   # count of AWB rows
#             "hawb": blank_group(),   # SUM(no_of_houses)
#             "pcs": blank_group(),    # SUM(pcs)
#             "gross_kg": blank_group(),  # SUM(gross) — converted to MT at the end
#             "chg_kg": blank_group(),    # SUM(chg)   — converted to MT at the end
#         }
 
#         # ── Python: fold each AWB row into total + its PAX/CAO bucket ──
#         for r in rows:
#             info = resolve_airline(r.flight_no or "", r.dest or "")
#             cat = "passenger" if info.category == "PAX" else "freighter"
#             sh = r.shift
#             for grp in ("total", cat):
#                 metrics["mawb"][grp][sh] += 1                    # one row = one MAWB
#                 metrics["hawb"][grp][sh] += float(r.houses or 0)
#                 metrics["pcs"][grp][sh] += float(r.pcs or 0)
#                 metrics["gross_kg"][grp][sh] += float(r.gross_kg or 0)
#                 metrics["chg_kg"][grp][sh] += float(r.chg_kg or 0)
 
#         # ── shift totals, and kg -> MT for the weight metrics ──
#         for key, grp_dict in metrics.items():
#             for grp in ("total", "passenger", "freighter"):
#                 d = grp_dict[grp]
#                 d["total"] = d[MORNING] + d[AFTERNOON] + d[EVENING]
 
#         # Convert the two weight metrics from kg to MT (3dp), keep counts as-is.
#         def to_mt_group(grp_dict):
#             out = {}
#             for grp in ("total", "passenger", "freighter"):
#                 out[grp] = {k: _kg_to_mt(v) for k, v in grp_dict[grp].items()}
#             return out
 
#         return {
#             "mawb": metrics["mawb"],
#             "hawb": metrics["hawb"],
#             "pcs": metrics["pcs"],
#             "gross_mt": to_mt_group(metrics["gross_kg"]),
#             "chg_mt": to_mt_group(metrics["chg_kg"]),
#         }
 
 
#     # ── SLA performance, per shift ──────────────────────────────────────────
#     async def _segregation_sla(self, rng) -> dict:
#         shift = self._shift_label()
#         atw = func.greatest(Flight.last_uld_arrival, Flight.bulk_uld_arrival)
#         gross_kg = func.coalesce(func.sum(Awb.gross_wgt), 0)
 
#         per_flight = (
#             select(
#                 Flight.id.label("fid"),
#                 shift.label("shift"),
#                 atw.label("atw"),
#                 Flight.flt_com_dat_tim.label("fcc"),
#                 gross_kg.label("gross_kg"),
#             )
#             .select_from(Flight)
#             .join(Awb, Awb.flight_id == Flight.id)
#             .where(rng)
#             .group_by(Flight.id, shift, atw, Flight.flt_com_dat_tim)
#         ).subquery()
 
#         tier_hours = case(
#             (per_flight.c.gross_kg <= 10000, 4),
#             (per_flight.c.gross_kg <= 20000, 6),
#             else_=8,
#         )
#         elapsed_hours = func.extract("epoch", per_flight.c.fcc - per_flight.c.atw) / 3600.0
#         is_success = case(
#             (
#                 (per_flight.c.atw.isnot(None))
#                 & (per_flight.c.fcc.isnot(None))
#                 & (elapsed_hours <= tier_hours),
#                 1,
#             ),
#             else_=0,
#         )
 
#         stmt = (
#             select(
#                 per_flight.c.shift.label("shift"),
#                 func.count().label("total"),
#                 func.coalesce(func.sum(is_success), 0).label("success"),
#             )
#             .select_from(per_flight)
#             .group_by(per_flight.c.shift)
#         )
#         rows = (await self.session.execute(stmt)).all()
 
#         def pct(success, total):
#             return round(success / total * 100.0, 1) if total else None
 
#         out = {
#             MORNING: {"total": 0, "success": 0, "pct": None},
#             AFTERNOON: {"total": 0, "success": 0, "pct": None},
#             EVENING: {"total": 0, "success": 0, "pct": None},
#         }
#         day_total = day_success = 0
#         for r in rows:
#             out[r.shift] = {"total": int(r.total), "success": int(r.success), "pct": pct(int(r.success), int(r.total))}
#             day_total += int(r.total)
#             day_success += int(r.success)
#         out["total"] = {"total": day_total, "success": day_success, "pct": pct(day_success, day_total)}
#         return out
 
#     # ── Section builders ────────────────────────────────────────────────────
#     @staticmethod
#     def _sv(d: dict) -> ShiftValues:
#         return ShiftValues(
#             morning=d[MORNING], afternoon=d[AFTERNOON],
#             evening=d[EVENING], total=d["total"],
#         )
 
#     def _overview_section(self, t: dict, release: dict) -> MetricSection:
#         sys, man = MetricSource.system, MetricSource.manual
#         seg = "Segregation Report"
 
#         # a — Gross Wgt (MT), collapsible into DEL / I2I / I2D
#         gross_row = MetricRow(
#             key="sum_gross_wgt", s_no="a", description="Gross Wgt (MT)",
#             values=self._sv(t["gross_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg,
#             children=[
#                 MetricRow(key="sum_gross_del", s_no="a.1", description="Import - Delhi",
#                           values=self._sv(t["local_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
#                 MetricRow(key="sum_gross_i2i", s_no="a.2", description="Import TP - I2I",
#                           values=self._sv(t["i2i_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
#                 MetricRow(key="sum_gross_i2d", s_no="a.3", description="Import TP - I2D",
#                           values=self._sv(t["i2d_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
#             ],
#         )
 
#         # b — Charge Wgt (MT), collapsible into DEL / I2I / I2D (charge weight)
#         chg_row = MetricRow(
#             key="sum_chg_wgt", s_no="b", description="Charge Wgt (MT)",
#             values=self._sv(t["chg_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg,
#             children=[
#                 MetricRow(key="sum_chg_del", s_no="b.1", description="Import - Delhi",
#                           values=self._sv(t["local_chg_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
#                 MetricRow(key="sum_chg_i2i", s_no="b.2", description="Import TP - I2I",
#                           values=self._sv(t["i2i_chg_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
#                 MetricRow(key="sum_chg_i2d", s_no="b.3", description="Import TP - I2D",
#                           values=self._sv(t["i2d_chg_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
#             ],
#         )
 
#         # c — Gross vs Charge Weight (%): charge / gross * 100, per shift.
#         # (Frontend colours it: <110% red, >=110% green.)
#         def _pct_of(chg: dict, gross: dict) -> ShiftValues:
#             def one(sh):
#                 g = gross[sh]
#                 return round(chg[sh] / g * 100.0, 1) if g else None
#             return ShiftValues(
#                 morning=one(MORNING), afternoon=one(AFTERNOON),
#                 evening=one(EVENING), total=one("total"),
#             )
 
#         gross_vs_chg = MetricRow(
#             key="sum_gross_vs_chg", s_no="c", description="Gross Weight vs Charge Weight (%)",
#             values=_pct_of(t["chg_mt"], t["gross_mt"]),
#             unit=MetricUnit.percent, source=sys, source_report=seg,
#             note="Charge ÷ Gross; <110% red, ≥110% green",
#         )
 
#         rows = [
#             gross_row,
#             chg_row,
#             gross_vs_chg,
#             MetricRow(key="sum_delivery_gross", s_no="d", description="Delivery Gross Wgt (MT)",
#                       values=self._sv(release["delivery_mt"]), unit=MetricUnit.mt,
#                       source=sys, source_report="Release Report"),
#             MetricRow(key="sum_prod_delivery", s_no="e", description="Productivity on Delivery (Grs MT/Month)",
#                       pending=True, unit=MetricUnit.productivity, source=sys, source_report="Release Report/Roster",
#                       note="Total GP Gross MT / On Role WHA * day count",
#                       children=[
#                           MetricRow(key="sum_prod_delivery_onrole_wha", s_no="e.1",
#                                     description="On Role WHA Count", pending=True,
#                                     unit=MetricUnit.count, source=sys, source_report="Roster"),
#                           MetricRow(key="sum_prod_delivery_onrole_prod", s_no="e.2",
#                                     description="On Role Productivity", pending=True,
#                                     unit=MetricUnit.productivity, source=sys, source_report="Roster"),
#                           MetricRow(key="sum_prod_delivery_onfloor_wha", s_no="e.3",
#                                     description="On Floor WHA Count", pending=True,
#                                     unit=MetricUnit.count, source=sys, source_report="Roster"),
#                           MetricRow(key="sum_prod_delivery_onfloor_prod", s_no="e.4",
#                                     description="On Floor Productivity", pending=True,
#                                     unit=MetricUnit.productivity, source=sys, source_report="Roster"),
#                       ]),
#             MetricRow(key="sum_prod_segregation", s_no="f", description="Productivity on Segregation (Grs MT/Month)",
#                       pending=True, unit=MetricUnit.productivity, source=sys, source_report="Segregation Report/Roster",
#                       note="Total Seg Gross MT / On Role WHA * day count",
#                       children=[
#                           MetricRow(key="sum_prod_seg_onrole_wha", s_no="f.1",
#                                     description="On Role WHA Count", pending=True,
#                                     unit=MetricUnit.count, source=sys, source_report="Roster"),
#                           MetricRow(key="sum_prod_seg_onrole_prod", s_no="f.2",
#                                     description="On Role Productivity", pending=True,
#                                     unit=MetricUnit.productivity, source=sys, source_report="Roster"),
#                           MetricRow(key="sum_prod_seg_onfloor_wha", s_no="f.3",
#                                     description="On Floor WHA Count", pending=True,
#                                     unit=MetricUnit.count, source=sys, source_report="Roster"),
#                           MetricRow(key="sum_prod_seg_onfloor_prod", s_no="f.4",
#                                     description="On Floor Productivity", pending=True,
#                                     unit=MetricUnit.productivity, source=sys, source_report="Roster"),
#                       ]),
#         ]
#         return MetricSection(key="summary", title="Summary", rows=rows)
 
#     def _segregation_section(self, t: dict, flight_cats: dict, awb_cats: dict) -> MetricSection:
#         sys, man = MetricSource.system, MetricSource.manual
#         seg = "Segregation Report"
 
#         # Helper: turn a {morning,afternoon,evening,total} dict into ShiftValues.
#         def _counts_sv(d: dict) -> ShiftValues:
#             return ShiftValues(
#                 morning=float(d[MORNING]), afternoon=float(d[AFTERNOON]),
#                 evening=float(d[EVENING]), total=float(d["total"]),
#             )
 
#         # Helper: build a "parent + Passenger/Freighter children" row for a
#         # metric that lives in awb_cats (mawb/hawb/pcs/gross_mt/chg_mt) or
#         # flight_cats. `group` is the awb_cats key; `unit` its unit.
#         def _split_row(key, s_no, desc, group: dict, unit) -> MetricRow:
#             return MetricRow(
#                 key=key, s_no=s_no, description=desc,
#                 values=_counts_sv(group["total"]), unit=unit, source=sys, source_report=seg,
#                 children=[
#                     MetricRow(key=f"{key}_pax", s_no=f"{s_no}.1",
#                               description=f"Passenger {desc}",
#                               values=_counts_sv(group["passenger"]),
#                               unit=unit, source=sys, source_report=seg),
#                     MetricRow(key=f"{key}_cao", s_no=f"{s_no}.2",
#                               description=f"Freighters {desc}",
#                               values=_counts_sv(group["freighter"]),
#                               unit=unit, source=sys, source_report=seg),
#                 ],
#             )
 
#         # a — Flight Count (from flight_cats: distinct flights per category)
#         flight_count_row = MetricRow(
#             key="seg_flight_count", s_no="a", description="Flight Count",
#             values=_counts_sv(flight_cats["total"]),
#             unit=MetricUnit.count, source=sys, source_report=seg,
#             children=[
#                 MetricRow(key="seg_flight_count_pax", s_no="a.1",
#                           description="Passenger Flights Count",
#                           values=_counts_sv(flight_cats["passenger"]),
#                           unit=MetricUnit.count, source=sys, source_report=seg),
#                 MetricRow(key="seg_flight_count_cao", s_no="a.2",
#                           description="Freighters Count",
#                           values=_counts_sv(flight_cats["freighter"]),
#                           unit=MetricUnit.count, source=sys, source_report=seg),
#             ],
#         )
 
#         rows = [
#             flight_count_row,
#             # b — MAWB Count (distinct AWB per category)
#             _split_row("seg_mawb_count", "b", "MAWB Count", awb_cats["mawb"], MetricUnit.count),
#             # c — HAWB Count (SUM of no_of_houses per category)
#             _split_row("seg_hawb_count", "c", "HAWB Count", awb_cats["hawb"], MetricUnit.count),
#             # d — Piece Count
#             _split_row("seg_piece_count", "d", "Piece Count", awb_cats["pcs"], MetricUnit.count),
#             # e — Gross Weight (MT)
#             _split_row("seg_gross_wgt", "e", "Gross Weight (MT)", awb_cats["gross_mt"], MetricUnit.mt),
#             # f — Charge Weight (MT)
#             _split_row("seg_chg_wgt", "f", "Charge Weight (MT)", awb_cats["chg_mt"], MetricUnit.mt),
#             # g — On Floor Productivity (no children; pending Roster)
#             MetricRow(key="seg_onfloor_productivity", s_no="g", description="On Floor Productivity",
#                       pending=True, unit=MetricUnit.productivity, source=man, source_report="Roster",
#                       note="(Gross MT / On Floor WHA) * 30",
#                       children=[
#                           MetricRow(key="seg_onfloor_manpower", s_no="g.1",
#                                     description="On Floor Manpower (WHA)", pending=True,
#                                     unit=MetricUnit.count, source=man, source_report="Roster",
#                                     note="Needs Roster"),
#                       ]),
#         ]
#         return MetricSection(key="segregation", title="P.1  Segregation", rows=rows)
 
#     def _examination_section(self, pick_order: dict) -> MetricSection:
#         """P.2 Examination — from the pick order report."""
#         sys, man = MetricSource.system, MetricSource.manual
#         po = "Pick Order Report"
#         rows = [
#             MetricRow(key="exam_awb_count", s_no="a",
#                       description="No. of Pick Order / AWB Number",
#                       values=self._sv(pick_order["awb_count"]), unit=MetricUnit.count,
#                       source=sys, source_report=po),
#             MetricRow(key="exam_pcs", s_no="b", description="No. of Pcs",
#                       values=self._sv(pick_order["pcs"]), unit=MetricUnit.count,
#                       source=sys, source_report=po),
#             MetricRow(key="exam_onfloor_productivity", s_no="c",
#                       description="On Floor Productivity (Pcs/WHA)", pending=True,
#                       unit=MetricUnit.productivity, source=man, source_report="Roster",
#                       note="(No. of Pcs / On Floor WHA) * days in month",
#                       children=[
#                           MetricRow(key="exam_onfloor_manpower", s_no="c.1",
#                                     description="On Floor Manpower (WHA)", pending=True,
#                                     unit=MetricUnit.count, source=man, source_report="Roster"),
#                       ]),
#         ]
#         return MetricSection(key="examination", title="P.2  Examination", rows=rows)
 
#     def _release_section(self, release: dict, truck: dict) -> MetricSection:
#         """P.3 Release Report — from irr_report (gate_pass_issued_date shifts).
#         Truck Count comes from the truck IN/OUT report."""
#         sys, man = MetricSource.system, MetricSource.manual
#         rel = "Release Report"
#         rows = [
#             MetricRow(key="rel_gp_count", s_no="a", description="Gate Pass Count",
#                       values=self._sv(release["gp_count"]), unit=MetricUnit.count,
#                       source=sys, source_report=rel),
#             MetricRow(key="rel_pcs", s_no="b", description="Piece Count",
#                       values=self._sv(release["pcs"]), unit=MetricUnit.count,
#                       source=sys, source_report=rel),
#             MetricRow(key="rel_gross_wgt", s_no="c", description="Gross Weight (MT)",
#                       values=self._sv(release["gross_mt"]), unit=MetricUnit.mt,
#                       source=sys, source_report=rel),
#             # d — Truck Count (unique plates) from the truck IN/OUT report.
#             MetricRow(key="rel_truck_count", s_no="d", description="Truck Count",
#                       values=self._sv(truck["truck_count"]), unit=MetricUnit.count,
#                       source=sys, source_report="Import Truck Slot Mgt"),
#             # f — On Floor Productivity (Roster) pending.
#             MetricRow(key="rel_onfloor_productivity", s_no="f", description="On Floor Productivity",
#                       pending=True, unit=MetricUnit.productivity, source=man, source_report="Roster",
#                       note="(Gross MT / On Floor WHA) * days in month",
#                       children=[
#                           MetricRow(key="rel_onfloor_manpower", s_no="f.1",
#                                     description="On Floor Manpower (WHA)", pending=True,
#                                     unit=MetricUnit.count, source=man, source_report="Roster"),
#                       ]),
#         ]
#         return MetricSection(key="release", title="P.3  Release Report", rows=rows)
 
#     def _sla_section(self, seg: dict, release: dict, truck: dict) -> MetricSection:
#         sys = MetricSource.system
#         vals = ShiftValues(
#             morning=seg[MORNING]["pct"], afternoon=seg[AFTERNOON]["pct"],
#             evening=seg[EVENING]["pct"], total=seg["total"]["pct"],
#         )
#         online = release["online_pct"]
#         online_vals = ShiftValues(
#             morning=online[MORNING], afternoon=online[AFTERNOON],
#             evening=online[EVENING], total=online["total"],
#         )
#         rows = [
#             MetricRow(key="sla_seg_performance", s_no="1", description="Segregation Performance",
#                       values=vals, pending=seg["total"]["pct"] is None,
#                       unit=MetricUnit.percent, source=sys, source_report="Segregation Report",
#                       note=f"{seg['total']['success']}/{seg['total']['total']} flights within SLA (day)"),
#             # Release Performance SLA — AF-AE > 4h = failure (from irr_report).
#             MetricRow(key="sla_release_performance", s_no="2", description="Release Performance",
#                       values=ShiftValues(
#                           morning=release["release_perf"][MORNING]["pct"],
#                           afternoon=release["release_perf"][AFTERNOON]["pct"],
#                           evening=release["release_perf"][EVENING]["pct"],
#                           total=release["release_perf"]["total"]["pct"],
#                       ),
#                       pending=release["release_perf"]["total"]["pct"] is None,
#                       unit=MetricUnit.percent, source=sys, source_report="Release Report",
#                       note=f"{release['release_perf']['total']['success']}/"
#                            f"{release['release_perf']['total']['total']} GP within 4h SLA (day)"),
#             MetricRow(key="sla_truckout_performance", s_no="3", description="Truck Out Performance",
#                       values=ShiftValues(
#                           morning=truck["truck_out_sla"][MORNING]["pct"],
#                           afternoon=truck["truck_out_sla"][AFTERNOON]["pct"],
#                           evening=truck["truck_out_sla"][EVENING]["pct"],
#                           total=truck["truck_out_sla"]["total"]["pct"],
#                       ),
#                       pending=truck["truck_out_sla"]["total"]["pct"] is None,
#                       unit=MetricUnit.percent, source=sys, source_report="Import Truck Slot Mgt",
#                       note=f"{truck['truck_out_sla']['total']['success']}/"
#                            f"{truck['truck_out_sla']['total']['total']} trucks within 4h "
#                            f"(fail: {truck['truck_out_sla']['total']['fail_over_4h']} over-4h, "
#                            f"{truck['truck_out_sla']['total']['fail_null_gp_end']} no-GP-end, "
#                            f"{truck['truck_out_sla']['total']['fail_no_match']} unmatched)"),
#             MetricRow(key="sla_online_gp", s_no="4", description="Online Gate Pass",
#                       values=online_vals,
#                       pending=online["total"] is None,
#                       unit=MetricUnit.percent, source=sys, source_report="Release Report",
#                       note="Online GP vs total GP"),
#         ]
#         return MetricSection(key="sla", title="P.5  SLA", rows=rows)
# # =================================IMPORT  RELEASE SERVICE SECTION =========================



# # """
# # Release (IRR) metric computation — SHIFT-BASED.

# # Source table: irr_report (IrrReport). One row per Gate Pass.

# # Shift bucketing:
# #     A Release row is assigned to a shift by gate_pass_issued_date (the GP issue
# #     time), converted to IST — same operating-day windows as the segregation
# #     dashboard (Morning 06-14, Afternoon 14-22, Evening 22-06 next day).

# # Metrics built here (all confirmed):
# #     Gate Pass Count   = COUNT(DISTINCT gate_pass_no)
# #     Piece Count       = SUM(pcs)
# #     Gross Weight (MT) = SUM(grg_wt) / 1000
# #     Online Gate Pass %= GPs with online_counter ILIKE 'Online' / total GP * 100

# # Left pending (rules not finalised):
# #     Release Performance SLA  — needs the two datetime columns confirmed
# #                                (spec: AF - AE > 4h => failure).
# #     Truck Count              — sourced from Import Truck Slot Mgt, not irr_report.

# # Design mirrors segregation_shift_service: named IST zone in SQL (never a
# # '+05:30' text offset), one grouped-by-shift query, day totals reconciled.
# # """


# # # IST = timezone(timedelta(hours=5, minutes=30))
# # # IST_ZONE_NAME = "Asia/Kolkata"

# # # MORNING, AFTERNOON, EVENING = "morning", "afternoon", "evening"

# # from app.db.models.importOperation.import_release_report import IrrReport as Irr

# # # def _kg_to_mt(kg: Optional[float]) -> float:
# # #     return round(float(kg or 0) / 1000.0, 3)


# # class ReleaseShiftService:
# #     """Release (irr_report) metrics for a single IST operating day, split by shift."""

# #     def __init__(self, session: AsyncSession):
# #         self.session = session

# #     # ── shift SQL helpers (bucket by gate_pass_issued_date) ─────────────────
# #     def _issue_ist(self):
# #         """gate_pass_issued_date as IST wall-clock (named zone — no sign trap)."""
# #         return func.timezone(IST_ZONE_NAME, Irr.gate_pass_issued_date)

# #     def _shift_label(self):
# #         hour = func.extract("hour", self._issue_ist())
# #         return case(
# #             ((hour >= 6) & (hour < 14), literal(MORNING)),
# #             ((hour >= 14) & (hour < 22), literal(AFTERNOON)),
# #             else_=literal(EVENING),
# #         )

# #     def _day_window_utc(self, d: date) -> tuple[datetime, datetime]:
# #         start_ist = datetime(d.year, d.month, d.day, 6, 0, tzinfo=IST)
# #         end_ist = start_ist + timedelta(days=1)
# #         return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)

# #     # ── main compute ─────────────────────────────────────────────────────────
# #     async def compute(self, report_date: date) -> dict:
# #         """
# #         Returns a dict of per-shift metric dicts, each shaped
# #         {morning, afternoon, evening, total}:

# #             {
# #               "gp_count":     {...},
# #               "pcs":          {...},
# #               "gross_mt":     {...},
# #               "delivery_mt":  {...},   # same as gross_mt — Summary "d"
# #               "online_pct":   {...},   # Online GP % per shift + day
# #             }

# #         The dashboard service maps these onto MetricRows.
# #         """
# #         day_start_utc, day_end_utc = self._day_window_utc(report_date)
# #         rng = (
# #             (Irr.gate_pass_issued_date >= day_start_utc)
# #             & (Irr.gate_pass_issued_date < day_end_utc)
# #         )

# #         shift = self._shift_label()
# #         online = func.upper(func.trim(Irr.online_counter)) == "ONLINE"

# #         # One grouped pass: per shift, count GP / online GP, sum pcs & weight.
# #         stmt = (
# #             select(
# #                 shift.label("shift"),
# #                 func.count(distinct(Irr.gate_pass_no)).label("gp_count"),
# #                 func.count(distinct(case((online, Irr.gate_pass_no)))).label("online_gp"),
# #                 func.coalesce(func.sum(Irr.pcs), 0).label("pcs"),
# #                 func.coalesce(func.sum(Irr.grg_wt), 0).label("gross_kg"),
# #             )
# #             .where(rng)
# #             .group_by(shift)
# #         )
# #         rows = (await self.session.execute(stmt)).all()

# #         def blank():
# #             return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}

# #         gp = blank()
# #         online_gp = blank()
# #         pcs = blank()
# #         gross = blank()
# #         for r in rows:
# #             sh = r.shift
# #             gp[sh] = float(r.gp_count)
# #             online_gp[sh] = float(r.online_gp)
# #             pcs[sh] = float(r.pcs)
# #             gross[sh] = _kg_to_mt(r.gross_kg)

# #         # Shift-summable metrics: sum across the three shifts.
# #         for m in (gp, online_gp, pcs, gross):
# #             m["total"] = round(m[MORNING] + m[AFTERNOON] + m[EVENING], 3)

# #         # Day-wide DISTINCT GP count (a GP shouldn't span shifts — one issue
# #         # time — but recompute distinct to be safe, matching segregation.)
# #         day_gp = await self._day_distinct_gp(rng)
# #         gp["total"] = float(day_gp)

# #         # Online % per shift and for the day = online GP / total GP * 100.
# #         def pct(part: dict, whole: dict) -> dict:
# #             out = {}
# #             for k in (MORNING, AFTERNOON, EVENING, "total"):
# #                 out[k] = round(part[k] / whole[k] * 100.0, 1) if whole[k] else None
# #             return out

# #         online_pct = pct(online_gp, gp)

# #         return {
# #             "gp_count": gp,
# #             "pcs": pcs,
# #             "gross_mt": gross,
# #             "delivery_mt": gross,   # Summary "d" Delivery Gross Wgt = same sum
# #             "online_pct": online_pct,
# #         }

# #     async def _day_distinct_gp(self, rng) -> int:
# #         stmt = select(func.count(distinct(Irr.gate_pass_no))).where(rng)
# #         return int((await self.session.execute(stmt)).scalar() or 0)









# """
# Release (IRR) metric computation — SHIFT-BASED.

# Source table: irr_report (IrrReport). One row per Gate Pass.

# Shift bucketing:
#     A Release row is assigned to a shift by gate_pass_issued_date (the GP issue
#     time), converted to IST — same operating-day windows as the segregation
#     dashboard (Morning 06-14, Afternoon 14-22, Evening 22-06 next day).

# Metrics built here (all confirmed):
#     Gate Pass Count   = COUNT(DISTINCT gate_pass_no)
#     Piece Count       = SUM(pcs)
#     Gross Weight (MT) = SUM(grg_wt) / 1000
#     Online Gate Pass %= GPs with online_counter ILIKE 'Online' / total GP * 100

# Left pending (rules not finalised):
#     Release Performance SLA  — needs the two datetime columns confirmed
#                                (spec: AF - AE > 4h => failure).
#     Truck Count              — sourced from Import Truck Slot Mgt, not irr_report.

# Design mirrors segregation_shift_service: named IST zone in SQL (never a
# '+05:30' text offset), one grouped-by-shift query, day totals reconciled.
# """

# from datetime import date, datetime, timedelta, timezone
# from typing import Optional

# from sqlalchemy import func, select, case, distinct, literal, Date, Time
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.db.models.importOperation.import_release_report import IrrReport as Irr

# import logging

# logger = logging.getLogger(__name__)

# IST = timezone(timedelta(hours=5, minutes=30))
# IST_ZONE_NAME = "Asia/Kolkata"

# MORNING, AFTERNOON, EVENING = "morning", "afternoon", "evening"


# def _kg_to_mt(kg: Optional[float]) -> float:
#     return round(float(kg or 0) / 1000.0, 3)


# class ReleaseShiftService:
#     """Release (irr_report) metrics for a single IST operating day, split by shift."""

#     def __init__(self, session: AsyncSession):
#         self.session = session

#     # ── shift SQL helpers ────────────────────────────────────────────────────
#     #
#     # IMPORTANT STORAGE QUIRK:
#     #   gate_pass_issued_date  -> timestamptz (UTC), but only its DATE is
#     #                             reliable; its time-of-day is NOT (≈midnight).
#     #   gate_pass_issued_time  -> STRING, the true issue clock time already in
#     #                             IST, e.g. '07:20:00'.
#     #
#     # So the real IST issue moment = (date-field's IST date) + (time string).
#     # We build that combined IST timestamp in SQL and bucket on ITS hour.
#     # We must NOT extract the hour from gate_pass_issued_date alone — that
#     # would put nearly every GP in the Evening bucket.

#     def _safe_issued_time(self):
#         """
#         gate_pass_issued_time cast to TIME — but DEFENSIVELY.

#         The column is a free-text string and real data contains bad values
#         (e.g. a stray '30-Jun-26' date). A blind CAST(... AS TIME) makes
#         Postgres raise 'invalid input syntax for type time' and 500s the whole
#         request. So we only cast rows whose value matches a 24-hour HH:MM(:SS)
#         pattern; everything else falls back to midnight '00:00:00'.

#         Regex: ^([01]?\\d|2[0-3]):[0-5]\\d(:[0-5]\\d)?$
#           - hour 0-23 (one or two digits), minute 00-59, optional :seconds.
#         """
#         raw = func.trim(Irr.gate_pass_issued_time)
#         is_valid = raw.op("~")(literal(r"^([01]?[0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?$"))
#         safe_str = case((is_valid, raw), else_=literal("00:00:00"))
#         return func.cast(safe_str, Time)

#     def _issued_ist_ts(self):
#         """
#         Combined IST issue timestamp:
#             (gate_pass_issued_date AT TIME ZONE IST)::date  +  safe_issued_time

#         - AT TIME ZONE 'Asia/Kolkata' converts the UTC stamp to IST wall-clock,
#           then ::date takes the correct IST calendar date.
#         - gate_pass_issued_time is already IST; cast (defensively) to a time and
#           add it. Result is a naive IST timestamp (no tz math needed after).
#         """
#         ist_date = func.cast(
#             func.timezone(IST_ZONE_NAME, Irr.gate_pass_issued_date), Date
#         )
#         # date + time -> timestamp (Postgres allows date + time addition)
#         return ist_date + self._safe_issued_time()

#     def _shift_label(self):
#         hour = func.extract("hour", self._issued_ist_ts())
#         return case(
#             ((hour >= 6) & (hour < 14), literal(MORNING)),
#             ((hour >= 14) & (hour < 22), literal(AFTERNOON)),
#             else_=literal(EVENING),
#         )

#     def _day_window_ist(self, d: date) -> tuple[datetime, datetime]:
#         """Operating-day bounds as NAIVE IST timestamps [d 06:00, d+1 06:00).

#         We compare against the combined IST issue timestamp (which is naive
#         IST), so the bounds are naive IST too — no UTC conversion here.
#         """
#         start = datetime(d.year, d.month, d.day, 6, 0)
#         return start, start + timedelta(days=1)

#     # ── data-quality filter ───────────────────────────────────────────────────
#     _TIME_RE = r"^([01]?[0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?$"

#     def _usable_row(self):
#         """
#         A row is USABLE for the dashboard only if:
#           - gate_pass_issued_date is NOT NULL (we need the date), AND
#           - gate_pass_issued_time matches a valid 24-hour HH:MM(:SS) string.

#         Rows failing either test are corrupt (ingestion mapped the wrong column
#         in) and are EXCLUDED from all metrics. Use dropped_row_ids() to see
#         exactly which rows were skipped.
#         """
#         time_ok = func.trim(Irr.gate_pass_issued_time).op("~")(literal(self._TIME_RE))
#         return (Irr.gate_pass_issued_date.isnot(None)) & time_ok

#     async def dropped_row_ids(self, report_date: date) -> list[dict]:
#         """
#         Diagnostic: returns the rows that WOULD BE dropped for this report_date's
#         source data because of a null date or malformed time. Each entry carries
#         id + gate_pass_no + the offending values, so the caller can log exactly
#         what and how many were excluded.

#         Note: we cannot window these by the operating day (their timestamp is
#         unbuildable), so this returns ALL currently-corrupt rows. Filter/limit in
#         the caller if you only care about a date's upload.
#         """
#         bad = ~self._usable_row()
#         stmt = (
#             select(
#                 Irr.id,
#                 Irr.gate_pass_no,
#                 Irr.gate_pass_issued_date,
#                 Irr.gate_pass_issued_time,
#             )
#             .where(bad)
#         )
#         rows = (await self.session.execute(stmt)).all()
#         return [
#             {
#                 "id": r.id,
#                 "gate_pass_no": r.gate_pass_no,
#                 "gate_pass_issued_date": r.gate_pass_issued_date,
#                 "gate_pass_issued_time": r.gate_pass_issued_time,
#             }
#             for r in rows
#         ]

#     # ── main compute ─────────────────────────────────────────────────────────
#     async def compute(self, report_date: date) -> dict:
#         """
#         Returns a dict of per-shift metric dicts, each shaped
#         {morning, afternoon, evening, total}:

#             {
#               "gp_count":     {...},
#               "pcs":          {...},
#               "gross_mt":     {...},
#               "delivery_mt":  {...},   # same as gross_mt — Summary "d"
#               "online_pct":   {...},   # Online GP % per shift + day
#             }

#         The dashboard service maps these onto MetricRows.
#         """
#         day_start_ist, day_end_ist = self._day_window_ist(report_date)
#         # Only consider USABLE rows (valid date + valid time string). Corrupt
#         # rows (null date, or a non-time value like '26063598' / a date in the
#         # time column) are excluded so they neither crash the cast nor pollute
#         # totals. dropped_row_ids() reports exactly which rows were skipped.
#         usable = self._usable_row()
#         # Filter on the COMBINED IST issue timestamp (date field's IST date +
#         # time string), so the operating-day window uses the true issue time.
#         issued_ts = self._issued_ist_ts()
#         rng = usable & (issued_ts >= day_start_ist) & (issued_ts < day_end_ist)

#         # Log dropped rows for this build so bad data is visible in the logs.
#         dropped = await self.dropped_row_ids(report_date)
#         if dropped:
#             logger.warning(
#                 "ReleaseShiftService: dropped %d corrupt irr_report row(s): ids=%s",
#                 len(dropped),
#                 [d["id"] for d in dropped],
#             )

#         shift = self._shift_label()
#         online = func.upper(func.trim(Irr.online_counter)) == "ONLINE"

#         # One grouped pass: per shift, count GP / online GP, sum pcs & weight.
#         stmt = (
#             select(
#                 shift.label("shift"),
#                 func.count(distinct(Irr.gate_pass_no)).label("gp_count"),
#                 func.count(distinct(case((online, Irr.gate_pass_no)))).label("online_gp"),
#                 func.coalesce(func.sum(Irr.pcs), 0).label("pcs"),
#                 func.coalesce(func.sum(Irr.grg_wt), 0).label("gross_kg"),
#             )
#             .where(rng)
#             .group_by(shift)
#         )
#         rows = (await self.session.execute(stmt)).all()

#         def blank():
#             return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}

#         gp = blank()
#         online_gp = blank()
#         pcs = blank()
#         gross = blank()
#         for r in rows:
#             sh = r.shift
#             gp[sh] = float(r.gp_count)
#             online_gp[sh] = float(r.online_gp)
#             pcs[sh] = float(r.pcs)
#             gross[sh] = _kg_to_mt(r.gross_kg)

#         # Shift-summable metrics: sum across the three shifts.
#         for m in (gp, online_gp, pcs, gross):
#             m["total"] = round(m[MORNING] + m[AFTERNOON] + m[EVENING], 3)

#         # Day-wide DISTINCT GP count (a GP shouldn't span shifts — one issue
#         # time — but recompute distinct to be safe, matching segregation.)
#         day_gp = await self._day_distinct_gp(rng)
#         gp["total"] = float(day_gp)

#         # Online % per shift and for the day = online GP / total GP * 100.
#         def pct(part: dict, whole: dict) -> dict:
#             out = {}
#             for k in (MORNING, AFTERNOON, EVENING, "total"):
#                 out[k] = round(part[k] / whole[k] * 100.0, 1) if whole[k] else None
#             return out

#         online_pct = pct(online_gp, gp)

#         # Release Performance SLA (AF - AE <= 4h = success), per shift + day.
#         release_perf = await self._release_sla(rng)

#         return {
#             "gp_count": gp,
#             "pcs": pcs,
#             "gross_mt": gross,
#             "delivery_mt": gross,   # Summary "d" Delivery Gross Wgt = same sum
#             "online_pct": online_pct,
#             "release_perf": release_perf,   # {morning/afternoon/evening/total: {total,success,pct}}
#             # Data-quality: rows excluded as corrupt (null date / bad time).
#             # The caller can surface count / ids to the UI or an audit log.
#             "dropped_rows": dropped,
#             "dropped_count": len(dropped),
#         }

#     async def _release_sla(self, rng) -> dict:
#         """
#         Release Performance SLA per shift.

#         Rule (from spec):
#             AE = gate_pass_recd_date_time
#             AF = gate_pass_end_date_time
#             If (AF - AE) > 4 hours  -> FAILURE, else success.
#             Performance % = success GPs / total GPs (that have both AE and AF).

#         Rows missing AE or AF can't be evaluated, so they're excluded from BOTH
#         success and total (they neither pass nor fail) — same convention as the
#         segregation SLA with missing ATW/FCC.

#         Returns per-shift + day:
#             {morning|afternoon|evening|total: {"total": n, "success": n, "pct": float|None}}
#         """
#         ae = Irr.gate_pass_recd_date_time
#         af = Irr.gate_pass_end_date_time
#         shift = self._shift_label()

#         # elapsed hours = (AF - AE) in hours
#         elapsed_hours = func.extract("epoch", af - ae) / 3600.0
#         has_both = ae.isnot(None) & af.isnot(None)
#         is_success = case(((has_both) & (elapsed_hours <= 4.0), 1), else_=0)

#         stmt = (
#             select(
#                 shift.label("shift"),
#                 # total = GPs that CAN be evaluated (both AE & AF present)
#                 func.count(distinct(case((has_both, Irr.gate_pass_no)))).label("total"),
#                 func.coalesce(func.sum(is_success), 0).label("success"),
#             )
#             .where(rng)
#             .group_by(shift)
#         )
#         rows = (await self.session.execute(stmt)).all()

#         def entry(total, success):
#             return {"total": total, "success": success,
#                     "pct": round(success / total * 100.0, 1) if total else None}

#         out = {
#             MORNING: entry(0, 0), AFTERNOON: entry(0, 0), EVENING: entry(0, 0),
#         }
#         day_total = day_success = 0
#         for r in rows:
#             t, s = int(r.total), int(r.success)
#             out[r.shift] = entry(t, s)
#             day_total += t
#             day_success += s
#         out["total"] = entry(day_total, day_success)
#         return out

#     async def _day_distinct_gp(self, rng) -> int:
#         stmt = select(func.count(distinct(Irr.gate_pass_no))).where(rng)
#         return int((await self.session.execute(stmt)).scalar() or 0)
    







# # ========================================== Truck in out service =========================================
# """
# Truck IN/OUT (Truck Slot Mgt) metric computation — SHIFT-BASED.

# Source table: dr_imp_truck_in_out (DigitalReportImportTruckInOut).
# One row per Gate Pass truck movement.

# Shift bucketing:
#     A truck row is assigned to a shift by time_in (truck entry), converted to
#     IST — same operating-day windows as the rest of the dashboard.

# Metrics built here:
#     Gate Pass Count = COUNT(DISTINCT gp_no)
#     Piece Count     = SUM(pcs)
#     Truck Count     = distinct vehicle plates. truck_no may hold MULTIPLE plates
#                       separated by backslash (e.g. 'DL1LAC0107\\DL1LW9062'); we
#                       split and count unique plates across the day. 'BY HAND' is
#                       counted as its own "plate" (kept, not excluded).

#     Truck Out Performance SLA:
#         For each truck GP, match gp_no -> IrrReport.gate_pass_no to get the GP
#         end time (gate_pass_end_date_time). GP end is always BEFORE truck time_in,
#         so gap = time_in - gp_end is positive.
#           success            : matched, gp_end present, gap <= 4h
#           failure over_4h    : matched, gp_end present, gap  > 4h
#           failure null_gp_end: matched a release row but gp_end IS NULL
#           failure no_match   : gp_no not found in the release report at all
#         Unlike the other SLAs, unmatched rows COUNT AS FAILURE (not excluded),
#         per requirement. Total = all truck GPs in range.
#         Output includes per-reason counts AND the gp_no list for each failure.
# """

# from datetime import date, datetime, timedelta, timezone
# from typing import Optional

# from sqlalchemy import func, select, case, literal, String
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.db.models.digital_reports.import_dept.import_truck_in_out import DigitalReportImportTruckInOut as Truck
# from app.db.models.importOperation.import_release_report import IrrReport as Irr

# IST = timezone(timedelta(hours=5, minutes=30))
# IST_ZONE_NAME = "Asia/Kolkata"

# MORNING, AFTERNOON, EVENING = "morning", "afternoon", "evening"


# class TruckShiftService:
#     """Truck IN/OUT metrics for a single IST operating day, split by shift."""

#     def __init__(self, session: AsyncSession):
#         self.session = session

#     # ── shift helpers (bucket by time_in) ─────────────────────────────────────
#     def _time_in_ist(self):
#         """time_in as IST wall-clock (named zone — avoids the +05:30 sign trap)."""
#         return func.timezone(IST_ZONE_NAME, Truck.time_in)

#     def _shift_label(self):
#         hour = func.extract("hour", self._time_in_ist())
#         return case(
#             ((hour >= 6) & (hour < 14), literal(MORNING)),
#             ((hour >= 14) & (hour < 22), literal(AFTERNOON)),
#             else_=literal(EVENING),
#         )

#     def _day_window_utc(self, d: date) -> tuple[datetime, datetime]:
#         start_ist = datetime(d.year, d.month, d.day, 6, 0, tzinfo=IST)
#         end_ist = start_ist + timedelta(days=1)
#         return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)

#     # ── main compute ──────────────────────────────────────────────────────────
#     async def compute(self, report_date: date) -> dict:
#         """
#         Returns per-shift metric dicts + the Truck Out SLA breakdown:

#             {
#               "gp_count":    {morning/afternoon/evening/total},
#               "pcs":         {...},
#               "truck_count": {...},           # unique plates (backslash-split)
#               "truck_out_sla": {
#                   morning/afternoon/evening/total: {
#                       "total": n, "success": n, "pct": float|None,
#                       "fail_over_4h": n, "fail_null_gp_end": n, "fail_no_match": n,
#                   },
#                   "failures": [ {gp_no, reason}, ... ],   # every failing GP
#               },
#             }
#         """
#         day_start_utc, day_end_utc = self._day_window_utc(report_date)
#         rng = (Truck.time_in >= day_start_utc) & (Truck.time_in < day_end_utc)

#         gp_count, pcs = await self._counts(rng)
#         truck_count = await self._truck_counts(rng)
#         truck_out_sla = await self._truck_out_sla(rng)

#         return {
#             "gp_count": gp_count,
#             "pcs": pcs,
#             "truck_count": truck_count,
#             "truck_out_sla": truck_out_sla,
#         }

#     # ── GP count + pcs (one grouped pass) ─────────────────────────────────────
#     async def _counts(self, rng) -> tuple[dict, dict]:
#         shift = self._shift_label()
#         stmt = (
#             select(
#                 shift.label("shift"),
#                 func.count(func.distinct(Truck.gp_no)).label("gp_count"),
#                 func.coalesce(func.sum(Truck.pcs), 0).label("pcs"),
#             )
#             .where(rng)
#             .group_by(shift)
#         )
#         rows = (await self.session.execute(stmt)).all()

#         def blank():
#             return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}

#         gp, pcs = blank(), blank()
#         for r in rows:
#             gp[r.shift] = float(r.gp_count)
#             pcs[r.shift] = float(r.pcs)
#         for m in (gp, pcs):
#             m["total"] = m[MORNING] + m[AFTERNOON] + m[EVENING]
#         return gp, pcs

#     # ── truck count: split truck_no on backslash, count unique plates ─────────
#     async def _truck_counts(self, rng) -> dict:
#         """
#         truck_no may contain multiple plates joined by backslash. We pull
#         (shift, truck_no) and split/dedupe in Python — cleaner than SQL string
#         gymnastics and easy to adjust (e.g. if you later want to drop BY HAND).
#         """
#         shift = self._shift_label()
#         stmt = select(shift.label("shift"), Truck.truck_no).where(rng)
#         rows = (await self.session.execute(stmt)).all()

#         # collect a set of plates per shift so duplicates across rows don't count twice
#         plates = {MORNING: set(), AFTERNOON: set(), EVENING: set()}
#         for r in rows:
#             if not r.truck_no:
#                 continue
#             for plate in str(r.truck_no).split("\\"):
#                 p = plate.strip().upper()
#                 if p:
#                     plates[r.shift].add(p)

#         out = {sh: float(len(plates[sh])) for sh in (MORNING, AFTERNOON, EVENING)}
#         # Day total = unique plates across the whole day (union of the 3 shifts).
#         out["total"] = float(len(plates[MORNING] | plates[AFTERNOON] | plates[EVENING]))
#         return out

#     # ── Truck Out SLA (join to release for GP end) ────────────────────────────
#     async def _truck_out_sla(self, rng) -> dict:
#         """
#         LEFT JOIN truck rows to the release report on gp_no = gate_pass_no to get
#         gp_end. Then classify each truck GP in Python so we can attach a reason
#         and collect the failing gp_no list.
#         """
#         shift = self._shift_label()
#         # Truck.gp_no is an int; IrrReport.gate_pass_no is a string — cast for join.
#         gp_no_str = func.cast(Truck.gp_no, String)

#         stmt = (
#             select(
#                 Truck.gp_no.label("gp_no"),
#                 shift.label("shift"),
#                 Truck.time_in.label("time_in"),
#                 Irr.gate_pass_end_date_time.label("gp_end"),
#                 Irr.gate_pass_no.label("matched_gp"),
#             )
#             .select_from(Truck)
#             .join(Irr, Irr.gate_pass_no == gp_no_str, isouter=True)
#             .where(rng)
#         )
#         rows = (await self.session.execute(stmt)).all()

#         # Step 1: resolve one outcome per truck gp_no. A gp_no may join to
#         # multiple release rows; a success on ANY matched row wins, else keep
#         # the most informative failure (over_4h > null_gp_end > no_match).
#         # We also remember each gp's shift (from time_in, stable per gp).
#         FAIL_RANK = {"over_4h": 3, "null_gp_end": 2, "no_match": 1}
#         best: dict[int, dict] = {}   # gp_no -> {"outcome","shift"}

#         for r in rows:
#             gp = r.gp_no
#             if r.matched_gp is None:
#                 outcome = "no_match"
#             elif r.gp_end is None:
#                 outcome = "null_gp_end"
#             else:
#                 gap_h = (r.time_in - r.gp_end).total_seconds() / 3600.0 if r.time_in else None
#                 outcome = "success" if (gap_h is not None and gap_h <= 4.0) else "over_4h"

#             cur = best.get(gp)
#             if cur is None:
#                 best[gp] = {"outcome": outcome, "shift": r.shift}
#             elif cur["outcome"] != "success":
#                 # upgrade to success, or to a higher-ranked failure
#                 if outcome == "success":
#                     best[gp] = {"outcome": "success", "shift": r.shift}
#                 elif cur["outcome"] != "success" and FAIL_RANK.get(outcome, 0) > FAIL_RANK.get(cur["outcome"], 0):
#                     best[gp] = {"outcome": outcome, "shift": r.shift}

#         # Step 2: aggregate the resolved outcomes once.
#         def blank_entry():
#             return {"total": 0, "success": 0, "fail_over_4h": 0,
#                     "fail_null_gp_end": 0, "fail_no_match": 0}

#         agg = {MORNING: blank_entry(), AFTERNOON: blank_entry(), EVENING: blank_entry()}
#         failures: list[dict] = []
#         for gp, info in best.items():
#             sh, outcome = info["shift"], info["outcome"]
#             agg[sh]["total"] += 1
#             if outcome == "success":
#                 agg[sh]["success"] += 1
#             else:
#                 agg[sh][_fail_key(outcome)] += 1
#                 failures.append({"gp_no": gp, "reason": outcome})

#         # Step 3: pct + day rollup.
#         def pct(e):
#             return round(e["success"] / e["total"] * 100.0, 1) if e["total"] else None

#         out = {}
#         day = blank_entry()
#         for sh in (MORNING, AFTERNOON, EVENING):
#             e = agg[sh]
#             e["pct"] = pct(e)
#             out[sh] = e
#             for k in ("total", "success", "fail_over_4h", "fail_null_gp_end", "fail_no_match"):
#                 day[k] += e[k]
#         day["pct"] = pct(day)
#         out["total"] = day
#         out["failures"] = failures
#         return out


# def _fail_key(reason: str) -> str:
#     return {"over_4h": "fail_over_4h",
#             "null_gp_end": "fail_null_gp_end",
#             "no_match": "fail_no_match"}[reason]
















# """
# Pick Order (Examination / P.2) metric computation — SHIFT-BASED.

# Source table: dr_imp_pick_order (DigitalReportImportPickOrder).

# Metrics (from the CEO spec, P.2 Examination):
#     a — No. of Pick Order / AWB Number = COUNT(DISTINCT awb_no)
#     b — No. of Pcs                     = SUM(pcs_for_examination)
#     (c On Floor Productivity + c.1 manpower -> pending, Roster)

# ────────────────────────────────────────────────────────────────────────────
# SHIFT BUCKETING DATETIME  — EASY TO CHANGE
# ────────────────────────────────────────────────────────────────────────────
# Which timestamp decides a pick-order row's shift is controlled by ONE setting:

#     _SHIFT_BUCKET_COLUMN

# Currently it buckets by POE start time (poe_start_datetime). If you later want a
# different basis (e.g. POE end, RFE, or FFE), change just that one line to the
# matching model column — nothing else in this file needs to change.

# Available columns (all stored UTC):
#     PickOrder.rfe_datetime
#     PickOrder.ffe_datetime
#     PickOrder.poe_start_datetime   <-- current
#     PickOrder.poe_end_datetime
# """


# from app.db.models.digital_reports.import_dept.import_pick_order import DigitalReportImportPickOrder as PickOrder


# # ── THE ONE SETTING TO CHANGE THE SHIFT-BUCKETING BASIS ─────────────────────
# # Swap this to poe_end_datetime / rfe_datetime / ffe_datetime if needed.
# _SHIFT_BUCKET_COLUMN = PickOrder.poe_start_datetime


# class PickOrderShiftService:
#     """Examination (pick order) metrics for a single IST day, split by shift."""

#     def __init__(self, session: AsyncSession):
#         self.session = session

#     # ── shift helpers (bucket by the configured column) ───────────────────────
#     def _bucket_ist(self):
#         """The bucketing timestamp expressed in IST wall-clock (named zone)."""
#         return func.timezone(IST_ZONE_NAME, _SHIFT_BUCKET_COLUMN)

#     def _shift_label(self):
#         hour = func.extract("hour", self._bucket_ist())
#         return case(
#             ((hour >= 6) & (hour < 14), literal(MORNING)),
#             ((hour >= 14) & (hour < 22), literal(AFTERNOON)),
#             else_=literal(EVENING),
#         )

#     def _day_window_utc(self, d: date) -> tuple[datetime, datetime]:
#         start_ist = datetime(d.year, d.month, d.day, 6, 0, tzinfo=IST)
#         end_ist = start_ist + timedelta(days=1)
#         return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)

#     async def compute(self, report_date: date) -> dict:
#         """
#         Returns per-shift metric dicts {morning/afternoon/evening/total}:
#             {
#               "awb_count": {...},   # distinct AWB numbers
#               "pcs":       {...},   # sum of pcs_for_examination
#             }

#         Note: pick-order rows are ALSO tagged with a stored `report_date` (the
#         upload key). Here we bucket by the event timestamp's operating day, which
#         is the dashboard-consistent behaviour. If instead you want to select rows
#         purely by the stored report_date column, filter on that in _both queries_
#         — kept as a comment below.
#         """
#         day_start_utc, day_end_utc = self._day_window_utc(report_date)
#         col = _SHIFT_BUCKET_COLUMN
#         # Bucket by the event timestamp's operating day.
#         rng = (col.isnot(None)) & (col >= day_start_utc) & (col < day_end_utc)
#         # Alternative (select by stored upload key instead):
#         # rng = (PickOrder.report_date == report_date) & (col.isnot(None))

#         shift = self._shift_label()
#         stmt = (
#             select(
#                 shift.label("shift"),
#                 func.count(distinct(PickOrder.awb_no)).label("awb_count"),
#                 func.coalesce(func.sum(PickOrder.pcs_for_examination), 0).label("pcs"),
#             )
#             .where(rng)
#             .group_by(shift)
#         )
#         rows = (await self.session.execute(stmt)).all()

#         def blank():
#             return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}

#         awb, pcs = blank(), blank()
#         for r in rows:
#             awb[r.shift] = float(r.awb_count)
#             pcs[r.shift] = float(r.pcs)
#         pcs["total"] = pcs[MORNING] + pcs[AFTERNOON] + pcs[EVENING]

#         # AWB count total must be day-wide distinct (an AWB could appear in two
#         # shifts), so recompute distinct over the whole day rather than summing.
#         day_awb = await self._day_distinct_awb(rng)
#         awb["total"] = float(day_awb)

#         return {"awb_count": awb, "pcs": pcs}

#     async def _day_distinct_awb(self, rng) -> int:
#         stmt = select(func.count(distinct(PickOrder.awb_no))).where(rng)
#         return int((await self.session.execute(stmt)).scalar() or 0)





























































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
from app.services.digital_reports.import_dpt.operation_productivity_report.common_airline_utils import resolve_airline
from app.schemas.digital_reports.import_dept.operation_productivity_schema import (
    ImportProductivityDashboardResponse, ImportProductivityDashboardMeta,
    MetricSection, MetricRow, ShiftValues, ShiftWindow,
    MetricUnit, MetricSource,
)


IST = timezone(timedelta(hours=5, minutes=30))
IST_ZONE_NAME = "Asia/Kolkata"

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


def _merge_calendar_totals(op_dict: dict, cal_dict: dict) -> None:
    """
    Copy each metric's calendar-day total into the operating-day dict under a
    'calendar_total' key. `op_dict`/`cal_dict` are {metric: {shift..., 'total'}}
    shaped (e.g. from _segregation_totals). Only the 'total' of the calendar
    pass is used (calendar total is a single number, no shift split).
    """
    for metric, cal_vals in cal_dict.items():
        if isinstance(cal_vals, dict) and metric in op_dict:
            op_dict[metric]["calendar_total"] = cal_vals.get("total")


def _merge_calendar_group(op_group: dict, cal_group: dict) -> None:
    """
    Same as above but for the category-split groups (total/passenger/freighter),
    each of which is a {shift..., 'total'} dict. Copies the calendar 'total'
    into each subgroup's 'calendar_total'.
    """
    for sub in ("total", "passenger", "freighter"):
        if sub in op_group and sub in cal_group:
            op_group[sub]["calendar_total"] = cal_group[sub].get("total")


class ProductivityImportShiftService:
    """Computes productivity dashboard metrics for a single IST date, split by shift."""

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

        Uses the NAMED zone 'Asia/Kolkata'. Do NOT use a text offset like
        '+05:30' here: Postgres interprets that as a POSIX-style zone where the
        sign is inverted, so it subtracts 5:30 instead of adding it and every
        row lands in the wrong shift.
        """
        return func.timezone(IST_ZONE_NAME, Flight.flt_com_dat_tim)

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

    def _calendar_window_utc(self, d: date) -> tuple[datetime, datetime]:
        """Strict calendar-day bounds in UTC: [date 00:00 IST, date+1 00:00 IST).

        This is the midnight-to-midnight window for the extra `calendar_total`
        column. It differs from the operating day by the two 06:00 edge-slices.
        """
        start_ist = datetime(d.year, d.month, d.day, 0, 0, tzinfo=IST)
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
        flight_cats = await self._flight_count_by_category(rng)
        awb_cats = await self._awb_metrics_by_category(rng)

        # ── Calendar-day pass ────────────────────────────────────────────────
        # Same aggregates over the strict calendar window (00:00->24:00 IST),
        # used to fill each metric's `calendar_total`. Reuses the exact same
        # queries, only the date range differs.
        cal_start_utc, cal_end_utc = self._calendar_window_utc(report_date)
        cal_rng = (
            (Flight.flt_com_dat_tim >= cal_start_utc)
            & (Flight.flt_com_dat_tim < cal_end_utc)
        )
        cal_totals = await self._segregation_totals(cal_rng)
        cal_flight_cats = await self._flight_count_by_category(cal_rng)
        cal_awb_cats = await self._awb_metrics_by_category(cal_rng)
        cal_seg_perf = await self._segregation_sla(cal_rng)

        # Merge calendar-day totals into the operating-day dicts as calendar_total.
        _merge_calendar_totals(totals, cal_totals)
        _merge_calendar_group(flight_cats, cal_flight_cats)
        for m in ("mawb", "hawb", "pcs", "gross_mt", "chg_mt"):
            _merge_calendar_group(awb_cats[m], cal_awb_cats[m])
        # Segregation SLA calendar %.
        seg_perf["total"]["calendar_pct"] = cal_seg_perf["total"]["pct"]

        # Release (irr_report) metrics — computed by a separate service that
        # buckets by gate_pass_issued_date. Returns per-shift metric dicts.
        release = await ReleaseShiftService(self.session).compute(report_date)
        # Truck IN/OUT metrics — buckets by time_in; SLA joins to release.
        truck = await TruckShiftService(self.session).compute(report_date)
        # Pick Order (Examination) metrics — buckets by POE start (configurable).
        pick_order = await PickOrderShiftService(self.session).compute(report_date)

        sections = [
            self._overview_section(totals, release),
            self._segregation_section(totals, flight_cats, awb_cats),
            self._examination_section(pick_order),
            self._release_section(release, truck),
            self._sla_section(seg_perf, release, truck),
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
                # Same DEL / I2I / I2D split, but on CHARGE weight (for Summary "b").
                func.coalesce(func.sum(
                    case((dest == LOCAL_DEST, Awb.chg_wgt), else_=0)), 0).label("local_chg_kg"),
                func.coalesce(func.sum(
                    case((dest.in_(I2D_DESTS), Awb.chg_wgt), else_=0)), 0).label("i2d_chg_kg"),
                func.coalesce(func.sum(
                    case((~dest.in_(I2D_DESTS | {LOCAL_DEST}), Awb.chg_wgt), else_=0)), 0).label("i2i_chg_kg"),
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
            "local_chg_mt": blank(), "i2d_chg_mt": blank(), "i2i_chg_mt": blank(),
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
            out["local_chg_mt"][sh] = _kg_to_mt(r.local_chg_kg)
            out["i2d_chg_mt"][sh] = _kg_to_mt(r.i2d_chg_kg)
            out["i2i_chg_mt"][sh] = _kg_to_mt(r.i2i_chg_kg)

        # Totals. Weight/pcs sum across shifts; distinct counts must be
        # recomputed day-wide (a flight/AWB could appear in two shifts).
        for key in ("gross_mt", "chg_mt", "pcs", "local_mt", "i2d_mt", "i2i_mt",
                    "local_chg_mt", "i2d_chg_mt", "i2i_chg_mt"):
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

    async def _flight_count_by_category(self, rng) -> dict:
        """
        Distinct flight count per shift, split into Passenger (PAX) and
        Freighter (CAO) using the shared airline master.

        A flight is one physical departure; its PAX/CAO category is stable
        regardless of per-AWB dest, so we classify each distinct flight once
        by its flight_no. We pull (flight_no, dest, shift) for the distinct
        flights and count per shift × category in Python — mirroring how the
        existing segregation report classifies.

        Returns:
            {
              "total":      {morning, afternoon, evening, total},   # both cats
              "passenger":  {...same shape...},
              "freighter":  {...same shape...},
            }
        """
        shift = self._shift_label()
        stmt = (
            select(
                Flight.id,
                Flight.flight_no,
                Flight.dest,
                shift.label("shift"),
            )
            .select_from(Flight)
            .where(rng)
            .distinct()
        )
        rows = (await self.session.execute(stmt)).all()

        def blank_counts():
            return {MORNING: 0, AFTERNOON: 0, EVENING: 0, "total": 0}

        out = {
            "total": blank_counts(),
            "passenger": blank_counts(),
            "freighter": blank_counts(),
        }
        # A flight id could in theory appear under one shift only (its FCC is a
        # single instant), so counting rows == counting distinct flights here.
        for r in rows:
            info = resolve_airline(r.flight_no or "", r.dest or "")
            bucket = "passenger" if info.category == "PAX" else "freighter"
            sh = r.shift
            out[bucket][sh] += 1
            out["total"][sh] += 1

        for grp in ("total", "passenger", "freighter"):
            out[grp]["total"] = out[grp][MORNING] + out[grp][AFTERNOON] + out[grp][EVENING]
        return out

    async def _awb_metrics_by_category(self, rng) -> dict:
        """
        AWB-level metrics (MAWB / HAWB / Piece / Gross / Charge) per shift,
        split into Passenger (PAX) and Freighter (CAO).

        WHY THIS SHAPE:
        The PAX/CAO category is decided by the airline master via
        resolve_airline(flight_no, dest) — that is Python logic, so the split
        cannot be done purely in SQL. To stay efficient we do as much as
        possible in ONE SQL pass, then fold flight_no -> category in Python.

        SQL step (one query):
          Group by (shift, flight_no, awb_no) and aggregate the AWB's numbers.
          Grouping down to awb_no means each MAWB is one row per shift/flight —
          so counting rows gives the distinct MAWB count, and SUM(no_of_houses)
          gives HAWB, SUM(pcs)/SUM(weights) give the rest. (An AWB that was
          split into several DB rows under the same flight is collapsed here.)

        Python step:
          For each (shift, flight_no, awb_no) row, resolve the flight to
          PAX/CAO once and add its numbers into that bucket. flight_no is all
          we need for the category (dest only matters for the Air-India
          Delhi/TP split, which this dashboard does not use).

        Returns a dict keyed by metric, each holding total/passenger/freighter,
        each of those a {morning, afternoon, evening, total} dict:
            {
              "mawb":  {"total": {...}, "passenger": {...}, "freighter": {...}},
              "hawb":  {...},
              "pcs":   {...},
              "gross_mt": {...},   # already converted to MT
              "chg_mt":   {...},   # already converted to MT
            }
        """
        shift = self._shift_label()

        # ── SQL: one row per (shift, flight_no, awb_no) with that AWB's totals ──
        stmt = (
            select(
                shift.label("shift"),
                Flight.flight_no.label("flight_no"),
                Flight.dest.label("dest"),
                Awb.awb_no.label("awb_no"),
                func.coalesce(func.sum(Awb.pcs), 0).label("pcs"),
                func.coalesce(func.sum(Awb.gross_wgt), 0).label("gross_kg"),
                func.coalesce(func.sum(Awb.chg_wgt), 0).label("chg_kg"),
                func.coalesce(func.sum(Awb.no_of_houses), 0).label("houses"),
            )
            .select_from(Awb)
            .join(Flight, Awb.flight_id == Flight.id)
            .where(rng)
            .group_by(shift, Flight.flight_no, Flight.dest, Awb.awb_no)
        )
        rows = (await self.session.execute(stmt)).all()

        # ── prepare zeroed accumulators ──
        def blank():
            return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}

        def blank_group():
            return {"total": blank(), "passenger": blank(), "freighter": blank()}

        metrics = {
            "mawb": blank_group(),   # count of AWB rows
            "hawb": blank_group(),   # SUM(no_of_houses)
            "pcs": blank_group(),    # SUM(pcs)
            "gross_kg": blank_group(),  # SUM(gross) — converted to MT at the end
            "chg_kg": blank_group(),    # SUM(chg)   — converted to MT at the end
        }

        # ── Python: fold each AWB row into total + its PAX/CAO bucket ──
        for r in rows:
            info = resolve_airline(r.flight_no or "", r.dest or "")
            cat = "passenger" if info.category == "PAX" else "freighter"
            sh = r.shift
            for grp in ("total", cat):
                metrics["mawb"][grp][sh] += 1                    # one row = one MAWB
                metrics["hawb"][grp][sh] += float(r.houses or 0)
                metrics["pcs"][grp][sh] += float(r.pcs or 0)
                metrics["gross_kg"][grp][sh] += float(r.gross_kg or 0)
                metrics["chg_kg"][grp][sh] += float(r.chg_kg or 0)

        # ── shift totals, and kg -> MT for the weight metrics ──
        for key, grp_dict in metrics.items():
            for grp in ("total", "passenger", "freighter"):
                d = grp_dict[grp]
                d["total"] = d[MORNING] + d[AFTERNOON] + d[EVENING]

        # Convert the two weight metrics from kg to MT (3dp), keep counts as-is.
        def to_mt_group(grp_dict):
            out = {}
            for grp in ("total", "passenger", "freighter"):
                out[grp] = {k: _kg_to_mt(v) for k, v in grp_dict[grp].items()}
            return out

        return {
            "mawb": metrics["mawb"],
            "hawb": metrics["hawb"],
            "pcs": metrics["pcs"],
            "gross_mt": to_mt_group(metrics["gross_kg"]),
            "chg_mt": to_mt_group(metrics["chg_kg"]),
        }


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
            calendar_total=d.get("calendar_total"),
        )

    def _overview_section(self, t: dict, release: dict) -> MetricSection:
        sys, man = MetricSource.system, MetricSource.manual
        seg = "Segregation Report"

        # a — Gross Wgt (MT), collapsible into DEL / I2I / I2D
        gross_row = MetricRow(
            key="sum_gross_wgt", s_no="a", description="Gross Wgt (MT)",
            values=self._sv(t["gross_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg,
            children=[
                MetricRow(key="sum_gross_del", s_no="a.1", description="Import - Delhi",
                          values=self._sv(t["local_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
                MetricRow(key="sum_gross_i2i", s_no="a.2", description="Import TP - I2I",
                          values=self._sv(t["i2i_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
                MetricRow(key="sum_gross_i2d", s_no="a.3", description="Import TP - I2D",
                          values=self._sv(t["i2d_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
            ],
        )

        # b — Charge Wgt (MT), collapsible into DEL / I2I / I2D (charge weight)
        chg_row = MetricRow(
            key="sum_chg_wgt", s_no="b", description="Charge Wgt (MT)",
            values=self._sv(t["chg_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg,
            children=[
                MetricRow(key="sum_chg_del", s_no="b.1", description="Import - Delhi",
                          values=self._sv(t["local_chg_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
                MetricRow(key="sum_chg_i2i", s_no="b.2", description="Import TP - I2I",
                          values=self._sv(t["i2i_chg_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
                MetricRow(key="sum_chg_i2d", s_no="b.3", description="Import TP - I2D",
                          values=self._sv(t["i2d_chg_mt"]), unit=MetricUnit.mt, source=sys, source_report=seg),
            ],
        )

        # c — Gross vs Charge Weight (%): charge / gross * 100, per shift.
        # (Frontend colours it: <110% red, >=110% green.)
        def _pct_of(chg: dict, gross: dict) -> ShiftValues:
            def one(sh):
                g = gross[sh]
                return round(chg[sh] / g * 100.0, 1) if g else None
            # calendar %: charge_cal / gross_cal * 100
            gc = gross.get("calendar_total")
            cc = chg.get("calendar_total")
            cal = round(cc / gc * 100.0, 1) if (gc and cc is not None) else None
            return ShiftValues(
                morning=one(MORNING), afternoon=one(AFTERNOON),
                evening=one(EVENING), total=one("total"),
                calendar_total=cal,
            )

        gross_vs_chg = MetricRow(
            key="sum_gross_vs_chg", s_no="c", description="Gross Weight vs Charge Weight (%)",
            values=_pct_of(t["chg_mt"], t["gross_mt"]),
            unit=MetricUnit.percent, source=sys, source_report=seg,
            note="Charge ÷ Gross; <110% red, ≥110% green",
        )

        rows = [
            gross_row,
            chg_row,
            gross_vs_chg,
            MetricRow(key="sum_delivery_gross", s_no="d", description="Delivery Gross Wgt (MT)",
                      values=self._sv(release["delivery_mt"]), unit=MetricUnit.mt,
                      source=sys, source_report="Release Report"),
            MetricRow(key="sum_prod_delivery", s_no="e", description="Productivity on Delivery (Grs MT/Month)",
                      pending=True, unit=MetricUnit.productivity, source=sys, source_report="Release Report/Roster",
                      note="Total GP Gross MT / On Role WHA * day count",
                      children=[
                          MetricRow(key="sum_prod_delivery_onrole_wha", s_no="e.1",
                                    description="On Role WHA Count", pending=True,
                                    unit=MetricUnit.count, source=sys, source_report="Roster"),
                          MetricRow(key="sum_prod_delivery_onrole_prod", s_no="e.2",
                                    description="On Role Productivity", pending=True,
                                    unit=MetricUnit.productivity, source=sys, source_report="Roster"),
                          MetricRow(key="sum_prod_delivery_onfloor_wha", s_no="e.3",
                                    description="On Floor WHA Count", pending=True,
                                    unit=MetricUnit.count, source=sys, source_report="Roster"),
                          MetricRow(key="sum_prod_delivery_onfloor_prod", s_no="e.4",
                                    description="On Floor Productivity", pending=True,
                                    unit=MetricUnit.productivity, source=sys, source_report="Roster"),
                      ]),
            MetricRow(key="sum_prod_segregation", s_no="f", description="Productivity on Segregation (Grs MT/Month)",
                      pending=True, unit=MetricUnit.productivity, source=sys, source_report="Segregation Report/Roster",
                      note="Total Seg Gross MT / On Role WHA * day count",
                      children=[
                          MetricRow(key="sum_prod_seg_onrole_wha", s_no="f.1",
                                    description="On Role WHA Count", pending=True,
                                    unit=MetricUnit.count, source=sys, source_report="Roster"),
                          MetricRow(key="sum_prod_seg_onrole_prod", s_no="f.2",
                                    description="On Role Productivity", pending=True,
                                    unit=MetricUnit.productivity, source=sys, source_report="Roster"),
                          MetricRow(key="sum_prod_seg_onfloor_wha", s_no="f.3",
                                    description="On Floor WHA Count", pending=True,
                                    unit=MetricUnit.count, source=sys, source_report="Roster"),
                          MetricRow(key="sum_prod_seg_onfloor_prod", s_no="f.4",
                                    description="On Floor Productivity", pending=True,
                                    unit=MetricUnit.productivity, source=sys, source_report="Roster"),
                      ]),
        ]
        return MetricSection(key="summary", title="Summary", rows=rows)

    def _segregation_section(self, t: dict, flight_cats: dict, awb_cats: dict) -> MetricSection:
        sys, man = MetricSource.system, MetricSource.manual
        seg = "Segregation Report"

        # Helper: turn a {morning,afternoon,evening,total} dict into ShiftValues.
        def _counts_sv(d: dict) -> ShiftValues:
            ct = d.get("calendar_total")
            return ShiftValues(
                morning=float(d[MORNING]), afternoon=float(d[AFTERNOON]),
                evening=float(d[EVENING]), total=float(d["total"]),
                calendar_total=float(ct) if ct is not None else None,
            )

        # Helper: build a "parent + Passenger/Freighter children" row for a
        # metric that lives in awb_cats (mawb/hawb/pcs/gross_mt/chg_mt) or
        # flight_cats. `group` is the awb_cats key; `unit` its unit.
        def _split_row(key, s_no, desc, group: dict, unit) -> MetricRow:
            return MetricRow(
                key=key, s_no=s_no, description=desc,
                values=_counts_sv(group["total"]), unit=unit, source=sys, source_report=seg,
                children=[
                    MetricRow(key=f"{key}_pax", s_no=f"{s_no}.1",
                              description=f"Passenger {desc}",
                              values=_counts_sv(group["passenger"]),
                              unit=unit, source=sys, source_report=seg),
                    MetricRow(key=f"{key}_cao", s_no=f"{s_no}.2",
                              description=f"Freighters {desc}",
                              values=_counts_sv(group["freighter"]),
                              unit=unit, source=sys, source_report=seg),
                ],
            )

        # a — Flight Count (from flight_cats: distinct flights per category)
        flight_count_row = MetricRow(
            key="seg_flight_count", s_no="a", description="Flight Count",
            values=_counts_sv(flight_cats["total"]),
            unit=MetricUnit.count, source=sys, source_report=seg,
            children=[
                MetricRow(key="seg_flight_count_pax", s_no="a.1",
                          description="Passenger Flights Count",
                          values=_counts_sv(flight_cats["passenger"]),
                          unit=MetricUnit.count, source=sys, source_report=seg),
                MetricRow(key="seg_flight_count_cao", s_no="a.2",
                          description="Freighters Count",
                          values=_counts_sv(flight_cats["freighter"]),
                          unit=MetricUnit.count, source=sys, source_report=seg),
            ],
        )

        rows = [
            flight_count_row,
            # b — MAWB Count (distinct AWB per category)
            _split_row("seg_mawb_count", "b", "MAWB Count", awb_cats["mawb"], MetricUnit.count),
            # c — HAWB Count (SUM of no_of_houses per category)
            _split_row("seg_hawb_count", "c", "HAWB Count", awb_cats["hawb"], MetricUnit.count),
            # d — Piece Count
            _split_row("seg_piece_count", "d", "Piece Count", awb_cats["pcs"], MetricUnit.count),
            # e — Gross Weight (MT)
            _split_row("seg_gross_wgt", "e", "Gross Weight (MT)", awb_cats["gross_mt"], MetricUnit.mt),
            # f — Charge Weight (MT)
            _split_row("seg_chg_wgt", "f", "Charge Weight (MT)", awb_cats["chg_mt"], MetricUnit.mt),
            # g — On Floor Productivity (no children; pending Roster)
            MetricRow(key="seg_onfloor_productivity", s_no="g", description="On Floor Productivity",
                      pending=True, unit=MetricUnit.productivity, source=man, source_report="Roster",
                      note="(Gross MT / On Floor WHA) * 30",
                      children=[
                          MetricRow(key="seg_onfloor_manpower", s_no="g.1",
                                    description="On Floor Manpower (WHA)", pending=True,
                                    unit=MetricUnit.count, source=man, source_report="Roster",
                                    note="Needs Roster"),
                      ]),
        ]
        return MetricSection(key="segregation", title="P.1  Segregation", rows=rows)

    def _examination_section(self, pick_order: dict) -> MetricSection:
        """P.2 Examination — from the pick order report."""
        sys, man = MetricSource.system, MetricSource.manual
        po = "Pick Order Report"
        rows = [
            MetricRow(key="exam_awb_count", s_no="a",
                      description="No. of Pick Order / AWB Number",
                      values=self._sv(pick_order["awb_count"]), unit=MetricUnit.count,
                      source=sys, source_report=po),
            MetricRow(key="exam_pcs", s_no="b", description="No. of Pcs",
                      values=self._sv(pick_order["pcs"]), unit=MetricUnit.count,
                      source=sys, source_report=po),
            MetricRow(key="exam_onfloor_productivity", s_no="c",
                      description="On Floor Productivity (Pcs/WHA)", pending=True,
                      unit=MetricUnit.productivity, source=man, source_report="Roster",
                      note="(No. of Pcs / On Floor WHA) * days in month",
                      children=[
                          MetricRow(key="exam_onfloor_manpower", s_no="c.1",
                                    description="On Floor Manpower (WHA)", pending=True,
                                    unit=MetricUnit.count, source=man, source_report="Roster"),
                      ]),
        ]
        return MetricSection(key="examination", title="P.2  Examination", rows=rows)

    def _release_section(self, release: dict, truck: dict) -> MetricSection:
        """P.3 Release Report — from irr_report (gate_pass_issued_date shifts).
        Truck Count comes from the truck IN/OUT report."""
        sys, man = MetricSource.system, MetricSource.manual
        rel = "Release Report"
        rows = [
            MetricRow(key="rel_gp_count", s_no="a", description="Gate Pass Count",
                      values=self._sv(release["gp_count"]), unit=MetricUnit.count,
                      source=sys, source_report=rel),
            MetricRow(key="rel_pcs", s_no="b", description="Piece Count",
                      values=self._sv(release["pcs"]), unit=MetricUnit.count,
                      source=sys, source_report=rel),
            MetricRow(key="rel_gross_wgt", s_no="c", description="Gross Weight (MT)",
                      values=self._sv(release["gross_mt"]), unit=MetricUnit.mt,
                      source=sys, source_report=rel),
            # d — Truck Count (unique plates) from the truck IN/OUT report.
            MetricRow(key="rel_truck_count", s_no="d", description="Truck Count",
                      values=self._sv(truck["truck_count"]), unit=MetricUnit.count,
                      source=sys, source_report="Import Truck Slot Mgt"),
            # f — On Floor Productivity (Roster) pending.
            MetricRow(key="rel_onfloor_productivity", s_no="f", description="On Floor Productivity",
                      pending=True, unit=MetricUnit.productivity, source=man, source_report="Roster",
                      note="(Gross MT / On Floor WHA) * days in month",
                      children=[
                          MetricRow(key="rel_onfloor_manpower", s_no="f.1",
                                    description="On Floor Manpower (WHA)", pending=True,
                                    unit=MetricUnit.count, source=man, source_report="Roster"),
                      ]),
        ]
        return MetricSection(key="release", title="P.3  Release Report", rows=rows)

    def _sla_section(self, seg: dict, release: dict, truck: dict) -> MetricSection:
        sys = MetricSource.system
        vals = ShiftValues(
            morning=seg[MORNING]["pct"], afternoon=seg[AFTERNOON]["pct"],
            evening=seg[EVENING]["pct"], total=seg["total"]["pct"],
            calendar_total=seg["total"].get("calendar_pct"),
        )
        online = release["online_pct"]
        online_vals = ShiftValues(
            morning=online[MORNING], afternoon=online[AFTERNOON],
            evening=online[EVENING], total=online["total"],
            calendar_total=online.get("calendar_total"),
        )
        rows = [
            MetricRow(key="sla_seg_performance", s_no="1", description="Segregation Performance",
                      values=vals, pending=seg["total"]["pct"] is None,
                      unit=MetricUnit.percent, source=sys, source_report="Segregation Report",
                      note=f"{seg['total']['success']}/{seg['total']['total']} flights within SLA (day)"),
            # Release Performance SLA — AF-AE > 4h = failure (from irr_report).
            MetricRow(key="sla_release_performance", s_no="2", description="Release Performance",
                      values=ShiftValues(
                          morning=release["release_perf"][MORNING]["pct"],
                          afternoon=release["release_perf"][AFTERNOON]["pct"],
                          evening=release["release_perf"][EVENING]["pct"],
                          total=release["release_perf"]["total"]["pct"],
                          calendar_total=release["release_perf"]["total"].get("calendar_pct"),
                      ),
                      pending=release["release_perf"]["total"]["pct"] is None,
                      unit=MetricUnit.percent, source=sys, source_report="Release Report",
                      note=f"{release['release_perf']['total']['success']}/"
                           f"{release['release_perf']['total']['total']} GP within 4h SLA (day)"),
            MetricRow(key="sla_truckout_performance", s_no="3", description="Truck Out Performance",
                      values=ShiftValues(
                          morning=truck["truck_out_sla"][MORNING]["pct"],
                          afternoon=truck["truck_out_sla"][AFTERNOON]["pct"],
                          evening=truck["truck_out_sla"][EVENING]["pct"],
                          total=truck["truck_out_sla"]["total"]["pct"],
                          calendar_total=truck["truck_out_sla"]["total"].get("calendar_pct"),
                      ),
                      pending=truck["truck_out_sla"]["total"]["pct"] is None,
                      unit=MetricUnit.percent, source=sys, source_report="Import Truck Slot Mgt",
                      note=f"{truck['truck_out_sla']['total']['success']}/"
                           f"{truck['truck_out_sla']['total']['total']} trucks within 4h "
                           f"(fail: {truck['truck_out_sla']['total']['fail_over_4h']} over-4h, "
                           f"{truck['truck_out_sla']['total']['fail_null_gp_end']} no-GP-end, "
                           f"{truck['truck_out_sla']['total']['fail_no_match']} unmatched)"),
            MetricRow(key="sla_online_gp", s_no="4", description="Online Gate Pass",
                      values=online_vals,
                      pending=online["total"] is None,
                      unit=MetricUnit.percent, source=sys, source_report="Release Report",
                      note="Online GP vs total GP"),
        ]
        return MetricSection(key="sla", title="P.5  SLA", rows=rows)
    



# =========================================================

"""
Release (IRR) metric computation — SHIFT-BASED.

Source table: irr_report (IrrReport). One row per Gate Pass.

Shift bucketing:
    A Release row is assigned to a shift by gate_pass_issued_date (the GP issue
    time), converted to IST — same operating-day windows as the segregation
    dashboard (Morning 06-14, Afternoon 14-22, Evening 22-06 next day).

Metrics built here (all confirmed):
    Gate Pass Count   = COUNT(DISTINCT gate_pass_no)
    Piece Count       = SUM(pcs)
    Gross Weight (MT) = SUM(grg_wt) / 1000
    Online Gate Pass %= GPs with online_counter ILIKE 'Online' / total GP * 100

Left pending (rules not finalised):
    Release Performance SLA  — needs the two datetime columns confirmed
                               (spec: AF - AE > 4h => failure).
    Truck Count              — sourced from Import Truck Slot Mgt, not irr_report.

Design mirrors segregation_shift_service: named IST zone in SQL (never a
'+05:30' text offset), one grouped-by-shift query, day totals reconciled.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, case, distinct, literal, Date, Time
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.importOperation.import_release_report import IrrReport as Irr

import logging

logger = logging.getLogger(__name__)

IST = timezone(timedelta(hours=5, minutes=30))
IST_ZONE_NAME = "Asia/Kolkata"

# MORNING, AFTERNOON, EVENING = "morning", "afternoon", "evening"


def _kg_to_mt(kg: Optional[float]) -> float:
    return round(float(kg or 0) / 1000.0, 3)


class ReleaseShiftService:
    """Release (irr_report) metrics for a single IST operating day, split by shift."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── shift SQL helpers ────────────────────────────────────────────────────
    #
    # IMPORTANT STORAGE QUIRK:
    #   gate_pass_issued_date  -> timestamptz (UTC), but only its DATE is
    #                             reliable; its time-of-day is NOT (≈midnight).
    #   gate_pass_issued_time  -> STRING, the true issue clock time already in
    #                             IST, e.g. '07:20:00'.
    #
    # So the real IST issue moment = (date-field's IST date) + (time string).
    # We build that combined IST timestamp in SQL and bucket on ITS hour.
    # We must NOT extract the hour from gate_pass_issued_date alone — that
    # would put nearly every GP in the Evening bucket.

    def _safe_issued_time(self):
        """
        gate_pass_issued_time cast to TIME — but DEFENSIVELY.

        The column is a free-text string and real data contains bad values
        (e.g. a stray '30-Jun-26' date). A blind CAST(... AS TIME) makes
        Postgres raise 'invalid input syntax for type time' and 500s the whole
        request. So we only cast rows whose value matches a 24-hour HH:MM(:SS)
        pattern; everything else falls back to midnight '00:00:00'.

        Regex: ^([01]?\\d|2[0-3]):[0-5]\\d(:[0-5]\\d)?$
          - hour 0-23 (one or two digits), minute 00-59, optional :seconds.
        """
        raw = func.trim(Irr.gate_pass_issued_time)
        is_valid = raw.op("~")(literal(r"^([01]?[0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?$"))
        safe_str = case((is_valid, raw), else_=literal("00:00:00"))
        return func.cast(safe_str, Time)

    def _issued_ist_ts(self):
        """
        Combined IST issue timestamp:
            (gate_pass_issued_date AT TIME ZONE IST)::date  +  safe_issued_time

        - AT TIME ZONE 'Asia/Kolkata' converts the UTC stamp to IST wall-clock,
          then ::date takes the correct IST calendar date.
        - gate_pass_issued_time is already IST; cast (defensively) to a time and
          add it. Result is a naive IST timestamp (no tz math needed after).
        """
        ist_date = func.cast(
            func.timezone(IST_ZONE_NAME, Irr.gate_pass_issued_date), Date
        )
        # date + time -> timestamp (Postgres allows date + time addition)
        return ist_date + self._safe_issued_time()

    def _shift_label(self):
        hour = func.extract("hour", self._issued_ist_ts())
        return case(
            ((hour >= 6) & (hour < 14), literal(MORNING)),
            ((hour >= 14) & (hour < 22), literal(AFTERNOON)),
            else_=literal(EVENING),
        )

    def _day_window_ist(self, d: date) -> tuple[datetime, datetime]:
        """Operating-day bounds as NAIVE IST timestamps [d 06:00, d+1 06:00).

        We compare against the combined IST issue timestamp (which is naive
        IST), so the bounds are naive IST too — no UTC conversion here.
        """
        start = datetime(d.year, d.month, d.day, 6, 0)
        return start, start + timedelta(days=1)

    def _calendar_window_ist(self, d: date) -> tuple[datetime, datetime]:
        """Calendar-day bounds as naive IST: [date 00:00, date+1 00:00)."""
        start = datetime(d.year, d.month, d.day, 0, 0)
        return start, start + timedelta(days=1)

    # ── data-quality filter ───────────────────────────────────────────────────
    _TIME_RE = r"^([01]?[0-9]|2[0-3]):[0-5][0-9](:[0-5][0-9])?$"

    def _usable_row(self):
        """
        A row is USABLE for the dashboard only if:
          - gate_pass_issued_date is NOT NULL (we need the date), AND
          - gate_pass_issued_time matches a valid 24-hour HH:MM(:SS) string.

        Rows failing either test are corrupt (ingestion mapped the wrong column
        in) and are EXCLUDED from all metrics. Use dropped_row_ids() to see
        exactly which rows were skipped.
        """
        time_ok = func.trim(Irr.gate_pass_issued_time).op("~")(literal(self._TIME_RE))
        return (Irr.gate_pass_issued_date.isnot(None)) & time_ok

    async def dropped_row_ids(self, report_date: date) -> list[dict]:
        """
        Diagnostic: returns the rows that WOULD BE dropped for this report_date's
        source data because of a null date or malformed time. Each entry carries
        id + gate_pass_no + the offending values, so the caller can log exactly
        what and how many were excluded.

        Note: we cannot window these by the operating day (their timestamp is
        unbuildable), so this returns ALL currently-corrupt rows. Filter/limit in
        the caller if you only care about a date's upload.
        """
        bad = ~self._usable_row()
        stmt = (
            select(
                Irr.id,
                Irr.gate_pass_no,
                Irr.gate_pass_issued_date,
                Irr.gate_pass_issued_time,
            )
            .where(bad)
        )
        rows = (await self.session.execute(stmt)).all()
        return [
            {
                "id": r.id,
                "gate_pass_no": r.gate_pass_no,
                "gate_pass_issued_date": r.gate_pass_issued_date,
                "gate_pass_issued_time": r.gate_pass_issued_time,
            }
            for r in rows
        ]

    # ── main compute ─────────────────────────────────────────────────────────
    async def compute(self, report_date: date) -> dict:
        """
        Returns a dict of per-shift metric dicts, each shaped
        {morning, afternoon, evening, total}:

            {
              "gp_count":     {...},
              "pcs":          {...},
              "gross_mt":     {...},
              "delivery_mt":  {...},   # same as gross_mt — Summary "d"
              "online_pct":   {...},   # Online GP % per shift + day
            }

        The dashboard service maps these onto MetricRows.
        """
        day_start_ist, day_end_ist = self._day_window_ist(report_date)
        # Only consider USABLE rows (valid date + valid time string). Corrupt
        # rows (null date, or a non-time value like '26063598' / a date in the
        # time column) are excluded so they neither crash the cast nor pollute
        # totals. dropped_row_ids() reports exactly which rows were skipped.
        usable = self._usable_row()
        # Filter on the COMBINED IST issue timestamp (date field's IST date +
        # time string), so the operating-day window uses the true issue time.
        issued_ts = self._issued_ist_ts()
        rng = usable & (issued_ts >= day_start_ist) & (issued_ts < day_end_ist)

        # Log dropped rows for this build so bad data is visible in the logs.
        dropped = await self.dropped_row_ids(report_date)
        if dropped:
            logger.warning(
                "ReleaseShiftService: dropped %d corrupt irr_report row(s): ids=%s",
                len(dropped),
                [d["id"] for d in dropped],
            )

        # Operating-day metrics (existing behaviour).
        result = await self._aggregate(rng)

        # Calendar-day pass: same aggregate over [00:00, 24:00) IST. We only
        # keep the single-number totals and merge them as `calendar_total`.
        cal_start, cal_end = self._calendar_window_ist(report_date)
        cal_rng = usable & (issued_ts >= cal_start) & (issued_ts < cal_end)
        cal = await self._aggregate(cal_rng)

        # Merge calendar totals into the value metrics.
        for m in ("gp_count", "pcs", "gross_mt", "delivery_mt"):
            result[m]["calendar_total"] = cal[m]["total"]
        # Online % calendar figure (recompute from calendar online/total).
        result["online_pct"]["calendar_total"] = cal["online_pct"]["total"]
        # Release SLA calendar % (single number).
        result["release_perf"]["total"]["calendar_pct"] = cal["release_perf"]["total"]["pct"]

        result["dropped_rows"] = dropped
        result["dropped_count"] = len(dropped)
        return result

    async def _aggregate(self, rng) -> dict:
        """Compute all release metric dicts over an arbitrary row-range `rng`."""
        shift = self._shift_label()
        online = func.upper(func.trim(Irr.online_counter)) == "ONLINE"

        # One grouped pass: per shift, count GP / online GP, sum pcs & weight.
        stmt = (
            select(
                shift.label("shift"),
                func.count(distinct(Irr.gate_pass_no)).label("gp_count"),
                func.count(distinct(case((online, Irr.gate_pass_no)))).label("online_gp"),
                func.coalesce(func.sum(Irr.pcs), 0).label("pcs"),
                func.coalesce(func.sum(Irr.grg_wt), 0).label("gross_kg"),
            )
            .where(rng)
            .group_by(shift)
        )
        rows = (await self.session.execute(stmt)).all()

        def blank():
            return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}

        gp = blank()
        online_gp = blank()
        pcs = blank()
        gross = blank()
        for r in rows:
            sh = r.shift
            gp[sh] = float(r.gp_count)
            online_gp[sh] = float(r.online_gp)
            pcs[sh] = float(r.pcs)
            gross[sh] = _kg_to_mt(r.gross_kg)

        for m in (gp, online_gp, pcs, gross):
            m["total"] = round(m[MORNING] + m[AFTERNOON] + m[EVENING], 3)

        day_gp = await self._day_distinct_gp(rng)
        gp["total"] = float(day_gp)

        def pct(part: dict, whole: dict) -> dict:
            out = {}
            for k in (MORNING, AFTERNOON, EVENING, "total"):
                out[k] = round(part[k] / whole[k] * 100.0, 1) if whole[k] else None
            return out

        online_pct = pct(online_gp, gp)
        release_perf = await self._release_sla(rng)

        return {
            "gp_count": gp,
            "pcs": pcs,
            "gross_mt": gross,
            "delivery_mt": gross,
            "online_pct": online_pct,
            "release_perf": release_perf,
        }

    async def _release_sla(self, rng) -> dict:
        """
        Release Performance SLA per shift.

        Rule (from spec):
            AE = gate_pass_recd_date_time
            AF = gate_pass_end_date_time
            If (AF - AE) > 4 hours  -> FAILURE, else success.
            Performance % = success GPs / total GPs (that have both AE and AF).

        Rows missing AE or AF can't be evaluated, so they're excluded from BOTH
        success and total (they neither pass nor fail) — same convention as the
        segregation SLA with missing ATW/FCC.

        Returns per-shift + day:
            {morning|afternoon|evening|total: {"total": n, "success": n, "pct": float|None}}
        """
        ae = Irr.gate_pass_recd_date_time
        af = Irr.gate_pass_end_date_time
        shift = self._shift_label()

        # elapsed hours = (AF - AE) in hours
        elapsed_hours = func.extract("epoch", af - ae) / 3600.0
        has_both = ae.isnot(None) & af.isnot(None)
        is_success = case(((has_both) & (elapsed_hours <= 4.0), 1), else_=0)

        stmt = (
            select(
                shift.label("shift"),
                # total = GPs that CAN be evaluated (both AE & AF present)
                func.count(distinct(case((has_both, Irr.gate_pass_no)))).label("total"),
                func.coalesce(func.sum(is_success), 0).label("success"),
            )
            .where(rng)
            .group_by(shift)
        )
        rows = (await self.session.execute(stmt)).all()

        def entry(total, success):
            return {"total": total, "success": success,
                    "pct": round(success / total * 100.0, 1) if total else None}

        out = {
            MORNING: entry(0, 0), AFTERNOON: entry(0, 0), EVENING: entry(0, 0),
        }
        day_total = day_success = 0
        for r in rows:
            t, s = int(r.total), int(r.success)
            out[r.shift] = entry(t, s)
            day_total += t
            day_success += s
        out["total"] = entry(day_total, day_success)
        return out

    async def _day_distinct_gp(self, rng) -> int:
        stmt = select(func.count(distinct(Irr.gate_pass_no))).where(rng)
        return int((await self.session.execute(stmt)).scalar() or 0)
    





    # =====================================================



    """
Truck IN/OUT (Truck Slot Mgt) metric computation — SHIFT-BASED.

Source table: dr_imp_truck_in_out (DigitalReportImportTruckInOut).
One row per Gate Pass truck movement.

Shift bucketing:
    A truck row is assigned to a shift by time_in (truck entry), converted to
    IST — same operating-day windows as the rest of the dashboard.

Metrics built here:
    Gate Pass Count = COUNT(DISTINCT gp_no)
    Piece Count     = SUM(pcs)
    Truck Count     = distinct vehicle plates. truck_no may hold MULTIPLE plates
                      separated by backslash (e.g. 'DL1LAC0107\\DL1LW9062'); we
                      split and count unique plates across the day. 'BY HAND' is
                      counted as its own "plate" (kept, not excluded).

    Truck Out Performance SLA:
        For each truck GP, match gp_no -> IrrReport.gate_pass_no to get the GP
        end time (gate_pass_end_date_time). GP end is always BEFORE truck time_in,
        so gap = time_in - gp_end is positive.
          success            : matched, gp_end present, gap <= 4h
          failure over_4h    : matched, gp_end present, gap  > 4h
          failure null_gp_end: matched a release row but gp_end IS NULL
          failure no_match   : gp_no not found in the release report at all
        Unlike the other SLAs, unmatched rows COUNT AS FAILURE (not excluded),
        per requirement. Total = all truck GPs in range.
        Output includes per-reason counts AND the gp_no list for each failure.
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, case, literal, String
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.digital_reports.import_dept.import_truck_in_out import DigitalReportImportTruckInOut as Truck
from app.db.models.importOperation.import_release_report import IrrReport as Irr

IST = timezone(timedelta(hours=5, minutes=30))
IST_ZONE_NAME = "Asia/Kolkata"

MORNING, AFTERNOON, EVENING = "morning", "afternoon", "evening"


class TruckShiftService:
    """Truck IN/OUT metrics for a single IST operating day, split by shift."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── shift helpers (bucket by time_in) ─────────────────────────────────────
    def _time_in_ist(self):
        """time_in as IST wall-clock (named zone — avoids the +05:30 sign trap)."""
        return func.timezone(IST_ZONE_NAME, Truck.time_in)

    def _shift_label(self):
        hour = func.extract("hour", self._time_in_ist())
        return case(
            ((hour >= 6) & (hour < 14), literal(MORNING)),
            ((hour >= 14) & (hour < 22), literal(AFTERNOON)),
            else_=literal(EVENING),
        )

    def _day_window_utc(self, d: date) -> tuple[datetime, datetime]:
        start_ist = datetime(d.year, d.month, d.day, 6, 0, tzinfo=IST)
        end_ist = start_ist + timedelta(days=1)
        return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)

    def _calendar_window_utc(self, d: date) -> tuple[datetime, datetime]:
        """Calendar-day bounds in UTC: [date 00:00 IST, date+1 00:00 IST)."""
        start_ist = datetime(d.year, d.month, d.day, 0, 0, tzinfo=IST)
        end_ist = start_ist + timedelta(days=1)
        return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)

    # ── main compute ──────────────────────────────────────────────────────────
    async def compute(self, report_date: date) -> dict:
        """
        Returns per-shift metric dicts + the Truck Out SLA breakdown:

            {
              "gp_count":    {morning/afternoon/evening/total},
              "pcs":         {...},
              "truck_count": {...},           # unique plates (backslash-split)
              "truck_out_sla": {
                  morning/afternoon/evening/total: {
                      "total": n, "success": n, "pct": float|None,
                      "fail_over_4h": n, "fail_null_gp_end": n, "fail_no_match": n,
                  },
                  "failures": [ {gp_no, reason}, ... ],   # every failing GP
              },
            }
        """
        day_start_utc, day_end_utc = self._day_window_utc(report_date)
        rng = (Truck.time_in >= day_start_utc) & (Truck.time_in < day_end_utc)

        gp_count, pcs = await self._counts(rng)
        truck_count = await self._truck_counts(rng)
        truck_out_sla = await self._truck_out_sla(rng)

        # Calendar-day pass [00:00, 24:00) IST — merge single-number totals.
        cal_start_utc, cal_end_utc = self._calendar_window_utc(report_date)
        cal_rng = (Truck.time_in >= cal_start_utc) & (Truck.time_in < cal_end_utc)
        cal_gp, cal_pcs = await self._counts(cal_rng)
        cal_truck = await self._truck_counts(cal_rng)
        cal_sla = await self._truck_out_sla(cal_rng)
        gp_count["calendar_total"] = cal_gp["total"]
        pcs["calendar_total"] = cal_pcs["total"]
        truck_count["calendar_total"] = cal_truck["total"]
        truck_out_sla["total"]["calendar_pct"] = cal_sla["total"]["pct"]

        return {
            "gp_count": gp_count,
            "pcs": pcs,
            "truck_count": truck_count,
            "truck_out_sla": truck_out_sla,
        }

    # ── GP count + pcs (one grouped pass) ─────────────────────────────────────
    async def _counts(self, rng) -> tuple[dict, dict]:
        shift = self._shift_label()
        stmt = (
            select(
                shift.label("shift"),
                func.count(func.distinct(Truck.gp_no)).label("gp_count"),
                func.coalesce(func.sum(Truck.pcs), 0).label("pcs"),
            )
            .where(rng)
            .group_by(shift)
        )
        rows = (await self.session.execute(stmt)).all()

        def blank():
            return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}

        gp, pcs = blank(), blank()
        for r in rows:
            gp[r.shift] = float(r.gp_count)
            pcs[r.shift] = float(r.pcs)
        for m in (gp, pcs):
            m["total"] = m[MORNING] + m[AFTERNOON] + m[EVENING]
        return gp, pcs

    # ── truck count: split truck_no on backslash, count unique plates ─────────
    async def _truck_counts(self, rng) -> dict:
        """
        truck_no may contain multiple plates joined by backslash. We pull
        (shift, truck_no) and split/dedupe in Python — cleaner than SQL string
        gymnastics and easy to adjust (e.g. if you later want to drop BY HAND).
        """
        shift = self._shift_label()
        stmt = select(shift.label("shift"), Truck.truck_no).where(rng)
        rows = (await self.session.execute(stmt)).all()

        # collect a set of plates per shift so duplicates across rows don't count twice
        plates = {MORNING: set(), AFTERNOON: set(), EVENING: set()}
        for r in rows:
            if not r.truck_no:
                continue
            for plate in str(r.truck_no).split("\\"):
                p = plate.strip().upper()
                if p:
                    plates[r.shift].add(p)

        out = {sh: float(len(plates[sh])) for sh in (MORNING, AFTERNOON, EVENING)}
        # Day total = unique plates across the whole day (union of the 3 shifts).
        out["total"] = float(len(plates[MORNING] | plates[AFTERNOON] | plates[EVENING]))
        return out

    # ── Truck Out SLA (join to release for GP end) ────────────────────────────
    async def _truck_out_sla(self, rng) -> dict:
        """
        LEFT JOIN truck rows to the release report on gp_no = gate_pass_no to get
        gp_end. Then classify each truck GP in Python so we can attach a reason
        and collect the failing gp_no list.
        """
        shift = self._shift_label()
        # Truck.gp_no is an int; IrrReport.gate_pass_no is a string — cast for join.
        gp_no_str = func.cast(Truck.gp_no, String)

        stmt = (
            select(
                Truck.gp_no.label("gp_no"),
                shift.label("shift"),
                Truck.time_in.label("time_in"),
                Irr.gate_pass_end_date_time.label("gp_end"),
                Irr.gate_pass_no.label("matched_gp"),
            )
            .select_from(Truck)
            .join(Irr, Irr.gate_pass_no == gp_no_str, isouter=True)
            .where(rng)
        )
        rows = (await self.session.execute(stmt)).all()

        # Step 1: resolve one outcome per truck gp_no. A gp_no may join to
        # multiple release rows; a success on ANY matched row wins, else keep
        # the most informative failure (over_4h > null_gp_end > no_match).
        # We also remember each gp's shift (from time_in, stable per gp).
        FAIL_RANK = {"over_4h": 3, "null_gp_end": 2, "no_match": 1}
        best: dict[int, dict] = {}   # gp_no -> {"outcome","shift"}

        for r in rows:
            gp = r.gp_no
            if r.matched_gp is None:
                outcome = "no_match"
            elif r.gp_end is None:
                outcome = "null_gp_end"
            else:
                gap_h = (r.time_in - r.gp_end).total_seconds() / 3600.0 if r.time_in else None
                outcome = "success" if (gap_h is not None and gap_h <= 4.0) else "over_4h"

            cur = best.get(gp)
            if cur is None:
                best[gp] = {"outcome": outcome, "shift": r.shift}
            elif cur["outcome"] != "success":
                # upgrade to success, or to a higher-ranked failure
                if outcome == "success":
                    best[gp] = {"outcome": "success", "shift": r.shift}
                elif cur["outcome"] != "success" and FAIL_RANK.get(outcome, 0) > FAIL_RANK.get(cur["outcome"], 0):
                    best[gp] = {"outcome": outcome, "shift": r.shift}

        # Step 2: aggregate the resolved outcomes once.
        def blank_entry():
            return {"total": 0, "success": 0, "fail_over_4h": 0,
                    "fail_null_gp_end": 0, "fail_no_match": 0}

        agg = {MORNING: blank_entry(), AFTERNOON: blank_entry(), EVENING: blank_entry()}
        failures: list[dict] = []
        for gp, info in best.items():
            sh, outcome = info["shift"], info["outcome"]
            agg[sh]["total"] += 1
            if outcome == "success":
                agg[sh]["success"] += 1
            else:
                agg[sh][_fail_key(outcome)] += 1
                failures.append({"gp_no": gp, "reason": outcome})

        # Step 3: pct + day rollup.
        def pct(e):
            return round(e["success"] / e["total"] * 100.0, 1) if e["total"] else None

        out = {}
        day = blank_entry()
        for sh in (MORNING, AFTERNOON, EVENING):
            e = agg[sh]
            e["pct"] = pct(e)
            out[sh] = e
            for k in ("total", "success", "fail_over_4h", "fail_null_gp_end", "fail_no_match"):
                day[k] += e[k]
        day["pct"] = pct(day)
        out["total"] = day
        out["failures"] = failures
        return out


def _fail_key(reason: str) -> str:
    return {"over_4h": "fail_over_4h",
            "null_gp_end": "fail_null_gp_end",
            "no_match": "fail_no_match"}[reason]




# ================================================================================




"""
Pick Order (Examination / P.2) metric computation — SHIFT-BASED.

Source table: dr_imp_pick_order (DigitalReportImportPickOrder).

Metrics (from the CEO spec, P.2 Examination):
    a — No. of Pick Order / AWB Number = COUNT(DISTINCT awb_no)
    b — No. of Pcs                     = SUM(pcs_for_examination)
    (c On Floor Productivity + c.1 manpower -> pending, Roster)

────────────────────────────────────────────────────────────────────────────
SHIFT BUCKETING DATETIME  — EASY TO CHANGE
────────────────────────────────────────────────────────────────────────────
Which timestamp decides a pick-order row's shift is controlled by ONE setting:

    _SHIFT_BUCKET_COLUMN

Currently it buckets by POE start time (poe_start_datetime). If you later want a
different basis (e.g. POE end, RFE, or FFE), change just that one line to the
matching model column — nothing else in this file needs to change.

Available columns (all stored UTC):
    PickOrder.rfe_datetime
    PickOrder.ffe_datetime
    PickOrder.poe_start_datetime   <-- current
    PickOrder.poe_end_datetime
"""

from datetime import date, datetime, timedelta, timezone
from typing import Optional

from sqlalchemy import func, select, case, literal, distinct
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.digital_reports.import_dept.import_pick_order import DigitalReportImportPickOrder as PickOrder

IST = timezone(timedelta(hours=5, minutes=30))
IST_ZONE_NAME = "Asia/Kolkata"

MORNING, AFTERNOON, EVENING = "morning", "afternoon", "evening"

# ── THE ONE SETTING TO CHANGE THE SHIFT-BUCKETING BASIS ─────────────────────
# Swap this to poe_end_datetime / rfe_datetime / ffe_datetime if needed.
_SHIFT_BUCKET_COLUMN = PickOrder.poe_start_datetime


class PickOrderShiftService:
    """Examination (pick order) metrics for a single IST day, split by shift."""

    def __init__(self, session: AsyncSession):
        self.session = session

    # ── shift helpers (bucket by the configured column) ───────────────────────
    def _bucket_ist(self):
        """The bucketing timestamp expressed in IST wall-clock (named zone)."""
        return func.timezone(IST_ZONE_NAME, _SHIFT_BUCKET_COLUMN)

    def _shift_label(self):
        hour = func.extract("hour", self._bucket_ist())
        return case(
            ((hour >= 6) & (hour < 14), literal(MORNING)),
            ((hour >= 14) & (hour < 22), literal(AFTERNOON)),
            else_=literal(EVENING),
        )

    def _day_window_utc(self, d: date) -> tuple[datetime, datetime]:
        start_ist = datetime(d.year, d.month, d.day, 6, 0, tzinfo=IST)
        end_ist = start_ist + timedelta(days=1)
        return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)

    def _calendar_window_utc(self, d: date) -> tuple[datetime, datetime]:
        """Calendar-day bounds in UTC: [date 00:00 IST, date+1 00:00 IST)."""
        start_ist = datetime(d.year, d.month, d.day, 0, 0, tzinfo=IST)
        end_ist = start_ist + timedelta(days=1)
        return start_ist.astimezone(timezone.utc), end_ist.astimezone(timezone.utc)

    async def compute(self, report_date: date) -> dict:
        """
        Returns per-shift metric dicts {morning/afternoon/evening/total}:
            {
              "awb_count": {...},   # distinct AWB numbers
              "pcs":       {...},   # sum of pcs_for_examination
            }

        Note: pick-order rows are ALSO tagged with a stored `report_date` (the
        upload key). Here we bucket by the event timestamp's operating day, which
        is the dashboard-consistent behaviour. If instead you want to select rows
        purely by the stored report_date column, filter on that in _both queries_
        — kept as a comment below.
        """
        day_start_utc, day_end_utc = self._day_window_utc(report_date)
        col = _SHIFT_BUCKET_COLUMN
        # Bucket by the event timestamp's operating day.
        rng = (col.isnot(None)) & (col >= day_start_utc) & (col < day_end_utc)
        # Alternative (select by stored upload key instead):
        # rng = (PickOrder.report_date == report_date) & (col.isnot(None))

        shift = self._shift_label()
        stmt = (
            select(
                shift.label("shift"),
                func.count(distinct(PickOrder.awb_no)).label("awb_count"),
                func.coalesce(func.sum(PickOrder.pcs_for_examination), 0).label("pcs"),
            )
            .where(rng)
            .group_by(shift)
        )
        rows = (await self.session.execute(stmt)).all()

        def blank():
            return {MORNING: 0.0, AFTERNOON: 0.0, EVENING: 0.0, "total": 0.0}

        awb, pcs = blank(), blank()
        for r in rows:
            awb[r.shift] = float(r.awb_count)
            pcs[r.shift] = float(r.pcs)
        pcs["total"] = pcs[MORNING] + pcs[AFTERNOON] + pcs[EVENING]

        # AWB count total must be day-wide distinct (an AWB could appear in two
        # shifts), so recompute distinct over the whole day rather than summing.
        day_awb = await self._day_distinct_awb(rng)
        awb["total"] = float(day_awb)

        # Calendar-day pass [00:00, 24:00) IST — single-number totals.
        cal_start_utc, cal_end_utc = self._calendar_window_utc(report_date)
        cal_rng = (col.isnot(None)) & (col >= cal_start_utc) & (col < cal_end_utc)
        cal_stmt = (
            select(
                func.count(distinct(PickOrder.awb_no)).label("awb_count"),
                func.coalesce(func.sum(PickOrder.pcs_for_examination), 0).label("pcs"),
            ).where(cal_rng)
        )
        cal_row = (await self.session.execute(cal_stmt)).one()
        awb["calendar_total"] = float(cal_row.awb_count)
        pcs["calendar_total"] = float(cal_row.pcs)

        return {"awb_count": awb, "pcs": pcs}

    async def _day_distinct_awb(self, rng) -> int:
        stmt = select(func.count(distinct(PickOrder.awb_no))).where(rng)
        return int((await self.session.execute(stmt)).scalar() or 0)