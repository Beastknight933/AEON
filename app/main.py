from contextlib import asynccontextmanager
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from app.core.config import settings
from app.core.logging import setup_logging, get_logger
from app.middleware.correlation import CorrelationIdMiddleware
from app.middleware.error_handler import register_error_handlers
from app.api.v1.health import router as health_router
from app.api.v1.auth import router as auth_router
from app.api.v1.agents import router as agents_router
from app.api.v1.policies import router as policies_router
from app.api.v1.budgets import router as budgets_router

setup_logging(debug=settings.DEBUG)
logger = get_logger("aeon.main")


@asynccontextmanager
async def lifespan(app: FastAPI):
    logger.info(f"Starting {settings.APP_NAME} in [{settings.APP_ENV}] mode (Milestone 2: Policies & Budgets)")
    yield
    logger.info(f"Shutting down {settings.APP_NAME}")


def create_application() -> FastAPI:
    app = FastAPI(
        title=settings.APP_NAME,
        description="AEON: Agent Procurement Control Plane — Milestone 2: Procurement Policies & Budget Integrity Engine.",
        version="1.0.0",
        docs_url="/docs",
        redoc_url="/redoc",
        openapi_url="/openapi.json",
        lifespan=lifespan,
    )

    # Correlation ID middleware
    app.add_middleware(CorrelationIdMiddleware)

    # CORS configuration (Strict origins, never wildcard with credentials)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.CORS_ORIGINS,
        allow_credentials=True,
        allow_methods=["GET", "POST", "PUT", "PATCH", "DELETE", "OPTIONS"],
        allow_headers=["*"],
        expose_headers=["X-Correlation-ID", "Content-Disposition"],
    )

    # Centralized error handlers
    register_error_handlers(app)

    # Mount Milestone 1 & 2 routers
    app.include_router(health_router)
    app.include_router(health_router, prefix=settings.API_V1_PREFIX)
    app.include_router(auth_router, prefix=settings.API_V1_PREFIX)
    app.include_router(agents_router, prefix=settings.API_V1_PREFIX)
    app.include_router(policies_router, prefix=settings.API_V1_PREFIX)
    app.include_router(budgets_router, prefix=settings.API_V1_PREFIX)

    @app.get("/", tags=["Root"])
    async def root():
        return {
            "message": "AEON Agent Procurement Control Plane API (Milestone 2)",
            "docs": "/docs",
            "version": "1.0.0",
            "health": "/health",
        }

    return app


app = create_application()
