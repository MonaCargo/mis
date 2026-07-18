


from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import pandas as pd
from app.db.session import get_db
from fastapi.responses import StreamingResponse
import io
import xlsxwriter




# ----------------- MODELS -----------------
from app.db.models.digital_reports.export_dept.cargo_uplift_report import DigitalReportCargoUpliftReport
from app.db.models.digital_reports.export_dept.car_message_report import DigitalReportCarMessageReport
from app.db.models.digital_reports.export_dept.x_ray_report import DigitalReportXrayReport
from app.db.models.digital_reports.export_dept.import_tp_xray_report import DigitalReportImportTpXrayReport
from app.db.models.digital_reports.export_dept.export_tp_xray_report import DigitalReportExportTpXrayReport
from app.db.models.digital_reports.export_dept.export_loaded_inventory import DigitalReportExportLoadedInventory
from app.db.models.digital_reports.export_dept.export_transhipment_report import DigitalReportExportTranshipmentReport
from app.db.models.digital_reports.export_dept.import_segregation_report import DigitalReportImportSegregationReport

# ⚠️
from app.db.models.exportOperation.car_message import ExportSequenceItemUldLoading as ExportItemUldLoading
from app.db.models.exportOperation.car_message import ExportCarMessageAwbMaster as ExportCarMessageAwbMaster

router = APIRouter()


# ============================================================
#  DB HELPERS (ORM)
# ============================================================
async def fetch_df(db: AsyncSession, stmt) -> pd.DataFrame:
    """Execute any select() statement and return a DataFrame."""
    result = await db.execute(stmt)
    return pd.DataFrame(result.mappings().all())


def between_stmt(model, col_name: str, start_dt, end_dt):
    """
    ORM equivalent of:
      SELECT * FROM <table> WHERE <col> >= :s AND <col> < :e

    NOTE: we select(*model.__table__.c) instead of select(model) so that
    result.mappings() yields flat {column: value} dicts (which pandas wants),
    rather than {"ModelName": <orm object>}.
    """
    col = getattr(model, col_name)
    return select(*model.__table__.c).where(and_(col >= start_dt, col < end_dt))


def screening_stmt(start_dt, end_dt):
    """
    ORM equivalent of the SLA screening join:
      SELECT ul.loaded_at, COALESCE(awb.gross_wt, 0) AS gross_wt, awb.shc
      FROM export_item_uld_loading ul
      JOIN export_car_message_awb_master awb ON ul.awb_master_id = awb.id
      WHERE ul.loaded_at >= :s AND ul.loaded_at < :e
        AND awb.shc NOT ILIKE '%PER%'
        AND awb.shc NOT ILIKE '%PEM%'
    """
    return (
        select(
            ExportItemUldLoading.loaded_at,
            func.coalesce(ExportCarMessageAwbMaster.gross_wt, 0).label("gross_wt"),
            ExportCarMessageAwbMaster.shc,
        )
        .join(
            ExportCarMessageAwbMaster,
            ExportItemUldLoading.awb_master_id == ExportCarMessageAwbMaster.id,
        )
        .where(
            ExportItemUldLoading.loaded_at >= start_dt,
            ExportItemUldLoading.loaded_at < end_dt

            #------------ removing per / pem filter from screening----------------------
            # ~ExportCarMessageAwbMaster.shc.ilike("%PER%"),
            # ~ExportCarMessageAwbMaster.shc.ilike("%PEM%"),
        )
    )


async def fetch_all_dashboard_data(db: AsyncSession, start_dt, end_dt) -> dict:
    """Single place where all 9 datasets get loaded — used by both endpoints."""
    return {
        "uplift":      await fetch_df(db, between_stmt(DigitalReportCargoUpliftReport,        "uld_release_date_time", start_dt, end_dt)),
        "car_msg":     await fetch_df(db, between_stmt(DigitalReportCarMessageReport,         "car_msg_date_time",     start_dt, end_dt)),
        "loaded":      await fetch_df(db, between_stmt(DigitalReportExportLoadedInventory,    "loaded_date_time",      start_dt, end_dt)),
        "imp_seg":     await fetch_df(db, between_stmt(DigitalReportImportSegregationReport,  "tfd_date_time",         start_dt, end_dt)),
        "exp_tp":      await fetch_df(db, between_stmt(DigitalReportExportTranshipmentReport, "xray_date_time",        start_dt, end_dt)),
        "xray":        await fetch_df(db, between_stmt(DigitalReportXrayReport,               "xray_date_time",        start_dt, end_dt)),
        "imp_tp_xray": await fetch_df(db, between_stmt(DigitalReportImportTpXrayReport,       "xray_date_time",        start_dt, end_dt)),
        "exp_tp_xray": await fetch_df(db, between_stmt(DigitalReportExportTpXrayReport,       "xray_date_time",        start_dt, end_dt)),
        "screening":    await fetch_df(db, screening_stmt(start_dt, end_dt)),
    }


# ============================================================
#  SHIFT AGGREGATION HELPERS (unchanged)
# ============================================================
# divisor: value to divide the aggregated number by (e.g. 1000 to convert KG -> MT)
# decimals: rounding precision (0 -> whole numbers, e.g. 153029 kg -> 153 MT)
def get_shift_metrics(df: pd.DataFrame, datetime_col: str, metric_col: str, agg_type: str = 'sum',
                      divisor: float = 1, decimals: int = 0) -> dict:
    result = {"1st Shift": 0, "2nd Shift": 0, "3rd Shift": 0, "Total": 0}

    if df.empty or datetime_col not in df.columns or metric_col not in df.columns:
        return result

    df_clean = df.copy()
    df_clean[datetime_col] = pd.to_datetime(df_clean[datetime_col], errors='coerce')

    if agg_type == 'sum':
        df_clean[metric_col] = pd.to_numeric(df_clean[metric_col], errors='coerce').fillna(0)

    df_clean = df_clean.dropna(subset=[datetime_col]).copy()

    if agg_type in ['nunique', 'count']:
        df_clean = df_clean[df_clean[metric_col].astype(str).str.strip() != '']

    def assign_shift_utc(row):
        # IST = UTC + 5.5h
        h_float = row[datetime_col].hour + (row[datetime_col].minute / 60)
        if 0.5 <= h_float < 8.5:      # 1st Shift  06:00-14:00 IST
            return '1st Shift'
        elif 8.5 <= h_float < 16.5:   # 2nd Shift  14:00-22:00 IST
            return '2nd Shift'
        else:                          # 3rd Shift  22:00-06:00 IST
            return '3rd Shift'

    df_clean['shift'] = df_clean.apply(assign_shift_utc, axis=1)

    if agg_type == 'sum':
        grouped = df_clean.groupby('shift')[metric_col].sum().to_dict()
    elif agg_type == 'nunique':
        grouped = df_clean.groupby('shift')[metric_col].nunique().to_dict()
    elif agg_type == 'count':
        grouped = df_clean.groupby('shift')[metric_col].count().to_dict()
    else:
        grouped = {}

    for shift in ["1st Shift", "2nd Shift", "3rd Shift"]:
        raw_val = float(grouped.get(shift, 0)) / divisor
        result[shift] = round(raw_val, decimals) if decimals > 0 else int(round(raw_val))

    result["Total"] = sum(result[s] for s in ["1st Shift", "2nd Shift", "3rd Shift"])
    if decimals > 0:
        result["Total"] = round(result["Total"], decimals)
    return result


