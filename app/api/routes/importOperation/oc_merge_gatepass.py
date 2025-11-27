


# from sqlalchemy.ext.asyncio import AsyncSession
# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy import text
# from typing import List, Dict, Any
# from pydantic import BaseModel
# import logging
# import time

# from app.db.session import get_db

# logger = logging.getLogger(__name__)

# router = APIRouter(prefix="/oc-merge-testing-report", tags=["OC Merge GatePass Testing"])
# # Pydantic Models for Response
# class GatePassTestRecord(BaseModel):
#     awb_no: str
#     hawb: str
#     oc_no: str
#     no_of_pc: int
#     location: str
#     weight_in_kgs: float
#     flight_no: str
#     flight_date: str

# class GatePassTestResponse(BaseModel):
#     success: bool
#     message: str
#     total_records: int
#     sample_records: List[GatePassTestRecord]
#     execution_time: float

# # @router.post("/test-gatepass-generate", response_model=GatePassTestResponse)
# # async def test_gatepass_generate(db: AsyncSession = Depends(get_db)):
# #     """
# #     Generate final gatepass data from OC_REPORT and related tables
# #     CORRECTED FIELD NAMES: hawb_no (oc_report) vs hwb_no (warehouse)
# #     """
# #     start_time = time.time()
    
# #     try:
# #         # CORRECTED QUERY WITH PROPER FIELD NAMES
        
# #         # Execute the query
# #         result = await db.execute(query)
# #         records = result.fetchall()
        
# #         execution_time = round(time.time() - start_time, 2)
        
# #         if not records:
# #             return GatePassTestResponse(
# #                 success=False,
# #                 message="No data found in OC_REPORT table",
# #                 total_records=0,
# #                 sample_records=[],
# #                 execution_time=execution_time
# #             )
        
# #         # Convert to response format
# #         sample_records = []
# #         for record in records:
# #             sample_records.append(GatePassTestRecord(
# #                 awb_no=record.awb_no,
# #                 hawb=record.hawb or "",
# #                 oc_no=record.oc_no,
# #                 no_of_pc=record.no_of_pc,
# #                 location=record.location or "No Location",
# #                 weight_in_kgs=float(record.weight_in_kgs) if record.weight_in_kgs else 0.0,
# #                 flight_no=record.flight_no or "No Flight",
# #                 flight_date=str(record.flight_date) if record.flight_date else "No Date"
# #             ))
        
# #         # Get total count for information
# #         count_query = text("SELECT COUNT(*) as total FROM oc_report")
# #         count_result = await db.execute(count_query)
# #         total_records = count_result.scalar() or 0
        
# #         return GatePassTestResponse(
# #             success=True,
# #             message=f"Successfully generated {len(sample_records)} sample records from {total_records} total OC records",
# #             total_records=total_records,
# #             sample_records=sample_records,
# #             execution_time=execution_time
# #         )
        
# #     except Exception as e:
# #         logger.error(f"Error generating gatepass test data: {str(e)}")
# #         raise HTTPException(
# #             status_code=500, 
# #             detail=f"Failed to generate test data: {str(e)}"
# #         )





# from sqlalchemy.ext.asyncio import AsyncSession
# from fastapi import APIRouter, Depends, HTTPException
# from sqlalchemy import text
# from typing import List, Dict, Any
# from pydantic import BaseModel
# import logging
# import time

# from app.db.session import get_db

# logger = logging.getLogger(__name__)

# router = APIRouter(prefix="/generate-oc-merge-gatepass", tags=[])

# # Pydantic Models for Response
# class GatePassTestRecord(BaseModel):
#     awb_no: str
#     hawb: str
#     oc_no: str
#     no_of_pc: int
#     location: str
#     weight_in_kgs: float
#     flight_no: str
#     flight_date: str
#     irregularity_remarks: str  # ← NEW FIELD

# class GatePassTestResponse(BaseModel):
#     success: bool
#     message: str
#     total_records: int
#     sample_records: List[GatePassTestRecord]
#     execution_time: float

# @router.post("/test-gatepass-generate", response_model=GatePassTestResponse)
# async def test_gatepass_generate(db: AsyncSession = Depends(get_db)):
#     """
#     Generate final gatepass data with IRREGULARITY REMARKS - ERROR FIXED
#     """
#     start_time = time.time()
    
