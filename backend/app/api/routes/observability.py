"""Opt-in observability verification hooks for local/manual smoke checks."""

from fastapi import APIRouter, HTTPException, status

from ...core.config import settings

router = APIRouter(prefix="/observability")


@router.post("/sentry-test", status_code=status.HTTP_202_ACCEPTED)
def trigger_sentry_test_event() -> dict[str, str]:
    """Raise a test exception when observability verification routes are enabled."""

    if not settings.observability_enable_test_routes:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail="Not found.")

    raise RuntimeError("SCRUM-93 backend Sentry test event")
