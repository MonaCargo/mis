
# from fastapi import APIRouter, Depends, Query
# from sqlalchemy import text 
# from sqlalchemy.orm import Session
# from datetime import datetime, timedelta
# import pandas as pd
# from app.db.session import get_db 
# from fastapi.responses import StreamingResponse
# import io 

# router = APIRouter()

# # --- Helper Function for Shift Aggregation (Updated for UTC shift boundaries) ---
# # 🔄 CHANGE 1: Added `divisor` and `decimals` params.
# #    - divisor: value to divide the aggregated number by (e.g. 1000 to convert KG -> MT)
# #    - decimals: rounding precision (kept 0 so MT values show as whole numbers,
# #      e.g. 153029 kg -> 153 MT). Default divisor=1, decimals=0 means all
# #      existing (non-weight) calls behave EXACTLY as before — nothing breaks
# #      for pcs/awb/machine counts.
# def get_shift_metrics(df: pd.DataFrame, datetime_col: str, metric_col: str, agg_type: str = 'sum',
#                        divisor: float = 1, decimals: int = 0) -> dict:
#     result = {"1st Shift": 0, "2nd Shift": 0, "3rd Shift": 0, "Total": 0}
    
#     if df.empty or datetime_col not in df.columns or metric_col not in df.columns:
#         return result

#     df_clean = df.copy()
#     df_clean[datetime_col] = pd.to_datetime(df_clean[datetime_col], errors='coerce')
    
#     # 1. Nulls ko hatane ke bajaye 0 fill kar dein (Metric column ke liye)
#     # Yeh aapki calculation ko robust banayega
#     if agg_type == 'sum':
#         df_clean[metric_col] = pd.to_numeric(df_clean[metric_col], errors='coerce').fillna(0)
    
#     # 2. Dropna ab sirf tab karein agar datetime_col missing ho
#     df_clean = df_clean.dropna(subset=[datetime_col]).copy()
    
#     if agg_type in ['nunique', 'count']:
#         df_clean = df_clean[df_clean[metric_col].astype(str).str.strip() != '']

#     def assign_shift_utc(row):
#         # Convert time to fractional hours (e.g., 08:30 = 8.5)
#         h_float = row[datetime_col].hour + (row[datetime_col].minute / 60)
#         # Mapping IST shifts to UTC hours (IST = UTC + 5.5 hours)
#         # 1st Shift (06:00-14:00 IST) -> (00:30-08:30 UTC)
#         if 0.5 <= h_float < 8.5: return '1st Shift'
#         # 2nd Shift (14:00-22:00 IST) -> (08:30-16:30 UTC)
#         elif 8.5 <= h_float < 16.5: return '2nd Shift'
#         # 3rd Shift (22:00-06:00 IST) -> (16:30-24:00 UTC OR 00:00-00:30 UTC)
#         else: return '3rd Shift'
        
#     df_clean['shift'] = df_clean.apply(assign_shift_utc, axis=1)
    
#     if agg_type == 'sum':
#         grouped = df_clean.groupby('shift')[metric_col].sum().to_dict()
#     elif agg_type == 'nunique':
#         grouped = df_clean.groupby('shift')[metric_col].nunique().to_dict()
#     elif agg_type == 'count':
#         grouped = df_clean.groupby('shift')[metric_col].count().to_dict()
#     else:
#         grouped = {}

#     # 🔄 CHANGE 2: Divide by `divisor` before rounding, and round to `decimals`
#     #    instead of always forcing int(). For divisor=1, decimals=0 this is
#     #    identical to the old behavior: int(round(float(value)))
#     for shift in ["1st Shift", "2nd Shift", "3rd Shift"]:
#         raw_val = float(grouped.get(shift, 0)) / divisor
#         result[shift] = round(raw_val, decimals) if decimals > 0 else int(round(raw_val))
        
#     result["Total"] = sum(result[s] for s in ["1st Shift", "2nd Shift", "3rd Shift"])
#     if decimals > 0:
#         result["Total"] = round(result["Total"], decimals)
#     return result

# # --- Helper Functions (Remaining) ---
# def combine_metrics(d1: dict, d2: dict) -> dict:
#     return {
#         "1st Shift": d1.get("1st Shift", 0) + d2.get("1st Shift", 0),
#         "2nd Shift": d1.get("2nd Shift", 0) + d2.get("2nd Shift", 0),
#         "3rd Shift": d1.get("3rd Shift", 0) + d2.get("3rd Shift", 0),
#         "Total": d1.get("Total", 0) + d2.get("Total", 0)
#     }