def combine_metrics(d1: dict, d2: dict) -> dict:
    return {
        "1st Shift": d1.get("1st Shift", 0) + d2.get("1st Shift", 0),
        "2nd Shift": d1.get("2nd Shift", 0) + d2.get("2nd Shift", 0),
        "3rd Shift": d1.get("3rd Shift", 0) + d2.get("3rd Shift", 0),
        "Total": d1.get("Total", 0) + d2.get("Total", 0)
    }


def combine_three_metrics(d1: dict, d2: dict, d3: dict) -> dict:
    return {
        "1st Shift": d1.get("1st Shift", 0) + d2.get("1st Shift", 0) + d3.get("1st Shift", 0),
        "2nd Shift": d1.get("2nd Shift", 0) + d2.get("2nd Shift", 0) + d3.get("2nd Shift", 0),
        "3rd Shift": d1.get("3rd Shift", 0) + d2.get("3rd Shift", 0) + d3.get("3rd Shift", 0),
        "Total": d1.get("Total", 0) + d2.get("Total", 0) + d3.get("Total", 0)
    }


def divide_metrics(num_dict: dict, den_dict: dict) -> dict:
    res = {}
    for shift in ["1st Shift", "2nd Shift", "3rd Shift", "Total"]:
        n = num_dict.get(shift, 0)
        d = den_dict.get(shift, 0)
        res[shift] = int(round(n / d)) if d > 0 else 0
    return res


# 🆕 NEW: percentage helper — same shape/contract as divide_metrics (per-shift
# + Total keys), but expressed as num/den * 100, rounded to a whole number
# (consistent with the other integer metrics in this dashboard).
# Purely additive: does not alter divide_metrics or anything that already
# calls it, and is only used below to add the new "Scanning %" SLA row.
def get_percentage_metrics(num_dict: dict, den_dict: dict, decimals: int = 0) -> dict:
    res = {}
    for shift in ["1st Shift", "2nd Shift", "3rd Shift", "Total"]:
        n = num_dict.get(shift, 0)
        d = den_dict.get(shift, 0)
        pct = (n / d) * 100 if d > 0 else 0
        res[shift] = round(pct, decimals) if decimals > 0 else int(round(pct))
    return res



def build_buildup_df(df_uplift: pd.DataFrame) -> pd.DataFrame:
    df_up_sub = (
        df_uplift[['uld_release_date_time', 'gross_wgt', 'uld_no', 'pcs', 'awb_no', 'flt_no']]
        .rename(columns={'uld_release_date_time': 'shift_time'})
        if not df_uplift.empty else pd.DataFrame()
    )
    return df_up_sub



# --- New helper: proper distinct-count across combined tables + shifts ---
# ---------------function added after live-------------------
def get_combined_unique_metric(dfs_and_cols: list, datetime_col_name: str = 'xray_date_time') -> dict:
    """
    dfs_and_cols: list of (df, datetime_col, metric_col) tuples from different tables.
    Combines them into ONE frame first, then dedupes serial_no/awb_no correctly
    both within a shift AND across shifts/tables for the Total.
    """
    frames = []
    for df, dt_col, metric_col in dfs_and_cols:
        if df.empty or dt_col not in df.columns or metric_col not in df.columns:
            continue
        sub = df[[dt_col, metric_col]].copy()
        sub.columns = [datetime_col_name, 'metric_val']
        frames.append(sub)

    result = {"1st Shift": 0, "2nd Shift": 0, "3rd Shift": 0, "Total": 0}
    if not frames:
        return result

    combined = pd.concat(frames, ignore_index=True)
    combined[datetime_col_name] = pd.to_datetime(combined[datetime_col_name], errors='coerce')
    combined = combined.dropna(subset=[datetime_col_name])
    combined = combined[combined['metric_val'].astype(str).str.strip() != '']

    def assign_shift_utc(row):
        h_float = row[datetime_col_name].hour + (row[datetime_col_name].minute / 60)
        if 0.5 <= h_float < 8.5: return '1st Shift'
        elif 8.5 <= h_float < 16.5: return '2nd Shift'
        else: return '3rd Shift'

    combined['shift'] = combined.apply(assign_shift_utc, axis=1)

    grouped = combined.groupby('shift')['metric_val'].nunique().to_dict()
    for shift in ["1st Shift", "2nd Shift", "3rd Shift"]:
        result[shift] = int(grouped.get(shift, 0))

    # ✅ Total = distinct count over the ENTIRE combined dataset (dedup across
    # shifts AND across all source tables) — NOT sum of per-shift counts.
    result["Total"] = int(combined['metric_val'].nunique())
    return result


# ============================================================
# 🆕 NEW: FULL DAY (calendar day) HELPER — purely additive
# ============================================================

def add_fullday_column(shift_dict: dict, fullday_shift_dict: dict, fullday_label: str) -> dict:
    """
    Takes the existing shift-metrics dict (1st/2nd/3rd Shift + Total) and
    appends one more key for the full calendar-day figure, without
    modifying any existing keys.
    """
    merged = dict(shift_dict)  # copy — don't mutate original
    merged[fullday_label] = fullday_shift_dict.get("Total", 0)
    return merged


