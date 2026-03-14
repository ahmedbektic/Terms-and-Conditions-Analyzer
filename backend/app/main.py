"""FastAPI application bootstrap.

Layer: transport/bootstrap.
This module wires middleware and top-level routers, but keeps business logic
in route dependencies and services.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from .api.router import api_router
from .core.config import settings


def create_app() -> FastAPI:
    """Create and configure the API application instance."""

    app = FastAPI(
        title="Terms and Conditions Analyzer API",
        version="0.1.0",
        description="MVP API for terms submission, analysis, and saved report retrieval.",
    )
    app.add_middleware(
        CORSMiddleware,
        allow_origins=settings.cors_allowed_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