# def combine_three_metrics(d1: dict, d2: dict, d3: dict) -> dict:
#     return {
#         "1st Shift": d1.get("1st Shift", 0) + d2.get("1st Shift", 0) + d3.get("1st Shift", 0),
#         "2nd Shift": d1.get("2nd Shift", 0) + d2.get("2nd Shift", 0) + d3.get("2nd Shift", 0),
#         "3rd Shift": d1.get("3rd Shift", 0) + d2.get("3rd Shift", 0) + d3.get("3rd Shift", 0),
#         "Total": d1.get("Total", 0) + d2.get("Total", 0) + d3.get("Total", 0)
#     }

# def divide_metrics(num_dict: dict, den_dict: dict) -> dict:
#     res = {}
#     for shift in ["1st Shift", "2nd Shift", "3rd Shift", "Total"]:
#         n = num_dict.get(shift, 0)
#         d = den_dict.get(shift, 0)
#         res[shift] = int(round(n / d)) if d > 0 else 0
#     return res

# # --- Main API Endpoint ---
# @router.get("/dashboard/summary")

# async def get_dashboard_summary(
#     target_date: str = Query(..., description="Format: YYYY-MM-DD"), 
#     db: Session = Depends(get_db)
# ):
#     # ✅ Sahi (IST 6 AM = UTC 00:30):
#     start_dt = datetime.strptime(target_date, "%Y-%m-%d") + timedelta(hours=0, minutes=30)
#     end_dt = start_dt + timedelta(days=1)     # n an n+1 date logic....


#     # def fetch_data(query, params):
#     #     with sync_engine.connect() as conn:
#     #         return pd.read_sql(text(query), conn, params=params)

#     async def fetch_data(query: str, params: dict) -> pd.DataFrame:
#         result = await db.execute(text(query), params)
#         return pd.DataFrame(result.mappings().all())

#     sql_params = {"s": start_dt, "e": end_dt}

#     # Fetching Data
#     df_uplift = await fetch_data("SELECT * FROM dr_exp_cargo_uplift_report WHERE uld_release_date_time >= :s AND uld_release_date_time < :e", sql_params)
#     df_car_msg = await fetch_data("SELECT * FROM dr_exp_car_message_report WHERE car_msg_date_time >= :s AND car_msg_date_time < :e", sql_params)
#     df_loaded = await fetch_data("SELECT * FROM dr_exp_export_loaded_inventory WHERE loaded_date_time >= :s AND loaded_date_time < :e", sql_params)
#     df_imp_seg = await fetch_data("SELECT * FROM dr_exp_import_segregation_report WHERE tfd_date_time >= :s AND tfd_date_time < :e", sql_params)
#     df_exp_tp = await fetch_data("SELECT * FROM dr_exp_export_transhipment_report WHERE xray_date_time >= :s AND xray_date_time < :e", sql_params)
#     df_xray = await fetch_data("SELECT * FROM dr_exp_xray_report WHERE xray_date_time >= :s AND xray_date_time < :e", sql_params)
#     df_imp_tp_xray = await fetch_data("SELECT * FROM dr_exp_import_tp_xray_report WHERE xray_date_time >= :s AND xray_date_time < :e", sql_params)
#     df_exp_tp_xray = await fetch_data("SELECT * FROM dr_exp_export_tp_xray_report WHERE xray_date_time >= :s AND xray_date_time < :e", sql_params)
#     df_scanning = await fetch_data(
#     """
#     SELECT ul.loaded_at, COALESCE(awb.gross_wt, 0) as gross_wt, awb.shc 
#     FROM export_item_uld_loading ul
#     JOIN export_car_message_awb_master awb ON ul.awb_master_id = awb.id
#     WHERE ul.loaded_at >= :s AND ul.loaded_at < :e
#     AND awb.shc NOT ILIKE '%PER%' 
#     AND awb.shc NOT ILIKE '%PEM%'
#     """, 
#     sql_params
# )

#     # Metrics Calculation

#     # 🔄 CHANGE 3: TP Tonnage — chg_wgt is a weight field -> divisor=1000, decimals=0
#     tp_tonnage_wgt = combine_metrics(
#     get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0),
#     get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0)
# )

#     imp_awb = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'awb_no', 'nunique')  # count -> unchanged
#     imp_pcs = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'pcs', 'sum')          # count -> unchanged
#     # 🔄 CHANGE 4: imp_wgt, exp_wgt are weight fields -> divisor=1000, decimals=0
#     imp_wgt = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
#     exp_awb = get_shift_metrics(df_exp_tp, 'xray_date_time', 'awb_no', 'nunique')   # count -> unchanged
#     exp_pcs = get_shift_metrics(df_exp_tp, 'xray_date_time', 'rec_pcs', 'sum')      # count -> unchanged
#     exp_wgt = get_shift_metrics(df_exp_tp, 'xray_date_time', 'received_wgt', 'sum', divisor=1000, decimals=0)

