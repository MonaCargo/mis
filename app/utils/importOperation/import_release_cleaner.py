# # app/utils/import_release_cleaner.py

# import pandas as pd
# import numpy as np
# from typing import Literal, Optional, Any
# from io import BytesIO
# from datetime import datetime
# import pytz
# import re


# # ============================================================================
# # COLUMN MAPPING
# # ============================================================================

# IMPORT_RELEASE_COLUMNS = {
#     'Date': 'date',
#     'Agent': 'agent',
#     'Consignee': 'consignee',
#     'Consignee Address': 'consignee_address',
#     'State': 'state',
#     'Consolidator': 'consolidator',
#     'AWB': 'awb',
#     'HWB': 'hwb',
#     'BOE NUM': 'boe_num',
#     'OC NUM': 'oc_num',
#     'Org': 'org',
#     'Pcs': 'pcs',
#     'Grg Wt': 'grg_wt',
#     'Chg Wt': 'chg_wt',
#     'NOG': 'nog',
#     'SHC': 'shc',
#     'Flight No': 'flight_no',
#     'Flight Date': 'flight_date',
#     'Segregation Date': 'segregation_date',
#     'Segregation Time': 'segregation_time',
#     'DO NUM': 'do_num',
#     'SDO NUM': 'sdo_num',
#     'Integration Mode': 'integration_mode',
#     'Cosys ID': 'cosys_id',
#     'Pick order recd. date/time': 'pick_order_recd_datetime',
#     'Pick order End date/Time': 'pick_order_end_datetime',
#     'Gate Pass No': 'gate_pass_no',
#     'Gate Pass issued Date': 'gate_pass_issued_date',
#     'Gate Pass issued time': 'gate_pass_issued_time',
#     'Gate Pass recd. Date/Time': 'gate_pass_recd_datetime',
#     'Gate Pass End Date/Time': 'gate_pass_end_datetime',
#     'Gate Pass Released By': 'gate_pass_released_by',
#     'Actual DLV Date & Time': 'actual_dlv_datetime',
#     'Truck Load Date & Time': 'truck_load_datetime',
#     'ATA': 'ata',
#     'Flight Complete Date/Time': 'flight_complete_datetime',
#     'DELIVERED TO': 'delivered_to',
#     'DLV ID TYP': 'dlv_id_typ',
#     'DLV ID  NO': 'dlv_id_no',
#     'CHA ID': 'cha_id',
#     'Manually BOE user': 'manually_boe_user',
#     'Manually BOE date/time': 'manually_boe_datetime',
#     'Manual BOE approval user': 'manual_boe_approval_user',
#     'Manual BOE approval date/time': 'manual_boe_approval_datetime',
#     'Manually OC user': 'manually_oc_user',
#     'Manually OC date/time': 'manually_oc_datetime',
#     'Manual OC approval user': 'manual_oc_approval_user',
#     'Manual OC approval date/time': 'manual_oc_approval_datetime',
#     'DLV Zone': 'dlv_zone',
#     'Mobile Number': 'mobile_number',
#     'Online/Counter': 'online_counter',
#     'LOCATION_PCS': 'location_pcs',
# }

# IMPORT_RELEASE_RULES = {
#     "awb": {"required": True},
# }

# DATETIME_COMBINATIONS = {
#     "segregation": {
#         "date_col": "segregation_date",
#         "time_col": "segregation_time",
#         "combined_col": "segregation_datetime"
#     },
#     "gate_pass_issued": {
#         "date_col": "gate_pass_issued_date",
#         "time_col": "gate_pass_issued_time",
#         "combined_col": "gate_pass_issued_datetime"
#     }
# }


# # ============================================================================
# # PARSING FUNCTIONS
# # ============================================================================

# def parse_excel_datetime(value: Any, row_index: int, col_name: str, mandatory: bool = False, timezone: str = "Asia/Kolkata") -> Optional[datetime]:
#     if pd.isna(value) or value in [None, "", "NA", "N/A"]:
#         if mandatory:
#             raise ValueError(f"Row {row_index}: Column '{col_name}' is mandatory but missing")
#         return None
    
#     local_tz = pytz.timezone(timezone)
    
