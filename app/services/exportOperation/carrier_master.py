

import re

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db.models.exportOperation.export_carrier_master import ExportCarrierMaster, ExportCarrierPfx
from app.schemas.exportOperation.carrier_master import CarrierBulkUploadResponse
from app.utils.common.helperFunction import get_utc_now
from app.utils.exportOperation.export_carrier_master_cleaning import clean_carrier_excel

async def bulk_upload_carriers_from_excel(
    db: AsyncSession,
    file_bytes: bytes,
) -> CarrierBulkUploadResponse:

    now = get_utc_now()

    # ── Clean excel data ───────────────────────────────────────
    cleaned = clean_carrier_excel(file_bytes)

    if not cleaned:
        raise HTTPException(status_code=400, detail="No valid data found in Excel")

    # ── Fetch existing carrier codes in one query ──────────────
    existing_result = await db.execute(
        select(ExportCarrierMaster.carrier_code)
    )
    existing_codes = {row.carrier_code for row in existing_result.mappings().all()}

    # ── Fetch existing pfx to avoid duplicates ─────────────────
    existing_pfx_result = await db.execute(
        select(ExportCarrierPfx.carrier_master_id, ExportCarrierPfx.pfx)
    )
    existing_pfx_set = {
        (row.carrier_master_id, row.pfx)
        for row in existing_pfx_result.mappings().all()
    }

    to_insert_carriers = []
    skipped_codes = []

    for item in cleaned:
        code = item["carrier_code"]

        if code in existing_codes:
            skipped_codes.append(code)
            continue

        to_insert_carriers.append(
            ExportCarrierMaster(
                carrier_code=code,
                name=item["name"],
                is_active=True,
                created_at=now,
                updated_at=now,
            )
        )

    to_insert_pfx = []

    if to_insert_carriers:
        db.add_all(to_insert_carriers)
        await db.flush()  # ✅ get ids without committing

        # ── Build carrier_code → id map after flush ────────────
        code_to_id = {c.carrier_code: c.id for c in to_insert_carriers}

        # ── Build pfx rows using integer id ───────────────────
        for item in cleaned:
            code = item["carrier_code"]

            if code not in code_to_id:
                continue  # was skipped — already exists

            carrier_id = code_to_id[code]

            for pfx in item["pfx_list"]:
                if (carrier_id, pfx) not in existing_pfx_set:
                    to_insert_pfx.append(
                        ExportCarrierPfx(
                            carrier_master_id=carrier_id,  # ✅ integer id
                            pfx=pfx,
                            created_at=now,
                        )
                    )

        if to_insert_pfx:
            db.add_all(to_insert_pfx)

        await db.commit()

    return CarrierBulkUploadResponse(
        success=True,
        message=f"{len(to_insert_carriers)} carriers inserted, {len(skipped_codes)} skipped",
        inserted=len(to_insert_carriers),
        skipped=len(skipped_codes),
        skipped_codes=skipped_codes,
        pfx_skipped_non_numeric={}, 
    )





# async def verify_carrier_from_flight_no(
#     db: AsyncSession,
#     flight_no: str,
# ) -> dict:

#     flight_no = flight_no.strip().upper()

#     # ── Extract carrier code — first 2 chars ──────────────────
#     # handles both: AI420 (alpha) and 6E420 (alphanumeric)
#     match = re.match(r"^([A-Z0-9]{2})", flight_no)
#     if not match:
#         return {"is_valid": False, "carrier_code": None, "carrier_name": None, "message": "Invalid flight number format"}

#     carrier_code = match.group(1)

#     # ── Check in carrier master ────────────────────────────────
#     result = await db.execute(
#         select(ExportCarrierMaster).where(
#             ExportCarrierMaster.carrier_code == carrier_code,
#             ExportCarrierMaster.is_active == True,
#         )
#     )
#     carrier = result.scalar_one_or_none()

#     if not carrier:
#         return {
#             "is_valid": False,
#             "carrier_code": carrier_code,
#             "carrier_name": None,
#             "message": f"Carrier '{carrier_code}' not found in system",
#         }

#     return {
#         "is_valid": True,
#         "carrier_code": carrier.carrier_code,
#         "carrier_name": carrier.name,
#         "message": f"Carrier '{carrier_code}' is valid",
#     }





