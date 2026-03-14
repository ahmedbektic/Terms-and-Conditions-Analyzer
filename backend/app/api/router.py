"""Top-level API router composition.

Layer: transport routing.
This keeps endpoint registration in one place so versioning and feature modules
remain easy to evolve.
"""

from fastapi import APIRouter

from .routes.agreements import router as agreements_router
from .routes.reports import router as reports_router

api_router = APIRouter()
api_router.include_router(agreements_router, tags=["agreements"])
api_router.include_router(reports_router, tags=["reports"])
