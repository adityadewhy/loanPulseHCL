"""
app/main.py — LoanPulse FastAPI Application Entry Point.

Responsibilities:
- Configure structured logging before anything else
- Lifespan: validate config, seed default admin, start background scheduler
- CORS middleware (configurable via env)
- Mount domain routers and static frontend
- Expose /health check endpoint
"""
import logging
import os
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from fastapi.staticfiles import StaticFiles
from sqlalchemy import select, text

from app.logging_config import setup_logging

# ── Logging must be configured before any other app imports ────────────────
setup_logging()
logger = logging.getLogger(__name__)

from app.auth.utils import hash_password  # noqa: E402
from app.config import settings  # noqa: E402
from app.database import AsyncSessionLocal, engine  # noqa: E402
from app.models import User  # noqa: E402

# Import Domain Routers
from app.auth.router import router as auth_router  # noqa: E402
from app.routers.applications import router as applications_router  # noqa: E402
from app.routers.disbursements import router as disbursements_router  # noqa: E402
from app.routers.repayments import router as repayments_router  # noqa: E402
from app.routers.notifications import router as notifications_router  # noqa: E402
from app.routers.dashboard import router as dashboard_router  # noqa: E402
from app.routers.documents import router as documents_router  # noqa: E402

# ── Startup / Shutdown ─────────────────────────────────────────────────────

@asynccontextmanager
async def lifespan(app: FastAPI):
    """
    Startup: validate critical config, seed default admin user, warm DB pool.
    Shutdown: log graceful exit.
    """
    # Validate minimum required configuration
    if not settings.database_url:
        raise RuntimeError("DATABASE_URL is not set — cannot start without a database connection.")
    if settings.secret_key.startswith("dev-insecure"):
        logger.warning("SECRET_KEY is using an insecure dev default — set a strong key in production.")

    # Seed default admin user (idempotent)
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
            logger.info("Seeded default admin user: admin@loanpulse.local")
        else:
            logger.info("Admin user already exists — skipping seed.")

    logger.info("LoanPulse API started — version %s", APP_VERSION)
    yield
    logger.info("LoanPulse API shutting down.")


# ── Application Instance ───────────────────────────────────────────────────

APP_VERSION = "1.0.0"

app = FastAPI(
    title="LoanPulse API",
    version=APP_VERSION,
    description=(
        "Full-stack loan origination, AI risk underwriting, "
        "disbursement, and repayment tracking platform."
    ),
    lifespan=lifespan,
    # Disable Swagger/ReDoc in production if desired via env flag
    docs_url="/docs" if os.getenv("ENABLE_DOCS", "true").lower() == "true" else None,
    redoc_url=None,
)

# ── CORS ───────────────────────────────────────────────────────────────────
# ALLOWED_ORIGINS env var: comma-separated list, e.g. "https://myapp.com,https://www.myapp.com"
# Defaults to "*" for local development only.
_raw_origins = os.getenv("ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in _raw_origins.split(",") if o.strip()]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type", "Accept"],
)

# ── Routers ────────────────────────────────────────────────────────────────
app.include_router(auth_router)
app.include_router(applications_router)
app.include_router(disbursements_router)
app.include_router(repayments_router)
app.include_router(notifications_router)
app.include_router(dashboard_router)
app.include_router(documents_router)

# ── Static Frontend ────────────────────────────────────────────────────────
_static_dir = os.path.join(os.path.dirname(__file__), "static")
os.makedirs(_static_dir, exist_ok=True)
app.mount("/static", StaticFiles(directory=_static_dir), name="static")


# ── Routes ─────────────────────────────────────────────────────────────────

@app.get("/", include_in_schema=False)
async def serve_index():
    """Serves the Single Page Application shell."""
    index_path = os.path.join(_static_dir, "index.html")
    if os.path.exists(index_path):
        return FileResponse(index_path)
    return JSONResponse(
        {"name": "LoanPulse API", "version": APP_VERSION, "status": "online", "docs": "/docs"},
        status_code=200,
    )


@app.get("/health", tags=["System"], summary="Health check")
async def health_check():
    """
    Returns HTTP 200 with DB connectivity status.
    Used by load balancers, Docker HEALTHCHECK, and monitoring systems.
    """
    db_ok = False
    try:
        async with AsyncSessionLocal() as db:
            await db.execute(text("SELECT 1"))
            db_ok = True
    except Exception as exc:
        logger.error("Health check DB ping failed: %s", exc)

    status = "healthy" if db_ok else "degraded"
    return JSONResponse(
        {"status": status, "version": APP_VERSION, "database": "ok" if db_ok else "error"},
        status_code=200 if db_ok else 503,
    )