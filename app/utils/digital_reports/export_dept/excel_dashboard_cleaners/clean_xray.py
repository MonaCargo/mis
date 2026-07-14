

import pandas as pd
import re
from io import BytesIO
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.base_utils import _extract_file_date_display, standardize_columns  # smart_filter_operational_date removed (Check 2 disabled)

def process_xray_report(file_content: bytes, filename: str, selected_date: str):
    file_io = BytesIO(file_content)

    # ==========================================
    # STEP 1: CHECK 1 (FILE METADATA / HEADER DATE VALIDATION)
    # ==========================================
    try:
        # Header 8th row par hai, isliye top 7 rows read karenge
        file_io.seek(0)  # ✅ pointer reset (safe practice before every read)

        if filename.lower().endswith('.csv'):
            # ✅ ROOT FIX: header check ko sirf TEXT SEARCH chahiye, structured
            # dataframe nahi. CSV tokenizer (chahe kitna bhi robust banao)
            # field-count mismatch pe poori line hi DROP kar sakta hai
            # (on_bad_lines='skip') — isi wajah se FROM DATE/TO DATE wali
            # line silently skip ho rahi thi aur "not found" aa raha tha.
            # Fix: raw bytes ko seedha text lines me padho, CSV parsing bypass.
            raw_bytes = file_io.read()
            try:
                decoded_text = raw_bytes.decode('utf-8', errors='ignore')
            except Exception:
                decoded_text = raw_bytes.decode('latin-1', errors='ignore')
            header_lines = decoded_text.splitlines()[:7]
            raw_header_text = "".join(header_lines).upper()
        else:
            header_df = pd.read_excel(file_io, header=None, nrows=7)
            raw_header_text = "".join(header_df.fillna('').values.flatten().astype(str)).upper()

        # NORMALIZE: Remove spaces, hyphens, slashes, and commas
        clean_header_text = re.sub(r'[\s\-/,]', '', raw_header_text)

        # Prepare Target Date Variations
        target_dt = pd.to_datetime(selected_date)
        target_str_long = target_dt.strftime('%d%b%Y').upper()  # 24JUN2026
        target_str_short = target_dt.strftime('%d%b%y').upper()  # 24JUN26

        # The Blocker Check (Ab dono me se koi bhi milega toh chal jayega)
        if target_str_long not in clean_header_text and target_str_short not in clean_header_text:
            # raise ValueError(
            #     f"Blocker: File date mismatch. Expected {selected_date}, "
            #     f"but found nothing in the header (Checked for {target_str_long} & {target_str_short})."
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
    file_io.seek(0)

    try:
        if filename.lower().endswith('.csv'):
            # ✅ sep=',' hardcoded (sep=None auto-detect ragged files pe
            # "bad delimiter value" deta hai) + engine='python' aur
            # on_bad_lines='skip' for stability
            df = pd.read_csv(file_io, skiprows=5, sep=',', engine='python', on_bad_lines='skip')
        else:
            df = pd.read_excel(file_io, skiprows=5)
    except Exception as e:
        raise ValueError(f"File reading error: {str(e)}")

    print(f"[DEBUG] After initial read: {len(df)} rows")  # 🔍 DEBUG

    # CLEANING: Remove Extra Spaces
    df.columns = df.columns.astype(str).str.strip()
    df = df.apply(lambda x: x.str.strip() if x.dtype == "object" else x)

    df = standardize_columns(df)
    df.columns = df.columns.astype(str).str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()

    # Drop rows without AWB
    if 'AWB NO.' in df.columns:
        df = df.dropna(subset=['AWB NO.'])

    print(f"[DEBUG] After AWB NO. dropna: {len(df)} rows")  # 🔍 DEBUG

    # MAPPING (saari keys UPPERCASE — df.columns bhi upar .str.upper() se
    # uppercase hi hain, isliye exact case-sensitive match hoga)
    column_mapping = {
        'SL. NO.': 'sl_no', 'SL.NO.': 'sl_no', 'AWB NO.': 'awb_no', 'SB NO.': 'sb_no',
        'SB DATE': 'sb_date', 'ORGIN': 'origin', 'DESTINATION': 'destination',
        'PCS.': 'pcs', 'GROSS WT': 'gross_wgt', 'CHG WT': 'chg_wgt', 'NOG': 'nog',
        'SHC': 'shc', 'CAR MSG DATE/TIME': 'car_msg_date_time',
        'CAR MSG DATE/ TIME': 'car_msg_date_time', 'LEO DATE/TIME': 'leo_date_time',
        'XRAY_START_DT': 'xray_start_date_time', 'XRAY_END_DT': 'xray_end_date_time',
        'X-RAY TYPEX-RAY TYPE': 'xray_type', 'X-RAY DT/TIME': 'xray_date_time',
        'X-RAY-USER': 'xray_user', 'PHS (PCS)': 'phs_pcs', 'ETD (PCS)': 'etd_pcs',
        'EDS (PCS)': 'eds_pcs', 'EDD (PCS)': 'edd_pcs', 'EDD (PCS': 'edd_pcs',
        'VCK (PCS)': 'vck_pcs', 'VCK (PCS': 'vck_pcs', 'CMD (PCS)': 'cmd_pcs',
        'CMD (PCS': 'cmd_pcs', 'DOC ACCPT DT/ TIME': 'doc_accept_date_time',
        'DOC ACCPT DT/ TIM': 'doc_accept_date_time', 'RCS/RCF/RCT DT/TIME': 'rcs_rcf_rct_date_time',
        'RCS/RCF/RCT DT T': 'rcs_rcf_rct_date_time', 'UPLIFTING DT/TIME': 'uplifting_date_time',
        'FLT NO': 'flt_no', 'AGENT NAME': 'agent_name', 'SERIAL NO.': 'serial_no',
        'DEVICE MODEL NO.': 'device_model', 'DEVICE MODEL M': 'device_model',
        'REMARKS': 'remarks'
    }

    df_db = df.rename(columns=column_mapping)
    columns_to_keep = list(dict.fromkeys(column_mapping.values()))
    existing_cols = [col for col in columns_to_keep if col in df_db.columns]
    df_db = df_db[existing_cols]

    # DATE CONVERSION (UTC)
    if 'sb_date' in df_db.columns:
        df_db['sb_date'] = pd.to_datetime(df_db['sb_date'], errors='coerce').dt.date

    date_time_cols = [
        'car_msg_date_time', 'leo_date_time', 'xray_start_date_time',
        'xray_end_date_time', 'xray_date_time', 'doc_accept_date_time',
        'rcs_rcf_rct_date_time', 'uplifting_date_time'
    ]
    for col in date_time_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_datetime(df_db[col], errors='coerce')
            df_db[col] = df_db[col].dt.tz_localize('Asia/Kolkata', ambiguous='infer').dt.tz_convert('UTC').dt.tz_localize(None)

    # STRING & NUMERIC
    string_cols = ['awb_no', 'sb_no', 'origin', 'destination', 'nog', 'shc', 'xray_type', 'xray_user', 'flt_no', 'agent_name', 'serial_no', 'device_model', 'remarks']
    for col in string_cols:
        if col in df_db.columns:
            df_db[col] = df_db[col].astype(str).str.replace(r'\.0$', '', regex=True).replace({'nan': None, 'None': None, 'NaT': None})

    numeric_cols = ['sl_no', 'pcs', 'gross_wgt', 'chg_wgt', 'phs_pcs', 'etd_pcs', 'eds_pcs', 'edd_pcs', 'vck_pcs', 'cmd_pcs']
    for col in numeric_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_numeric(df_db[col], errors='coerce')

    # AGGREGATION
    if not df_db.empty and 'awb_no' in df_db.columns:
        agg_funcs = {col: 'first' for col in df_db.columns if col != 'awb_no'}
        metrics_to_sum = ['pcs', 'gross_wgt', 'chg_wgt', 'phs_pcs', 'etd_pcs', 'eds_pcs', 'edd_pcs', 'vck_pcs', 'cmd_pcs']
        for col in metrics_to_sum:
            if col in df_db.columns:
                agg_funcs[col] = 'sum'
        df_db = df_db.groupby('awb_no', as_index=False).agg(agg_funcs)

    print(f"[DEBUG] After groupby(awb_no): {len(df_db)} rows")  # 🔍 DEBUG

    df_db = df_db.replace({pd.NA: None, float('nan'): None, pd.NaT: None})

    # ✅ CHECK 2 REMOVED (per business decision): pehle yahan
    # smart_filter_operational_date() call hoti thi jo sirf matching-date
    # rows rakhti thi aur baaki drop kar deti thi. Ab saara data allow hota
    # hai — chahe date same ho, alag ho, ya xray_date_time NULL hi kyun na
    # ho. Sirf Check 1 (header/metadata date validation) abhi bhi active
    # hai, jo file-level sanity check hai.
    dropped_count = 0

    if df_db.empty:
        raise ValueError(f"No data found in the uploaded file for {selected_date}.")

    df_db['report_date'] = pd.to_datetime(selected_date).date()

    return df_db, dropped_count