#     try:
#         # CORRECTED QUERY - FIXED STRING_AGG SYNTAX
#         query = text('''
#             WITH warehouse_agg AS (
#                 SELECT 
#                     awb_no,
#                     COALESCE(hwb_no, '') as hwb_no,
#                     -- FIXED: Removed ORDER BY with DISTINCT
#                     STRING_AGG(DISTINCT warehouse_location, ', ') as locations,
#                     -- Weight: All same per AWB+HAWB, take any one
#                     MAX(grs_wgt) as weight,
#                     -- Flight info: All same per AWB+HAWB, take any one
#                     MAX(fltno) as flight_number,
#                     MAX(flt_date) as flight_date_val
#                 FROM import_wherehouse_inventry
#                 GROUP BY awb_no, COALESCE(hwb_no, '')
#             ),
#             irregularity_agg AS (
#                 SELECT 
#                     awb_no,
#                     COALESCE(hwb_no, '') as hwb_no,
#                     -- FIXED: Two options below - choose one:

#                     -- OPTION 1: DISTINCT without ORDER BY (Simple)
#                     STRING_AGG(DISTINCT open_remarks, ' | ') as all_remarks

#                     -- OPTION 2: ORDER BY without DISTINCT (Chronological order)
#                     -- STRING_AGG(open_remarks, ' | ' ORDER BY irr_open_date_time DESC) as all_remarks

#                 FROM irregularity_report
#                 WHERE open_remarks IS NOT NULL 
#                   AND open_remarks != ''
#                 GROUP BY awb_no, COALESCE(hwb_no, '')
#             )
            
#             SELECT 
#                 oc.awb_no,
#                 oc.hawb_no as hawb,
#                 oc.oc_no,
#                 oc.pcs as no_of_pc,
#                 COALESCE(wh.locations, 'No Location') as location,
#                 wh.weight as weight_in_kgs,
#                 wh.flight_number as flight_no,
#                 wh.flight_date_val as flight_date,
#                 COALESCE(irr.all_remarks, 'No Irregularities') as irregularity_remarks
#             FROM oc_report oc
#             LEFT JOIN warehouse_agg wh ON 
#                 oc.awb_no = wh.awb_no 
#                 AND COALESCE(oc.hawb_no, '') = wh.hwb_no
#             LEFT JOIN irregularity_agg irr ON 
#                 oc.awb_no = irr.awb_no 
#                 AND COALESCE(oc.hawb_no, '') = irr.hwb_no
#             ORDER BY oc.awb_no
#             LIMIT 50
#         ''')
        
#         # Execute the query
#         result = await db.execute(query)
#         records = result.fetchall()
        
#         execution_time = round(time.time() - start_time, 2)
        
#         if not records:
#             return GatePassTestResponse(
#                 success=False,
#                 message="No data found in OC_REPORT table",
#                 total_records=0,
#                 sample_records=[],
#                 execution_time=execution_time
#             )
        
#         # Convert to response format
#         sample_records = []
#         for record in records:
#             sample_records.append(GatePassTestRecord(
#                 awb_no=record.awb_no,
#                 hawb=record.hawb or "",
#                 oc_no=record.oc_no,
#                 no_of_pc=record.no_of_pc,
#                 location=record.location or "No Location",
#                 weight_in_kgs=float(record.weight_in_kgs) if record.weight_in_kgs else 0.0,
#                 flight_no=record.flight_no or "No Flight",
#                 flight_date=str(record.flight_date) if record.flight_date else "No Date",
#                 irregularity_remarks=record.irregularity_remarks or "No Irregularities"  # ← ADDED THIS LINE
#             ))
        
#         # Get total count for information
#         count_query = text("SELECT COUNT(*) as total FROM oc_report")
#         count_result = await db.execute(count_query)
#         total_records = count_result.scalar() or 0
        
#         return GatePassTestResponse(
#             success=True,
#             message=f"Successfully generated {len(sample_records)} sample records from {total_records} total OC records",
#             total_records=total_records,
#             sample_records=sample_records,
#             execution_time=execution_time
#         )
        
#     except Exception as e:
#         logger.error(f"Error generating gatepass test data: {str(e)}")
#         raise HTTPException(
#             status_code=500, 
#             detail=f"Failed to generate test data: {str(e)}"
#         )












# @router.get("/test-data-stats")
# async def test_data_stats(db: AsyncSession = Depends(get_db)):
#     """
#     Get statistics about the test data generation with FIELD NAME INFO
#     """
#     try:
#         # Get counts from both tables
#         oc_count_query = text("SELECT COUNT(*) as count FROM oc_report")
#         warehouse_count_query = text("SELECT COUNT(*) as count FROM import_wherehouse_inventry")
        
#         oc_count = await db.execute(oc_count_query)
#         warehouse_count = await db.execute(warehouse_count_query)
        
#         oc_total = oc_count.scalar() or 0
#         warehouse_total = warehouse_count.scalar() or 0
        
