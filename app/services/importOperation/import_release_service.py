

# from typing import Dict, Any
# from datetime import date
# import time
# from sqlalchemy import and_, delete, text
# from sqlalchemy.dialects.postgresql import insert
# from sqlalchemy.ext.asyncio import AsyncSession
# from fastapi import HTTPException
# from app.db.models.importOperation.import_release_report import IrrReport
# from app.utils.importOperation.import_release_cleaner import clean_import_release_file
# from app.utils.stable_advisary_dblock_hash import stable_int32_lock_key

# class IrrReportService:


#     from sqlalchemy.dialects.postgresql import insert

# class IrrReportService:
#     # this is without gatepass end date update on oc_num exiting (conflict: old version)
#     # @staticmethod
#     # async def delete_all_old_and_processfile_and_save_irr_data(
#     #     file,
#     #     file_type: str,
#     #     db: AsyncSession,
#     #     cosys_report_date: date,
#     #     uploaded_by: str
#     # ) -> Dict[str, Any]:
#     #     try:
#     #         # Step 1: Clean and parse the file
#     #         clean_start = time.time()
#     #         df = clean_import_release_file(file, file_type)

#     #         if df.empty:
#     #             raise HTTPException(status_code=400, detail="File is empty or contains no valid data")

#     #         records = df.to_dict('records')
#     #         total_records = len(records)

#     #         for record in records:
#     #             record['cosys_report_date'] = cosys_report_date
#     #             record['uploaded_by'] = uploaded_by

#     #         clean_time = time.time() - clean_start
#     #         print("-Data Cleaning:", {clean_time})
#     #         print("locked added")
            
#     #         table_key = stable_int32_lock_key("irr_report")
#     #         date_key = stable_int32_lock_key(str(cosys_report_date))

#     #         result = await db.execute(
#     #                 text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
#     #                 {"key1": table_key, "key2": date_key}
#     #             )
#     #         lock_acquired = result.scalar()
#     #         if not lock_acquired:
#     #             return {
#     #                 "success": False,
#     #                 "errors": [],
#     #                 "message":"Another process is currently modifying the table..."
#     #             }
           
#     #         # Step 2: Filter out records with null oc_num
#     #         valid_records = [r for r in records if r.get('oc_num') is not None]
#     #         skipped_null_oc = len(records) - len(valid_records)

#     #         # Step 3: Insert new records only (skip duplicates) in batches
#     #         num_columns = len(df.columns)
#     #         print("==================================",num_columns)
#     #         max_pg_params = 28000
#     #         batch_size = max_pg_params // num_columns
            
#     #         inserted_count = 0
#     #         duplicate_count = 0

#     #         for i in range(0, len(valid_records), batch_size):
#     #             batch = valid_records[i:i + batch_size]
                
#     #             # Use PostgreSQL's INSERT ... ON CONFLICT DO NOTHING
#     #             stmt = insert(IrrReport).values(batch)
#     #             stmt = stmt.on_conflict_do_nothing(
#     #                  index_elements=['oc_num']  # ✅ Specify the unique constraint column
#     #             )
                
#     #             result = await db.execute(stmt)
#     #             # result.rowcount gives the number of actually inserted rows
#     #             inserted_count += result.rowcount
            
#     #         duplicate_count = len(valid_records) - inserted_count
            
#     #         # Step 4: Commit the transaction
#     #         await db.commit()

#     #         # Step 5: Return success response
#     #         return {
#     #             'success': True,
#     #             'total_records': total_records,
#     #             'valid_records': len(valid_records),
#     #             'inserted_records': inserted_count,
#     #             'duplicate_records': duplicate_count,
#     #             'skipped_null_oc': skipped_null_oc,
#     #             'status_code': 200,
#     #             'message': f"Successfully inserted {inserted_count} new records for date {cosys_report_date}. {duplicate_count} duplicates skipped. {skipped_null_oc} records skipped due to missing oc_num."
#     #         }

#     #     except HTTPException:
#     #         raise
#     #     except ValueError as e:
#     #         raise HTTPException(status_code=400, detail=str(e))
#     #     except Exception as e:
#     #         await db.rollback()
#     #         raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
        

#     # New Version
#     @staticmethod
#     async def delete_all_old_and_processfile_and_save_irr_data(
#         file,
#         file_type: str,
#         db: AsyncSession,
#         cosys_report_date: date,
#         uploaded_by: str
#     ) -> Dict[str, Any]:
#         try:
#             # Step 1: Clean and parse the file
#             clean_start = time.time()
#             df = clean_import_release_file(file, file_type)

#             if df.empty:
#                 raise HTTPException(status_code=400, detail="File is empty or contains no valid data")

#             records = df.to_dict('records')
#             total_records = len(records)

#             for record in records:
#                 record['cosys_report_date'] = cosys_report_date
#                 record['uploaded_by'] = uploaded_by

