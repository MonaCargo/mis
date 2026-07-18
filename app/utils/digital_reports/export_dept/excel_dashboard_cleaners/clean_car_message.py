




import pandas as pd
import re
from io import BytesIO
from app.utils.digital_reports.export_dept.excel_dashboard_cleaners.base_utils import standardize_columns, combine_date_time  

def _extract_file_date_display(clean_header_text: str) -> str:
    match = re.search(r'(\d{1,2})([A-Z]{3})(\d{4})', clean_header_text)
    if not match:
        match = re.search(r'(\d{1,2})([A-Z]{3})(\d{2})(?!\d)', clean_header_text)

    if not match:
        return "Unknown (no date found in file header)"

    day, mon_abbr, year = match.groups()
    if len(year) == 2:
        year = f"20{year}"

    try:
        parsed = pd.to_datetime(f"{day}{mon_abbr}{year}", format="%d%b%Y")
        return parsed.strftime('%d-%B-%Y')
    except Exception:
        return f"Unrecognized format ({day}{mon_abbr}{year})"


def process_car_message(file_content: bytes, filename: str, selected_date: str):
    file_io = BytesIO(file_content)

    # ==========================================
    # STEP 1: ROBUST HEADER VALIDATION (No CSV Parser)
    # ==========================================
    file_io.seek(0)
    target_dt = pd.to_datetime(selected_date)
    target_str_long = target_dt.strftime('%d%b%Y').upper()  # 24JUN2026
    target_str_short = target_dt.strftime('%d%b%y').upper()  # 24JUN26

    if filename.lower().endswith('.csv'):
        raw_bytes = file_io.read()
        decoded_text = raw_bytes.decode('utf-8', errors='ignore')
        header_lines = decoded_text.splitlines()[:5]
        raw_header_text = "".join(header_lines).upper()
    else:
        header_df = pd.read_excel(file_io, header=None, nrows=5)
        raw_header_text = "".join(header_df.fillna('').values.flatten().astype(str)).upper()

    clean_header_text = re.sub(r'[\s\-/,]', '', raw_header_text)

    if target_str_long not in clean_header_text and target_str_short not in clean_header_text:
        file_date_display = _extract_file_date_display(clean_header_text)
        expected_date_display = target_dt.strftime('%d-%B-%Y')

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
            df = pd.read_csv(file_io, skiprows=5, engine='python', on_bad_lines='skip')
        else:
            df = pd.read_excel(file_io, skiprows=5)
    except Exception as e:
        raise ValueError(f"File reading error: {str(e)}")

    # ==========================================
    # CLEANING
    # ==========================================
    df.columns = df.columns.astype(str).str.strip()
    df = df.map(lambda x: x.strip() if isinstance(x, str) else x)
    df = standardize_columns(df)

  
    total_row_mask = df.apply(
        lambda row: row.astype(str).str.contains('TOTAL', case=False, na=False).any(),
        axis=1
    )
    if total_row_mask.any():
        print(f"Dropped {total_row_mask.sum()} Grand Total/summary row(s) before AWB ffill.")
        df = df[~total_row_mask]

    # AWB Clean & Grouping Prep
    if 'AWB NO.' in df.columns:
        df['AWB NO.'] = df['AWB NO.'].astype(str).str.replace(r'\.0$', '', regex=True)
        df['AWB NO.'] = df['AWB NO.'].replace({'nan': pd.NA, 'None': pd.NA, '': pd.NA})
        df['AWB NO.'] = df['AWB NO.'].ffill()
        df = df.dropna(subset=['AWB NO.'])
        # Filter garbage leftover rows (e.g. the "Date  24-Jun-26" row right after the header)
        df = df[~df['AWB NO.'].str.contains('24-Jun|Date|Time', case=False, na=False)]

    # ==========================================
    # Capture ORIGIN/DESTINATION per AWB BEFORE dropping blank-Sl.No. rows
    # ==========================================
    origin_dest_map = None
    if all(c in df.columns for c in ['AWB NO.', 'ORGIN', 'DESTINATION']):
        origin_dest_map = (
            df.groupby('AWB NO.', as_index=False)
              .agg({'ORGIN': 'first', 'DESTINATION': 'first'})
              .rename(columns={'AWB NO.': 'awb_no', 'ORGIN': '_origin_map', 'DESTINATION': '_destination_map'})
        )

    # ==========================================
    # Drop ONLY rows with blank Sl.No. (data rows, not header/columns)
    # ==========================================
    sl_no_col = 'Sl.No.' if 'Sl.No.' in df.columns else ('Sl. No.' if 'Sl. No.' in df.columns else None)
    if sl_no_col:
        before_count = len(df)
        df = df[df[sl_no_col].notna() & (df[sl_no_col].astype(str).str.strip() != '')].copy()
        skipped = before_count - len(df)
        if skipped > 0:
            print(f"Dropped {skipped} row(s) with blank Sl.No. (summary/destination-only rows).")

    # Combine Date & Time
    df = combine_date_time(df, 'CAR MSG DATE', 'CAR MSG TIME', 'car_msg_date_time')

    # Mapping
    column_mapping = {
        'Sl.No.': 'sl_no', 'AWB NO.': 'awb_no', 'ORGIN': 'origin', 'DESTINATION': 'destination',
        'SB No.': 'sb_no', 'SB DATE': 'sb_date', 'HWB no.': 'hwb_no', 'PCS.': 'pcs',
        'GROSS WT': 'gross_wgt', 'VOLUMETRIC WT': 'volumetric_wgt', 'CHG WT': 'chg_wgt',
        'NOG': 'nog', 'SHC': 'shc'
    }
    if 'Sl. No.' in df.columns: column_mapping['Sl. No.'] = 'sl_no'

    df_db = df.rename(columns=column_mapping)
    columns_to_keep = [c for c in list(column_mapping.values()) + ['car_msg_date_time'] if c in df_db.columns]
    df_db = df_db[columns_to_keep]

    # ==========================================
    # Aggregation
    # ==========================================
    agg_funcs = {col: 'first' for col in df_db.columns if col not in ['pcs', 'gross_wgt', 'volumetric_wgt', 'chg_wgt']}
    agg_funcs.update({'pcs': 'sum', 'gross_wgt': 'sum', 'volumetric_wgt': 'sum', 'chg_wgt': 'sum'})
    if 'awb_no' in df_db.columns:
        df_db = df_db.groupby('awb_no', as_index=False).agg(agg_funcs)

    # ==========================================
    # Merge back origin/destination (lost when blank-Sl.No. rows were dropped)
    # ==========================================
    if origin_dest_map is not None and 'awb_no' in df_db.columns:
        df_db = df_db.merge(origin_dest_map, on='awb_no', how='left')
        if 'origin' in df_db.columns:
            df_db['origin'] = df_db['origin'].fillna(df_db['_origin_map'])
        else:
            df_db['origin'] = df_db['_origin_map']
        if 'destination' in df_db.columns:
            df_db['destination'] = df_db['destination'].fillna(df_db['_destination_map'])
        else:
            df_db['destination'] = df_db['_destination_map']
        df_db = df_db.drop(columns=['_origin_map', '_destination_map'], errors='ignore')

    # STRING, DATE & NUMERIC CONVERSION
    string_cols = ['awb_no', 'origin', 'destination', 'sb_no', 'hwb_no', 'nog', 'shc']
    for col in string_cols:
        if col in df_db.columns:
            df_db[col] = df_db[col].astype(str)
            df_db[col] = df_db[col].str.replace(r'\.0$', '', regex=True)
            df_db[col] = df_db[col].replace({'nan': None, 'None': None, 'NaT': None, 'null': None})
            df_db[col] = df_db[col].where(df_db[col] != 'None', None)

    if 'sb_date' in df_db.columns:
        df_db['sb_date'] = pd.to_datetime(df_db['sb_date'], dayfirst=True, errors='coerce').dt.date

    if 'car_msg_date_time' in df_db.columns:
        df_db['car_msg_date_time'] = pd.to_datetime(df_db['car_msg_date_time'], dayfirst=True, errors='coerce')
        df_db['car_msg_date_time'] = df_db['car_msg_date_time'].dt.tz_localize('Asia/Kolkata', ambiguous='infer').dt.tz_convert('UTC').dt.tz_localize(None)

    for col in ['sl_no', 'pcs', 'gross_wgt', 'volumetric_wgt', 'chg_wgt']:
        if col in df_db.columns:
            df_db[col] = pd.to_numeric(df_db[col], errors='coerce')

    # FINAL FILTER & CLEAN
    df_db = df_db.replace({pd.NA: None, float('nan'): None, pd.NaT: None})

    # ✅ CHECK 2 REMOVED (per business decision): saara data allow hota hai
    # ab — chahe car_msg_date_time same ho, alag ho, ya NULL hi ho.
    dropped_count = 0

    if df_db.empty:
        raise ValueError(f"No data found in the uploaded file for {selected_date}.")

    df_db['report_date'] = pd.to_datetime(selected_date).date()
    print("Check Tail")
    print(df_db.tail(10))
    return df_db, dropped_count