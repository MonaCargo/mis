from fastapi import APIRouter, Depends
from fastapi.responses import FileResponse
from dotenv import load_dotenv

load_dotenv()
import os
APP_VERSION = os.getenv("APP_VERSION")


router = APIRouter()

@router.get("/apk-version")
async def get_app_version():
    print(f"App Version from env: {APP_VERSION}")
    return {"version": APP_VERSION}


@router.get("/download-apk")
def download_apk():
    return FileResponse("static/app-release.apk", media_type="application/vnd.android.package-archive", filename="app-release.apk")