#             clean_time = time.time() - clean_start
#             print("-Data Cleaning:", {clean_time})
#             print("locked added")
            
#             table_key = stable_int32_lock_key("irr_report")
#             date_key = stable_int32_lock_key(str(cosys_report_date))

#             result = await db.execute(
#                     text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
#                     {"key1": table_key, "key2": date_key}
#                 )
#             lock_acquired = result.scalar()
#             if not lock_acquired:
#                 return {
#                     "success": False,
#                     "errors": [],
#                     "message":"Another process is currently modifying the table..."
#                 }
           
#             # Step 2: Filter out records with null oc_num
#             valid_records = [r for r in records if r.get('oc_num') is not None]
#             skipped_null_oc = len(records) - len(valid_records)

#             # Step 3: Insert new records only (skip duplicates) in batches
#             num_columns = len(df.columns)
#             print("==================================",num_columns)
#             max_pg_params = 28000
#             batch_size = max_pg_params // num_columns
            
#             inserted_count = 0
#             duplicate_count = 0
#             updated_count = 0   # 🔥 new

#             for i in range(0, len(valid_records), batch_size):
#                 batch = valid_records[i:i + batch_size]
                
#                 # Use PostgreSQL's INSERT ... ON CONFLICT DO NOTHING
#                 stmt = insert(IrrReport).values(batch)
#                 # stmt = stmt.on_conflict_do_nothing(
#                 #      index_elements=['oc_num']  # ✅ Specify the unique constraint column
#                 # )
#                  # 🔥 Update only when DB has NULL & incoming file has value
#                 stmt = stmt.on_conflict_do_update(
#                     index_elements=['oc_num'],   # Unique identifier
#                     set_={
#                         "gate_pass_end_date_time": text("EXCLUDED.gate_pass_end_date_time")
#                     },
#                     where=and_(
#                         IrrReport.gate_pass_end_date_time.is_(None),
#                         text("EXCLUDED.gate_pass_end_date_time IS NOT NULL")
#                     )
#                 ).returning(
#                     text("(xmax = 0)::int AS inserted"),   # 1 for insert, 0 otherwise
#                     text("(xmax <> 0)::int AS updated")    # 1 for update, 0 otherwise
#                 )
                
#                 result = await db.execute(stmt)
#                 rows = result.fetchall()

#                 print("DB Response sample:", rows[:3]) # Debug

#                 inserted_count += sum(row[0] for row in rows)
#                 updated_count  += sum(row[1] for row in rows)

#             # duplicates = total_valid - inserted - updated
#             duplicate_count = len(valid_records) - inserted_count - updated_count

#             await db.commit()

#             #     # result.rowcount gives the number of actually inserted rows
#             #     inserted_count += result.rowcount
            
#             # duplicate_count = len(valid_records) - inserted_count
            
#             # # Step 4: Commit the transaction
#             # await db.commit()

#             # Step 5: Return success response
#             # return {
#             #     'success': True,
#             #     'total_records': total_records,
#             #     'valid_records': len(valid_records),
#             #     'inserted_records': inserted_count,
#             #     'duplicate_records': duplicate_count,
#             #     'skipped_null_oc': skipped_null_oc,
#             #     'status_code': 200,
#             #     'message': f"Successfully inserted {inserted_count} new records for date {cosys_report_date}. {duplicate_count} duplicates skipped. {skipped_null_oc} records skipped due to missing oc_num."
#             # }

#             return {
#                 "success": True,
#                 "date": str(cosys_report_date),
#                 "total_records_in_file": total_records,
#                 "valid_records": len(valid_records),
#                 "inserted_records": inserted_count,
#                 "updated_records": updated_count,
#                 "duplicate_records": duplicate_count,
#                 "skipped_null_oc": skipped_null_oc,
#                 "message": (
#                     f"{inserted_count} new records inserted, "
#                     f"{updated_count} updated (gate_pass_end_date_time filled), "
#                     f"{duplicate_count} duplicates skipped, "
#                     f"{skipped_null_oc} skipped due to missing oc_num."
#                 )
#             }

#         except HTTPException:
#             raise
#         except ValueError as e:
#             raise HTTPException(status_code=400, detail=str(e))
#         except Exception as e:
#             await db.rollback()
#             raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
        
  

# ========================= NEW STRUCTURE two level ============================================= 



import re
import uuid
import time
from typing import Dict, Any
from datetime import date

from sqlalchemy import and_, text
from sqlalchemy.dialects.postgresql import insert
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import HTTPException

from app.db.models.importOperation.import_release_report import IrrReport
from app.utils.importOperation.import_release_cleaner import clean_import_release_file
from app.utils.stable_advisary_dblock_hash import stable_int32_lock_key


# ================== OC UTILITIES ==================

