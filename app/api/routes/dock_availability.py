from fastapi import APIRouter, Depends
from sqlalchemy.ext.asyncio import AsyncSession
from app.db.session import get_db
from app.services import dock_availability_service
from app.schemas.user import UserRead
from app.core.dependency import verify_token_and_get_user


router = APIRouter()

@router.get("/availability")
async def get_dock_availability(
    db: AsyncSession = Depends(get_db),
    current_user: UserRead = Depends(verify_token_and_get_user),  # Get the current authenticated user

    ):
    docks = await dock_availability_service.get_all_docks(db)
    available = [d for d in docks if not d.is_dock_occupied]
    occupied = [d for d in docks if d.is_dock_occupied]

    return {
        "success": True,
        "data": {
            "total_docks": len(docks),
            "available_count": len(available),
            "occupied_count": len(occupied),
            "docks": [
                {
                    "dock_no": d.dock_no,
                    "dock_in_time": d.dock_in_time,
                    "is_dock_occupied": d.is_dock_occupied
                }
                for d in docks
            ]
        }
    }

@router.post("/occupy")
async def occupy_dock(dock_no: str,
                       db: AsyncSession = Depends(get_db),
                       current_user: UserRead = Depends(verify_token_and_get_user),  # Get the current authenticated user
                    ):
    dock = await dock_availability_service.occupy_dock(db, dock_no)
    return {
        "success": True,
        "message": f"Dock {dock_no} marked as occupied",
        "data": {
            "dock_no": dock.dock_no,
            "dock_in_time": dock.dock_in_time,
            "is_dock_occupied": dock.is_dock_occupied
        }
    }

@router.post("/release")
async def release_dock(dock_no: str,
                        db: AsyncSession = Depends(get_db),
                        current_user: UserRead = Depends(verify_token_and_get_user),  # Get the current authenticated user

                        ):
    dock = await dock_availability_service.release_dock(db, dock_no)
    return {
        "success": True,
        "message": f"Dock {dock_no} is now available",
        "data": {
            "dock_no": dock.dock_no,
            "dock_in_time": dock.dock_in_time,
            "is_dock_occupied": dock.is_dock_occupied
        }
    }

@router.post("/create")
async def create_dock(dock_no: str,
                       db: AsyncSession = Depends(get_db),
                        current_user: UserRead = Depends(verify_token_and_get_user), 
                       ):
    """Create a new dock"""
    dock = await dock_availability_service.create_dock(db, dock_no)
    return {
        "success": True,
        "message": f"Dock {dock_no} created successfully",
        "data": {
            "dock_no": dock.dock_no,
            "dock_in_time": dock.dock_in_time,
            "is_dock_occupied": dock.is_dock_occupied
        }
    }

@router.get("/details/{dock_no}")
async def get_dock_details(dock_no: str, db: AsyncSession = Depends(get_db),current_user: UserRead = Depends(verify_token_and_get_user)):
    """Get dock details including employee info"""
    details = await dock_availability_service.get_dock_details(db, dock_no)
    return {"success": True, "data": details}