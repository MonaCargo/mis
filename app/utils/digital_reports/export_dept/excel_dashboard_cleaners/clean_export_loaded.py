

import pandas as pd
import re
from io import BytesIO
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.base_utils import _extract_file_date_display, standardize_columns  # smart_filter_operational_date removed (Check 2 disabled)

def process_export_loaded_inventory(file_content: bytes, filename: str, selected_date: str):
    file_io = BytesIO(file_content)

    # ==========================================
    # STEP 1: ROBUST HEADER VALIDATION (No CSV Parser)
    # ==========================================
    file_io.seek(0)
    target_dt = pd.to_datetime(selected_date)
    target_str_long = target_dt.strftime('%d%b%Y').upper()
    target_str_short = target_dt.strftime('%d%b%y').upper()

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
        # raise ValueError(f"Blocker: File date mismatch. Expected {selected_date}.")
        file_date_display = _extract_file_date_display(clean_header_text)
        expected_date_display = target_dt.strftime('%d-%B-%Y')  # e.g. 14-July-2026

        raise ValueError(
            f"Blocker: File date mismatch. File shows {file_date_display}, "
            f"but you selected {expected_date_display}."
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

    # CLEANING
    df.columns = df.columns.astype(str).str.strip()
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)
    df = standardize_columns(df)
    df.columns = df.columns.astype(str).str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()

    # Mapping
    column_mapping = {
        'CARRIER': 'carrier', 'AWB': 'awb_no', 'ULD NO.': 'uld_no', 'ULD NO': 'uld_no',
        'STATUS': 'status', 'LOADED DATE & TIME': 'loaded_date_time',
        'DESTINATION': 'destination', 'AGENT': 'agent', 'PCS': 'pcs',
        'WGT CHG': 'wgt_chg', 'WGT_CHG': 'wgt_chg', 'WGT GRS': 'wgt_grs',
        'WGT_GRS': 'wgt_grs', 'VOL(MC)': 'volume', 'SHC CODE': 'shc_code',
        'SHC_CODE': 'shc_code', 'FLT_NUM': 'flt_num', 'FLT NUM': 'flt_num',
        'ULD WGT': 'uld_wgt', 'ULD_WGT': 'uld_wgt'
    }

    df_db = df.rename(columns=column_mapping)
    df_db = df_db[[c for c in dict.fromkeys(column_mapping.values()) if c in df_db.columns]]

    # STRING & NUMERIC
    string_cols = ['carrier', 'awb_no', 'uld_no', 'status', 'destination', 'agent', 'shc_code', 'flt_num']
    for col in string_cols:
        if col in df_db.columns:
            df_db[col] = df_db[col].astype(str).replace(r'^\s*$', pd.NA, regex=True).replace(['nan', 'None', 'NAN', 'NaN', 'null'], pd.NA)

    numeric_cols = ['pcs', 'wgt_chg', 'wgt_grs', 'volume', 'uld_wgt']
    for col in numeric_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_numeric(df_db[col], errors='coerce')

    # DATE CONVERSION (UTC)
    if 'loaded_date_time' in df_db.columns:
        df_db['loaded_date_time'] = pd.to_datetime(df_db['loaded_date_time'], dayfirst=True, errors='coerce')
        df_db['loaded_date_time'] = (
            df_db['loaded_date_time']
            .dt.tz_localize('Asia/Kolkata', ambiguous='infer')
            .dt.tz_convert('UTC')
            .dt.tz_localize(None)
        )

    # AGGREGATION
    if not df_db.empty and 'awb_no' in df_db.columns and 'uld_no' in df_db.columns:
        group_cols = ['awb_no', 'uld_no']
        agg_funcs = {col: 'first' for col in df_db.columns if col not in group_cols}
        for col in numeric_cols:
            if col in df_db.columns:
                agg_funcs[col] = 'sum'
        df_db = df_db.groupby(group_cols, dropna=False, as_index=False).agg(agg_funcs)

    df_db = df_db.replace({pd.NA: None, float('nan'): None, pd.NaT: None})

    # ✅ CHECK 2 REMOVED (per business decision): saara data allow hota hai
    # ab — chahe loaded_date_time same ho, alag ho, ya NULL hi ho.
    dropped_count = 0

    if df_db.empty:
        raise ValueError(f"No data found in the uploaded file for {selected_date}.")

    df_db['report_date'] = pd.to_datetime(selected_date).date()

    # Returning Tuple as expected by the API controller
    return df_db, dropped_count