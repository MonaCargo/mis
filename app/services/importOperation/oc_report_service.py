# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy import select, func
# from typing import List, Dict, Any
# import pandas as pd
# from app.db.models.importOperation.oc_report import OcReport  # Your SQLAlchemy model
# from app.schemas.importOperation.oc_report import BulkUploadResponse
# from app.utils.importOperation.oc_report_cleaner import clean_and_parse_oc_report


# class OcReportService:
    
#     @staticmethod
#     async def bulk_create_from_file(
#         db: AsyncSession,
#         file,
#         file_type: str
#     ) -> BulkUploadResponse:
#         """
#         Process file upload and bulk insert records
#         """
#         try:
#             # Clean and parse the file
#             df = clean_and_parse_oc_report(file, file_type)
            
#             # Convert to list of dictionaries
#             records = df.to_dict('records')
#             total_records = len(records)
            
#             if total_records == 0:
#                 return BulkUploadResponse(
#                     success=False,
#                     total_records=0,
#                     inserted_records=0,
#                     failed_records=0,
#                     errors=[],
#                     message="No records found in the file"
#                 )
            
#             # Bulk insert using SQLAlchemy
#             try:
#                 db.bulk_insert_mappings(OcReport, records)
#                 await db.commit()
                
#                 return BulkUploadResponse(
#                     success=True,
#                     total_records=total_records,
#                     inserted_records=total_records,
#                     failed_records=0,
#                     errors=[],
#                     message=f"Successfully uploaded {total_records} records"
#                 )
                
#             except Exception as e:
#                 await db.rollback()
#                 return BulkUploadResponse(
#                     success=False,
#                     total_records=total_records,
#                     inserted_records=0,
#                     failed_records=total_records,
#                     errors=[{"error": str(e)}],
#                     message=f"Database error: {str(e)}"
#                 )
                
#         except Exception as e:
#             return BulkUploadResponse(
#                 success=False,
#                 total_records=0,
#                 inserted_records=0,
#                 failed_records=0,
#                 errors=[{"error": str(e)}],
#                 message=f"File processing error: {str(e)}"
#             )
    
    
    


from datetime import date
from sqlalchemy import delete, select, text
from sqlalchemy.dialects.postgresql import insert

from sqlalchemy.ext.asyncio import AsyncSession
from app.db.models.importOperation.oc_report import OcReport
from app.schemas.importOperation.oc_report import BulkUploadResponse
from app.utils.importOperation.oc_report_cleaner import clean_and_parse_oc_report
from app.utils.stable_advisary_dblock_hash import stable_int32_lock_key


def chunk_list(data, size=1500):
    for i in range(0, len(data), size):
        yield data[i:i + size]