#     if isinstance(value, datetime):
#         if value.tzinfo is None:
#             return local_tz.localize(value).astimezone(pytz.UTC)
#         return value.astimezone(pytz.UTC)
    
#     if isinstance(value, pd.Timestamp):
#         dt = value.to_pydatetime()
#         if dt.tzinfo is None:
#             return local_tz.localize(dt).astimezone(pytz.UTC)
#         return dt.astimezone(pytz.UTC)
    
#     if isinstance(value, str):
#         value = value.strip()
#         datetime_formats = [
#             "%d-%b-%Y %H:%M", "%m/%d/%Y %I:%M:%S %p", "%d/%m/%Y %I:%M:%S %p",
#             "%Y-%m-%d %H:%M:%S", "%m/%d/%Y %H:%M:%S", "%d/%m/%Y %H:%M:%S",
#             "%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d",
#         ]
#         for fmt in datetime_formats:
#             try:
#                 naive_dt = datetime.strptime(value, fmt)
#                 return local_tz.localize(naive_dt).astimezone(pytz.UTC)
#             except ValueError:
#                 continue
#         if mandatory:
#             raise ValueError(f"Row {row_index}: Column '{col_name}' has invalid datetime format '{value}'")
#         return None
    
#     if isinstance(value, (int, float, np.float64, np.int64)):
#         try:
#             naive_dt = pd.to_datetime(value, unit='D', origin='1899-12-30')
#             dt = naive_dt.to_pydatetime()
#             return local_tz.localize(dt).astimezone(pytz.UTC)
#         except Exception as e:
#             if mandatory:
#                 raise ValueError(f"Row {row_index}: Column '{col_name}' has invalid numeric date '{value}': {e}")
#             return None
    
#     if mandatory:
#         raise ValueError(f"Row {row_index}: Column '{col_name}' has unrecognized type {type(value)}")
#     return None


# def parse_excel_date(value: Any, row_index: int, col_name: str, mandatory: bool = False, timezone: str = "Asia/Kolkata") -> Optional[datetime]:
#     if pd.isna(value) or value in [None, "", "NA", "N/A"]:
#         if mandatory:
#             raise ValueError(f"Row {row_index}: Column '{col_name}' is mandatory but missing")
#         return None
    
#     local_tz = pytz.timezone(timezone)
    
#     if isinstance(value, datetime):
#         date_only = value.date()
#         naive_dt = datetime.combine(date_only, datetime.min.time())
#         return local_tz.localize(naive_dt).astimezone(pytz.UTC)
    
#     if isinstance(value, pd.Timestamp):
#         date_only = value.date()
#         naive_dt = datetime.combine(date_only, datetime.min.time())
#         return local_tz.localize(naive_dt).astimezone(pytz.UTC)
    
#     if isinstance(value, str):
#         value = value.strip()
#         date_formats = ["%m/%d/%Y", "%d/%m/%Y", "%Y-%m-%d", "%d-%b-%Y", "%d-%m-%Y", "%m-%d-%Y"]
#         for fmt in date_formats:
#             try:
#                 naive_dt = datetime.strptime(value, fmt)
#                 return local_tz.localize(naive_dt).astimezone(pytz.UTC)
#             except ValueError:
#                 continue
#         if mandatory:
#             raise ValueError(f"Row {row_index}: Column '{col_name}' has invalid date format '{value}'")
#         return None
    
#     if isinstance(value, (int, float, np.float64, np.int64)):
#         try:
#             naive_dt = pd.to_datetime(value, unit='D', origin='1899-12-30')
#             dt = naive_dt.to_pydatetime()
#             date_only = dt.date()
#             midnight_dt = datetime.combine(date_only, datetime.min.time())
#             return local_tz.localize(midnight_dt).astimezone(pytz.UTC)
#         except Exception as e:
#             if mandatory:
#                 raise ValueError(f"Row {row_index}: Column '{col_name}' has invalid numeric date '{value}': {e}")
#             return None
    
#     if mandatory:
#         raise ValueError(f"Row {row_index}: Column '{col_name}' has unrecognized type {type(value)}")
#     return None


