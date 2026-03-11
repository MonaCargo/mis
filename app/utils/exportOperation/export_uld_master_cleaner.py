import io
from typing import List, Dict, Any
from sqlalchemy.orm import Session
import pandas as pd

COLUMN_MAPPING = {
    "uld no.": "uld_no",   # exact Excel header
    "carrier": "carrier",  # exact Excel header
}



def parse_uld_excel(file_bytes: bytes) -> List[Dict[str, str]]:
    """Parse uploaded Excel file and return list of {uld_no, carrier} dicts."""
    df = pd.read_excel(io.BytesIO(file_bytes))


    # Strip whitespace from column names, then map to our internal names
    df.columns = [col.strip() for col in df.columns]
    df = df.rename(columns=lambda col: COLUMN_MAPPING.get(col.lower(), col))

    # # Expect columns: uld_no, carrier
    # required = {"uld_no", "carrier"}
    # if not required.issubset(set(df.columns)):
    #     raise ValueError(f"Excel must contain columns: {required}. Found: {set(df.columns)}")

    # Validate required columns are present after mapping
    required = {"uld_no", "carrier"}
    missing = required - set(df.columns)
    if missing:
        raise ValueError(
            f"Could not map required columns: {missing}. "
            f"Excel columns found: {list(df.columns)}. "
            f"Supported names: {list(COLUMN_MAPPING.keys())}"
        )

    df = df.dropna(subset=["uld_no", "carrier"])
    df["uld_no"] = df["uld_no"].astype(str).str.strip()
    df["carrier"] = df["carrier"].astype(str).str.strip()

    return df[["uld_no", "carrier"]].to_dict(orient="records")