class OcReportService:
    
  
    # @staticmethod
    # async def _bulk_create_from_file_oc_report(
    #     db: AsyncSession,
    #     file,
    #     file_type: str,
    #     cosys_report_date: date,
    #     emp_id: str
    # ) -> BulkUploadResponse:
    
    #     try:
    #         df = clean_and_parse_oc_report(file, file_type)
    #         records = df.to_dict("records")
    #         total_records = len(records)

    #         if total_records == 0:
    #             return BulkUploadResponse(
    #                 success=False,
    #                 total_records=0,
    #                 inserted_records=0,
    #                 failed_records=0,
    #                 errors=[],
    #                 message="No records found in the file"
    #             )

    #         for r in records:
    #             r["cosys_report_date"] = cosys_report_date
    #             r["uploaded_by"] = emp_id

            

    #         try:
    #             table_key = stable_int32_lock_key("oc_report")
    #             date_key = stable_int32_lock_key(str(cosys_report_date))

    #             result = await db.execute(
    #                 text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
    #                 {"key1": table_key, "key2": date_key}
    #             )
    #             lock_acquired = result.scalar()

    #             if not lock_acquired:
    #                 return BulkUploadResponse(
    #                     success=False,
    #                     total_records=0,
    #                     inserted_records=0,
    #                     failed_records=0,
    #                     errors=[],
    #                     message="Another process is currently modifying the table..."
    #                 )


    #             # ✅ Atomic block (delete then insert) (Single SQLTransaction)
    #             await db.execute(
    #                 delete(OcReport).where(OcReport.cosys_report_date == cosys_report_date)
    #             )
    #             await db.execute(insert(OcReport).values(records))

    #             await db.commit()  # ✅ commit everything if success

    #             return BulkUploadResponse(
    #                 success=True,
    #                 total_records=total_records,
    #                 inserted_records=total_records,
    #                 failed_records=0,
    #                 errors=[],
    #                 message=f"Successfully replaced data for {cosys_report_date}"
    #             )

    #         except Exception as e:
    #             await db.rollback()  # ✅ rollback delete if insert fails
    #             return BulkUploadResponse(
    #                 success=False,
    #                 total_records=total_records,
    #                 inserted_records=0,
    #                 failed_records=total_records,
    #                 errors=[{"error": str(e)}],
    #                 message="Database error: " + str(e)
    #             )

    #     except Exception as e:
    #         return BulkUploadResponse(
    #             success=False,
    #             total_records=0,
    #             inserted_records=0,
    #             failed_records=0,
    #             errors=[{"error": str(e)}],
    #             message="File processing error: " + str(e)
    #         )
   


    @staticmethod
    async def bulk_create_from_file_oc_report(
        db: AsyncSession,
        file,
        file_type: str,
        cosys_report_date: date,
        emp_id: str
    ) -> BulkUploadResponse:
        """
        Efficiently bulk insert OC Report data:
        ✅ Keeps only unique oc_no
        ✅ Uses ON CONFLICT DO NOTHING (PostgreSQL)
        ✅ Handles 5,000+ records safely
        ✅ Advisory lock for per-date atomicity
        """
        try:
            df = clean_and_parse_oc_report(file, file_type)
            records = df.to_dict("records")
            total_records = len(records)

            if total_records == 0:
                return BulkUploadResponse(
                    success=False,
                    total_records=0,
                    inserted_records=0,
                    failed_records=0,
                    errors=[],
                    message="No records found in the file"
                )

            for r in records:
                r["cosys_report_date"] = cosys_report_date
                r["uploaded_by"] = emp_id

            # Acquire per-date advisory lock
            table_key = stable_int32_lock_key("oc_report")
            date_key = stable_int32_lock_key(str(cosys_report_date))

            result = await db.execute(
                text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
                {"key1": table_key, "key2": date_key}
            )
            if not result.scalar():
                return BulkUploadResponse(
                    success=False,
                    total_records=0,
                    inserted_records=0,
                    failed_records=0,
                    errors=[],
                    message="Another process is currently modifying the table..."
                )

            # # ✅ Delete old records for the same date first
            # await db.execute(
            #     delete(OcReport).where(OcReport.cosys_report_date == cosys_report_date)
            # )

            # ✅ Batch insert with ON CONFLICT DO NOTHING
            total_inserted = 0
            for batch in chunk_list(records, 1500):
                stmt = (
                    insert(OcReport)
                    .values(batch)
                    .on_conflict_do_nothing(index_elements=["oc_no"])
                    .returning(OcReport.id)
                )
                result = await db.execute(stmt)
                total_inserted += len(result.fetchall())

                # Optional: Commit per batch (safe and efficient)
                await db.commit()

            return BulkUploadResponse(
                success=True,
                total_records=total_records,
                inserted_records=total_inserted,
                failed_records=total_records - total_inserted,
                errors=[],
                message=f"Successfully inserted {total_inserted} unique records, skipped {total_records - total_inserted} duplicates"
            )

        except Exception as e:
            await db.rollback()
            return BulkUploadResponse(
                success=False,
                total_records=0,
                inserted_records=0,
                failed_records=0,
                errors=[{"error": str(e)}],
                message=f"Error processing file: {str(e)}"
            )

   
    @staticmethod
    async def get_by_id(db: AsyncSession, report_id: int):
        """
        Get OC report by ID
        """
        try:
            result = await db.execute(
                select(OcReport).where(OcReport.id == report_id)
            )
            report = result.scalar_one_or_none()

            if report:
                return report  # ✅ return the found record

            return None  # ✅ correct fallback

        except Exception as e:
            raise
