

import re
import pandas as pd
import numpy as np
from typing import Literal, Dict, Any, List
from io import BytesIO
from datetime import datetime
import pytz

# Mapping Excel columns to database columns
REQUIRED_COLUMNS = {
    'AWB NO': 'awb_no',
    'HWB NO': 'hwb_no', 
    'M/H': 'm_h',
    'ORIGIN': 'origin',
    'DESTINATION': 'destination',
    'WAREHOUSE LOCATION': 'warehouse_location',
    'STATUS': 'status',
    'LOCATION DATE': 'location_date',
    'PCS': 'pcs',
    'WGT_CHG': 'wgt_chg',
    'GRS_WGT': 'grs_wgt',
    'NATURE OF GOODS': 'nature_of_goods',
    'SHC': 'shc',
    'AGENT': 'agent',
    'FLTNO': 'fltno',
    'FLT DATE': 'flt_date',
    'CNE NAM': 'cne_name',
    'CNE ADDR': 'cne_addr'
}



# -------

import re
import pandas as pd

# def normalize_hwb_no(value) -> str:
#     """
#     Normalize HWB number by removing trailing single letters (like P, M, etc.)
#     Examples:
#         'HCN1684061 P' -> 'HCN1684061'
#         'HCN1684061P' -> 'HCN1684061'
#         'HCN1684061' -> 'HCN1684061'
#     """
#     if not value or pd.isna(value):
#         return None

#     # Convert to string and strip whitespace
#     value = str(value).strip()

#     # Remove trailing single letter (with or without space before it)
#     cleaned = re.sub(r'\s?[A-Za-z]$', '', value)
#     return cleaned if cleaned else None

def normalize_hwb_no(value) -> str:
    """
    Normalize HWB number by removing any trailing characters
    that come after a space at the end.
    
    Examples:
        'HCN1684061 P' -> 'HCN1684061'
        'HCN1684061 123' -> 'HCN1684061'
        'HCN1684061P' -> 'HCN1684061P'  # keep
        'HCN1684061' -> 'HCN1684061'
    """
    if not value or pd.isna(value):
        return None

    # Convert to string and strip whitespace
    value = str(value).strip()

    # Remove anything after a space at the end
    cleaned = re.sub(r'\s.+$', '', value)

    return cleaned if cleaned else None

# Test
X = normalize_hwb_no('NUE1063925 P')
print(X)  # Output: 'NUE1063925'


# --------

from pandas import Timestamp

def convert_to_utc(dt):
    if isinstance(dt, Timestamp):
        if dt.tzinfo is None:
            return dt.tz_localize("Asia/Kolkata").astimezone(pytz.UTC)
        return dt.astimezone(pytz.UTC)

    if isinstance(dt, datetime):
        if dt.tzinfo is None:
            return pytz.timezone("Asia/Kolkata").localize(dt).astimezone(pytz.UTC)
        return dt.astimezone(pytz.UTC)

    return None  # if invalid or empty



def normalize_awb_no(value) -> str:
    if not value:
        return None
    # Safe conversion to string of awb
    value = str(value)
    # Remove all non-digit characters
    cleaned = re.sub(r'\D', '', value)

    # Handle length correction
    if len(cleaned) == 11:
        return cleaned
    elif len(cleaned) == 10:
        return '0' + cleaned
    else:
        return None  # Invalid AWB format


def clean_airway_bill_file_advanced(file: BytesIO, file_type: Literal["csv", "excel"]) -> List[Dict[str, Any]]:
    """
    Advanced version with more control over reading the file
    """
    # Read the entire file first to inspect
    if file_type == "csv":
        df_full = pd.read_csv(file, header=None, dtype=str)
    elif file_type == "excel":
        df_full = pd.read_excel(file, header=None, dtype=str)
    
    # Find the header row (row 7, which is index 6 in 0-indexed)
    header_row_index = 6
    
    # Read file again with proper header
    if file_type == "csv":
        df = pd.read_csv(file, skiprows=header_row_index, header=0, dtype=str)
    elif file_type == "excel":
        df = pd.read_excel(file, skiprows=header_row_index, header=0, dtype=str)
    
    # Remove empty rows
    df = df.dropna(how='all')
    
    # Remove last row
    if len(df) > 0:
        df = df.iloc[:-1]
    
    # Clean column names (remove extra spaces, newlines)
    df.columns = df.columns.str.strip()
    
    # Validate required columns
    missing = [col for col in REQUIRED_COLUMNS.keys() if col not in df.columns]
    if missing:
        raise ValueError(f"Missing columns: {missing}")
    
    # Select and rename columns
    df_clean = df[list(REQUIRED_COLUMNS.keys())].rename(columns=REQUIRED_COLUMNS)

    # ✅ Normalize AWB number RIGHT HERE
    if 'awb_no' in df_clean.columns:
        df_clean['awb_no'] = df_clean['awb_no'].apply(normalize_awb_no)
        
    # ✅ Normalize HWB number
    if 'hwb_no' in df_clean.columns:
        df_clean['hwb_no'] = df_clean['hwb_no'].apply(normalize_hwb_no)
    
    
    # Check mandatory AWB NO
    for idx, row in df_clean.iterrows():
        actual_row_num = idx + header_row_index + 2  # +2 because header row is +1 and we want actual Excel row
        if pd.isna(row['awb_no']) or row['awb_no'] in [None, "", "nan", "None"]:
            raise ValueError(f"Row {actual_row_num}: AWB NO is mandatory but missing")
    
    # Parse datetime columns
    # for col in ["location_date", "flt_date"]:
    #     if col in df_clean.columns:
    #         df_clean[col] = pd.to_datetime(df_clean[col], errors='coerce')
    

    # ✅ Parse and localize timezone for datetime fields
    for col in ["location_date", "flt_date"]:
        if col in df_clean.columns:
            df_clean[col] = pd.to_datetime(df_clean[col], errors='coerce')
            df_clean[col] = df_clean[col].apply(convert_to_utc)

    # Convert string columnsS
    string_columns = ['awb_no', 'hwb_no', 'm_h', 'origin', 'destination', 'warehouse_location', 
                     'status', 'nature_of_goods', 'shc', 'agent', 'fltno', 'cne_name', 'cne_addr']
    
    for col in string_columns:
        if col in df_clean.columns:
            df_clean[col] = df_clean[col].astype(str).str.strip()
            df_clean[col] = df_clean[col].replace(['nan', 'None', 'NaT', '<NA>'], None)
            # Convert empty strings to None
            df_clean[col] = df_clean[col].replace('', None)
    
    # Convert numeric columns
    if 'pcs' in df_clean.columns:
        df_clean['pcs'] = pd.to_numeric(df_clean['pcs'], errors='coerce').fillna(0).astype('int64')
    if 'wgt_chg' in df_clean.columns:
        df_clean['wgt_chg'] = pd.to_numeric(df_clean['wgt_chg'], errors='coerce')
    if 'grs_wgt' in df_clean.columns:
        df_clean['grs_wgt'] = pd.to_numeric(df_clean['grs_wgt'], errors='coerce')
    
    # Replace NaN/NaT with None
    df_clean = df_clean.replace({np.nan: None, pd.NaT: None})
    
    # Convert to list of dictionaries
    records = df_clean.to_dict('records')
    
    return records