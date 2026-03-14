"""Route-level JWT auth tests for report endpoints.

These tests validate the request path:
Authorization header -> subject resolver -> owner-scoped repository access.
"""

from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import jwt
import pytest

from app.api import deps
from app.api.deps import reset_demo_storage
from app.auth.subject_resolver import AuthSubjectResolver
from app.auth.supabase_jwt import SupabaseJwtVerifier
from app.main import create_app

TEST_SECRET = "c" * 48
TEST_ISSUER = "https://api-test.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"


def _issue_token(
    *,
    sub: str,
    signing_secret: str = TEST_SECRET,
    exp_offset_seconds: int = 3600,
) -> str:
    payload = {
        "sub": sub,
        "aud": TEST_AUDIENCE,
        "iss": TEST_ISSUER,
        "exp": int(
            (datetime.now(timezone.utc) + timedelta(seconds=exp_offset_seconds)).timestamp()
        ),
        "email": f"{sub}@example.com",
    }
    return jwt.encode(payload, signing_secret, algorithm="HS256")


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_issue_token(sub=user_id)}"}


@pytest.fixture(autouse=True)
def _jwt_subject_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    """Use deterministic JWT subject resolution for each test."""

    reset_demo_storage()
    verifier = SupabaseJwtVerifier(
        jwt_secret=TEST_SECRET,
        expected_issuer=TEST_ISSUER,
        expected_audience=TEST_AUDIENCE,
        require_signature_verification=True,
    )
    resolver = AuthSubjectResolver(
        jwt_verifier=verifier,
    )
    monkeypatch.setattr(deps, "_request_subject_resolver", resolver)
    yield
    reset_demo_storage()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_reports_endpoint_requires_bearer_token(client: TestClient) -> None:
    response = client.get("/api/v1/reports")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Bearer token."


def test_reports_endpoint_rejects_invalid_token_signature(client: TestClient) -> None:
    token_with_wrong_signature = _issue_token(sub="user-1", signing_secret="d" * 48)
    response = client.get(
        "/api/v1/reports",
        headers={"Authorization": f"Bearer {token_with_wrong_signature}"},
    )

    assert response.status_code == 401
    assert response.json()["detail"] == "Token verification failed."


def test_reports_endpoint_ignores_legacy_session_header_without_bearer_token(
    client: TestClient,
) -> None:
    response = client.get("/api/v1/reports", headers={"X-Session-Id": "legacy-session"})

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Bearer token."


def test_authenticated_user_can_create_and_view_report_history(client: TestClient) -> None:
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/reports/analyze",
        json={"source_url": "https://service.example/terms"},
        headers=owner_headers,
    )
    assert create_response.status_code == 201
    created_report = create_response.json()

    list_response = client.get("/api/v1/reports", headers=owner_headers)
    assert list_response.status_code == 200
    listed_reports = list_response.json()
    assert len(listed_reports) == 1
    assert listed_reports[0]["id"] == created_report["id"]

    get_response = client.get(f"/api/v1/reports/{created_report['id']}", headers=owner_headers)
    assert get_response.status_code == 200
    assert get_response.json()["id"] == created_report["id"]


def test_reports_are_filtered_by_authenticated_owner(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/reports/analyze",
        json={"source_url": "https://owner-a.example/terms"},
        headers=_auth_headers("auth-user-a"),
    )
    assert create_response.status_code == 201
    report_id = create_response.json()["id"]

    list_owner_a = client.get("/api/v1/reports", headers=_auth_headers("auth-user-a"))
    list_owner_b = client.get("/api/v1/reports", headers=_auth_headers("auth-user-b"))
    get_owner_b = client.get(f"/api/v1/reports/{report_id}", headers=_auth_headers("auth-user-b"))

    assert list_owner_a.status_code == 200
    assert len(list_owner_a.json()) == 1
    assert list_owner_b.status_code == 200
    assert list_owner_b.json() == []
    assert get_owner_b.status_code == 404
