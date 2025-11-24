# from datetime import datetime

# import pandas as pd


# def clean_column_names(df: pd.DataFrame) -> pd.DataFrame:
#     """Clean column names - remove extra spaces, quotes, and standardize"""
#     df.columns = (
#         df.columns
#         .str.strip()
#         .str.replace(r'\s+', '_', regex=True)
#         .str.replace(r'["\']', '', regex=True)
#         .str.upper()
#     )
    
#     # Map column names to standard names
#     column_mapping = {
#         'FLT_NO': 'flt_no',
#         'FLT_DATE': 'flt_date',
#         'AWB_NUMBER': 'awb_number',
#         'HWB_NUM': 'hwb_num',
#         'ORG': 'org',
#         'DEST': 'dest',
#         'TOT_PCS': 'tot_pcs',
#         'TOT_WGT': 'tot_wgt',
#         'ULD_NUMBER': 'uld_number',
#         'SEG_DATE': 'seg_date',
#         'AGT': 'agt',
#         'IRR_CODE': 'irr_code',
#         'PCS': 'pcs',
#         'OPEN_REMARKS': 'open_remarks',
#         'IRR_OPEN_DATE/TIME': 'irr_open_datetime',
#         'IRR_CLOSE_DATE/TIME': 'irr_close_datetime',
#         'COSYS_ID': 'cosys_id',
#         'CLOSING_REMARKS': 'closing_remarks',
#         'PERFORMANCE_(IRR_CLOSE-OPEN)': 'performance'
#     }
    
#     df.columns = [column_mapping.get(col, col.lower()) for col in df.columns]
#     return df


# def parse_datetime(date_val):
#     """Parse various datetime formats and convert to UTC"""
#     if pd.isna(date_val) or date_val == '':
#         return None
    
#     if isinstance(date_val, datetime):
#         # If already datetime, ensure it's UTC
#         if date_val.tzinfo is None:
#             # Assume naive datetime is UTC
#             return date_val.replace(tzinfo=None)
#         else:
#             # Convert to UTC and remove timezone info for storage
#             return date_val.astimezone(datetime.timezone.utc).replace(tzinfo=None)
    
#     date_str = str(date_val).strip()
    
#     # Try common formats
#     formats = [
#         '%Y-%m-%d %H:%M:%S',
#         '%Y-%m-%d %H:%M',
#         '%Y-%m-%d',
#         '%d-%m-%Y %H:%M:%S',
#         '%d-%m-%Y %H:%M',
#         '%d-%m-%Y',
#         '%d/%m/%Y %H:%M:%S',
#         '%d/%m/%Y %H:%M',
#         '%d/%m/%Y',
#         '%m/%d/%Y %H:%M:%S',
#         '%m/%d/%Y %H:%M',
#         '%m/%d/%Y',
#     ]
    
#     for fmt in formats:
#         try:
#             # Parse and assume UTC (naive datetime)
#             return datetime.strptime(date_str, fmt)
#         except (ValueError, TypeError):
#             continue
    
#     return None


# def clean_irregularity_report(df: pd.DataFrame) -> pd.DataFrame:
#     """Main cleaning function for flight irregularity data"""
    
#     # 1. Clean column names
#     df = clean_column_names(df)
    
#     # 2. Remove completely empty rows
#     df = df.dropna(how='all')
    
#     # 3. Strip whitespace from all string columns
#     string_columns = df.select_dtypes(include=['object']).columns
#     for col in string_columns:
#         df[col] = df[col].apply(lambda x: x.strip() if isinstance(x, str) else x)
    
#     # 4. Parse datetime columns and convert to UTC
#     datetime_columns = ['flt_date', 'seg_date', 'irr_open_datetime', 'irr_close_datetime']
#     for col in datetime_columns:
#         if col in df.columns:
#             df[col] = df[col].apply(parse_datetime)
    
#     # 5. Clean numeric columns
#     if 'tot_pcs' in df.columns:
#         df['tot_pcs'] = pd.to_numeric(df['tot_pcs'], errors='coerce')
#     if 'pcs' in df.columns:
#         df['pcs'] = pd.to_numeric(df['pcs'], errors='coerce')
#     if 'tot_wgt' in df.columns:
#         df['tot_wgt'] = pd.to_numeric(df['tot_wgt'], errors='coerce')
    
#     # 6. Clean airport codes - preserve as-is, just strip whitespace
#     for col in ['org', 'dest']:
#         if col in df.columns:
#             df[col] = df[col].apply(
#                 lambda x: str(x).strip() if pd.notna(x) and x != '' else None
#             )
    
#     # 7. Clean AWB numbers - preserve as-is, just strip whitespace
#     if 'awb_number' in df.columns:
#         df['awb_number'] = df['awb_number'].apply(
#             lambda x: str(x).strip() if pd.notna(x) and x != '' else None
#         )
    
#     # 8. Replace empty strings with None
#     df = df.replace(['', 'nan', 'NaN', 'None'], None)
    
#     return df










import pandas as pd
import numpy as np
from datetime import datetime
import pytz



import re

def normalize_awb_no(value) -> str:
    if not value:
        return None
    # Safe conversion to string
    value = str(value)
    cleaned = re.sub(r'\D', '', value)
    if len(cleaned) == 10:
        return '0' + cleaned
    elif len(cleaned) == 11:
        return cleaned
    else:
        return None