#     xr_awb = get_shift_metrics(df_xray, 'xray_date_time', 'awb_no', 'nunique')      # count -> unchanged
#     xr_pcs = get_shift_metrics(df_xray, 'xray_date_time', 'pcs', 'sum')             # count -> unchanged
#     # 🔄 CHANGE 5: xr_wgt is a weight field -> divisor=1000, decimals=0
#     xr_wgt = get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
#     xr_mac = get_shift_metrics(df_xray, 'xray_date_time', 'serial_no', 'nunique')   # count -> unchanged
    
#     total_xray_awb = combine_three_metrics(xr_awb, get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'awb_no', 'nunique'), get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'awb_no', 'nunique'))
#     total_xray_pcs = combine_three_metrics(xr_pcs, get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'pcs', 'sum'), get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'pcs', 'sum'))
#     total_xray_mac = combine_three_metrics(xr_mac, get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'serial_no', 'nunique'), get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'serial_no', 'nunique'))
#     prod_pcs = divide_metrics(total_xray_pcs, total_xray_mac)  # pieces/machine -> not a weight metric, unchanged

#     # 🔄 CHANGE 6: prod_wgt (Machine Productivity in MT) — the total weight fed into
#     #    divide_metrics must already be in MT, so each of the three components below
#     #    now uses divisor=1000, decimals=0. The final divide by machine count then
#     #    naturally yields MT/machine.
#     prod_wgt = divide_metrics(
#         combine_three_metrics(
#             xr_wgt,
#             get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
#             get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
#         ),
#         total_xray_mac
#     )

#     df_up_sub = df_uplift[['uld_release_date_time', 'gross_wgt', 'uld_no', 'pcs', 'awb_no', 'flt_no']].rename(columns={'uld_release_date_time': 'shift_time'}) if not df_uplift.empty else pd.DataFrame()
#     df_load_sub = df_loaded[['loaded_date_time', 'wgt_grs', 'uld_no', 'pcs', 'awb_no', 'flt_num']].rename(columns={'loaded_date_time': 'shift_time', 'wgt_grs': 'gross_wgt', 'flt_num': 'flt_no'}) if not df_loaded.empty else pd.DataFrame()
#     df_buildup = pd.concat([df_up_sub, df_load_sub], ignore_index=True)

#     # 🔄 CHANGE 7: SLA Scanning weight -> divisor=1000, decimals=0
#     sla_scanning = get_shift_metrics(df_scanning, 'loaded_at', 'gross_wt', 'sum', divisor=1000, decimals=0)

#     return {
#         "date": target_date,
#         "sections": {
#             "Export_Tonnage": {
#                 # 🔄 CHANGE 8: Export Tonnage Gross/Chg Wgt -> divisor=1000, decimals=0
#                 "Gross Wgt (MT)": get_shift_metrics(df_uplift, 'uld_release_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
#                 "Chg Wgt (MT)": get_shift_metrics(df_uplift, 'uld_release_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0)
#             },
#             "TP_Tonnage": {"Received Chg Wgt (MT)": tp_tonnage_wgt},
#             "TD Tonnage": {
#                 "Airway Bill Count": get_shift_metrics(df_car_msg, 'car_msg_date_time', 'awb_no', 'nunique'),  # count -> unchanged
#                 "Piece Count": get_shift_metrics(df_car_msg, 'car_msg_date_time', 'pcs', 'sum'),               # count -> unchanged
#                 # 🔄 CHANGE 9: TD Gross Wgt -> divisor=1000, decimals=0
#                 "Gross Wgt (MT)": get_shift_metrics(df_car_msg, 'car_msg_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
#             },
#             "TP": {
#                 "No. of AWB": combine_metrics(imp_awb, exp_awb),
#                 "No. of Pieces": combine_metrics(imp_pcs, exp_pcs),
#                 "Gross Wgt (MT)": combine_metrics(imp_wgt, exp_wgt)
#             },
#             "X_Ray": {
#                 "Airway Bill Count": total_xray_awb,
#                 "Piece Count": total_xray_pcs,
#                 "No of Machine Operated": total_xray_mac,
#                 "Machine Productivity (in Piece)": prod_pcs,
#                 "Machine Productivity (MT)": prod_wgt
#             },
#             "Build_Up": {
#                 # 🔄 CHANGE 10: Build-Up Gross Wgt -> divisor=1000, decimals=0
#                 "Gross Wgt (MT)": get_shift_metrics(df_buildup, 'shift_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
#                 "No. of Uld": get_shift_metrics(df_buildup, 'shift_time', 'uld_no', 'nunique'),   # count -> unchanged
#                 "No. of Pcs": get_shift_metrics(df_buildup, 'shift_time', 'pcs', 'sum'),          # count -> unchanged
#                 "No. of AWB": get_shift_metrics(df_buildup, 'shift_time', 'awb_no', 'nunique'),   # count -> unchanged
#                 "No. of Flight": get_shift_metrics(df_buildup, 'shift_time', 'flt_no', 'nunique') # count -> unchanged
#             },
#             "SLA": {
#                 # 🔄 CHANGE 11: SLA X-Ray weight -> divisor=1000, decimals=0
#                 "X-Ray Gross Wgt (MT)": get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
#                 "Scanning Gross Wgt (MT)": sla_scanning
#             }
#         }
#     }

