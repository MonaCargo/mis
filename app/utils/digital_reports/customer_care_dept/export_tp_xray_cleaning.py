
import pandas as pd 
import re
import numpy as np
import warnings

warnings.filterwarnings("ignore", message=".*Parsing dates in.* format when dayfirst=True.*")
def normalize_awb_no(value) -> str:
    if pd.isna(value) or not str(value).strip() or str(value).strip().lower() == 'nan':
        return ""
    # Safe conversion to string of awb
    value = str(value)

    # Remove all non-digit characters
    cleaned = re.sub(r'\D', '', value)

    # Ensure it's 11 digits
    if len(cleaned) >= 11:
        return cleaned[:11]  # Raw 11-digit string without the quote
    elif len(cleaned) == 10:
        return '0' + cleaned
    else:
        return value  # Invalid AWB format
    
def fmt_date(d):
    """Format a date object as '08-JUL-2026'; return placeholder if None."""
    if d is None:
        return "N/A"
    return d.strftime("%d-%b-%Y").upper()


def convert_ist_to_utc(value) -> str:
    if pd.isna(value) or not str(value).strip() or str(value).strip().lower() == 'NaN':
        return value

    date_str = str(value).strip()
    if '/' in date_str:
    # dt = None

    # formats_to_try = [
    #     '%d%b%Y %H%M',
    #     '%d/%m/%Y %H:%M',
    #     '%m/%d/%Y %H:%M',
    #     '%d-%b-%y',
    #     '%d-%b',
    # ]
    
    # for fmt in formats_to_try:
        try:
            first_part = int(date_str.split('/')[0])
            is_day_first = True if first_part >12 else False
        # 1. First attempt native pandas datetime parsing with dayfirst prioritization
            dt = pd.to_datetime(date_str, dayfirst=True, errors='raise')
        except Exception:
            dt = pd.to_datetime(date_str, errors='coerce')
    else:
        try:
            # 2. Fallback check specifically tailored for missing-year text strings like "16-Jun"
            if len(date_str) <= 7 and '-' in date_str:
                dt = pd.to_datetime(date_str + '-26', format='%d-%b-%y', errors='raise')
            else:
                # 3. Last resort string matching fallback
                dt = pd.to_datetime(date_str, format='%d%b%Y %H%M', errors='raise')
        except Exception:
            return value # Return original string if it's completely unparseable

    # Shift time safely from Indian Standard Time (IST) to UTC
    dt_ist = dt.tz_localize('Asia/Kolkata', ambiguous='NaT', nonexistent='NaT')
    if pd.isna(dt_ist):
        return value
    
    dt_ist = dt.tz_localize('Asia/Kolkata', ambiguous='NaT', nonexistent='NaT')
    if pd.isna(dt_ist):
        return value

    dt_utc = dt_ist.tz_convert('UTC')
    return dt_utc.strftime('%Y-%m-%d %H:%M:%S')

