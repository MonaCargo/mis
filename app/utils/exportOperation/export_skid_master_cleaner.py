import re

import pandas as pd
import numpy as np
from typing import Tuple
from io import BytesIO

from app.utils.common.enums import ExoportSkidtypeValue


def clean_export_skid_master(file_bytes: BytesIO, file_type: str):

    if file_type == "excel":
        df = pd.read_excel(file_bytes,dtype=str)
    else:
        df = pd.read_csv(file_bytes,dtype=str)

    df.columns = [str(c).strip().upper() for c in df.columns]

    required_cols = ["SKID NO.", "SKID WT", "SKID CAPACITY"]

    for col in required_cols:
        if col not in df.columns:
            raise ValueError(f"Missing required column: {col}")

    cleaned = []
    faulty = []

    for _, row in df.iterrows():

        skid_no_raw = row.get("SKID NO.")
        skid_wgt = row.get("SKID WT")
        skid_capacity = row.get("SKID CAPACITY")
        remarks = row.get("REMARKS")
        status = row.get("SKID STATUS")

        if pd.isna(skid_no_raw):
            faulty.append(row.to_dict())
            continue

        

        skid_no = str(skid_no_raw).strip()

        # Remove only unwanted wrapping characters
        skid_no = re.sub(r'[,"\']', '', skid_no).strip()

        if not skid_no:
            faulty.append(row.to_dict())
            continue

        cleaned.append({
            "skid_no": skid_no,
            "skid_wgt": float(skid_wgt) if not pd.isna(skid_wgt) else None,
            "skid_capacity": float(skid_capacity) if not pd.isna(skid_capacity) else None,
            "remarks": str(remarks).strip() if not pd.isna(remarks) else None,
            "skid_type": "REAL",
            "is_active": False if str(status).strip().upper() == "N" else True,
            "is_locked": False
        })

    cleaned_df = pd.DataFrame(cleaned).replace({np.nan: None})
    faulty_df = pd.DataFrame(faulty).replace({np.nan: None})

    return cleaned_df, faulty_df