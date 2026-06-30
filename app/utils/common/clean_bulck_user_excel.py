# from fastapi import HTTPException
# import pandas as pd


# def parse_user_excel(file, role: str) -> list[dict]:
#     df = pd.read_excel(file)

#     # ✅ Normalize headers
#     df.columns = (
#         df.columns
#         .str.strip()
#         .str.lower()
#         .str.replace(" ", "_")
#     )

#     required = {"emp_id", "name"}
#     missing = required - set(df.columns)
#     if missing:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Missing required columns: {list(missing)}"
#         )

#     users = []
#     seen_emp_ids = set()

#     for idx, row in df.iterrows():
#         emp_id = row["emp_id"]
#         name = row["name"]

#         if pd.isna(emp_id) or pd.isna(name):
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Null value at Excel row {idx + 2}"
#             )

#         emp_id = str(emp_id).strip()
#         name = str(name).strip()

#         if not emp_id or not name:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Empty value at Excel row {idx + 2}"
#             )

#         if emp_id in seen_emp_ids:
#             raise HTTPException(
#                 status_code=400,
#                 detail=f"Duplicate emp_id '{emp_id}' at row {idx + 2}"
#             )

#         seen_emp_ids.add(emp_id)

#         users.append({
#             "emp_id": emp_id,
#             "name": name,
#             # "role": "exp_skd_cargo_loc_user"
#              "role": role,
#         })
    
#     print(df.head(10))

#     # raise HTTPException(
#     #             status_code=400,
#     #             detail=f"Duplicate emp_id checking"
#     #     )

#     return users
















from fastapi import HTTPException
import pandas as pd
import re

EMP_ID_REGEX = re.compile(r"^\d{6}$")  # exactly 6 digits

# Special handling for G$ security
IMP_SEC_ROLES = {"imp_sec_ll", "imp_sec_ul","imp_sec_ll_and_ul"}      # ← ADD
IMP_SEC_EMP_ID_REGEX = re.compile(r"^(?:[A-Za-z]\d{5}|\d{6})$") # ← ADD

def parse_user_excel(file, role: str) -> tuple[list[dict], list[dict]]:
    df = pd.read_excel(file)

    # Normalize headers
    df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

    required = {"emp_id", "name"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {list(missing)}",
        )

    valid_users: list[dict] = []
    invalid_users: list[dict] = []
    seen_emp_ids: set[str] = set()

    for idx, row in df.iterrows():
        excel_row = idx + 2  # +1 for 0-index, +1 for header row
        raw_emp_id = row["emp_id"]
        raw_name = row["name"]

        # Normalize emp_id — pandas may read 100001 as 100001.0 (float)
        if pd.isna(raw_emp_id):
            emp_id = ""
        elif isinstance(raw_emp_id, float):
            emp_id = str(int(raw_emp_id)) if raw_emp_id.is_integer() else str(raw_emp_id)
        else:
            emp_id = str(raw_emp_id).strip()

        name = "" if pd.isna(raw_name) else str(raw_name).strip()

        # --- validation ---
        if not emp_id:
            invalid_users.append({
                "emp_id": "",
                "name": name,
                "row": excel_row,
                "reason": "Empty emp_id",
            })
            continue

        if not name:
            invalid_users.append({
                "emp_id": emp_id,
                "name": "",
                "row": excel_row,
                "reason": "Empty name",
            })
            continue

        # if not EMP_ID_REGEX.match(emp_id):
        #     invalid_users.append({
        #         "emp_id": emp_id,
        #         "name": name,
        #         "row": excel_row,
        #         "reason": "emp_id must be exactly 6 digits (numbers only)",
        #     })
        #     continue

        if role in IMP_SEC_ROLES:
            if not IMP_SEC_EMP_ID_REGEX.match(emp_id):
                invalid_users.append({
                    "emp_id": emp_id,
                    "name": name,
                    "row": excel_row,
                    "reason": "emp_id must be 6 digits, or 1 letter followed by 5 digits",
                })
                continue
        else:
            if not EMP_ID_REGEX.match(emp_id):
                invalid_users.append({
                    "emp_id": emp_id,
                    "name": name,
                    "row": excel_row,
                    "reason": "emp_id must be exactly 6 digits (numbers only)",
                })
                continue

        if emp_id in seen_emp_ids:
            invalid_users.append({
                "emp_id": emp_id,
                "name": name,
                "row": excel_row,
                "reason": "Duplicate emp_id in the file",
            })
            continue

        seen_emp_ids.add(emp_id)
        valid_users.append({
            "emp_id": emp_id,
            "name": name,
            "role": role,
        })

    return valid_users, invalid_users





















