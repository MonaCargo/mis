from typing import Optional

import pandas as pd
import io
from app.utils.digital_reports.customer_care_dept.monthly_excel_data_clean_extract import XRAY_MASTER
import numpy as np
from datetime import datetime, timedelta, timezone

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import delete, select, func, desc
import datetime as dt_module
from calendar import monthrange
from datetime import datetime 
from collections import defaultdict
from fastapi import HTTPException, UploadFile
from datetime import time as  dt_time


from app.db.models.digital_reports.customer_care.import_tp_xray import DigitalReportImportTpXray
from app.db.models.digital_reports.customer_care.export_tp_xray import DigitalReportExportTpXray
from app.db.models.digital_reports.customer_care.export_xray import DigitalReportExportXray
from app.db.models.digital_reports.customer_care.xray_performance import DigitalReportXRayPerformance

import re
import time 
from app.utils.digital_reports.customer_care_dept.export_tp_xray_cleaning import (
    normalize_awb_no  , 
    convert_ist_to_utc , 
    fast_validation_before_conversion 
)
from app.utils.digital_reports.customer_care_dept.import_tp_xray_cleaning import (
    normalize_awb_no , 
    convert_ist_to_utc , 
    fast_validation_before_conversion 
)
from app.utils.digital_reports.customer_care_dept.export_xray_cleaning import (
    normalize_awb_no , 
    convert_ist_to_utc , 
    fast_validation_before_conversion 
)






_MACHINE_NAME_TO_SERIAL = {
    meta["machineNo"].upper().replace(" ", ""): serial
    for serial, meta in XRAY_MASTER.items()
}


def _match_serial_for_column(col_name: str) -> Optional[str]:
    base = col_name.rsplit('_', 1)[0] if '_' in col_name else col_name
    key = base.upper().replace(" ", "")
    if key in _MACHINE_NAME_TO_SERIAL:
        return _MACHINE_NAME_TO_SERIAL[key]
    for name_key, serial in _MACHINE_NAME_TO_SERIAL.items():
        if key in name_key or name_key in key:
            return serial
    return None

# DATE_LIKE_PATTERN = re.compile(
#     r'^(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})|^(\d{1,2}[A-Za-z]{3}\d{2,4})|^(\d{4}[-/]\d{1,2}[-/]\d{1,2})', 
#     re.IGNORECASE
# )

DATE_LIKE_PATTERN = re.compile(
    r'^(\d{1,2}[-/]\d{1,2}[-/]\d{2,4})'
    r'|^(\d{1,2}[-/][A-Za-z]{3}[-/]\d{2,4})'     # <-- add this line: matches 08-JUL-26
    r'|^(\d{1,2}[A-Za-z]{3}\d{2,4})'
    r'|^(\d{4}[-/]\d{1,2}[-/]\d{1,2})',
    re.IGNORECASE
)