# # ----------------- Final Export Endpoint (Updated) ------------------
# @router.get("/dashboard/export")
# async def export_dashboard(
#     target_date: str = Query(..., description="Format: YYYY-MM-DD"),
#     export_format: str = Query("excel", regex="^(excel|csv)$"),
#     db: Session = Depends(get_db)
# ):
#     # ✅ Sahi (IST 6 AM = UTC 00:30):
#     start_dt = datetime.strptime(target_date, "%Y-%m-%d") + timedelta(hours=0, minutes=30)
#     end_dt = start_dt + timedelta(days=1)
    
#     # def fetch_data(query, params):
#     #     with sync_engine.connect() as conn:
#     #         return pd.read_sql(text(query), conn, params=params)
#     async def fetch_data(query: str, params: dict) -> pd.DataFrame:
#         result = await db.execute(text(query), params)
#         return pd.DataFrame(result.mappings().all())

#     sql_params = {"s": start_dt, "e": end_dt}

#     # 1. Fetching all data (Scanning data included)
#     df_uplift = await fetch_data("SELECT * FROM dr_exp_cargo_uplift_report WHERE uld_release_date_time >= :s AND uld_release_date_time < :e", sql_params)
#     df_car_msg = await fetch_data("SELECT * FROM dr_exp_car_message_report WHERE car_msg_date_time >= :s AND car_msg_date_time < :e", sql_params)
#     df_loaded = await fetch_data("SELECT * FROM dr_exp_export_loaded_inventory WHERE loaded_date_time >= :s AND loaded_date_time < :e", sql_params)
#     df_imp_seg = await fetch_data("SELECT * FROM dr_exp_import_segregation_report WHERE tfd_date_time >= :s AND tfd_date_time < :e", sql_params)
#     df_exp_tp = await fetch_data("SELECT * FROM dr_exp_export_transhipment_report WHERE xray_date_time >= :s AND xray_date_time < :e", sql_params)
#     df_xray = await fetch_data("SELECT * FROM dr_exp_xray_report WHERE xray_date_time >= :s AND xray_date_time < :e", sql_params)
#     df_imp_tp_xray = await fetch_data("SELECT * FROM dr_exp_import_tp_xray_report WHERE xray_date_time >= :s AND xray_date_time < :e", sql_params)
#     df_exp_tp_xray = await fetch_data("SELECT * FROM dr_exp_export_tp_xray_report WHERE xray_date_time >= :s AND xray_date_time < :e", sql_params)
    
#     # Naya Scanning Data fetch (SLA ke liye)
#     df_scanning = await fetch_data("""
#         SELECT ul.loaded_at, COALESCE(awb.gross_wt, 0) as gross_wt, awb.shc 
#         FROM export_item_uld_loading ul
#         JOIN export_car_message_awb_master awb ON ul.awb_master_id = awb.id
#         WHERE ul.loaded_at >= :s AND ul.loaded_at < :e
#         AND awb.shc NOT ILIKE '%PER%' 
#         AND awb.shc NOT ILIKE '%PEM%'
#     """, sql_params)

#     # 2. Metrics Calculation
#     # 🔄 CHANGE 1: imp_wgt, exp_wgt are weight fields -> divisor=1000, decimals=0
#     #    (imp_awb/imp_pcs/exp_awb/exp_pcs are counts -> left unchanged)
#     imp_awb, imp_pcs, imp_wgt = (
#         get_shift_metrics(df_imp_seg, 'tfd_date_time', 'awb_no', 'nunique'),
#         get_shift_metrics(df_imp_seg, 'tfd_date_time', 'pcs', 'sum'),
#         get_shift_metrics(df_imp_seg, 'tfd_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
#     )
#     exp_awb, exp_pcs, exp_wgt = (
#         get_shift_metrics(df_exp_tp, 'xray_date_time', 'awb_no', 'nunique'),
#         get_shift_metrics(df_exp_tp, 'xray_date_time', 'rec_pcs', 'sum'),
#         get_shift_metrics(df_exp_tp, 'xray_date_time', 'received_wgt', 'sum', divisor=1000, decimals=0)
#     )
    