# def parse_excel_time(value: Any, row_index: int, col_name: str, mandatory: bool = False) -> Optional[str]:
#     if pd.isna(value) or value in [None, "", "NA", "N/A"]:
#         if mandatory:
#             raise ValueError(f"Row {row_index}: Column '{col_name}' is mandatory but missing")
#         return None
    
#     if isinstance(value, str):
#         time_str = value.strip()
#         if re.match(r'^\d{1,2}:\d{2}:\d{2}\s*(AM|PM)$', time_str, re.IGNORECASE):
#             return time_str.upper()
#         if re.match(r'^\d{2}:\d{2}:\d{2}$', time_str):
#             return time_str
        
#         time_formats = ["%I:%M:%S %p", "%H:%M:%S", "%I:%M %p", "%H:%M"]
#         for fmt in time_formats:
#             try:
#                 time_obj = datetime.strptime(time_str, fmt).time()
#                 hour = time_obj.hour
#                 am_pm = "AM" if hour < 12 else "PM"
#                 display_hour = hour if hour <= 12 else hour - 12
#                 if display_hour == 0:
#                     display_hour = 12
#                 return f"{display_hour}:{time_obj.minute:02d}:{time_obj.second:02d} {am_pm}"
#             except ValueError:
#                 continue
#         if mandatory:
#             raise ValueError(f"Row {row_index}: Column '{col_name}' has invalid time format '{value}'")
#         return time_str
    
#     if isinstance(value, (int, float, np.float64, np.int64)):
#         try:
#             if 0 <= value < 1:
#                 total_seconds = int(value * 86400)
#                 hours = total_seconds // 3600
#                 minutes = (total_seconds % 3600) // 60
#                 seconds = total_seconds % 60
#                 am_pm = "AM" if hours < 12 else "PM"
#                 display_hour = hours if hours <= 12 else hours - 12
#                 if display_hour == 0:
#                     display_hour = 12
#                 return f"{display_hour}:{minutes:02d}:{seconds:02d} {am_pm}"
#             else:
#                 if mandatory:
#                     raise ValueError(f"Row {row_index}: Column '{col_name}' has invalid time value '{value}'")
#                 return None
#         except Exception as e:
#             if mandatory:
#                 raise ValueError(f"Row {row_index}: Column '{col_name}' time parsing error: {e}")
#             return None
    
#     if mandatory:
#         raise ValueError(f"Row {row_index}: Column '{col_name}' has unrecognized type {type(value)}")
#     return None


# def combine_date_time(date_value: Optional[datetime], time_value: Optional[str], timezone: str = "Asia/Kolkata") -> Optional[datetime]:
#     if date_value is None:
#         return None
#     if time_value is None or time_value.strip() == "":
#         return date_value
    
#     local_tz = pytz.timezone(timezone)
#     local_date = date_value.astimezone(local_tz).date()
    
#     time_formats = ["%I:%M:%S %p", "%H:%M:%S", "%I:%M %p", "%H:%M"]
#     time_obj = None
#     for fmt in time_formats:
#         try:
#             time_obj = datetime.strptime(time_value.strip(), fmt).time()
#             break
#         except ValueError:
#             continue
    
#     if time_obj is None:
#         return date_value
    
#     naive_dt = datetime.combine(local_date, time_obj)
#     localized_dt = local_tz.localize(naive_dt)
#     return localized_dt.astimezone(pytz.UTC)


# # ============================================================================
# # MAIN CLEANING FUNCTION
# # ============================================================================

# def clean_import_release_file(
#     file: BytesIO,
#     file_type: Literal["csv", "excel"],
#     header_row: int = 0,
#     remove_last_row: bool = False,
#     timezone: str = "Asia/Kolkata"
# ) -> pd.DataFrame:
#     """Clean and prepare Import Release file for database insertion."""
    
#     # Read file
#     if file_type == "csv":
#         df = pd.read_csv(file, header=header_row, dtype={'AWB': str, 'HWB': str, 'BOE NUM': str, 'OC NUM': str, 'Gate Pass No': str, 'Mobile Number': str})
#     elif file_type == "excel":
#         df = pd.read_excel(file, header=header_row, dtype={'AWB': str, 'HWB': str, 'BOE NUM': str, 'OC NUM': str, 'Gate Pass No': str, 'Mobile Number': str})
#     else:
#         raise ValueError("Unsupported file type: only 'csv' or 'excel' supported")
    
