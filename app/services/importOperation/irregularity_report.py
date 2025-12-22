


# ==================================


# from typing import Any, Dict, List
# import io
# from datetime import date
# from sqlalchemy import delete, insert, text
# from sqlalchemy.ext.asyncio import AsyncSession
# import pandas as pd

# from app.db.models.importOperation.irregularity_report import Irregularity
# from app.utils.importOperation.irregularity_report_cleaner import clean_irregularities_file
# from app.utils.stable_advisary_dblock_hash import stable_int32_lock_key

# class IrregularitiesService:

#     @staticmethod
#     async def delete_all_old_and_bulk_create_from_file(
#         db: AsyncSession,
#         file,
#         file_type: str,
#         cosys_report_date: date,
#         uploaded_by: str
#     ) -> Dict[str, Any]:
#         """
#         Process file upload and bulk insert records (async-safe) - Single method like OC report
#         """
#         try:
#             # Clean and parse the file
#             file_like_object = io.BytesIO(file) if isinstance(file, bytes) else file
#             df = clean_irregularities_file(file_like_object, file_type)
            
#             # Convert to list of dictionaries
#             records = df.to_dict('records')
#             total_records = len(records)
            
#             if total_records == 0:
#                 return {
#                     "success": False,
#                     "total_records": 0,
#                     "inserted_records": 0,
#                     "failed_records": 0,
#                     "errors": [],
#                     "message": "No records found in the file"
#                 }
            
#             # Add cosys_report_date and uploaded_by to each record
#             for record in records:
#                 record['cosys_report_date'] = cosys_report_date
#                 record['uploaded_by'] = uploaded_by
            
#             # Async bulk insert using insert() + execute()
#             try:
#                 table_key = stable_int32_lock_key("irregularity_report")
#                 date_key = stable_int32_lock_key(str(cosys_report_date))

#                 result = await db.execute(
#                     text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
#                     {"key1": table_key, "key2": date_key}
#                 )
#                 lock_acquired = result.scalar()
#                 if not lock_acquired:
#                     return {
#                         "success": False,
                        
                        
#                         "errors": [],
#                         "message":"Another process is currently modifying the table..."
#                     }

                
#                 # Delete only records with matching cosys_report_date
#                 await db.execute(
#                     delete(Irregularity).where(Irregularity.cosys_report_date == cosys_report_date)
#                 )
                
                

#                 # Bulk insert using SQLAlchemy core for better performance
#                 stmt = insert(Irregularity).values(records)
#                 await db.execute(stmt)
#                 await db.commit()
                
#                 return {
#                     "success": True,
#                     "total_records": total_records,
#                     "inserted_records": total_records,
#                     "failed_records": 0,
#                     "errors": [],
#                     "message": f"Successfully uploaded {total_records} records for date {cosys_report_date}",
#                     "sample_records": records[:5] if records else []  # Keep sample for response
#                 }
                
#             except Exception as e:
#                 await db.rollback()
#                 return {
#                     "success": False,
#                     "total_records": total_records,
#                     "inserted_records": 0,
#                     "failed_records": total_records,
#                     "errors": [{"error": str(e)}],
#                     "message": f"Database error: {str(e)}"
#                 }
                
#         except Exception as e:
#             return {
#                 "success": False,
#                 "total_records": 0,
#                 "inserted_records": 0,
#                 "failed_records": 0,
#                 "errors": [{"error": str(e)}],
#                 "message": f"File processing error: {str(e)}"
#             }


# ===============================================================================

# New version below with batching and improved error handling (above is previous without batching)




from typing import Any, Dict
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

        try:
            # Read file
            file_like_object = io.BytesIO(file) if isinstance(file, bytes) else file
            df = clean_irregularities_file(file_like_object, file_type)

            records = df.to_dict("records")
            total_records = len(records)

            if total_records == 0:
                return {
                    "success": False,
                    "message": "No records found in the file",
                    "total_records": 0,
                }

            # Add additional fields
            for record in records:
                record["cosys_report_date"] = cosys_report_date
                record["uploaded_by"] = uploaded_by

            # Acquire lock
            table_key = stable_int32_lock_key("irregularity_report")
            date_key = stable_int32_lock_key(str(cosys_report_date))

            lock_result = await db.execute(
                text("SELECT pg_try_advisory_xact_lock(:k1, :k2)"),
                {"k1": table_key, "k2": date_key},
            )

            if not lock_result.scalar():
                return {
                    "success": False,
                    "message": "Another process is currently modifying this table..."
                }

            # Delete old records for that date
            await db.execute(
                delete(Irregularity).where(Irregularity.cosys_report_date == cosys_report_date)
            )

            # ---------- FIX: INSERT IN BATCHES ----------
            BATCH_SIZE = 1000   # Safe (21 params × 1000 rows = 21000 < 32767)

            inserted = 0
            for i in range(0, total_records, BATCH_SIZE):
                batch = records[i:i + BATCH_SIZE]

                stmt = insert(Irregularity)
                await db.execute(stmt, batch)

                inserted += len(batch)

            await db.commit()

            # ------------------------------------------

            return {
                "success": True,
                "message": f"Successfully uploaded {inserted} records.",
                "total_records": total_records,
                "inserted_records": inserted,
                "sample_records": records[:5]
            }

        except Exception as e:
            await db.rollback()
            return {
                "success": False,
                "message": f"Error: {str(e)}",
                "errors": [{"error": str(e)}]
            }
