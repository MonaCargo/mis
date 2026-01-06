

from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy import select, and_, or_, text, func, case, literal_column
from sqlalchemy.dialects.postgresql import insert
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple
import uuid
import time
from pydantic import BaseModel

from app.db.models.importOperation.oc_merge_gatepass import OcMergeGatePass
from app.services.importOperation.igp_number_generator import IGPNumberGenerator
from app.utils.importOperation.temp_irm_oc_file_cleaner import clean_and_parse_fast_track_file


# ═══════════════════════════════════════════════════════════════
# RESPONSE MODELS
# ═══════════════════════════════════════════════════════════════

class OcMergeGatePassResponse(BaseModel):
    """Individual record response"""
    id: int
    igp_no: str
    awb_no: str
    hawb: Optional[str]
    oc_no: str
    no_of_pc: Optional[int]
    flight_no: Optional[str]
    location: Optional[str]
    customer_name: Optional[str]
    
    class Config:
        from_attributes = True


class FastTrackUploadResponse(BaseModel):
    """Complete upload response matching generate-and-save API pattern"""
    success: bool
    message: str
    data: List[OcMergeGatePassResponse]
    total_records: int  # ← Change from total_processed
    inserted_records: int  # ← Change from total_inserted
    total_updated: int
    skipped_existing_unchanged: int
    skipped_duplicates_in_file: int
    failed_records: int
    execution_time: float
    igp_range: str
    batch_id: str
    errors: List[Dict[str, Any]] = []


# ═══════════════════════════════════════════════════════════════
# UTILITY FUNCTIONS
# ═══════════════════════════════════════════════════════════════

def chunk_list(data: List, size: int):
    """Split list into chunks"""
    for i in range(0, len(data), size):
        yield data[i:i + size]


def get_utc_now():
    """Get current UTC time"""
    return datetime.utcnow()


# ═══════════════════════════════════════════════════════════════
# MAIN SERVICE CLASS
# ═══════════════════════════════════════════════════════════════

