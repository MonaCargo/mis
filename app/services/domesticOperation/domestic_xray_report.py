# services/domestic_xray_service.py
import asyncio
from fastapi import BackgroundTasks
import os, base64, msal, requests
import re
import time
from sqlalchemy.orm import Session
from sqlalchemy import and_, or_, func, select, update, delete
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException, UploadFile
from typing import Optional, List
from datetime import datetime, date, timedelta, timezone ,time as dt_time
import pandas as pd
from app.db.models.domesticOperation.domestic_xray_report import DomesticXrayEmployee

from app.db.models.domesticOperation.domestic_xray_report import DomesticXray
from app.schemas.domesticOperation.domestic_xray_report import (
    DomesticXrayCreate,
    DomesticXrayUpdate,
    DomesticXrayFilterParams,
    EmployeeCreate,
    EmployeeResponse,
    PdfGenerateStatusUpdate,
    EmailStatusUpdate
)
from app.utils.common.helperFunction import get_utc_now
from app.utils.domesticOperation.generate_security_pdf import generate_security_pdf, transform_backend_payload
from app.utils.domesticOperation.xray_report_cleaner import DomesticXrayDataCleaner
from dotenv import load_dotenv


RECIPIENT_098 = "dcsc.developer@cscindia.in" 
RECIPIENT_775 = "dcsc.developer@cscindia.in"
VIKASH_EMAIL = "vikas.kanodia@cscindia.in"


load_dotenv()
def get_env_variable(name: str) -> str:
    """Get environment variable or raise error if missing."""
    value = os.getenv(name)
    if not value:
        raise EnvironmentError(f"Missing environment variable: {name}")
    return value

TENANT_ID = get_env_variable("TENANT_ID")
CLIENT_ID = get_env_variable("CLIENT_ID")
CLIENT_SECRET = get_env_variable("CLIENT_SECRET")
SENDER_EMAIL = get_env_variable("SENDER_EMAIL")

print(f"TENANT_ID: {TENANT_ID} CLIENT_ID: {CLIENT_ID} SENDER_EMAIL: {SENDER_EMAIL} cLIENT_SECRET: {CLIENT_SECRET}")

# Helper functions for safe type conversion
def safe_int(value):
    """Safely convert value to int, return None if invalid"""
    try:
        if value is None or str(value).strip() == "":
            return None
        return int(value)
    except (ValueError, TypeError, AttributeError):
        return None

def safe_float(value):
    """Safely convert value to float, return None if invalid"""
    try:
        if value is None or str(value).strip() == "":
            return None
        return float(value)
    except (ValueError, TypeError, AttributeError):
        return None

def safe_str(value):
    """Safely convert value to string, return None if invalid"""
    try:
        if value is None or str(value).strip() == "":
            return None
        return str(value).strip()
    except (TypeError, AttributeError):
        return None

# def safe_datetime(value):
#     """Safely convert value to timezone-aware datetime, return None if invalid"""
#     try:
#         if value is None or pd.isna(value):
#             return None
#         # Convert pandas Timestamp to Python datetime
#         dt = value.to_pydatetime() if isinstance(value, pd.Timestamp) else value
#         # Ensure timezone-aware (UTC)
#         return dt.replace(tzinfo=timezone.utc) if dt.tzinfo is None else dt
#     except (ValueError, TypeError, AttributeError):
#         return None

def safe_datetime(value):
    """Safely convert value to timezone-aware datetime, return None if invalid"""
    try:
        if value is None or pd.isna(value):
            return None
        
        # Convert pandas Timestamp to Python datetime
        dt = value.to_pydatetime() if isinstance(value, pd.Timestamp) else value
        
        # If already timezone-aware, return as-is (already in IST from cleaner)
        if dt.tzinfo is not None:
            return dt
        
        # If somehow naive, assume IST and localize
        from pytz import timezone as pytz_timezone
        ist = pytz_timezone('Asia/Kolkata')
        return ist.localize(dt)
        
    except (ValueError, TypeError, AttributeError):
        return None

