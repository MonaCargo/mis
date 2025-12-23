










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




def clean_and_parse_oc_report(file, file_type: str) -> pd.DataFrame:
    """
    Cleans and parses a CSV or Excel file, renames columns, and converts integrate_date_time to UTC.
    
    Parameters:
        file: Uploaded file object
        file_type: 'csv' or 'excel'
    
    Returns:
        Cleaned pandas DataFrame with UTC timestamps
    """
    # Read file
    if file_type.lower() == "csv": # it take both capital and small csv extension
        df = pd.read_csv(file,header=5)
    elif file_type == "excel":
        df = pd.read_excel(file, header=5)
    else:
        raise ValueError("Unsupported file type. Use 'csv' or 'excel'.")
    
    # Drop first two columns
    df = df.iloc[:, 2:]
    
    # Rename columns
    require_column_name = {
        'MSGID': 'msg_id',
        ' AWBNO': 'awb_no',
        'HWBNO': 'hawb_no',
        'OC NO ': 'oc_no',
        'BOE NO': 'boe_no',
        'PCS': 'pcs',
        'INTEGRATE DATE & TIME': 'integrate_date_time',
    }
    
    # RENAME THE COLUMN  
    df = df[list(require_column_name.keys())].rename(columns=require_column_name)

    # ✅ Normalize AWB number
    if 'awb_no' in df.columns:
        df['awb_no'] = df['awb_no'].apply(normalize_awb_no)

    
    
    def to_utc(dt_str):
        try:
            # Handle NaN, None, empty strings
            if pd.isna(dt_str) or str(dt_str).strip() in ['', 'nan', 'None', 'NaT']:
                return None
            
            dt_str = str(dt_str).strip()
            
            # Try multiple date formats
            formats = [
                "%d-%b-%Y %H:%M:%S",      # 25-Jan-2025 14:30:45
                "%d-%m-%Y %H:%M:%S",      # 25-01-2025 14:30:45
                "%Y-%m-%d %H:%M:%S",      # 2025-01-25 14:30:45
                "%d/%m/%Y %H:%M:%S",      # 25/01/2025 14:30:45
            ]
            
            local_dt = None
            for fmt in formats:
                try:
                    local_dt = datetime.strptime(dt_str, fmt)
                    break
                except ValueError:
                    continue
            
            if local_dt is None:
                print(f"Could not parse datetime: '{dt_str}'")
                return None
            
            # Localize to Asia/Kolkata timezone
            local_dt = pytz.timezone("Asia/Kolkata").localize(local_dt)
            
            # Convert to UTC (timezone-aware)
            utc_dt = local_dt.astimezone(pytz.utc)
            
            return utc_dt
            
        except Exception as e:
            print(f"Error converting datetime '{dt_str}': {e}")
            return None



    # Apply UTC conversion
    df["integrate_date_time"] = df["integrate_date_time"].apply(to_utc)

    # ❗ Validate missing integrate_date_time
    missing = df[df["integrate_date_time"].isna()]
    if not missing.empty:
        raise ValueError(
            f"{len(missing)} rows have missing or invalid INTEGRATE DATE & TIME."
        )
    
    # Convert PCS to integer, handle NaN
     # ✅ Convert PCS to integer, keep NULL if missing (don't default to 0)
    df["pcs"] = pd.to_numeric(df["pcs"], errors='coerce')
    df["pcs"] = df["pcs"].apply(lambda x: int(x) if pd.notna(x) else None)
    
    # Clean string columns - remove extra spaces and convert empty to None
    string_columns = ['msg_id', 'awb_no', 'hawb_no', 'oc_no', 'boe_no']
    for col in string_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace(['nan', 'None', 'NaT', '', 'N/A'], None)
    
    # Replace pandas NaN/NaT with Python None for database compatibility
    df = df.replace({np.nan: None, pd.NaT: None})
    
    return df





















# import pandas as pd
# import numpy as np
# from datetime import datetime
# import pytz

# def clean_and_parse_oc_report(file, file_type: str) -> pd.DataFrame:
#     """
#     Cleans and parses a CSV or Excel file, renames columns, and converts integrate_date_time to UTC.
#     """
#     try:
#         # Read Excel file with proper header row
#         if file_type == "csv":
#             df = pd.read_csv(file)
#         elif file_type == "excel":
#             df = pd.read_excel(file, header=4)  # Header at row 5
#         else:
#             raise ValueError("Unsupported file type. Use 'csv' or 'excel'.")
        
