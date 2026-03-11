# utils/clean_export_location_master.py

import pandas as pd
import numpy as np
from io import BytesIO

REQUIRED_COLUMNS = ["OPS TYPE", "AREA CODE", "LOC"]

def clean_export_location_master(file_bytes: BytesIO, file_type: str) -> pd.DataFrame:

    # 1️⃣ Read file
    if file_type == "excel":
        df = pd.read_excel(file_bytes, dtype=str)
    elif file_type == "csv":
        df = pd.read_csv(file_bytes, dtype=str)
    else:
        raise ValueError("Unsupported file type. Use 'excel' or 'csv'")

    # 2️⃣ Normalize columns
    df.columns = df.columns.str.strip().str.upper()

    # 3️⃣ Validate required columns
    missing_cols = [col for col in REQUIRED_COLUMNS if col not in df.columns]
    if missing_cols:
        raise ValueError(f"Missing required columns: {missing_cols}")

    # 4️⃣ Select only required columns
    df = df[REQUIRED_COLUMNS]

    # 5️⃣ Clean values
    df = df.replace(r"^\s*$", np.nan, regex=True)  # empty → NaN

    df = df.dropna(how="all")  # 😎 drop full empty rows

    for col in REQUIRED_COLUMNS:
        df[col] = df[col].astype(str).str.strip().str.upper()

    # 6️⃣ Remove rows with null after cleaning
    df = df.dropna()

    # 7️⃣ Remove duplicates
    df = df.drop_duplicates()

    df.reset_index(drop=True, inplace=True)

    return df