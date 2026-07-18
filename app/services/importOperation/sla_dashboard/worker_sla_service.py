# app/services/gp_dashboard_service.py
"""
Import Gate Pass Monitoring Dashboard (New App) — aggregation engine.

Pure config-driven: reads app/config/gp_dashboard_config.py and never
hardcodes a slab, column, threshold or filter mode. Add a column or move
a boundary in the config and this service adapts with no change.

Pipeline
--------
1. Query eligible shipments:
     - gate_pass_issued_date_time_combo IS NOT NULL   (only GP shipments)
     - that column BETWEEN start_dt AND end_dt
     - drop rows whose location has ANY token starting ISR / PI / TDP
2. For each COLUMN_PAIR, per row:
     - diff = (b - a) in minutes
     - find the matching slab (low < diff <= high); NULL -> Blank
     - accumulate the filter-mode weight (count | sum(field))
3. Percent = slab_value / column_total * 100  (Logic #5)
4. Colour each Number cell from the column's thresholds + the slab.

Returns a JSON-ready grid the frontend renders directly.
"""

from datetime import datetime
from typing import Any, Optional

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.services.importOperation.sla_dashboard.worker_sla_dashboard_config import (
    DETAILED_SLABS,
    SUMMARY_SLABS,
    COLUMN_PAIRS,
    FILTER_MODES,
    DEFAULT_FILTER_MODE,
    COLORS,
    BLANK_COLOR_KEY,
    EXCLUDE_LOCATION_PREFIXES,
    LOCATION_SPLIT_CHARS,
    MT_ROUND_DP,
)
# Adjust this import path to wherever the model actually lives in your tree.
from app.db.models.importOperation.worker_assignment import WorkerAssignmentShipment


# ---------------------------------------------------------------------------
# small helpers
# ---------------------------------------------------------------------------
def _split_tokens(location: Optional[str]) -> list[str]:
    """Split a location Text field on any of the configured separators."""
    if not location:
        return []
    # normalise every split char to a single delimiter, then split
    tmp = location
    primary = LOCATION_SPLIT_CHARS[0]
    for ch in LOCATION_SPLIT_CHARS[1:]:
        tmp = tmp.replace(ch, primary)
    return [t.strip() for t in tmp.split(primary) if t.strip()]


def _is_excluded_location(location: Optional[str]) -> bool:
    """True if ANY token starts with an excluded prefix (case-insensitive)."""
    for tok in _split_tokens(location):
        up = tok.upper()
        if any(up.startswith(p) for p in EXCLUDE_LOCATION_PREFIXES):
            return True
    return False


def _diff_minutes(a: Optional[datetime], b: Optional[datetime]) -> Optional[float]:
    """(b - a) in minutes; None if either side is missing."""
    if a is None or b is None:
        return None
    return (b - a).total_seconds() / 60.0


def _find_slab(diff_min: Optional[float], slabs: list[dict]) -> dict:
    """
    Bucket a diff into a slab using  low < diff <= high.
      diff is None            -> the Blank slab (low is None)
      high is None            -> open-ended upper slab (diff > low)
      negative / zero diff    -> smallest non-blank slab (low is 0)
    """
    if diff_min is None:
        return next(s for s in slabs if s["low"] is None)

    # guard: sub-zero (dirty data) falls into the first real bucket
    if diff_min <= 0:
        return next(s for s in slabs if s["low"] == 0)

    for s in slabs:
        low, high = s["low"], s["high"]
        if low is None:            # skip Blank
            continue
        if high is None:           # open-ended ">" bucket
            if diff_min > low:
                return s
        elif low < diff_min <= high:
            return s
    # fallback (shouldn't hit if slabs are contiguous) -> open-ended bucket
    return next(s for s in slabs if s["high"] is None and s["low"] is not None)


def _cell_color(slab: dict, thresholds: dict) -> str:
    """Colour for a Number cell = f(column thresholds, slab)."""
    if slab["low"] is None:                       # Blank
        return COLORS[BLANK_COLOR_KEY]
    # represent the slab by its lower edge for classification;
    # the open-ended (>) slab uses its low as the representative minute.
    rep = slab["low"] if slab["high"] is None else slab["high"]
    if rep <= thresholds["green_max"]:
        return COLORS["green"]
    if rep <= thresholds["amber_max"]:
        return COLORS["amber"]
    return COLORS["red"]


def _weight(row: Any, mode: dict) -> float:
    """Value a single row contributes under the active filter mode."""
    if mode["kind"] == "count":
        return 1.0
    val = getattr(row, mode["field"], None)
    return float(val) if val is not None else 0.0


