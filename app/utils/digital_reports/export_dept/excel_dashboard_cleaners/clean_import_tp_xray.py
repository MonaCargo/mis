

import pandas as pd
import re
from io import BytesIO
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.base_utils  import _extract_file_date_display, standardize_columns  # smart_filter_operational_date removed (Check 2 disabled)

def process_import_tp_xray(file_content: bytes, filename: str, selected_date: str) -> pd.DataFrame:
    file_io = BytesIO(file_content)

    # ==========================================
    # STEP 1: CHECK 1 (FILE METADATA / HEADER DATE VALIDATION)
    # ==========================================
    try:
        file_io.seek(0)  # ✅ safe practice

        # ✅ FIX: CSV ke liye ab raw TEXT SEARCH — pandas CSV tokenizer bypass.
        # Header check ko structured dataframe ki zaroorat nahi, sirf text
        # match chahiye. Isse "Expected N fields, saw M" jaisi tokenizing
        # crashes aur ragged-line drop dono issues khatam ho jate hain.
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

        # ✅ FIX: dono date formats check karo (long aur short year), warna
        # jo files short-year format ('24JUN26') use karti hain unpe false
        # blocker aayega.
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
            # ✅ FIX: sep=',' explicit (auto-detect "bad delimiter value" deta
            # hai) + engine='python' + on_bad_lines='skip' for stability
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

    # --- BULLETPROOF HEADER CLEANUP ---
    df.columns = df.columns.astype(str).str.replace(r'\s+', ' ', regex=True).str.strip().str.upper()

    # AWB No validation
    if 'AWB NO.' in df.columns:
        df['AWB NO.'] = df['AWB NO.'].astype(str).str.strip()
        df = df[~df['AWB NO.'].isin(['', 'nan', 'None', 'NAN', 'NaN'])]
        df = df[df['AWB NO.'].notna()]

    # Mapping (saari keys UPPERCASE — df.columns bhi upar .str.upper() se
    # uppercase hi hain, isliye exact case-sensitive match hoga)
    column_mapping = {
        'SL. NO.': 'sl_no', 'SL.NO.': 'sl_no',
        'AWB NO.': 'awb_no', 'ORGIN': 'origin', 'DESTINATION': 'destination',
        'PCS.': 'pcs', 'GROSS WT': 'gross_wgt', 'CHG WT': 'chg_wgt',
        'NOG': 'nog', 'SHC': 'shc', 'X-RAY STRT DATE & TIME': 'xray_start_date_time',
        'X-RAY END DATE & TIME': 'xray_end_date_time', 'X-RAY TYPE': 'xray_type',
        'X-RAY DT/TIME': 'xray_date_time', 'X-RAY-USE': 'xray_user', 'X-RAY-USER': 'xray_user',
        'PHS (PCS)': 'phs_pcs', 'ETD (PCS)': 'etd_pcs', 'EDS (PCS)': 'eds_pcs',
        'EDD (PCS)': 'edd_pcs', 'VCK (PCS)': 'vck_pcs', 'CMD (PCS)': 'cmd_pcs',
        'CMD (PCS': 'cmd_pcs', 'PHS(PCS)': 'phs_pcs', 'ETD(PCS)': 'etd_pcs',
        'EDS(PCS)': 'eds_pcs', 'EDD(PCS)': 'edd_pcs', 'VCK(PCS)': 'vck_pcs',
        'CMD(PCS)': 'cmd_pcs', 'RCS/RCF/RCT DT/TIME': 'rcs_rcf_rct_date_time',
        'RCS/RCF/RCT DT T': 'rcs_rcf_rct_date_time', 'UPLIFTING DT/TIME': 'uplifting_date_time',
        'FLT NO': 'flt_no', 'AGENT NAME': 'agent_name', 'SERIAL NO.': 'serial_no',
        'DEVICE MODEL NO.': 'device_model_no', 'DEVICE MODEL N': 'device_model_no',
        'REMARKS': 'remarks'
    }

    df_db = df.rename(columns=column_mapping)
    columns_to_keep = list(dict.fromkeys(column_mapping.values()))
    existing_cols = [col for col in columns_to_keep if col in df_db.columns]
    df_db = df_db[existing_cols]

    # --- DATE + TIME CONVERSION (TO UTC) ---
    date_time_cols = [
        'xray_start_date_time', 'xray_end_date_time', 'xray_date_time',
        'rcs_rcf_rct_date_time', 'uplifting_date_time'
    ]
    for col in date_time_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_datetime(df_db[col], errors='coerce')
            df_db[col] = (
                df_db[col]
                .dt.tz_localize('Asia/Kolkata', ambiguous='infer')
                .dt.tz_convert('UTC')
                .dt.tz_localize(None)
            )

    # --- STRING CONVERSION ---
    string_cols = [
        'serial_no', 'awb_no', 'flt_no', 'xray_type',
        'destination', 'nog', 'shc', 'agent_name',
        'origin', 'xray_user', 'device_model_no', 'remarks'
    ]
    for col in string_cols:
        if col in df_db.columns:
            df_db[col] = df_db[col].astype(str).str.replace(r'\.0$', '', regex=True)
            df_db[col] = df_db[col].replace({'nan': None, 'None': None, 'NaT': None})

    # --- NUMERIC CONVERSION ---
    numeric_cols = [
        'sl_no', 'pcs', 'gross_wgt', 'chg_wgt', 'phs_pcs',
        'etd_pcs', 'eds_pcs', 'edd_pcs', 'vck_pcs', 'cmd_pcs'
    ]
    for col in numeric_cols:
        if col in df_db.columns:
            df_db[col] = pd.to_numeric(df_db[col], errors='coerce')

    # ==========================================
    # --- AWB AGGREGATION LOGIC ---
    # ==========================================
    # ⚠️ NOTE: agar ek AWB legitimately 2 baar file me aata hai (jaise partial
    # consignment split), toh ye step unhe EK row me merge (sum) kar dega aur
    # doosri entry ki details (first-wins) discard ho jayengi. X-ray cleaner
    # me humne yehi behavior dekha tha jisse 257 rows se 145 reh gayi thi.
    # Agar tumhare business rules me duplicate-AWB legitimate hai, ye poora
    # groupby block hataana padega.
    if not df_db.empty and 'awb_no' in df_db.columns:
        agg_funcs = {col: 'first' for col in df_db.columns if col != 'awb_no'}
        metrics_to_sum = [
            'pcs', 'gross_wgt', 'chg_wgt', 'phs_pcs',
            'etd_pcs', 'eds_pcs', 'edd_pcs', 'vck_pcs', 'cmd_pcs'
        ]
        for col in metrics_to_sum:
            if col in df_db.columns:
                agg_funcs[col] = 'sum'
        df_db = df_db.groupby('awb_no', as_index=False).agg(agg_funcs)

    df_db = df_db.replace({pd.NA: None, float('nan'): None, pd.NaT: None})

    # ✅ CHECK 2 REMOVED (per business decision): saara data allow hota hai
    # ab — chahe date same ho, alag ho, ya xray_date_time NULL hi ho.
    # Sirf Check 1 (header/metadata date validation) active hai.
    dropped_count = 0

    if df_db.empty:
        raise ValueError(f"No data found in the uploaded file for {selected_date}.")

    df_db['report_date'] = pd.to_datetime(selected_date).date()

    return df_db, dropped_count