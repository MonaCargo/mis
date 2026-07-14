

import pandas as pd
import re
from io import BytesIO
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.base_utils  import _extract_file_date_display, standardize_columns  # smart_filter_operational_date removed (Check 2 disabled)

def process_export_tp_xray(file_content: bytes, filename: str, selected_date: str) -> pd.DataFrame:
    file_io = BytesIO(file_content)

    # ==========================================
    # STEP 1: CHECK 1 (FILE METADATA / HEADER DATE VALIDATION)
    # ==========================================
    try:
        file_io.seek(0)  # ✅ safe practice

        # ✅ FIX: CSV ke liye raw TEXT SEARCH — pandas CSV tokenizer bypass,
        # koi delimiter/field-count crash ya silent-line-drop nahi hoga.
        if filename.lower().endswith('.csv'):
            raw_bytes = file_io.read()
            try:
                decoded_text = raw_bytes.decode('utf-8', errors='ignore')
            except Exception:
                decoded_text = raw_bytes.decode('latin-1', errors='ignore')
            header_lines = decoded_text.splitlines()[:5]
            raw_header_text = "".join(header_lines).upper()
        else:
            header_df = pd.read_excel(file_io, header=None, nrows=5)
            raw_header_text = str(header_df.values).upper()

        # NORMALIZE: Remove spaces, hyphens, slashes, and commas
        clean_header_text = re.sub(r'[\s\-/,]', '', raw_header_text)

        # ✅ FIX: long aur short year format dono check karo
        target_dt = pd.to_datetime(selected_date)
        target_str_long = target_dt.strftime('%d%b%Y').upper()   # 24JUN2026
        target_str_short = target_dt.strftime('%d%b%y').upper()  # 24JUN26

        # The Blocker Check
        if target_str_long not in clean_header_text and target_str_short not in clean_header_text:
            # raise ValueError(
            #     f"Blocker: Uploaded file does not belong to {selected_date}. "
            #     f"The target date was not found in the file's header area "
            #     f"(Checked for {target_str_long} & {target_str_short})."
            # )
            file_date_display = _extract_file_date_display(clean_header_text)
            expected_date_display = target_dt.strftime('%d-%B-%Y')  # e.g. 14-July-2026

            raise ValueError(
            f"Blocker: File date mismatch. File date is {file_date_display}, "
            f"but your selected date is {expected_date_display}."
        )
    except Exception as e:
        if isinstance(e, ValueError):
            raise e
        raise ValueError(f"Header reading error: {str(e)}")

    # ==========================================
    # STEP 2: LOAD & CLEAN ACTUAL DATA
    # ==========================================
    file_io.seek(0)  # Pointer ko wapas zero pe laao reading ke liye

    # 1. READ FILE: Header 6th row par hai, isliye skiprows=5
    try:
        if filename.lower().endswith('.csv'):
            # ✅ FIX: sep=',' explicit + engine='python' + on_bad_lines='skip'
            df = pd.read_csv(file_io, skiprows=5, sep=',', engine='python', on_bad_lines='skip')
        else:
            df = pd.read_excel(file_io, skiprows=5)
    except Exception as e:
        raise ValueError(f"File reading error: {str(e)}")

    # 2. CLEANING: Remove Extra Spaces from Headers and Cells
    df.columns = df.columns.astype(str).str.strip()
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

    # 3. Standardize Columns
    df = standardize_columns(df)

    # --- ULTIMATE HEADER CLEANUP ---
    df.columns = df.columns.astype(str).str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()

    # ✅ AWB No validation
    if 'AWB NO.' in df.columns:
        df['AWB NO.'] = df['AWB NO.'].astype(str).str.strip()
        df = df[~df['AWB NO.'].isin(['', 'nan', 'None', 'NAN', 'NaN'])]
        df = df[df['AWB NO.'].notna()]

    # --- EXACT MAPPING WITH UPPERCASE KEYS ---
    column_mapping = {
        'SL. NO.': 'sl_no',
        'SL.NO.': 'sl_no',
        'AWB NO.': 'awb_no',
        'ORGIN': 'origin',
        'DESTINATION': 'destination',
        'PCS.': 'pcs',
        'GROSS WT': 'gross_wgt',
        'CHG WT': 'chg_wgt',
        'NOG': 'nog',
        'SHC': 'shc',
        'X-RAY START DATE & TIME': 'xray_start_date_time',
        'X-RAY END DATE & TIME': 'xray_end_date_time',
        'X-RAY TYPE': 'xray_type',
        'X-RAY DT/TIME': 'xray_date_time',
        'X-RAY-USER': 'xray_user',
        'DOC ACCPT DT/ TIME': 'doc_accept_date_time',
        'RCS/RCF/RCT DT/TIME': 'rcs_rcf_rct_date_time',
        'UPLIFTING DT/TIME': 'uplifting_date_time',
        'FLT NO': 'flt_no',
        'AGENT NAME': 'agent_name',
        'SERIAL NO.': 'serial_no',
        'DEVICE MODEL NO.': 'device_model_no',
        'REMARKS': 'remarks'
    }

    df_db = df.rename(columns=column_mapping)
    columns_to_keep = list(dict.fromkeys(column_mapping.values()))

    existing_cols = [col for col in columns_to_keep if col in df_db.columns]
    df_db = df_db[existing_cols]

    # --- STRING CONVERSION ---
    
    string_cols = [
       'awb_no', 'origin', 'destination', 'nog', 'shc',
        'xray_type', 'xray_user', 'flt_no', 'agent_name',
        'device_model_no', 'remarks']
   
    for col in string_cols:
        if col in df_db.columns:
            df_db[col] = df_db[col].astype(str).str.replace(r'\.0$', '', regex=True)
            df_db[col] = df_db[col].replace({'nan': None, 'None': None, 'NaT': None, 'NAN': None})

    # --- DATE CONVERSION (WITH UTC) ---
    date_columns = [
        'xray_start_date_time', 'xray_end_date_time', 'xray_date_time',
        'doc_accept_date_time', 'rcs_rcf_rct_date_time', 'uplifting_date_time'
    ]
    for col in date_columns:
        if col in df_db.columns:
            # 1. Convert to Datetime
            df_db[col] = pd.to_datetime(df_db[col], errors='coerce')
            # 2. IST -> UTC Conversion
            df_db[col] = (
                df_db[col]
                .dt.tz_localize('Asia/Kolkata', ambiguous='infer')
                .dt.tz_convert('UTC')
                .dt.tz_localize(None)
            )

    # --- NUMERIC CONVERSION ---
    # ✅ FIX: 'serial_no' yahan se hata diya (ab string_cols me hai)
    numeric_cols = ['sl_no', 'pcs', 'gross_wgt', 'chg_wgt', 'serial_no']

    for col in numeric_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_numeric(df_db[col], errors='coerce')

    # ==========================================
    # --- AWB AGGREGATION LOGIC ---
    # ==========================================
    # ⚠️ NOTE: same known behavior — agar ek AWB legitimately 2 baar file me
    # aata hai, ye row ko merge/sum kar dega. Business rules confirm karke
    # dekh lena jaise import_tp_xray me discuss kiya tha.
    if not df_db.empty and 'awb_no' in df_db.columns:
        agg_funcs = {col: 'first' for col in df_db.columns if col != 'awb_no'}
        metrics_to_sum = ['pcs', 'gross_wgt', 'chg_wgt']
        for col in metrics_to_sum:
            if col in df_db.columns:
                agg_funcs[col] = 'sum'
        df_db = df_db.groupby('awb_no', as_index=False).agg(agg_funcs)
    # ==========================================

    df_db = df_db.replace({pd.NA: None, float('nan'): None, pd.NaT: None})

    # ✅ CHECK 2 REMOVED (per business decision): saara data allow hota hai.
    dropped_count = 0

    if df_db.empty:
        raise ValueError(f"No data found in the uploaded file for {selected_date}.")

    df_db['report_date'] = pd.to_datetime(selected_date).date()

    return df_db, dropped_count