#         return {
#             "success": True,
#             "source_tables": {
#                 "oc_report": {
#                     "total_records": oc_total,
#                     "key_fields": {
#                         "awb_field": "awb_no",
#                         "hawb_field": "hawb_no"
#                     }
#                 },
#                 "import_wherehouse_inventry": {
#                     "total_records": warehouse_total,
#                     "key_fields": {
#                         "awb_field": "awb_no", 
#                         "hawb_field": "hwb_no"  # ← DIFFERENT FIELD NAME!
#                     }
#                 }
#             },
#             "join_logic": {
#                 "primary_key": "awb_no + hawb_no/hwb_no",
#                 "join_condition": "oc_report.awb_no = warehouse.awb_no AND oc_report.hawb_no = warehouse.hwb_no",
#                 "join_type": "LEFT JOIN",
#                 "note": "FIELD NAME CORRECTION APPLIED: hawb_no (oc) ↔ hwb_no (warehouse)"
#             }
#         }
        
#     except Exception as e:
#         logger.error(f"Error getting test data stats: {str(e)}")
#         raise HTTPException(status_code=500, detail=str(e))


# ============================================================







from zoneinfo import ZoneInfo
import pytz
from sqlalchemy.ext.asyncio import AsyncSession
from fastapi import APIRouter, Body, Depends, HTTPException, Query
from sqlalchemy import case, literal_column, or_, select, text
from sqlalchemy.dialects.postgresql import insert

from typing import List
import logging
import time
from datetime import datetime, timedelta

from app.db.session import get_db
from app.db.models.importOperation.oc_merge_gatepass import OcMergeGatePass
from app.schemas.importOperation.oc_merge_gatepass import (
    MarkPrintedRequest,
    OcMergeGatePassListResponse,
    OcMergeGatePassResponse
    
)
from app.services.importOperation.igp_number_generator import IGPNumberGenerator
from app.services.importOperation.oc_merge_gatepass import OcMergeGatepassService

from app.utils.common.helperFunction import get_utc_now

logger = logging.getLogger(__name__)

router = APIRouter(prefix="/generate-oc-merge-gatepass", tags=[])

# @router.post("/generate-and-save", response_model=OcMergeGatePassListResponse)
# async def generate_and_save_gatepass(
#     limit: int = Query(10000, description="Number of records to process", le=10000),
#     db: AsyncSession = Depends(get_db)
# ):
#     """
#     SINGLE API: GENERATE AND SAVE GATE PASS RECORDS
    
#     This single API does everything:
#     1. Processes data from OC_REPORT, warehouse, and irregularity tables
#     2. Generates IGP numbers automatically
#     3. Saves all records to database
#     4. Returns saved records with database IDs for printing
    
#     Efficiently handles 500-1000 records in one go.
#     """
#     start_time = time.time()
    
#     try:
#         logger.info(f"Starting direct generate and save for up to {limit} records")
        
#         # Step 1: Process data from all tables
#         query = text('''
#             WITH warehouse_agg AS (
#                 SELECT 
#                     awb_no,
#                     COALESCE(hwb_no, '') as hwb_no,
#                     STRING_AGG(DISTINCT warehouse_location, ', ') as locations,
#                     MAX(grs_wgt) as weight,
#                     MAX(fltno) as flight_number,
#                     MAX(flt_date) as flight_date_val
#                 FROM import_wherehouse_inventry
#                 GROUP BY awb_no, COALESCE(hwb_no, '')
#             ),
#             irregularity_agg AS (
#                 SELECT 
#                     awb_no,
#                     COALESCE(hwb_no, '') as hwb_no,
#                     STRING_AGG(DISTINCT open_remarks, ' | ') as all_remarks
#                 FROM irregularity_report
#                 WHERE open_remarks IS NOT NULL 
#                   AND open_remarks != ''
#                 GROUP BY awb_no, COALESCE(hwb_no, '')
#             )
            
#             SELECT 
#                 oc.awb_no,
#                 oc.hawb_no as hawb,
#                 oc.oc_no,
#                 oc.pcs as no_of_pc,
#                 oc.integrate_date_time as integrate_date_time,
#                 wh.locations as location,
#                 wh.weight as weight_in_kgs,
#                 wh.flight_number as flight_no,
#                 wh.flight_date_val as flight_date,
#                 irr.all_remarks as irregularity_remarks
#             FROM oc_report oc
#             LEFT JOIN warehouse_agg wh ON 
#                 oc.awb_no = wh.awb_no 
#                 AND COALESCE(oc.hawb_no, '') = wh.hwb_no
#             LEFT JOIN irregularity_agg irr ON 
#                 oc.awb_no = irr.awb_no 
#                 AND COALESCE(oc.hawb_no, '') = irr.hwb_no
#             ORDER BY oc.id
#             LIMIT :limit
#         ''')
        
#         result = await db.execute(query, {"limit": limit})
#         processed_records = result.fetchall()
        