#     # X-Ray Aggregation
#     # 🔄 CHANGE 2: xr_wgt is a weight field -> divisor=1000, decimals=0
#     #    (xr_awb/xr_pcs/xr_mac are counts -> left unchanged)
#     xr_awb, xr_pcs, xr_wgt, xr_mac = (
#         get_shift_metrics(df_xray, 'xray_date_time', 'awb_no', 'nunique'),
#         get_shift_metrics(df_xray, 'xray_date_time', 'pcs', 'sum'),
#         get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
#         get_shift_metrics(df_xray, 'xray_date_time', 'serial_no', 'nunique')
#     )
#     tot_xr_awb = combine_three_metrics(xr_awb, get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'awb_no', 'nunique'), get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'awb_no', 'nunique'))
#     tot_xr_pcs = combine_three_metrics(xr_pcs, get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'pcs', 'sum'), get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'pcs', 'sum'))
#     tot_xr_mac = combine_three_metrics(xr_mac, get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'serial_no', 'nunique'), get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'serial_no', 'nunique'))
    
#     # Build-up
#     df_up_sub = df_uplift[['uld_release_date_time', 'gross_wgt', 'uld_no', 'pcs', 'awb_no', 'flt_no']].rename(columns={'uld_release_date_time': 'shift_time'}) if not df_uplift.empty else pd.DataFrame()
#     df_load_sub = df_loaded[['loaded_date_time', 'wgt_grs', 'uld_no', 'pcs', 'awb_no', 'flt_num']].rename(columns={'loaded_date_time': 'shift_time', 'wgt_grs': 'gross_wgt', 'flt_num': 'flt_no'}) if not df_loaded.empty else pd.DataFrame()
#     df_buildup = pd.concat([df_up_sub, df_load_sub], ignore_index=True)

#     # 3. Add to Summary
#     summary_data = []
#     def add_row(cat, desc, metrics): summary_data.append({"Category": cat, "Description": desc, **metrics})

#     # 🔄 CHANGE 3: Export Tonnage Gross/Chg Wgt -> divisor=1000, decimals=0
#     #    Also renamed description to "(MT)" so the exported file matches the dashboard labels
#     add_row("Export Tonnage", "Gross Wgt (MT)", get_shift_metrics(df_uplift, 'uld_release_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0))
#     add_row("Export Tonnage", "Chg Wgt (MT)", get_shift_metrics(df_uplift, 'uld_release_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0))

#     # 🔄 CHANGE 4: TP Tonnage Received Chg Wgt -> both source metrics are weight fields
#     #    -> divisor=1000, decimals=0 on each before combining
#     add_row("TP Tonnage", "Received Chg Wgt (MT)", combine_metrics(
#         get_shift_metrics(df_exp_tp, 'xray_date_time', 'received_wgt', 'sum', divisor=1000, decimals=0),
#         get_shift_metrics(df_imp_seg, 'tfd_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0)
#     ))

#     add_row("TD Tonnage", "Airway Bill Count", get_shift_metrics(df_car_msg, 'car_msg_date_time', 'awb_no', 'nunique'))  # count -> unchanged
#     add_row("TD Tonnage", "Piece Count", get_shift_metrics(df_car_msg, 'car_msg_date_time', 'pcs', 'sum'))               # count -> unchanged
#     # 🔄 CHANGE 5: TD Tonnage Gross Wgt -> divisor=1000, decimals=0
#     add_row("TD Tonnage", "Gross Wgt (MT)", get_shift_metrics(df_car_msg, 'car_msg_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0))

#     add_row("TP", "No. of AWB", combine_metrics(imp_awb, exp_awb))
#     add_row("TP", "No. of Pieces", combine_metrics(imp_pcs, exp_pcs))
#     add_row("TP", "Gross Wgt (MT)", combine_metrics(imp_wgt, exp_wgt))  # imp_wgt/exp_wgt already converted above
    
#     # X-Ray details
#     add_row("X_Ray", "Airway Bill Count", tot_xr_awb)
#     add_row("X_Ray", "Piece Count", tot_xr_pcs)
#     add_row("X_Ray", "No of Machine Operated", tot_xr_mac)
#     add_row("X_Ray", "Machine Productivity (in Piece)", divide_metrics(tot_xr_pcs, tot_xr_mac))  # not a weight metric -> unchanged
#     # 🔄 CHANGE 6: Machine Productivity (in MT) -> the two extra weight components
#     #    (df_imp_tp_xray / df_exp_tp_xray gross_wgt) now use divisor=1000, decimals=0
#     #    so the numerator fed into divide_metrics is already in MT (xr_wgt was
#     #    converted in CHANGE 2). Result is MT-per-machine, not kg-per-machine.
#     add_row("X_Ray", "Machine Productivity (in MT)", divide_metrics(
#         combine_three_metrics(
#             xr_wgt,
#             get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
#             get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
#         ),
#         tot_xr_mac
#     ))
    
