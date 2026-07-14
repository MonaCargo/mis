import os
import asyncio
import urllib.parse
import numpy as np
import pandas as pd
from sqlalchemy.ext.asyncio import create_async_engine, AsyncSession
from sqlalchemy.orm import sessionmaker
from datetime import datetime, timedelta, timezone




XRAY_MASTER = {
    "190595": {"machineNo": "No.1",           "device_model_no": "145180-2is",  "order": 1},
    "205102": {"machineNo": "No.2 (S)",       "device_model_no": "100100V-2is", "order": 2},
    "129846": {"machineNo": "No.3",           "device_model_no": "145180-2is",  "order": 3},
    "129730": {"machineNo": "No.4",           "device_model_no": "145180-2is",  "order": 4},
    "204042": {"machineNo": "No.5 (S)",       "device_model_no": "100100V-2is", "order": 5},
    "207812": {"machineNo": "No.6 (S)",       "device_model_no": "100100V-2is", "order": 6},
    "127187": {"machineNo": "No.7",           "device_model_no": "145180-2is",  "order": 7},
    "203888": {"machineNo": "No.8 (S)",       "device_model_no": "100100V-2is", "order": 8},
    "127105": {"machineNo": "No.9",           "device_model_no": "145180-2is",  "order": 9},
    "202833": {"machineNo": "No.10 (S)",      "device_model_no": "100100V-2is", "order": 10},
    "210212": {"machineNo": "No.11 (S)",      "device_model_no": "100100V-2is", "order": 11},
    "190802": {"machineNo": "No.12",          "device_model_no": "145180-2is",  "order": 12},
    "214551": {"machineNo": "No.13",          "device_model_no": "100100V-2is", "order": 13},
    "129729": {"machineNo": "No.14",          "device_model_no": "145180-2is",  "order": 14},
    "129149": {"machineNo": "No.15",          "device_model_no": "145180-2is",  "order": 15},
    "212146": {"machineNo": "No.16 (S)",      "device_model_no": "145180-2is",  "order": 16},
    "159928": {"machineNo": "No.17 (S)",      "device_model_no": "100100V-2is", "order": 17},
    "129836": {"machineNo": "No.18 (EXP TP)", "device_model_no": "145180-2is",  "order": 18},
    "204039": {"machineNo": "No.19 (IMP TP) (S)", "device_model_no": "100100V-2is", "order": 19},
    "190801": {"machineNo": "No.20 (IMP TP)", "device_model_no": "145180-2is",  "order": 20},
    "190992": {"machineNo": "No.21 (IMP TP)", "device_model_no": "145180-2is",  "order": 21},
}

# file_name = "app/utils/X-Ray Performance Report.csv"
file_name = "app/utils/digital_reports/customer_care_dept/X-Ray Performance Report.csv"

# 2. Extract Device ID from metadata before reading table
device_id = None
with open(file_name, 'r', encoding='utf-8', errors='ignore') as f:
    lines = f.readlines()
    file_content = "".join(lines)
    for key, meta in XRAY_MASTER.items():
        mach_clean = meta["machineNo"].replace(" ", "").split("(")[0]
        if key in file_content or mach_clean in file_content.replace(" ", ""):
            device_id = key
            break

    # Find where the table actually starts
    header_idx = None
    for idx, line in enumerate(lines):
        row_tokens = [token.strip().upper() for token in line.split(',')]
        if "MONTH" in row_tokens:
            header_idx = idx
            break

if header_idx is None:
    raise ValueError("Could not find the data table structure starting with 'Month'.")

# 3. Read the Raw Header Block (the row with 'Month' and the sub-header row right below it)
header_df = pd.read_csv(file_name, skiprows=header_idx, nrows=2, header=None)

# Process row 0 (Machine Names) and row 1 (Metrics like Baggage Count/Decision)
row0 = header_df.iloc[0].ffill().fillna("").tolist() # fill merged cell gaps
row1 = header_df.iloc[1].fillna("").tolist()
raw_headers = []
for r0, r1 in zip(row0, row1):
    r0_str, r1_str = str(r0).strip(), str(r1).strip()
    if r0_str == r1_str or not r1_str:
        raw_headers.append(r0_str)
    elif not r0_str:
        raw_headers.append(r1_str)
    else:
        raw_headers.append(f"{r0_str}_{r1_str}")
        
# Combine them uniquely
combined_headers = []
counts = {}
for name in raw_headers:
    if not name:
        name = "Unnamed"
    if name in counts:
        counts[name] += 1
        combined_headers.append(f"{name}_{counts[name]}")
    else:
        counts[name] = 0
        combined_headers.append(name)

# 4. Load the data using our clean headers
df = pd.read_csv(file_name, skiprows=header_idx + 2, header=None, names=combined_headers)
df.columns = [str(col).strip() for col in df.columns]

if 'Month' not in df.columns:
    potential_month_cols = [c for c in df.columns if 'month' in c.lower()]
    if potential_month_cols:
        # Us pehli column ka naam change karke exact 'Month' rakh dein
        df.rename(columns={potential_month_cols[0]: 'Month'}, inplace=True)
        print(f"🔄 Auto-mapped column '{potential_month_cols[0]}' to 'Month'")
    else:
        # Agar pehli column hi aapki month data hold karti hai (standard format ke mutabik)
        df.rename(columns={df.columns[0]: 'Month'}, inplace=True)
        print(f"🔄 Fallback: Auto-mapped the first column '{df.columns[0]}' to 'Month'")

# 5. Clean Data Rows: Keep ONLY valid month items (e.g., 'JUL\'26', 'Jun\'22')
month_regex = r"^[A-Za-z]{3}'\d{2}$"
df = df[df['Month'].astype(str).str.strip().str.match(month_regex, na=False)].copy()
df = df[~df['Month'].astype(str).str.strip().str.upper().str.startswith("JUL'26")].copy()
# 6. Global Cleanups (Remove empty trails, map strings)
df = df.replace(["-", r"^\s*$"], np.nan, regex=True)
df = df.replace(",", "", regex=True)

# Drop any columns that are entirely NaN/Empty
df = df.dropna(axis=1, how='all')

# 7. Inject Master Metadata
if device_id:
    meta = XRAY_MASTER[device_id]
    df.insert(0, "Order", meta["order"])
    df.insert(1, "Device_Model_No", meta["device_model_no"])
    df.insert(2, "Machine_No", meta["machineNo"])
    df.insert(3, "Device_ID", device_id)
    print(f"✅ Successfully auto-matched Device ID: {device_id}")
else:
    print("⚠️ Warning: Could not find matching Device ID in file headers.")

# Reset layout Indexing
df = df.reset_index(drop=True)

# Verify Output
print("\nFinal Polished Data Preview:")
print(df.head())




# Run the async loop handler
if __name__ == "__main__":
    
    # Save the target clean table backup locally
    df.to_csv("Cleaned_XRay_Report.csv", index=False)
    print("💾 Backup saved locally as 'Cleaned_XRay_Report.csv'")
# return_value = asyncio.run(MISReportService.save_monthly_report_to_db(df))
