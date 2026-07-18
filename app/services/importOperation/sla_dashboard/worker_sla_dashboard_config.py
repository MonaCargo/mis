# app/config/gp_dashboard_config.py
"""
STATIC MASTERS for the Import Gate Pass Monitoring Dashboard (New App).

Everything the dashboard renders is driven from this file. To change a
behaviour you edit here — the service loops these lists blindly and never
hardcodes a slab, a column, or a threshold.

WHAT YOU CAN SAFELY EDIT
------------------------
1. DETAILED_SLABS / SUMMARY_SLABS : add / remove / re-bound time buckets.
       - boundaries are in MINUTES
       - low  = None  -> this is the "Blank" (NULL) bucket
       - high = None  -> open-ended upper bucket (the ">" row)
       - bucketing rule: low < diff_minutes <= high
2. COLUMN_PAIRS : the 12 metric columns.
       - a / b : model attribute names; diff = (b - a)
       - blank_on = "b"      -> Blank when B is NULL (A guaranteed present)
                    "either"  -> Blank when A OR B is NULL
       - color_thresholds : green_max / amber_max in MINUTES  (<-- PLACEHOLDERS)
3. FILTER_MODES : how a slab's "Number" is measured.
4. COLORS : the actual hex values for each colour name.

NOTE ON color_thresholds:
    These are PLACEHOLDER business rules, guessed per activity (short for
    an operator-assign step, long for a truck-out step). Tune them later —
    only this file changes, no service edits needed.
"""

# ---------------------------------------------------------------------------
# 1. COLOUR PALETTE  (edit hex here; slabs/columns reference by name)
# ---------------------------------------------------------------------------
COLORS = {
    "green":  "#53BC58",   # within target
    # "amber":  "#EEB559",   # watch
    "amber":  "#f6c7aa",   # watch
    "red":    "#F45151",   # breach
    "grey":   "#F0E9E9",   # Blank / not-yet-done
}

BLANK_COLOR_KEY = "grey"   # fixed colour for the Blank bucket, any column


# ---------------------------------------------------------------------------
# 2. TIME SLABS  (minutes; bucketing rule = low < diff <= high)
# ---------------------------------------------------------------------------
# key = safe code identifier (no spaces/special chars) used in response dicts
# label = display string shown verbatim in the UI / Excel

DETAILED_SLABS = [
    {"sn": 1,  "key": "d_lt_00_30",     "label": "< 00:30 Hrs",     "low": 0,    "high": 30},
    {"sn": 2,  "key": "d_00_31_01_00",  "label": "00:31-01:00 Hrs", "low": 30,   "high": 60},
    {"sn": 3,  "key": "d_01_01_01_30",  "label": "01:01-01:30 Hrs", "low": 60,   "high": 90},
    {"sn": 4,  "key": "d_01_31_02_00",  "label": "01:31-02:00 Hrs", "low": 90,   "high": 120},
    {"sn": 5,  "key": "d_02_01_02_30",  "label": "02:01-02:30 Hrs", "low": 120,  "high": 150},
    {"sn": 6,  "key": "d_02_31_03_00",  "label": "02:31-03:00 Hrs", "low": 150,  "high": 180},
    {"sn": 7,  "key": "d_03_01_03_30",  "label": "03:01-03:30 Hrs", "low": 180,  "high": 210},
    {"sn": 8,  "key": "d_03_31_04_00",  "label": "03:31-04:00 Hrs", "low": 210,  "high": 240},
    {"sn": 9,  "key": "d_04_01_04_30",  "label": "04:01-04:30 Hrs", "low": 240,  "high": 270},
    {"sn": 10, "key": "d_04_31_05_00",  "label": "04:31-05:00 Hrs", "low": 270,  "high": 300},
    {"sn": 11, "key": "d_05_01_06_00",  "label": "05:01-06:00 Hrs", "low": 300,  "high": 360},
    {"sn": 12, "key": "d_06_01_07_00",  "label": "06:01-07:00 Hrs", "low": 360,  "high": 420},
    {"sn": 13, "key": "d_07_01_08_00",  "label": "07:01-08:00 Hrs", "low": 420,  "high": 480},
    {"sn": 14, "key": "d_08_01_09_00",  "label": "08:01-09:00 Hrs", "low": 480,  "high": 540},
    {"sn": 15, "key": "d_09_01_10_00",  "label": "09:01-10:00 Hrs", "low": 540,  "high": 600},
    {"sn": 16, "key": "d_gt_10_00",     "label": "> 10:00 Hrs",     "low": 600,  "high": None},
    {"sn": 17, "key": "d_blank",        "label": "Blank",           "low": None, "high": None},
]

SUMMARY_SLABS = [
    {"sn": 1, "key": "s_lt_02_00",    "label": "< 02:00 Hrs",     "low": 0,    "high": 120},
    {"sn": 2, "key": "s_02_01_04_00", "label": "02:01-04:00 Hrs", "low": 120,  "high": 240},
    {"sn": 3, "key": "s_04_01_06_00", "label": "04:01-06:00 Hrs", "low": 240,  "high": 360},
    {"sn": 4, "key": "s_06_01_08_00", "label": "06:01-08:00 Hrs", "low": 360,  "high": 480},
    {"sn": 5, "key": "s_gt_08_00",    "label": "> 08:00 Hrs",     "low": 480,  "high": None},
    {"sn": 6, "key": "s_blank",       "label": "Blank",           "low": None, "high": None},
]


