# app/main.py

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.staticfiles import StaticFiles
from app.api.routes import api_v1_router
from dotenv import load_dotenv



load_dotenv()

app = FastAPI(
    title="Scalable FastAPI Backend",
    description="A modern backend with JWT auth, PostgreSQL, and clean architecture",
    version="1.0.0"
)
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