def _finalize(value: float, mode: dict) -> float:
    """Apply kg->MT conversion + rounding for the display value."""
    if mode.get("mt"):
        return round(value / 1000.0, MT_ROUND_DP)
    # counts are ints; piece sums are ints too
    if mode["kind"] == "count" or mode["field"] == "no_of_pc":
        return round(value)
    return round(value, MT_ROUND_DP)


# ---------------------------------------------------------------------------
# main entry point
# ---------------------------------------------------------------------------
async def build_gp_dashboard(
    db: AsyncSession,
    start_dt: datetime,
    end_dt: datetime,
    filter_by: str = DEFAULT_FILTER_MODE,
) -> dict:
    """
    Build the full GP dashboard grid for a date range + filter mode.

    Returns:
        {
          "filter_by": "gp_count",
          "filter_label": "GP (Count)",
          "range": {"start": ..., "end": ...},
          "columns": [ {key, label}, ... ],          # 12 columns, in order
          "detailed": { <col_key>: { "slabs": {<slab_key>: {number, perc, color, ...}},
                                     "total": <num> } },
          "summary":  { <col_key>: { ... same shape ... } },
          "grand_total": <num>,   # eligible shipments under this filter
        }
    """
    if filter_by not in FILTER_MODES:
        filter_by = DEFAULT_FILTER_MODE
    mode = FILTER_MODES[filter_by]

    M = WorkerAssignmentShipment

    # -- 1. query eligible shipments -----------------------------------------
    stmt = (
        select(M)
        .where(M.gate_pass_issued_date_time_combo.is_not(None))
        .where(M.gate_pass_issued_date_time_combo.between(start_dt, end_dt))
    )
    rows = (await db.execute(stmt)).scalars().all()

    # location exclusion in Python (token-level rule, hard to express in SQL)
    rows = [r for r in rows if not _is_excluded_location(r.location)]

    # -- 2. init accumulators -------------------------------------------------
    # detailed[col_key][slab_key] = float
    detailed: dict[str, dict[str, float]] = {
        c["key"]: {s["key"]: 0.0 for s in DETAILED_SLABS} for c in COLUMN_PAIRS
    }
    summary: dict[str, dict[str, float]] = {
        c["key"]: {s["key"]: 0.0 for s in SUMMARY_SLABS} for c in COLUMN_PAIRS
    }

    # -- 3. accumulate --------------------------------------------------------
    for row in rows:
        w = _weight(row, mode)
        for col in COLUMN_PAIRS:
            a = getattr(row, col["a"], None)
            b = getattr(row, col["b"], None)

            # Blank rule: "b" -> blank only when B missing (A guaranteed);
            #             "either" -> blank when A or B missing
            if col["blank_on"] == "either" and (a is None or b is None):
                diff = None
            elif col["blank_on"] == "b" and b is None:
                diff = None
            else:
                diff = _diff_minutes(a, b)

            d_slab = _find_slab(diff, DETAILED_SLABS)
            s_slab = _find_slab(diff, SUMMARY_SLABS)
            detailed[col["key"]][d_slab["key"]] += w
            summary[col["key"]][s_slab["key"]] += w

    # -- 4. shape output with perc + colour ----------------------------------
    def _shape(acc: dict[str, dict[str, float]], slabs: list[dict]) -> dict:
        out: dict[str, Any] = {}
        for col in COLUMN_PAIRS:
            col_key = col["key"]
            raw = acc[col_key]
            total_raw = sum(raw.values())
            slab_out: dict[str, Any] = {}
            for s in slabs:
                v_raw = raw[s["key"]]
                number = _finalize(v_raw, mode)
                perc = round((v_raw / total_raw * 100.0), 2) if total_raw else 0.0
                slab_out[s["key"]] = {
                    "sn": s["sn"],
                    "label": s["label"],
                    "number": number,
                    "perc": perc,                       # Perc cell: NO colour
                    "color": _cell_color(s, col["color_thresholds"]),  # Number cell colour
                }
            out[col_key] = {
                "slabs": slab_out,
                "total": _finalize(total_raw, mode),
            }
        return out

    grand_total = _finalize(sum(_weight(r, mode) for r in rows), mode)

    return {
        "filter_by": filter_by,
        "filter_label": mode["label"],
        "range": {"start": start_dt.isoformat(), "end": end_dt.isoformat()},
        "columns": [{"key": c["key"], "label": c["label"]} for c in COLUMN_PAIRS],
        "detailed_slabs_meta": [
            {"sn": s["sn"], "key": s["key"], "label": s["label"]} for s in DETAILED_SLABS
        ],
        "summary_slabs_meta": [
            {"sn": s["sn"], "key": s["key"], "label": s["label"]} for s in SUMMARY_SLABS
        ],
        "detailed": _shape(detailed, DETAILED_SLABS),
        "summary": _shape(summary, SUMMARY_SLABS),
        "grand_total": grand_total,
        "row_count": len(rows),
    }