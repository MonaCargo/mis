

# from typing import Dict, Any
# from sqlalchemy import delete, text
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.exc import SQLAlchemyError
# from fastapi import HTTPException
# from app.db.models.importOperation.import_release_report import IrrReport
# from app.utils.importOperation.import_release_cleaner import clean_import_release_file

# class IrrReportService:

#     @staticmethod
#     async def delete_all_old_and_processfile_and_save_irr_data(
#         file,
#         file_type: str,
#         db: AsyncSession
#     ) -> Dict[str, Any]:
#         try:
#             # print("================================")
#             df = clean_import_release_file(file, file_type)
#             # print("Resrjkjkjkjk===============",df.head())

#             if df.empty:
#                 raise HTTPException(status_code=400, detail="File is empty or contains no valid data")

#             records = df.to_dict('records')
#             total_records = len(records)

#              # Step 1: Delete existing records
#             await db.execute(delete(IrrReport))

#             # Step 2: Reset sequence (PostgreSQL only)
#             await db.execute(text("ALTER SEQUENCE irr_report_id_seq RESTART WITH 1"))

#             # Calculate safe batch size
#             num_columns = len(df.columns)
#             max_pg_params = 32000
#             batch_size = max_pg_params // num_columns
#             saved_count = 0

#             for i in range(0, total_records, batch_size):
#                 batch = records[i:i + batch_size]
#                 irr_objects = [IrrReport(**r) for r in batch]

#                 db.add_all(irr_objects)
#                 await db.commit()
#                 saved_count += len(batch)

#             return {
#                 'success': True,
#                 'total_records': total_records,
#                 'saved_records': saved_count,
#                 'status_code':200
#             }

#         except HTTPException:
#             raise
#         except ValueError as e:
#             # Catch specific validation errors from cleaner
#             await db.rollback()
#             raise HTTPException(status_code=400, detail=str(e))
#         except Exception as e:
#             await db.rollback()
#             raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")




# =============================================================================================

# from typing import Dict, Any
# from datetime import date
# import time
# from sqlalchemy import delete, text
# from sqlalchemy.ext.asyncio import AsyncSession
# from sqlalchemy.exc import SQLAlchemyError
# from fastapi import HTTPException
# from app.db.models.importOperation.import_release_report import IrrReport
# from app.utils.importOperation.import_release_cleaner import clean_import_release_file

# class IrrReportService:

#     @staticmethod
#     async def delete_all_old_and_processfile_and_save_irr_data(
#         file,
#         file_type: str,
#         db: AsyncSession,
#         cosys_report_date: date,  # Add this parameter
#         uploaded_by: str  # Add this parameter
#     ) -> Dict[str, Any]:
#         try:
#             clean_start = time.time()
#             df = clean_import_release_file(file, file_type)

            
           
#             if df.empty:
#                 raise HTTPException(status_code=400, detail="File is empty or contains no valid data")

#             records = df.to_dict('records')
#             total_records = len(records)
            
#             # Add metadata to each record
#             for record in records:
#                 record['cosys_report_date'] = cosys_report_date
#                 record['uploaded_by'] = uploaded_by
#             clean_time = time.time() - clean_start
#             print("-Data Cleaning:", {clean_time} )

#             # Advisory lock key based on cosys_report_date
#             lock_key = hash(str(cosys_report_date))

#             async with db.begin():  # Transaction block
                
#                 # Step 1: Delete only records with matching cosys_report_date
#                 await db.execute(
#                     delete(IrrReport).where(IrrReport.cosys_report_date == cosys_report_date)
#                 )

            

#                 # Calculate safe batch size
#                 num_columns = len(df.columns)
#                 max_pg_params = 32000
#                 batch_size = max_pg_params // num_columns
#                 saved_count = 0

#                 for i in range(0, total_records, batch_size):
#                     batch = records[i:i + batch_size]
#                     irr_objects = [IrrReport(**r) for r in batch]

#                     db.add_all(irr_objects)
#                     await db.commit()
#                     saved_count += len(batch)

#                 return {
#                     'success': True,
#                     'total_records': total_records,
#                     'saved_records': saved_count,
#                     'status_code': 200,
#                     'message': f"Successfully uploaded {saved_count} records for date {cosys_report_date}"
#                 }

#         except HTTPException:
#             raise
#         except ValueError as e:
#             await db.rollback()
#             raise HTTPException(status_code=400, detail=str(e))
#         except Exception as e:
#             await db.rollback()
#             raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")





























from typing import Dict, Any
from datetime import date
import time
from sqlalchemy import delete, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException
from app.db.models.importOperation.import_release_report import IrrReport
from app.utils.importOperation.import_release_cleaner import clean_import_release_file
from app.utils.stable_advisary_dblock_hash import stable_int32_lock_key

class IrrReportService:


    from sqlalchemy.dialects.postgresql import insert

