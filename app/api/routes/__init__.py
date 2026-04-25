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
from .importOperation.worker_assignment import router as worker_assignment
from .importOperation.all_import_logs_route import router as all_import_logs_route
from .importOperation.damage_report import router as damage_report


from .domesticOperation.domestic_xray_report import router as domestic_xray_report_route
from .exportOperation.car_message import router as export_car_message_awb_router
from .exportOperation.export_skid_master import router as export_skid_master_router
from .exportOperation.export_uld_master import router as export_uld_master_router
from .exportOperation.export_location_master import router as export_location_master_router
from .exportOperation.export_carrier_master import router as export_carrier_master_router
from .exportOperation.export_base_master import router as export_base_master_router
from .exportOperation.export_fileupload_meta_log import router as export_fileupload_meta_log_router
from .exportOperation.export_import_tp_report_for_car import router as export_impotrt_xray_tp_report_router


# You can add more routes here as your app grows

api_v1_router = APIRouter()

#======= Include individual route modules
api_v1_router.include_router(user_router, prefix="/users", tags=["Users"])
api_v1_router.include_router(auth_router, prefix="/auth", tags=["Auth"])
api_v1_router.include_router(dock_router, prefix="/dock", tags=["DOCK"])
api_v1_router.include_router(export_slot_file_upload, prefix="/truck", tags=["Export Slot File Upload || truck"])
api_v1_router.include_router(manual_slot_file_router, prefix="/manualSlot", tags=["Manual Slot File Upload || truck"])
api_v1_router.include_router(dock_availability_router, prefix="/dockAvailability", tags=["Dock Availability"])

# Car message --------
api_v1_router.include_router(export_car_message_awb_router, prefix="/export/car", tags=["Export Car Message AWB"])
# 
api_v1_router.include_router(export_skid_master_router, prefix="/export/skid", tags=["Export Skid Master"])
api_v1_router.include_router(export_uld_master_router, prefix="/export/uld", tags=["Export ULD Master"])
api_v1_router.include_router(export_location_master_router, prefix="/export/location-master", tags=["Export Locations Master"])
api_v1_router.include_router(export_base_master_router, prefix="/export/base-master", tags=["Export Base Master"])
api_v1_router.include_router(export_carrier_master_router, prefix="/export/carrier-master", tags=["Export Carrier Master"])
api_v1_router.include_router(export_fileupload_meta_log_router, prefix="/export/file-upload-meta/logs", tags=["Export File Upload Meta Logs"])
api_v1_router.include_router(export_impotrt_xray_tp_report_router, prefix="/export/import/tp-report", tags=["Export Or ImportFile Upload TP Report"])

 



#======= IMPORT OPERATION RELATED ROUTER
api_v1_router.include_router(import_release_report, prefix="/import", tags=["Import release report"])
api_v1_router.include_router(import_wherehouse_inventry, prefix="/import", tags=["import_wherehouse_inventry"])
api_v1_router.include_router(oc_report, prefix="/import", tags=["oc-report"])
api_v1_router.include_router(irregularity_report, prefix="/import", tags=["irregularities-report"])
api_v1_router.include_router(oc_merge_gatepass, prefix="/import", tags=["oc-merge-gatepass-report"])
api_v1_router.include_router(all_import_logs_route, prefix="/import", tags=["logs report of imports"])

# ---> Fast Track TEMP IRM OC MERGE
api_v1_router.include_router(temp_irm_oc_merge_creation, prefix="/import", tags=["Fast Track TEMP IRM OC MERGE"])
# ---> 
# worker assignment--->
api_v1_router.include_router(worker_assignment, prefix="/import", tags=["worker assignment"])



#======= app verion route
api_v1_router.include_router(app_version_router, prefix="/version", tags=["App Version"])

# ============= damage reason route
api_v1_router.include_router(damage_report,prefix='/import',tags=["damage-report"])

# =============================== DOMESTIC OPERATION ==========================================================
api_v1_router.include_router(domestic_xray_report_route,prefix='/domestic',tags=['Domestic X-ray'])