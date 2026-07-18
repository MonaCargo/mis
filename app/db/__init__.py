from app.db.base import Base
from app.db.models.export_slot_file import ExportSlotFileRecord, ExportSlotAWB
from app.db.models.user import User
from app.db.models.importOperation.import_wherehouse_inventry import ImportWhereHouseInventry
from app.db.models.importOperation.oc_report import OcReport
from app.db.models.importOperation.import_release_report import IrrReport
from app.db.models.importOperation.irregularity_report import Irregularity
from app.db.models.importOperation.oc_merge_gatepass import OcMergeGatePass
from app.db.models.manual_slot import ExportManualSlotFileRecord
from app.db.models.dock_availability import DockAvailability
# from app.db.models.importOperation.worker_assignment import WorkerAssignment 
from app.db.models.importOperation.worker_assignment import WorkerAssignmentShipment, WorkerAssignmentHeader
from app.db.models.importOperation.audit_log_worker_assignment import WorkerAssignmentAuditLog 
from app.db.models.audit_log_user import UserAuditLog 
from app.db.models.importOperation.damage_report import DamageReason,DamageReport,DamageReportAuditLog,DamageReportImage,DamageReportReason
from app.db.models.exportOperation.car_message import ExportAwbSkidItemSequence, ExportAwbSkidMapping,ExportCarMessageAwbMaster, ExportFlightBookingHeader,ExportFlightBookingDetail,ExportSkidLocationMapping

from app.db.models.exportOperation.car_message_flow_audit_log import ExportOperationCarMessageFlowAuditLog
from app.db.models.exportOperation.export_base_master import ExportBaseMaster



from app.db.models.exportOperation.export_skid_master import ExportSkidMaster
from app.db.models.exportOperation.export_uld_master import ExportUldMaster
from app.db.models.exportOperation.export_location_master import ExportLocationsMaster
from app.db.models.exportOperation.export_carrier_master import ExportCarrierMaster

from app.db.models.exportOperation.export_fileupload_meta_log import ExportFileUploadMetaLog

from app.db.models.domesticOperation.domestic_xray_report import DomesticXray
from app.db.models.exportOperation.export_and_import_tp_xray import ExportTpXray
from app.db.models.exportOperation.import_segrigation_report import ImportSegregationReport
from app.db.models.exportOperation.export_transipment_report import ExportTranshipmentReport
from app.db.models.exportOperation.uld_master_logs import ExportUldMasterOperationLogs
from app.db.models.exportOperation.export_uld_loading_sheet_form import ExportLoadingSheetForm
from app.db.models.importOperation.import_gp_mismatch_log import ImportGpMismatchLog
from app.db.models.importOperation.import_shipment_hold import ImportShipmentHold
from app.db.models.digital_reports.segrigation_report import DigitalReportImportSegFlight,DigitalReportImportSegAwb
from app.db.models.digital_reports.import_dept.import_truck_in_out import DigitalReportImportTruckInOut
from app.db.models.exportOperation.export_uld_loading_sheet_form import ExportLoadingSheetFormHistoryLog
from app.db.models.importOperation.imp_truck_in_out_module import ImportTruckInStaging , ImportTruckVisit, ImportGatePass, ImportGatePassAssignment, ImportGatePassLoading
from app.db.models.app_config.app_config import AppConfig ,AppConfigLog 

from app.db.models.digital_reports.import_dept.import_pick_order import DigitalReportImportPickOrder
from app.db.models.digital_reports.import_dept.import_emp_roaster import DigitalReportRosterAttendance,DigitalReportRosterEmployee



from app.db.models.digital_reports.export_dept.cargo_uplift_report import DigitalReportCargoUpliftReport
from app.db.models.digital_reports.export_dept.car_message_report import DigitalReportCarMessageReport
from app.db.models.digital_reports.export_dept.x_ray_report import DigitalReportXrayReport
from app.db.models.digital_reports.export_dept.export_tp_xray_report import DigitalReportExportTpXrayReport
from app.db.models.digital_reports.export_dept.import_segregation_report import DigitalReportImportSegregationReport
from app.db.models.digital_reports.export_dept.import_tp_xray_report import DigitalReportImportTpXrayReport
from app.db.models.digital_reports.export_dept.export_transhipment_report import DigitalReportExportTranshipmentReport
from app.db.models.digital_reports.export_dept.export_loaded_inventory import DigitalReportExportLoadedInventory




from app.db.models.digital_reports.customer_care.export_xray import DigitalReportExportXray
from app.db.models.digital_reports.customer_care.export_tp_xray import DigitalReportExportTpXray
from app.db.models.digital_reports.customer_care.import_tp_xray import DigitalReportImportTpXray
from app.db.models.digital_reports.customer_care.xray_performance import DigitalReportXRayPerformance



__all__ = [

"ImportGpMismatchLog",
"ImportShipmentHold",




# export DR
'DigitalReportCargoUpliftReport',
'DigitalReportCarMessageReport',
'DigitalReportXrayReport',
'DigitalReportExportTpXrayReport',
'DigitalReportImportTpXrayReport',
'DigitalReportExportLoadedInventory',
'DigitalReportExportTranshipmentReport',
'DigitalReportImportSegregationReport',


# Controle room DR (customer care)
"DigitalReportExportXray",
"DigitalReportExportTpXray",
"DigitalReportImportTpXray",
"DigitalReportXRayPerformance",


# Import DR
"DigitalReportImportSegFlight",
"DigitalReportImportSegAwb",
'DigitalReportImportTruckInOut',
'DigitalReportImportPickOrder',
"DigitalReportRosterAttendance",
"DigitalReportRosterEmployee",

"AppConfig", "AppConfigLog",

    "ImportTruckInStaging","ImportTruckVisit", "ImportGatePass", "ImportGatePassAssignment", "ImportGatePassLoading"
    ,
    # 'WorkerAssignment',
    'ExportLoadingSheetForm',
   'ExportLoadingSheetFormHistoryLog',

    'ExportUldMasterOperationLogs',

      'ExportTranshipmentReport',  
       'ImportSegregationReport',

    "ExportTpXray",

    'ExportFileUploadMetaLog',

    'ExportAwbSkidItemSequence',
    'ExportAwbSkidMapping',
    'ExportCarMessageAwbMaster',

    'ExportSkidMaster',
    
    'ExportUldMaster',
    'ExportLocationsMaster',

    'ExportFlightBookingHeader',
    'ExportFlightBookingDetail',
    'ExportOperationCarMessageFlowAuditLog',

    'ExportBaseMaster',
    'ExportCarrierMaster',

    
    # ---------


    'WorkerAssignmentShipment',
    'WorkerAssignmentHeader',

    'WorkerAssignmentAuditLog',
    'UserAuditLog',


    'ExportSlotFileRecord',
    'ImportWhereHouseInventry',
    'ExportManualSlotFileRecord',
    'DockAvailability',

    'DockOperationAWBLink',
    'AWBDockOperation',
    
    'OcReport',
    'IrrReport',
    'Irregularity',
    'OcMergeGatePass',
    'ExportSlotAWB',
    'AWBSequence',
    'User',


    'DamageReason',
    'DamageReport',
    'DamageReportAuditLog',
    'DamageReportImage',
    'DamageReportReason',

    'DomesticXray',
]