#         if not processed_records:
#             execution_time = round(time.time() - start_time, 2)
#             return OcMergeGatePassListResponse(
#                 success=False,
#                 message="No data found to process",
#                 data=[],
#                 total_processed=0,
#                 execution_time=execution_time,
#                 igp_range="None"
#             )
        
#         logger.info(f"Processed {len(processed_records)} records from database, now saving...")
        
#         # Step 2: Generate IGP numbers for all records
#         igp_numbers = await IGPNumberGenerator.generate_bulk_igp_numbers(
#             db, len(processed_records)
#         )
        
#         current_time = datetime.now()
#         saved_records = []
        
#         # Step 3: Save all records to database
#         for i, record in enumerate(processed_records):
#             gatepass_record = OcMergeGatePass(
#                 # Auto-generated fields
#                 igp_no=igp_numbers[i],
#                 igp_print_date_time=current_time,
#                 pd_in_time=None,
                
#                 # Processed data
#                 awb_no=record.awb_no,
#                 hawb=record.hawb or "",
#                 oc_no=record.oc_no,
#                 no_of_pc=record.no_of_pc,
#                 integrate_date_time=record.integrate_date_time,
#                 location=record.location or "",
#                 weight_in_kgs=float(record.weight_in_kgs) if record.weight_in_kgs else 0.0,
#                 flight_no=record.flight_no or "",
#                 flight_date=record.flight_date,
#                 irregularity_remarks=record.irregularity_remarks or "",
                
#                 # Default values
#                 no_of_pc_recd=None,
#                 verified_by="",
#                 agent_name="",
#                 customer_name=""
#             )
            
#             saved_records.append(gatepass_record)
#             db.add(gatepass_record)
        
#         # Single commit for all records
#         await db.commit()
#         logger.info(f"Successfully committed {len(saved_records)} records to database")
        
#         # Refresh to get database IDs
#         for record in saved_records:
#             await db.refresh(record)
        
#         # Convert to response format
#         response_records = [
#                 OcMergeGatePassResponse
# (
#                 id=record.id,
#                 igp_no=record.igp_no,
#                 igp_print_date_time=record.igp_print_date_time,
#                 awb_no=record.awb_no,
#                 hawb=record.hawb,
#                 oc_no=record.oc_no,
#                 no_of_pc=record.no_of_pc,
#                 integrate_date_time=record.integrate_date_time,
#                 location=record.location,
#                 weight_in_kgs=record.weight_in_kgs,
#                 flight_no=record.flight_no,
#                 flight_date=record.flight_date,
#                 irregularity_remarks=record.irregularity_remarks,
#                 pd_in_time=record.pd_in_time,
#                 no_of_pc_recd=record.no_of_pc_recd,
#                 verified_by=record.verified_by,
#                 agent_name=record.agent_name,
#                 customer_name=record.customer_name
#             )
#             for record in saved_records
#         ]
        
#         execution_time = round(time.time() - start_time, 2)
#         first_igp = igp_numbers[0]
#         last_igp = igp_numbers[-1]
        
#         logger.info(f"Direct generate and save completed: {len(response_records)} records in {execution_time}s")
        
#         return OcMergeGatePassListResponse(
#             success=True,
#             message=f"Successfully processed and saved {len(response_records)} gate pass records",
#             total_processed=len(response_records),
#             data=response_records,
#             execution_time=execution_time,
#             igp_range=f"{first_igp} to {last_igp}"
#         )
        
#     except Exception as e:
#         await db.rollback()
#         logger.error(f"Error in direct generate and save: {str(e)}")
#         raise HTTPException(
#             status_code=500, 
#             detail=f"Failed to process and save gate pass records: {str(e)}"
#         )



# ===================================================================================================



# chunk_list stays the same
def chunk_list(data, chunk_size=1000):
    for i in range(0, len(data), chunk_size):
        yield data[i:i + chunk_size]