class IrrReportService:

    @staticmethod
    async def delete_all_old_and_processfile_and_save_irr_data(
        file,
        file_type: str,
        db: AsyncSession,
        cosys_report_date: date,
        uploaded_by: str
    ) -> Dict[str, Any]:
        try:
            # Step 1: Clean and parse the file
            clean_start = time.time()
            df = clean_import_release_file(file, file_type)

            if df.empty:
                raise HTTPException(status_code=400, detail="File is empty or contains no valid data")

            records = df.to_dict('records')
            total_records = len(records)

            for record in records:
                record['cosys_report_date'] = cosys_report_date
                record['uploaded_by'] = uploaded_by

            clean_time = time.time() - clean_start
            print("-Data Cleaning:", {clean_time})
            print("locked added")
            
            table_key = stable_int32_lock_key("irr_report")
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
           
            # Step 2: Filter out records with null oc_num
            valid_records = [r for r in records if r.get('oc_num') is not None]
            skipped_null_oc = len(records) - len(valid_records)

            # Step 3: Insert new records only (skip duplicates) in batches
            num_columns = len(df.columns)
            print("==================================",num_columns)
            max_pg_params = 28000
            batch_size = max_pg_params // num_columns
            
            inserted_count = 0
            duplicate_count = 0

            for i in range(0, len(valid_records), batch_size):
                batch = valid_records[i:i + batch_size]
                
                # Use PostgreSQL's INSERT ... ON CONFLICT DO NOTHING
                stmt = insert(IrrReport).values(batch)
                stmt = stmt.on_conflict_do_nothing(
                     index_elements=['oc_num']  # ✅ Specify the unique constraint column
                )
                
                result = await db.execute(stmt)
                # result.rowcount gives the number of actually inserted rows
                inserted_count += result.rowcount
            
            duplicate_count = len(valid_records) - inserted_count
            
            # Step 4: Commit the transaction
            await db.commit()

            # Step 5: Return success response
            return {
                'success': True,
                'total_records': total_records,
                'valid_records': len(valid_records),
                'inserted_records': inserted_count,
                'duplicate_records': duplicate_count,
                'skipped_null_oc': skipped_null_oc,
                'status_code': 200,
                'message': f"Successfully inserted {inserted_count} new records for date {cosys_report_date}. {duplicate_count} duplicates skipped. {skipped_null_oc} records skipped due to missing oc_num."
            }

        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
        


    #============= this is priviousaly which blidaly save all incommin correct data without checking duplicate ==============
    # @staticmethod
    # async def delete_all_old_and_processfile_and_save_irr_data(
    #     file,
    #     file_type: str,
    #     db: AsyncSession,
    #     cosys_report_date: date,
    #     uploaded_by: str
    # ) -> Dict[str, Any]:
    #     try:
    #         # Step 1: Clean and parse the file
    #         clean_start = time.time()
    #         df = clean_import_release_file(file, file_type)

    #         if df.empty:
    #             raise HTTPException(status_code=400, detail="File is empty or contains no valid data")

    #         records = df.to_dict('records')
    #         total_records = len(records)

    #         for record in records:
    #             record['cosys_report_date'] = cosys_report_date
    #             record['uploaded_by'] = uploaded_by

    #         clean_time = time.time() - clean_start
    #         print("-Data Cleaning:", {clean_time})
    #         print("locked added")
            
    #         table_key = stable_int32_lock_key("irr_report")
    #         date_key = stable_int32_lock_key(str(cosys_report_date))

    #         result = await db.execute(
    #                 text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
    #                 {"key1": table_key, "key2": date_key}
    #             )
    #         lock_acquired = result.scalar()
    #         if not lock_acquired:
    #             return {
    #                 "success": False,
                        
                    
    #                 "errors": [],
    #                 "message":"Another process is currently modifying the table..."
    #             }
           

    #         # # Step 4: Delete existing records for the report date
    #         # await db.execute(
    #         #     delete(IrrReport).where(IrrReport.cosys_report_date == cosys_report_date)
    #         # )

    #         # Step 5: Insert new records in safe batches
    #         num_columns = len(df.columns)
    #         max_pg_params = 32000
    #         batch_size = max_pg_params // num_columns
    #         saved_count = 0

    #         for i in range(0, total_records, batch_size):
    #             batch = records[i:i + batch_size]
    #             irr_objects = [IrrReport(**r) for r in batch]
    #             db.add_all(irr_objects)
    #             saved_count += len(batch)
            
    #         # Step 4: Commit manually since we're not using db.begin()
    #         await db.commit()

    #         # Step 6: Return success response
    #         return {
    #             'success': True,
    #             'total_records': total_records,
    #             'saved_records': saved_count,
    #             'status_code': 200,
    #             'message': f"Successfully uploaded {saved_count} records for date {cosys_report_date}"
    #         }

    #     except HTTPException:
    #         raise
    #     except ValueError as e:
    #         raise HTTPException(status_code=400, detail=str(e))
    #     except Exception as e:
    #         raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