# from fastapi import HTTPException
# import pandas as pd
# import re

# EMP_ID_REGEX = re.compile(r"^\d{6}$")  # exactly 6 digits

# # Special handling for roles with alphanumeric or leading-zero emp_ids
# IMP_SEC_ROLES = {"imp_sec_ll", "imp_sec_ul", "imp_sec_ll_and_ul", "imp_sec_truck_in_out_all"}  # ← added
# IMP_SEC_EMP_ID_REGEX = re.compile(r"^(?:[A-Za-z]\d{5}|\d{6})$")


# def parse_user_excel(file, role: str) -> tuple[list[dict], list[dict]]:
#     df = pd.read_excel(file)

#     df.columns = df.columns.str.strip().str.lower().str.replace(" ", "_")

#     required = {"emp_id", "name"}
#     missing = required - set(df.columns)
#     if missing:
#         raise HTTPException(
#             status_code=400,
#             detail=f"Missing required columns: {list(missing)}",
#         )

#     valid_users: list[dict] = []
#     invalid_users: list[dict] = []
#     seen_emp_ids: set[str] = set()

#     for idx, row in df.iterrows():
#         excel_row = idx + 2
#         raw_emp_id = row["emp_id"]
#         raw_name = row["name"]

#         # Normalize emp_id
#         # if pd.isna(raw_emp_id):
#         #     emp_id = ""
#         # elif isinstance(raw_emp_id, float):
#         #     if raw_emp_id.is_integer():
#         #         # ✅ Zero-pad back to 6 digits to preserve leading zeros
#         #         emp_id = str(int(raw_emp_id)).zfill(6)
#         #     else:
#         #         emp_id = str(raw_emp_id)
#         # else:
#         #     emp_id = str(raw_emp_id).strip()

#         # Normalize emp_id
#         if pd.isna(raw_emp_id):
#             emp_id = ""
#         elif isinstance(raw_emp_id, float):
#             if raw_emp_id.is_integer():
#                 emp_id = str(int(raw_emp_id)).zfill(6)   # 1211.0 → "001211"
#             else:
#                 emp_id = str(raw_emp_id)
#         elif isinstance(raw_emp_id, int):                 # ← ADD THIS BRANCH
#             emp_id = str(raw_emp_id).zfill(6)             # 1211 → "001211"
#         else:
#             emp_id = str(raw_emp_id).strip()

#         name = "" if pd.isna(raw_name) else str(raw_name).strip()

#         # --- validation ---
#         if not emp_id:
#             invalid_users.append({"emp_id": "", "name": name, "row": excel_row, "reason": "Empty emp_id"})
#             continue

#         if not name:
#             invalid_users.append({"emp_id": emp_id, "name": "", "row": excel_row, "reason": "Empty name"})
#             continue

#         if role in IMP_SEC_ROLES:
#             if not IMP_SEC_EMP_ID_REGEX.match(emp_id):
#                 invalid_users.append({
#                     "emp_id": emp_id, "name": name, "row": excel_row,
#                     "reason": "emp_id must be 6 digits, or 1 letter followed by 5 digits",
#                 })
#                 continue
#         else:
#             if not EMP_ID_REGEX.match(emp_id):
#                 invalid_users.append({
#                     "emp_id": emp_id, "name": name, "row": excel_row,
#                     "reason": "emp_id must be exactly 6 digits (numbers only)",
#                 })
#                 continue

#         if emp_id in seen_emp_ids:
#             invalid_users.append({"emp_id": emp_id, "name": name, "row": excel_row, "reason": "Duplicate emp_id in the file"})
#             continue

#         seen_emp_ids.add(emp_id)
#         valid_users.append({"emp_id": emp_id, "name": name, "role": role})

#     return valid_users, invalid_users