# ============================================================
#  SUMMARY ENDPOINT
# ============================================================
@router.get("/dashboard/summary")
async def get_dashboard_summary(
    target_date: str = Query(..., description="Format: YYYY-MM-DD"),
    db: AsyncSession = Depends(get_db)
):
    # IST 6 AM = UTC 00:30
    start_dt = datetime.strptime(target_date, "%Y-%m-%d") + timedelta(hours=0, minutes=30)
    end_dt = start_dt + timedelta(days=1)   # n -> n+1 date logic

    data = await fetch_all_dashboard_data(db, start_dt, end_dt)
    df_uplift      = data["uplift"]
    df_car_msg     = data["car_msg"]
    df_loaded      = data["loaded"]
    df_imp_seg     = data["imp_seg"]
    df_exp_tp      = data["exp_tp"]
    df_xray        = data["xray"]
    df_imp_tp_xray = data["imp_tp_xray"]
    df_exp_tp_xray = data["exp_tp_xray"]
    df_screening    = data["screening"]

    # ============================================================
    # 🆕 NEW: Full Day (calendar day) dataset — 00:00 to 23:59:59 of target_date
    # Completely separate fetch, does not touch/replace the operational

    fullday_start_dt = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(hours=5, minutes=30)
    fullday_end_dt = fullday_start_dt + timedelta(days=1)
    fullday_label = f"{target_date} (00:00 to 23:59)"

    fullday_data = await fetch_all_dashboard_data(db, fullday_start_dt, fullday_end_dt)
    fd_uplift      = fullday_data["uplift"]
    fd_car_msg     = fullday_data["car_msg"]
    fd_imp_seg     = fullday_data["imp_seg"]
    fd_exp_tp      = fullday_data["exp_tp"]
    fd_xray        = fullday_data["xray"]
    fd_imp_tp_xray = fullday_data["imp_tp_xray"]
    fd_exp_tp_xray = fullday_data["exp_tp_xray"]
    fd_screening   = fullday_data["screening"]

    # --- TP Tonnage (weight -> MT) ---
    tp_tonnage_wgt = combine_metrics(
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0)
    )
    # 🆕 full-day mirror
    fd_tp_tonnage_wgt = combine_metrics(
        get_shift_metrics(fd_imp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0),
        get_shift_metrics(fd_exp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0)
    )

    imp_awb = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'awb_no', 'nunique')
    imp_pcs = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'pcs', 'sum')
    imp_wgt = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)

    # 🆕 full-day mirror
    fd_imp_awb = get_shift_metrics(fd_imp_seg, 'tfd_date_time', 'awb_no', 'nunique')
    fd_imp_pcs = get_shift_metrics(fd_imp_seg, 'tfd_date_time', 'pcs', 'sum')
    fd_imp_wgt = get_shift_metrics(fd_imp_seg, 'tfd_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)

    exp_awb = get_shift_metrics(df_exp_tp, 'xray_date_time', 'awb_no', 'nunique')
    exp_pcs = get_shift_metrics(df_exp_tp, 'xray_date_time', 'rec_pcs', 'sum')
    exp_wgt = get_shift_metrics(df_exp_tp, 'xray_date_time', 'received_wgt', 'sum', divisor=1000, decimals=0)

    # 🆕 full-day mirror
    fd_exp_awb = get_shift_metrics(fd_exp_tp, 'xray_date_time', 'awb_no', 'nunique')
    fd_exp_pcs = get_shift_metrics(fd_exp_tp, 'xray_date_time', 'rec_pcs', 'sum')
    fd_exp_wgt = get_shift_metrics(fd_exp_tp, 'xray_date_time', 'received_wgt', 'sum', divisor=1000, decimals=0)

    xr_awb = get_shift_metrics(df_xray, 'xray_date_time', 'awb_no', 'nunique')
    xr_pcs = get_shift_metrics(df_xray, 'xray_date_time', 'pcs', 'sum')
    xr_wgt = get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
    xr_mac = get_shift_metrics(df_xray, 'xray_date_time', 'serial_no', 'nunique')

    # 🆕 full-day mirror
    fd_xr_wgt = get_shift_metrics(fd_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)

    # total_xray_awb = combine_three_metrics(
    #     xr_awb,
    #     get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'awb_no', 'nunique'),
    #     get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'awb_no', 'nunique')
    # )

     #changes after live....
    total_xray_awb = get_combined_unique_metric([
    (df_xray, 'xray_date_time', 'awb_no'),
    (df_imp_tp_xray, 'xray_date_time', 'awb_no'),
    (df_exp_tp_xray, 'xray_date_time', 'awb_no'),
])
    # 🆕 full-day mirror
    fd_total_xray_awb = get_combined_unique_metric([
        (fd_xray, 'xray_date_time', 'awb_no'),
        (fd_imp_tp_xray, 'xray_date_time', 'awb_no'),
        (fd_exp_tp_xray, 'xray_date_time', 'awb_no'),
    ])

    total_xray_pcs = combine_three_metrics(
        xr_pcs,
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'pcs', 'sum'),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'pcs', 'sum')
    )
    # 🆕 full-day mirror
    fd_total_xray_pcs = combine_three_metrics(
        get_shift_metrics(fd_xray, 'xray_date_time', 'pcs', 'sum'),
        get_shift_metrics(fd_imp_tp_xray, 'xray_date_time', 'pcs', 'sum'),
        get_shift_metrics(fd_exp_tp_xray, 'xray_date_time', 'pcs', 'sum')
    )
    #changes after live....
    # total_xray_mac = combine_three_metrics(
    #     xr_mac,
    #     get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'serial_no', 'nunique'),
    #     get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'serial_no', 'nunique')
    # )
    total_xray_mac = get_combined_unique_metric([
    (df_xray, 'xray_date_time', 'serial_no'),
    (df_imp_tp_xray, 'xray_date_time', 'serial_no'),
    (df_exp_tp_xray, 'xray_date_time', 'serial_no'),
])
    # 🆕 full-day mirror
    fd_total_xray_mac = get_combined_unique_metric([
        (fd_xray, 'xray_date_time', 'serial_no'),
        (fd_imp_tp_xray, 'xray_date_time', 'serial_no'),
        (fd_exp_tp_xray, 'xray_date_time', 'serial_no'),
    ])

    prod_pcs = divide_metrics(total_xray_pcs, total_xray_mac)
    # 🆕 full-day mirror
    fd_prod_pcs = divide_metrics(fd_total_xray_pcs, fd_total_xray_mac)

    # Numerator already in MT -> result is MT/machine
    prod_wgt = divide_metrics(
        combine_three_metrics(
            xr_wgt,
            get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
            get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
        ),
        total_xray_mac
    )
    # 🆕 full-day mirror
    fd_prod_wgt = divide_metrics(
        combine_three_metrics(
            fd_xr_wgt,
            get_shift_metrics(fd_imp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
            get_shift_metrics(fd_exp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
        ),
        fd_total_xray_mac
    )

    df_uplift_scanning = (
        df_uplift[~df_uplift['shc'].astype(str).str.upper().str.contains('PER|PEM', na=False)]
        if not df_uplift.empty and 'shc' in df_uplift.columns else df_uplift
    )
    # 🆕 full-day mirror
    fd_uplift_scanning = (
        fd_uplift[~fd_uplift['shc'].astype(str).str.upper().str.contains('PER|PEM', na=False)]
        if not fd_uplift.empty and 'shc' in fd_uplift.columns else fd_uplift
    )


    df_buildup = build_buildup_df(df_uplift)   #-----------------changes after live-----------------
    sla_screening = get_shift_metrics(df_screening, 'loaded_at', 'gross_wt', 'sum', divisor=1000, decimals=0)
    sla_scanning_new = get_shift_metrics(df_uplift_scanning, 'uld_release_date_time', 'pcs', 'sum')

    # 🆕 full-day mirror
    fd_buildup = build_buildup_df(fd_uplift)
    fd_sla_screening = get_shift_metrics(fd_screening, 'loaded_at', 'gross_wt', 'sum', divisor=1000, decimals=0)
    fd_sla_scanning_new = get_shift_metrics(fd_uplift_scanning, 'uld_release_date_time', 'pcs', 'sum')

    # 🆕 NEW: captured into a variable so it can be reused both in the
    # Build_Up section below (same value/behaviour as before) and as the
    # denominator for the new "Scanning %" row in SLA. No logic change to
    # the number itself, just avoiding recomputation.
    buildup_pcs = get_shift_metrics(df_buildup, 'shift_time', 'pcs', 'sum')
    # 🆕 full-day mirror
    fd_buildup_pcs = get_shift_metrics(fd_buildup, 'shift_time', 'pcs', 'sum')

    # 🆕 NEW: Scanning (Pcs) as a percentage of Build Up No. of Pcs, per shift + Total.
    sla_scanning_pct = get_percentage_metrics(sla_scanning_new, buildup_pcs)
    # 🆕 full-day mirror
    fd_sla_scanning_pct = get_percentage_metrics(fd_sla_scanning_new, fd_buildup_pcs)

    return {
        "date": target_date,
        "sections": {
            "Export_Tonnage": {
                "Gross Wgt (MT)": add_fullday_column(
                    get_shift_metrics(df_uplift, 'uld_release_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                    get_shift_metrics(fd_uplift, 'uld_release_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                    fullday_label
                ),
                "Chg Wgt (MT)": add_fullday_column(
                    get_shift_metrics(df_uplift, 'uld_release_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0),
                    get_shift_metrics(fd_uplift, 'uld_release_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0),
                    fullday_label
                )
            },
            "TP_Tonnage": {
                "Received Chg Wgt (MT)": add_fullday_column(tp_tonnage_wgt, fd_tp_tonnage_wgt, fullday_label)
            },
            "TD Tonnage": {
                "Airway Bill Count": add_fullday_column(
                    get_shift_metrics(df_car_msg, 'car_msg_date_time', 'awb_no', 'nunique'),
                    get_shift_metrics(fd_car_msg, 'car_msg_date_time', 'awb_no', 'nunique'),
                    fullday_label
                ),
                "Piece Count": add_fullday_column(
                    get_shift_metrics(df_car_msg, 'car_msg_date_time', 'pcs', 'sum'),
                    get_shift_metrics(fd_car_msg, 'car_msg_date_time', 'pcs', 'sum'),
                    fullday_label
                ),
                "Gross Wgt (MT)": add_fullday_column(
                    get_shift_metrics(df_car_msg, 'car_msg_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                    get_shift_metrics(fd_car_msg, 'car_msg_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                    fullday_label
                )
            },
            "TP": {
                "No. of AWB": add_fullday_column(
                    combine_metrics(imp_awb, exp_awb),
                    combine_metrics(fd_imp_awb, fd_exp_awb),
                    fullday_label
                ),
                "No. of Pieces": add_fullday_column(
                    combine_metrics(imp_pcs, exp_pcs),
                    combine_metrics(fd_imp_pcs, fd_exp_pcs),
                    fullday_label
                ),
                "Gross Wgt (MT)": add_fullday_column(
                    combine_metrics(imp_wgt, exp_wgt),
                    combine_metrics(fd_imp_wgt, fd_exp_wgt),
                    fullday_label
                )
            },
            "X_Ray": {
                "Airway Bill Count": add_fullday_column(total_xray_awb, fd_total_xray_awb, fullday_label),
                "Piece Count": add_fullday_column(total_xray_pcs, fd_total_xray_pcs, fullday_label),
                "No of Machine Operated": add_fullday_column(total_xray_mac, fd_total_xray_mac, fullday_label),
                "Machine Productivity (in Piece)": add_fullday_column(prod_pcs, fd_prod_pcs, fullday_label),
                "Machine Productivity (MT)": add_fullday_column(prod_wgt, fd_prod_wgt, fullday_label)
            },
            # "Build_Up": {
            #     "Gross Wgt (MT)": get_shift_metrics(df_buildup, 'shift_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
            #     "No. of Uld": get_shift_metrics(df_buildup, 'shift_time', 'uld_no', 'nunique'),
            #     "No. of Pcs": get_shift_metrics(df_buildup, 'shift_time', 'pcs', 'sum'),
            #     "No. of AWB": get_shift_metrics(df_buildup, 'shift_time', 'awb_no', 'nunique'),
            #     "No. of Flight": get_shift_metrics(df_buildup, 'shift_time', 'flt_no', 'nunique')
            # },

            # ----------------changes after live----------------
            "Build_Up": {
            "Gross Wgt (MT)": add_fullday_column(
                get_shift_metrics(df_buildup, 'shift_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                get_shift_metrics(fd_buildup, 'shift_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                fullday_label
            ),
            "No. of Uld": add_fullday_column(
                get_combined_unique_metric([(df_buildup, 'shift_time', 'uld_no')], datetime_col_name='shift_time'),
                get_combined_unique_metric([(fd_buildup, 'shift_time', 'uld_no')], datetime_col_name='shift_time'),
                fullday_label
            ),
            "No. of Pcs": add_fullday_column(buildup_pcs, fd_buildup_pcs, fullday_label),  # 🆕 reused variable — same value as before (get_shift_metrics(df_buildup, 'shift_time', 'pcs', 'sum'))
            "No. of AWB": add_fullday_column(
                get_combined_unique_metric([(df_buildup, 'shift_time', 'awb_no')], datetime_col_name='shift_time'),
                get_combined_unique_metric([(fd_buildup, 'shift_time', 'awb_no')], datetime_col_name='shift_time'),
                fullday_label
            ),
            "No. of Flight": add_fullday_column(
                get_combined_unique_metric([(df_buildup, 'shift_time', 'flt_no')], datetime_col_name='shift_time'),
                get_combined_unique_metric([(fd_buildup, 'shift_time', 'flt_no')], datetime_col_name='shift_time'),
                fullday_label
            )
},


            "SLA": {
                "X-Ray Gross Wgt (MT)": add_fullday_column(
                    get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                    get_shift_metrics(fd_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                    fullday_label
                ),
                "Screening Gross Wgt (MT)": add_fullday_column(sla_screening, fd_sla_screening, fullday_label),
                "Scanning (Pcs)": add_fullday_column(sla_scanning_new, fd_sla_scanning_new, fullday_label),
                "Scanning (Pcs) %": add_fullday_column(sla_scanning_pct, fd_sla_scanning_pct, fullday_label)  # 🆕 NEW: Scanning (Pcs) / Build Up No. of Pcs * 100, per shift + Total

            }
        }
    }




# ============================================================
#  EXPORT ENDPOINT (updated to match frontend dashboard)
# ============================================================

SHIFT_COLS_BASE = ["1st Shift", "2nd Shift", "3rd Shift", "Total"]


def compute_col_widths(sections):
    """
    Scans all descriptions and section titles to size column B automatically.
    Numeric columns (C-G) get a sensible fixed width.
    """
    max_desc_len = len("Description")
    max_sno_len = len("S.No")

    for section_title, items in sections:
        max_desc_len = max(max_desc_len, len(section_title))
        section_no = section_title.split(".")[0]
        for idx, (desc, _metrics, _is_pct, _rule) in enumerate(items, start=1):
            max_desc_len = max(max_desc_len, len(desc))
            max_sno_len = max(max_sno_len, len(f"{section_no}.{idx}"))

    return {
        "sno": max_sno_len + 2,
        "desc": max_desc_len + 2,
        "shift": 18,   # fixed
        "total": 14,   # fixed
        "fullday": 22  # fixed width for the new 00:00 to 23:59 column
    }


@router.get("/dashboard/export")
async def export_dashboard(
    target_date: str = Query(..., description="Format: YYYY-MM-DD"),
    export_format: str = Query("excel", regex="^(excel|csv)$"),
    db: AsyncSession = Depends(get_db)
):
    # ============================================================
    #  OPERATIONAL WINDOW (6 AM to 6 AM)
    # ============================================================
    start_dt = datetime.strptime(target_date, "%Y-%m-%d") + timedelta(hours=0, minutes=30)
    end_dt = start_dt + timedelta(days=1)

    data = await fetch_all_dashboard_data(db, start_dt, end_dt)
    df_uplift      = data["uplift"]
    df_car_msg     = data["car_msg"]
    df_imp_seg     = data["imp_seg"]
    df_exp_tp      = data["exp_tp"]
    df_xray        = data["xray"]
    df_imp_tp_xray = data["imp_tp_xray"]
    df_exp_tp_xray = data["exp_tp_xray"]
    df_screening   = data["screening"]

    # ============================================================
    # 🆕 NEW: FULL DAY (00:00 to 23:59)
    # ============================================================
    fullday_start_dt = datetime.strptime(target_date, "%Y-%m-%d") - timedelta(hours=5, minutes=30)
    fullday_end_dt = fullday_start_dt + timedelta(days=1)
    fullday_label = f"{target_date}\n(00:00 to 23:59)"

    fullday_data = await fetch_all_dashboard_data(db, fullday_start_dt, fullday_end_dt)
    fd_uplift      = fullday_data["uplift"]
    fd_car_msg     = fullday_data["car_msg"]
    fd_imp_seg     = fullday_data["imp_seg"]
    fd_exp_tp      = fullday_data["exp_tp"]
    fd_xray        = fullday_data["xray"]
    fd_imp_tp_xray = fullday_data["imp_tp_xray"]
    fd_exp_tp_xray = fullday_data["exp_tp_xray"]
    fd_screening   = fullday_data["screening"]

    # ---------------- same computations as /dashboard/summary ----------------
    # TP Tonnage
    tp_tonnage_wgt = combine_metrics(
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0)
    )
    fd_tp_tonnage_wgt = combine_metrics(
        get_shift_metrics(fd_imp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0),
        get_shift_metrics(fd_exp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0)
    )

    # TP 
    imp_awb = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'awb_no', 'nunique')
    imp_pcs = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'pcs', 'sum')
    imp_wgt = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
    
    fd_imp_awb = get_shift_metrics(fd_imp_seg, 'tfd_date_time', 'awb_no', 'nunique')
    fd_imp_pcs = get_shift_metrics(fd_imp_seg, 'tfd_date_time', 'pcs', 'sum')
    fd_imp_wgt = get_shift_metrics(fd_imp_seg, 'tfd_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)

    exp_awb = get_shift_metrics(df_exp_tp, 'xray_date_time', 'awb_no', 'nunique')
    exp_pcs = get_shift_metrics(df_exp_tp, 'xray_date_time', 'rec_pcs', 'sum')
    exp_wgt = get_shift_metrics(df_exp_tp, 'xray_date_time', 'received_wgt', 'sum', divisor=1000, decimals=0)

    fd_exp_awb = get_shift_metrics(fd_exp_tp, 'xray_date_time', 'awb_no', 'nunique')
    fd_exp_pcs = get_shift_metrics(fd_exp_tp, 'xray_date_time', 'rec_pcs', 'sum')
    fd_exp_wgt = get_shift_metrics(fd_exp_tp, 'xray_date_time', 'received_wgt', 'sum', divisor=1000, decimals=0)

    # XRAY
    xr_wgt = get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
    fd_xr_wgt = get_shift_metrics(fd_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)

    tot_xr_awb = get_combined_unique_metric([
        (df_xray, 'xray_date_time', 'awb_no'),
        (df_imp_tp_xray, 'xray_date_time', 'awb_no'),
        (df_exp_tp_xray, 'xray_date_time', 'awb_no'),
    ])
    fd_total_xray_awb = get_combined_unique_metric([
        (fd_xray, 'xray_date_time', 'awb_no'),
        (fd_imp_tp_xray, 'xray_date_time', 'awb_no'),
        (fd_exp_tp_xray, 'xray_date_time', 'awb_no'),
    ])

    tot_xr_pcs = combine_three_metrics(
        get_shift_metrics(df_xray, 'xray_date_time', 'pcs', 'sum'),
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'pcs', 'sum'),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'pcs', 'sum')
    )
    fd_total_xray_pcs = combine_three_metrics(
        get_shift_metrics(fd_xray, 'xray_date_time', 'pcs', 'sum'),
        get_shift_metrics(fd_imp_tp_xray, 'xray_date_time', 'pcs', 'sum'),
        get_shift_metrics(fd_exp_tp_xray, 'xray_date_time', 'pcs', 'sum')
    )

    tot_xr_mac = get_combined_unique_metric([
        (df_xray, 'xray_date_time', 'serial_no'),
        (df_imp_tp_xray, 'xray_date_time', 'serial_no'),
        (df_exp_tp_xray, 'xray_date_time', 'serial_no'),
    ])
    fd_total_xray_mac = get_combined_unique_metric([
        (fd_xray, 'xray_date_time', 'serial_no'),
        (fd_imp_tp_xray, 'xray_date_time', 'serial_no'),
        (fd_exp_tp_xray, 'xray_date_time', 'serial_no'),
    ])

    prod_pcs = divide_metrics(tot_xr_pcs, tot_xr_mac)
    fd_prod_pcs = divide_metrics(fd_total_xray_pcs, fd_total_xray_mac)

    prod_wgt = divide_metrics(
        combine_three_metrics(
            xr_wgt,
            get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
            get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
        ),
        tot_xr_mac
    )
    fd_prod_wgt = divide_metrics(
        combine_three_metrics(
            fd_xr_wgt,
            get_shift_metrics(fd_imp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
            get_shift_metrics(fd_exp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
        ),
        fd_total_xray_mac
    )

    # Build Up & SLA
    df_uplift_scanning = (
        df_uplift[~df_uplift['shc'].astype(str).str.upper().str.contains('PER|PEM', na=False)]
        if not df_uplift.empty and 'shc' in df_uplift.columns else df_uplift
    )
    fd_uplift_scanning = (
        fd_uplift[~fd_uplift['shc'].astype(str).str.upper().str.contains('PER|PEM', na=False)]
        if not fd_uplift.empty and 'shc' in fd_uplift.columns else fd_uplift
    )

    df_buildup = build_buildup_df(df_uplift)
    fd_buildup = build_buildup_df(fd_uplift)

    sla_screening       = get_shift_metrics(df_screening, 'loaded_at', 'gross_wt', 'sum', divisor=1000, decimals=0)
    sla_scanning_new    = get_shift_metrics(df_uplift_scanning, 'uld_release_date_time', 'pcs', 'sum')
    buildup_pcs         = get_shift_metrics(df_buildup, 'shift_time', 'pcs', 'sum')
    sla_scanning_pct    = get_percentage_metrics(sla_scanning_new, buildup_pcs)

    fd_sla_screening    = get_shift_metrics(fd_screening, 'loaded_at', 'gross_wt', 'sum', divisor=1000, decimals=0)
    fd_sla_scanning_new = get_shift_metrics(fd_uplift_scanning, 'uld_release_date_time', 'pcs', 'sum')
    fd_buildup_pcs      = get_shift_metrics(fd_buildup, 'shift_time', 'pcs', 'sum')
    fd_sla_scanning_pct = get_percentage_metrics(fd_sla_scanning_new, fd_buildup_pcs)

    # ---------------- structured sections (mirrors frontend numbering) ----------------
    # Each item: (description, metrics_dict, is_percent, highlight_rule)
    sections = [
        ("1. EXPORT TONNAGE", [
            ("Gross Wgt (MT)", add_fullday_column(
                get_shift_metrics(df_uplift, 'uld_release_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                get_shift_metrics(fd_uplift, 'uld_release_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0), fullday_label), False, None),
            ("Chg Wgt (MT)", add_fullday_column(
                get_shift_metrics(df_uplift, 'uld_release_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0),
                get_shift_metrics(fd_uplift, 'uld_release_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0), fullday_label), False, None),
        ]),
        ("2. TP TONNAGE", [
            ("Received Chg Wgt (MT)", add_fullday_column(tp_tonnage_wgt, fd_tp_tonnage_wgt, fullday_label), False, None),
        ]),
        ("3. TD TONNAGE", [
            ("Airway Bill Count", add_fullday_column(
                get_shift_metrics(df_car_msg, 'car_msg_date_time', 'awb_no', 'nunique'),
                get_shift_metrics(fd_car_msg, 'car_msg_date_time', 'awb_no', 'nunique'), fullday_label), False, None),
            ("Piece Count", add_fullday_column(
                get_shift_metrics(df_car_msg, 'car_msg_date_time', 'pcs', 'sum'),
                get_shift_metrics(fd_car_msg, 'car_msg_date_time', 'pcs', 'sum'), fullday_label), False, None),
            ("Gross Wgt (MT)", add_fullday_column(
                get_shift_metrics(df_car_msg, 'car_msg_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                get_shift_metrics(fd_car_msg, 'car_msg_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0), fullday_label), False, None),
        ]),
        ("4. TP", [
            ("No. of AWB", add_fullday_column(combine_metrics(imp_awb, exp_awb), combine_metrics(fd_imp_awb, fd_exp_awb), fullday_label), False, None),
            ("No. of Pieces", add_fullday_column(combine_metrics(imp_pcs, exp_pcs), combine_metrics(fd_imp_pcs, fd_exp_pcs), fullday_label), False, None),
            ("Gross Wgt (MT)", add_fullday_column(combine_metrics(imp_wgt, exp_wgt), combine_metrics(fd_imp_wgt, fd_exp_wgt), fullday_label), False, None),
        ]),
        ("5. X-RAY", [
            ("Airway Bill Count", add_fullday_column(tot_xr_awb, fd_total_xray_awb, fullday_label), False, None),
            ("Piece Count", add_fullday_column(tot_xr_pcs, fd_total_xray_pcs, fullday_label), False, None),
            ("No of Machine Operated", add_fullday_column(tot_xr_mac, fd_total_xray_mac, fullday_label), False, None),
            ("Machine Productivity (in Piece)", add_fullday_column(prod_pcs, fd_prod_pcs, fullday_label), False, None),
            ("Machine Productivity (MT)", add_fullday_column(prod_wgt, fd_prod_wgt, fullday_label), False, None),
        ]),
        ("6. BUILD UP", [
            ("Gross Wgt (MT)", add_fullday_column(
                get_shift_metrics(df_buildup, 'shift_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                get_shift_metrics(fd_buildup, 'shift_time', 'gross_wgt', 'sum', divisor=1000, decimals=0), fullday_label), False, None),
            ("No. of Uld", add_fullday_column(
                get_combined_unique_metric([(df_buildup, 'shift_time', 'uld_no')], datetime_col_name='shift_time'),
                get_combined_unique_metric([(fd_buildup, 'shift_time', 'uld_no')], datetime_col_name='shift_time'), fullday_label), False, None),
            ("No. of Pcs", add_fullday_column(buildup_pcs, fd_buildup_pcs, fullday_label), False, None),
            ("No. of AWB", add_fullday_column(
                get_combined_unique_metric([(df_buildup, 'shift_time', 'awb_no')], datetime_col_name='shift_time'),
                get_combined_unique_metric([(fd_buildup, 'shift_time', 'awb_no')], datetime_col_name='shift_time'), fullday_label), False, None),
            ("No. of Flight", add_fullday_column(
                get_combined_unique_metric([(df_buildup, 'shift_time', 'flt_no')], datetime_col_name='shift_time'),
                get_combined_unique_metric([(fd_buildup, 'shift_time', 'flt_no')], datetime_col_name='shift_time'), fullday_label), False, None),
        ]),
        ("7. SLA", [
            # 🆕 Changed rule from "xray_target" to None
            ("X-Ray Gross Wgt (MT)", add_fullday_column(xr_wgt, fd_xr_wgt, fullday_label), False, None),
            ("Screening Gross Wgt (MT)", add_fullday_column(sla_screening, fd_sla_screening, fullday_label), False, None),
            ("Scanning (Pcs)", add_fullday_column(sla_scanning_new, fd_sla_scanning_new, fullday_label), False, None),
            ("Scanning (Pcs) %", add_fullday_column(sla_scanning_pct, fd_sla_scanning_pct, fullday_label), True, None),
        ]),
    ]

    output = io.BytesIO()
    
    # Define columns to render, including the dynamic 5th column
    export_columns = SHIFT_COLS_BASE + [fullday_label]

    # Format the date for the Excel headers to match the UI (e.g., "24-Jun-2026")
    ui_date_str = datetime.strptime(target_date, "%Y-%m-%d").strftime("%d-%b-%Y")

    if export_format == "csv":
        # Map internal shift keys to exact display headers for CSV
        csv_header_mapping = {
            "1st Shift": "Morning 06:00 - 14:00",
            "2nd Shift": "Afternoon 14:00 - 22:00",
            "3rd Shift": "Evening 22:00 - 06:00 (next day also)",
            "Total": f"{ui_date_str} (Shifts Total)",
            fullday_label: f"{ui_date_str} (00:00 - 23:59)"
        }
        
        rows = []
        for section_title, items in sections:
            base_row = {"S.No.": section_title, "Description": ""}
            for c in export_columns:
                base_row[csv_header_mapping[c]] = ""
            rows.append(base_row)
            
            section_no = section_title.split(".")[0]
            for idx, (desc, metrics, is_pct, _rule) in enumerate(items, start=1):
                row = {"S.No.": f"{section_no}.{idx}", "Description": desc}
                for c in export_columns:
                    val = metrics.get(c, 0)
                    row[csv_header_mapping[c]] = f"{val}%" if is_pct else val
                rows.append(row)
                
        df_final = pd.DataFrame(rows)
        df_final.to_csv(output, index=False, encoding='utf-8')
        media_type, filename = "text/csv", f"Dashboard_{target_date}.csv"

    else:
        workbook = xlsxwriter.Workbook(output, {"in_memory": True})
        ws = workbook.add_worksheet("Export Dashboard")
        
        widths = compute_col_widths(sections)

        # ---------------- formats (matching frontend palette) ----------------
        fmt_title = workbook.add_format({"bold": True, "font_size": 16, "align": "center", "valign": "vcenter"})
        fmt_subtitle = workbook.add_format({"italic": True, "font_size": 10, "font_color": "#555555", "align": "center", "valign": "vcenter"})
        
        # Headers
        fmt_header = workbook.add_format({"bold": True, "bg_color": "#EAF1FB", "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
        fmt_header_total = workbook.add_format({"bold": True, "bg_color": "#FCE38A", "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
        fmt_header_fullday = workbook.add_format({"bold": True, "bg_color": "#A9DFBF", "border": 1, "align": "center", "valign": "vcenter", "text_wrap": True})
        
        # Section & Basic Text
        fmt_section = workbook.add_format({"bold": True, "bg_color": "#F3F4F6", "border": 1, "font_size": 10})
        fmt_sno = workbook.add_format({"border": 1, "align": "center", "font_color": "#6B7280"})
        fmt_desc = workbook.add_format({"border": 1})
        
        # Data Cells
        fmt_val = workbook.add_format({"border": 1, "align": "right", "num_format": "#,##0"})
        fmt_val_total = workbook.add_format({"border": 1, "align": "right", "num_format": "#,##0", "bg_color": "#FFF6DA", "bold": True})
        fmt_val_fullday = workbook.add_format({"border": 1, "align": "right", "num_format": "#,##0", "bg_color": "#E8F8F5", "bold": True})
        
        # Percentages
        fmt_pct = workbook.add_format({"border": 1, "align": "right", "num_format": "0\"%\""})
        fmt_pct_total = workbook.add_format({"border": 1, "align": "right", "num_format": "0\"%\"", "bg_color": "#FFF6DA", "bold": True})
        fmt_pct_fullday = workbook.add_format({"border": 1, "align": "right", "num_format": "0\"%\"", "bg_color": "#E8F8F5", "bold": True})

        # ---------------- column widths ----------------
        ws.set_column(0, 0, widths["sno"])
        ws.set_column(1, 1, widths["desc"])
        ws.set_column(2, 4, widths["shift"])
        ws.set_column(5, 5, widths["total"])
        ws.set_column(6, 6, widths["fullday"])

        # ---------------- title ----------------
        ws.merge_range(0, 0, 0, 6, "Export Operational Dashboard", fmt_title)
        ws.merge_range(1, 0, 1, 6, f"Generated Dashboard is of Date : {ui_date_str}", fmt_subtitle)
        ws.set_row(0, 26)
        ws.set_row(1, 18)

        # ---------------- column headers ----------------
        header_row = 3
        ws.write(header_row, 0, "S.No.", fmt_header)
        ws.write(header_row, 1, "Description", fmt_header)
        ws.write(header_row, 2, "Morning\n06:00 - 14:00", fmt_header)
        ws.write(header_row, 3, "Afternoon\n14:00 - 22:00", fmt_header)
        ws.write(header_row, 4, "Evening\n22:00 - 06:00 (next day also)", fmt_header)
        ws.write(header_row, 5, f"{ui_date_str}\n(Shifts Total)", fmt_header_total)
        ws.write(header_row, 6, f"{ui_date_str}\n(00:00 - 23:59)", fmt_header_fullday)
        ws.set_row(header_row, 30)
        ws.freeze_panes(header_row + 1, 0) 

        row = header_row + 1

        for section_title, items in sections:
            ws.merge_range(row, 0, row, 6, section_title, fmt_section)
            row += 1
            section_no = section_title.split(".")[0]
            for idx, (desc, metrics, is_pct, rule) in enumerate(items, start=1):
                ws.write(row, 0, f"{section_no}.{idx}", fmt_sno)
                ws.write(row, 1, desc, fmt_desc)

                for col_idx, shift_key in enumerate(export_columns, start=2):
                    val = metrics.get(shift_key, 0)

                    # Determine correct cell format strictly based on column (no more SLA red/green)
                    if is_pct:
                        if shift_key == "Total": cell_fmt = fmt_pct_total
                        elif shift_key == fullday_label: cell_fmt = fmt_pct_fullday
                        else: cell_fmt = fmt_pct
                    else:
                        if shift_key == "Total": cell_fmt = fmt_val_total
                        elif shift_key == fullday_label: cell_fmt = fmt_val_fullday
                        else: cell_fmt = fmt_val

                    ws.write(row, col_idx, val, cell_fmt)
                row += 1

        workbook.close()
        media_type = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet"
        filename = f"Dashboard_{target_date}.xlsx"

    output.seek(0)
    return StreamingResponse(
        output,
        media_type=media_type,
        headers={"Content-Disposition": f"attachment; filename={filename}"}
    )






# ===========================  ✌️✌️✌️✌️ Operational report Upload ====================================




from fastapi import APIRouter, UploadFile, File, Form, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, insert

from app.db.session import get_db
from app.core.dependency import verify_token_and_get_user

# ----------------- MODELS -----------------
# NOTE: fix this path if your actual folder is app.db.models.importOperation.Excel_dashboard
from app.db.models.digital_reports.export_dept.cargo_uplift_report import DigitalReportCargoUpliftReport
from app.db.models.digital_reports.export_dept.car_message_report import DigitalReportCarMessageReport
from app.db.models.digital_reports.export_dept.x_ray_report import DigitalReportXrayReport
from app.db.models.digital_reports.export_dept.import_tp_xray_report import DigitalReportImportTpXrayReport
from app.db.models.digital_reports.export_dept.export_tp_xray_report import DigitalReportExportTpXrayReport
from app.db.models.digital_reports.export_dept.export_loaded_inventory import DigitalReportExportLoadedInventory
from app.db.models.digital_reports.export_dept.export_transhipment_report import DigitalReportExportTranshipmentReport
from app.db.models.digital_reports.export_dept.import_segregation_report import DigitalReportImportSegregationReport
 


# ----------------- CLEANERS -----------------
# NOTE: each cleaner now takes (contents, filename, report_date) and must

from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.clean_cargo_uplift import process_cargo_uplift
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.clean_car_message import process_car_message
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.clean_xray import process_xray_report
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.clean_import_tp_xray import process_import_tp_xray
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.clean_export_tp_xray import process_export_tp_xray
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.clean_export_loaded import process_export_loaded_inventory
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.clean_import_segregation import process_import_segregation
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.clean_export_transhipment import process_export_transhipment




def _attach_uploaded_by(records: list[dict], emp_id: int) -> list[dict]:
    """Stamps every record with who uploaded it, same as pick_order.py's uploaded_by=emp_id."""
    for r in records:
        r["uploaded_by"] = emp_id
    return records


# ----------------- ENDPOINTS -----------------
@router.post("/cargo-uplift/upload")
async def upload_cargo_uplift(
    file: UploadFile = File(...),
    report_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    emp_id = int(current_user.emp_id)
    try:
        contents = await file.read()
        
        # ✅ Updated: Unpacking both dataframe and the dropped rows count
        df_cleaned, dropped_count = process_cargo_uplift(contents, file.filename, report_date)
        
        if df_cleaned.empty:
            raise HTTPException(status_code=400, detail="File is empty or contains no valid operational data.")

        await db.execute(
            delete(DigitalReportCargoUpliftReport).where(DigitalReportCargoUpliftReport.report_date == df_cleaned['report_date'].iloc[0])
        )

        records = _attach_uploaded_by(df_cleaned.to_dict(orient='records'), emp_id)
        if records:
            await db.execute(insert(DigitalReportCargoUpliftReport), records)

        await db.commit()
        
        # ✅ Success message with transparency for filtered rows
        msg = f"Successfully processed {len(records)} records for date: {report_date}."
        if dropped_count > 0:
            msg += f" Note: {dropped_count} rows were ignored due to date mismatch."
            
        return {"status": "success", "message": msg}
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/car-message/upload")
async def upload_car_message(
    file: UploadFile = File(...),
    report_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    emp_id = int(current_user.emp_id)
    try:
        contents = await file.read()
        
        # ✅ Updated: Unpacking both dataframe and the dropped rows count
        df_cleaned, dropped_count = process_car_message(contents, file.filename, report_date)
        
        if df_cleaned.empty:
            raise HTTPException(status_code=400, detail="File is empty or contains no valid operational data.")

        await db.execute(
            delete(DigitalReportCarMessageReport).where(DigitalReportCarMessageReport.report_date == df_cleaned['report_date'].iloc[0])
        )

        records = _attach_uploaded_by(df_cleaned.to_dict(orient='records'), emp_id)
        if records:
            await db.execute(insert(DigitalReportCarMessageReport), records)

        await db.commit()
        
        # ✅ Success message with transparency for filtered rows
        msg = f"Successfully processed {len(records)} records for date: {report_date}."
        if dropped_count > 0:
            msg += f" Note: {dropped_count} rows were ignored due to date mismatch."
            
        return {"status": "success", "message": msg}
    
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))                                                                                                                         
    

@router.post("/x-ray/upload")
async def upload_xray_report(
    file: UploadFile = File(...),
    report_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    emp_id = int(current_user.emp_id)
    try:
        contents = await file.read()
        
        # ✅ Updated: Unpacking both dataframe and the dropped rows count
        df_cleaned, dropped_count = process_xray_report(contents, file.filename, report_date)
        
        if df_cleaned.empty:
            raise HTTPException(status_code=400, detail="File is empty or contains no valid operational data.")

        await db.execute(
            delete(DigitalReportXrayReport).where(DigitalReportXrayReport.report_date == df_cleaned['report_date'].iloc[0])
        )

        records = _attach_uploaded_by(df_cleaned.to_dict(orient='records'), emp_id)
        if records:
            await db.execute(insert(DigitalReportXrayReport), records)

        await db.commit()
        
        # ✅ Message mein dropped_count add kar diya for better transparency
        msg = f"Successfully processed {len(records)} records for date: {report_date}."
        if dropped_count > 0:
            msg += f" Note: {dropped_count} rows were ignored due to date mismatch."
            
        return {"status": "success", "message": msg}
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/import-tp-xray/upload")
async def upload_import_tp_xray(
    file: UploadFile = File(...),
    report_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    emp_id = int(current_user.emp_id)
    try:
        contents = await file.read()
        
        # ✅ Updated: Unpacking both dataframe and the dropped rows count
        df_cleaned, dropped_count = process_import_tp_xray(contents, file.filename, report_date)
        
        if df_cleaned.empty:
            raise HTTPException(status_code=400, detail="File is empty or contains no valid operational data.")

        await db.execute(
            delete(DigitalReportImportTpXrayReport).where(DigitalReportImportTpXrayReport.report_date == df_cleaned['report_date'].iloc[0])
        )

        records = _attach_uploaded_by(df_cleaned.to_dict(orient='records'), emp_id)
        if records:
            await db.execute(insert(DigitalReportImportTpXrayReport), records)

        await db.commit()
        
        # ✅ Message mein dropped_count add kar diya
        msg = f"Successfully processed {len(records)} records for date: {report_date}."
        if dropped_count > 0:
            msg += f" Note: {dropped_count} rows were ignored due to date mismatch."
            
        return {"status": "success", "message": msg}
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))                                                                                                                         
    

@router.post("/export-tp-xray/upload")
async def upload_export_tp_xray(
    file: UploadFile = File(...),
    report_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    emp_id = int(current_user.emp_id)
    try:
        contents = await file.read()
        
        # ✅ Updated: Unpacking both dataframe and the dropped rows count
        df_cleaned, dropped_count = process_export_tp_xray(contents, file.filename, report_date)
        
        if df_cleaned.empty:
            raise HTTPException(status_code=400, detail="File is empty or contains no valid operational data.")

        await db.execute(
            delete(DigitalReportExportTpXrayReport).where(DigitalReportExportTpXrayReport.report_date == df_cleaned['report_date'].iloc[0])
        )

        records = _attach_uploaded_by(df_cleaned.to_dict(orient='records'), emp_id)
        if records:
            await db.execute(insert(DigitalReportExportTpXrayReport), records)

        await db.commit()
        
        # ✅ Dynamic message with dropped count
        msg = f"Successfully processed {len(records)} records for date: {report_date}."
        if dropped_count > 0:
            msg += f" Note: {dropped_count} rows were ignored due to date mismatch."
            
        return {"status": "success", "message": msg}
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export-loaded-inventory/upload")
async def upload_export_loaded_inventory(
    file: UploadFile = File(...),
    report_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    emp_id = int(current_user.emp_id)
    try:
        contents = await file.read()
        
        # ✅ Updated: Unpacking both dataframe and the dropped rows count
        df_cleaned, dropped_count = process_export_loaded_inventory(contents, file.filename, report_date)
        
        if df_cleaned.empty:
            raise HTTPException(status_code=400, detail="File is empty or contains no valid operational data.")

        await db.execute(
            delete(DigitalReportExportLoadedInventory).where(DigitalReportExportLoadedInventory.report_date == df_cleaned['report_date'].iloc[0])
        )

        records = _attach_uploaded_by(df_cleaned.to_dict(orient='records'), emp_id)
        if records:
            await db.execute(insert(DigitalReportExportLoadedInventory), records)

        await db.commit()
        
        # ✅ Dynamic message with dropped count transparency
        msg = f"Successfully processed {len(records)} records for date: {report_date}."
        if dropped_count > 0:
            msg += f" Note: {dropped_count} rows were ignored due to date mismatch."
            
        return {"status": "success", "message": msg}
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/export-transhipment/upload")
async def upload_export_transhipment(
    file: UploadFile = File(...),
    report_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    emp_id = int(current_user.emp_id)
    try:
        contents = await file.read()
        
        # ✅ Updated: Unpacking both dataframe and the dropped rows count
        df_cleaned, dropped_count = process_export_transhipment(contents, file.filename, report_date)
        
        if df_cleaned.empty:
            raise HTTPException(status_code=400, detail="File is empty or contains no valid operational data.")

        await db.execute(
            delete(DigitalReportExportTranshipmentReport).where(DigitalReportExportTranshipmentReport.report_date == df_cleaned['report_date'].iloc[0])
        )

        records = _attach_uploaded_by(df_cleaned.to_dict(orient='records'), emp_id)
        if records:
            await db.execute(insert(DigitalReportExportTranshipmentReport), records)

        await db.commit()
        
        # ✅ Dynamic message with dropped count transparency
        msg = f"Successfully processed {len(records)} records for date: {report_date}."
        if dropped_count > 0:
            msg += f" Note: {dropped_count} rows were ignored due to date mismatch."
            
        return {"status": "success", "message": msg}
        
    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))



@router.post("/import-segregation/upload")
async def upload_import_segregation(
    file: UploadFile = File(...),
    report_date: str = Form(...),
    db: AsyncSession = Depends(get_db),
    current_user=Depends(verify_token_and_get_user),
):
    emp_id = int(current_user.emp_id)
    try:
        contents = await file.read()
        
        # ✅ Updated: Unpacking both dataframe and the dropped rows count
        df_cleaned, dropped_count = process_import_segregation(contents, file.filename, report_date)
        
        if df_cleaned.empty:
            raise HTTPException(status_code=400, detail="File is empty or contains no valid operational data.")

        await db.execute(
            delete(DigitalReportImportSegregationReport).where(
                DigitalReportImportSegregationReport.report_date == df_cleaned['report_date'].iloc[0]
            )
        )

        records = _attach_uploaded_by(df_cleaned.to_dict(orient='records'), emp_id)
        if records:
            await db.execute(insert(DigitalReportImportSegregationReport), records)

        await db.commit()
        
        # ✅ Dynamic message with dropped count transparency
        msg = f"Successfully processed {len(records)} records for date: {report_date}."
        if dropped_count > 0:
            msg += f" Note: {dropped_count} rows were ignored due to date mismatch."
            
        return {"status": "success", "message": msg}
        
    except ValueError as ve:
       
        raise HTTPException(status_code=400, detail=str(ve))
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))

