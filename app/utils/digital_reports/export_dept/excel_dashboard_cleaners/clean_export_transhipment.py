

import pandas as pd
import re
from io import BytesIO
from typing import Tuple
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.base_utils  import _extract_file_date_display, standardize_columns, combine_date_time  # smart_filter_operational_date removed (Check 2 disabled)

def process_export_transhipment(file_content: bytes, filename: str, selected_date: str) -> Tuple[pd.DataFrame, int]:
    file_io = BytesIO(file_content)

    # ==========================================
    # STEP 1: ROBUST HEADER VALIDATION (No CSV Parser)
    # ==========================================
    file_io.seek(0)
    target_dt = pd.to_datetime(selected_date)

    target_str_long = target_dt.strftime('%d%b%Y').upper()   # 24JUN2026
    target_str_short = target_dt.strftime('%d%b%y').upper()  # 24JUN26
    target_str_numeric = target_dt.strftime('%d%m%Y')        # 24062026
    target_str_iso = target_dt.strftime('%Y%m%d')            # 20260624

    if filename.lower().endswith('.csv'):
        raw_bytes = file_io.read()
        decoded_text = raw_bytes.decode('utf-8', errors='ignore')
        header_lines = decoded_text.splitlines()[:10]
        raw_header_text = "".join(header_lines).upper()
    else:
        header_df = pd.read_excel(file_io, header=None, nrows=10)
        raw_header_text = "".join(header_df.fillna('').values.flatten().astype(str)).upper()

    clean_header_text = re.sub(r'[\s\-/,]', '', raw_header_text)

    valid_formats = [target_str_long, target_str_short, target_str_numeric, target_str_iso]

    if not any(fmt in clean_header_text for fmt in valid_formats):
        # raise ValueError(f"Blocker: File date mismatch. Expected {selected_date} (Checked for {target_str_long}, {target_str_short}, and {target_str_numeric}).")

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
            df = pd.read_csv(file_io, skiprows=10, engine='python', on_bad_lines='skip')
        else:
            df = pd.read_excel(file_io, skiprows=10)
    except Exception as e:
        raise ValueError(f"File reading error: {str(e)}")

    # ==========================================
    # CLEANING
    # ==========================================
    df.columns = df.columns.astype(str).str.strip()

    # 🚨 ANTI-CRASH FIX 1: Drop duplicate columns from Excel
    df = df.loc[:, ~df.columns.duplicated()]

    # Safely strip only elements that are actually strings
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)

    df = standardize_columns(df)

    # Combine Date & Time
    df = combine_date_time(df, 'X-Ray DATE', 'X-Ray TIME', 'xray_date_time')
    df.columns = df.columns.astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()

    # 🚨 ANTI-CRASH FIX 2: Drop duplicates again just in case spacing removal created them
    df = df.loc[:, ~df.columns.duplicated()]

    # AWB No validation
    awb_col = None
    for candidate in ['AWB No.', 'AWB No', 'AWB NO']:
        if candidate in df.columns:
            awb_col = candidate
            break

    if awb_col:
        df[awb_col] = df[awb_col].astype(str).str.strip()
        df = df[~df[awb_col].isin(['', 'nan', 'None', 'NAN', 'NaN'])]
        df = df[df[awb_col].notna()]

    # MAPPING
    column_mapping = {
        'SL No': 'sl_no', 'AWB No.': 'awb_no', 'AWB No': 'awb_no', 'PCS': 'pcs',
        'Gross wgt': 'gross_wgt', 'Rec_PCS': 'rec_pcs', 'Received wgt': 'received_wgt',
        'Received_Chg_Wgt': 'received_chg_wgt', 'SHC': 'shc', 'Billing SHC': 'billing_shc',
        'Commodity': 'commodity', 'ORG': 'org', 'DES': 'des', 'DOC DATE & TIME.': 'doc_date_time',
        'DOC DATE & TIME': 'doc_date_time', 'EXP TP SEG FLIGHT No.': 'exp_tp_seg_flight_no',
        'EXP TP SEG FLIGHT No': 'exp_tp_seg_flight_no', 'EXP TP FLIGHT DATE': 'exp_tp_flight_date',
        'EXP TP SEG No DATE AND TIME': 'exp_tp_seg_no_date_time', 'TRM NO': 'trm_no',
        'TRM DATE': 'trm_date', 'X-Ray DATE': 'xray_date', 'X-Ray TIME': 'xray_time',
        'xray_date_time': 'xray_date_time', 'RAMP TRANSFER DATE/TIME': 'ramp_transfer_date_time',
        'RAMP TRANSFER REMARK': 'ramp_transfer_remark', 'RAMP TRANSFER USER': 'ramp_transfer_user',
        'AIRLINE CD': 'airline_cd', 'FLIGHT NO': 'flight_no', 'FLIGHT DATE': 'flight_date',
        'ULD LOAD': 'uld_load', 'DEPARTURE DATE & TIME': 'departure_date_time'
    }

    df_db = df.rename(columns=column_mapping)

    # 🚨 ANTI-CRASH FIX 3: Ensure mapping didn't map two different columns to the exact same name
    df_db = df_db.loc[:, ~df_db.columns.duplicated()]

    # 🚨 ROOT-CAUSE FIX (yehi asli bug tha): column_mapping.values() me
    # DUPLICATE values hain — jaise 'AWB No.' aur 'AWB No' dono 'awb_no' pe,
    # 'DOC DATE & TIME.' aur 'DOC DATE & TIME' dono 'doc_date_time' pe,
    # 'EXP TP SEG FLIGHT No.' aur 'EXP TP SEG FLIGHT No' dono
    # 'exp_tp_seg_flight_no' pe map ho rahe the.
    # Bina dedup ke, neeche wali selection list me 'awb_no' 2 baar chala
    # jaata tha. df_db[[col_list]] jab ek naam list me 2 baar diya jata hai,
    # toh pandas result me wahi column bhi 2 baar duplicate kar deta hai —
    # bhale hi df_db khud duplicate-free ho (upar wala dedup isliye kaam
    # nahi kar raha tha, kyunki duplicate SELECTION LIST se create ho raha
    # tha, source dataframe se nahi).
    # Result: df_db['awb_no'] Series nahi, balki 2-column DataFrame ban
    # jaata. Aage jab '.str.replace()' call hota (jo sirf Series pe hota
    # hai, DataFrame pe nahi), toh crash: "'DataFrame' object has no
    # attribute 'str'". Fix: dict.fromkeys() se values dedupe karo pehle.
    select_cols = list(dict.fromkeys(column_mapping.values()))
    df_db = df_db[[col for col in select_cols if col in df_db.columns]]

    # STRING CONVERSION
    string_cols = ['awb_no', 'shc', 'billing_shc', 'commodity', 'org', 'des', 'exp_tp_seg_flight_no', 'xray_time', 'ramp_transfer_remark', 'ramp_transfer_user', 'airline_cd', 'flight_no', 'uld_load']
    for col in string_cols:
        if col in df_db.columns:
            df_db[col] = df_db[col].astype(str).str.replace(r'\.0$', '', regex=True).replace({'nan': None, 'None': None, 'NaT': None, 'NAN': None})

    # DATE CONVERSION
    date_only_cols = ['exp_tp_flight_date', 'trm_date', 'xray_date', 'flight_date']
    for col in date_only_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_datetime(df_db[col], dayfirst=True, errors='coerce').dt.date

    date_time_cols = ['doc_date_time', 'exp_tp_seg_no_date_time', 'ramp_transfer_date_time', 'departure_date_time', 'xray_date_time']
    for col in date_time_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_datetime(df_db[col], dayfirst=True, errors='coerce')
            df_db[col] = df_db[col].dt.tz_localize('Asia/Kolkata', ambiguous='infer').dt.tz_convert('UTC').dt.tz_localize(None)

    # NUMERIC CONVERSION
    numeric_cols = ['sl_no', 'pcs', 'gross_wgt', 'rec_pcs', 'received_wgt', 'received_chg_wgt', 'trm_no']
    for col in numeric_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_numeric(df_db[col], errors='coerce')

    # AGGREGATION
    if not df_db.empty and 'awb_no' in df_db.columns:
        agg_funcs = {col: 'first' for col in df_db.columns if col != 'awb_no'}
        metrics_to_sum = ['pcs', 'gross_wgt', 'rec_pcs', 'received_wgt', 'received_chg_wgt']
        for col in metrics_to_sum:
            if col in df_db.columns:
                agg_funcs[col] = 'sum'
        df_db = df_db.groupby('awb_no', as_index=False).agg(agg_funcs)

    df_db = df_db.replace({pd.NA: None, float('nan'): None, pd.NaT: None})

    # ==========================================
    # ✅ CHECK 2 REMOVED (per business decision): saara data allow hota hai
    # ab — chahe xray_date_time same ho, alag ho, ya NULL hi ho. Sirf Check
    # 1 (header/metadata date validation, upar STEP 1 me) active hai.
    # ==========================================
    dropped_count = 0

    if df_db.empty:
        raise ValueError(f"No data found in the uploaded file for {selected_date}.")

    df_db['report_date'] = pd.to_datetime(selected_date).date()

    return df_db, dropped_count