@router.post("/generate-and-save", response_model=OcMergeGatePassListResponse)
async def generate_and_save_gatepass(
    body: dict = Body(...),
    limit: int = Query(8000, le=8000),
    db: AsyncSession = Depends(get_db)
):
    date = body.get("date")
    start_time = time.time()

    try:
        # 1️⃣ Convert IST → UTC
        ist_zone = ZoneInfo("Asia/Kolkata")
        utc_zone = ZoneInfo("UTC")

        selected_date_ist = datetime.strptime(date, "%Y-%m-%d").replace(tzinfo=ist_zone)
        ist_start = selected_date_ist.replace(hour=0, minute=0, second=0, microsecond=0)
        ist_end = ist_start + timedelta(days=1) - timedelta(seconds=1)

        utc_start = ist_start.astimezone(utc_zone)
        utc_end = ist_end.astimezone(utc_zone)

        # 2️⃣ Count rows in oc_report
        count_query = text("""
            SELECT COUNT(*) 
            FROM oc_report 
            WHERE integrate_date_time BETWEEN :utc_start AND :utc_end
        """)
        total_records_in_oc_report = (
            (await db.execute(count_query, {"utc_start": utc_start, "utc_end": utc_end}))
            .scalar() or 0
        )

        # 3️⃣ Fetch source data
        query = text("""
            WITH warehouse_agg AS (
                SELECT 
                    awb_no,
                    COALESCE(hwb_no, '') AS hwb_no,
                    STRING_AGG(warehouse_location || '/' || pcs::text, ', ') AS location_pcs_pairs,
                    SUM(grs_wgt) AS weight,
                    MAX(fltno) AS flight_number,
                    MAX(flt_date) AS flight_date_val,
                    MAX(shc) AS shc,
                    MAX(cne_name) AS cne_name 
                FROM import_wherehouse_inventry
                GROUP BY awb_no, COALESCE(hwb_no, '')
            ),
            irregularity_agg AS (
                SELECT 
                    awb_no,
                    COALESCE(hwb_no, '') AS hwb_no,
                    STRING_AGG( open_remarks, ' | ') AS all_remarks,
                    STRING_AGG( irr_code, ' | ') AS all_irr_codes 
                FROM irregularity_report
                WHERE open_remarks IS NOT NULL AND open_remarks != ''
                GROUP BY awb_no, COALESCE(hwb_no, '')
            )
            SELECT 
                oc.awb_no,
                oc.hawb_no AS hawb,
                oc.oc_no,
                oc.pcs AS no_of_pc,
                oc.integrate_date_time,
                wh.location_pcs_pairs AS locations,
                wh.weight AS weight_in_kgs,
                wh.cne_name AS cne_name ,
                wh.flight_number AS flight_no,
                wh.flight_date_val AS flight_date,
                irr.all_remarks AS irregularity_remarks,
                irr.all_irr_codes AS irr_codes,
                wh.shc AS shc
            FROM oc_report oc
            LEFT JOIN warehouse_agg wh 
                ON oc.awb_no = wh.awb_no AND COALESCE(oc.hawb_no, '') = wh.hwb_no
            LEFT JOIN irregularity_agg irr 
                ON oc.awb_no = irr.awb_no AND COALESCE(oc.hawb_no, '') = irr.hwb_no
            WHERE oc.integrate_date_time BETWEEN :utc_start AND :utc_end
            ORDER BY oc.id
            LIMIT :limit
        """)

        result = await db.execute(query, {
            "utc_start": utc_start,
            "utc_end": utc_end,
            "limit": limit
        })
        records = result.fetchall()

        # ------------------------------------------
        # 4️⃣ FILTER — Skip OCs already in irr_report
        # ------------------------------------------

        base_oc_list = [r.oc_no for r in records]

        if base_oc_list:
            release_query = text("""
                SELECT DISTINCT oc_num 
                FROM irr_report
                WHERE oc_num = ANY(:oc_list)
            """)

            release_res = await db.execute(release_query, {"oc_list": base_oc_list})
            released_oc_set = {row.oc_num for row in release_res.fetchall()}
        else:
            released_oc_set = set()

        # Keep only OCs NOT present in irr_report
        records = [r for r in records if r.oc_no not in released_oc_set]

        if not records:
            return OcMergeGatePassListResponse(
                success=True,
                message=f"No pending OC numbers. All already processed in irr_report.",
                data=[],
                total_processed=0,
                execution_time=round(time.time() - start_time, 2),
                igp_range="None"
            )

        # 5️⃣ Pre-detect existing oc_no
        oc_nos = [r.oc_no for r in records]
        existing_map = {}

        for oc_chunk in chunk_list(oc_nos, 1000):
            q = select(OcMergeGatePass.oc_no, OcMergeGatePass.igp_no).where(
                OcMergeGatePass.oc_no.in_(oc_chunk)
            )
            res = await db.execute(q)
            for row in res.fetchall():
                existing_map[row.oc_no] = row.igp_no

        # 6️⃣ Prepare inserts/updates
        to_insert = []
        to_update = []

        for r in records:
            base = {
                "igp_no": None,
                "igp_print_date_time": None,
                "pd_in_time": None,
                "flight_no": r.flight_no or "",
                "awb_no": r.awb_no,
                "hawb": r.hawb ,# we want to keep hawb as NULL if it's NULL
                "oc_no": r.oc_no,
                "flight_date": r.flight_date,
                "no_of_pc": r.no_of_pc,
                "weight_in_kgs": float(r.weight_in_kgs) if r.weight_in_kgs is not None else None,
                "location": r.locations or None,
                "irregularity_remarks": r.irregularity_remarks or None,
                "irr_codes": r.irr_codes or None,  # ✅ ADD THIS LINE
                "shc": r.shc or None,
                "no_of_pc_recd": None,
                "verified_by": "",
                "agent_name": "",
                
                "integrate_date_time": r.integrate_date_time,
                "customer_name": r.cne_name or "",

                "updated_at": get_utc_now(),  # ✅ Set manually

            }

            if r.oc_no in existing_map:
                base["igp_no"] = existing_map[r.oc_no]
                base["created_at"] = None
                to_update.append(base)
            else:
                base["created_at"] = get_utc_now()  # ✅ Set manually # ✅ For inserts: DO set created_at
                to_insert.append(base)

        # 7️⃣ Generate IGP numbers for new rows
        new_igp_list = []
        if to_insert:
            new_igp_list = await IGPNumberGenerator.generate_bulk_igp_numbers(db, len(to_insert))
           
            for i, rec in enumerate(to_insert):
                rec["igp_no"] = new_igp_list[i]
                rec["igp_print_date_time"] = None  # Set later during actual print

        # 8️⃣ UPSERT - Update only NULL or empty fields
        payload = to_insert + to_update
        total_inserted = 0
        total_updated = 0
        returned_rows = []

        for batch_no, batch in enumerate(chunk_list(payload, 1000), start=1):
            stmt = (
                insert(OcMergeGatePass)
                .values(batch)
                .on_conflict_do_update(
                    index_elements=["oc_no"],
                    set_={
                        # Update location only if existing is NULL or empty
                        "location": case(
                            (
                                or_(
                                    OcMergeGatePass.location.is_(None),
                                    OcMergeGatePass.location == ''
                                ),
                                insert(OcMergeGatePass).excluded.location
                            ),
                            else_=OcMergeGatePass.location
                        ),
                        
                        # Update weight only if existing is NULL
                        "weight_in_kgs": case(
                            (
                                OcMergeGatePass.weight_in_kgs.is_(None),
                                insert(OcMergeGatePass).excluded.weight_in_kgs
                            ),
                            else_=OcMergeGatePass.weight_in_kgs
                        ),
                        
                        # Update flight_no only if existing is NULL or empty
                        "flight_no": case(
                            (
                                or_(
                                    OcMergeGatePass.flight_no.is_(None),
                                    OcMergeGatePass.flight_no == ''
                                ),
                                insert(OcMergeGatePass).excluded.flight_no
                            ),
                            else_=OcMergeGatePass.flight_no
                        ),
                        
                        # Update flight_date only if existing is NULL
                        "flight_date": case(
                            (
                                OcMergeGatePass.flight_date.is_(None),
                                insert(OcMergeGatePass).excluded.flight_date
                            ),
                            else_=OcMergeGatePass.flight_date
                        ),
                        
                        # Update shc only if existing is NULL or empty
                        "shc": case(
                            (
                                or_(
                                    OcMergeGatePass.shc.is_(None),
                                    OcMergeGatePass.shc == ''
                                ),
                                insert(OcMergeGatePass).excluded.shc
                            ),
                            else_=OcMergeGatePass.shc
                        ),
                        
                        # Update irregularity_remarks only if existing is NULL or empty
                        "irregularity_remarks": case(
                            (
                                or_(
                                    OcMergeGatePass.irregularity_remarks.is_(None),
                                    OcMergeGatePass.irregularity_remarks == ''
                                ),
                                insert(OcMergeGatePass).excluded.irregularity_remarks
                            ),
                            else_=OcMergeGatePass.irregularity_remarks
                        ),
                        
                        # Update irr_codes only if existing is NULL or empty
                        "irr_codes": case(
                            (
                                or_(
                                    OcMergeGatePass.irr_codes.is_(None),
                                    OcMergeGatePass.irr_codes == ''
                                ),
                                insert(OcMergeGatePass).excluded.irr_codes
                            ),
                            else_=OcMergeGatePass.irr_codes
                        ),

                        "customer_name": case(
                            (
                                or_(
                                    OcMergeGatePass.customer_name.is_(None),
                                    OcMergeGatePass.customer_name == ''
                                ),
                                insert(OcMergeGatePass).excluded.customer_name
                            ),
                            else_=OcMergeGatePass.customer_name
                        ),
                        "updated_at": insert(OcMergeGatePass).excluded.updated_at
                                            }
                )
                .returning(
                    OcMergeGatePass.id,
                    *OcMergeGatePass.__table__.c,
                    literal_column("xmax").label("xmax")
                )
            )

            result = await db.execute(stmt)
            rows = result.fetchall()
            await db.commit()

            returned_rows.extend(rows)

            total_inserted += sum(1 for r in rows if r.xmax == 0)
            total_updated += sum(1 for r in rows if r.xmax != 0)        

        # # 8️⃣ UPSERT
        # payload = to_insert + to_update
        # total_inserted = 0
        # total_updated = 0
        # returned_rows = []

        # for batch_no, batch in enumerate(chunk_list(payload, 1000), start=1):
        #     stmt = (
        #         insert(OcMergeGatePass)
        #         .values(batch)
        #         .on_conflict_do_update(
        #             index_elements=["oc_no"],
        #             set_={
        #                 "location": insert(OcMergeGatePass).excluded.location,
        #                 "weight_in_kgs": insert(OcMergeGatePass).excluded.weight_in_kgs,
        #                 "flight_no": insert(OcMergeGatePass).excluded.flight_no,
        #                 "flight_date": insert(OcMergeGatePass).excluded.flight_date,
        #                 "shc": insert(OcMergeGatePass).excluded.shc,
        #                 "irregularity_remarks": insert(OcMergeGatePass).excluded.irregularity_remarks,
        #                 "irr_codes": insert(OcMergeGatePass).excluded.irr_codes, 
        #             }
        #         )
        #         .returning(
        #             OcMergeGatePass.id,
        #             *OcMergeGatePass.__table__.c,
        #             literal_column("xmax").label("xmax")
        #         )
        #     )

        #     result = await db.execute(stmt)
        #     rows = result.fetchall()
        #     await db.commit()

        #     returned_rows.extend(rows)

        #     total_inserted += sum(1 for r in rows if r.xmax == 0)
        #     total_updated += sum(1 for r in rows if r.xmax != 0)

        # 9️⃣ Response
        execution_time = round(time.time() - start_time, 2)
        igp_range = f"{new_igp_list[0]} → {new_igp_list[-1]}" if new_igp_list else "None"

        response_data = [OcMergeGatePassResponse.model_validate(dict(r._mapping)) for r in returned_rows]

        return OcMergeGatePassListResponse(
            success=True,
            message=f"Completed for {date}. Inserted: {total_inserted}, Updated: {total_updated}.",
            data=response_data,
            total_processed=total_inserted + total_updated,
            execution_time=execution_time,
            igp_range=igp_range
        )

    except Exception as e:
        await db.rollback()
        logger.exception("Error during generate-and-save")
        raise HTTPException(status_code=500, detail=str(e))



