

# import os
# import re
# import pandas as pd
# import numpy as np
# from datetime import datetime,date, time,timedelta,timezone
# import pytz

# # NORMALIZE THE GATE PASS NO (remove .0, non-digits)
# def normalize_gate_pass_no(value) -> str:
#     if not value:
#         return None

#     value = str(value).strip()

#     # Remove decimals like 25240231.0
#     if value.endswith(".0"):
#         value = value[:-2]

#     # Remove all non-digit characters
#     cleaned = re.sub(r"\D", "", value)

#     return cleaned if cleaned else None




# # NORMALIZE THE AWB no AND CAP IT TO 11 CHAR (iF MORE THAN THAT AND NOT COME IN MY TRIPPING VALIDATION THEN GET none ) 
# def normalize_awb_no(value) -> str:
#     if not value:
#         return None
#     # Safe conversion to string of awb
#     value = str(value)

#     # Remove all non-digit characters
#     cleaned = re.sub(r'\D', '', value)

#     # Ensure it's 11 digits
#     if len(cleaned) == 11:
#         return cleaned
#     elif len(cleaned) == 10:
#         return '0' + cleaned
#     else:
#         return None  # Invalid AWB format



# def clean_import_release_file(file, file_type: str) -> pd.DataFrame:
#     """
#     Cleans IRR file (CSV or Excel), renames columns, trims rows, and converts all date/time fields to UTC.
    
#     Parameters:
#         file: Uploaded file object
#         file_type: 'csv' or 'excel'
    
#     Returns:
#         Cleaned pandas DataFrame with UTC timestamps
#     """
 
#         # Read file based on type
#     if file_type == "excel":
#         df = pd.read_excel(file, header=9)
#     elif file_type == "csv":
#         df = pd.read_csv(file,header=7)  # for .CSV file
        
#     elif file_type == "CSV":
#         df = pd.read_csv(file,header=7)  # for .CSV file
#     else:
#         raise ValueError("Unsupported file type. Use 'csv' or 'excel'.")
    
#     # Forward-fill 'Date' column
#     # print("Cleaning date start", df.head(20))

#     df['Date'] = df['Date'].ffill()


#     # print("Cleaning date stop", df.head())

    
#     # Drop last 3 rows and first column
#     df = df.iloc[:-3, 1:]
    
#     # Drop rows where all columns (except first two) are NaN
#     df = df.dropna(how='all', subset=df.columns[2:])
    
#     # Column renaming map
#     column_mapping = {
#         'Date': 'date',
#         'Agent ': 'agent',
#         'Consignee': 'consignee',
#         'Consignee Address': 'consignee_address',
#         'State': 'state',
#         'Consolidator': 'consolidator',
#         'AWB': 'awb',
#         'HWB': 'hwb',
#         'BOE NUM': 'boe_num',
#         'OC NUM': 'oc_num',
#         'Org': 'org',
#         'Pcs': 'pcs',
#         'Grg Wt': 'grg_wt',
#         'Chg Wt': 'chg_wt',
#         'NOG': 'nog',
#         'SHC': 'shc',
#         'Flight No': 'flight_no',
#         'Flight Date': 'flight_date',
#         'Segregation Date': 'segregation_date',
#         'Segregation Time': 'segregation_time',
#         'DO NUM': 'do_num',
#         'SDO NUM': 'sdo_num',
#         'Integration Mode': 'integration_mode',
#         'Cosys ID': 'cosys_id',
#         'Pick order recd. date/time': 'pick_order_recd_date_time',
#         'Pick order End date/Time': 'pick_order_end_date_time',
#         'Gate Pass No': 'gate_pass_no',
#         'Gate Pass issued Date': 'gate_pass_issued_date',
#         'Gate Pass issued time': 'gate_pass_issued_time',
#         'Gate Pass recd. Date/Time': 'gate_pass_recd_date_time',
#         'Gate Pass End Date/Time': 'gate_pass_end_date_time',
#         'Gate Pass Released By': 'gate_pass_released_by',
#         'Actual DLV Date & Time': 'actual_dlv_date_time',
#         'Truck Load Date & Time': 'truck_load_date_time',
#         'ATA': 'ata',
#         'Flight Complete Date/Time': 'flight_complete_date_time',
#         'DELIVERED TO': 'delivered_to',
#         'DLV ID TYP ': 'dlv_id_typ',
#         'DLV ID  NO ': 'dlv_id_no',
#         'CHA ID': 'cha_id',
#         'Manually BOE user': 'manually_boe_user',
#         'Manually BOE date/time': 'manually_boe_date_time',
#         'Manual BOE approval user': 'manual_boe_approval_user',
#         'Manual BOE approval date/time': 'manual_boe_approval_date_time',
#         'Manually OC user': 'manually_oc_user',
#         'Manually OC date/time': 'manually_oc_date_time',
#         'Manual OC approval user': 'manual_oc_approval_user',
#         'Manual OC approval date/time': 'manual_oc_approval_date_time',
#         'DLV Zone': 'dlv_zone',
#         'Mobile Number': 'mobile_number',
#         'Online/Counter': 'online_counter',
#         'LOCATION_PCS': 'location_pcs'
#     }
    
