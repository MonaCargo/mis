import re

import pandas as pd
from typing import Tuple

def standardize_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Removes trailing spaces, normalizes header names, and silently drops any duplicates created."""
    df.columns = df.columns.astype(str).str.strip().str.replace('\n', '').str.replace(' + ', ' ', regex=True)
    
    # THE SHIELD: Drop any duplicate columns that were accidentally created by the spacing cleanup
    df = df.loc[:, ~df.columns.duplicated()]
    
    return df


def combine_date_time(df: pd.DataFrame, date_col: str, time_col: str, new_col: str) -> pd.DataFrame:
    """Combines separate Date and Time columns into a single Datetime object."""
    # THE SAFETY CHECK: Only proceed if both columns actually exist and aren't duplicated!
    if date_col in df.columns and time_col in df.columns:
        d_str = df[date_col].astype(str).str.split(' ').str[0]
        t_str = df[time_col].astype(str).str.split(' ').str[-1]
        
        # FIXED: Added dayfirst=True to kill the warning and speed up parsing!
        df[new_col] = pd.to_datetime(d_str + ' ' + t_str, dayfirst=True, errors='coerce')
        
    return df


def assign_shift_and_date(df: pd.DataFrame, datetime_col: str) -> pd.DataFrame:
    """
    Assigns logical_date and shift based on 10 PM to 6 AM boundary.
    (6 AM to 13:59 PM, 14:00 PM to 21:59 PM, 22:00 PM to 05:59 AM)
    """
    df[datetime_col] = pd.to_datetime(df[datetime_col], errors='coerce')
    
    # Calculate Logical Date (Shift everything back by 6 hours for correct daily grouping)
    df['logical_date'] = (df[datetime_col] - pd.Timedelta(hours=6)).dt.date
    
    # Assign Shift
    hour = df[datetime_col].dt.hour
    
    def get_shift(h):
        if pd.isna(h):
            return None
        if 6 <= h < 14:
            return '1st Shift'
        elif 14 <= h < 22:
            return '2nd Shift'
        else:
            return '3rd Shift'
            
    df['shift'] = hour.apply(get_shift)
    return df




def smart_filter_operational_date(df: pd.DataFrame, datetime_col: str, selected_date: str) -> Tuple[pd.DataFrame, int]:
    """
    Check 2: Filter out past/lag dates silently and keep only the selected_date data.
    Returns the filtered dataframe and the count of dropped rows for UI warnings.
    """
    if df.empty or datetime_col not in df.columns:
        return df, 0
        
    target_date = pd.to_datetime(selected_date).date()
    
    # Operational column se dates safely nikal lo 
    # FIXED: Added dayfirst=True for much faster parsing and no terminal warnings
    file_dates = pd.to_datetime(df[datetime_col], dayfirst=True, errors='coerce').dt.date
    
    # Filter: Match rows (Sirf selected_date wali rows rakho)
    match_mask = (file_dates == target_date)
    
    filtered_df = df[match_mask].copy()
    
    # Safely convert to standard int taaki JSON serialization me issue na aaye
    dropped_count = int((~match_mask).sum())
    
    # Backend log ke liye
    if dropped_count > 0:
        print(f"⚠️ Smart Filter: Dropped {dropped_count} rows with lag/past operational dates.")
        
    # Ab ye dono cheezein wapas bhejega
    return filtered_df, dropped_count






# Used to convert numeric date format to like 23 jul 2026--------
def _extract_file_date_display(clean_header_text: str) -> str:
    # Try the 4-digit-year pattern first (e.g. 14JUL2026) since it's more specific.
    match = re.search(r'(\d{1,2})([A-Z]{3})(\d{4})', clean_header_text)
    if not match:
        # Fall back to 2-digit-year pattern (e.g. 14JUL26)
        match = re.search(r'(\d{1,2})([A-Z]{3})(\d{2})(?!\d)', clean_header_text)

    if not match:
        return "Unknown (no date found in file header)"

    day, mon_abbr, year = match.groups()
    if len(year) == 2:
        year = f"20{year}"  # assume 2000s

    try:
        parsed = pd.to_datetime(f"{day}{mon_abbr}{year}", format="%d%b%Y")
        return parsed.strftime('%d-%B-%Y')  # e.g. 14-July-2026
    except Exception:
        # Date-like text was found but couldn't be parsed cleanly
        return f"Unrecognized format ({day}{mon_abbr}{year})"




