"""
app/main.py — Main FastAPI Application Entry Point for LoanMaster.
Configures lifespan events, includes domain routers, and mounts static frontend.
"""
from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
from sqlalchemy import select
import os

from app.database import AsyncSessionLocal
from app.models import User
from app.auth.utils import hash_password

# Import Domain Routers
from app.auth.router import router as auth_router
from app.routers.applications import router as applications_router
from app.routers.disbursements import router as disbursements_router
from app.routers.repayments import router as repayments_router
from app.routers.notifications import router as notifications_router
from app.routers.dashboard import router as dashboard_router
from app.routers.documents import router as documents_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: ensure default admin user exists for immediate access.
    Shutdown: clean up resources.
    """
    async with AsyncSessionLocal() as db:
        res = await db.execute(select(User).where(User.email == "admin@loanpulse.local"))
        if not res.scalar_one_or_none():
            admin = User(
                email="admin@loanpulse.local",
                hashed_password=hash_password("Admin123!"),
                full_name="System Administrator",
                role="ADMIN",
            )
            db.add(admin)
            await db.commit()
            print("[Lifespan] Initialized default admin user: admin@loanpulse.local / Admin123!")

    yield


app = FastAPI(
    title="LoanPulse: LoanMaster Management API",
    version="1.0.0",
    description="Full-stack loan application processing, AI risk assessment, disbursement, and repayment tracking.",
    lifespan=lifespan,
)

# Include Routers
app.include_router(auth_router)
app.include_router(applications_router)
app.include_router(disbursements_router)
app.include_router(repayments_router)
app.include_router(notifications_router)
app.include_router(dashboard_router)
app.include_router(documents_router)

# Mount Static Files for Frontend
static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=static_dir), name="static")


@app.get("/")
async def serve_index():
    """Serves the Single Page Application."""
    index_path = os.path.join(static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return {
        "name": "LoanPulse: LoanMaster API",
        "version": "1.0.0",
        "status": "online",
        "docs_url": "/docs",
        "frontend": "Creating index.html...",
    }