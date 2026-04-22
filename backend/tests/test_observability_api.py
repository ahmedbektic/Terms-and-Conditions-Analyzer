from dataclasses import replace

from fastapi.testclient import TestClient
import pytest

from app.api.routes import observability as observability_route
from app.core.config import settings as app_settings
from app.main import create_app


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_sentry_test_route_returns_404_when_disabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        observability_route,
        "settings",
        replace(app_settings, observability_enable_test_routes=False),
    )

    response = client.post("/api/v1/observability/sentry-test")

    assert response.status_code == 404


def test_sentry_test_route_raises_when_enabled(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        observability_route,
        "settings",
        replace(app_settings, observability_enable_test_routes=True),
    )

    with pytest.raises(RuntimeError, match="SCRUM-93 backend Sentry test event"):
        client.post("/api/v1/observability/sentry-test")