#     # Select and rename columns
#     df = df[list(column_mapping.keys())].rename(columns=column_mapping)

#      # ===========================New Addon 06/12/25  👌========================================

#     # ============================================
#     # 🔥 OC_NUM Cleaning + Duplicate Detection
#     # ============================================
#     if 'oc_num' in df.columns:

#         print("\n📌 Checking OC_NUM duplicates before cleaning...")

#         # Convert to string + strip spaces
#         df['oc_num'] = df['oc_num'].astype(str).str.strip()

#         # Remove blanks + non-numeric OC_NUM
#         before_clean = len(df)
#         df = df[df['oc_num'].str.match(r'^\d+$', na=False)]
#         after_clean = len(df)
#         print(f"🧹 Removed {before_clean - after_clean} invalid OC_NUM rows (blank or non-numeric)")

#         # Show duplicates BEFORE dropping
#         dupes = df[df.duplicated(subset=['oc_num'], keep=False)].sort_values('oc_num')

#         if not dupes.empty:
#             print("\n⚠️ Duplicate OC_NUM values before dedupe:")
#             print(dupes[['oc_num']].value_counts().rename("count"))
#         else:
#             print("✅ No duplicates found before dedupe")

#         # Drop duplicates — keep the LAST row
#         before_dedup = len(df)
#         df = df.drop_duplicates(subset=['oc_num'], keep='last')
#         after_dedup = len(df)

#         print(f"🔥 Removed {before_dedup - after_dedup} duplicate OC_NUM rows")
#         print("✅ OC_NUM cleaning completed successfully.\n")

#     # ===============================================================================================


#     # ✅ Normalize AWB number
#     if 'awb' in df.columns:
#         df['awb'] = df['awb'].apply(normalize_awb_no)

#         # print(df.head(10))
    
#     # Define date/time columns that need UTC conversion
#     datetime_columns = [
#         'date',
#         'flight_date',
#         'segregation_date',
#         'pick_order_recd_date_time',
#         'pick_order_end_date_time',
#         'gate_pass_issued_date',
#         'gate_pass_recd_date_time',
#         'gate_pass_end_date_time',
#         'actual_dlv_date_time',
#         'truck_load_date_time',
#         'ata',
#         'flight_complete_date_time',
#         'manually_boe_date_time',
#         'manual_boe_approval_date_time',
#         'manually_oc_date_time',
#         'manual_oc_approval_date_time'
#     ]
    
#     # UTC conversion function with multiple format support
#     def to_utc(dt_str):
#         try:
#             # Handle NaN, None, empty strings
#             if pd.isna(dt_str) or str(dt_str).strip() in ['', 'nan', 'None', 'NaT']:
#                 return None
            
#             dt_str = str(dt_str).strip()
            
#             # Try multiple datetime formats
#             formats = [
#                 "%Y-%m-%d %H:%M:%S",      # 2025-01-25 14:30:45
#                 "%d-%m-%Y %H:%M:%S",      # 25-01-2025 14:30:45
#                 "%d/%m/%Y %H:%M:%S",      # 25/01/2025 14:30:45
#                 "%Y-%m-%d",               # 2025-01-25 (date only)
#                 "%d-%m-%Y",               # 25-01-2025 (date only)
#                 "%d/%m/%Y",               # 25/01/2025 (date only)
#                 "%d-%b-%Y %H:%M:%S",      # 25-Jan-2025 14:30:45
#                 "%d-%b-%Y",               # 25-Jan-2025 (date only)
#             ]
            
#             local_dt = None
#             for fmt in formats:
#                 try:
#                     local_dt = datetime.strptime(dt_str, fmt)
#                     break
#                 except ValueError:
#                     continue
            
#             if local_dt is None:
#                 print(f"Warning: Could not parse datetime '{dt_str}'")
#                 return None
            
#             # Localize to Asia/Kolkata timezone
#             local_dt = pytz.timezone("Asia/Kolkata").localize(local_dt)
            
#             # Convert to UTC (timezone-aware)
#             utc_dt = local_dt.astimezone(pytz.utc)
            
#             return utc_dt
            
#         except Exception as e:
#             print(f"Error converting datetime '{dt_str}': {e}")
#             return None
    
#     # Apply UTC conversion to all datetime columns
#     for col in datetime_columns:
#         if col in df.columns:
#             df[col] = df[col].apply(to_utc)
    
#     # Handle time-only field (segregation_time, gate_pass_issued_time)
#     # These might need special handling if they're just HH:MM:SS without date
#     time_only_columns = ['segregation_time', 'gate_pass_issued_time']
    
