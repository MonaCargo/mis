# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.routes import api_v1_router
from dotenv import load_dotenv
import logging 
from apscheduler.schedulers.asyncio import AsyncIOScheduler       
from app.services.importOperation.worker_assignment_service import auto_assign_job 
from app.services.exportOperation.car_message_flight_reconcile import run_reconcile_job 

load_dotenv()

logger = logging.getLogger(__name__)                   
scheduler = AsyncIOScheduler()       


app = FastAPI(
    title="Scalable FastAPI Backend",
    description="A modern backend with JWT auth, PostgreSQL, and clean architecture",
    version="1.0.0"
)



@app.on_event("startup")
async def _start_scheduler():

    # 🚫🚫🚫 DON'T TOUCH THIS JOB (By deepak)
    # scheduler.add_job(
    #     auto_assign_job,
    #     trigger="interval",
    #     seconds=120,  
    #     id="auto_assign",
    #     max_instances=1,
    #     coalesce=True,
    #     replace_existing=True,
    # )

     # ✅ ADD — reconcile departed flight bookings, hourly
    scheduler.add_job(
        run_reconcile_job,
        trigger="interval",
        seconds=1800,
        id="reconcile_departed_flight_bookings",
        max_instances=1,
        coalesce=True,
        replace_existing=True,
    )

    scheduler.start()
    logger.info("[scheduler] auto-assign started (every 5 min)")
    print(">>> SCHEDULER STARTED <<<")

@app.on_event("shutdown")
async def _stop_scheduler():
    scheduler.shutdown()



app.mount("/api/static", StaticFiles(directory="static"), name="static")
app.mount("/uploads", StaticFiles(directory="uploads"), name="uploads")

# CORS configuration (adjust origins as needed)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # Change to specific domains in production
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Register API routes
app.include_router(api_v1_router, prefix="/api")

@app.get("/health", tags=["Health"])
async def health_check():
    return {"message": "API is running! And health is OK.😎"}
