# utils/cleaner.py
import re
import pandas as pd
import numpy as np
import math
from datetime import datetime,time as dt_time
from typing import Optional, Union, Any
import io
from fastapi import HTTPException, UploadFile
from pytz import timezone

class DomesticXrayDataCleaner:
    """
    Data cleaner for Domestic X-ray reports.
    Handles Excel and CSV file processing and normalization with NaN handling.
    """
    
    COLUMN_MAPPING = {
        'AWB No.': 'awb_no',
        'DEST.': 'destination',
        'Accp. date': 'accp_date',
        'Accp.Time': 'accp_time',
        'Accp.Pcs': 'accp_pcs',
        'Rej.Pcs.': 'rej_pcs',
        'Gross Weight': 'gross_weight',
        'Rej Gross Wgt': 'rej_gross_weight',
        'Chg Weight': 'chg_weight',
        'SHC': 'shc',
        'Name of Goods': 'name_of_goods',
        'Agent Name': 'agent_name',
        'Freighter Type': 'freighter_type',
        'X-RAY TYPE': 'xray_type',
        'PHS (PCS)': 'phs_pcs',
        'ETD (PCS)': 'etd_pcs',
        'EDS (PCS)': 'eds_pcs',
        'EDD (PCS)': 'edd_pcs',
        'VCK (PCS)': 'vck_pcs',
        'CMD (PCS)': 'cmd_pcs',
        'X-RAY DT/TIME': 'xray_date_time',
        'X-RAY-USER': 'xray_user',
        'Serial No.': 'serial_no',
        'REMARKS': 'remarks'
    }
    
    ALLOWED_EXTENSIONS = {'.xlsx', '.xls', '.csv'}
    ALLOWED_MIME_TYPES = {
        'application/vnd.openxmlformats-officedocument.spreadsheetml.sheet',
        'application/vnd.ms-excel',
        'text/csv',
        'application/csv'
    }
    
    # Define numeric columns that should be cleaned
    NUMERIC_COLUMNS = [
        'accp_pcs', 'rej_pcs', 'gross_weight', 'rej_gross_weight',
        'chg_weight', 'phs_pcs', 'etd_pcs', 'eds_pcs', 'edd_pcs',
        'vck_pcs', 'cmd_pcs', 'serial_no'
    ]
    
    # Columns where NaN should default to 0 instead of None
    ZERO_DEFAULT_COLUMNS = ['rej_pcs', 'rej_gross_weight']
    
    @staticmethod
    def clean_nan_values(value: Any) -> Any:
        """
        Clean NaN, inf, and -inf values from data.
        
        Args:
            value: Value to clean
            
        Returns:
            Cleaned value (None for invalid floats, original value otherwise)
        """
        if value is None:
            return None
        
        # Handle pandas NA/NaT
        if pd.isna(value):
            return None
        
        # Handle numpy nan/inf
        if isinstance(value, (float, np.floating)):
            if math.isnan(value) or math.isinf(value):
                return None
        
        # Handle string representations
        if isinstance(value, str):
            value_lower = value.lower().strip()
            if value_lower in ['nan', '-nan', 'inf', '-inf', 'infinity', '-infinity', '']:
                return None
        
        return value
    
    @staticmethod
    def clean_dataframe_nan(df: pd.DataFrame) -> pd.DataFrame:
        """
        Clean all NaN, inf, and -inf values from DataFrame.
        
        Args:
            df: DataFrame to clean
            
        Returns:
            Cleaned DataFrame
        """
        # Replace inf and -inf with NaN first
        df = df.replace([np.inf, -np.inf], np.nan)
        
        # For numeric columns, replace NaN with None
        for col in df.columns:
            if df[col].dtype in ['float64', 'float32', 'int64', 'int32']:
                # Replace NaN with None for numeric columns
                df[col] = df[col].apply(lambda x: None if pd.isna(x) else x)
        
        # For object columns, replace NaN and empty strings with None
        for col in df.select_dtypes(include=['object']).columns:
            df[col] = df[col].apply(lambda x: None if pd.isna(x) or (isinstance(x, str) and x.strip() == '') else x)
        
        return df
    
    @staticmethod
    def safe_numeric_conversion(value: Any, default: Any = None) -> Any:
        """
        Safely convert value to numeric, handling NaN cases.
        
        Args:
            value: Value to convert
            default: Default value if conversion fails
            
        Returns:
            Converted numeric value or default
        """
        if value is None or pd.isna(value):
            return default
        
        try:
            converted = pd.to_numeric(value, errors='coerce')
            if pd.isna(converted) or math.isnan(converted) or math.isinf(converted):
                return default
            return converted
        except (ValueError, TypeError):
            return default
    
    @staticmethod
    def localize_to_ist(dt: pd.Timestamp) -> Optional[pd.Timestamp]:
        """
        Convert naive datetime to IST (Indian Standard Time) aware datetime.
        
        Args:
            dt: Datetime to localize
            
        Returns:
            IST-aware datetime or None
        """
        if dt is None or pd.isna(dt):
            return None
        
        # If already timezone-aware, return as-is
        if dt.tzinfo is not None:
            return dt
        
        # Localize to IST (UTC+5:30)
        ist = timezone('Asia/Kolkata')
        return ist.localize(dt)
    
    @staticmethod
    def parse_xray_datetime(value: Any) -> Optional[pd.Timestamp]:
        """
        Parse xray_date_time with multiple format attempts.
        Returns timezone-aware datetime in IST.
        
        Args:
            value: Value to parse
            
        Returns:
            IST-aware datetime or None
        """
        # Handle None, NaN, NaT
        if value is None or pd.isna(value):
            return None
        
        # If already a datetime object (from Excel), localize it
        if isinstance(value, (pd.Timestamp, datetime)):
            dt = pd.Timestamp(value)
            return DomesticXrayDataCleaner.localize_to_ist(dt)
        
        # Convert to string and clean
        value_str = str(value).strip()
        
        # Check for nan string
        if value_str.lower() in ['nan', 'nat', '']:
            return None
        
        # Try multiple date formats
        formats = [
            "%d-%m-%Y %H:%M",    # 09-01-2026 14:30
            "%d-%m-%Y %H:%M:%S", # 09-01-2026 14:30:00
            "%d%b%Y %H:%M",      # 09Jan2026 14:30
            "%Y-%m-%d %H:%M:%S", # 2026-01-09 14:30:00
            "%Y-%m-%d %H:%M",    # 2026-01-09 14:30
            "%d/%m/%Y %H:%M",    # 09/01/2026 14:30
        ]
        
        for fmt in formats:
            try:
                dt = pd.to_datetime(value_str, format=fmt)
                return DomesticXrayDataCleaner.localize_to_ist(dt)
            except (ValueError, TypeError):
                continue
        
        # Last resort: let pandas infer the format
        try:
            result = pd.to_datetime(value_str, errors='coerce')
            if pd.notna(result):
                return DomesticXrayDataCleaner.localize_to_ist(result)
        except:
            pass
        
        return None
    
 
    @staticmethod
    def normalize_awb_no(value) -> Optional[str]:
        """
        Normalize AWB number to 11 digits.
        
        Args:
            value: AWB number to normalize
            
        Returns:
            Normalized 11-digit AWB number or None if invalid
        """
        if not value or pd.isna(value):
            return None
        
        value = str(value).strip()
        
        # Check for NaN string representation
        if value.lower() in ['nan', '-nan', '']:
            return None
        
        cleaned = re.sub(r'\D', '', value)
        
        if len(cleaned) == 11:
            return cleaned
        elif len(cleaned) == 10:
            return '0' + cleaned
        else:
            return None
    
    @staticmethod
    def validate_file_type(file: UploadFile) -> None:
        """
        Validate uploaded file type.
        
        Args:
            file: Uploaded file object
            
        Raises:
            HTTPException: If file type is invalid
        """
        # Check file extension
        file_ext = None
        if file.filename:
            file_ext = '.' + file.filename.lower().split('.')[-1]
        
        if file_ext not in DomesticXrayDataCleaner.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file extension. Allowed: {', '.join(DomesticXrayDataCleaner.ALLOWED_EXTENSIONS)}"
            )
        
        # Check MIME type
        if file.content_type not in DomesticXrayDataCleaner.ALLOWED_MIME_TYPES:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Upload Excel (.xlsx, .xls) or CSV (.csv) files only."
            )
    
    @staticmethod
    async def read_file_to_dataframe(file: UploadFile, header_row: int = 5) -> pd.DataFrame:
        """
        Read uploaded file into pandas DataFrame.
        
        Args:
            file: Uploaded file object
            header_row: Row number containing headers (0-indexed for CSV, actual row for Excel)
            
        Returns:
            pandas DataFrame
            
        Raises:
            HTTPException: If file reading fails
        """
        try:
            content = await file.read()
            file_ext = '.' + file.filename.lower().split('.')[-1]
            
            if file_ext in ['.xlsx', '.xls']:
                df = pd.read_excel(io.BytesIO(content), header=header_row)
            elif file_ext == '.csv':
                # For CSV, skip the header rows
                header_row = 2
                df = pd.read_csv(io.BytesIO(content), header=header_row)
            else:
                raise HTTPException(status_code=400, detail="Unsupported file format")
            
            print("DataFrame loaded successfully")
            print(f"Shape: {df.shape}")
            
            return df
            
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error reading file: {str(e)}"
            )
    
    


    @staticmethod
    def process_xray_report(df: pd.DataFrame) -> pd.DataFrame:
        """
        Process and clean X-ray report DataFrame.
        
        Args:
            df: Raw DataFrame from file
            
        Returns:
            Cleaned and processed DataFrame
            
        Raises:
            HTTPException: If processing fails
        """
        try:
            # Remove the first two columns (Unnamed and Sl.No.)
            df = df.iloc[:, 2:]
            
            # Rename columns to snake_case
            df = df.rename(columns=DomesticXrayDataCleaner.COLUMN_MAPPING)
            
            # Clean NaN values early
            df = DomesticXrayDataCleaner.clean_dataframe_nan(df)
            
            # Convert 'accp_date' to datetime
            df['accp_date'] = pd.to_datetime(df['accp_date'], format="%d%b%Y", errors='coerce')
            
            # Convert 'accp_time' to time - handles both Excel and CSV
            def parse_time(value):
                """Parse time from Excel (datetime) or CSV (string) formats"""
                if value is None or pd.isna(value):
                    return None
                
                # If already a Python time object (from Excel)
                if isinstance(value, dt_time):
                    return value
                
                # If it's a Timestamp (from Excel with date+time)
                if isinstance(value, pd.Timestamp):
                    return value.time()
                
                # If it's a datetime object
                if isinstance(value, datetime):
                    return value.time()
                
                # Convert to string for CSV or other formats
                value_str = str(value).strip()
                
                # Check for invalid values
                if value_str.lower() in ['', 'nan', 'nat', 'none']:
                    return None
                
                try:
                    # Try parsing as HH:MM (most common)
                    parsed = pd.to_datetime(value_str, format="%H:%M", errors='coerce')
                    if pd.notna(parsed):
                        return parsed.time()
                    
                    # Try parsing as HH:MM:SS
                    parsed = pd.to_datetime(value_str, format="%H:%M:%S", errors='coerce')
                    if pd.notna(parsed):
                        return parsed.time()
                    
                    # Let pandas infer the format
                    parsed = pd.to_datetime(value_str, errors='coerce')
                    if pd.notna(parsed):
                        return parsed.time()
                except Exception as e:
                    print(f"Error parsing time value '{value}': {e}")
                    pass
                
                return None
            
            df['accp_time'] = df['accp_time'].apply(parse_time)
            
            # Create 'merge_acceptance_date_time' column - handles both Excel and CSV
            def create_merge_datetime(row):
                """Create merged datetime from date and time"""
                accp_date = row['accp_date']
                accp_time = row['accp_time']
                
                # Check if date is valid
                if pd.isna(accp_date):
                    return None
                
                # Check if time is valid
                if accp_time is None or (isinstance(accp_time, float) and math.isnan(accp_time)):
                    return None
                
                try:
                    # Combine date and time
                    date_str = accp_date.strftime('%Y-%m-%d')
                    time_str = str(accp_time)
                    
                    # Check for invalid time string
                    if time_str.lower() in ['nat', 'none', '', 'nan']:
                        return None
                    
                    datetime_str = f"{date_str} {time_str}"
                    merged_dt = pd.to_datetime(datetime_str, errors='coerce')
                    
                    if pd.notna(merged_dt):
                        return DomesticXrayDataCleaner.localize_to_ist(merged_dt)
                except Exception as e:
                    print(f"Error creating merge datetime for row: {e}")
                    pass
                
                return None
            
            df['merge_acceptance_date_time'] = df.apply(create_merge_datetime, axis=1)
            
            # Debug logging
            print(f"\n=== Time Parsing Debug ===")
            print(f"accp_time null count: {df['accp_time'].isna().sum()} / {len(df)}")
            print(f"merge_acceptance_date_time null count: {df['merge_acceptance_date_time'].isna().sum()} / {len(df)}")
            print(f"Sample accp_time values (first 5):")
            for idx, val in enumerate(df['accp_time'].head(5)):
                print(f"  {idx}: {val} (type: {type(val)})")
            print(f"Sample merge_acceptance_date_time values (first 5):")
            for idx, val in enumerate(df['merge_acceptance_date_time'].head(5)):
                print(f"  {idx}: {val} (type: {type(val)})")
            print(f"========================\n")
            
            # Reorder columns to place 'merge_acceptance_date_time' as the 4th column
            columns = df.columns.tolist()
            if 'merge_acceptance_date_time' in columns:
                columns.remove('merge_acceptance_date_time')
            columns.insert(3, 'merge_acceptance_date_time')
            df = df[columns]
            
            # Normalize AWB numbers
            df['awb_no'] = df['awb_no'].apply(DomesticXrayDataCleaner.normalize_awb_no)
            
            # Convert 'xray_date_time' to datetime with robust parsing
            print("Before xray_date_time conversion:")
            print(df['xray_date_time'].head())
            print(f"Data type: {df['xray_date_time'].dtype}")

            df['xray_date_time'] = df['xray_date_time'].apply(
                DomesticXrayDataCleaner.parse_xray_datetime
            )

            print("After xray_date_time conversion:")
            print(df['xray_date_time'].head())
            print(f"Null count: {df['xray_date_time'].isna().sum()}")

            # drop rows with null xray_date_time  
            df = df[df['xray_date_time'].notna()]

            # Log rows with null xray_date_time for debugging
            null_xray = df[df['xray_date_time'].isna()]
            if len(null_xray) > 0:
                print(f"WARNING: {len(null_xray)} rows have null xray_date_time")
                print("Sample AWBs with null xray_date_time:", null_xray['awb_no'].head(5).tolist())

            # Clean numeric columns - convert and handle NaN
            for col in DomesticXrayDataCleaner.NUMERIC_COLUMNS:
                if col in df.columns:
                    # Use 0 as default for rejection columns, None for others
                    default_value = 0 if col in DomesticXrayDataCleaner.ZERO_DEFAULT_COLUMNS else None
                    df[col] = df[col].apply(
                        lambda x: DomesticXrayDataCleaner.safe_numeric_conversion(x, default=default_value)
                    )
            
            # Remove rows with invalid AWB numbers
            df = df[df['awb_no'].notna()]
            
            # Remove completely empty rows
            df = df.dropna(how='all')
            
            # Final cleanup - ensure no NaN values remain
            df = DomesticXrayDataCleaner.clean_dataframe_nan(df)
            
            # Log any remaining NaN issues for debugging
            nan_columns = []
            for col in df.columns:
                if df[col].dtype in ['float64', 'float32']:
                    nan_count = df[col].apply(lambda x: isinstance(x, float) and (math.isnan(x) or math.isinf(x))).sum()
                    if nan_count > 0:
                        nan_columns.append((col, nan_count))
            
            if nan_columns:
                print(f"Warning: NaN values found after cleaning: {nan_columns}")
            
            return df
            
        except Exception as e:
            raise HTTPException(
                status_code=400,
                detail=f"Error processing data: {str(e)}"
            )
        

        
    @staticmethod
    def validate_processed_data(df: pd.DataFrame) -> dict:
        """
        Validate processed data and return statistics.
        
        Args:
            df: Processed DataFrame
            
        Returns:
            Dictionary with validation statistics
        """
        stats = {
            'total_rows': len(df),
            'valid_awb_count': df['awb_no'].notna().sum(),
            'invalid_awb_count': df['awb_no'].isna().sum(),
            'date_range': {
                'start': df['accp_date'].min().strftime('%Y-%m-%d') if df['accp_date'].notna().any() else None,
                'end': df['accp_date'].max().strftime('%Y-%m-%d') if df['accp_date'].notna().any() else None
            },
            'unique_destinations': df['destination'].nunique(),
            'unique_agents': df['agent_name'].nunique(),
            'nan_check': {
                'has_nan_values': False,
                'columns_with_nan': []
            }
        }
        
        # Check for any remaining NaN values
        for col in df.columns:
            if df[col].dtype in ['float64', 'float32', 'int64', 'int32']:
                nan_count = df[col].apply(
                    lambda x: isinstance(x, (float, np.floating)) and (math.isnan(x) or math.isinf(x))
                ).sum()
                if nan_count > 0:
                    stats['nan_check']['has_nan_values'] = True
                    stats['nan_check']['columns_with_nan'].append({
                        'column': col,
                        'nan_count': int(nan_count)
                    })
        
        return stats
    
    @staticmethod
    async def clean_and_validate(file: UploadFile, header_row: int = 5) -> tuple[pd.DataFrame, dict]:
        """
        Complete cleaning and validation pipeline.
        
        Args:
            file: Uploaded file object
            header_row: Row number containing headers
            
        Returns:
            Tuple of (cleaned DataFrame, validation statistics)
        """
        # Validate file type
        DomesticXrayDataCleaner.validate_file_type(file)
        
        # Read file
        df = await DomesticXrayDataCleaner.read_file_to_dataframe(file, header_row)
        
        # Process data
        df_cleaned = DomesticXrayDataCleaner.process_xray_report(df)
        
        # Validate and get statistics
        stats = DomesticXrayDataCleaner.validate_processed_data(df_cleaned)
        
        return df_cleaned, stats
    
    @staticmethod
    def dataframe_to_dict_clean(df: pd.DataFrame) -> list[dict]:
        """
        Convert DataFrame to list of dictionaries with NaN handling.
        
        Args:
            df: DataFrame to convert
            
        Returns:
            List of dictionaries with cleaned values
        """
        records = df.to_dict('records')
        cleaned_records = []
        
        for record in records:
            cleaned_record = {}
            for key, value in record.items():
                cleaned_record[key] = DomesticXrayDataCleaner.clean_nan_values(value)
            cleaned_records.append(cleaned_record)
        
        return cleaned_records

