# from sqlalchemy.orm import Session
# from sqlalchemy import delete, select, text
# from typing import List, Dict, Any
# from sqlalchemy.ext.asyncio import AsyncSession

# from app.db.models.importOperation.import_wherehouse_inventry import ImportWhereHouseInventry


# class ImportWhereHouseInventryService:
    
#     @staticmethod
#     # def create_record(db: AsyncSession, data: Dict[str, Any]) -> ImportWhereHouseInventry:
#     #     record = ImportWhereHouseInventry(**data)
#     #     db.add(record)
#     #     db.commit()
#     #     db.refresh(record)
#     #     return record       (NOT CORRECT)
    

#     @staticmethod
#     async def delete_all_old_and_bulk_create_all_records(db: AsyncSession, records_data: List[Dict[str, Any]]) -> int:
#         if not records_data:
#             return 0
#             # Step 1: Delete existing records
#         await db.execute(delete(ImportWhereHouseInventry))

#             # Step 2: Reset sequence (PostgreSQL only)
#         await db.execute(text("ALTER SEQUENCE import_wherehouse_inventry_id_seq RESTART WITH 1"))


#         # Step 3: Insert new records
#         new_records = [ImportWhereHouseInventry(**data) for data in records_data]
#         db.add_all(new_records)
#         await db.commit()

#         return len(new_records)


# --==============================================================






from sqlalchemy.orm import Session
from sqlalchemy import delete, select, text
from typing import List, Dict, Any
from sqlalchemy.ext.asyncio import AsyncSession
from datetime import date
from app.db.models.importOperation.import_wherehouse_inventry import ImportWhereHouseInventry
from app.utils.stable_advisary_dblock_hash import stable_int32_lock_key
from sqlalchemy.dialects.postgresql import insert

class ImportWhereHouseInventryService:

    #=================== inser unique on combination of awb and hwb  version  ==========================
    # @staticmethod
    # async def bulk_create_all_records_wharehouse_inventry(
    #     db: AsyncSession, 
    #     records_data: List[Dict[str, Any]],
    #     cosys_report_date: date,
    #     uploaded_by: str,
    #     batch_size: int = 1000
    # ) -> Dict[str, Any]:
    #     """
    #     Insert records, let database unique constraint handle duplicates.
    #     Uses INSERT ... ON CONFLICT DO NOTHING for PostgreSQL.
    #     """
    #     if not records_data:
    #         return {
    #             "success": True,
    #             "inserted_records": 0,
    #             "duplicate_records": 0,
    #             "message": "No records to process"
    #         }
        
    #     try:
    #         # Advisory lock for this table and date
    #         table_key = stable_int32_lock_key("import_wherehouse_inventry")
    #         date_key = stable_int32_lock_key(str(cosys_report_date))

    #         result = await db.execute(
    #             text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
    #             {"key1": table_key, "key2": date_key}
    #         )
    #         lock_acquired = result.scalar()
    #         if not lock_acquired:
    #             return {
    #                 "success": False,
    #                 "message": "Another process is currently modifying the table..."
    #             }

    #         # Add metadata to all records
    #         for record in records_data:
    #             record['cosys_report_date'] = cosys_report_date
    #             record['uploaded_by'] = uploaded_by

    #         total_inserted = 0
    #         total_duplicates = 0

    #         # Insert in batches with conflict handling
    #         for i in range(0, len(records_data), batch_size):
    #             batch = records_data[i:i + batch_size]
                
    #             # Use raw SQL for INSERT ... ON CONFLICT DO NOTHING
               
    #             stmt = insert(ImportWhereHouseInventry).values(batch)
    #             stmt = stmt.on_conflict_do_nothing(
    #                 index_elements=['awb_no', 'hwb_no']  # Must match unique constraint
    #             )
                
    #             result = await db.execute(stmt)
    #             inserted_count = result.rowcount if result.rowcount else 0
    #             total_inserted += inserted_count
    #             total_duplicates += (len(batch) - inserted_count)

    #         await db.commit()

    #         return {
    #             "success": True,
    #             "inserted_records": total_inserted,
    #             "duplicate_records": total_duplicates,
    #             "message": f"Successfully uploaded {total_inserted} new records. "
    #                       f"Skipped {total_duplicates} duplicates",
    #             "total_records": len(records_data)
    #         }

    #     except Exception as e:
    #         await db.rollback()
    #         return {
    #             "success": False,
    #             "inserted_records": 0,
    #             "duplicate_records": 0,
    #             "message": f"Database error: {str(e)}",
    #             "total_records": len(records_data)
    #         }







    # ======================== THIS IS DELETE TO THAT DATE  AND ADVISARY LOCK  VERSION  ==========================
    @staticmethod
    async def bulk_create_all_records_wharehouse_inventry(
        db: AsyncSession, 
        records_data: List[Dict[str, Any]],
        cosys_report_date: date,
        uploaded_by: str,
        batch_size: int = 1000  # ----- NEW: batch size parameter for safe insertion
    ) -> Dict[str, Any]:
        """
        Delete old records for specific date and bulk insert new records safely in batches
        """
        if not records_data:
            return {
                "success": True,
                "inserted_records": 0,
                "message": "No records to process"
            }
        
        try:
            # Advisory lock for this table and date
            table_key = stable_int32_lock_key("import_wherehouse_inventry")
            date_key = stable_int32_lock_key(str(cosys_report_date))

            result = await db.execute(
                text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
                {"key1": table_key, "key2": date_key}
            )
            lock_acquired = result.scalar()
            if not lock_acquired:
                return {
                    "success": False,
                    "message": "Another process is currently modifying the table..."
                }

            # ----- NEW: delete old records for the date
            await db.execute(
                delete(ImportWhereHouseInventry).where(
                    ImportWhereHouseInventry.cosys_report_date == cosys_report_date
                )
            )

            # Add metadata
            for record in records_data:
                record['cosys_report_date'] = cosys_report_date
                record['uploaded_by'] = uploaded_by

            total_inserted = 0

            # ----- NEW: Insert in batches
            for i in range(0, len(records_data), batch_size):
                batch = records_data[i:i + batch_size]
                new_records = [ImportWhereHouseInventry(**data) for data in batch]
                db.add_all(new_records)
                await db.flush()   # ensure they're staged safely before committing
                total_inserted += len(batch)

            await db.commit()  # final commit after all batches

            return {
                "success": True,
                "inserted_records": total_inserted,
                "message": f"Successfully uploaded {total_inserted} records for {cosys_report_date}",
                "total_records": total_inserted
            }

        except Exception as e:
            await db.rollback()
            return {
                "success": False,
                "inserted_records": 0,
                "message": f"Database error: {str(e)}",
                "total_records": len(records_data)
            }
    