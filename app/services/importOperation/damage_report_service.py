# app/services/damage_report_service.py
import os
import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
from sqlalchemy.exc import IntegrityError
from sqlalchemy import select, and_, desc, func
from sqlalchemy.orm import selectinload
import shutil
from pathlib import Path
import aiofiles

from app.db.models.importOperation.damage_report import (
    DamageReport, 
    DamageReportImage, 
    DamageReportAuditLog,
    DamageReason,
    DamageReportReason
)
from app.db.models.importOperation.worker_assignment import WorkerAssignmentHeader, WorkerAssignmentShipment
from app.schemas.importOperation.damage_report import DamageReportCreate, DamageReportUpdate
from app.utils.common.enums import DamageStatusInWorkerAssignmnet
from app.utils.common.helperFunction import get_utc_now


class DamageReportService:
    """Async service layer for damage report operations"""

    # Configuration
    UPLOAD_DIR = os.path.join("uploads", "damage_reports")
    MAX_FILE_SIZE = 5 * 1024 * 1024  # 5MB
    ALLOWED_EXTENSIONS = {".jpg", ".jpeg", ".png"}
    MAX_IMAGES_PER_REPORT = 5

    def __init__(self, db: AsyncSession):
        self.db = db
        # Ensure upload directory exists
        Path(self.UPLOAD_DIR).mkdir(parents=True, exist_ok=True)


    # async def create_damage_report(
    #     self,
    #     report_data: DamageReportCreate,
    #     images: List[UploadFile],
    #     user_info: dict
    # ) -> Tuple[DamageReport, List[DamageReportImage]]:
    #     """
    #     Create or update a damage report.
    #     Tracks all changes: additions, removals, and updates.
    #     """
    #     saved_images: List[DamageReportImage] = []
        
    #     # =====================================================
    #     # 1️⃣ Fetch Shipment + Header (CRITICAL)
    #     # =====================================================

    #     shipment_result = await self.db.execute(
    #         select(WorkerAssignmentShipment)
    #         .where(
    #             WorkerAssignmentShipment.id
    #             == report_data.assignment_shipment_id
    #         )
    #     )

    #     shipment = shipment_result.scalar_one_or_none()

    #     if not shipment:
    #         raise HTTPException(
    #             400,
    #             "Invalid assignment_shipment_id"
    #         )

    #     header_id = shipment.assignment_header_id


    #     # =====================================================
    #     # 2️⃣ Check Existing Report
    #     # =====================================================

    #     existing_result = await self.db.execute(

    #         select(DamageReport)
    #         .options(selectinload(DamageReport.reasons))
    #         .where(
    #             DamageReport.assignment_shipment_id
    #             == report_data.assignment_shipment_id,

    #             DamageReport.oc_no == report_data.oc_no,
    #             DamageReport.location == report_data.location,
    #         )
    #     )

    #     existing_report = existing_result.scalars().first()

    #     # =====================================================
    #     # 3️⃣ Validate Images + Reasons
    #     # =====================================================

    #     if not existing_report:

    #         if not report_data.reason_ids:
    #             raise HTTPException(
    #                 400,
    #                 "At least one damage reason required"
    #             )

    #         if not images:
    #             raise HTTPException(
    #                 400,
    #                 "At least one image required for new report"
    #             )

    #     else:

    #         if not report_data.reason_ids:
    #             raise HTTPException(
    #                 400,
    #                 "At least one damage reason required"
    #             )


    #     if images and len(images) > self.MAX_IMAGES_PER_REPORT:

    #         raise HTTPException(
    #             400,
    #             f"Maximum {self.MAX_IMAGES_PER_REPORT} images allowed"
    #         )


    #     # Validate reason IDs
    #     await self._validate_reason_ids(report_data.reason_ids)

    #     try:
    #         if existing_report:
    #             # ========== UPDATE EXISTING REPORT ==========
                
    #             changes = []
                
    #             # Update remarks
    #             if report_data.remarks != existing_report.remarks:
    #                 old_remarks = existing_report.remarks
    #                 existing_report.remarks = report_data.remarks
    #                 if old_remarks and report_data.remarks:
    #                     changes.append("remarks updated")
    #                 elif report_data.remarks:
    #                     changes.append("remarks added")
    #                 else:
    #                     changes.append("remarks removed")
                
    #             existing_report.updated_at = datetime.utcnow()
    #             self.db.add(existing_report)
    #             await self.db.flush()

    #             # ===== SYNC REASONS (Handle Add/Remove) =====
    #             existing_reason_ids = {r.reason_id for r in existing_report.reasons}
    #             new_reason_ids = set(report_data.reason_ids)
                
    #             # Find added and removed reasons
    #             added_reasons = new_reason_ids - existing_reason_ids
    #             removed_reasons = existing_reason_ids - new_reason_ids
                
    #             # Remove old reasons that are no longer selected
    #             if removed_reasons:
    #                 for reason_rel in existing_report.reasons:
    #                     if reason_rel.reason_id in removed_reasons:
    #                         await self.db.delete(reason_rel)
    #                 changes.append(f"{len(removed_reasons)} reason(s) removed")
                
    #             # Add new reasons
    #             if added_reasons:
    #                 for reason_id in added_reasons:
    #                     report_reason = DamageReportReason(
    #                         report_id=existing_report.id,
    #                         reason_id=reason_id,
    #                         emp_id=user_info.get("emp_id", report_data.emp_id),
    #                         device_id=user_info.get("device_id"),
    #                     )
    #                     self.db.add(report_reason)
    #                 changes.append(f"{len(added_reasons)} reason(s) added")

    #             # Add new images if provided
    #             if images:
    #                 for idx, image in enumerate(images):
    #                     image_record = await self._save_image(
    #                         existing_report.id,
    #                         image,
    #                         idx,
    #                         emp_id=user_info.get("emp_id", report_data.emp_id),
    #                         device_id=user_info.get("device_id")
    #                     )
    #                     saved_images.append(image_record)
    #                 changes.append(f"{len(images)} new image(s) added")

    #             action = "UPDATE"
    #             source_action = "report_updated"
    #             description = f"Damage report updated: {', '.join(changes)}" if changes else "No changes detected"

    #         else:
    #             # ========== CREATE NEW REPORT ==========
                
    #             db_report = DamageReport(
    #                 # ✅ New mapping
    #                 assignment_header_id=header_id,
    #                 assignment_shipment_id=shipment.id,

    #                 oc_no=report_data.oc_no,
    #                 awb_no=report_data.awb_no,
    #                 hawb=report_data.hawb,
    #                 location=report_data.location,
    #                 remarks=report_data.remarks,
    #                 reported_at=report_data.reported_at,
    #                 created_at=get_utc_now(),
    #                 updated_at=get_utc_now(),
    #             )
    #             self.db.add(db_report)
    #             await self.db.flush()

    #             # Add damage reasons
    #             for reason_id in report_data.reason_ids:
    #                 report_reason = DamageReportReason(
    #                     report_id=db_report.id,
    #                     reason_id=reason_id,
    #                     emp_id=user_info.get("emp_id", report_data.emp_id),
    #                     device_id=user_info.get("device_id", report_data.device_id)
    #                 )
    #                 self.db.add(report_reason)

    #             # Save images
    #             for idx, image in enumerate(images):
    #                 image_record = await self._save_image(
    #                     db_report.id,
    #                     image,
    #                     idx,
    #                     emp_id=user_info.get("emp_id", report_data.emp_id),
    #                     device_id=user_info.get("device_id")
    #                 )
    #                 saved_images.append(image_record)

    #             existing_report = db_report
    #             action = "CREATE"
    #             source_action = "report_created"
    #             description = f"Damage report created: {len(report_data.reason_ids)} reason(s), {len(saved_images)} image(s)"

    #         # Commit transaction
    #         await self.db.commit()
    #         await self.db.refresh(existing_report, ["reasons", "images"])

    #         # Create audit log
    #         await self._create_audit_log(
    #             damage_report_id=db_report.id,

    #             assignment_header_id=header_id,
    #             assignment_shipment_id=shipment.id,

    #             oc_no=shipment.header.oc_no,
    #             location=shipment.location,

    #             db_action=action,
    #             source_action=source_action,
    #             changed_by=user_info.get("emp_id"),
    #             changed_by_role=user_info.get("role"),
    #             ip_address=user_info.get("ip_address"),
    #             device_id=user_info.get("device_id"),
    #             user_agent=user_info.get("user_agent"),
    #             description=description
    #         )

    #         return existing_report, saved_images

    #     except Exception as e:
    #         await self.db.rollback()
    #         for image in saved_images:
    #             await self._delete_image_file(image.image_url)
    #         raise HTTPException(status_code=500, detail=f"Failed to create/update damage report: {str(e)}")

    # async def create_damage_report(
    #     self,
    #     report_data: DamageReportCreate,
    #     images: List[UploadFile],
    #     user_info: dict
    # ) -> Tuple[DamageReport, List[DamageReportImage]]:

    #     saved_images: List[DamageReportImage] = []

    #     # =====================================================
    #     # 🔴 FIX 1: Fetch Shipment + Header (DON'T TRUST CLIENT)
    #     # =====================================================
    #     shipment_result = await self.db.execute(
    #         select(WorkerAssignmentShipment)
    #         .where(
    #             WorkerAssignmentShipment.id
    #             == report_data.assignment_shipment_id
    #         )
    #     )


    #     shipment = shipment_result.scalar_one_or_none()

    #     if not shipment:
    #         raise HTTPException(400, "Invalid assignment_shipment_id")


    #     # 👇 MANUAL HEADER FETCH (NO RELATIONSHIP)
    #     header_result = await self.db.execute(
    #         select(WorkerAssignmentHeader).where(
    #             WorkerAssignmentHeader.id == shipment.assignment_header_id
    #         )
    #     )

    #     header = header_result.scalar_one_or_none()

    #     if not header:
    #         raise HTTPException(400, "Shipment header missing")


    #     header_id = shipment.assignment_header_id

    #     # 🔴 Validate OC from client vs header
    #     if report_data.oc_no != header.oc_no:
    #         raise HTTPException(
    #             status_code=400,
    #             detail="OC number does not match shipment header"
    #         )


    #     # =====================================================
    #     # 🔴 FIX 2: Check Existing Report (Use REAL OC + Location)
    #     # =====================================================
    #     existing_result = await self.db.execute(

    #         select(DamageReport)
    #         .options(selectinload(DamageReport.reasons))
    #         .where(
    #             DamageReport.assignment_shipment_id
    #             == shipment.id,

    #             # 🔴 FIX: use DB values, not client values
    #             DamageReport.oc_no == header.oc_no,
    #             DamageReport.location == shipment.location,
    #         )
    #     )

    #     existing_report = existing_result.scalars().first()


    #     # =====================================================
    #     # 3️⃣ Validate Images + Reasons
    #     # =====================================================
    #     if not existing_report:

    #         if not report_data.reason_ids:
    #             raise HTTPException(400, "At least one damage reason required")

    #         if not images:
    #             raise HTTPException(400, "At least one image required")

    #     else:

    #         if not report_data.reason_ids:
    #             raise HTTPException(400, "At least one damage reason required")


    #     if images and len(images) > self.MAX_IMAGES_PER_REPORT:

    #         raise HTTPException(
    #             400,
    #             f"Maximum {self.MAX_IMAGES_PER_REPORT} images allowed"
    #         )


    #     await self._validate_reason_ids(report_data.reason_ids)


    #     try:

    #         # =================================================
    #         # UPDATE
    #         # =================================================
    #         if existing_report:

    #             changes = []

    #             # ---- Remarks ----
    #             if report_data.remarks != existing_report.remarks:

    #                 existing_report.remarks = report_data.remarks
    #                 changes.append("remarks updated")

    #             existing_report.updated_at = get_utc_now()

    #             await self.db.flush()


    #             # ---- Sync Reasons ----
    #             old_ids = {r.reason_id for r in existing_report.reasons}
    #             new_ids = set(report_data.reason_ids)

    #             added = new_ids - old_ids
    #             removed = old_ids - new_ids


    #             for rel in existing_report.reasons:
    #                 if rel.reason_id in removed:
    #                     await self.db.delete(rel)


    #             for rid in added:

    #                 self.db.add(
    #                     DamageReportReason(
    #                         report_id=existing_report.id,
    #                         reason_id=rid,
    #                         emp_id=user_info.get("emp_id"),
    #                         device_id=user_info.get("device_id")
    #                     )
    #                 )


    #             # ---- Add Images ----
    #             if images:

    #                 for idx, img in enumerate(images):

    #                     rec = await self._save_image(
    #                         existing_report.id,
    #                         img,
    #                         idx,
    #                         emp_id=user_info.get("emp_id"),
    #                         device_id=user_info.get("device_id")
    #                     )

    #                     saved_images.append(rec)


    #             # 🔴 FIX 3: db_report was missing (CRASH BUG)
    #             db_report = existing_report


    #             action = "UPDATE"
    #             source_action = "report_updated"

    #             description = (
    #                 "Updated: " + ", ".join(changes)
    #                 if changes else "No changes"
    #             )


    #         # =================================================
    #         # CREATE
    #         # =================================================
    #         else:

    #             db_report = DamageReport(

    #                 # 🔴 FIX 4: Save REAL assignment chain
    #                 assignment_header_id=header_id,
    #                 assignment_shipment_id=shipment.id,

    #                 # 🔴 FIX 5: Save REAL OC + Location (NOT client)
    #                 oc_no=report_data.oc_no,
    #                 location=report_data.location , 

    #                 awb_no=report_data.awb_no,
    #                 hawb=report_data.hawb,

    #                 remarks=report_data.remarks,
    #                 reported_at=report_data.reported_at,

    #                 created_at=get_utc_now(),
    #                 updated_at=get_utc_now(),
    #             )

    #             self.db.add(db_report)

    #             await self.db.flush()


    #             # ---- Add Reasons ----
    #             for rid in report_data.reason_ids:

    #                 self.db.add(
    #                     DamageReportReason(
    #                         report_id=db_report.id,
    #                         reason_id=rid,
    #                         emp_id=user_info.get("emp_id"),
    #                         device_id=user_info.get("device_id"),
    #                     )
    #                 )


    #             # ---- Save Images ----
    #             for idx, img in enumerate(images):

    #                 rec = await self._save_image(
    #                     db_report.id,
    #                     img,
    #                     idx,
    #                     emp_id=user_info.get("emp_id"),
    #                     device_id=user_info.get("device_id")
    #                 )

    #                 saved_images.append(rec)


    #             action = "CREATE"
    #             source_action = "report_created"

    #             description = (
    #                 f"Created with {len(report_data.reason_ids)} reasons "
    #                 f"and {len(saved_images)} images"
    #             )


    #         # =====================================================
    #         # COMMIT
    #         # =====================================================
    #         await self.db.commit()


    #         result = await self.db.execute(
    #             select(DamageReport)
    #             .options(
    #                 selectinload(DamageReport.reasons),
    #                 selectinload(DamageReport.images),
    #             )
    #             .where(DamageReport.id == db_report.id)
    #         )

    #         db_report = result.scalar_one()

    #         # =====================================================
    #         # AUDIT
    #         # =====================================================
    #         await self._create_audit_log(

    #             damage_report_id=db_report.id,

    #             # 🔴 FIX 6: Save assignment context
    #             assignment_header_id=header_id,
    #             assignment_shipment_id=shipment.id,

    #             oc_no=header.oc_no,
    #             location=shipment.location,

    #             db_action=action,
    #             source_action=source_action,

    #             changed_by=user_info.get("emp_id"),
    #             changed_by_role=user_info.get("role"),

    #             ip_address=user_info.get("ip_address"),
    #             device_id=user_info.get("device_id"),

    #             user_agent=user_info.get("user_agent"),

    #             description=description,

    #             changed_at=get_utc_now(),  # 🔴 FIX 7: mandatory
    #         )


    #         return db_report, saved_images


    #     except Exception as e:

    #         await self.db.rollback()

    #         for img in saved_images:
    #             await self._delete_image_file(img.image_url)

    #         raise HTTPException(
    #             500,
    #             f"Failed to save report: {str(e)}"
    #         )

    async def create_damage_report(
        self,
        report_data: DamageReportCreate,
        images: List[UploadFile],
        user_info: dict
    ) -> Tuple[DamageReport, List[DamageReportImage]]:

        saved_images: List[DamageReportImage] = []
        print(report_data,"report_data")

        # =====================================================
        # 🔴 FIX 1: Fetch Shipment + Header (DON'T TRUST CLIENT)
        # =====================================================
        shipment_result = await self.db.execute(
            select(WorkerAssignmentShipment)
            .where(
                WorkerAssignmentShipment.id
                == report_data.assignment_shipment_id
            )
        )

        shipment = shipment_result.scalar_one_or_none()

        if not shipment:
            raise HTTPException(400, "Invalid assignment_shipment_id")

        # 👇 MANUAL HEADER FETCH (NO RELATIONSHIP)
        header_result = await self.db.execute(
            select(WorkerAssignmentHeader).where(
                WorkerAssignmentHeader.id == shipment.assignment_header_id
            )
        )

        header = header_result.scalar_one_or_none()

        if not header:
            raise HTTPException(400, "Shipment header missing")

        header_id = shipment.assignment_header_id

        # 🔴 Validate OC from client vs header
        if report_data.oc_no != header.oc_no:
            raise HTTPException(
                status_code=400,
                detail="OC number does not match shipment header"
            )

        # =====================================================
        # 🔴 FIX 2: Check Existing Report (Use REAL OC + Location)
        # =====================================================
        existing_result = await self.db.execute(
            select(DamageReport)
            .options(selectinload(DamageReport.reasons))
            .where(
                DamageReport.assignment_shipment_id
                == shipment.id,

            # used client values
                DamageReport.oc_no == header.oc_no,
                DamageReport.location == report_data.location,
            )
        )

        existing_report = existing_result.scalars().first()

        # =====================================================
        # 3️⃣ Validate Images + Reasons
        # =====================================================
        if not existing_report:
            if not report_data.reason_ids:
                raise HTTPException(400, "At least one damage reason required")

            if not images:
                raise HTTPException(400, "At least one image required")
        else:
            if not report_data.reason_ids:
                raise HTTPException(400, "At least one damage reason required")

        if images and len(images) > self.MAX_IMAGES_PER_REPORT:
            raise HTTPException(
                400,
                f"Maximum {self.MAX_IMAGES_PER_REPORT} images allowed"
            )

        await self._validate_reason_ids(report_data.reason_ids)

        try:
            # # =================================================
            # # UPDATE
            # # =================================================
            # if existing_report:
            #     changes = []

            #     # ---- Remarks ----
            #     if report_data.remarks != existing_report.remarks:
            #         existing_report.remarks = report_data.remarks
            #         changes.append("remarks updated")

            #     existing_report.updated_at = get_utc_now()

            #     await self.db.flush()

            # =================================================
            # UPDATE
            # =================================================
            if existing_report:
                changes = []

                role = user_info.get("role")

                # -----------------------------------
                # NORMAL USER → update remarks only
                # -----------------------------------
                if role != "imp_tracer":

                    if report_data.remarks is not None and report_data.remarks != existing_report.remarks:

                        old_val = existing_report.remarks

                        existing_report.remarks = report_data.remarks

                        # changes.append(("remarks", old_val, report_data.remarks))
                        changes.append(f"remarks updated: {old_val} → {report_data.remarks}")

                        



                # -----------------------------------
                # TRACER → update tracer_remarks only
                # -----------------------------------
                else:
                    print("Tracer updating report...", report_data.tracer_remarks, "------------",existing_report.tracer_remarks)

                    if report_data.tracer_remarks is not None and report_data.tracer_remarks != existing_report.tracer_remarks:

                        old_val = existing_report.tracer_remarks

                        existing_report.tracer_remarks = report_data.tracer_remarks

                        # changes.append(("tracer_remarks", old_val, report_data.tracer_remarks))
                        changes.append(f"tracer remarks updated: {old_val} → {report_data.tracer_remarks}")




                existing_report.updated_at = get_utc_now()

                await self.db.flush()


                # ---- Sync Reasons ----
                old_ids = {r.reason_id for r in existing_report.reasons}
                new_ids = set(report_data.reason_ids)

                added = new_ids - old_ids
                removed = old_ids - new_ids

                for rel in existing_report.reasons:
                    if rel.reason_id in removed:
                        await self.db.delete(rel)

                for rid in added:
                    self.db.add(
                        DamageReportReason(
                            report_id=existing_report.id,
                            reason_id=rid,
                            emp_id=user_info.get("emp_id"),
                            device_id=user_info.get("device_id")
                        )
                    )

                # ---- Add Images ----
                if images:
                    for idx, img in enumerate(images):
                        rec = await self._save_image(
                            existing_report.id,
                            img,
                            idx,
                            emp_id=user_info.get("emp_id"),
                            device_id=user_info.get("device_id")
                        )
                        saved_images.append(rec)

                # 🔴 FIX 3: db_report was missing (CRASH BUG)
                db_report = existing_report

                action = "UPDATE"
                source_action = "report_updated"

                description = (
                    "Updated: " + ", ".join(changes)
                    if changes else "No changes"
                )

            # =================================================
            # CREATE
            # =================================================
            else:
                db_report = DamageReport(
                    # 🔴 FIX 4: Save REAL assignment chain
                    assignment_header_id=header_id,
                    assignment_shipment_id=shipment.id,

                    # 🔴 FIX 5: Save REAL OC + Location (NOT client)
                    oc_no=report_data.oc_no,
                    location=report_data.location,

                    awb_no=report_data.awb_no,
                    hawb=report_data.hawb,

                    remarks=report_data.remarks,
                    reported_at=report_data.reported_at,

                    created_at=get_utc_now(),
                    updated_at=get_utc_now(),
                )

                self.db.add(db_report)

                # 🔴 ADD THIS BLOCK 👇👇👇(SYNC TO WORKER ASSIGNMENT)
                # =========================
                current_status = shipment.damage_report_status

                # Only set OPEN if no active tracer case
                if current_status is None:

                    shipment.damage_report_status = DamageStatusInWorkerAssignmnet.OPEN.value
                    shipment.damage_resolve_datetime = None

                # ❌ THIS USED WHEN NEED IN FUTURE THAT REOPEN NOT TODAY (FEB...)
                # elif current_status == DamageStatusInWorkerAssignmnet.RESOLVED.value:
                #     # New damage after resolved → reopen
                #     shipment.damage_report_status = DamageStatusInWorkerAssignmnet.OPEN.value
                #     shipment.damage_resolve_datetime = None


                    # If already OPEN or IN_PROGRESS → DO NOTHING
                    # (Keep existing status)
                shipment.updated_at = get_utc_now()
                self.db.add(shipment)
                # 🔴------ END

                await self.db.flush()

                # ---- Add Reasons ----
                for rid in report_data.reason_ids:
                    self.db.add(
                        DamageReportReason(
                            report_id=db_report.id,
                            reason_id=rid,
                            emp_id=user_info.get("emp_id"),
                            device_id=user_info.get("device_id"),
                        )
                    )

                # ---- Save Images ----
                for idx, img in enumerate(images):
                    rec = await self._save_image(
                        db_report.id,
                        img,
                        idx,
                        emp_id=user_info.get("emp_id"),
                        device_id=user_info.get("device_id")
                    )
                    saved_images.append(rec)

                action = "CREATE"
                source_action = "report_created"

                description = (
                    f"Created with {len(report_data.reason_ids)} reasons "
                    f"and {len(saved_images)} images"
                )

            # =====================================================
            # FLUSH BEFORE AUDIT
            # =====================================================
            await self.db.flush()

            # =====================================================
            # AUDIT
            # =====================================================
            await self._create_audit_log(
                damage_report_id=db_report.id,

                # 🔴 FIX 6: Save assignment context
                assignment_header_id=header_id,
                assignment_shipment_id=shipment.id,

                oc_no=header.oc_no,
                location=report_data.location,

                db_action=action,
                source_action=source_action,

                changed_by=user_info.get("emp_id"),
                changed_by_role=user_info.get("role"),

                ip_address=user_info.get("ip_address"),
                device_id=user_info.get("device_id"),

                user_agent=user_info.get("user_agent"),

                description=description,

                changed_at=get_utc_now(),  # 🔴 FIX 7: mandatory
            )

            # =====================================================
            # COMMIT (SINGLE COMMIT)
            # =====================================================
            await self.db.commit()

            # =====================================================
            # REFRESH REPORT WITH RELATIONSHIPS
            # =====================================================
            result = await self.db.execute(
                select(DamageReport)
                .options(
                    selectinload(DamageReport.reasons),
                    selectinload(DamageReport.images),
                )
                .where(DamageReport.id == db_report.id)
            )

            db_report = result.scalar_one()

            return db_report, saved_images

        except Exception as e:
            await self.db.rollback()
            import traceback
            for img in saved_images:
                await self._delete_image_file(img.image_url)

            # Print full traceback to console
            traceback.print_exc()    

            raise HTTPException(
                500,
                f"Failed to save report: {str(e)}"
            )    