def safe_time(value):
    """Safely convert value to time, return None if invalid"""
    try:
        if value is None or pd.isna(value):
            return None
        
        # If it's already a time object, return it
        if isinstance(value, dt_time):
            return value
        
        # If it's a string like 'nan' or empty
        if isinstance(value, str):
            value_str = value.strip().lower()
            if value_str in ['', 'nan', 'nat', 'none']:
                return None
        
        # If it's a pandas Timestamp
        if isinstance(value, pd.Timestamp):
            return value.to_pydatetime().time()
        
        # If it's a datetime object
        if isinstance(value, datetime):
            return value.time()
        
        # Try to parse as time
        parsed = pd.to_datetime(str(value), errors="coerce")
        if pd.notna(parsed):
            return parsed.time()
        
        return None
        
    except (ValueError, TypeError, AttributeError):
        return None

def to_python_type(value):
    """Convert numpy types to Python native types"""
    import numpy as np
    if isinstance(value, (np.integer, np.int64)):
        return int(value)
    if isinstance(value, (np.floating, np.float64)):
        return float(value)
    if isinstance(value, np.bool_):
        return bool(value)
    if pd.isna(value):
        return None
    return value


class DomesticXrayService:
    """Service layer for Domestic X-ray operations"""
    
    @staticmethod
    async def upload_and_process_file(
        db: AsyncSession,
        file: UploadFile,
        uploaded_by: str,
    ) -> dict:
        """
        Upload and process domestic x-ray file with duplicate detection and sequential numbering.
        
        Args:
            db: Async database session
            file: Uploaded file
            uploaded_by: Username of uploader
            
        Returns:
            Dictionary with upload results and statistics
        """
        # Clean and validate file
        df_cleaned, stats = await DomesticXrayDataCleaner.clean_and_validate(file)
        
        # Extract all AWB numbers from the file (only valid ones)
        file_awbs = [
            row.get('awb_no') 
            for _, row in df_cleaned.iterrows() 
            if row.get('awb_no') and pd.notna(row.get('awb_no'))
        ]
        
        # Batch check: Query only AWBs that are in current file (optimized for large tables)
        existing_awbs_set = set()
        if file_awbs:
            result = await db.execute(
                select(DomesticXray.awb_no).where(DomesticXray.awb_no.in_(file_awbs))
            )
            existing_awbs_set = set(result.scalars().all())
        
        # Get the last sequential number from database
        last_seq_result = await db.execute(
            select(DomesticXray.seq_num)
            .where(DomesticXray.seq_num.like('D%'))
            .order_by(DomesticXray.seq_num.desc())
            .limit(1)
        )
        last_seq = last_seq_result.scalar_one_or_none()
        
        # Initialize counter
        if last_seq:
            # Extract numeric part and increment (e.g., "D0000123" -> 123 -> 124)
            try:
                last_number = int(last_seq[1:])  # Remove 'D' prefix
                current_seq_number = last_number + 1
            except (ValueError, IndexError):
                current_seq_number = 1
        else:
            current_seq_number = 1
        
        # Prepare records for bulk insert
        records_to_insert = []
        invalid_count = 0
        duplicate_count = 0
        intra_file_duplicates = set()
        
        for _, row in df_cleaned.iterrows():
            try:
                awb = row.get('awb_no')
                
                # Skip if AWB number is missing
                if not awb or pd.isna(awb):
                    invalid_count += 1
                    continue
                
                # Skip if AWB already exists in database or file
                if awb in existing_awbs_set or awb in intra_file_duplicates:
                    duplicate_count += 1
                    continue
                
                # Generate sequential number (7 digits with 'D' prefix)
                seq_num = f"D{current_seq_number:07d}"
                
                # Create record with safe type conversions
                record_data = {
                    "seq_num": seq_num,  # Add sequential number
                    "awb_no": awb,
                    "destination": safe_str(row.get("destination")),
                    "accp_date": safe_datetime(row.get("accp_date")),
                    "merge_acceptance_date_time": safe_datetime(row.get("merge_acceptance_date_time")),
                    "accp_time": safe_time(row.get("accp_time")),
                    "accp_pcs": safe_int(row.get("accp_pcs")),
                    "rej_pcs": safe_int(row.get("rej_pcs")),
                    "gross_weight": safe_float(row.get("gross_weight")),
                    "rej_gross_weight": safe_float(row.get("rej_gross_weight")),
                    "chg_weight": safe_float(row.get("chg_weight")),
                    "shc": safe_str(row.get("shc")),
                    "name_of_goods": safe_str(row.get("name_of_goods")),
                    "agent_name": safe_str(row.get("agent_name")),
                    "freighter_type": safe_str(row.get("freighter_type")),
                    "xray_type": safe_str(row.get("xray_type")),
                    "phs_pcs": safe_int(row.get("phs_pcs")),
                    "etd_pcs": safe_int(row.get("etd_pcs")),
                    "eds_pcs": safe_int(row.get("eds_pcs")),
                    "edd_pcs": safe_int(row.get("edd_pcs")),
                    "vck_pcs": safe_int(row.get("vck_pcs")),
                    "cmd_pcs": safe_int(row.get("cmd_pcs")),
                    "xray_date_time": safe_datetime(row.get("xray_date_time")),
                    "xray_user": safe_str(row.get("xray_user")),
                    "serial_no": safe_str(row.get("serial_no")),
                    "remarks": safe_str(row.get("remarks")),
                    "uploaded_by": uploaded_by,
                    "is_pdf_generated": False,
                    "is_email_sent": False,
                    "created_at": get_utc_now(),
                    "updated_at": get_utc_now()
                }
                
                records_to_insert.append(DomesticXray(**record_data))
                intra_file_duplicates.add(awb)
                
                # Increment counter for next record
                current_seq_number += 1
                
            except Exception as e:
                print(f"Error processing row: {e}")
                invalid_count += 1
                continue
        
        # Bulk insert with error handling
        inserted_count = 0
        if records_to_insert:
            try:
                db.add_all(records_to_insert)
                await db.commit()
                inserted_count = len(records_to_insert)
            except Exception as e:
                await db.rollback()
                raise HTTPException(
                    status_code=500,
                    detail=f"Error inserting records: {str(e)}"
                )
        
        # Convert numpy types to Python types for JSON serialization
        clean_stats = {k: to_python_type(v) for k, v in stats.items()}
        
        return {
            'success': True,
            'message': f'Successfully uploaded {inserted_count} records. Skipped {duplicate_count} duplicates and {invalid_count} invalid records.',
            'total_records': len(df_cleaned),
            'valid_records': inserted_count,
            'invalid_records': invalid_count,
            'duplicate_records': duplicate_count,
            'seq_num_range': {
                'start': f"D{current_seq_number - inserted_count:07d}" if inserted_count > 0 else None,
                'end': f"D{current_seq_number - 1:07d}" if inserted_count > 0 else None
            },
            'statistics': clean_stats,
            'upload_details': {
                'file_name': file.filename,
                'uploaded_by': uploaded_by,
                'upload_timestamp': datetime.now(timezone.utc).isoformat()
            }
        }


    @staticmethod
    async def fetch_pending_records(db: AsyncSession, start_date: datetime, end_date: datetime) -> List[DomesticXray]:
        """
        Fetch records in date range where PDF and email are not yet generated/sent.
        """

        # Make end_date inclusive by adding 1 day 
        end_date_inclusive = end_date + timedelta(days=1)
        stmt = (
            select(DomesticXray)
            .where(
                DomesticXray.xray_date_time.between(start_date, end_date_inclusive),
                # DomesticXray.is_pdf_generated == False,
                DomesticXray.is_email_sent == False
            )
        )
        result = await db.execute(stmt)
        return result.scalars().all()




    @staticmethod
    async def generate_and_save_pdf(record: DomesticXray, db: AsyncSession) -> dict:
        try:
            start_time = time.perf_counter()

            # Build payload from DB record
            payload = {
                "awb_no": record.awb_no,
                "doc_no": record.seq_num,
                "xray_user": record.xray_user,
                "destination": record.destination,
                "name_of_goods": record.name_of_goods,
                "remarks": record.remarks,
                "xray_type": record.xray_type,
                "xray_date_time": record.xray_date_time,
                "seq_num": record.seq_num,
                "serial_no": record.serial_no,
            }

            user_id = record.xray_user
            employee_id = None
            if user_id:
                res = await DomesticXrayService.get_domestic_employee_by_user_id(db=db, user_id=user_id)
                employee_id = res.employee_id if res else None

            print("payload ===================", payload)

            data = transform_backend_payload(payload, employee_id)
            print("transformed data ===================", data)

            pdf_path = generate_security_pdf(data)
            print(f"Generated PDF at: {pdf_path}")

            elapsed = time.perf_counter() - start_time
            print(f"PDF processing took {elapsed:.2f} seconds")

            awb = data["awb_no"].replace("-", "") if "-" in data["awb_no"] else data["awb_no"]

            stmt = (
                update(DomesticXray)
                .where(and_(DomesticXray.awb_no == awb, DomesticXray.seq_num == data["doc_no"]))
                .values(
                    is_pdf_generated=True,
                    pdf_generated_date_time=get_utc_now(),
                    updated_at=get_utc_now()
                )
            )
            await db.execute(stmt)
            await db.commit()

            return {
                "success": True,
                "message": "PDF generated successfully",
                "pdf_path": pdf_path,
                "awb_no": data["awb_no"],
                "doc_no": data["doc_no"],
                "employee_id": data.get("employee_id")
            }
        except Exception as e:
            return {"success": False, "message": f"PDF generation failed: {str(e)}"}


    
    @staticmethod
    async def background_send_email(db: AsyncSession, awb_no: str, doc_no: str, pdf_path: str):
        """
        Background task: send email with retry, update DB, delete PDF.
        Handles success, API errors, and Python exceptions.
        """

        max_retries = 3
        base_delay = 2  # Seconds

        awb_no_clean = awb_no.replace("-", "") if "-" in awb_no else awb_no

        for attempt in range(1, max_retries + 1):
            start_time = time.perf_counter()
            try:
                print(f"Attempt {attempt}: Sending email for AWB {awb_no}")

                # Acquire token
                authority = f"https://login.microsoftonline.com/{TENANT_ID}"
                app = msal.ConfidentialClientApplication(
                    CLIENT_ID,
                    authority=authority,
                    client_credential=CLIENT_SECRET
                )
                token_response = app.acquire_token_for_client(scopes=["https://graph.microsoft.com/.default"])
                if "access_token" not in token_response:
                    raise Exception("Failed to acquire Graph API token")
                access_token = token_response["access_token"]

                # Recipient logic
                if awb_no_clean.startswith("098"):
                    recipient_email = RECIPIENT_098
                    receipient_name = "Air India Cargo"

                elif awb_no_clean.startswith("775"):
                    recipient_email = RECIPIENT_775
                    receipient_name = "SpiceJet Cargo"

                # else:
                #     recipient_email = "dcsc.developer@cscindia.in"

                pdf_path = os.path.join("static", "pdfs", f"{awb_no}.pdf")
                print(f"Sending email to {recipient_email} for AWB {awb_no} pdf path {pdf_path}")

                # Read PDF
                if not os.path.exists(pdf_path):
                    raise FileNotFoundError(f"PDF not found: {pdf_path}")
                with open(pdf_path, "rb") as f:
                    pdf_content = base64.b64encode(f.read()).decode("utf-8")

                # Send email
                endpoint = f"https://graph.microsoft.com/v1.0/users/{SENDER_EMAIL}/sendMail"
                email_data = {
                    "message": {
                        "subject": f"CSD for AWB {awb_no}",
                        "body": {
                            "contentType": "HTML",                                                                  
                            "content": (
                                f"Dear {receipient_name},<br><br>"
                                f"Please find the attached Consignment Security Declaration (CSD) for AWB {awb_no}.<br><br>"
                                f"Regards,<br>DCSC-Security"
                            )
                        },
                        "toRecipients": [{"emailAddress": {"address": recipient_email}}],
                        "ccRecipients": [{"emailAddress": {"address": VIKASH_EMAIL}}],
                        "attachments": [{
                            "@odata.type": "#microsoft.graph.fileAttachment",
                            "name": os.path.basename(pdf_path),
                            "contentType": "application/pdf",
                            "contentBytes": pdf_content
                        }]  
                    },
                    "saveToSentItems": "true"
                }
                headers = {"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"}

                response = requests.post(endpoint, json=email_data, headers=headers)
                print(f"Email send response status: {response.status_code}, body: {response.text}")

                # ✅ Success
                if response.status_code == 202:
                    stmt = (
                        update(DomesticXray)
                        .where(and_(DomesticXray.awb_no == awb_no_clean, DomesticXray.seq_num == doc_no))
                        .values(
                            is_email_sent=True,
                            email_sent_date_time=datetime.utcnow(),
                            retry_count=attempt,
                            email_error_message=None,
                            updated_at=datetime.utcnow()
                        )
                    )
                    await db.execute(stmt)
                    await db.commit()

                    try:
                        os.remove(pdf_path)
                        print(f"Deleted PDF: {pdf_path}")
                    except Exception as e:
                        print(f"Failed to delete PDF: {e}")

                    elapsed = time.perf_counter() - start_time
                    print(f"✅ Email processing took {elapsed:.2f} seconds")
                    return  # Exit after success

                # ❌ API error (non-202 response)
                else:
                    try:
                        error_json = response.json()
                        error_core = error_json.get("error", {})
                        error_code = error_core.get("code", "UnknownError")
                        error_message = error_core.get("message", response.text)
                        error_msg = f"{error_code}: {error_message}"
                    except Exception:
                        error_msg = f"Graph API error {response.status_code}"

                    stmt = (
                        update(DomesticXray)
                        .where(and_(DomesticXray.awb_no == awb_no_clean, DomesticXray.seq_num == doc_no))
                        .values(
                            is_email_sent=False,
                            retry_count=attempt,
                            email_error_message=error_msg,
                            updated_at=datetime.utcnow()
                        )
                    )
                    await db.execute(stmt)
                    await db.commit()
                    print(f"❌ {error_msg}")

            except Exception as e:
                # ❌ Python exception (network, file, etc.)
                print(f"❌ Attempt {attempt} failed: {e}")
                stmt = (
                    update(DomesticXray)
                    .where(and_(DomesticXray.awb_no == awb_no_clean, DomesticXray.seq_num == doc_no))
                    .values(
                        is_email_sent=False,
                        retry_count=attempt,
                        email_error_message=str(e),
                        updated_at=datetime.utcnow()
                    )
                )
                await db.execute(stmt)
                await db.commit()

            # Retry logic
            if attempt < max_retries:
                await asyncio.sleep(base_delay * attempt)  # exponential backoff
            else:
                print(f"❌ Email permanently failed for AWB {awb_no} after {max_retries} attempts")

    @staticmethod    
    async def search_domestic_xray(
        db: AsyncSession,
        search_type: str,
        search_value: str,
    ):
        """
        Domestic XRAY search:
        Allowed search keys:
        - awb_no
        - seq_num
        """

        # ----------------------------------------------------
        # Allowed searchable fields (STRICT)
        # ----------------------------------------------------
        search_fields = {
            "awb_no": DomesticXray.awb_no,
            "seq_num": DomesticXray.seq_num,
        }

        if search_type not in search_fields:
            return []

        column = search_fields[search_type]

        # ----------------------------------------------------
        # Query
        # ----------------------------------------------------
        stmt = (
            select(DomesticXray)
            .where(column == search_value)
            .order_by(DomesticXray.xray_date_time.desc())
        )

        result = await db.execute(stmt)
        rows = result.scalars().all()

        # ----------------------------------------------------
        # Convert model → dict (generic, safe)
        # ----------------------------------------------------
        def model_to_dict(obj):
            return {
                column.name: getattr(obj, column.name)
                for column in obj.__table__.columns
            }

        # return [model_to_dict(row) for row in rows]
        # from datetime import datetime, date, time
        # def model_to_dict(obj):
        #     result = {}
        #     for column in obj.__table__.columns:
        #         value = getattr(obj, column.name)

        #         # Serialize datetime/time/date objects to string
        #         if isinstance(value, datetime):
        #             result[column.name] = value.isoformat()  # "2026-01-15T11:13:27.444531"
        #         elif isinstance(value, date):
        #             result[column.name] = value.isoformat()  # "2026-01-15"
        #         elif isinstance(value, time):
        #             result[column.name] = value.strftime("%H:%M:%S")  # "00:59:00"
        #         else:
        #             result[column.name] = value

        #     return result
        
        return [model_to_dict(row) for row in rows]



    @staticmethod
    async def get_by_id(db: AsyncSession, record_id: int) -> Optional[DomesticXray]:
        """Get domestic x-ray record by ID"""
        result = await db.execute(
            select(DomesticXray).where(DomesticXray.id == record_id)
        )
        return result.scalar_one_or_none()
    
    @staticmethod
    async def get_by_awb(db: AsyncSession, awb_no: str) -> List[DomesticXray]:
        """Get all records for a specific AWB number"""
        result = await db.execute(
            select(DomesticXray).where(DomesticXray.awb_no == awb_no)
        )
        return result.scalars().all()
    

    @staticmethod
    async def get_filtered_records(
        db: AsyncSession,
        # filters: DomesticXrayFilterParams,
        xray_filter_status: Optional[str],
        start_date: Optional[date],
        end_date: Optional[date],
        page: int ,
        page_size: int 
    ) -> tuple[List[DomesticXray], int]:
        """
        Get filtered and paginated records.
        
        Returns:
            Tuple of (records list, total count)
        """
        # Build base query
        query = select(DomesticXray)
        count_query = select(func.count()).select_from(DomesticXray)
        
        # Apply filters
        conditions = []
        
        # if filters.awb_no:
        #     conditions.append(DomesticXray.awb_no.like(f"%{filters.awb_no}%"))
        
        # if filters.destination:
        #     conditions.append(DomesticXray.destination == filters.destination)
        
        # if filters.agent_name:
        #     conditions.append(DomesticXray.agent_name.like(f"%{filters.agent_name}%"))
        
        # if filters.xray_type:
        #     conditions.append(DomesticXray.xray_type == filters.xray_type)
        
        # if filters.uploaded_by:
        #     conditions.append(DomesticXray.uploaded_by == filters.uploaded_by)
        
        # if filters.is_pdf_generated is not None:
        #     conditions.append(DomesticXray.is_pdf_generated == filters.is_pdf_generated)
        
        # if filters.is_email_sent is not None:
        #     conditions.append(DomesticXray.is_email_sent == filters.is_email_sent)
        
        # if filters.start_date:
        #     start_datetime = datetime.combine(filters.start_date, datetime.min.time(), tzinfo=timezone.utc)
        #     conditions.append(DomesticXray.created_at >= start_datetime)
        
        # if filters.end_date:
        #     end_datetime = datetime.combine(filters.end_date, datetime.max.time(), tzinfo=timezone.utc)
        #     conditions.append(DomesticXray.created_at <= end_datetime)

        # if start_date:
        #     start_dt = datetime.combine(
        #         start_date, datetime.min.time(), tzinfo=timezone.utc
        #     )
        #     conditions.append(DomesticXray.xray_date_time >= start_dt)

        # if end_date:
        #     end_dt = datetime.combine(
        #         end_date, datetime.max.time(), tzinfo=timezone.utc
        #     )
        #     conditions.append(DomesticXray.xray_date_time <= end_dt)

        if start_date:
            conditions.append(DomesticXray.xray_date_time >= start_date)

        if end_date:
            conditions.append(DomesticXray.xray_date_time <= end_date)


        if xray_filter_status and xray_filter_status != "all":

            if xray_filter_status == "pdf_generated_email_not_send":
                conditions.append(DomesticXray.is_pdf_generated.is_(True))
                conditions.append(DomesticXray.is_email_sent.is_(False))

            elif xray_filter_status == "pdf_generated_email_send":
                conditions.append(DomesticXray.is_pdf_generated.is_(True))
                conditions.append(DomesticXray.is_email_sent.is_(True))

            elif xray_filter_status == "email_send":
                conditions.append(DomesticXray.is_email_sent.is_(True))
                
            elif xray_filter_status == "email_not_send":
                conditions.append(DomesticXray.is_email_sent.is_(False))

            else:
                raise HTTPException(
                    status_code=400,
                    detail=f"Invalid xray_filter_status: {xray_filter_status}"
                )
        # Apply conditions to both queries
        if conditions:
            query = query.where(and_(*conditions))
            count_query = count_query.where(and_(*conditions))
        
        # Get total count
        total_result = await db.execute(count_query)
        total = total_result.scalar() or 0
        offset = (page - 1) * page_size
        
        
        # Apply ordering and pagination
        query = query.order_by(DomesticXray.xray_date_time.desc()).offset(offset).limit(page_size)
        
        # Execute query
        result = await db.execute(query)
        records = result.scalars().all()

        import math
        print("\n=== Checking for NaN values ===")
        for idx, record in enumerate(records):
            for column in record.__table__.columns:
                value = getattr(record, column.name)
                if isinstance(value, float) and math.isnan(value):
                    print(f"⚠️ NaN FOUND!")
                    print(f"   Record Index: {idx}")
                    print(f"   Record ID: {record.id if hasattr(record, 'id') else 'N/A'}")
                    print(f"   AWB No: {record.awb_no if hasattr(record, 'awb_no') else 'N/A'}")
                    print(f"   Column: {column.name}")
                    print(f"   Value: {value}")
                    print("-" * 50)
    # ===================================
        
        return list(records), total
    


    @staticmethod
    async def update_record(
        db: AsyncSession,
        record_id: int,
        update_data: DomesticXrayUpdate
    ) -> Optional[DomesticXray]:
        """Update a domestic x-ray record"""
        record = await DomesticXrayService.get_by_id(db, record_id)
        
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        
        # Update fields
        update_dict = update_data.model_dump(exclude_unset=True)
        update_dict['updated_at'] = get_utc_now()
        
        for field, value in update_dict.items():
            setattr(record, field, value)
        
        await db.commit()
        await db.refresh(record)
        return record
    
    @staticmethod
    async def update_pdf_status(
        db: AsyncSession,
        record_ids: List[int],
        status_update: PdfGenerateStatusUpdate
    ) -> dict:
        """Update PDF generation status for multiple records"""
        if status_update.pdf_generated_date_time is None:
            status_update.pdf_generated_date_time = get_utc_now()
        
        stmt = (
            update(DomesticXray)
            .where(DomesticXray.id.in_(record_ids))
            .values(
                is_pdf_generated=status_update.is_pdf_generated,
                pdf_generated_date_time=status_update.pdf_generated_date_time,
                updated_at=get_utc_now()
            )
        )
        
        result = await db.execute(stmt)
        await db.commit()
        
        return {
            'success': True,
            'message': f'Updated PDF status for {result.rowcount} records',
            'affected_count': result.rowcount
        }
    
    @staticmethod
    async def update_email_status(
        db: AsyncSession,
        record_ids: List[int],
        status_update: EmailStatusUpdate
    ) -> dict:
        """Update email status for multiple records"""
        if status_update.email_sent_date_time is None:
            status_update.email_sent_date_time = get_utc_now()
        
        stmt = (
            update(DomesticXray)
            .where(DomesticXray.id.in_(record_ids))
            .values(
                is_email_sent=status_update.is_email_sent,
                email_sent_date_time=status_update.email_sent_date_time,
                updated_at=get_utc_now()
            )
        )
        
        result = await db.execute(stmt)
        await db.commit()
        
        return {
            'success': True,
            'message': f'Updated email status for {result.rowcount} records',
            'affected_count': result.rowcount
        }
    
    @staticmethod
    async def delete_record(db: AsyncSession, record_id: int) -> bool:
        """Delete a domestic x-ray record"""
        record = await DomesticXrayService.get_by_id(db, record_id)
        
        if not record:
            raise HTTPException(status_code=404, detail="Record not found")
        
        await db.delete(record)
        await db.commit()
        return True
    
    @staticmethod
    async def bulk_delete_records(db: AsyncSession, record_ids: List[int]) -> dict:
        """Delete multiple records by IDs"""
        stmt = delete(DomesticXray).where(DomesticXray.id.in_(record_ids))
        result = await db.execute(stmt)
        await db.commit()
        
        return {
            'success': True,
            'message': f'Deleted {result.rowcount} records',
            'deleted_count': result.rowcount
        }
    
    @staticmethod
    async def get_statistics(
        db: AsyncSession,
        start_date: Optional[date] = None,
        end_date: Optional[date] = None
    ) -> dict:
        """Get statistics for domestic x-ray reports"""
        # Build base query with filters
        conditions = []
        
        if start_date:
            start_datetime = datetime.combine(start_date, datetime.min.time(), tzinfo=timezone.utc)
            conditions.append(DomesticXray.xray_date_time >= start_datetime)
        
        if end_date:
            end_datetime = datetime.combine(end_date, datetime.max.time(), tzinfo=timezone.utc)
            conditions.append(DomesticXray.xray_date_time <= end_datetime)
        
        # Total records
        count_query = select(func.count()).select_from(DomesticXray)
        if conditions:
            count_query = count_query.where(and_(*conditions))
        
        total_result = await db.execute(count_query)
        total_records = total_result.scalar()
        
        # Printed records
        printed_query = select(func.count()).select_from(DomesticXray).where(DomesticXray.is_pdf_generated == True)
        if conditions:
            printed_query = printed_query.where(and_(*conditions))
        
        printed_result = await db.execute(printed_query)
        printed_records = printed_result.scalar()
        
        # Emailed records
        emailed_query = select(func.count()).select_from(DomesticXray).where(DomesticXray.is_email_sent == True)
        if conditions:
            emailed_query = emailed_query.where(and_(*conditions))
        
        emailed_result = await db.execute(emailed_query)
        emailed_records = emailed_result.scalar()
        
        # Unique counts
        unique_awbs_query = select(func.count(func.distinct(DomesticXray.awb_no)))
        unique_dest_query = select(func.count(func.distinct(DomesticXray.destination)))
        unique_agents_query = select(func.count(func.distinct(DomesticXray.agent_name)))
        
        if conditions:
            unique_awbs_query = unique_awbs_query.where(and_(*conditions))
            unique_dest_query = unique_dest_query.where(and_(*conditions))
            unique_agents_query = unique_agents_query.where(and_(*conditions))
        
        unique_awbs = (await db.execute(unique_awbs_query)).scalar()
        unique_destinations = (await db.execute(unique_dest_query)).scalar()
        unique_agents = (await db.execute(unique_agents_query)).scalar()
        
        # X-ray type distribution
        xray_query = select(
            DomesticXray.xray_type,
            func.count(DomesticXray.id).label('count')
        ).group_by(DomesticXray.xray_type)
        
        if conditions:
            xray_query = xray_query.where(and_(*conditions))
        
        xray_result = await db.execute(xray_query)
        xray_types = xray_result.all()
        
        return {
            'total_records': total_records,
            'printed_records': printed_records,
            'emailed_records': emailed_records,
            'unique_awbs': unique_awbs,
            'unique_destinations': unique_destinations,
            'unique_agents': unique_agents,
            'xray_type_distribution': [{'type': xt[0], 'count': xt[1]} for xt in xray_types if xt[0]]
        }
    


