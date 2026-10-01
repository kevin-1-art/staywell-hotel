import logging
from contextlib import asynccontextmanager

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from starlette.middleware.trustedhost import TrustedHostMiddleware
from slowapi import Limiter, _rate_limit_exceeded_handler
from slowapi.errors import RateLimitExceeded
from slowapi.util import get_remote_address
from sqlalchemy import text

from app.config import settings
from app.database import SessionLocal
from app.routers.guests import router as guests_router
from app.routers.housekeeping import router as housekeeping_router
from app.routers.auth import router as auth_router
from app.routers.maintenance import router as maintenance_router
from app.routers.reservations import router as reservations_router
from app.routers.operations import router as operations_router
from app.routers.reports import router as reports_router
from app.routers.rooms import router as rooms_router
from app.routers.stays import router as stays_router
from app.routers.users import router as users_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")
logger = logging.getLogger("hotel.api")


@asynccontextmanager
async def lifespan(_: FastAPI):
    logger.info("Hotel API started")
    yield
    logger.info("Hotel API stopped")


app = FastAPI(
    title=settings.app_name,
    version="0.1.0",
    description="Hotel operations API. OpenAPI is available at /docs.",
    lifespan=lifespan,
)
limiter = Limiter(key_func=get_remote_address, default_limits=["300/minute"])
app.state.limiter = limiter
app.add_exception_handler(RateLimitExceeded, _rate_limit_exceeded_handler)
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.cors_origins,
    allow_credentials=True,
    allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE"],
    allow_headers=["Authorization", "Content-Type"],
)
app.add_middleware(TrustedHostMiddleware, allowed_hosts=settings.trusted_hosts)


@app.middleware("http")
async def security_headers(request, call_next):
    response = await call_next(request)
    response.headers["X-Content-Type-Options"] = "nosniff"
    response.headers["X-Frame-Options"] = "DENY"
    response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"
    response.headers["Permissions-Policy"] = "camera=(), microphone=(), geolocation=()"
    if request.url.path.startswith("/api/"):
        response.headers["Cache-Control"] = "no-store"
    return response
app.include_router(auth_router, prefix="/api/v1")
app.include_router(rooms_router, prefix="/api/v1")
app.include_router(guests_router, prefix="/api/v1")
app.include_router(reservations_router, prefix="/api/v1")
app.include_router(stays_router)
app.include_router(housekeeping_router, prefix="/api/v1")
app.include_router(maintenance_router, prefix="/api/v1")
app.include_router(operations_router)
app.include_router(reports_router)
app.include_router(users_router, prefix="/api/v1")


@app.get("/health", tags=["System"])
def health() -> dict[str, str]:
    with SessionLocal() as db:
        db.execute(text("SELECT 1"))
    return {"status": "ok", "database": "connected"}