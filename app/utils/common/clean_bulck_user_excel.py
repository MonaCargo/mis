from fastapi import HTTPException
import pandas as pd


def parse_user_excel(file) -> list[dict]:
    df = pd.read_excel(file)

    # ✅ Normalize headers
    df.columns = (
        df.columns
        .str.strip()
        .str.lower()
        .str.replace(" ", "_")
    )

    required = {"emp_id", "name"}
    missing = required - set(df.columns)
    if missing:
        raise HTTPException(
            status_code=400,
            detail=f"Missing required columns: {list(missing)}"
        )

    users = []
    seen_emp_ids = set()

    for idx, row in df.iterrows():
        emp_id = row["emp_id"]
        name = row["name"]

        if pd.isna(emp_id) or pd.isna(name):
            raise HTTPException(
                status_code=400,
                detail=f"Null value at Excel row {idx + 2}"
            )

        emp_id = str(emp_id).strip()
        name = str(name).strip()

        if not emp_id or not name:
            raise HTTPException(
                status_code=400,
                detail=f"Empty value at Excel row {idx + 2}"
            )

        if emp_id in seen_emp_ids:
            raise HTTPException(
                status_code=400,
                detail=f"Duplicate emp_id '{emp_id}' at row {idx + 2}"
            )

        seen_emp_ids.add(emp_id)

        users.append({
            "emp_id": emp_id,
            "name": name,
            "role": "exp_skd_cargo_loc_user"
        })
    
    print(df.head(10))

    # raise HTTPException(
    #             status_code=400,
    #             detail=f"Duplicate emp_id checking"
    #     )

    return users