class FastTrackIrmTemporaryOcMergeService:
    
    @staticmethod
    async def generate_temp_oc_no(db: AsyncSession) -> str:
        """
        Generate unique 10-digit temporary OC number using PostgreSQL sequence.
        Format: 9XXXXXXXXX (starts with 9, followed by 9 digits)
        Range: 9000000001 to 9999999999
        """
        try:
            # Ensure sequence exists
            await db.execute(text("""
                CREATE SEQUENCE IF NOT EXISTS temp_oc_seq
                START WITH 9000000001
                INCREMENT BY 1
                MINVALUE 9000000001
                MAXVALUE 9999999999
                CACHE 10
            """))
            
            # Get next value
            result = await db.execute(text("SELECT nextval('temp_oc_seq')"))
            temp_oc = result.scalar()
            
            return str(temp_oc)
        except Exception as e:
            raise Exception(f"Failed to generate temporary OC: {str(e)}")


    @staticmethod
    async def bulk_create_from_file(
        db: AsyncSession,
        file,
        file_type: str,
        uploaded_by: str
    ) -> FastTrackUploadResponse:
        """
        ═══════════════════════════════════════════════════════════════
        COMPLETE BULK UPLOAD SERVICE - FOLLOWING generate-and-save PATTERN
        ═══════════════════════════════════════════════════════════════
        
        📋 PROCESS FLOW:
        1. Parse Excel/CSV file
        2. Detect duplicates within file
        3. Check existing records using AWB+HAWB index (uq_awb_hawb)
        4. Enrich data from Warehouse Inventory (aggregated)
        5. Enrich data from Irregularity Report (aggregated)
        6. Generate temporary OC numbers for NEW records only
        7. Generate IGP numbers for NEW records only
        8. UPSERT with conditional updates (only NULL/empty fields)
        9. Track inserted vs updated using xmax
        10. Return comprehensive response
        
        ✅ USES COMPOSITE UNIQUE INDEX: (awb_no, COALESCE(hawb, ''))
        """
        
        batch_id = str(uuid.uuid4())
        start_time = time.time()
        errors = []

        # it check that if not get data like loc weigts then no need to create temp oc 
        def has_meaningful_data(base: dict) -> bool:
            return any([
                base.get("location"),
                base.get("no_of_pc"),
                base.get("weight_in_kgs")
            ])

        
        try:
            # ═══════════════════════════════════════════════════════════════
            # STEP 1: Parse and Validate File
            # ═══════════════════════════════════════════════════════════════
            df = clean_and_parse_fast_track_file(file, file_type)
            records = df.to_dict("records")
            total_records_in_file = len(records)

            if total_records_in_file == 0:
                return FastTrackUploadResponse(
                    success=False,
                    message="No valid records found in the file",
                    data=[],
                  total_records=0,  # ← Changed
                   inserted_records=0,  # ← Changed
                    total_updated=0,
                    skipped_existing_unchanged=0,
                    skipped_duplicates_in_file=0,
                    failed_records=0,
                    execution_time=round(time.time() - start_time, 2),
                    igp_range="None",
                    batch_id=batch_id,
                    errors=[]
                )

            # ═══════════════════════════════════════════════════════════════
            # STEP 2: Detect Duplicates Within File & Build Unique Pairs
            # ═══════════════════════════════════════════════════════════════
            seen_in_file = {}
            unique_records = []
            skipped_duplicates_in_file = 0
            
            for idx, record in enumerate(records):
                awb = record.get("awb_no")
                hawb = record.get("hawb") or None  # Normalize: empty -> None
                
                if not awb:
                    errors.append({
                        "row": idx + 1,
                        "error": "Missing AWB number"
                    })
                    continue
                
                # Create key matching the index: (awb_no, COALESCE(hawb, ''))
                key = (awb, hawb if hawb else None)
                
                # Check for duplicates within file
                if key in seen_in_file:
                    skipped_duplicates_in_file += 1
                    continue
                
                seen_in_file[key] = idx + 1
                unique_records.append({
                    "awb_no": awb,
                    "hawb": hawb,
                    "row": idx + 1,
                    **record
                })

            # ═══════════════════════════════════════════════════════════════
            # STEP 3: Fetch Enrichment Data (Warehouse + IRR)
            # Using CTEs like generate-and-save API
            # ═══════════════════════════════════════════════════════════════
            awb_list = list(set([r["awb_no"] for r in unique_records]))
            
            enrichment_query = text("""
                WITH warehouse_agg AS (
                    SELECT 
                        awb_no,
                        COALESCE(hwb_no, '') AS hwb_no,
                        STRING_AGG(warehouse_location || '/' || pcs::text, ', ') AS location_pcs_pairs,
                        SUM(grs_wgt) AS weight,
                        SUM(wgt_chg) AS chg_wgt_in_kg,
                                    
                        SUM(pcs) AS total_pcs,
                                    
                        MAX(fltno) AS flight_number,
                        MAX(flt_date) AS flight_date_val,
                        MAX(shc) AS shc,
                        MAX(cne_name) AS cne_name,
                        MAX(agent) AS agent_name
                    FROM import_wherehouse_inventry
                    WHERE awb_no = ANY(:awb_list)
                    GROUP BY awb_no, COALESCE(hwb_no, '')
                ),
                irregularity_agg AS (
                    SELECT 
                        awb_no,
                        COALESCE(hwb_no, '') AS hwb_no,
                        STRING_AGG(open_remarks, ' | ') AS all_remarks,
                        STRING_AGG(irr_code, ' | ') AS all_irr_codes 
                    FROM irregularity_report
                    WHERE awb_no = ANY(:awb_list)
                        AND open_remarks IS NOT NULL 
                        AND open_remarks != ''
                    GROUP BY awb_no, COALESCE(hwb_no, '')
                )
                SELECT 
                    wh.awb_no,
                    wh.hwb_no,
                    wh.location_pcs_pairs,
                    wh.weight,
                    wh.total_pcs,
                    wh.chg_wgt_in_kg,
                    wh.flight_number,
                    wh.flight_date_val,
                    wh.shc,
                    wh.cne_name,
                    wh.agent_name,
                    irr.all_remarks,
                    irr.all_irr_codes
                FROM warehouse_agg wh
                LEFT JOIN irregularity_agg irr 
                    ON wh.awb_no = irr.awb_no AND wh.hwb_no = irr.hwb_no
            """)
            
            enrichment_result = await db.execute(enrichment_query, {"awb_list": awb_list})
            enrichment_rows = enrichment_result.fetchall()

            print(f"Column names: {enrichment_result.keys()}")
            
            # Create enrichment map: (awb, hawb) -> data
            enrichment_map = {}
            for row in enrichment_rows:
                hawb_key = row.hwb_no if row.hwb_no else None
                key = (row.awb_no, hawb_key)
                enrichment_map[key] = {
                    "location": row.location_pcs_pairs,
                    "weight_in_kgs": float(row.weight) if row.weight is not None else None,
                    "chg_wgt_in_kg": float(row.chg_wgt_in_kg) if row.chg_wgt_in_kg is not None else None,
                    "total_pcs": int(row.total_pcs) if row.total_pcs is not None else None,
                    "flight_no": row.flight_number,
                    "flight_date": row.flight_date_val,
                    "shc": row.shc,
                    "customer_name": row.cne_name,
                    "agent_name": row.agent_name,
                    "irregularity_remarks": row.all_remarks,
                    "irr_codes": row.all_irr_codes
                }

            # ═══════════════════════════════════════════════════════════════
            # STEP 4: Check Existing Records Using AWB+HAWB Index
            # Query uses: (awb_no, COALESCE(hawb, ''))
            # ═══════════════════════════════════════════════════════════════
            awb_hawb_pairs = [(r["awb_no"], r["hawb"]) for r in unique_records]
            
            # Build conditions matching the unique index
            conditions = []
            for awb, hawb in awb_hawb_pairs:
                hawb_value = hawb if hawb else ''
                conditions.append(
                    and_(
                        OcMergeGatePass.awb_no == awb,
                        func.coalesce(OcMergeGatePass.hawb, '') == hawb_value
                    )
                )
            
            # Query existing records in chunks
            existing_map = {}
            for condition_chunk in chunk_list(conditions, 500):
                query = select(
                    OcMergeGatePass.awb_no,
                    OcMergeGatePass.hawb,
                    OcMergeGatePass.oc_no,
                    OcMergeGatePass.igp_no
                ).where(or_(*condition_chunk))
                
                result = await db.execute(query)
                for row in result.fetchall():
                    hawb_key = row.hawb if row.hawb else None
                    key = (row.awb_no, hawb_key)
                    existing_map[key] = {
                        "oc_no": row.oc_no,
                        "igp_no": row.igp_no
                    }

            # ═══════════════════════════════════════════════════════════════
            # STEP 5: Generate Temp OC & IGP for NEW Records
            # ═══════════════════════════════════════════════════════════════
            to_insert = []
            to_update = []
            current_time = get_utc_now()

            # ✅ INITIALIZE COUNTERS EARLY
            skipped_existing_unchanged = 0

            
            for record in unique_records:
                awb = record["awb_no"]
                hawb = record["hawb"]
                key = (awb, hawb)

                # 🚨 HARD VALIDATION: integrate_date_time is mandatory
                if not record.get("integrate_date_time"):
                    errors.append({
                        "row": record["row"],
                        "awb_no": awb,
                        "hawb": hawb,
                        "error": "Missing integrate_date_time"
                    })
                    continue

                
                # Get enrichment data
                enrichment = enrichment_map.get(key, {})
                
                # Merge data: Excel > Enrichment > Default
                def get_value(excel_key, enrichment_key, default=None):
                    excel_val = record.get(excel_key)
                    if excel_val is not None and excel_val != '':
                        return excel_val
                    enrich_val = enrichment.get(enrichment_key)
                    if enrich_val is not None and enrich_val != '':
                        return enrich_val
                    return default
                
                base = {
                    "awb_no": awb,
                    "hawb": hawb,  # Keep as None if None
                    "location": get_value("location", "location"),
                    "weight_in_kgs": get_value("weight_in_kgs", "weight_in_kgs"),
                    "chg_wgt_in_kg": get_value("chg_wgt_in_kg", "chg_wgt_in_kg"),
                    "no_of_pc": get_value("no_of_pc", "total_pcs"),
                    "flight_no": get_value("flight_no", "flight_no", ""),
                    "flight_date": get_value("flight_date", "flight_date"),
                    "shc": get_value("shc", "shc"),
                    "customer_name": get_value("customer_name", "customer_name", ""),
                    "agent_name": get_value("agent_name", "agent_name", ""),
                    "irregularity_remarks": get_value("irregularity_remarks", "irregularity_remarks"),
                    "integrate_date_time": get_value("integrate_date_time", None),  # ← ADD THIS
                    "irr_codes": get_value("irr_codes", "irr_codes"),
                    "igp_print_date_time": None,
                    "pd_in_time": None,
                    "no_of_pc_recd": None,
                    "verified_by": "",
                    "updated_at": current_time,
                    "uploaded_by": uploaded_by,
                     # ✅ ADD THESE
                    "is_temp_irm_oc": False,
                    "temp_irm_oc_no": None
                }

                # 🚫 NEW HARD BUSINESS RULE
                if not has_meaningful_data(base):
                    skipped_existing_unchanged += 1
                    errors.append({
                        "row": record["row"],
                        "awb_no": awb,
                        "hawb": hawb,
                        "error": "Skipped: No shipment data found (location / pcs / weight missing)"
                    })
                    continue
                
                if key in existing_map:
                    # EXISTING RECORD → UPDATE ONLY
                    if key not in enrichment_map:
                        skipped_existing_unchanged += 1   # ✅ ADD THIS LINE
                    base.update({
                        "oc_no": existing_map[key]["oc_no"],
                        "igp_no": existing_map[key]["igp_no"],
                        "created_at": None
                        # ❗ DO NOT TOUCH temp_irm_oc_no
                        # ❗ DO NOT TOUCH is_temp_irm_oc
                    })
                    to_update.append(base)

                else:
                    # NEW RECORD → CREATE TEMP OC
                    try:
                        temp_oc = await FastTrackIrmTemporaryOcMergeService.generate_temp_oc_no(db)

                        base.update({
                            "oc_no": temp_oc,
                            "temp_irm_oc_no": temp_oc,
                            "is_temp_irm_oc": True,
                            "igp_no": None,
                            "created_at": current_time,
                            "uploaded_by":uploaded_by,
                        })
                        to_insert.append(base)

                    except Exception as e:
                        errors.append({
                            "row": record["row"],
                            "awb_no": awb,
                            "hawb": hawb,
                            "error": f"Failed to generate temp OC: {str(e)}"
                        })

            # ═══════════════════════════════════════════════════════════════
            # STEP 6: Generate IGP Numbers for NEW Records
            # ═══════════════════════════════════════════════════════════════
            new_igp_list = []
            if to_insert:
                new_igp_list = await IGPNumberGenerator.generate_bulk_igp_numbers(db, len(to_insert))
                
                for i, rec in enumerate(to_insert):
                    rec["igp_no"] = new_igp_list[i]

            # ═══════════════════════════════════════════════════════════════
            # STEP 7: UPSERT with Conditional Updates
            # Uses composite unique index: (awb_no, COALESCE(hawb, ''))
            # Only updates NULL or empty fields (same as generate-and-save)
            # ═══════════════════════════════════════════════════════════════
            payload = to_insert + to_update
            total_inserted = 0
            total_updated = 0
            returned_rows = []

            for batch in chunk_list(payload, 1000):
                stmt = (
                    insert(OcMergeGatePass)
                    .values(batch)
                    .on_conflict_do_update(
                        # Use the composite unique index
                        index_elements=[
                            "awb_no",
                            text("COALESCE(hawb, '')")
                        ],
                        set_={
                            # --- NEVER OVERWRITE temp_irm_oc_no (keep history) ---
                            "temp_irm_oc_no": OcMergeGatePass.temp_irm_oc_no,
                            "uploaded_by": OcMergeGatePass.uploaded_by,

                            
                            # ---------------

                             # 2️⃣ (THINK ABOUT THIS IS FALLOW CORRECT FLOW IF DO THIS CONDITION) ❌ ❌❌❌ When real oc_no arrives → make is_temp_irm_oc = False
                            "is_temp_irm_oc": case(
                                (
                                    insert(OcMergeGatePass).excluded.oc_no.isnot(None),
                                    False
                                ),
                                else_=OcMergeGatePass.is_temp_irm_oc
                            ),

                            #  -----------

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

                            "chg_wgt_in_kg": case(
                                (
                                    OcMergeGatePass.chg_wgt_in_kg.is_(None),
                                    insert(OcMergeGatePass).excluded.chg_wgt_in_kg
                                ),
                                else_=OcMergeGatePass.chg_wgt_in_kg
                            ),
                             "no_of_pc": case(
                                (
                                    OcMergeGatePass.no_of_pc.is_(None),
                                    insert(OcMergeGatePass).excluded.no_of_pc
                                ),
                                else_=OcMergeGatePass.no_of_pc
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

                            "agent_name": case(
                                (
                                    or_(
                                        OcMergeGatePass.agent_name.is_(None),
                                        OcMergeGatePass.agent_name == ''
                                    ),
                                    insert(OcMergeGatePass).excluded.agent_name
                                ),
                                else_=OcMergeGatePass.agent_name
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

                # xmax = 0 means INSERT, xmax != 0 means UPDATE
                total_inserted += sum(1 for r in rows if r.xmax == 0)
                total_updated += sum(1 for r in rows if r.xmax != 0)

            # ═══════════════════════════════════════════════════════════════
            # STEP 8: Build Response (Same as generate-and-save)
            # ═══════════════════════════════════════════════════════════════
            execution_time = round(time.time() - start_time, 2)
            igp_range = f"{new_igp_list[0]} → {new_igp_list[-1]}" if new_igp_list else "None"
            
            response_data = [
                OcMergeGatePassResponse.model_validate(dict(r._mapping)) 
                for r in returned_rows
            ]
            
            failed_records = len(errors)
            total_processed = total_inserted + total_updated

            return FastTrackUploadResponse(
                success=True,
                # message=f"Fast-track upload completed. Inserted: {total_inserted}, Updated: {total_updated}, Skipped duplicates: {skipped_duplicates_in_file}",
                message=f"Fast-track upload completed. Inserted: {total_inserted}, Updated: {total_updated}",
                data=response_data,
                total_records=total_processed,
                inserted_records=total_inserted,
                total_updated=total_updated,
                skipped_existing_unchanged=skipped_existing_unchanged,
                skipped_duplicates_in_file=skipped_duplicates_in_file,
                failed_records=failed_records,
                execution_time=execution_time,
                igp_range=igp_range,
                batch_id=batch_id,
                errors=errors
            )

        except Exception as e:
            await db.rollback()
            return FastTrackUploadResponse(
                success=False,
                message=f"Error processing file: {str(e)}",
                data=[],
                total_records=0,  # ← Changed
        inserted_records=0,  # ← Changed
                total_updated=0,
                skipped_existing_unchanged=0,
                skipped_duplicates_in_file=0,
                failed_records=0,
                execution_time=round(time.time() - start_time, 2),
                igp_range="None",
                batch_id=batch_id,
                errors=[{"error": str(e)}]
            )


