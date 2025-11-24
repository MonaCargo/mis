import pandas as pd
import numpy as np
from typing import Literal
from io import BytesIO
from datetime import datetime
import pytz


REQUIRED_COLUMNS_MANUAL_SLOT = {
    'Date': 'date',
    'Time': 'time',
    'TC NO': 'tc_no',
    'AWB': 'awb',
    'pcs': 'pcs',
    'Agent Name': 'agent_name',
    'User': 'user',
    'Leger Name': 'leger_name',
    'datetime': 'merge_datetime'
}

class FileStructureError(Exception):
    """Custom exception for file structure validation errors"""
    pass


def read_file(file, file_type: str, header: int = 2) -> pd.DataFrame:
    """Read file based on type with appropriate engine"""
    readers = {
        "csv": lambda f: pd.read_csv(f, header=header),
        "excel": lambda f: pd.read_excel(f, header=header, engine='openpyxl')
    }
    
    if file_type not in readers:
        raise ValueError(f"Unsupported file type: {file_type}. Expected 'csv' or 'excel'")
    
    try:
        df = readers[file_type](file)
        
        # Check if DataFrame is empty
        if df.empty:
            raise FileStructureError("The uploaded file is empty. Please upload a file with data.")
        
        # Check if DataFrame has any columns
        if len(df.columns) == 0:
            raise FileStructureError("The uploaded file has no columns. Please check the file format.")
        
        return df
    except pd.errors.EmptyDataError:
        raise FileStructureError("The uploaded file is empty or corrupted.")
    except pd.errors.ParserError as e:
        raise FileStructureError(f"Failed to parse the file. The file may be corrupted or have incorrect format: {e}")
    except Exception as e:
        raise FileStructureError(f"Failed to read {file_type.upper()} file: {e}")


def filter_valid_legers(df: pd.DataFrame) -> pd.DataFrame:
    """
    Filter rows where 'Leger Name' starts with 'Export TRM_TSP Charges' or 'Export TSP Charges'.
    Handles missing or malformed 'Leger Name' column gracefully.
    """
    if 'Leger Name' not in df.columns:
        available_cols = ', '.join(df.columns.tolist())
        raise FileStructureError(
            f"Invalid file structure: Missing 'Leger Name' column. "
            f"Available columns: {available_cols}. "
            f"Please ensure you're uploading the correct file format with header at row 3."
        )
    
    # Check if column has any non-null values
    if df['Leger Name'].isna().all():
        raise FileStructureError("'Leger Name' column exists but contains no data.")
    
    user_col = df['Leger Name'].astype(str).str.strip()
    mask = (user_col.str.startswith('Export TRM_TSP Charges')) | (user_col.str.startswith('Export TSP Charges'))
    
    filtered_df = df[mask].copy()
    
    # Check if any rows match the filter
    if filtered_df.empty:
        raise FileStructureError(
            "No valid records found. 'Leger Name' must start with 'Export TRM_TSP Charges' or 'Export TSP Charges'. "
            "Please verify the file contains the correct data."
        )
    
    return filtered_df


def validate_required_columns(df: pd.DataFrame):
    """Check if all required columns are present"""
    check_cols = list(REQUIRED_COLUMNS_MANUAL_SLOT.keys())[:-1]  # Exclude 'datetime'
    missing = [col for col in check_cols if col not in df.columns]
    
    if missing:
        available_cols = ', '.join(df.columns.tolist())
        raise FileStructureError(
            f"Invalid file format. Missing required columns: {', '.join(missing)}. "
            f"Available columns: {available_cols}. "
            f"Please ensure the file has the correct structure."
        )


def clean_awb_field(awb_series: pd.Series) -> pd.Series:
    """Remove spaces and special characters from AWB field"""
    return awb_series.astype(str).str.replace(r'\s+', '', regex=True).str.strip()


def convert_pcs_to_int(pcs_series: pd.Series) -> pd.Series:
    """Convert pcs column to integer, handling errors gracefully"""
    return pd.to_numeric(pcs_series, errors='coerce').fillna(0).astype(int)


def create_datetime_column(df: pd.DataFrame, local_tz: str = "Asia/Kolkata") -> pd.DataFrame:
    """
    Create tz-aware datetime column from Date and Time, normalized to UTC.
    Example input: 11-Oct-2025 10:00:00
    """
    try:
        datetime_str = df['Date'].astype(str) + ' ' + df['Time'].astype(str)
        dt_series = pd.to_datetime(datetime_str, errors='coerce', dayfirst=True)
        
        # Check if all datetime conversions failed
        if dt_series.isna().all():
            raise FileStructureError(
                "Failed to parse Date and Time columns. "
                "Please ensure they contain valid date/time values in the expected format (e.g., '11-Oct-2025' and '10:00:00')."
            )
        
        # Localize to provided timezone
        dt_series = dt_series.dt.tz_localize(local_tz, nonexistent='NaT', ambiguous='NaT')
        
        # Convert to UTC
        df['datetime'] = dt_series.dt.tz_convert("UTC")
        
        return df
    except Exception as e:
        raise FileStructureError(f"Error creating datetime column: {e}")


def reorder_columns(df: pd.DataFrame) -> pd.DataFrame:
    """Reorder columns with datetime at position 2"""
    cols = df.columns.tolist()
    if 'datetime' in cols:
        cols.remove('datetime')
        cols.insert(2, 'datetime')
        df = df[cols]
    return df


def clean_manual_slot_file(file, file_type: str) -> pd.DataFrame:
    """
    Main function to clean and validate manual slot file.
    Raises FileStructureError for any file structure issues.
    """
    try:
        # Read file
        df = read_file(file, file_type)
        
        # Check if DataFrame has enough rows
        if len(df) < 1:
            raise FileStructureError("The file doesn't contain enough data rows after the header.")
        
        # Filter valid legers
        df = filter_valid_legers(df)
        
        # Remove first column if exists (usually index or empty)
        if df.shape[1] > 1:
            df = df.iloc[:, 1:].copy()
        else:
            raise FileStructureError("The file doesn't have enough columns after filtering.")
        
        # Validate required columns
        validate_required_columns(df)
        
        # Create datetime column
        df = create_datetime_column(df)
        
        # Select and rename columns
        cleaned_df = df[list(REQUIRED_COLUMNS_MANUAL_SLOT.keys())].rename(
            columns=REQUIRED_COLUMNS_MANUAL_SLOT
        )
        
        # Clean AWB field (remove spaces)
        cleaned_df['awb'] = clean_awb_field(cleaned_df['awb'])
        
        # Convert pcs to integer
        cleaned_df['pcs'] = convert_pcs_to_int(cleaned_df['pcs'])
        
        # Reorder columns
        cleaned_df = reorder_columns(cleaned_df)
        
        # Final validation - ensure we have data
        if cleaned_df.empty:
            raise FileStructureError("No valid data found after processing the file.")
        
        print(cleaned_df.head(20))
        return cleaned_df
        
    except FileStructureError:
        # Re-raise our custom errors as-is
        raise
    except KeyError as e:
        raise FileStructureError(f"Column access error: {e}. Please verify the file structure.")
    except Exception as e:
        raise FileStructureError(f"Unexpected error while processing file: {e}")

