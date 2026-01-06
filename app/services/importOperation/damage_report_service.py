# app/services/damage_report_service.py
import os
import uuid
from datetime import datetime
from typing import List, Optional, Tuple
from fastapi import UploadFile, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession
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
from app.schemas.importOperation.damage_report import DamageReportCreate, DamageReportUpdate


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


    async def create_damage_report(
        self,
        report_data: DamageReportCreate,
        images: List[UploadFile],
        user_info: dict
    ) -> Tuple[DamageReport, List[DamageReportImage]]:
        """
        Create or update a damage report.
        Tracks all changes: additions, removals, and updates.
        """
        saved_images: List[DamageReportImage] = []
        
        # Check for existing report
        existing_report_result = await self.db.execute(
            select(DamageReport)
            .options(selectinload(DamageReport.reasons))
            .filter(
                DamageReport.worker_assignment_id == report_data.worker_assignment_id,
                DamageReport.oc_no == report_data.oc_no,
                DamageReport.awb_no == report_data.awb_no,
                DamageReport.location == report_data.location,
            )
        )
        existing_report = existing_report_result.scalars().first()
        
        # For NEW reports, both reasons and images required
        if not existing_report:
            if not report_data.reason_ids or len(report_data.reason_ids) == 0:
                raise HTTPException(status_code=400, detail="At least one damage reason is required")
            if not images or len(images) == 0:
                raise HTTPException(status_code=400, detail="At least one image is required for new reports")
        else:
            # For UPDATES, must have at least 1 reason (can't remove all)
            if not report_data.reason_ids or len(report_data.reason_ids) == 0:
                raise HTTPException(status_code=400, detail="At least one damage reason must be selected")
        
        if images and len(images) > self.MAX_IMAGES_PER_REPORT:
            raise HTTPException(
                status_code=400,
                detail=f"Maximum {self.MAX_IMAGES_PER_REPORT} images allowed per report"
            )

        # Validate reason IDs
        await self._validate_reason_ids(report_data.reason_ids)

        try:
            if existing_report:
                # ========== UPDATE EXISTING REPORT ==========
                
                changes = []
                
                # Update remarks
                if report_data.remarks != existing_report.remarks:
                    old_remarks = existing_report.remarks
                    existing_report.remarks = report_data.remarks
                    if old_remarks and report_data.remarks:
                        changes.append("remarks updated")
                    elif report_data.remarks:
                        changes.append("remarks added")
                    else:
                        changes.append("remarks removed")
                
                existing_report.updated_at = datetime.utcnow()
                self.db.add(existing_report)
                await self.db.flush()

                # ===== SYNC REASONS (Handle Add/Remove) =====
                existing_reason_ids = {r.reason_id for r in existing_report.reasons}
                new_reason_ids = set(report_data.reason_ids)
                
                # Find added and removed reasons
                added_reasons = new_reason_ids - existing_reason_ids
                removed_reasons = existing_reason_ids - new_reason_ids
                
                # Remove old reasons that are no longer selected
                if removed_reasons:
                    for reason_rel in existing_report.reasons:
                        if reason_rel.reason_id in removed_reasons:
                            await self.db.delete(reason_rel)
                    changes.append(f"{len(removed_reasons)} reason(s) removed")
                
                # Add new reasons
                if added_reasons:
                    for reason_id in added_reasons:
                        report_reason = DamageReportReason(
                            report_id=existing_report.id,
                            reason_id=reason_id,
                            emp_id=user_info.get("emp_id", report_data.emp_id),
                            device_id=user_info.get("device_id"),
                        )
                        self.db.add(report_reason)
                    changes.append(f"{len(added_reasons)} reason(s) added")

                # Add new images if provided
                if images:
                    for idx, image in enumerate(images):
                        image_record = await self._save_image(
                            existing_report.id,
                            image,
                            idx,
                            emp_id=user_info.get("emp_id", report_data.emp_id),
                            device_id=user_info.get("device_id")
                        )
                        saved_images.append(image_record)
                    changes.append(f"{len(images)} new image(s) added")

                action = "UPDATE"
                source_action = "report_updated"
                description = f"Damage report updated: {', '.join(changes)}" if changes else "No changes detected"

            else:
                # ========== CREATE NEW REPORT ==========
                
                db_report = DamageReport(
                    worker_assignment_id=report_data.worker_assignment_id,
                    oc_no=report_data.oc_no,
                    awb_no=report_data.awb_no,
                    hawb=report_data.hawb,
                    location=report_data.location,
                    remarks=report_data.remarks,
                    reported_at=report_data.reported_at,
                    created_at=datetime.utcnow(),
                    updated_at=datetime.utcnow(),
                )
                self.db.add(db_report)
                await self.db.flush()

                # Add damage reasons
                for reason_id in report_data.reason_ids:
                    report_reason = DamageReportReason(
                        report_id=db_report.id,
                        reason_id=reason_id,
                        emp_id=user_info.get("emp_id", report_data.emp_id),
                        device_id=user_info.get("device_id", report_data.device_id)
                    )
                    self.db.add(report_reason)

                # Save images
                for idx, image in enumerate(images):
                    image_record = await self._save_image(
                        db_report.id,
                        image,
                        idx,
                        emp_id=user_info.get("emp_id", report_data.emp_id),
                        device_id=user_info.get("device_id")
                    )
                    saved_images.append(image_record)

                existing_report = db_report
                action = "CREATE"
                source_action = "report_created"
                description = f"Damage report created: {len(report_data.reason_ids)} reason(s), {len(saved_images)} image(s)"

            # Commit transaction
            await self.db.commit()
            await self.db.refresh(existing_report, ["reasons", "images"])

            # Create audit log
            await self._create_audit_log(
                damage_report_id=existing_report.id,
                oc_no=report_data.oc_no,
                location=report_data.location,
                db_action=action,
                source_action=source_action,
                changed_by=user_info.get("emp_id"),
                changed_by_role=user_info.get("role"),
                ip_address=user_info.get("ip_address"),
                device_id=user_info.get("device_id"),
                user_agent=user_info.get("user_agent"),
                description=description
            )

            return existing_report, saved_images

        except Exception as e:
            await self.db.rollback()
            for image in saved_images:
                await self._delete_image_file(image.image_url)
            raise HTTPException(status_code=500, detail=f"Failed to create/update damage report: {str(e)}")


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
        description: Optional[str] = None
    ):
        """Create audit log entry"""
        audit_log = DamageReportAuditLog(
            damage_report_id=damage_report_id,
            oc_no=oc_no,
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
            changed_at=datetime.utcnow()
        )
        self.db.add(audit_log)
        await self.db.commit()

    # Damage Reason Management Methods
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
        await self.db.commit()
        await self.db.refresh(db_reason)
        
        return db_reason