#     if remove_last_row and len(df) > 0:
#         df = df.iloc[:-1]
    
#     # Validate columns
#     available_columns = [col for col in IMPORT_RELEASE_COLUMNS.keys() if col in df.columns]
#     for excel_col, db_col in IMPORT_RELEASE_COLUMNS.items():
#         if IMPORT_RELEASE_RULES.get(db_col, {}).get("required", False):
#             if excel_col not in df.columns:
#                 raise ValueError(f"Missing required column: {excel_col}")
    
#     # Rename columns
#     df_clean = df[available_columns].rename(columns=IMPORT_RELEASE_COLUMNS)
    
#     # Validate mandatory fields per row
#     for idx, row in df_clean.iterrows():
#         for col, rules in IMPORT_RELEASE_RULES.items():
#             if rules.get("required") and col in df_clean.columns:
#                 if pd.isna(row[col]) or row[col] in [None, ""]:
#                     raise ValueError(f"Row {idx + header_row + 2}: Column '{col}' is mandatory but missing")
    
#     # Clean AWB (trim only)
#     if 'awb' in df_clean.columns:
#         df_clean['awb'] = df_clean['awb'].astype(str).str.strip()
#         df_clean['awb'] = df_clean['awb'].replace(['nan', 'NaN', 'None', 'NA', 'N/A', ''], None)
    
#     # Clean mobile number (trim only)
#     if 'mobile_number' in df_clean.columns:
#         df_clean['mobile_number'] = df_clean['mobile_number'].astype(str).str.strip()
#         df_clean['mobile_number'] = df_clean['mobile_number'].replace(['nan', 'NaN', 'None', 'NA', 'N/A', ''], None)
    
#     # Numeric fields
#     if 'pcs' in df_clean.columns:
#         df_clean['pcs'] = pd.to_numeric(df_clean['pcs'], errors='coerce').fillna(0).astype('int64')
#     if 'grg_wt' in df_clean.columns:
#         df_clean['grg_wt'] = pd.to_numeric(df_clean['grg_wt'], errors='coerce')
#     if 'chg_wt' in df_clean.columns:
#         df_clean['chg_wt'] = pd.to_numeric(df_clean['chg_wt'], errors='coerce')
    
#     # Date fields
#     date_fields = ['segregation_date', 'gate_pass_issued_date', 'flight_date']
#     for col in date_fields:
#         if col in df_clean.columns:
#             parsed_values = []
#             for idx, val in enumerate(df_clean[col], start=header_row + 2):
#                 dt = parse_excel_date(val, idx, col, mandatory=False, timezone=timezone)
#                 parsed_values.append(dt)
#             df_clean[col] = pd.Series(parsed_values, index=df_clean.index)
    
#     # Time fields
#     time_fields = ['segregation_time', 'gate_pass_issued_time']
#     for col in time_fields:
#         if col in df_clean.columns:
#             parsed_values = []
#             for idx, val in enumerate(df_clean[col], start=header_row + 2):
#                 time_str = parse_excel_time(val, idx, col, mandatory=False)
#                 parsed_values.append(time_str)
#             df_clean[col] = pd.Series(parsed_values, index=df_clean.index)
    
#     # DateTime fields
#     datetime_fields = ['date', 'pick_order_recd_datetime', 'pick_order_end_datetime', 'gate_pass_recd_datetime', 
#                        'gate_pass_end_datetime', 'actual_dlv_datetime', 'truck_load_datetime', 'ata',
#                        'flight_complete_datetime', 'manually_boe_datetime', 'manual_boe_approval_datetime',
#                        'manually_oc_datetime', 'manual_oc_approval_datetime']
#     for col in datetime_fields:
#         if col in df_clean.columns:
#             parsed_values = []
#             for idx, val in enumerate(df_clean[col], start=header_row + 2):
#                 dt = parse_excel_datetime(val, idx, col, mandatory=False, timezone=timezone)
#                 parsed_values.append(dt)
#             df_clean[col] = pd.Series(parsed_values, index=df_clean.index)
    