# -----------------------------------------------------------------

    async def _validate_reason_ids(self, reason_ids: List[int]):
        """Validate that all reason IDs exist and are active"""
        stmt = select(DamageReason).where(
            and_(
                DamageReason.id.in_(reason_ids),
                DamageReason.is_active == True
            )
        )
        result = await self.db.execute(stmt)
        valid_reasons = result.scalars().all()
        
        if len(valid_reasons) != len(reason_ids):
            raise HTTPException(
                status_code=400,
                detail="One or more invalid or inactive damage reason IDs"
            )

    async def _save_image(
        self,
        report_id: int,
        image: UploadFile,
        index: int,
        emp_id: str,
        device_id: Optional[str] = None
    ) -> DamageReportImage:
        """Save image file and create database record"""
        
        # Validate file extension
        file_ext = os.path.splitext(image.filename)[1].lower()
        if file_ext not in self.ALLOWED_EXTENSIONS:
            raise HTTPException(
                status_code=400,
                detail=f"Invalid file type. Allowed: {', '.join(self.ALLOWED_EXTENSIONS)}"
            )

        # Generate unique filename
        unique_filename = f"{report_id}_{uuid.uuid4().hex}_{index + 1}{file_ext}"
        file_path = os.path.join(self.UPLOAD_DIR, unique_filename)

        # Save file asynchronously
        try:
            async with aiofiles.open(file_path, 'wb') as out_file:
                content = await image.read()
                await out_file.write(content)
            
            # Get file size
            file_size = os.path.getsize(file_path)
            
            # Validate file size
            if file_size > self.MAX_FILE_SIZE:
                os.remove(file_path)
                raise HTTPException(
                    status_code=400,
                    detail=f"File size exceeds maximum limit of {self.MAX_FILE_SIZE / 1024 / 1024}MB"
                )

            # Create database record
            db_image = DamageReportImage(
                report_id=report_id,
                emp_id=emp_id, 
                device_id=device_id,
                image_url=file_path,
                image_name=unique_filename,
                file_size=file_size,
                mime_type=image.content_type
            )
            self.db.add(db_image)
            
            return db_image

        except Exception as e:
            # Clean up file on error
            if os.path.exists(file_path):
                os.remove(file_path)
            raise

    async def get_damage_reports_by_oc(
        self,
        oc_no: str,
        location: Optional[str] = None
    ) -> List[DamageReport]:
        """Get all damage reports for a specific OC"""
        stmt = select(DamageReport).options(
            selectinload(DamageReport.reasons).selectinload(DamageReportReason.reason),
            selectinload(DamageReport.images)
        ).where(DamageReport.oc_no == oc_no)
        
        if location:
            stmt = stmt.where(DamageReport.location == location)
        
        stmt = stmt.order_by(desc(DamageReport.reported_at))
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    # 😊😊
    async def get_damage_reports_by_shipment_and_location(
        self,
        assignment_shipment_id: int,
        oc_no: str,
        location: str
    ) -> List[DamageReport]:
        
        try:

            # =====================================================
            # 1️⃣ Fetch Shipment
            # =====================================================
            shipment_result = await self.db.execute(
                select(WorkerAssignmentShipment)
                .where(
                    WorkerAssignmentShipment.id == assignment_shipment_id
                )
            )

            shipment = shipment_result.scalar_one_or_none()

            if not shipment:
                raise HTTPException(
                    status_code=404,
                    detail="Invalid assignment_shipment_id"
                )


            # =====================================================
            # 2️⃣ Fetch Header Manually (NO RELATIONSHIP)
            # =====================================================
            header_result = await self.db.execute(
                select(WorkerAssignmentHeader)
                .where(
                    WorkerAssignmentHeader.id == shipment.assignment_header_id
                )
            )

            header = header_result.scalar_one_or_none()

            if not header:
                raise HTTPException(
                    status_code=404,
                    detail="Shipment header missing"
                )


            # =====================================================
            # 3️⃣ Validate OC (DO NOT TRUST CLIENT)
            # =====================================================
            if oc_no != header.oc_no:
                raise HTTPException(
                    status_code=400,
                    detail="OC number does not match shipment header"
                )


            # =====================================================
            # 4️⃣ Fetch Damage Reports (Shipment + Location)
            # =====================================================
            stmt = (
                select(DamageReport)

                .options(
                    selectinload(DamageReport.reasons)
                        .selectinload(DamageReportReason.reason),

                    selectinload(DamageReport.images)
                )

                .where(
                    DamageReport.assignment_shipment_id == assignment_shipment_id,
                    DamageReport.location == location  # ✅ use DB value
                )

                .order_by(
                    DamageReport.reported_at.desc()
                )
            )


            result = await self.db.execute(stmt)

            reports = result.scalars().all()

            return reports
        except Exception as e:

            import traceback

            print("\n🚨 SERVICE ERROR 🚨")
            traceback.print_exc()

            raise


    async def get_damage_reports_by_employee(
        self,
        emp_id: str,
        start_date: Optional[datetime] = None,
        end_date: Optional[datetime] = None
    ) -> List[DamageReport]:
        """Get all damage reports submitted by an employee"""
        stmt = select(DamageReport).options(
            selectinload(DamageReport.reasons).selectinload(DamageReportReason.reason),
            selectinload(DamageReport.images)
        ).where(DamageReport.emp_id == emp_id)
        
        if start_date:
            stmt = stmt.where(DamageReport.reported_at >= start_date)
        if end_date:
            stmt = stmt.where(DamageReport.reported_at <= end_date)
        
        stmt = stmt.order_by(desc(DamageReport.reported_at))
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_damage_report_by_id(self, report_id: int) -> Optional[DamageReport]:
        """Get a specific damage report by ID"""
        stmt = select(DamageReport).options(
            selectinload(DamageReport.reasons).selectinload(DamageReportReason.reason),
            selectinload(DamageReport.images)
        ).where(DamageReport.id == report_id)
        
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def update_damage_report(
        self,
        report_id: int,
        update_data: DamageReportUpdate,
        user_info: dict
    ) -> DamageReport:
        """Update an existing damage report"""
        db_report = await self.get_damage_report_by_id(report_id)
        
        if not db_report:
            raise HTTPException(status_code=404, detail="Damage report not found")

        # Track changes for audit
        changes = []
        
        # Update reasons if provided
        if update_data.reason_ids is not None:
            # Validate new reason IDs
            await self._validate_reason_ids(update_data.reason_ids)
            
            # Get old reason IDs
            old_reason_ids = [r.reason_id for r in db_report.reasons]
            
            # Delete old reasons
            for reason_rel in db_report.reasons:
                await self.db.delete(reason_rel)
            
            # Add new reasons
            for reason_id in update_data.reason_ids:
                report_reason = DamageReportReason(
                    report_id=report_id,
                    reason_id=reason_id,
                    emp_id=user_info.get("emp_id", None),
                    device_id=user_info.get("device_id")
                )
                self.db.add(report_reason)
            
            changes.append(("damage_reasons", str(old_reason_ids), str(update_data.reason_ids)))
        
        # Update remarks if provided
        if update_data.remarks is not None:
            old_remarks = db_report.remarks
            db_report.remarks = update_data.remarks
            changes.append(("remarks", old_remarks, update_data.remarks))
        
        print(update_data,"report_data")
        print(changes,"changes")

        try:
            await self.db.commit()
            await self.db.refresh(db_report, ["reasons", "images"])

            # Create audit logs for each change
            for field_name, old_val, new_val in changes:
                await self._create_audit_log(
                    damage_report_id=report_id,
                    oc_no=db_report.oc_no,
                    location=db_report.location,
                    db_action="UPDATE",
                    source_action="report_updated",
                    field_name=field_name,
                    old_value=old_val,
                    new_value=new_val,
                    changed_by=user_info.get("emp_id", "unknown"),
                    changed_by_role=user_info.get("role", "worker"),
                    ip_address=user_info.get("ip_address"),
                    device_id=user_info.get("device_id"),
                    user_agent=user_info.get("user_agent")
                )

            return db_report

        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to update damage report: {str(e)}")

    async def delete_damage_report(self, report_id: int, user_info: dict) -> bool:
        """Delete a damage report and its images"""
        db_report = await self.get_damage_report_by_id(report_id)
        
        if not db_report:
            raise HTTPException(status_code=404, detail="Damage report not found")

        try:
            # Delete image files
            for image in db_report.images:
                await self._delete_image_file(image.image_url)

            # Store info for audit before deletion
            oc_no = db_report.oc_no
            location = db_report.location

            # Delete from database (cascade will delete images and reasons)
            await self.db.delete(db_report)
            await self.db.commit()

            # Create audit log
            await self._create_audit_log(
                damage_report_id=report_id,
                oc_no=oc_no,
                location=location,
                db_action="DELETE",
                source_action="report_deleted",
                changed_by=user_info.get("emp_id", "unknown"),
                changed_by_role=user_info.get("role", "worker"),
                ip_address=user_info.get("ip_address"),
                device_id=user_info.get("device_id"),
                user_agent=user_info.get("user_agent"),
                description="Damage report and associated images deleted"
            )

            return True

        except Exception as e:
            await self.db.rollback()
            raise HTTPException(status_code=500, detail=f"Failed to delete damage report: {str(e)}")

    async def _delete_image_file(self, file_path: str):
        """Delete image file from filesystem"""
        try:
            if os.path.exists(file_path):
                os.remove(file_path)
        except Exception as e:
            print(f"Warning: Failed to delete image file {file_path}: {e}")

    async def _create_audit_log(
        self,
        damage_report_id: int,
         assignment_header_id: int,
    assignment_shipment_id: int,
        oc_no: str,
        location: str,
        db_action: str,
        source_action: str,
        changed_by: str,
        changed_by_role: str,
        field_name: Optional[str] = None,
        old_value: Optional[str] = None,
        new_value: Optional[str] = None,
        ip_address: Optional[str] = None,
        device_id: Optional[str] = None,
        user_agent: Optional[str] = None,
        description: Optional[str] = None,
        changed_at: Optional[datetime] = None

    ):
        """Create audit log entry"""
        audit_log = DamageReportAuditLog(
            damage_report_id=damage_report_id,
            oc_no=oc_no,
            assignment_header_id=assignment_header_id ,
            assignment_shipment_id= assignment_shipment_id,
            location=location,
            field_name=field_name,
            old_value=old_value,
            new_value=new_value,
            db_action=db_action,
            source_action=source_action,
            changed_by=changed_by,
            changed_by_role=changed_by_role,
            ip_address=ip_address,
            device_id=device_id,
            user_agent=user_agent,
            description=description,
            changed_at=changed_at or get_utc_now()
        )
        self.db.add(audit_log)
        # Already commited in create damage report
        # await self.db.commit()

    # Damage Reason Management Methods-----------------------------------------------------------------------
    async def get_all_damage_reasons(self, active_only: bool = True) -> List[DamageReason]:
        """Get all damage reasons"""
        stmt = select(DamageReason)
        print(active_only)
        if active_only:
            stmt = stmt.where(DamageReason.is_active == True)
        else :
            stmt = stmt.where(DamageReason.is_active == False)

        stmt = stmt.order_by(DamageReason.reason_code)
        
        result = await self.db.execute(stmt)
        return result.scalars().all()

    async def get_damage_reason_by_id(self, reason_id: int) -> Optional[DamageReason]:
        """Get a specific damage reason by ID"""
        stmt = select(DamageReason).where(DamageReason.id == reason_id)
        result = await self.db.execute(stmt)
        return result.scalar_one_or_none()

    async def create_damage_reason(
        self,
        reason_code: str,
        reason_name: str,
        description: Optional[str] = None
    ) -> DamageReason:
        """Create a new damage reason"""
        # Check if reason code already exists
        stmt = select(DamageReason).where(DamageReason.reason_code == reason_code)
        result = await self.db.execute(stmt)
        existing = result.scalar_one_or_none()
        
        if existing:
            raise HTTPException(
                status_code=400,
                detail=f"Damage reason with code '{reason_code}' already exists"
            )
        
        db_reason = DamageReason(
            reason_code=reason_code,
            reason_name=reason_name,
            description=description
        )
        self.db.add(db_reason)
        try:
            await self.db.commit()

        except IntegrityError:
                await self.db.rollback()
                raise HTTPException(
                    status_code=400,
                    detail=f"Damage reason '{reason_code}' already exists"
                )
        
        await self.db.refresh(db_reason)
        
        return db_reason