async def verify_carrier_from_flight_no(
    db: AsyncSession,
    flight_no: str,
) -> dict:

    flight_no = flight_no.strip().upper()

    # ── Total length: 2-char code + 4 digits = 6, 3-char code + 4 digits = 7
    if len(flight_no) < 6 or len(flight_no) > 7:
        return {
            "is_valid": False,
            "carrier_code": None,
            "carrier_name": None,
            "error_type": "INVALID_LENGTH",
            "message": f"'{flight_no}' has wrong length — expected 6 or 7 chars (2-3 char code + 4 digits)",
        }

    # ── Split: last 4 = flight digits, the rest = carrier code ──
    carrier_code = flight_no[:-4]
    flight_digits = flight_no[-4:]

    # ── Flight number must be exactly 4 NUMERIC digits ─────────
    if not flight_digits.isdigit():
        return {
            "is_valid": False,
            "carrier_code": carrier_code,
            "carrier_name": None,
            "error_type": "INVALID_FLIGHT_NUMBER",
            "message": f"Last 4 chars '{flight_digits}' must be numeric digits",
        }

    # ── Carrier code: 2 or 3 chars, alphanumeric ───────────────
    #    3-char code must NOT end in a digit (e.g. AHW, A6E ok; AI6 not)
    if len(carrier_code) == 3 and carrier_code[-1].isdigit():
        return {
            "is_valid": False,
            "carrier_code": carrier_code,
            "carrier_name": None,
            "error_type": "INVALID_FORMAT",
            "message": f"3-char carrier code '{carrier_code}' cannot end in a digit",
        }

    if not re.match(r"^[A-Z0-9]{2,3}$", carrier_code):
        return {
            "is_valid": False,
            "carrier_code": carrier_code,
            "carrier_name": None,
            "error_type": "INVALID_FORMAT",
            "message": f"Carrier code '{carrier_code}' must be 2-3 alphanumeric chars",
        }

    # ── EXACT carrier lookup — no fallback ─────────────────────
    result = await db.execute(
        select(ExportCarrierMaster).where(
            ExportCarrierMaster.carrier_code == carrier_code,
            ExportCarrierMaster.is_active == True,
        )
    )
    carrier = result.scalar_one_or_none()

    if not carrier:
        return {
            "is_valid": False,
            "carrier_code": carrier_code,
            "carrier_name": None,
            "error_type": "CARRIER_NOT_FOUND",
            "message": f"Carrier code '{carrier_code}' is not registered in the system",
        }

    # ── All valid ──────────────────────────────────────────────
    return {
        "is_valid": True,
        "carrier_code": carrier_code,
        "carrier_name": carrier.name,
        "error_type": None,
        "message": f"'{flight_no}' is valid — {carrier.name}",
    }


# async def verify_carrier_from_flight_no(
#     db: AsyncSession,
#     flight_no: str,
# ) -> dict:

#     flight_no = flight_no.strip().upper()

#     # ── Check total length ─────────────────────────────────────
#     if len(flight_no) > 7:
#         return {
#             "is_valid": False,
#             "carrier_code": None,
#             "carrier_name": None,
#             "error_type": "FLIGHT_NO_TOO_LONG",
#             "message": f"Flight number '{flight_no}' is too long — max 7 characters allowed",
#         }

#     # ── Extract carrier code + flight digits ───────────────────
#     match = re.match(r"^([A-Z0-9]{2,3})(\d+)$", flight_no)
#     if not match:
#         return {
#             "is_valid": False,
#             "carrier_code": None,
#             "carrier_name": None,
#             "error_type": "INVALID_FORMAT",
#             "message": "Invalid format — must be 2-3 char carrier code followed by digits (e.g. AI101, 6E420)",
#         }

#     carrier_code = match.group(1)
#     flight_digits = match.group(2)

#     # ── Validate flight number digits (1-4 digits) ─────────────
#     if len(flight_digits) < 1:
#         return {
#             "is_valid": False,
#             "carrier_code": carrier_code,
#             "carrier_name": None,
#             "error_type": "MISSING_FLIGHT_NUMBER",
#             "message": f"Carrier code '{carrier_code}' looks valid but flight number digits are missing",
#         }

#     if len(flight_digits) > 4:
#         return {
#             "is_valid": False,
#             "carrier_code": carrier_code,
#             "carrier_name": None,
#             "error_type": "FLIGHT_NUMBER_TOO_LONG",
#             "message": f"Flight number digits '{flight_digits}' too long — max 4 digits after carrier code",
#         }

#     # ── Try 3-char carrier first, fallback to 2-char ──────────
#     carrier = None
#     matched_code = carrier_code

#     result = await db.execute(
#         select(ExportCarrierMaster).where(
#             ExportCarrierMaster.carrier_code == carrier_code,
#             ExportCarrierMaster.is_active == True,
#         )
#     )
#     carrier = result.scalar_one_or_none()

#     if not carrier and len(carrier_code) == 3:
#         carrier_code_2 = carrier_code[:2]
#         result = await db.execute(
#             select(ExportCarrierMaster).where(
#                 ExportCarrierMaster.carrier_code == carrier_code_2,
#                 ExportCarrierMaster.is_active == True,
#             )
#         )
#         carrier = result.scalar_one_or_none()
#         if carrier:
#             matched_code = carrier_code_2

#     # ── Carrier not found ──────────────────────────────────────
#     if not carrier:
#         return {
#             "is_valid": False,
#             "carrier_code": carrier_code,
#             "carrier_name": None,
#             "error_type": "CARRIER_NOT_FOUND",
#             "message": f"Carrier code '{carrier_code}' is not registered in the system",
#         }

#     # ── All valid ──────────────────────────────────────────────
#     return {
#         "is_valid": True,
#         "carrier_code": matched_code,
#         "carrier_name": carrier.name,
#         "error_type": None,
#         "message": f"'{flight_no}' is valid — {carrier.name}",
#     }