class MISReportService:
    
    @staticmethod
    def get_val(row, header_map, col_name):
        idx = header_map.get(col_name.upper().strip())
        return str(row[idx]).strip() if idx is not None and idx < len(row) and pd.notna(row[idx]) else ""
    
    @staticmethod
    def get_serial(row, header_map, col_name):
        
        val = MISReportService.get_val(row, header_map, col_name)
        if not val:
            return val
        try:
            return str(int(float(val)))
        except (ValueError, TypeError):
            return val

    @staticmethod
    def get_num(row, header_map, col_name, is_float=False):
        idx = header_map.get(col_name.upper().strip())
        val = str(row[idx]).strip() if idx is not None and idx < len(row) and pd.notna(row[idx]) else ""
        if not val or val.upper() in ["NAN", "NULL"]:
            return None
        try: 
            return float(val) if is_float else int(float(val))
        except: 
            return None

    @staticmethod
    def parse_to_datetime(val):
        """Parses raw IST strings and returns a tz-aware UTC datetime object."""
        if not val or str(val).strip().upper() in ["NAN", "NAT", "NULL", "GEN", "N/A", ""]:
            return None
        try:
            dt_obj = pd.to_datetime(val, format="%d-%m-%Y %H:%M")
        except Exception:
            try:
                dt_obj = pd.to_datetime(val, dayfirst=True, errors="coerce")
            except Exception:
                return None

        if pd.isna(dt_obj):
            return None

        if dt_obj.tzinfo is not None:
            return dt_obj.tz_convert("UTC").to_pydatetime()

        dt_ist = dt_obj.tz_localize("Asia/Kolkata", ambiguous="NaT", nonexistent="NaT")
        if pd.isna(dt_ist):
            return None

        return dt_ist.tz_convert("UTC").to_pydatetime()
    
        if col_idx < preview_df.shape[1]:
            preview_df.iloc[header_idx + 1:, col_idx] = preview_df.iloc[header_idx + 1:, col_idx].apply(
                lambda v: parse_to_datetime(str(v).strip()).strftime("%Y-%m-%d %H:%M") 
                if parse_to_datetime(str(v).strip()) else v
            )
    
    @classmethod
    def _parse_and_validate(cls, df: pd.DataFrame, target_date: datetime.date):
        """Helper to find headers and execute imported fast_validation function."""
        header_idx = None
        awb_col_idx = None
        date_col_indices = []
        original_row_headers = []

        for idx, row in df.iterrows():
            row_string_values = [str(val).upper().strip() for val in row.values]
            # Match both "AWB NO." and "AWB NO"
            if any('AWB NO' in val or 'AWB_NO' in val for val in row_string_values):
                header_idx = idx
                original_row_headers = [str(val).upper().strip() for val in row.values]
                for c_idx, val in enumerate(row_string_values):
                    if 'AWB NO' in val or 'AWB_NO' in val:
                        awb_col_idx = c_idx
                    if 'DATE' in val or 'TIME' in val or 'DT' in val:
                        date_col_indices.append(c_idx)
                break

        if header_idx is None:
            raise HTTPException(status_code=400, detail="Could not find the AWB NO. column in the sheet.")

        try:
            user_date_str = target_date.strftime("%Y-%m-%d")
            fast_validation_before_conversion(df, header_idx, date_col_indices, original_row_headers, user_date_str)
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))

        return header_idx, awb_col_idx, date_col_indices, original_row_headers
   
    @staticmethod
    def _validate_row_date(val, target_date: datetime.date, row_idx: int, awb: str):
        """Helper to parse dates safely and validate row-by-row matching against target date."""
        if pd.isna(val) or not str(val).strip():
            return None
        
        clean_str = str(val).strip()
        try:
            date_part = clean_str.split()[0]
            row_date = datetime.strptime(date_part, "%d-%m-%Y").date()
        except Exception:
            try:
                row_date = pd.to_datetime(clean_str, dayfirst=True).date()
            except Exception:
                raise HTTPException(
                    status_code=400,
                    detail=f"Row {row_idx}: Unable to parse date/timestamp value '{val}'."
                )
        if row_date != target_date:
            raise HTTPException(
                status_code=400,
                detail=f"Upload Blocked! Row {row_idx} (AWB: {awb}) belongs to date {row_date}, but your selected target input date is {target_date}."
            )
        return row_date
    

    @staticmethod
    def print_terminal_preview(df, header_idx, awb_col_idx, date_col_indices, headers, label="REPORT"):
        """Utility method to beautifully print preview segments inside terminal logs."""
        try:
            print(f"\n========================= {label} DATA PREVIEW =========================\n")
            preview_df = df.iloc[header_idx + 1 : header_idx + 11].copy()
            preview_df.columns = headers
            
            cols_to_show = []
            if awb_col_idx is not None and awb_col_idx < len(headers):
                cols_to_show.append(headers[awb_col_idx])
            
            count = 0
            for d_idx in date_col_indices:
                if d_idx < len(headers) and count < 3:
                    cols_to_show.append(headers[d_idx])
                    count += 1
            
            pd.set_option('display.max_columns', None)
            pd.set_option('display.width', 1000)
            pd.set_option('display.colheader_justify', 'center')
            # print(preview_df[cols_to_show].to_string(index=False))
            # print("\n================================────────────────────────================\n")
        except Exception as e:
            print(f"Terminal preview rendering skipped: {e}")

    @staticmethod
    def print_database_save_log(db_objects, label="REPORT"):
        """Prints the finalized records with converted UTC timestamps right before DB commit."""
        try:
            if not db_objects:
                print(f"\n⚠️ [DB SAVE] No records found to save for {label}.")
                return

            # print(f"\n========================= [DB SAVE - CONVERTED UTC DATA] {label} =========================\n")
            
            # print(f"{'SL NO':<6} | {'AWB NUMBER':<14} | {'XRAY START (UTC)':<18} | {'XRAY END (UTC)':<18} | {'FLIGHT NO':<10}")
            # print("-" * 88)
            
            for obj in db_objects[:5]:
                sl_no    = getattr(obj, 'sl_no', 'N/A')
                awb      = getattr(obj, 'awb_no', 'N/A')
                xr_start = getattr(obj, 'xray_start_datetime', 'N/A')
                xr_end   = getattr(obj, 'xray_end_datetime', 'N/A')
                flt_no   = getattr(obj, 'flt_no', 'N/A')
                
                str_start = xr_start.strftime("%Y-%m-%d %H:%M") if hasattr(xr_start, 'strftime') else str(xr_start)
                str_end   = xr_end.strftime("%Y-%m-%d %H:%M") if hasattr(xr_end, 'strftime') else str(xr_end)
                
                # Fixed 'str_no' to 'flt_no' here:
                print(f"{str(sl_no):<6} | {str(awb):<14} | {str_start:<18} | {str_end:<18} | {str(flt_no):<10}")
                
            if len(db_objects) > 5:
                print(f"\n... and {len(db_objects) - 5} more records successfully saved in UTC format.")
            # print("\n========================================================================================\n")
        except Exception as e:
            print(f"Failed to log cleaned database saving state: {e}")    # @classmethod

    @staticmethod
    async def get_monthly_xray_performance_report(
        db: AsyncSession,
        
        report_month: Optional[str],
       
    ) -> dict:
        
        # 1. Base Query forced to 'monthly'
        query = select(DigitalReportXRayPerformance).where(
            DigitalReportXRayPerformance.period_type == 'monthly'
        )
        
        # 2. Apply optional filters
        
        # if report_month:
        #     query = query.where(DigitalReportXRayPerformance.report_month == report_month)
            
        # 3. Get Total Count for Pagination
        count_query = select(func.count()).select_from(query.subquery())
        total_count_result = await db.execute(count_query)
        total_count = total_count_result.scalar_one()

        # 4. Order by Newest Month First, then ID as fallback
        query = query.order_by(
            desc(DigitalReportXRayPerformance.report_month),
            desc(DigitalReportXRayPerformance.id)
        )

       
        
        # 6. Execute query
        result = await db.execute(query)
        records = result.scalars().all()
        
        return {
            "total_count": total_count,
            "data": records
        }

    @classmethod
    async def process_export_normal(cls, file: UploadFile, target_date: datetime, delete_previous: bool, db: AsyncSession, uploaded_by: str):
        # df = pd.read_csv(file.file, header=None)
        df = pd.read_csv(file.file, header=None, engine="python", names=range(35))
        t_read = time.perf_counter()
        t_start = time.perf_counter() 
        header_idx, awb_col_idx, date_col_indices, headers = cls._parse_and_validate(df, target_date) 
        t_validate = time.perf_counter()
        header_map = {str(h).upper().strip(): idx for idx, h in enumerate(headers)}

        file_content_string = df.astype(str).to_string().upper()

        if "X-RAY REPORT  " not in file_content_string:
            raise HTTPException(
                status_code=400,
                detail="Incorrect file! Please upload the valid Export X-RAY REPORT  "
            )
        def check_row_shift(row, headers, date_col_indices, idx, awb_col_idx):   
            awb = row[awb_col_idx] if awb_col_idx < len(row) else "Unknown"

            # 1. Target Validation on Date Fields
            date_fields = [ "X-RAY END DATE & TIME", ]
            for field in date_fields:
                col_idx = header_map.get(field)
                if col_idx is None or col_idx >= len(row) or pd.isna(row[col_idx]):
                    continue
                
                val = str(row[col_idx]).strip()
                if not val or val.upper() in ["GEN", "N/A", "NAN", "NAT", "NULL"]:
                    continue
                
                # Check if it looks like a valid date format
                if not bool(DATE_LIKE_PATTERN.match(val)):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Row {idx + 1} (AWB {awb}): Column shift detected — "
                               f"column '{field}' should contain a valid date but found '{val}'."
                    )

            # 2.🚫 Target Validation on PCS (Should be a pure number, not a date layout)
            pcs_fields = ["PCS", "PCS."]
            for field in pcs_fields:
                col_idx = header_map.get(field)
                if col_idx is None or col_idx >= len(row) or pd.isna(row[col_idx]):
                    continue
                
                val = str(row[col_idx]).strip()
                if not val:
                    continue
                
                # If PCS field accidentally matches a date pattern, a shift happened
                if bool(DATE_LIKE_PATTERN.match(val)):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Row {idx + 1} (AWB {awb}): Column shift detected — "
                               f"numeric column '{field}' contains a date value ('{val}')."
                    )
       
       
        # Only touch the ~10 rows that print_terminal_preview actually shows
        preview_slice = df.iloc[header_idx + 1 : header_idx + 11].copy()
        for col_idx in date_col_indices:
            if col_idx < preview_slice.shape[1]:
                preview_slice[col_idx] = preview_slice[col_idx].apply(
                    lambda v: (cls.parse_to_datetime(str(v).strip()).strftime("%Y-%m-%d %H:%M")
                            if cls.parse_to_datetime(str(v).strip()) else v)
                )

        cls.print_terminal_preview(preview_slice, header_idx, awb_col_idx, date_col_indices, headers, label="EXPORT NORMAL (CLEANED UTC)")
        db_objects = []
        count =0
        for idx in range(header_idx + 1, len(df)):
            row = df.iloc[idx]
            if row.isna().all():
                continue
            check_row_shift(row, headers, date_col_indices, idx, awb_col_idx)
            cleaned_awb = normalize_awb_no(row[awb_col_idx])
            if not cleaned_awb:
                continue

            raw_xray_end = cls.get_val(row, header_map, "XRAY_END_DT") or cls.get_val(row, header_map, "X-RAY END DATE & TIME")
                
            raw_xray_start = cls.get_val(row, header_map, "XRAY_START_DT") or cls.get_val(row, header_map, "X-RAY START DATE & TIME")
            
            raw_xray_dt = cls.get_val(row,header_map, "X-RAY DT/TIME") 
            
            raw_car_msg = cls.get_val(row,header_map, "CAR MSG DATE/TIME") 
            
            raw_leo_dt =  cls.get_val(row, header_map,"LEO DATE/TIME")  
                
            raw_doc_accpt = cls.get_val(row,header_map, "DOC ACCPT DT/ TIME")  
                
            raw_rcs_rcf = cls.get_val(row,header_map, "RCS/RCF/RCT DT/TIME") 
               
            raw_uplifting =  cls.get_val(row, header_map,"UPLIFTING DT/TIME")  
            
            raw_sb_date = cls.get_val(row, header_map,"SB DATE") 

            # CRITICAL FIX: Directly processing strings into datetimes without secondary shifts
            xray_end_obj = cls.parse_to_datetime(raw_xray_end)
            xray_start_obj = cls.parse_to_datetime(raw_xray_start)
            xray_dt_obj = cls.parse_to_datetime(raw_xray_dt)
            car_msg_obj = cls.parse_to_datetime(raw_car_msg)
            
            leo_dt_obj = cls.parse_to_datetime(raw_leo_dt)
            doc_accpt_obj = cls.parse_to_datetime(raw_doc_accpt)
            rcs_rcf_obj = cls.parse_to_datetime(raw_rcs_rcf)
            uplifting_obj = cls.parse_to_datetime(raw_uplifting)
            
            sb_dt = cls.parse_to_datetime(raw_sb_date)
            sb_date_obj = sb_dt.date() if sb_dt else None

            db_objects.append(DigitalReportExportXray(
                sl_no=cls.get_num(row,header_map, "Sl.No.")  or (idx - header_idx),
                awb_no=cleaned_awb,
                sb_no=cls.get_val(row,header_map, "SB No."),
                sb_date=sb_date_obj,
                origin=cls.get_val(row, header_map,"ORGIN") or cls.get_val(row, header_map,"ORIGIN"),
                destination=cls.get_val(row,header_map, "DESTINATION") ,
                pcs=(cls.get_num(row, header_map,"PCS.")or 0),
                grs_wt=(cls.get_num(row,header_map, "GROSS WT", is_float=True) or 0) ,
                chg_wt=cls.get_num(row, header_map,"CHG WT", is_float=True) ,
                nog=cls.get_val(row,header_map, "NOG") ,
                shc=cls.get_val(row,header_map, "SHC") , 
                car_msg_datetime=car_msg_obj,
                leo_datetime=leo_dt_obj,
                xray_start_datetime=xray_start_obj,
                xray_end_datetime=xray_end_obj,
                xray_type=cls.get_val(row,header_map, "X-RAY TYPEX-RAY TYPE") or cls.get_val(row,header_map, "X-RAY TYPE"), 
                xray_datetime=xray_dt_obj, 
                xray_user=cls.get_val(row,header_map, "X-RAY-USER"),
                phs_pcs=cls.get_num(row,header_map, "PHS (PCS)") , 
                etd_pcs=cls.get_num(row,header_map, "ETD (PCS)") , 
                eds_pcs=cls.get_num(row, header_map,"EDS (PCS)") , 
                edd_pcs=cls.get_num(row, header_map,"EDD (PCS)"),
                vck_pcs=cls.get_num(row, header_map,"VCK (PCS)") , 
                cmd_pcs=cls.get_num(row, header_map,"CMD (PCS)") , 
                doc_accpt_datetime=doc_accpt_obj, 
                rcs_rcf_rct_datetime=rcs_rcf_obj, 
                uplifting_datetime=uplifting_obj, 
                flt_no=cls.get_val(row,header_map, "FLT NO") ,
                agent_name=cls.get_val(row, header_map,"AGENT NAME") ,
                serial_no=cls.get_serial(row,header_map, "Serial No.") ,
                device_model_no=cls.get_val(row,header_map, "Device Model No.") ,
                remarks=cls.get_val(row, header_map,"Remarks") ,
                month_uploaded=target_date.strftime("%B"),
                uploaded_by=uploaded_by,
                report_date=target_date
            ))
        t_clean = time.perf_counter()
        if db_objects:

            clean_target_date = target_date.date() if hasattr(target_date, 'date') else target_date
            
            # We clear records sharing the identical report_date timestamp 
            await db.execute(
                delete(DigitalReportExportXray).where(DigitalReportExportXray.report_date == clean_target_date)
            )
            await db.flush()

        db.add_all(db_objects)
        print(f"DEBUG: Attempting to save {len(db_objects)} records to database.")
        await db.commit()
        
        # await db.refresh()
        t_commit = time.perf_counter()
        
        # Print final database save verification table
        cls.print_database_save_log(db_objects, label="EXPORT NORMAL")
    #     print(
    #         f"\n⏱️  TIMING [EXPORT NORMAL] "
    #         f"read_csv: {t_read - t_start:.3f}s | "
    #         f"validate: {t_validate - t_read:.3f}s | "
    #         f"clean_loop: {t_clean - t_validate:.3f}s | "
    #         f"db_commit: {t_commit - t_clean:.3f}s | "
    #         f"TOTAL: {t_commit - t_start:.3f}s\n"
    # )
        return {"status": "Success", "records_inserted": len(db_objects),
                "timing_seconds": {
                    "read_csv": round(t_read - t_start, 3),
                    "validate": round(t_validate - t_read, 3),
                    "clean_loop": round(t_clean - t_validate, 3),
                    "db_commit": round(t_commit - t_clean, 3),
                    "total": round(t_commit - t_start, 3),
                }}
    
    @classmethod
    async def process_export_tp(cls, file: UploadFile, target_date: datetime, delete_previous: bool, db: AsyncSession, uploaded_by: str):
        # df = pd.read_csv(file.file, header=None)
        df = pd.read_csv(file.file, header=None, engine="python", names=range(35))
        header_idx, awb_col_idx, date_col_indices, headers = cls._parse_and_validate(df, target_date)
        header_map = {str(h).upper().strip(): idx for idx, h in enumerate(headers)}
    
        file_content_string = df.astype(str).to_string().upper()
        print(f"DEBUG: File content string length: {len(file_content_string)}")
        print(f"DEBUG: File content string: {file_content_string}")

        if "EXPORT TP X-RAY REPORT" not in file_content_string:
            raise HTTPException(
                status_code=400,
                detail="Incorrect file! Please upload the valid Export TP X-RAY REPORT  "
            )
        def check_row_shift(row, headers, date_col_indices, idx, awb_col_idx):   
            awb = row[awb_col_idx] if awb_col_idx < len(row) else "Unknown"

            # 1. Target Validation on Date Fields
            date_fields = [ "X-RAY END DATE & TIME",  ]
            for field in date_fields:
                col_idx = header_map.get(field)
                if col_idx is None or col_idx >= len(row) or pd.isna(row[col_idx]):
                    continue
                
                val = str(row[col_idx]).strip()
                if not val or val.upper() in ["GEN", "N/A", "NAN", "NAT", "NULL"]:
                    continue
                
                # Check if it looks like a valid date format
                if not bool(DATE_LIKE_PATTERN.match(val)):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Row {idx + 1} (AWB {awb}): Column shift detected — "
                               f"column '{field}' should contain a valid date but found '{val}'."
                    )

            # 2.🚫 Target Validation on PCS (Should be a pure number, not a date layout)
            pcs_fields = ["PCS", "PCS."]
            for field in pcs_fields:
                col_idx = header_map.get(field)
                if col_idx is None or col_idx >= len(row) or pd.isna(row[col_idx]):
                    continue
                
                val = str(row[col_idx]).strip()
                if not val:
                    continue
                
                # If PCS field accidentally matches a date pattern, a shift happened
                if bool(DATE_LIKE_PATTERN.match(val)):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Row {idx + 1} (AWB {awb}): Column shift detected — "
                               f"numeric column '{field}' contains a date value ('{val}')."
                    )

        # Visual preview isolation conversion
        preview_df = df.copy()
        for col_idx in date_col_indices:
            if col_idx < preview_df.shape[1]:
                preview_df.iloc[header_idx + 1:, col_idx] = preview_df.iloc[header_idx + 1:, col_idx].apply(
                    lambda v: cls.parse_to_datetime(str(v).strip()).strftime("%Y-%m-%d %H:%M") 
                    if cls.parse_to_datetime(str(v).strip()) else v
                )

        cls.print_terminal_preview(preview_df, header_idx, awb_col_idx, date_col_indices, headers, label="EXPORT TP (CLEANED UTC)")

        db_objects = []
        count = 0
        for idx in range(header_idx + 1, len(df)):
            row = df.iloc[idx]
            if row.isna().all():
                continue
            check_row_shift(row, headers, date_col_indices, idx, awb_col_idx)
            cleaned_awb = normalize_awb_no(row[awb_col_idx])
            if not cleaned_awb:
                continue

            raw_xray_start = cls.get_val(row, header_map, "X-RAY STRT DATE & TIME") or cls.get_val(row, header_map, "X-RAY START DATE & TIME")
            
            raw_xray_end = cls.get_val(row, header_map, "X-RAY END DATE & TIME") or cls.get_val(row, header_map, "X-RAY START DATE & TIME")
            
            raw_xray_dt =  cls.get_val(row, header_map,"X-RAY DT/TIME")
            
            raw_rcs_rcf = cls.get_val(row, header_map,"RCS/RCF/RCT DT/TIME")
            
            raw_doc_accpt = cls.get_val(row,header_map, "DOC ACCPT DT/ TIME")  
            
            raw_uplifting = cls.get_val(row, header_map,"UPLIFTING DT/TIME")
            

            db_objects.append(DigitalReportExportTpXray(
                sl_no=cls.get_num(row, header_map,"Sl.No.") ,
                awb_no=cleaned_awb,
                origin=cls.get_val(row,header_map, "ORGIN") or cls.get_val(row, header_map,"ORIGIN") ,
                destination=cls.get_val(row, header_map,"DESTINATION") ,
                pcs=(cls.get_num(row,header_map, "PCS.")or 0),
                grs_wt=(cls.get_num(row,header_map, "GROSS WT", is_float=True) or 0),
                chg_wt=cls.get_num(row,header_map, "CHG WT", is_float=True) ,
                nog=cls.get_val(row,header_map, "NOG"),
                shc=cls.get_val(row, header_map,"SHC") ,
                xray_start_datetime=cls.parse_to_datetime(raw_xray_start),
                xray_end_datetime=cls.parse_to_datetime(raw_xray_end),
                xray_type=cls.get_val(row, header_map, "X-RAY TYPE"),
                xray_datetime=cls.parse_to_datetime(raw_xray_dt),
                xray_user= cls.get_val(row,header_map, "X-RAY-USER") ,
                # phs_pcs=get_num(row, "PHS PCS") or get_num(row, "PHS_PCS"),
                # etd_pcs=get_num(row, "ETD PCS") or get_num(row, "ETD_PCS"),
                # eds_pcs=get_num(row, "EDS PCS") or get_num(row, "EDS_PCS"),
                # edd_pcs=get_num(row, "EDD PCS") or get_num(row, "EDD_PCS"),
                # vck_pcs=get_num(row, "VCK PCS") or get_num(row, "VCK_PCS"),
                # cmd_pcs=get_num(row, "CMD PCS") or get_num(row, "CMD_PCS"),
                doc_accpt_datetime=cls.parse_to_datetime(raw_doc_accpt),
                rcs_rcf_rct_datetime=cls.parse_to_datetime(raw_rcs_rcf),
                uplifting_datetime=cls.parse_to_datetime(raw_uplifting),
                flt_no=cls.get_val(row,header_map, "FLT NO") or cls.get_val(row, header_map,"FLIGHT NO"),
                agent_name=cls.get_val(row,header_map, "AGENT NAME") ,
                serial_no= cls.get_serial(row,header_map, "Serial No."),
                device_model_no= cls.get_val(row,header_map, "Device Model No."),
                # remarks=get_val(row, "REMARKS") or "N/A",
                month_uploaded=target_date.strftime("%B"),
                uploaded_by=uploaded_by,
                report_date=target_date
            ))

        if db_objects:

            clean_target_date = target_date.date() if hasattr(target_date, 'date') else target_date
            
            # We clear records sharing the identical report_date timestamp 
            await db.execute(
                delete(DigitalReportExportTpXray).where(DigitalReportExportTpXray.report_date == clean_target_date)
            )
            await db.flush()

        db.add_all(db_objects)
        await db.commit()
        cls.print_database_save_log(db_objects, label="EXPORT TP")
        return {"status": "Success", "records_inserted": len(db_objects)}
     
    @classmethod
    async def process_import_digital(cls, file: UploadFile, target_date: datetime, delete_previous: bool, db: AsyncSession, uploaded_by: str):
        # df = pd.read_csv(file.file, header=None)
        df = pd.read_csv(file.file, header=None, engine="python", names=range(35))
        header_idx, awb_col_idx, date_col_indices, headers = cls._parse_and_validate(df, target_date)
        header_map = {str(h).upper().strip(): idx for idx, h in enumerate(headers)}

        file_content_string = df.astype(str).to_string().upper()
        
        if "X-RAY TP REPORT" not in file_content_string:
            raise HTTPException(
                status_code=400,
                detail="Incorrect file! Please upload the valid X-RAY TP REPORT"
            )
        # if delete_previous:
        #     await db.execute(delete(DigitalReportImportTpXray).where(DigitalReportImportTpXray.report_date == target_date))
        # def check_row_shift(row, headers, header_map, idx, awb_col_idx):
        def check_row_shift(row, headers, date_col_indices, idx, awb_col_idx):   
            awb = row[awb_col_idx] if awb_col_idx < len(row) else "Unknown"

            # Fields that should NEVER contain a date-like value
            text_only_fields = ["X-RAY TYPE", "X-RAY-USER", "NOG", "SHC", "FLT NO", "AGENT NAME"]
            for field in text_only_fields:
                col_idx = header_map.get(field.upper().strip())
                if col_idx is None or col_idx >= len(row) or pd.isna(row[col_idx]):
                    continue
                val = str(row[col_idx]).strip()
                if DATE_LIKE_PATTERN.match(val):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Row {idx + 1} (AWB {awb}): Column shift detected — field '{field}' "
                            f"contains a date-like value ('{val}'). Upload blocked, please fix the source file."
                    )
                

            #🚫 Fields that should be a date, if filled, must actually parse as one
            date_fields = ["X-RAY END DATE & TIME", "X-RAY STRT DATE & TIME", "X-RAY DT/TIME"]
            for field in date_fields:
                col_idx = header_map.get(field.upper().strip())
                if col_idx is None or col_idx >= len(row) or pd.isna(row[col_idx]):
                    continue
                val = str(row[col_idx]).strip()
                if val and not DATE_LIKE_PATTERN.match(val):
                    raise HTTPException(
                        status_code=400,
                        detail=f"Row {idx + 1} (AWB {awb}): Column shift detected — field '{field}' "
                            f"expected a date but got '{val}'. Upload blocked, please fix the source file."
                    )  
        
        # Visual preview isolation conversion
        preview_df = df.copy()
        for col_idx in date_col_indices:
            if col_idx < preview_df.shape[1]:
                preview_df.iloc[header_idx + 1:, col_idx] = preview_df.iloc[header_idx + 1:, col_idx].apply(
                    lambda v: cls.parse_to_datetime(str(v).strip()).strftime("%Y-%m-%d %H:%M") 
                    if cls.parse_to_datetime(str(v).strip()) else v
                )

        cls.print_terminal_preview(preview_df, header_idx, awb_col_idx, date_col_indices, headers, label="IMPORT DIGITAL (CLEANED UTC)")
      
        db_objects = []
        count = 0
        for idx in range(header_idx + 1, len(df)):
            row = df.iloc[idx]
            if row.isna().all():
                continue
            check_row_shift(row, headers, date_col_indices, idx, awb_col_idx)
            cleaned_awb = normalize_awb_no(row[awb_col_idx])
            if not cleaned_awb:
                continue

            raw_xray_start = cls.get_val(row, header_map,"X-RAY STRT DATE & TIME")
            
            raw_xray_end = cls.get_val(row, header_map,"X-RAY END DATE & TIME")
            
            raw_xray_dt = cls.get_val(row, header_map,"X-RAY DT/TIME")
            
            raw_rcs_rcf = cls.get_val(row,header_map, "RCS/RCF/RCT DT/TIME")
            
            raw_uplifting = cls.get_val(row,header_map, "UPLIFTING DT/TIME")
            
            
            if count<3:
                count = count+1
                print("xray_dt_obj👍👍👍👍",row)
                print("xray_dt_obj👍👍👍👍",row)

            db_objects.append(DigitalReportImportTpXray(
                sl_no=cls.get_num(row,header_map, "Sl.No.") ,
                awb_no=cleaned_awb,
                origin=cls.get_val(row, header_map,"ORGIN") or cls.get_val(row, header_map,"ORIGIN") ,
                destination=cls.get_val(row,header_map, "DESTINATION") ,
                pcs=(cls.get_num(row, header_map,"PCS.") or cls.get_num(row,header_map, "PCS") or 0) ,
                grs_wt=(cls.get_num(row, header_map,"GROSS WT", is_float=True) or 0),
                chg_wt=cls.get_num(row,header_map, "CHG WT", is_float=True) ,
                nog=cls.get_val(row,header_map, "NOG") ,
                shc=cls.get_val(row, header_map,"SHC") ,
                xray_start_datetime=cls.parse_to_datetime(raw_xray_start) ,
                xray_end_datetime=cls.parse_to_datetime(raw_xray_end),
                xray_type= cls.get_val(row, header_map,"X-RAY TYPE") ,
                xray_datetime=cls.parse_to_datetime(raw_xray_dt),
                xray_user= cls.get_val(row,header_map, "X-RAY-USER"),
                phs_pcs=cls.get_num(row,header_map, "PHS (PCS)") ,
                etd_pcs=cls.get_num(row,header_map, "ETD (PCS)") ,
                eds_pcs=cls.get_num(row,header_map, "EDS (PCS)") ,
                edd_pcs=cls.get_num(row, header_map,"EDD (PCS)") ,
                vck_pcs=cls.get_num(row, header_map,"VCK (PCS)") ,
                cmd_pcs=cls.get_num(row, header_map,"CMD (PCS)") ,
                
                rcs_rcf_rct_datetime=cls.parse_to_datetime(raw_rcs_rcf),
                uplifting_datetime=cls.parse_to_datetime(raw_uplifting),
                flt_no=cls.get_val(row, header_map,"FLT NO") or cls.get_val(row,header_map, "FLIGHT NO") ,
                agent_name=cls.get_val(row,header_map, "AGENT NAME") ,
                serial_no=cls.get_serial(row,header_map, "SERIAL NO") or cls.get_serial(row,header_map, "Serial No."),
                device_model_no=cls.get_val(row, header_map,"DEVICE MODEL NO") or cls.get_val(row, header_map,"Device Model No."),
                remarks=cls.get_val(row, header_map,"REMARKS") or "N/A",
                month_uploaded=target_date.strftime("%B"),
                uploaded_by=uploaded_by,
                report_date=target_date
            ))
        if db_objects:

            clean_target_date = target_date.date() if hasattr(target_date, 'date') else target_date
            # print("yyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyyy",(db_objects))
            # We clear records sharing the identical report_date timestamp 
            await db.execute(
                delete(DigitalReportImportTpXray).where(DigitalReportImportTpXray.report_date == clean_target_date)
            )
            await db.flush()
   
        db.add_all(db_objects)
        await db.commit()
        cls.print_database_save_log(db_objects, label="IMPORT DIGITAL")
        return {"status": "Success", "records_inserted": len(db_objects)}
    
    @staticmethod
    def transform_to_db_format(df: pd.DataFrame, exclude_month_token: Optional[str] = None):
       
        df = df.replace([np.nan, "NaN", "nan"], None)

       
        metadata_cols = {"Order", "Device_Model_No", "Machine_No", "Device_ID", "Month"}
        machine_pcs_cols = {}
        machine_ton_cols = {}
        for col in df.columns:
            if col in metadata_cols or "total" in col.lower():
                continue
            if col.endswith("_Pcs"):
                machine_pcs_cols[col[:-len("_Pcs")]] = col
            elif col.endswith("_Ton"):
                machine_ton_cols[col[:-len("_Ton")]] = col

        machine_bases = sorted(set(machine_pcs_cols) & set(machine_ton_cols))

        def to_num(val, as_float=False):
            if val is None:
                return 0 if as_float else 0
            try:
                cleaned = str(val).replace(',', '').strip()
                if cleaned in ("", "-"):
                    return 0 if as_float else 0
                return float(cleaned) if as_float else int(float(cleaned))
            except (ValueError, TypeError):
                return 0 if as_float else 0

        records = []
        for _, row in df.iterrows():
            raw_month = str(row.get("Month", "")).strip()
            if not raw_month or raw_month.upper() == "TOTAL":
                continue
            if exclude_month_token and raw_month.upper() == exclude_month_token.upper():
                continue

            try:
                # "JUL'26" -> date(2026, 7, 1)
                report_month = datetime.strptime(raw_month, "%b'%y").strftime("%Y-%m")
            except Exception:
                continue

            for base in machine_bases:
                pcs = to_num(row.get(machine_pcs_cols[base]))
                ton = to_num(row.get(machine_ton_cols[base]), as_float=True)

                if pcs == 0 and ton == 0:
                    # nothing reported for this machine this month — skip rather
                    # than writing a noisy zero row
                    continue

                serial = _match_serial_for_column(base) or ""
                machine_meta = XRAY_MASTER.get(serial, {})

                records.append({
                    "report_month": report_month,
                    "machine_code": serial or base[:50],
                    "machine_name": machine_meta.get("machineNo", base)[:100],
                    "pcs_count": pcs,
                    "grs_weight": ton,
                })

        return records

     
    @classmethod
    async def save_monthly_report_to_db(cls, records: list, db: AsyncSession):
        if not records:
            return {"status": "Success", "records_saved": 0}

        months = {r["report_month"] for r in records}
        codes = {r["machine_code"] for r in records}

        existing_rows = (
            await db.execute(
                select(DigitalReportXRayPerformance).where(
                    DigitalReportXRayPerformance.report_month.in_(months),
                    DigitalReportXRayPerformance.machine_code.in_(codes),
                )
            )
        ).scalars().all()
        existing_map = {
            (r.report_month, r.machine_code): r for r in existing_rows
        }

        for item in records:
            key = (item["report_month"], item["machine_code"])
            existing = existing_map.get(key)
            if existing:
                existing.pcs_count = int(item["pcs_count"])
                existing.grs_weight = float(item["grs_weight"])
                existing.machine_name = item["machine_name"]
            else:
                db.add(DigitalReportXRayPerformance(
                    report_month=item["report_month"],
                    period_type="monthly",
                    machine_code=item["machine_code"],
                    machine_name=item["machine_name"],
                    pcs_count=int(item["pcs_count"]),
                    grs_weight=float(item["grs_weight"]),
                ))

        await db.commit()
        return {"status": "Success", "records_saved": len(records)}

   
    @classmethod
    async def process_and_save_xray_performance_report(
        cls,
        file: UploadFile,
        db: AsyncSession,
        sheet_name: Optional[str] = None,
        exclude_month_token: Optional[str] = None,
    ):
        file_bytes = await file.read()
        filename = (file.filename or "").lower()

        if filename.endswith((".xlsx", ".xls")):
            xls = pd.ExcelFile(io.BytesIO(file_bytes))
            target_sheet = sheet_name or xls.sheet_names[0]
            raw = pd.read_excel(xls, sheet_name=target_sheet, header=None)
        else:
            # csv / text fallback
            text = file_bytes.decode("utf-8", errors="ignore")
            raw = pd.read_csv(io.StringIO(text), header=None)

        # Locate the row whose first cell is exactly "Month" (the Monthwise
        # Performance header), not just any row containing the token.
        header_idx = None
        for idx in range(len(raw)):
            if str(raw.iat[idx, 0]).strip().upper() == "MONTH":
                header_idx = idx
                break

        if header_idx is None:
            raise HTTPException(
                status_code=400,
                detail="Could not find the 'Monthwise Performance' table (row starting with 'Month').",
            )

        row0 = raw.iloc[header_idx].ffill().fillna("").tolist()
        row1 = raw.iloc[header_idx + 1].fillna("").tolist()

        raw_headers = []
        for r0, r1 in zip(row0, row1):
            r0_str, r1_str = str(r0).strip(), str(r1).strip()
            if r0_str == r1_str or not r1_str:
                raw_headers.append(r0_str)
            elif not r0_str:
                raw_headers.append(r1_str)
            else:
                raw_headers.append(f"{r0_str}_{r1_str}")

        combined_headers = []
        counts = {}
        for name in raw_headers:
            name = name or "Unnamed"
            if name in counts:
                counts[name] += 1
                combined_headers.append(f"{name}_{counts[name]}")
            else:
                counts[name] = 0
                combined_headers.append(name)

        body = raw.iloc[header_idx + 2:].copy()
        body.columns = combined_headers
        body = body.reset_index(drop=True)

        # Keep only real month rows like "JUL'26"
        month_regex = r"^[A-Za-z]{3}'\d{2}$"
        body = body[body['Month'].astype(str).str.strip().str.match(month_regex, na=False)].copy()

        body = body.replace(["-", r"^\s*$"], np.nan, regex=True)
        body = body.dropna(axis=1, how='all')

        records = cls.transform_to_db_format(body, exclude_month_token=exclude_month_token)
        return await cls.save_monthly_report_to_db(records, db)
 
    # ----------------- Backend data calculation-----------//
