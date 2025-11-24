

# # service.py
# from typing import Any, Dict, List
# import io

# import pandas as pd
# from sqlalchemy import delete, insert, text

# from app.db.models.importOperation.irregularity_report import Irregularity
# from app.utils.importOperation.irregularity_report_cleaner import clean_irregularities_file
# from sqlalchemy.ext.asyncio import AsyncSession

# # OPTIMIZED service.py


        
# class IrregularitiesService:

#     @staticmethod
#     def process_uploaded_file(file_content: bytes, filename: str, file_type: str) -> Dict[str, Any]:
#         """
#         Process uploaded irregularities file and return cleaned data (synchronous)
#         """
#         try:
#             file_like_object = io.BytesIO(file_content)
#             cleaned_df = clean_irregularities_file(file_like_object, file_type)
#             records = cleaned_df.to_dict('records')

#             return {
#                 "success": True,
#                 "message": f"Successfully processed {len(records)} records from {filename}",
#                 "records_count": len(records),
#                 "all_records": records,  # ✅ Added this key for db
#                 "sample_records": records[:5] if records else [], # it is only for test (5 data)
#                 "columns": list(cleaned_df.columns)
#             }
#         except Exception as e:
#             return {
#                 "success": False,
#                 "message": f"Error processing file: {str(e)}",
#                 "records_count": 0,
#                 "all_records": [],  # ✅ Added this key
#                 "sample_records": [],
#                 "columns": []
#             }

#     @staticmethod
#     async def delete_all_old_and_save_irregularities_filedata_to_db(db: AsyncSession, records: List[Dict]) -> Dict[str, Any]:
#         """
#         Save cleaned irregularities data to database (async) using bulk insert
#         """
#         try:
#             if not records:
#                 return {
#                     "success": True,
#                     "saved_count": 0,
#                     "error_count": 0,
#                     "errors": []
#                 }
            
#               # Step 1: Delete all existing records
#             await db.execute(delete(Irregularity))

#             # Step 2: Reset primary key sequence (PostgreSQL example)
#             if db.bind.dialect.name == "postgresql": # It ensure that it run only for postgresql 
#                 await db.execute(text("ALTER SEQUENCE irregularity_report_id_seq RESTART WITH 1"))
             


#             irregularities = [Irregularity(**record) for record in records]
#             db.add_all(irregularities)
#             await db.commit()

#             return {
#                 "success": True,
#                 "status_code":200,
#                 "saved_count": len(irregularities),
#                 "message":"Add new data (cleared old data)",
#                 "error_count": 0,
#                 "errors": []
#             }

#         except Exception as e:
#             await db.rollback()
#             return {
#                 "success": False,
#                 "saved_count": 0,
#                 "error_count": len(records),
#                 "errors": [str(e)]
#             }








# ==================================






from typing import Any, Dict, List
import io
from datetime import date
from sqlalchemy import delete, insert, text
from sqlalchemy.ext.asyncio import AsyncSession
import pandas as pd

from app.db.models.importOperation.irregularity_report import Irregularity
from app.utils.importOperation.irregularity_report_cleaner import clean_irregularities_file
from app.utils.stable_advisary_dblock_hash import stable_int32_lock_key

class IrregularitiesService:

    @staticmethod
    async def delete_all_old_and_bulk_create_from_file(
        db: AsyncSession,
        file,
        file_type: str,
        cosys_report_date: date,
        uploaded_by: str
    ) -> Dict[str, Any]:
        """
        Process file upload and bulk insert records (async-safe) - Single method like OC report
        """
        try:
            # Clean and parse the file
            file_like_object = io.BytesIO(file) if isinstance(file, bytes) else file
            df = clean_irregularities_file(file_like_object, file_type)
            
            # Convert to list of dictionaries
            records = df.to_dict('records')
            total_records = len(records)
            
            if total_records == 0:
                return {
                    "success": False,
                    "total_records": 0,
                    "inserted_records": 0,
                    "failed_records": 0,
                    "errors": [],
                    "message": "No records found in the file"
                }
            
            # Add cosys_report_date and uploaded_by to each record
            for record in records:
                record['cosys_report_date'] = cosys_report_date
                record['uploaded_by'] = uploaded_by
            
            # Async bulk insert using insert() + execute()
            try:
                table_key = stable_int32_lock_key("irregularity_report")
                date_key = stable_int32_lock_key(str(cosys_report_date))

                result = await db.execute(
                    text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
                    {"key1": table_key, "key2": date_key}
                )
                lock_acquired = result.scalar()
                if not lock_acquired:
                    return {
                        "success": False,
                        
                        
                        "errors": [],
                        "message":"Another process is currently modifying the table..."
                    }

                
                # Delete only records with matching cosys_report_date
                await db.execute(
                    delete(Irregularity).where(Irregularity.cosys_report_date == cosys_report_date)
                )
                
                

                # Bulk insert using SQLAlchemy core for better performance
                stmt = insert(Irregularity).values(records)
                await db.execute(stmt)
                await db.commit()
                
                return {
                    "success": True,
                    "total_records": total_records,
                    "inserted_records": total_records,
                    "failed_records": 0,
                    "errors": [],
                    "message": f"Successfully uploaded {total_records} records for date {cosys_report_date}",
                    "sample_records": records[:5] if records else []  # Keep sample for response
                }
                
            except Exception as e:
                await db.rollback()
                return {
                    "success": False,
                    "total_records": total_records,
                    "inserted_records": 0,
                    "failed_records": total_records,
                    "errors": [{"error": str(e)}],
                    "message": f"Database error: {str(e)}"
                }
                
        except Exception as e:
            return {
                "success": False,
                "total_records": 0,
                "inserted_records": 0,
                "failed_records": 0,
                "errors": [{"error": str(e)}],
                "message": f"File processing error: {str(e)}"
            }