# =================== Domestic X- ray User ====================================
# services.py

    def clean_xray_user_id(xray_id: str) -> str | None:
        if pd.isna(xray_id) or str(xray_id).strip() == "":
            return None
        cleaned = re.sub(r'[^A-Za-z0-9_]', '', str(xray_id).strip().upper())
        return cleaned if cleaned else None

    @staticmethod
    async def bulk_create_employees(db: AsyncSession, df: pd.DataFrame):
        employees = []
        for _, row in df.iterrows():
            emp = DomesticXrayEmployee(
                employee_id=str(row['employee_id']),
                employee_name=str(row['employee_name']),
                xray_user_id=row['xray_user_id']
            )
            db.add(emp)
            employees.append(emp)
        await db.commit()
        return employees
    

    @staticmethod
    async def get_domestic_xray_employees(db: AsyncSession) -> List[EmployeeResponse]:
        """
        Fetch all domestic employees from the database.
        """
        result = await db.execute(select(DomesticXrayEmployee))
        employees = result.scalars().all()
        return [EmployeeResponse.model_validate(emp) for emp in employees]

    @staticmethod
    async def get_domestic_employee_by_user_id(db: AsyncSession, user_id: str) -> EmployeeResponse | None:
        """
        Fetch a single employee by user_id.
        """
        user_id = user_id.strip().upper()
        result = await db.execute(
            select(DomesticXrayEmployee).where(DomesticXrayEmployee.xray_user_id == str(user_id))
        )
        emp = result.scalar_one_or_none()
        return EmployeeResponse.model_validate(emp) if emp else None
