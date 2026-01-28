from enum import Enum


class OriginSourceType(str, Enum):
    OC_MERGE = "OC_MERGE"
    IRR = "IRR"
    IRM = "IRM"