def fast_validation_before_conversion(df, header_idx, date_col_indices, original_row_headers, user_report_date_str):
    target_report_date = pd.to_datetime(user_report_date_str).date()
    from_date = None
    to_date = None

    for r_idx in range(0, header_idx):
        row_vals = [str(val).strip().upper() for val in df.iloc[r_idx].values if pd.notna(val)]
        for i, val in enumerate(row_vals):
            if 'FROM DATE:' in val and (i + 1)< len(row_vals):
                from_date = row_vals[i + 1]
            if 'TO DATE' in val and (i + 1)< len(row_vals):
                to_date = row_vals[i+1]    

    if from_date and to_date:
        file_from_date = pd.to_datetime(from_date, dayfirst=True).date()
        file_to_date = pd.to_datetime(to_date, dayfirst=True).date()
        
        if file_from_date != target_report_date or file_to_date != target_report_date:
            raise ValueError(
                
                f"Report Date does not match your Selected Date ({fmt_date(target_report_date)}) exactly."
            )
    # 2. Pinpoint the X-Ray End Date Column
    xray_end_col_idx = None
    for idx in date_col_indices:
        header_name = str(original_row_headers[idx]).upper().strip()
        if 'XRAY_END' in header_name or 'X-RAY_END' in header_name or ('END' in header_name and 'START' not in header_name) or 'X-RAY DT' in header_name:
            xray_end_col_idx = idx
            print(f"🔍 System targeted column index {idx} ({header_name}) for row validation.")
            break

    if xray_end_col_idx is not None:
        # Loop through every data row starting right after the header row
        for current_row_idx in range(header_idx + 1, len(df)):
            raw_val = df.iloc[current_row_idx, xray_end_col_idx]
            
            # Skip empty cells natively
            if pd.isna(raw_val) or not str(raw_val).strip():
                continue
                
            clean_str = str(raw_val).strip()
            
            # Parse individual row timestamp safely
            try:
                row_date = pd.to_datetime(clean_str, dayfirst=True).date()
            except Exception:
                try:
                    row_date = pd.to_datetime(clean_str).date()
                except Exception:
                    # If completely unparseable string, treat it as a data mismatch error
                    row_date = None

            # Check if this specific row mismatches the user's targeted execution date
            if row_date != target_report_date:
                # Safely extract the corresponding AWB number for this exact row
                offending_awb = "Unknown"
                if awb_col_idx is not None:
                    offending_awb = df.iloc[current_row_idx, awb_col_idx]

                excel_row_num = current_row_idx + 1
                raise ValueError(
                    f"\n Upload Blocked! Row Alignment Validation Failed.\n"
                    f"──────────────────────────────────────────────────\n"
                    f" Excel Row Location : Row {excel_row_num}\n"
                    f" Air Waybill (AWB)  : {offending_awb}\n"
                    f" Found Mismatch Date: {row_date if row_date else 'Invalid Date Format ('+clean_str+')'}\n"
                    f" Required Date      : {target_report_date}\n"
                    f"──────────────────────────────────────────────────\n"
                    f"Status: File modification halted. No data was processed."
                )

    print("✅ Strict Row-by-Row Validation Passed! Proceeding with data conversion...")
    return True
if __name__ == "__main__":
    input_filename = 'Export_tp.CSV'
    df = pd.read_csv(input_filename, header=None) 
    header_idx = None
    col_idx = None
    date_col_indices = []
    original_row_headers = []

    for idx, row in df.iterrows():
        row_string_values = [str(val).upper().strip() for val in row.values]
        
        if any('AWB NO.' in val or 'AWB NO' in val for val in row_string_values):
            header_idx = idx
            original_row_headers = [str(val).upper().strip() for val in row.values]
            date_col_indices = []
            for c_idx, val in enumerate(row_string_values):
                if 'AWB NO.' in val or 'AWB NO' in val:
                    awb_col_idx = c_idx
                if 'DATE' in val or 'TIME' in val or 'DT' in val:
                    date_col_indices.append(c_idx)
            break
        

    if header_idx is not None:
        USER_SELECTED_REPORT_DATE = '2026-06-25'

        try:
            fast_validation_before_conversion(df, header_idx, date_col_indices, original_row_headers, USER_SELECTED_REPORT_DATE)    
            # print(f" AWB Column Index: {awb_col_idx}")
        # print(f" Date Column Indices Found: {date_col_indices}")
            print(" Transforming dates to UTC formate...")      

            for i in range(header_idx +1, len(df)):
                    
                if awb_col_idx is not None:
                    df.iloc[i, awb_col_idx] = normalize_awb_no(df.iloc[i, awb_col_idx])
                    
                for d_idx in date_col_indices:
                    df.iloc[i, d_idx] = convert_ist_to_utc(df.iloc[i, d_idx])
        
            # df.to_csv('mis_tp_cleaned.csv', header=False, index=False)
            print("Success!")
        except ValueError as format_error:
            print(str(format_error))


    else:
        print("Could not find the AWB NO. column in the sheet.")