class XrayPerformanceCalculator:
   



    XRAY_MASTER = {
    "190595": {"machineNo": "No.1",           "device_model_no": "145180-2is",  "order": 1},
    "205102": {"machineNo": "No.2 (S)",       "device_model_no": "100100V-2is", "order": 2},
    "129846": {"machineNo": "No.3",           "device_model_no": "145180-2is",  "order": 3},
    "129730": {"machineNo": "No.4",           "device_model_no": "145180-2is",  "order": 4},
    "204042": {"machineNo": "No.5 (S)",       "device_model_no": "100100V-2is", "order": 5},
    "207812": {"machineNo": "No.6 (S)",       "device_model_no": "100100V-2is", "order": 6},
    "127187": {"machineNo": "No.7",           "device_model_no": "145180-2is",  "order": 7},
    "203888": {"machineNo": "No.8 (S)",       "device_model_no": "100100V-2is", "order": 8},
    "127105": {"machineNo": "No.9",           "device_model_no": "145180-2is",  "order": 9},
    "202833": {"machineNo": "No.10 (S)",      "device_model_no": "100100V-2is", "order": 10},
    "210212": {"machineNo": "No.11 (S)",      "device_model_no": "100100V-2is", "order": 11},
    "190802": {"machineNo": "No.12",          "device_model_no": "145180-2is",  "order": 12},
    "214551": {"machineNo": "No.13",          "device_model_no": "100100V-2is", "order": 13},
    "129729": {"machineNo": "No.14",          "device_model_no": "145180-2is",  "order": 14},
    "129149": {"machineNo": "No.15",          "device_model_no": "145180-2is",  "order": 15},
    "212146": {"machineNo": "No.16 (S)",      "device_model_no": "145180-2is",  "order": 16},
    "159928": {"machineNo": "No.17 (S)",      "device_model_no": "100100V-2is", "order": 17},
    "129836": {"machineNo": "No.18 (EXP TP)", "device_model_no": "145180-2is",  "order": 18},
    "204039": {"machineNo": "No.19 (IMP TP) (S)", "device_model_no": "100100V-2is", "order": 19},
    "190801": {"machineNo": "No.20 (IMP TP)", "device_model_no": "145180-2is",  "order": 20},
    "190992": {"machineNo": "No.21 (IMP TP)", "device_model_no": "145180-2is",  "order": 21},
}
    
    # ---------- shared helpers ----------
    @staticmethod
    def _get_shift_from_ist(dt_val: datetime):
        if not dt_val:
            return None
        t = dt_val.time() 
        
        # Shift M (06:00:00 IST to 13:59:59 IST)
        if dt_time(6, 0, 0) <= t <= dt_time(13, 59, 59):
            return "M"
        # Shift A (14:00:00 IST to 21:59:59 IST)
        elif dt_time(14, 0, 0) <= t <= dt_time(21, 59, 59):
            return "A"
        # Shift N (22:00:00 IST to 05:59:59 IST next morning)
        else:
            return "N"

    
    @staticmethod
    def _agg(records):
        pcs = sum(int(r["pcs"] or 0) for r in records)
        tons = round(sum(float(r["grs_wt"] or 0) for r in records) / 1000, 3)
        return pcs, (tons)
    
    @staticmethod
    def _normalize_serial(val):
        s = str(val or "").strip()
        if not s:
            return s
        try:
            return str(int(float(s)))
        except (ValueError, TypeError):
            return s

    @classmethod
    async def get_single_operational_day_report(cls, db: AsyncSession, report_date: dt_module.date):
      
        clean_date = report_date.date() if hasattr(report_date, "date") else report_date
        month_start_date = clean_date.replace(day=1)

        # Define absolute UTC limits mapping to the requested IST operational day boundary
        op_start_utc = datetime.combine(month_start_date, dt_time(0, 30)).replace(tzinfo=timezone.utc)
        op_end_utc = datetime.combine(clean_date + timedelta(days=1), dt_time(0, 29, 59)).replace(tzinfo=timezone.utc)
        # 1. Query DB using operational UTC boundaries
        res_exp_tp = await db.execute(
            select(DigitalReportExportTpXray.pcs, DigitalReportExportTpXray.grs_wt, DigitalReportExportTpXray.serial_no, DigitalReportExportTpXray.xray_end_datetime)
            .where(DigitalReportExportTpXray.xray_end_datetime.between(op_start_utc, op_end_utc))
        )
        res_imp_tp = await db.execute(
            select(DigitalReportImportTpXray.pcs, DigitalReportImportTpXray.grs_wt, DigitalReportImportTpXray.serial_no, DigitalReportImportTpXray.xray_end_datetime)
            .where(DigitalReportImportTpXray.xray_end_datetime.between(op_start_utc, op_end_utc))
        )
        res_gen = await db.execute(
            select(DigitalReportExportXray.pcs, DigitalReportExportXray.grs_wt, DigitalReportExportXray.serial_no, DigitalReportExportXray.xray_end_datetime)
            .where(DigitalReportExportXray.xray_end_datetime.between(op_start_utc, op_end_utc))
        )


        

        all_records = []
        seen_records = set()

        def parse_db_rows(rows):
            
            for r in rows:
                pcs = r[0] or 0
                grs_wt = r[1] or 0
                serial = cls._normalize_serial(r[2])
                
                utc_dt = r[3]  # This is the raw UTC timestamp from your DB
                if not utc_dt: 
                    continue
                
                # 🌟 STEP 1: Explicitly convert the DB timestamp to IST
                ist_dt = utc_dt + timedelta(hours=5, minutes=30)
                
                # # 🌟 STEP 2: Use the IST timestamp for fingerprint deduplication
                # record_key = (serial, ist_dt.isoformat(), pcs, grs_wt)
                # if record_key in seen_records:
                #     continue
                # seen_records.add(record_key)
                
                # 🌟 STEP 3: Assign the shift using the new local IST evaluator
                assigned_shift = cls._get_shift_from_ist(ist_dt)
                if ist_dt.time() < dt_time(6, 0, 0):  # Before 06:00 IST, belongs to the previous operational day
                    op_day = (ist_dt - timedelta(days=1)).date()
                else:
                    op_day = ist_dt.date()
                
                all_records.append({
                    "pcs": pcs,
                    "grs_wt": grs_wt,
                    "serial_no": serial,
                    "shift": assigned_shift,
                    "ist_datetime": ist_dt,  # Saved natively as IST for later table groupings
                    "op_day": op_day  # The operational day this record belongs to
                })
        parse_db_rows(res_exp_tp.all())
        parse_db_rows(res_imp_tp.all())
        parse_db_rows(res_gen.all())

        # Enforce exact column arrangement sorting matching layout configuration instructions
        serials_ordered = sorted(cls.XRAY_MASTER.keys(), key=lambda s: cls.XRAY_MASTER[s]["order"])

        # 2. Build Table 1: Shift Summary Data (M, A, N rows)
        shift_summary = {"M": {}, "A": {}, "N": {}, "Total": {}}
        grand_pcs_by_shift = {"M": 0, "A": 0, "N": 0, "Total": 0}
        grand_tons_by_shift = {"M": 0, "A": 0, "N": 0, "Total": 0}
        selected_day_records = [r for r in all_records if r["op_day"] == clean_date]
        

        for serial in serials_ordered:
            machine_records = [r for r in selected_day_records if r["serial_no"] == serial]
            
            for shift_key in ["M", "A", "N"]:
                shift_records = [r for r in machine_records if r["shift"] == shift_key]
                pcs, tons = cls._agg(shift_records)
                
                shift_summary[shift_key][serial] = {"pcs": pcs, "tons": round(tons)}
                grand_pcs_by_shift[shift_key] += pcs
                grand_tons_by_shift[shift_key] += tons
                
            # Aggregate row totals across the machine profile
            total_pcs, total_tons = cls._agg(machine_records)
            shift_summary["Total"][serial] = {"pcs": total_pcs, "tons": round(total_tons)}
            grand_pcs_by_shift["Total"] += total_pcs
            grand_tons_by_shift["Total"] += total_tons

        daily_matrix_rows = []
        column_totals = {s: {"pcs": 0, "tons": 0} for s in serials_ordered}
        grand_matrix_pcs = 0
        grand_matrix_tons = 0
            
        total_days = (clean_date - month_start_date).days + 1
        for d in range(total_days):
            current_loop_day = month_start_date + timedelta(days=d)
                
                # Gather all records falling into this specific operational date
            day_records = [
                r for r in all_records
                if (r["op_day"].date() if hasattr(r["op_day"], "date") else r["op_day"]) == current_loop_day
            ]
                
                
            date_matrix_row = {
                "date": current_loop_day.strftime("%Y-%m-%d"),
                "day": current_loop_day.day,
                 "machines": {}
            }
            
            row_pcs_sum = 0
            row_tons_sum = 0

            for serial in serials_ordered:
                    # Because the query is pre-filtered strictly to the operational date, 
                    # all data for this machine automatically belongs to this specific date's row.
                machine_records = [r for r in day_records if r["serial_no"] == serial]
                pcs, tons = cls._agg(machine_records)
                    
                date_matrix_row["machines"][serial] = {"pcs": pcs, "tons": round(tons)}
                row_pcs_sum += pcs
                row_tons_sum += tons

                column_totals[serial]["pcs"] += pcs
                column_totals[serial]["tons"] += tons

            date_matrix_row["total_pcs"] = row_pcs_sum
            date_matrix_row["total_tons"] = round(row_tons_sum)
            daily_matrix_rows.append(date_matrix_row)
            grand_matrix_pcs += row_pcs_sum
            grand_matrix_tons += row_tons_sum

                # Compute footer summary data
        for serial in serials_ordered:
                
            column_totals[serial]["tons"] = round(column_totals[serial]["tons"])
                

        excel_daily_matrix_rows = []
        excel_column_totals = {s: {"pcs": 0, "tons": 0} for s in serials_ordered}
        excel_grand_pcs = 0
        excel_grand_tons = 0

        next_month = (month_start_date.replace(day=28) + timedelta(days=4)).replace(day=1)
        full_month_days = (next_month - month_start_date).days

        for d in range(full_month_days):
            current_loop_day = month_start_date + timedelta(days=d)
            day_records = [
                r for r in all_records
                if (r["op_day"].date() if hasattr(r["op_day"], "date") else r["op_day"]) == current_loop_day
            ]

            row = {"date": current_loop_day.strftime("%Y-%m-%d"), "day": current_loop_day.day, "machines": {}}
            row_pcs_sum = 0
            row_tons_sum = 0

            for serial in serials_ordered:
                machine_records = [r for r in day_records if r["serial_no"] == serial]
                pcs, tons = cls._agg(machine_records)
                row["machines"][serial] = {"pcs": pcs, "tons": round(tons)}
                row_pcs_sum += pcs
                row_tons_sum += tons
                excel_column_totals[serial]["pcs"] += pcs
                excel_column_totals[serial]["tons"] += tons

            row["total_pcs"] = row_pcs_sum
            row["total_tons"] = round(row_tons_sum)
            excel_daily_matrix_rows.append(row)
            excel_grand_pcs += row_pcs_sum
            excel_grand_tons += row_tons_sum

        for serial in serials_ordered:
            excel_column_totals[serial]["tons"] = round(excel_column_totals[serial]["tons"])

        return {
            "machines": [
                {"serial_no": s, "machineNo": cls.XRAY_MASTER[s]["machineNo"], "device_model_no": cls.XRAY_MASTER[s]["device_model_no"]}
                for s in serials_ordered
            ],
            "shift_summary": {
                "rows": shift_summary,
                "grand_totals": {
                    k: {"pcs": grand_pcs_by_shift[k], "tons": round(grand_tons_by_shift[k])}
                    for k in ["M", "A", "N", "Total"]
                },
            },
            "daily_matrix": {
                "rows": daily_matrix_rows,
                "column_totals": column_totals,
                "grand_total": {"pcs": grand_matrix_pcs, "tons": round(grand_matrix_tons)},
            },
            "excel_daily_matrix": {
                "rows": excel_daily_matrix_rows,
                "column_totals": excel_column_totals,
                "grand_total": {"pcs": excel_grand_pcs, "tons": round(excel_grand_tons)},
            },
        }

    
    
    # ----------------- Full 3-table report matching the reference MIS Excel -----------//
    @staticmethod
    def _get_operational_date_from_utc(utc_dt: datetime):
        if not utc_dt:
            return None
        ist_dt = utc_dt + timedelta(hours=5, minutes=30)
        if ist_dt.time() >= dt_time(6, 0):
            return ist_dt.date()
        return ist_dt.date() - timedelta(days=1)

    

    @classmethod
    async def get_full_report(cls, db: AsyncSession, selected_date: dt_module.date):


       
        clean_date = selected_date.date() if hasattr(selected_date, "date") else selected_date
        year = clean_date.year
        month = clean_date.month
        days_in_month = monthrange(year, month)[1]

        # Pad 1 day either side of the calendar year so records that spill across the
        # Jan 1 / Dec 31 operational-day boundary still get captured before bucketing.
        db_start_utc = datetime.combine(clean_date, dt_time(0, 30, 0))
        db_end_utc = datetime.combine(clean_date + timedelta(days=1), dt_time(0, 29, 59))
        res_exp_tp = await db.execute(
            select(DigitalReportExportTpXray.pcs, DigitalReportExportTpXray.grs_wt,
                   DigitalReportExportTpXray.serial_no, DigitalReportExportTpXray.xray_end_datetime)
            .where(DigitalReportExportTpXray.xray_end_datetime.between(db_start_utc, db_end_utc))        )
        res_imp_tp = await db.execute(
            select(DigitalReportImportTpXray.pcs, DigitalReportImportTpXray.grs_wt,
                   DigitalReportImportTpXray.serial_no, DigitalReportImportTpXray.xray_end_datetime)
            .where(DigitalReportExportTpXray.xray_end_datetime.between(db_start_utc, db_end_utc))        )
        res_gen = await db.execute(
            select(DigitalReportExportXray.pcs, DigitalReportExportXray.grs_wt,
                   DigitalReportExportXray.serial_no, DigitalReportExportXray.xray_end_datetime)
            .where(DigitalReportExportTpXray.xray_end_datetime.between(db_start_utc, db_end_utc))        )

        # agg[(op_date, serial_no, shift)] = {"pcs": int, "grs_wt": float}  (grs_wt stays in kg here)
        agg = defaultdict(lambda: {"pcs": 0, "grs_wt": 0})

        def bucket_rows(rows):
            for pcs, grs_wt, serial_no, xray_end_dt in rows:
                if not xray_end_dt:
                    continue
                op_date = cls._get_operational_date_from_utc(xray_end_dt)
                if not op_date:
                    continue
                serial = cls._normalize_serial(serial_no)
                ist_dt = xray_end_dt + timedelta(hours=5, minutes=30)
                shift = cls._get_shift_from_ist(ist_dt)
                key = (op_date, serial, shift)
                agg[key]["pcs"] += int(pcs or 0)
                agg[key]["grs_wt"] += float(grs_wt or 0)

        bucket_rows(res_exp_tp.all())
        bucket_rows(res_imp_tp.all())
        bucket_rows(res_gen.all())

        def cell(op_date, serial, shifts=("M", "A", "N")):
            """Sums pcs/tons for one machine on one date across the given shifts."""
            pcs_total = 0
            wt_total = 0
            for sh in shifts:
                bucket = agg.get((op_date, serial, sh))
                if bucket:
                    pcs_total += bucket["pcs"]
                    wt_total += bucket["grs_wt"]
            return pcs_total, round(wt_total / 1000, 3)

        serials_ordered = sorted(cls.XRAY_MASTER.keys(), key=lambda s: cls.XRAY_MASTER[s]["order"])
        machines = [
            {"serial_no": s, "machineNo": cls.XRAY_MASTER[s]["machineNo"], "device_model_no": cls.XRAY_MASTER[s]["device_model_no"]}
            for s in serials_ordered
        ]

        # ---------- Table 1: Shift summary for the single selected day ----------
        shift_rows = {"M": {}, "A": {}, "N": {}, "Total": {}}
        shift_grand_pcs = {"M": 0, "A": 0, "N": 0, "Total": 0}
        shift_grand_tons = {"M": 0, "A": 0, "N": 0, "Total": 0}

        for serial in serials_ordered:
            for shift_key in ["M", "A", "N"]:
                pcs, tons = cell(clean_date, serial, shifts=(shift_key,))
                shift_rows[shift_key][serial] = {"pcs": pcs, "tons": round(tons)}
                shift_grand_pcs[shift_key] += pcs
                shift_grand_tons[shift_key] += tons
            total_pcs, total_tons = cell(clean_date, serial)
            shift_rows["Total"][serial] = {"pcs": total_pcs, "tons": round(total_tons)  }
            shift_grand_pcs["Total"] += total_pcs
            shift_grand_tons["Total"] += total_tons

        shift_summary = {
            "date": clean_date.strftime("%Y-%m-%d"),
            "rows": shift_rows,
            "grand_totals": {
                k: {"pcs": shift_grand_pcs[k], "tons": round(shift_grand_tons[k])}
                for k in ["M", "A", "N", "Total"]
            },
        }

        # ---------- Table 2: Datewise performance for the whole month ----------
        datewise_rows = []
        month_col_totals = {s: {"pcs": 0, "tons": 0} for s in serials_ordered}
        month_grand_pcs = 0
        month_grand_tons = 0

        for day_num in range(1, days_in_month + 1):
            this_day = dt_module.date(year, month, day_num)
            row_machines = {}
            row_pcs_sum = 0
            row_tons_sum = 0
            for serial in serials_ordered:
                pcs, tons = cell(this_day, serial)
                row_machines[serial] = {"pcs": pcs, "tons": tons}
                row_pcs_sum += pcs
                row_tons_sum += tons
                month_col_totals[serial]["pcs"] += pcs
                month_col_totals[serial]["tons"] += tons

            datewise_rows.append({
                "date": this_day.strftime("%Y-%m-%d"),
                "day": day_num,
                "machines": row_machines,
                "total_pcs": row_pcs_sum,
                "total_tons": round(row_tons_sum, 3),
            })
            month_grand_pcs += row_pcs_sum
            month_grand_tons += row_tons_sum

        for s in serials_ordered:
            month_col_totals[s]["tons"] = round(month_col_totals[s]["tons"])

        datewise_month = {
            "month_label": clean_date.strftime("%b-%y").upper(),
            "rows": datewise_rows,
            "column_totals": month_col_totals,
            "grand_total": {"pcs": month_grand_pcs, "tons": round(month_grand_tons)},
        }

        # ---------- Table 3: Monthwise performance for the whole year ----------
        monthwise_rows = []
        year_col_totals = {s: {"pcs": 0, "tons": 0} for s in serials_ordered}
        year_grand_pcs = 0
        year_grand_tons = 0

        for month_num in range(1, 13):
            days_in_this_month = monthrange(year, month_num)[1]
            row_machines = {}
            row_pcs_sum = 0
            row_tons_sum = 0
            for serial in serials_ordered:
                pcs_total = 0
                tons_total = 0
                for day_num in range(1, days_in_this_month + 1):
                    pcs, tons = cell(dt_module.date(year, month_num, day_num), serial)
                    pcs_total += pcs
                    tons_total += tons
                row_machines[serial] = {"pcs": pcs_total, "tons": round(tons_total)}
                row_pcs_sum += pcs_total
                row_tons_sum += tons_total
                year_col_totals[serial]["pcs"] += pcs_total
                year_col_totals[serial]["tons"] += tons_total

            monthwise_rows.append({
                "month": dt_module.date(year, month_num, 1).strftime("%b-%y").upper(),
                "month_num": month_num,
                "machines": row_machines,
                "total_pcs": row_pcs_sum,
                "total_tons": round(row_tons_sum),
            })
            year_grand_pcs += row_pcs_sum
            year_grand_tons += row_tons_sum

        for s in serials_ordered:
            year_col_totals[s]["tons"] = round(year_col_totals[s]["tons"])

        monthwise_year = {
            "year_label": str(year),
            "rows": monthwise_rows,
            "column_totals": year_col_totals,
            "grand_total": {"pcs": year_grand_pcs, "tons": round(year_grand_tons)},
        }

        return {
            "machines": machines,
            "shift_summary": shift_summary,
            "datewise_month": datewise_month,
            "monthwise_year": monthwise_year,
        }
    
    
    