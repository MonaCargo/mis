
# ============= 4TH FINAL VERSION ===================================


import pandas as pd
import numpy as np
from typing import Literal
from io import BytesIO
from datetime import datetime
import pytz


# Mapping Excel columns to internal names
REQUIRED_COLUMNS = {
    'Organisation Name': 'company_name',
    'Warehouse': 'warehouse',
    'Zone': 'zone',
    'Slot No': 'token_no',
     'AWB No.': 'awb_id',
    'Truck No': 'truck_number',
    'Pkgs.': 'pcs',
    'Status': 'status',
    'Remarks': 'remarks',
    'Type': 'cargo_type',
    'Rescheduled': 'rescheduled',
    'Rescheduled By': 'rescheduled_by',
    'Slot For': 'truck_slot_from',
    'Arrived At': 'truck_in_date_time',
}

# Define which fields are mandatory
COLUMN_RULES = {
    "company_name": {"required": True},
    "warehouse": {"required": True},
    "zone": {"required": True},
    "token_no": {"required": True},
    "truck_number": {"required": True},
    "truck_slot_from": {"required": True},  # key field
    "status": {"required": False},
    "remarks": {"required": False},
    "cargo_type": {"required": False},
    "rescheduled": {"required": False},
    "rescheduled_by": {"required": False},
    "truck_in_date_time": {"required": False},
    "awb_id": {"required": True},  # ✅ CHANGED from awbid to awb_id
    "pcs": {"required": False},
}


def parse_excel_datetime(value, row_index, col_name, mandatory=False):
    """
    Parse Excel datetime safely.
    Returns datetime or None if optional.
    Raises ValueError if mandatory and invalid.
    """
    if pd.isna(value):
        if mandatory:
            raise ValueError(f"Row {row_index}: Column '{col_name}' is mandatory but missing")
        return None

    if isinstance(value, datetime):
        return value

    if isinstance(value, str):
        try:
            return datetime.strptime(value.strip(), "%d-%b-%Y %H:%M")
        except ValueError:
            if mandatory:
                raise ValueError(f"Row {row_index}: Column '{col_name}' has invalid string '{value}' "
                                 f"(expected DD-MMM-YYYY HH:MM)")
            return None

    if isinstance(value, (int, float, np.float64, np.int64)):
        try:
            # Excel numeric date → datetime
            return pd.to_datetime(value, unit='d', origin='1899-12-30')
        except Exception:
            if mandatory:
                raise ValueError(f"Row {row_index}: Column '{col_name}' has invalid numeric date '{value}'")
            return None

    if mandatory:
        raise ValueError(f"Row {row_index}: Column '{col_name}' has unrecognized type {type(value)} with value '{value}'")
    return None




# changes bu pAM
def clean_file(file: BytesIO, file_type: Literal["csv", "excel"], remove_last_row: bool = True) -> pd.DataFrame:
    """
    Clean and prepare Excel/CSV file for DB insertion.
    """
    # --- Read file ---
    if file_type == "csv":
        df = pd.read_csv(file, header=1, dtype={'AWB No.': str})  # ⬅️ ADD dtype parameter
    elif file_type == "excel":
        df = pd.read_excel(file, header=1, dtype={'AWB No.': str})  # ⬅️ ADD dtype parameter
    else:
        raise ValueError("Unsupported file type: only support csv or excel")
    
    if remove_last_row:
        df = df.iloc[:-1]
    
    # --- Validate required columns exist ---
    missing = [col for col in REQUIRED_COLUMNS.keys() if col not in df.columns]
    if missing:
        raise ValueError(f"Invalid file format. Missing columns: {missing}")
    
    # --- Select and rename columns ---
    df_clean = df[list(REQUIRED_COLUMNS.keys())].rename(columns=REQUIRED_COLUMNS)
    
    # --- Check mandatory columns per row ---
    for idx, row in df_clean.iterrows():
        for col, rules in COLUMN_RULES.items():
            if rules.get("required") and (pd.isna(row[col]) or row[col] in [None, ""]):
                raise ValueError(f"Row {idx+2}: Column '{col}' is mandatory but missing")
    
    # --- Timezone setup ---
    local_tz = pytz.timezone("Asia/Kolkata")
    
    # --- Parse datetime columns and localize ---
    for col in ["truck_slot_from", "truck_in_date_time"]:
        if col in df_clean.columns:
            parsed_values = []
            mandatory = COLUMN_RULES.get(col, {}).get("required", False)
            for idx, val in enumerate(df_clean[col], start=2):
                dt = parse_excel_datetime(val, idx, col, mandatory=mandatory)
                # Localize tz-naive datetime and convert to UTC
                if dt is not None and dt.tzinfo is None:
                    dt = local_tz.localize(dt).astimezone(pytz.UTC)
                parsed_values.append(dt)
            df_clean[col] = pd.Series(parsed_values, index=df_clean.index)
    
    # --- ✅ Convert AWB to string (FIXES THE ERROR) ---
    if 'awb_id' in df_clean.columns:
          df_clean['awb_id'] = df_clean['awb_id'].astype(str).str.strip()
          df_clean['awb_id'] = df_clean['awb_id'].replace('nan', None)
    
    # --- Numeric columns ---
    if 'pcs' in df_clean.columns:
        df_clean['pcs'] = pd.to_numeric(df_clean['pcs'], errors='coerce').fillna(0).astype('int64')
    
    # --- Replace NaN / NaT with None ---
    df_clean = df_clean.replace({np.nan: None, pd.NaT: None})
    
    # df_clean.to_csv("cleaned_output.csv", index=False)  # For debugging
    
    return df_clean






