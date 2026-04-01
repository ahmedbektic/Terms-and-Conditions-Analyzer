"""FastAPI application bootstrap.

Layer: transport/bootstrap.
This module wires middleware and top-level routers, but keeps business logic
in route dependencies and services.
"""

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from .api.deps import get_request_rate_limiter
from .api.router import api_router
from .security import RateLimitExceededError
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
    request_rate_limiter = get_request_rate_limiter()

    @app.middleware("http")
    async def apply_request_rate_limits(request, call_next):
        try:
            evaluations = request_rate_limiter.evaluate(request)
        except RateLimitExceededError as error:
            response = JSONResponse(
                status_code=429,
                content={
                    "detail": error.detail,
                    "policy": error.evaluation.policy.name,
                    "retry_after_seconds": error.evaluation.retry_after_seconds,
                },
            )
            request_rate_limiter.apply_headers(
                response=response,
                evaluations=[error.evaluation],
            )
            return response

        response = await call_next(request)
        request_rate_limiter.apply_headers(response=response, evaluations=evaluations)
        return response

    app.include_router(api_router, prefix="/api/v1")

    @app.get("/health", tags=["health"])
    def health_check() -> dict[str, str]:
        return {"status": "ok"}

    return app


app = create_app()