#     # Build-up details
#     # 🔄 CHANGE 7: Build-Up Gross Wgt -> divisor=1000, decimals=0
#     add_row("Build_Up", "Gross Wgt (MT)", get_shift_metrics(df_buildup, 'shift_time', 'gross_wgt', 'sum', divisor=1000, decimals=0))
#     add_row("Build_Up", "No. of Uld", get_shift_metrics(df_buildup, 'shift_time', 'uld_no', 'nunique'))   # count -> unchanged
#     add_row("Build_Up", "No. of Pcs", get_shift_metrics(df_buildup, 'shift_time', 'pcs', 'sum'))          # count -> unchanged
#     add_row("Build_Up", "No. of AWB", get_shift_metrics(df_buildup, 'shift_time', 'awb_no', 'nunique'))   # count -> unchanged
#     add_row("Build_Up", "No. of Flight", get_shift_metrics(df_buildup, 'shift_time', 'flt_no', 'nunique')) # count -> unchanged
    
#     # SLA details (Updated)
#     # 🔄 CHANGE 8: SLA X-Ray & Scanning weight -> divisor=1000, decimals=0
#     add_row("SLA", "X-Ray (MT)", get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0))
#     add_row("SLA", "Scanning (MT)", get_shift_metrics(df_scanning, 'loaded_at', 'gross_wt', 'sum', divisor=1000, decimals=0))

#     # 4. Final Response... (streaming code)
#     df_final = pd.DataFrame(summary_data)
#     output = io.BytesIO()
#     if export_format == "csv":
#         df_final.to_csv(output, index=False, encoding='utf-8')
#         media_type, filename = "text/csv", f"Dashboard_{target_date}.csv"
#     else:
#         with pd.ExcelWriter(output, engine='xlsxwriter') as writer: df_final.to_excel(writer, sheet_name='Summary', index=False)
#         media_type, filename = "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet", f"Dashboard_{target_date}.xlsx"
#     output.seek(0)
#     return StreamingResponse(output, media_type=media_type, headers={"Content-Disposition": f"attachment; filename={filename}"})






# ================================================= NEW WITH SQLALCHAMY  ===========================

from fastapi import APIRouter, Depends, Query
from sqlalchemy import select, and_, func
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import datetime, timedelta
import pandas as pd
from app.db.session import get_db
from fastapi.responses import StreamingResponse
import io

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


