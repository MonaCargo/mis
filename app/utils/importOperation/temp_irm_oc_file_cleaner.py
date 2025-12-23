import pandas as pd
from typing import BinaryIO
from fastapi import HTTPException
from datetime import datetime
import pytz


# ======================================================
# STRICT AWB NORMALIZATION (FAIL-FAST)
# ======================================================
def normalize_awb_no(awb: any) -> str | None:
    """
    STRICT AWB validation:
    - ONLY digits allowed (0–9)
    - Length must be exactly 10 or 11
    - If 10 digits → pad leading zero
    - Any other format → REJECT
    """
    if pd.isna(awb) or awb is None:
        return None

    awb_str = str(awb).strip()

    if awb_str == "":
        return None

    if awb_str.upper() in {"NAN", "NONE", "NULL", "N/A", "NA"}:
        return None

    # ❌ Reject if contains anything except digits
    if not awb_str.isdigit():
        return None

    if len(awb_str) == 10:
        return "0" + awb_str
    elif len(awb_str) == 11:
        return awb_str

    return None


# ======================================================
# HAWB NORMALIZATION (OPTIONAL)
# ======================================================
def normalize_hawb_no(hawb: any) -> str | None:
    if pd.isna(hawb) or hawb is None:
        return None

    hawb_str = str(hawb).strip().upper()

    if hawb_str in {"", "NAN", "NONE", "NULL", "N/A"}:
        return None

    return hawb_str


# ======================================================
# IST → UTC DATETIME PARSER
# ======================================================
def parse_integrate_datetime(value: any) -> datetime | None:
    """
    Parse integrate_date_time from multiple formats.
    Assumes input is IST and converts to UTC.
    """
    if pd.isna(value) or value is None or str(value).strip() == "":
        return None

    ist = pytz.timezone("Asia/Kolkata")

    # Pandas Timestamp or datetime
    if isinstance(value, (pd.Timestamp, datetime)):
        if value.tzinfo is None:
            value = ist.localize(value)
        return value.astimezone(pytz.utc)

    value_str = str(value).strip()

    formats = [
        "%m/%d/%Y %I:%M:%S %p",
        "%d/%m/%Y %I:%M:%S %p",
        "%m/%d/%Y %H:%M:%S",
        "%d/%m/%Y %H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%d-%m-%Y %H:%M:%S",
        "%m/%d/%Y %I:%M %p",
        "%d/%m/%Y %I:%M %p",
        "%m/%d/%Y %H:%M",
        "%d/%m/%Y %H:%M",
        "%Y-%m-%d %H:%M",
        "%d-%m-%Y %H:%M",
    ]

    for fmt in formats:
        try:
            naive = datetime.strptime(value_str, fmt)
            return ist.localize(naive).astimezone(pytz.utc)
        except ValueError:
            continue

    return None