def clean_irregularities_file(file, file_type: str) -> pd.DataFrame:
    """
    Cleans IRREGULARITIES file (CSV or Excel), trims rows, renames columns,
    and converts all date/time fields to UTC.
    
    Parameters:
        file: Uploaded file object
        file_type: 'csv' or 'excel'
    
    Returns:
        Cleaned pandas DataFrame with UTC timestamps
    """
    # Read file based on type
    if file_type == "excel":
        df = pd.read_excel(file, header=8)
    elif file_type == "csv":
        df = pd.read_csv(file,header=8)
    elif file_type == "CSV":
        df = pd.read_csv(file,header=8)
    else:
        raise ValueError("Unsupported file type. Use 'csv' or 'excel'.")
    
    # Drop last 2 rows and first two columns
    df = df.iloc[:-2, 2:]
    
    # Drop rows where all columns are NaN
    df = df.dropna(how='all')
    
    # Column renaming map
    column_mapping = {
        'FLT_NO': 'flt_no',
        'FLT_DATE': 'flt_date',
        'AWB NUMBER': 'awb_no',
        'HWB_NUM': 'hwb_no',
        'ORG': 'org',
        'DEST': 'dest',
        'TOT_PCS': 'tot_pcs',
        'TOT_WGT': 'tot_wgt',
        'ULD NUMBER': 'uld_number',
        'SEG_DATE': 'seg_date',
        'AGT': 'agt',
        'IRR_CODE': 'irr_code',
        'PCS': 'pcs',
        'OPEN REMARKS': 'open_remarks',
        '\tIRR_OPEN DATE/TIME': 'irr_open_date_time',
        '\tIRR_CLOSE DATE/TIME': 'irr_close_date_time',
        '\tCOSYS ID': 'cosys_id',
        '\tCLOSING REMARKS\t': 'closing_remarks',
        'PERFORMANCE (IRR CLOSE-OPEN)': 'performance_irr_close_open'
    }
    
    # Rename columns
    df = df[list(column_mapping.keys())].rename(columns=column_mapping)


# ✅ Normalize AWB number immediately after renaming
    if 'awb_no' in df.columns:
        df['awb_no'] = df['awb_no'].apply(normalize_awb_no)
    
    # Define date/time columns that need UTC conversion
    datetime_columns = [
        'flt_date',
        'seg_date',
        'irr_open_date_time',
        'irr_close_date_time'
    ]
    
    # UTC conversion function with multiple format support
    def to_utc(dt_str):
        try:
            # Handle NaN, None, empty strings
            if pd.isna(dt_str) or str(dt_str).strip() in ['', 'nan', 'None', 'NaT']:
                return None
            
            dt_str = str(dt_str).strip()
            
            # Try multiple datetime formats
            formats = [
                "%Y-%m-%d %H:%M:%S",      # 2025-01-25 14:30:45
                "%d-%m-%Y %H:%M:%S",      # 25-01-2025 14:30:45
                "%d/%m/%Y %H:%M:%S",      # 25/01/2025 14:30:45
                "%Y-%m-%d",               # 2025-01-25 (date only)
                "%d-%m-%Y",               # 25-01-2025 (date only)
                "%d/%m/%Y",               # 25/01/2025 (date only)
                "%d-%b-%Y %H:%M:%S",      # 25-Jan-2025 14:30:45
                "%d-%b-%Y",               # 25-Jan-2025 (date only)
            ]
            
            local_dt = None
            for fmt in formats:
                try:
                    local_dt = datetime.strptime(dt_str, fmt)
                    break
                except ValueError:
                    continue
            
            if local_dt is None:
                print(f"Warning: Could not parse datetime '{dt_str}'")
                return None
            
            # Localize to Asia/Kolkata timezone
            local_dt = pytz.timezone("Asia/Kolkata").localize(local_dt)
            
            # Convert to UTC (timezone-aware)
            utc_dt = local_dt.astimezone(pytz.utc)
            
            return utc_dt
            
        except Exception as e:
            print(f"Error converting datetime '{dt_str}': {e}")
            return None
    
    # Apply UTC conversion to datetime columns
    for col in datetime_columns:
        if col in df.columns:
            df[col] = df[col].apply(to_utc)
    
    # Convert numeric columns
    numeric_columns = ['tot_pcs', 'tot_wgt', 'pcs']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            # Convert tot_pcs and pcs to integers
            if col in ['tot_pcs', 'pcs']:
                df[col] = df[col].apply(lambda x: int(x) if pd.notna(x) else None)
    
    # Clean string columns - remove extra spaces and convert empty to None
    string_columns = [
        'flt_no', 'awb_no', 'hwb_no', 'org', 'dest', 'uld_number',
        'agt', 'irr_code', 'open_remarks', 'cosys_id', 'closing_remarks',
        'performance_irr_close_open'
    ]
    
    for col in string_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace(['nan', 'None', 'NaT', '', 'N/A'], None)
    
    # Replace pandas NaN/NaT with Python None for database compatibility
    df = df.replace({np.nan: None, pd.NaT: None})
    
    return df