#     for col in time_only_columns:
#         if col in df.columns:
#             # Clean string values - remove extra spaces and convert empty to None
#             df[col] = df[col].astype(str).str.strip()
#             df[col] = df[col].replace(['nan', 'None', 'NaT', '', 'N/A'], None)
    
#     # Convert numeric columns
#     numeric_columns = ['pcs', 'grg_wt', 'chg_wt']
#     for col in numeric_columns:
#         if col in df.columns:
#             df[col] = pd.to_numeric(df[col], errors='coerce')
#             df[col] = df[col].apply(lambda x: int(x) if pd.notna(x) and col == 'pcs' else x)
    
#     # Clean string columns - remove extra spaces and convert empty to None
#     string_columns = [
#         'agent', 'consignee', 'consignee_address', 'state', 'consolidator',
#         'awb', 'hwb', 'boe_num', 'oc_num', 'org', 'nog', 'shc', 'flight_no',
#         'do_num', 'sdo_num', 'integration_mode', 'cosys_id', 'gate_pass_no',
#         'gate_pass_released_by', 'delivered_to', 'dlv_id_typ', 'dlv_id_no',
#         'cha_id', 'manually_boe_user', 'manual_boe_approval_user',
#         'manually_oc_user', 'manual_oc_approval_user', 'dlv_zone',
#         'mobile_number', 'online_counter', 'location_pcs'
#     ]
    
#     for col in string_columns:
#         if col in df.columns:
#             df[col] = df[col].astype(str).str.strip()
#             df[col] = df[col].replace(['nan', 'None', 'NaT', '', 'N/A'], None)
#      # Normalize gate_pass_no values
#     if 'gate_pass_no' in df.columns:
#         df['gate_pass_no'] = df['gate_pass_no'].apply(normalize_gate_pass_no)
#     # Replace pandas NaN/NaT with Python None for database compatibility
#     df = df.replace({np.nan: None, pd.NaT: None})
    
#     print(df['gate_pass_no'].head(6))


#     return df






# ================ new two level structure ==========================


import os
import re
import pandas as pd
import numpy as np
from datetime import datetime,date, time,timedelta,timezone
import pytz

# NORMALIZE THE GATE PASS NO (remove .0, non-digits)
def normalize_gate_pass_no(value) -> str:
    if not value:
        return None

    value = str(value).strip()

    # Remove decimals like 25240231.0
    if value.endswith(".0"):
        value = value[:-2]

    # Remove all non-digit characters
    cleaned = re.sub(r"\D", "", value)

    return cleaned if cleaned else None




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

       # 🔥 Define columns that should be read as strings to prevent .0 issues
    string_columns_to_avoid_float_issue = {
        'OC NUM': str,
        # 'Gate Pass No': str,
        # 'AWB': str,
        # 'BOE NUM': str,


        'Mobile Number': str
    }
 
        # Read file based on type
    if file_type == "excel":
        df = pd.read_excel(file, header=9,dtype=string_columns_to_avoid_float_issue)
    elif file_type == "csv":
        df = pd.read_csv(file,header=7,dtype=string_columns_to_avoid_float_issue)  # for .CSV file
        
    elif file_type == "CSV":
        df = pd.read_csv(file,header=7,dtype=string_columns_to_avoid_float_issue)  # for .CSV file
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

     # ===========================New Addon 06/12/25  👌========================================

    # ============================================
    # 🔥 OC_NUM Cleaning + Duplicate Detection
    # 🔥 OC_NUM Cleaning + Duplicate Detection (NO DROP)
    # ============================================
    if 'oc_num' in df.columns:

        print("\n📌 Checking OC_NUM duplicates...")

        # Convert to string + strip spaces
        df['oc_num'] = df['oc_num'].astype(str).str.strip()

        # Find duplicates based on oc_num
        dupes = df[df.duplicated(subset=['oc_num'], keep=False)].sort_values('oc_num')

        if not dupes.empty:
            print("\n⚠️ Duplicate OC_NUM values found:")
            print(dupes[['oc_num']].value_counts().rename("count"))
        else:
            print("✅ No duplicates found")

        print("ℹ️ NOTE: Duplicates are only reported, NOT removed.\n")

    # ===============================================================================================


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
     # Normalize gate_pass_no values
    if 'gate_pass_no' in df.columns:
        df['gate_pass_no'] = df['gate_pass_no'].apply(normalize_gate_pass_no)
    
    # ⬇️ ADD HERE ⬇️
    if 'gate_pass_no' in df.columns:
        before = len(df)
        df = df[df['gate_pass_no'].notna()]
        after = len(df)
        print(f"🚫 Dropped {before - after} rows with NULL gate_pass_no")

    # Replace pandas NaN/NaT with Python None for database compatibility
    df = df.replace({np.nan: None, pd.NaT: None})
    
    print(df['gate_pass_no'].head(6))


    return df
