# ======================================================
# MAIN FILE CLEANER (STRICT + FAIL-FAST)
# ======================================================
def clean_and_parse_fast_track_file(
    file: BinaryIO,
    file_type: str
) -> pd.DataFrame:
    """
    Expected columns:
    - AWBNO (required)
    - HWBNO (optional)
    - INTEGRATE DATE & TIME (required)

    ❌ Any invalid row → whole file rejected
    """
    try:
        # --------------------------------------------------
        # 1️⃣ Read file
        # --------------------------------------------------
        if file_type == "excel":
            df = pd.read_excel(file, engine="openpyxl")
        else:
            df = pd.read_csv(file)

        # --------------------------------------------------
        # 2️⃣ Normalize column names
        # --------------------------------------------------
        df.columns = df.columns.str.strip()

        rename_map = {
            "AWBNO": "awb_no",
            "AWB NO": "awb_no",
            "AWB_NO": "awb_no",
            "HWBNO": "hawb",
            "HAWB NO": "hawb",
            "HAWB_NO": "hawb",
            "INTEGRATE DATE & TIME": "integrate_date_time",
            "INTEGRATE DATE TIME": "integrate_date_time",
            "INTEGRATE_DATE_TIME": "integrate_date_time",
        }

        df = df.rename(columns=rename_map)

        # --------------------------------------------------
        # 3️⃣ Required columns check
        # --------------------------------------------------
        required_cols = ["awb_no", "integrate_date_time"]
        missing = [c for c in required_cols if c not in df.columns]

        if missing:
            raise ValueError(
                f"Missing required columns: {missing}. "
                f"Expected columns: AWBNO, HWBNO, INTEGRATE DATE & TIME"
            )

        if "hawb" not in df.columns:
            df["hawb"] = None

        df = df[["awb_no", "hawb", "integrate_date_time"]]
        df = df.dropna(how="all").reset_index(drop=True)

        # --------------------------------------------------
        # 4️⃣ STRICT AWB VALIDATION
        # --------------------------------------------------
        df["awb_no"] = df["awb_no"].apply(normalize_awb_no)

        invalid_awb = df[df["awb_no"].isna()]
        if not invalid_awb.empty:
            rows = (invalid_awb.index + 2).tolist()
            raise ValueError(
                "Invalid AWB number detected.\n"
                "Rules:\n"
                "- Only digits allowed\n"
                "- Length must be exactly 10 or 11\n"
                "- No spaces, letters, or special characters\n"
                f"Invalid rows (Excel row numbers): {rows[:10]}"
            )

        # --------------------------------------------------
        # 5️⃣ Normalize HAWB
        # --------------------------------------------------
        df["hawb"] = df["hawb"].apply(normalize_hawb_no)

        # --------------------------------------------------
        # 6️⃣ Parse integrate_date_time
        # --------------------------------------------------
        df["integrate_date_time"] = df["integrate_date_time"].apply(
            parse_integrate_datetime
        )

        invalid_dates = df[df["integrate_date_time"].isna()]
        if not invalid_dates.empty:
            rows = (invalid_dates.index + 2).tolist()
            raise ValueError(
                f"Invalid INTEGRATE DATE & TIME at rows: {rows[:10]}"
            )

        # --------------------------------------------------
        # 7️⃣ Remove duplicate AWB + HAWB
        # --------------------------------------------------
        df = df.drop_duplicates(subset=["awb_no", "hawb"], keep="first")

        if df.empty:
            raise ValueError("No valid records found after validation")
        
        print("Preview of cleaned data (top 10 rows):")
        print(df.head(10).to_string(index=False))


        return df.reset_index(drop=True)

    except ValueError as ve:
        raise HTTPException(status_code=400, detail=str(ve))
    except Exception as e:
        raise HTTPException(
            status_code=400,
            detail=f"File parsing error: {str(e)}"
        )


# # ======================================================
# # RECORD-LEVEL VALIDATION (OPTIONAL)
# # ======================================================
# def validate_fast_track_data(record: dict) -> tuple[bool, str]:
#     """
#     Assumes AWB already normalized & validated.
#     """
#     if not record.get("awb_no"):
#         return False, "AWB missing"

#     if not record.get("integrate_date_time"):
#         return False, "Integrate date & time missing"

#     if not isinstance(record["integrate_date_time"], datetime):
#         return False, "Invalid integrate_date_time"

#     return True, ""




# def get_fast_track_sample_format() -> dict:
#     """
#     Return sample format for fast-track Excel file.
#     Use this to generate a template or show users the expected format.
#     """
#     return {
#         "columns": ["AWBNO", "HWBNO", "INTEGRATE DATE & TIME"],
#         "sample_data": [
#             {
#                 "AWBNO": "12345678",
#                 "HWBNO": "H12345",
#                 "INTEGRATE DATE & TIME": "11/10/2025 5:20:00 PM"
#             },
#             {
#                 "AWBNO": "87654321",
#                 "HWBNO": "",
#                 "INTEGRATE DATE & TIME": "11/10/2025 6:30:00 PM"
#             },
#             {
#                 "AWBNO": "11223344",
#                 "HWBNO": "H67890",
#                 "INTEGRATE DATE & TIME": "12/15/2025 2:45:00 PM"
#             }
#         ],
#         "notes": [
#             "AWBNO: Required, minimum 8 characters, alphanumeric",
#             "HWBNO: Optional, can be blank or empty",
#             "INTEGRATE DATE & TIME: Required, format '11/10/2025 5:20:00 PM' or '11/10/2025 17:20:00'",
#             "Duplicate AWB+HWBNO combinations will be automatically removed (first occurrence kept)"
#         ]
#     }