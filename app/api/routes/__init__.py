from fastapi import APIRouter
from .user import router as user_router
from .export_slot_file_upload import router as export_slot_file_upload
from .auth import router as auth_router
from .dock import router as dock_router
from .importOperation.import_release import router as import_release_report
from .importOperation.import_whearhouse_inventry import router as import_wherehouse_inventry
from .importOperation.oc_report import router as oc_report
from .importOperation.irregularity_report import router as irregularity_report
from .importOperation.oc_merge_gatepass import router as oc_merge_gatepass
from .manual_slot_file import router as manual_slot_file_router
from .dock_availability import router as dock_availability_router
from .app_version import router as app_version_router

from .importOperation.temp_irm_oc_merge_creation import router as temp_irm_oc_merge_creation

# You can add more routes here as your app grows

api_v1_router = APIRouter()

#======= Include individual route modules
api_v1_router.include_router(user_router, prefix="/users", tags=["Users"])
api_v1_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_v1_router.include_router(dock_router, prefix="/dock", tags=["DOCK"])
api_v1_router.include_router(export_slot_file_upload, prefix="/truck", tags=["Export Slot File Upload || truck"])
api_v1_router.include_router(manual_slot_file_router, prefix="/manualSlot", tags=["Manual Slot File Upload || truck"])
api_v1_router.include_router(dock_availability_router, prefix="/dockAvailability", tags=["Dock Availability"])




#======= IMPORT OPERATION RELATED ROUTER
api_v1_router.include_router(import_release_report, prefix="/import", tags=["Import release report"])
api_v1_router.include_router(import_wherehouse_inventry, prefix="/import", tags=["import_wherehouse_inventry"])
api_v1_router.include_router(oc_report, prefix="/import", tags=["oc-report"])
api_v1_router.include_router(irregularity_report, prefix="/import", tags=["irregularities-report"])
api_v1_router.include_router(oc_merge_gatepass, prefix="/import", tags=["oc-merge-gatepass-report"])

# ---> Fast Track TEMP IRM OC MERGE
api_v1_router.include_router(temp_irm_oc_merge_creation, prefix="/import", tags=["Fast Track TEMP IRM OC MERGE"])

# ---> 



#======= app verion route
api_v1_router.include_router(app_version_router, prefix="/version", tags=["App Version"])