#     # Combine date + time fields
#     for combo_name, config in DATETIME_COMBINATIONS.items():
#         date_col = config["date_col"]
#         time_col = config["time_col"]
#         combined_col = config["combined_col"]
#         if date_col in df_clean.columns and time_col in df_clean.columns:
#             combined_values = []
#             for idx, row in df_clean.iterrows():
#                 date_val = row.get(date_col)
#                 time_val = row.get(time_col)
#                 combined_dt = combine_date_time(date_val, time_val, timezone=timezone)
#                 combined_values.append(combined_dt)
#             df_clean[combined_col] = pd.Series(combined_values, index=df_clean.index)
    
#     # Replace NaN/NaT with None
#     df_clean = df_clean.replace({np.nan: None, pd.NaT: None})
    
#     return df_clean
























import os
import re
import pandas as pd
import numpy as np
from datetime import datetime,date, time,timedelta,timezone
import pytz




# NORMALIZE THE AWB no AND CAP IT TO 11 CHAR (iF MORE THAN THAT AND NOT COME IN MY TRIPPING VALIDATION THEN GET none ) 
def normalize_awb_no(value) -> str:
    if not value:
        return None
    # Safe conversion to string of awb
    value = str(value)

    # Remove all non-digit characters
    cleaned = re.sub(r'\D', '', value)

    # Ensure it's 11 digits
    if len(cleaned) == 11:
        return cleaned
    elif len(cleaned) == 10:
        return '0' + cleaned
    else:
        return None  # Invalid AWB format