#         print(f"Initial DataFrame shape: {df.shape}")
#         print("First few rows of integrate_date_time:")
#         print(df['INTEGRATE DATE & TIME'].head().tolist())
        
#         # Clean column names
#         df.columns = df.columns.astype(str).str.strip()
        
#         # Define required columns
#         require_column_name = {
#             'MSGID': 'msg_id',
#             'AWBNO': 'awb_no',
#             'HWBNO': 'hawb_no', 
#             'OC NO': 'oc_no',
#             'BOE NO': 'boe_no',
#             'PCS': 'pcs',
#             'INTEGRATE DATE & TIME': 'integrate_date_time',
#         }
        
#         # Select and rename columns
#         df = df[list(require_column_name.keys())].rename(columns=require_column_name)
        
#         # FIXED: Better datetime conversion
#         def to_utc(dt_val):
#             try:
#                 if pd.isna(dt_val) or str(dt_val).strip() in ['', 'nan', 'None', 'NaT', 'NULL']:
#                     return None
                
#                 dt_str = str(dt_val).strip()
#                 print(f"Original datetime string: '{dt_str}'")
                
#                 # Handle Excel datetime objects (they might be already parsed)
#                 if isinstance(dt_val, (datetime, pd.Timestamp)):
#                     parsed_dt = dt_val
#                     print(f"Already a datetime object: {parsed_dt}")
#                 else:
#                     # Try parsing as string - your data shows "11/3/2025 23:40"
#                     # This could be MM/DD/YYYY or DD/MM/YYYY
#                     date_formats = [
#                         "%m/%d/%Y %H:%M",      # 11/3/2025 23:40 (US format)
#                         "%d/%m/%Y %H:%M",      # 11/3/2025 23:40 (EU format)
#                         "%m/%d/%Y %H:%M:%S",   # With seconds
#                         "%d/%m/%Y %H:%M:%S",   # With seconds
#                         "%Y-%m-%d %H:%M:%S",   # ISO format
#                         "%Y-%m-%d %H:%M",      # ISO format without seconds
#                     ]
                    
#                     parsed_dt = None
#                     for fmt in date_formats:
#                         try:
#                             parsed_dt = datetime.strptime(dt_str, fmt)
#                             print(f"Successfully parsed with format: {fmt}")
#                             break
#                         except ValueError:
#                             continue
                    
#                     if parsed_dt is None:
#                         # Last resort: let pandas try to parse it
#                         try:
#                             parsed_dt = pd.to_datetime(dt_str)
#                             print(f"Pandas parsed it: {parsed_dt}")
#                         except:
#                             print(f"Could not parse datetime: {dt_str}")
#                             return None
                
#                 # Ensure we have a timezone-aware datetime
#                 if parsed_dt.tzinfo is None:
#                     # Assume the time is in Asia/Kolkata timezone
#                     localized_dt = pytz.timezone("Asia/Kolkata").localize(parsed_dt)
#                 else:
#                     localized_dt = parsed_dt
                
#                 # Convert to UTC
#                 utc_dt = localized_dt.astimezone(pytz.utc)
#                 print(f"Final UTC datetime: {utc_dt}")
#                 return utc_dt
                
#             except Exception as e:
#                 print(f"Error converting datetime '{dt_val}': {e}")
#                 return None
        
#         # Apply UTC conversion
#         print("Converting integrate_date_time to UTC...")
#         df["integrate_date_time"] = df["integrate_date_time"].apply(to_utc)
        
#         print(f"Conversion results:")
#         print(f"Total rows: {len(df)}")
#         print(f"Successful conversions: {df['integrate_date_time'].notnull().sum()}")
#         print(f"Failed conversions: {df['integrate_date_time'].isnull().sum()}")
        
#         # Convert PCS to integer
#         df["pcs"] = pd.to_numeric(df["pcs"], errors='coerce')
#         df["pcs"] = df["pcs"].apply(lambda x: int(x) if pd.notna(x) else None)
        
#         # Clean string columns
#         string_columns = ['msg_id', 'awb_no', 'hawb_no', 'oc_no', 'boe_no']
#         for col in string_columns:
#             if col in df.columns:
#                 df[col] = df[col].astype(str).str.strip()
#                 df[col] = df[col].replace(['nan', 'None', 'NaT', '', 'N/A', 'NULL'], None)
        
#         # Replace pandas NaN/NaT with Python None
#         df = df.replace({np.nan: None, pd.NaT: None})
        
#         print("Final data sample:")
#         print(df.head())
        
#         return df
        
#     except Exception as e:
#         print(f"Error in clean_and_parse_oc_report: {e}")
#         raise