# ---------------------------------

@router.get("/gatepass-by-date-range", response_model=dict)
async def get_gatepass_by_date_range(
    start_date: str = Query(..., description="Start date in YYYY-MM-DD format"),
    end_date: str = Query(..., description="End date in YYYY-MM-DD format"),
    db: AsyncSession = Depends(get_db)
):
    """
    Get all OcMergeGatePass records by date range (no pagination)
    Based on integrate_date_time.
    Frontend sends date in IST; convert 00:00 IST → UTC.
    Excludes records containing GF_03, GF_05, GF_10 in location field.
    """
    try:
        # Parse and validate input
        try:
            ist = pytz.timezone("Asia/Kolkata")

            # start_date: 00:00 IST → convert to UTC
            start_naive = datetime.strptime(start_date, "%Y-%m-%d")
            start_ist = ist.localize(start_naive.replace(hour=0, minute=0, second=0, microsecond=0))
            start_dt = start_ist.astimezone(pytz.UTC)

            # end_date: 23:59:59.999999 IST → convert to UTC
            end_naive = datetime.strptime(end_date, "%Y-%m-%d")
            end_ist = ist.localize(end_naive.replace(hour=23, minute=59, second=59, microsecond=999999))
            end_dt = end_ist.astimezone(pytz.UTC)

        except ValueError:
            raise HTTPException(
                status_code=400, 
                detail="Invalid date format. Use YYYY-MM-DD"
            )

        # Validation
        if start_dt > end_dt:
            raise HTTPException(
                status_code=400,
                detail="Start date cannot be after end date"
            )

        # Fetch records from service
        gatepass_records = await OcMergeGatepassService.get_gatepass_by_date_range(
            db=db,
            start_date=start_dt,
            end_date=end_dt
        )

        # 🆕 Define locations to exclude
        # excluded_locations = ["GF_03", "GF_05", "GF_10"]/
        excluded_locations = ["GF_03", "GF_05", "GF_10", "IGF_1_A","IGF_21_A"]
        # Prefix match exclusions (starts with)
        excluded_location_prefixes = {
            "ISR",       # e.g., GF_01, GF_11_A, etc.
            "IUC",      # Example if needed later
            "TDP",      # Example if needed later
            "PI"
        }
        excluded_irr_codes = ["SSPD", "FDCA"] # eclude these irr_codes rows as well
        excluded_shc_values = ["per", "val", "hum","dgr"]  # 🚨 Case-sensitive exact match
        
        # 🆕 Filter records - exclude any record that contains excluded locations in location field
        filtered_records = []
        excluded_records = []  # 🆕 Store excluded records with their OC numbers
        
        for record in gatepass_records:
            exclude_flag = False  # 🆕 Track if record should be excluded

            # --- Check for excluded locations ---
           

            
            
            if record.location:
                # Extract first part and uppercase for consistent comparison
                location_prefix = record.location.split("/")[0].strip().upper()

                # -------- EXACT MATCH CHECK --------
                if location_prefix in (loc.upper() for loc in excluded_locations):
                    exclude_flag = True

                # -------- PREFIX MATCH CHECK --------
                if any(location_prefix.startswith(prefix.upper()) for prefix in excluded_location_prefixes):
                    exclude_flag = True

            # if record.location:
            #     location_prefix = str(record.location).split("/")[0].strip().upper()
            #     if location_prefix in (loc.upper() for loc in excluded_locations):
            #         exclude_flag = True

            # --- Check for excluded SHC values (case-insensitive exact match) ---
            if record.shc:
                shc_value = str(record.shc).strip().upper()
                if shc_value in (val.upper() for val in excluded_shc_values):
                    exclude_flag = True
            
            # --- Check for excluded irr_codes ---
            # # --- Exclude by IRR Codes ---
            if record.irr_codes:
                irr_values = [v.strip().upper() for v in str(record.irr_codes).split("|")]
                if any(code.upper() in irr_values for code in excluded_irr_codes):
                    exclude_flag = True


            if exclude_flag:
                excluded_records.append(record)
                continue  # Skip this record

            filtered_records.append(record)
        # 🆕 Extract excluded OC numbers
        excluded_oc_nos = [record.oc_no for record in excluded_records if record.oc_no]

        # Build response only with filtered records
        records_data = []
        for record in filtered_records:
            record_dict = {
                "id": record.id,
                "igp_no": record.igp_no,
                "oc_no": record.oc_no,
                "awb_no": record.awb_no,
                "hawb": record.hawb,
                "no_of_pc": record.no_of_pc,
                "weight_in_kgs": record.weight_in_kgs,
                "location": record.location,
                "flight_no": record.flight_no,
                "flight_date": record.flight_date.isoformat() if record.flight_date else None,
                
                "irregularity_remarks": record.irregularity_remarks,
                "pd_in_time": record.pd_in_time.isoformat() if record.pd_in_time else None,
                "no_of_pc_recd": record.no_of_pc_recd,
                "verified_by": record.verified_by,
                "agent_name": record.agent_name,
                "customer_name": record.customer_name,
                "release_zone": record.release_zone,
                "integrate_date_time": record.integrate_date_time.isoformat() if record.integrate_date_time else None,
                "shc": record.shc,
                "igp_print_date_time": record.igp_print_date_time.isoformat() if record.igp_print_date_time else None,
                "irr_codes": record.irr_codes,
                "is_printed": record.is_printed
            }
            records_data.append(record_dict)

        total_count = len(records_data)
        excluded_count = len(excluded_records)
        original_count = len(gatepass_records)

        return {
            "success": True,
            "data": records_data,
            "total_records": total_count,
            "date_range": {
                "start_date": start_date,
                "end_date": end_date
            },
            "filter_info": {
                "excluded_locations": excluded_locations,
                "excluded_shc_values": excluded_shc_values,  # 🆕
                "original_count": original_count,
                "filtered_count": total_count,
                "excluded_count": excluded_count,
                "excluded_oc_nos": excluded_oc_nos,  # 🆕 Include excluded OC numbers
                "excluded_oc_nos_count": len(excluded_oc_nos)  # 🆕 Count of excluded OC numbers
            },
            "message": f"Found {total_count} records between {start_date} and {end_date} (excluded {excluded_count} records containing GF_03, GF_05, or GF_10)"
        }

    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Internal server error: {str(e)}")


# ----------------------------------------------------------------
# @router.post("/mark-printed")
# async def mark_igp_printed(
#     request: MarkPrintedRequest,
#     db: AsyncSession = Depends(get_db)
# ):
#     updated_count = await OcMergeGatepassService.update_igp_print_status_and_datetime(db, request.oc_nos)
    
#     if updated_count == 0:
#         raise HTTPException(status_code=404, detail="No matching records found")

#     return {
#         "message": "IGP print status updated successfully",
#         "total_records_updated": updated_count
#     }

# --------------------------------------------------------------------------------


@router.post("/mark-printed")
async def mark_igp_printed(
    request: MarkPrintedRequest,
    db: AsyncSession = Depends(get_db)
):
    updated_rows = await OcMergeGatepassService.update_igp_print_status_and_datetime(db, request.oc_nos)
    
    if not updated_rows:
        raise HTTPException(status_code=404, detail="No matching records found")

    return {
        "message": "IGP print status updated successfully",
        "total_records_updated": len(updated_rows),
        "updated_rows": updated_rows
    }

