

import pandas as pd
import numpy as np
import re
from io import BytesIO
from typing import Tuple # Added for correct type hinting
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.base_utils import _extract_file_date_display, standardize_columns, combine_date_time  # smart_filter_operational_date removed (Check 2 disabled)

# FIXED: Updated return type hint
def process_cargo_uplift(file_content: bytes, filename: str, selected_date: str) -> Tuple[pd.DataFrame, int]:
    file_io = BytesIO(file_content)

    # ==========================================
    # STEP 1: ROBUST HEADER VALIDATION (No CSV Parser)
    # ==========================================
    file_io.seek(0)
    target_dt = pd.to_datetime(selected_date)
    target_str_long = target_dt.strftime('%d%b%Y').upper() # 24JUN2026
    target_str_short = target_dt.strftime('%d%b%y').upper() # 24JUN26

    if filename.lower().endswith('.csv'):
        raw_bytes = file_io.read()
        decoded_text = raw_bytes.decode('utf-8', errors='ignore')
        header_lines = decoded_text.splitlines()[:7]
        raw_header_text = "".join(header_lines).upper()
    else:
        header_df = pd.read_excel(file_io, header=None, nrows=7)
        raw_header_text = "".join(header_df.fillna('').values.flatten().astype(str)).upper()

    clean_header_text = re.sub(r'[\s\-/,]', '', raw_header_text)

    if target_str_long not in clean_header_text and target_str_short not in clean_header_text:
        # raise ValueError(f"Blocker: File date mismatch. Expected {selected_date} (Checked for {target_str_long} & {target_str_short}).")
        file_date_display = _extract_file_date_display(clean_header_text)
        expected_date_display = target_dt.strftime('%d-%B-%Y')  # e.g. 14-July-2026

        raise ValueError(
            f"Blocker: File date mismatch. File date is {file_date_display}, "
            f"but your selected date is {expected_date_display}."
        )

    # ==========================================
    # STEP 2: ROBUST DATA LOADING
    # ==========================================
    file_io.seek(0)
    try:
        if filename.lower().endswith('.csv'):
            df = pd.read_csv(file_io, skiprows=7, engine='python', on_bad_lines='skip')
        else:
            df = pd.read_excel(file_io, skiprows=7)
    except Exception as e:
        raise ValueError(f"File reading error: {str(e)}")

    # ==========================================
    # CLEANING (BUG FIXED HERE)
    # ==========================================
    df.columns = df.columns.astype(str).str.strip()

    # Safely strip only elements that are actually strings
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)

    df = standardize_columns(df)

    # Combine Dates and Times
    df = combine_date_time(df, 'CAR DATE', 'CAR TIME', 'car_date_time')
    df = combine_date_time(df, 'DOC DATE', 'DOC TIME', 'doc_date_time')
    df = combine_date_time(df, 'XRAY DATE', 'XRAY TIME', 'xray_date_time')
    df = combine_date_time(df, 'RCS/RCF/RCT DATE', 'RCS/RCF/RCT TIME', 'rcs_rcf_rct_date_time')
    df = combine_date_time(df, 'Flight ETD DAT', 'Flight ETD TIM', 'flight_etd_date_time')
    df = combine_date_time(df, 'Flight Departure DATE', 'Flight Departure TIME', 'flight_dep_date_time')
    df = combine_date_time(df, 'ULD RELEASE DATE', 'ULD RELEASE TIME', 'uld_release_date_time')

    # MAPPING
    column_mapping = {
        'SL.No.': 'sl_no', 'FLT NO.': 'flt_no', 'FLT DATE': 'flt_date',
        'AWB No': 'awb_no', 'AWB Sfx': 'awb_sfx', 'ORIGIN': 'origin', 'DEST': 'dest',
        'PCS': 'pcs', 'GRS Wg': 'gross_wgt', 'CHG WGT': 'chg_wgt', 'Volumn(MC)': 'volume',
        'ULD No.': 'uld_no', 'NOG': 'nog', 'SHC': 'shc', 'CHG SHC': 'chg_shc',
        'Billing SHC': 'billing_shc', 'AGENT': 'agent', 'SHIPPER NAME': 'shipper_name',
        'TRM NUMBER': 'trm_number', 'TRM DATE': 'trm_date', 'PASSENGER/FREIGHTER': 'passenger_freighter'
    }

    df_db = df.rename(columns=column_mapping)

    # GARBAGE ROW FIX
    if 'flt_date' in df_db.columns:
        df_db = df_db[~df_db['flt_date'].astype(str).str.contains('AWB COUNT|TOTAL', case=False, na=False)]
    
    # --- DATE CONVERSION FOR FLT_DATE & TRM_DATE (Crucial for DB DATE fields) ---
    for col in ['flt_date', 'trm_date']:
        if col in df_db.columns:
            # Errors='coerce' bad data ko NaT (Not a Time) bana dega
            df_db[col] = pd.to_datetime(df_db[col], errors='coerce')
            
            # Agar date valid hai toh .date() nikalein, warna None
            df_db[col] = df_db[col].apply(lambda x: x.date() if pd.notnull(x) else None)

    # AWB No validation
    if 'awb_no' in df_db.columns:
        df_db['awb_no'] = df_db['awb_no'].astype(str).str.strip()
        df_db = df_db[~df_db['awb_no'].isin(['', 'nan', 'None', 'NaN'])]
        df_db = df_db[df_db['awb_no'].notna()]

    # DATE CONVERSION (WITH UTC)
    date_cols_keep = ['car_date_time', 'doc_date_time', 'xray_date_time', 'rcs_rcf_rct_date_time',
                      'flight_etd_date_time', 'flight_dep_date_time', 'uld_release_date_time']

    for col in date_cols_keep:
        if col in df_db.columns:
            df_db[col] = pd.to_datetime(df_db[col], dayfirst=True, errors='coerce')
            df_db[col] = df_db[col].dt.tz_localize('Asia/Kolkata', ambiguous='infer').dt.tz_convert('UTC').dt.tz_localize(None)

    # STRING & NUMERIC
    string_cols = ['flt_no', 'awb_no', 'awb_sfx', 'origin', 'dest', 'uld_no', 'nog', 'shc', 'chg_shc', 'billing_shc', 'agent', 'shipper_name', 'trm_number', 'passenger_freighter']
    for col in string_cols:
        if col in df_db.columns:
             df_db[col] = df_db[col].astype(str).str.replace(r'\.0$', '', regex=True).replace({'nan': None, 'None': None, 'NaT': None})

    numeric_cols = ['sl_no', 'pcs', 'gross_wgt', 'chg_wgt', 'volume']
    for col in numeric_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_numeric(df_db[col], errors='coerce')

    # Final NaN replacement
    df_db = df_db.replace({pd.NA: None, float('nan'): None, pd.NaT: None})

    # AGGREGATION
    if not df_db.empty and 'awb_no' in df_db.columns and 'uld_no' in df_db.columns:
        group_cols = ['awb_no', 'uld_no']
        agg_funcs = {col: 'first' for col in df_db.columns if col not in group_cols}
        metrics_to_sum = ['pcs', 'gross_wgt', 'chg_wgt']
        for col in metrics_to_sum:
            if col in df_db.columns:
                agg_funcs[col] = 'sum'
        df_db = df_db.groupby(group_cols, dropna=False, as_index=False).agg(agg_funcs)

    # ==========================================
    # ✅ CHECK 2 REMOVED (per business decision): saara data allow hota hai
    # ab — chahe uld_release_date_time same ho, alag ho, ya NULL hi ho.
    # ==========================================


# --- YAHAN ADD KAREIN ---
  
    df_db = df_db.where(pd.notnull(df_db), None)
    df_db = df_db.replace([float('nan'), np.nan, pd.NA, pd.NaT, 'nan', 'NaN', 'None'], None)
    # ------------------------


    dropped_count = 0

    if df_db.empty:
        raise ValueError(f"No data found in the uploaded file for {selected_date}.")

    df_db['report_date'] = pd.to_datetime(selected_date).date()
    return df_db, dropped_count