NUMERIC_10_DIGIT_RE = re.compile(r"^\d{10}$")

UUID_HEX_LEN = 20
ALREADY_SUFFIXED_RE = re.compile(rf"-[0-9a-fA-F]{{{UUID_HEX_LEN}}}$")


def generate_oc_uuid_suffix() -> str:
    return uuid.uuid4().hex[:UUID_HEX_LEN]


def is_pure_numeric_10_digit_oc(oc: str) -> bool:
    """
    True only if oc is exactly 10 digits (0–9).
    """
    return bool(NUMERIC_10_DIGIT_RE.fullmatch(oc))


def needs_suffix(oc: str) -> bool:
    """
    OC needs suffix if:
    - contains non-digit chars OR
    - numeric but length != 10
    AND
    - not already suffixed with UUID
    """
    if ALREADY_SUFFIXED_RE.search(oc):
        return False

    if oc.isdigit() and len(oc) == 10:
        return False

    return True


# ================== SERVICE ==================

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

            records = df.to_dict("records")
            total_records = len(records)

            # ─────────────────────────────────────────────
            # 🔥 HANDLE ALPHA / ALPHANUMERIC OC_NUM
            # ─────────────────────────────────────────────

            alpha_indexes = []

            for i, r in enumerate(records):
                oc = r.get("oc_num")

                if not oc:
                    continue

                oc = oc.strip()

                # ✅ Keep pure numeric 10-digit OC as-is
                if is_pure_numeric_10_digit_oc(oc):
                    records[i]["oc_num"] = oc
                    continue

                # 🔁 Re-upload safety (already suffixed)
                if not needs_suffix(oc):
                    continue

                # ❌ Numeric but <10 OR alphanumeric → needs suffix
                alpha_indexes.append(i)

            # ✅ Apply UUID suffixes (NO DB CALL)
            for idx in alpha_indexes:
                original = records[idx]["oc_num"].strip()
                suffix = generate_oc_uuid_suffix()
                records[idx]["oc_num"] = f"{original}-{suffix}"

            for record in records:
                record["cosys_report_date"] = cosys_report_date
                record["uploaded_by"] = uploaded_by

            clean_time = time.time() - clean_start
            print("-Data Cleaning:", clean_time)

            # ─────────────────────────────────────────────
            # 🔒 Advisory Lock
            # ─────────────────────────────────────────────

            table_key = stable_int32_lock_key("irr_report")
            date_key = stable_int32_lock_key(str(cosys_report_date))

            result = await db.execute(
                text("SELECT pg_try_advisory_xact_lock(:key1, :key2)"),
                {"key1": table_key, "key2": date_key},
            )

            lock_acquired = result.scalar()
            if not lock_acquired:
                return {
                    "success": False,
                    "errors": [],
                    "message": "Another process is currently modifying the table...",
                }

            # Step 2: Filter out records with null oc_num
            valid_records = [r for r in records if r.get("oc_num") is not None]
            skipped_null_oc = len(records) - len(valid_records)

            # Step 3: Insert records in batches
            num_columns = len(df.columns)
            max_pg_params = 28000
            batch_size = max_pg_params // num_columns

            inserted_count = 0
            updated_count = 0

            for i in range(0, len(valid_records), batch_size):
                batch = valid_records[i : i + batch_size]

                stmt = (
                    insert(IrrReport)
                    .values(batch)
                    .on_conflict_do_update(
                        index_elements=["gate_pass_no"],
                        set_={
                            "gate_pass_end_date_time": text(
                                "EXCLUDED.gate_pass_end_date_time"
                            )
                        },
                        where=and_(
                            IrrReport.gate_pass_end_date_time.is_(None),
                            text("EXCLUDED.gate_pass_end_date_time IS NOT NULL"),
                        ),
                    )
                    .returning(
                        text("(xmax = 0)::int AS inserted"),
                        text("(xmax <> 0)::int AS updated"),
                    )
                )

                result = await db.execute(stmt)
                rows = result.fetchall()

                inserted_count += sum(row[0] for row in rows)
                updated_count += sum(row[1] for row in rows)

            duplicate_count = len(valid_records) - inserted_count - updated_count

            await db.commit()

            return {
                "success": True,
                "date": str(cosys_report_date),
                "total_records_in_file": total_records,
                "valid_records": len(valid_records),
                "inserted_records": inserted_count,
                "updated_records": updated_count,
                "duplicate_records": duplicate_count,
                "skipped_null_oc": skipped_null_oc,
                "message": (
                    f"{inserted_count} new records inserted, "
                    f"{updated_count} updated, "
                    f"{duplicate_count} duplicates skipped, "
                    f"{skipped_null_oc} skipped due to missing oc_num."
                ),
            }

        except HTTPException:
            raise
        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            await db.rollback()
            raise HTTPException(status_code=500, detail=f"Error processing file: {str(e)}")
