

import pandas as pd
import re
from io import BytesIO
from typing import Tuple
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.base_utils  import _extract_file_date_display, standardize_columns  # smart_filter_operational_date removed (Check 2 disabled)

def process_import_segregation(file_content: bytes, filename: str, selected_date: str) -> Tuple[pd.DataFrame, int]:
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
            # Added engine='python' and on_bad_lines='skip' for stability
            df = pd.read_csv(file_io, skiprows=7, engine='python', on_bad_lines='skip')
        else:
            df = pd.read_excel(file_io, skiprows=7)
    except Exception as e:
        raise ValueError(f"File reading error: {str(e)}")

    # 2. CLEANING: Remove Extra Spaces from Headers and Cells (FIXED)
    df.columns = df.columns.astype(str).str.strip()

    # Safely strip only elements that are actually strings
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)

    # 3. DROP EXTRA EMPTY COLUMNS: 3 columns extra hain left mein
    if df.shape[1] > 3:
        df = df.drop(df.columns[:3], axis=1)

    # 4. Standardize Columns
    df = standardize_columns(df)

    # --- HEADER CLEANUP ---
    df.columns = df.columns.astype(str).str.replace(r'\s+', ' ', regex=True).str.strip()

    # ✅ AWB No validation
    awb_col = None
    for candidate in ['AWB No', 'AWB No.', 'AWB NO', 'Awb No']:
        if candidate in df.columns:
            awb_col = candidate
            break

    if awb_col:
        df[awb_col] = df[awb_col].astype(str).str.strip()
        df = df[~df[awb_col].isin(['', 'nan', 'None', 'NAN', 'NaN'])]
        df = df[df[awb_col].notna()]

    # --- EXACT MAPPING ---
    column_mapping = {
        'Sl.No': 'sl_no',
        'Flight No.': 'flight_no',
        'Flight Date': 'flight_date',
        'AWB No': 'awb_no',
        'AWB No.': 'awb_no',
        'SFX': 'sfx',
        'ATA_Date/Time': 'ata_date_time',
        'FLT DOC Arrival_Date/Time': 'flt_doc_arrival_date_time',
        'Last ULD Arrival Date & Time': 'last_uld_arrival_date_time',
        'Bulk ULD Arrival Date & Time': 'bulk_uld_arrival_date_time',
        'Org': 'org',
        'DEST': 'dest',
        'Manifest Pcs': 'manifest_pcs',
        'Manifest Wgt': 'manifest_wgt',
        'SEG Pcs': 'seg_pcs',
        'SEG Wgt': 'seg_wgt',
        'PCS': 'pcs',
        'Gross weight': 'gross_wgt',
        'CHG WGT': 'chg_wgt',
        'Vol(MC)': 'vol_mc',
        'No of Houses': 'no_of_houses',
        'SHC': 'shc',
        'CHG SHC': 'chg_shc',
        'Billing SHC': 'billing_shc',
        'NOG': 'nog',
        'Consignee Details': 'consignee_details',
        'AWD date': 'awd_date',
        'NFD date': 'nfd_date',
        'RCF date': 'rcf_date',
        'DO date&time': 'do_date_time',
        'TFD date&time': 'tfd_date_time',
        'EGM/IGM_NO': 'egm_igm_no',
        'FLT_COM_DAT_TIM': 'flt_com_date_time',
        'FLIGHT STATUS': 'flight_status',
    }

    df_db = df.rename(columns=column_mapping)
    columns_to_keep = list(dict.fromkeys(column_mapping.values()))

    existing_cols = [col for col in columns_to_keep if col in df_db.columns]
    df_db = df_db[existing_cols]

    # --- STRING CONVERSION ---
    string_cols = [
        'flight_no', 'awb_no', 'sfx', 'org', 'dest', 'shc', 'chg_shc',
        'billing_shc', 'nog', 'consignee_details', 'egm_igm_no', 'flight_status',
    ]
    for col in string_cols:
        if col in df_db.columns:
            df_db[col] = df_db[col].astype(str).str.replace(r'\.0$', '', regex=True)
            df_db[col] = df_db[col].replace({'nan': None, 'None': None, 'NaT': None, 'NAN': None})

    # --- DATE ONLY CONVERSION (FIXED: Added dayfirst=True) ---
    date_only_cols = ['flight_date']
    for col in date_only_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_datetime(df_db[col], dayfirst=True, errors='coerce').dt.date

    # --- DATE + TIME CONVERSION TO UTC (FIXED: Added dayfirst=True) ---
    date_time_cols = [
        'ata_date_time', 'flt_doc_arrival_date_time', 'last_uld_arrival_date_time',
        'bulk_uld_arrival_date_time', 'awd_date', 'nfd_date', 'rcf_date',
        'do_date_time', 'tfd_date_time', 'flt_com_date_time',
    ]
    for col in date_time_cols:
        if col in df_db.columns:
            # 1. Convert to datetime
            df_db[col] = pd.to_datetime(df_db[col], dayfirst=True, errors='coerce')
            # 2. IST to UTC
            df_db[col] = (
                df_db[col]
                .dt.tz_localize('Asia/Kolkata', ambiguous='infer')
                .dt.tz_convert('UTC')
                .dt.tz_localize(None)
            )

    # --- NUMERIC CONVERSION ---
    numeric_cols = [
        'sl_no', 'manifest_pcs', 'manifest_wgt', 'seg_pcs', 'seg_wgt',
        'pcs', 'gross_wgt', 'chg_wgt', 'vol_mc', 'no_of_houses',
    ]
    for col in numeric_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_numeric(df_db[col], errors='coerce')

    # ==========================================
    # --- AWB + FLIGHT AGGREGATION LOGIC ---
    # ==========================================
    if not df_db.empty and 'awb_no' in df_db.columns:
        group_cols = ['awb_no']
        if 'flight_no' in df_db.columns:
            group_cols.append('flight_no')

        agg_funcs = {col: 'first' for col in df_db.columns if col not in group_cols}

        metrics_to_sum = [
            'manifest_pcs', 'manifest_wgt', 'seg_pcs', 'seg_wgt',
            'pcs', 'gross_wgt', 'chg_wgt', 'vol_mc', 'no_of_houses'
        ]
        for col in metrics_to_sum:
            if col in df_db.columns:
                agg_funcs[col] = 'sum'

        df_db = df_db.groupby(group_cols, dropna=False, as_index=False).agg(agg_funcs)

    # Handle NaN values for DB insertion
    df_db = df_db.replace({pd.NA: None, float('nan'): None, pd.NaT: None})

    # ==========================================
    # ✅ CHECK 2 REMOVED (per business decision): saara data allow hota hai
    # ab — chahe tfd_date_time same ho, alag ho, ya NULL hi ho.
    # ==========================================
    dropped_count = 0

    if df_db.empty:
        raise ValueError(f"No data found in the uploaded file for {selected_date}.")

    df_db['report_date'] = pd.to_datetime(selected_date).date()
    return df_db, dropped_count