def scanning_stmt(start_dt, end_dt):
    """
    ORM equivalent of the SLA scanning join:
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
            ExportItemUldLoading.loaded_at < end_dt,
            ~ExportCarMessageAwbMaster.shc.ilike("%PER%"),
            ~ExportCarMessageAwbMaster.shc.ilike("%PEM%"),
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
        "scanning":    await fetch_df(db, scanning_stmt(start_dt, end_dt)),
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


def build_buildup_df(df_uplift: pd.DataFrame, df_loaded: pd.DataFrame) -> pd.DataFrame:
    df_up_sub = (
        df_uplift[['uld_release_date_time', 'gross_wgt', 'uld_no', 'pcs', 'awb_no', 'flt_no']]
        .rename(columns={'uld_release_date_time': 'shift_time'})
        if not df_uplift.empty else pd.DataFrame()
    )
    df_load_sub = (
        df_loaded[['loaded_date_time', 'wgt_grs', 'uld_no', 'pcs', 'awb_no', 'flt_num']]
        .rename(columns={'loaded_date_time': 'shift_time', 'wgt_grs': 'gross_wgt', 'flt_num': 'flt_no'})
        if not df_loaded.empty else pd.DataFrame()
    )
    return pd.concat([df_up_sub, df_load_sub], ignore_index=True)


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
    df_scanning    = data["scanning"]

    # --- TP Tonnage (weight -> MT) ---
    tp_tonnage_wgt = combine_metrics(
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0)
    )

    imp_awb = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'awb_no', 'nunique')
    imp_pcs = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'pcs', 'sum')
    imp_wgt = get_shift_metrics(df_imp_seg, 'tfd_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)

    exp_awb = get_shift_metrics(df_exp_tp, 'xray_date_time', 'awb_no', 'nunique')
    exp_pcs = get_shift_metrics(df_exp_tp, 'xray_date_time', 'rec_pcs', 'sum')
    exp_wgt = get_shift_metrics(df_exp_tp, 'xray_date_time', 'received_wgt', 'sum', divisor=1000, decimals=0)

    xr_awb = get_shift_metrics(df_xray, 'xray_date_time', 'awb_no', 'nunique')
    xr_pcs = get_shift_metrics(df_xray, 'xray_date_time', 'pcs', 'sum')
    xr_wgt = get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
    xr_mac = get_shift_metrics(df_xray, 'xray_date_time', 'serial_no', 'nunique')

    total_xray_awb = combine_three_metrics(
        xr_awb,
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'awb_no', 'nunique'),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'awb_no', 'nunique')
    )
    total_xray_pcs = combine_three_metrics(
        xr_pcs,
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'pcs', 'sum'),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'pcs', 'sum')
    )
    total_xray_mac = combine_three_metrics(
        xr_mac,
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'serial_no', 'nunique'),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'serial_no', 'nunique')
    )

    prod_pcs = divide_metrics(total_xray_pcs, total_xray_mac)

    # Numerator already in MT -> result is MT/machine
    prod_wgt = divide_metrics(
        combine_three_metrics(
            xr_wgt,
            get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
            get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
        ),
        total_xray_mac
    )

    df_buildup = build_buildup_df(df_uplift, df_loaded)
    sla_scanning = get_shift_metrics(df_scanning, 'loaded_at', 'gross_wt', 'sum', divisor=1000, decimals=0)

    return {
        "date": target_date,
        "sections": {
            "Export_Tonnage": {
                "Gross Wgt (MT)": get_shift_metrics(df_uplift, 'uld_release_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                "Chg Wgt (MT)": get_shift_metrics(df_uplift, 'uld_release_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0)
            },
            "TP_Tonnage": {"Received Chg Wgt (MT)": tp_tonnage_wgt},
            "TD Tonnage": {
                "Airway Bill Count": get_shift_metrics(df_car_msg, 'car_msg_date_time', 'awb_no', 'nunique'),
                "Piece Count": get_shift_metrics(df_car_msg, 'car_msg_date_time', 'pcs', 'sum'),
                "Gross Wgt (MT)": get_shift_metrics(df_car_msg, 'car_msg_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
            },
            "TP": {
                "No. of AWB": combine_metrics(imp_awb, exp_awb),
                "No. of Pieces": combine_metrics(imp_pcs, exp_pcs),
                "Gross Wgt (MT)": combine_metrics(imp_wgt, exp_wgt)
            },
            "X_Ray": {
                "Airway Bill Count": total_xray_awb,
                "Piece Count": total_xray_pcs,
                "No of Machine Operated": total_xray_mac,
                "Machine Productivity (in Piece)": prod_pcs,
                "Machine Productivity (MT)": prod_wgt
            },
            "Build_Up": {
                "Gross Wgt (MT)": get_shift_metrics(df_buildup, 'shift_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                "No. of Uld": get_shift_metrics(df_buildup, 'shift_time', 'uld_no', 'nunique'),
                "No. of Pcs": get_shift_metrics(df_buildup, 'shift_time', 'pcs', 'sum'),
                "No. of AWB": get_shift_metrics(df_buildup, 'shift_time', 'awb_no', 'nunique'),
                "No. of Flight": get_shift_metrics(df_buildup, 'shift_time', 'flt_no', 'nunique')
            },
            "SLA": {
                "X-Ray Gross Wgt (MT)": get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
                "Scanning Gross Wgt (MT)": sla_scanning
            }
        }
    }


# ============================================================
#  EXPORT ENDPOINT
# ============================================================
@router.get("/dashboard/export")
async def export_dashboard(
    target_date: str = Query(..., description="Format: YYYY-MM-DD"),
    export_format: str = Query("excel", regex="^(excel|csv)$"),
    db: AsyncSession = Depends(get_db)
):
    start_dt = datetime.strptime(target_date, "%Y-%m-%d") + timedelta(hours=0, minutes=30)
    end_dt = start_dt + timedelta(days=1)

    data = await fetch_all_dashboard_data(db, start_dt, end_dt)
    df_uplift      = data["uplift"]
    df_car_msg     = data["car_msg"]
    df_loaded      = data["loaded"]
    df_imp_seg     = data["imp_seg"]
    df_exp_tp      = data["exp_tp"]
    df_xray        = data["xray"]
    df_imp_tp_xray = data["imp_tp_xray"]
    df_exp_tp_xray = data["exp_tp_xray"]
    df_scanning    = data["scanning"]

    imp_awb, imp_pcs, imp_wgt = (
        get_shift_metrics(df_imp_seg, 'tfd_date_time', 'awb_no', 'nunique'),
        get_shift_metrics(df_imp_seg, 'tfd_date_time', 'pcs', 'sum'),
        get_shift_metrics(df_imp_seg, 'tfd_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
    )
    exp_awb, exp_pcs, exp_wgt = (
        get_shift_metrics(df_exp_tp, 'xray_date_time', 'awb_no', 'nunique'),
        get_shift_metrics(df_exp_tp, 'xray_date_time', 'rec_pcs', 'sum'),
        get_shift_metrics(df_exp_tp, 'xray_date_time', 'received_wgt', 'sum', divisor=1000, decimals=0)
    )
    xr_awb, xr_pcs, xr_wgt, xr_mac = (
        get_shift_metrics(df_xray, 'xray_date_time', 'awb_no', 'nunique'),
        get_shift_metrics(df_xray, 'xray_date_time', 'pcs', 'sum'),
        get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
        get_shift_metrics(df_xray, 'xray_date_time', 'serial_no', 'nunique')
    )

    tot_xr_awb = combine_three_metrics(
        xr_awb,
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'awb_no', 'nunique'),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'awb_no', 'nunique')
    )
    tot_xr_pcs = combine_three_metrics(
        xr_pcs,
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'pcs', 'sum'),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'pcs', 'sum')
    )
    tot_xr_mac = combine_three_metrics(
        xr_mac,
        get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'serial_no', 'nunique'),
        get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'serial_no', 'nunique')
    )

    df_buildup = build_buildup_df(df_uplift, df_loaded)

    summary_data = []

    def add_row(cat, desc, metrics):
        summary_data.append({"Category": cat, "Description": desc, **metrics})

    add_row("Export Tonnage", "Gross Wgt (MT)", get_shift_metrics(df_uplift, 'uld_release_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0))
    add_row("Export Tonnage", "Chg Wgt (MT)", get_shift_metrics(df_uplift, 'uld_release_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0))

    add_row("TP Tonnage", "Received Chg Wgt (MT)", combine_metrics(
        get_shift_metrics(df_exp_tp, 'xray_date_time', 'received_wgt', 'sum', divisor=1000, decimals=0),
        get_shift_metrics(df_imp_seg, 'tfd_date_time', 'chg_wgt', 'sum', divisor=1000, decimals=0)
    ))

    add_row("TD Tonnage", "Airway Bill Count", get_shift_metrics(df_car_msg, 'car_msg_date_time', 'awb_no', 'nunique'))
    add_row("TD Tonnage", "Piece Count", get_shift_metrics(df_car_msg, 'car_msg_date_time', 'pcs', 'sum'))
    add_row("TD Tonnage", "Gross Wgt (MT)", get_shift_metrics(df_car_msg, 'car_msg_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0))

    add_row("TP", "No. of AWB", combine_metrics(imp_awb, exp_awb))
    add_row("TP", "No. of Pieces", combine_metrics(imp_pcs, exp_pcs))
    add_row("TP", "Gross Wgt (MT)", combine_metrics(imp_wgt, exp_wgt))

    add_row("X_Ray", "Airway Bill Count", tot_xr_awb)
    add_row("X_Ray", "Piece Count", tot_xr_pcs)
    add_row("X_Ray", "No of Machine Operated", tot_xr_mac)
    add_row("X_Ray", "Machine Productivity (in Piece)", divide_metrics(tot_xr_pcs, tot_xr_mac))
    add_row("X_Ray", "Machine Productivity (in MT)", divide_metrics(
        combine_three_metrics(
            xr_wgt,
            get_shift_metrics(df_imp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0),
            get_shift_metrics(df_exp_tp_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0)
        ),
        tot_xr_mac
    ))

    add_row("Build_Up", "Gross Wgt (MT)", get_shift_metrics(df_buildup, 'shift_time', 'gross_wgt', 'sum', divisor=1000, decimals=0))
    add_row("Build_Up", "No. of Uld", get_shift_metrics(df_buildup, 'shift_time', 'uld_no', 'nunique'))
    add_row("Build_Up", "No. of Pcs", get_shift_metrics(df_buildup, 'shift_time', 'pcs', 'sum'))
    add_row("Build_Up", "No. of AWB", get_shift_metrics(df_buildup, 'shift_time', 'awb_no', 'nunique'))
    add_row("Build_Up", "No. of Flight", get_shift_metrics(df_buildup, 'shift_time', 'flt_no', 'nunique'))

    add_row("SLA", "X-Ray (MT)", get_shift_metrics(df_xray, 'xray_date_time', 'gross_wgt', 'sum', divisor=1000, decimals=0))
    add_row("SLA", "Scanning (MT)", get_shift_metrics(df_scanning, 'loaded_at', 'gross_wt', 'sum', divisor=1000, decimals=0))

    df_final = pd.DataFrame(summary_data)
    output = io.BytesIO()
    if export_format == "csv":
        df_final.to_csv(output, index=False, encoding='utf-8')
        media_type, filename = "text/csv", f"Dashboard_{target_date}.csv"
    else:
        with pd.ExcelWriter(output, engine='xlsxwriter') as writer:
            df_final.to_excel(writer, sheet_name='Summary', index=False)
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
        # ✅ STRICT VALIDATION ERROR CATCHER
        raise HTTPException(status_code=400, detail=str(ve))
        
    except Exception as e:
        await db.rollback()
        raise HTTPException(status_code=500, detail=str(e))
