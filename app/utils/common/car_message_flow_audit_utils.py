# utils/audit_modules.py

class CarMessageFlowModule:
    AWB_MASTER          = "AWB_MASTER"
    SKID_ASSIGNMENT     = "SKID_ASSIGNMENT"
    LOCATION_MAPPING    = "LOCATION_MAPPING"
    FLIGHT_BOOKING      = "FLIGHT_BOOKING"
    ULD_ASSIGNMENT      = "ULD_ASSIGNMENT"
    SKID_RETRIEVAL      = "SKID_RETRIEVAL"          # ← separate from location
    BASE_DROP           = "BASE_DROP"  
    # CARGO_MANIFEST    = "CARGO_MANIFEST"
    # DEPARTURE_CTRL    = "DEPARTURE_CTRL"
    # FLIGHT_CLOSE      = "FLIGHT_CLOSE"


# ✅ Fixed immutable step codes — never integers, never reordered
class CarMessageFlowStep:
    AWB_MASTER          = "STEP_AWB_MASTER"
    SKID_ASSIGNMENT     = "STEP_SKID_ASSIGNMENT"
    LOCATION_MAPPING    = "STEP_LOCATION_MAPPING"
    FLIGHT_BOOKING      = "STEP_FLIGHT_BOOKING"
    ULD_ASSIGNMENT      = "STEP_ULD_ASSIGNMENT"
    SKID_RETRIEVAL          = "STEP_SKID_RETRIEVAL"     # ← separate from location
    BASE_DROP               = "STEP_BASE_DROP"  
    # CARGO_MANIFEST    = "STEP_CARGO_MANIFEST"
    # DEPARTURE_CTRL    = "STEP_DEPARTURE_CTRL"
    # FLIGHT_CLOSE      = "STEP_FLIGHT_CLOSE"


# ✅ Separate display order — only used for UI/report rendering
# changing this never affects stored data
FLOW_DISPLAY_ORDER = [
    CarMessageFlowStep.AWB_MASTER,
    CarMessageFlowStep.SKID_ASSIGNMENT,
    CarMessageFlowStep.LOCATION_MAPPING,
    CarMessageFlowStep.FLIGHT_BOOKING,
    CarMessageFlowStep.ULD_ASSIGNMENT,
    CarMessageFlowStep.SKID_RETRIEVAL,      # ← after location
    CarMessageFlowStep.BASE_DROP,  
    # "STEP_CARGO_MANIFEST",
    # "STEP_DEPARTURE_CTRL",
    # "STEP_FLIGHT_CLOSE",
]


# 👌👌👌👌=================================== IMP Information =======================

# What record_id means in the audit log:
# It is the id of the specific record that was directly affected by the operation — so you can go back and look up that exact row in its table.

# module = "FLIGHT_BOOKING"   → record_id = flight_header_id
#                                            (row in export_flight_booking_header)

# module = "ULD_ASSIGNMENT"   → record_id = assignment_id
#                                            (row in export_uld_assignment)

# module = "SKID_ASSIGNMENT"  → record_id = mapping_id
#                                            (row in export_awb_skid_mapping)

# module = "LOCATION_MAPPING" → record_id = location_mapping_id
#                                            (row in export_skid_location_mapping)

# -----
# log says module="FLIGHT_BOOKING", record_id=6
# → go look at export_flight_booking_header WHERE id = 6

# log says module="ULD_ASSIGNMENT", record_id=3
# → go look at export_uld_assignment WHERE id = 3