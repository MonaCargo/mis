from enum import Enum


class OriginSourceType(str, Enum):
    OC_MERGE = "OC_MERGE"
    IRR = "IRR"
    IRM = "IRM"




class DamageStatusInWorkerAssignmnet(str, Enum):
    OPEN = "open"
    IN_PROGRESS = "in_progress"
    RESOLVED = "resolved"
    # CLOSED = "closed"

class WorkerAssignmentAuditSource(str, Enum):
    # OPS_ASSIGN = "ops_assign"
    USER_ASSIGN = "assign_user"
    TRACER_ASSIGN = "tracer_assign"
    DAMAGE_UPDATE = "damage_status_update"

# class UserRole(str, Enum):
#     IMP_USER = "imp_user"
#     IMP_TRACER = "imp_tracer"
#     ADMIN = "admin"