# ---------------------------------------------------------------------------
# 3. COLUMN PAIRS  (the 12 metrics; diff = b - a)
# ---------------------------------------------------------------------------
# color_thresholds are PLACEHOLDERS — tune green_max / amber_max (minutes):
#     diff <= green_max            -> green
#     green_max < diff <= amber_max-> amber
#     diff > amber_max             -> red
#     Blank bucket                 -> grey (fixed, ignores thresholds)

COLUMN_PAIRS = [
    {
        "key": "gp_issue_vs_operator_assigned",
        "label": "GP Issue vs Operator Assigned",
        "a": "gate_pass_issued_date_time_combo",
        "b": "assigned_person_datetime",
        "blank_on": "b",
        "color_thresholds": {"green_max": 30, "amber_max": 60},
    },
    {
        "key": "operator_assigned_vs_drop_delv_zone",
        "label": "Operator Assigned vs Drop Delv Zone",
        "a": "assigned_person_datetime",
        "b": "drop_dlv_zone_datetime",
        "blank_on": "either",
        "color_thresholds": {"green_max": 30, "amber_max": 90},
    },
    {
        "key": "drop_delv_zone_vs_lift_loading",
        "label": "Drop Delv Zone vs Lift Loading",
        "a": "drop_dlv_zone_datetime",
        "b": "loading_in_lift_zone_datetime",
        "blank_on": "either",
        "color_thresholds": {"green_max": 30, "amber_max": 90},
    },
    {
        "key": "lift_loading_vs_lift_unloading",
        "label": "Lift Loading vs Lift Unloading",
        "a": "loading_in_lift_zone_datetime",
        "b": "unloading_from_lift_zone_datetime",
        "blank_on": "either",
        "color_thresholds": {"green_max": 60, "amber_max": 120},
    },
    {
        "key": "lift_unloading_vs_final_delivery",
        "label": "Lift Unloading vs Final Delivery (PD)",
        "a": "unloading_from_lift_zone_datetime",
        "b": "final_delivery_datetime",
        "blank_on": "either",
        "color_thresholds": {"green_max": 30, "amber_max": 90},
    },
    {
        "key": "gp_issue_vs_gp_rcvd_security",
        "label": "GP Issue vs GP Rcvd by Security",
        "a": "gate_pass_issued_date_time_combo",
        "b": "gp_received_datetime",
        "blank_on": "b",
        "color_thresholds": {"green_max": 30, "amber_max": 90},
    },
    {
        "key": "gp_issue_vs_final_delivery",
        "label": "GP Issue vs Final Delivery (PD)",
        "a": "gate_pass_issued_date_time_combo",
        "b": "final_delivery_datetime",
        "blank_on": "b",
        "color_thresholds": {"green_max": 120, "amber_max": 240},
    },
    {
        "key": "gp_rcvd_security_vs_final_delivery",
        "label": "GP Rcvd by Security vs Final Delivery (PD)",
        "a": "gp_received_datetime",
        "b": "final_delivery_datetime",
        "blank_on": "either",
        "color_thresholds": {"green_max": 120, "amber_max": 240},
    },
    {
        "key": "final_delivery_vs_truck_in",
        "label": "Final Delivery (PD) vs Truck In",
        "a": "final_delivery_datetime",
        "b": "truck_in_datetime",
        "blank_on": "either",
        "color_thresholds": {"green_max": 60, "amber_max": 180},
    },
    {
        "key": "final_delivery_vs_truck_out",
        "label": "Final Delivery (PD) vs Truck Out",
        "a": "final_delivery_datetime",
        "b": "truck_out_datetime",
        "blank_on": "either",
        "color_thresholds": {"green_max": 120, "amber_max": 240},
    },
    {
        "key": "truck_in_vs_truck_out",
        "label": "Truck In vs Truck Out",
        "a": "truck_in_datetime",
        "b": "truck_out_datetime",
        "blank_on": "either",
        "color_thresholds": {"green_max": 60, "amber_max": 120},
    },
    {
        "key": "gp_issue_vs_truck_out",
        "label": "GP Issue vs Truck Out",
        "a": "gate_pass_issued_date_time_combo",
        "b": "truck_out_datetime",
        "blank_on": "b",
        "color_thresholds": {"green_max": 240, "amber_max": 480},
    },
]


# ---------------------------------------------------------------------------
# 4. FILTER MODES  (how a slab's "Number" is measured)
# ---------------------------------------------------------------------------
# kind = "count"  -> +1 per shipment falling in the slab
#        "sum"    -> += getattr(row, field) per shipment
# mt = True       -> divide the summed value by 1000 (kg -> MT) and round
#
# NOTE: gross/charge weight columns on the shipment model are in KG.

FILTER_MODES = {
    "gp_count":   {"label": "GP (Count)",        "kind": "count", "field": None,            "mt": False},
    "piece":      {"label": "Piece (SUM)",       "kind": "sum",   "field": "no_of_pc",      "mt": False},
    "gross_wt":   {"label": "Gross Weight (SUM)", "kind": "sum",  "field": "weight_in_kgs", "mt": True},
    "charge_wt":  {"label": "Charge Weight (SUM)","kind": "sum",  "field": "chg_wgt_in_kg", "mt": True},
}

DEFAULT_FILTER_MODE = "gp_count"


# ---------------------------------------------------------------------------
# 5. LOCATION EXCLUSION  (Logic #4: drop PER & VAL cargo)
# ---------------------------------------------------------------------------
# Exclude a shipment if ANY location token starts with one of these prefixes.
# location is a Text column holding comma/semicolon separated tokens, e.g.
#   "IA_37_B-14;IA_14_B-8"
EXCLUDE_LOCATION_PREFIXES = ("ISR", "PI", "TDP")
LOCATION_SPLIT_CHARS = ";,"   # split on either ; or ,

MT_ROUND_DP = 3   # decimal places for MT values