def clean_import_release_file(file, file_type: str) -> pd.DataFrame:
    """
    Cleans IRR file (CSV or Excel), renames columns, trims rows, and converts all date/time fields to UTC.
    
    Parameters:
        file: Uploaded file object
        file_type: 'csv' or 'excel'
    
    Returns:
        Cleaned pandas DataFrame with UTC timestamps
    """
 
        # Read file based on type
    if file_type == "excel":
        df = pd.read_excel(file, header=9)
    elif file_type == "csv":
        df = pd.read_csv(file,header=7)  # for .CSV file
        
    elif file_type == "CSV":
        df = pd.read_csv(file,header=7)  # for .CSV file
    else:
        raise ValueError("Unsupported file type. Use 'csv' or 'excel'.")
    
    # Forward-fill 'Date' column
    # print("Cleaning date start", df.head(20))

    df['Date'] = df['Date'].ffill()


    # print("Cleaning date stop", df.head())

    
    # Drop last 3 rows and first column
    df = df.iloc[:-3, 1:]
    
    # Drop rows where all columns (except first two) are NaN
    df = df.dropna(how='all', subset=df.columns[2:])
    
    # Column renaming map
    column_mapping = {
        'Date': 'date',
        'Agent ': 'agent',
        'Consignee': 'consignee',
        'Consignee Address': 'consignee_address',
        'State': 'state',
        'Consolidator': 'consolidator',
        'AWB': 'awb',
        'HWB': 'hwb',
        'BOE NUM': 'boe_num',
        'OC NUM': 'oc_num',
        'Org': 'org',
        'Pcs': 'pcs',
        'Grg Wt': 'grg_wt',
        'Chg Wt': 'chg_wt',
        'NOG': 'nog',
        'SHC': 'shc',
        'Flight No': 'flight_no',
        'Flight Date': 'flight_date',
        'Segregation Date': 'segregation_date',
        'Segregation Time': 'segregation_time',
        'DO NUM': 'do_num',
        'SDO NUM': 'sdo_num',
        'Integration Mode': 'integration_mode',
        'Cosys ID': 'cosys_id',
        'Pick order recd. date/time': 'pick_order_recd_date_time',
        'Pick order End date/Time': 'pick_order_end_date_time',
        'Gate Pass No': 'gate_pass_no',
        'Gate Pass issued Date': 'gate_pass_issued_date',
        'Gate Pass issued time': 'gate_pass_issued_time',
        'Gate Pass recd. Date/Time': 'gate_pass_recd_date_time',
        'Gate Pass End Date/Time': 'gate_pass_end_date_time',
        'Gate Pass Released By': 'gate_pass_released_by',
        'Actual DLV Date & Time': 'actual_dlv_date_time',
        'Truck Load Date & Time': 'truck_load_date_time',
        'ATA': 'ata',
        'Flight Complete Date/Time': 'flight_complete_date_time',
        'DELIVERED TO': 'delivered_to',
        'DLV ID TYP ': 'dlv_id_typ',
        'DLV ID  NO ': 'dlv_id_no',
        'CHA ID': 'cha_id',
        'Manually BOE user': 'manually_boe_user',
        'Manually BOE date/time': 'manually_boe_date_time',
        'Manual BOE approval user': 'manual_boe_approval_user',
        'Manual BOE approval date/time': 'manual_boe_approval_date_time',
        'Manually OC user': 'manually_oc_user',
        'Manually OC date/time': 'manually_oc_date_time',
        'Manual OC approval user': 'manual_oc_approval_user',
        'Manual OC approval date/time': 'manual_oc_approval_date_time',
        'DLV Zone': 'dlv_zone',
        'Mobile Number': 'mobile_number',
        'Online/Counter': 'online_counter',
        'LOCATION_PCS': 'location_pcs'
    }
    
    # Select and rename columns
    df = df[list(column_mapping.keys())].rename(columns=column_mapping)

    # ✅ Normalize AWB number
    if 'awb' in df.columns:
        df['awb'] = df['awb'].apply(normalize_awb_no)

        # print(df.head(10))
    
    # Define date/time columns that need UTC conversion
    datetime_columns = [
        'date',
        'flight_date',
        'segregation_date',
        'pick_order_recd_date_time',
        'pick_order_end_date_time',
        'gate_pass_issued_date',
        'gate_pass_recd_date_time',
        'gate_pass_end_date_time',
        'actual_dlv_date_time',
        'truck_load_date_time',
        'ata',
        'flight_complete_date_time',
        'manually_boe_date_time',
        'manual_boe_approval_date_time',
        'manually_oc_date_time',
        'manual_oc_approval_date_time'
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
    
    # Apply UTC conversion to all datetime columns
    for col in datetime_columns:
        if col in df.columns:
            df[col] = df[col].apply(to_utc)
    
    # Handle time-only field (segregation_time, gate_pass_issued_time)
    # These might need special handling if they're just HH:MM:SS without date
    time_only_columns = ['segregation_time', 'gate_pass_issued_time']
    
    for col in time_only_columns:
        if col in df.columns:
            # Clean string values - remove extra spaces and convert empty to None
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace(['nan', 'None', 'NaT', '', 'N/A'], None)
    
    # Convert numeric columns
    numeric_columns = ['pcs', 'grg_wt', 'chg_wt']
    for col in numeric_columns:
        if col in df.columns:
            df[col] = pd.to_numeric(df[col], errors='coerce')
            df[col] = df[col].apply(lambda x: int(x) if pd.notna(x) and col == 'pcs' else x)
    
    # Clean string columns - remove extra spaces and convert empty to None
    string_columns = [
        'agent', 'consignee', 'consignee_address', 'state', 'consolidator',
        'awb', 'hwb', 'boe_num', 'oc_num', 'org', 'nog', 'shc', 'flight_no',
        'do_num', 'sdo_num', 'integration_mode', 'cosys_id', 'gate_pass_no',
        'gate_pass_released_by', 'delivered_to', 'dlv_id_typ', 'dlv_id_no',
        'cha_id', 'manually_boe_user', 'manual_boe_approval_user',
        'manually_oc_user', 'manual_oc_approval_user', 'dlv_zone',
        'mobile_number', 'online_counter', 'location_pcs'
    ]
    
    for col in string_columns:
        if col in df.columns:
            df[col] = df[col].astype(str).str.strip()
            df[col] = df[col].replace(['nan', 'None', 'NaT', '', 'N/A'], None)
    
    # Replace pandas NaN/NaT with Python None for database compatibility
    df = df.replace({np.nan: None, pd.NaT: None})
    
    return df











