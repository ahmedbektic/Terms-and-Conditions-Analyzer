from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import jwt
import pytest

from app.api import deps
from app.api.deps import reset_demo_storage
from app.auth.subject_resolver import AuthSubjectResolver
from app.auth.supabase_jwt import SupabaseJwtVerifier
from app.main import create_app

TEST_SECRET = "f" * 48
TEST_ISSUER = "https://agreements-test.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"


def _issue_token(*, sub: str, exp_offset_seconds: int = 3600) -> str:
    payload = {
        "sub": sub,
        "aud": TEST_AUDIENCE,
        "iss": TEST_ISSUER,
        "exp": int(
            (datetime.now(timezone.utc) + timedelta(seconds=exp_offset_seconds)).timestamp()
        ),
    }
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def _auth_headers(user_id: str) -> dict[str, str]:
    return {"Authorization": f"Bearer {_issue_token(sub=user_id)}"}


@pytest.fixture(autouse=True)
def _clear_storage(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_demo_storage()
    verifier = SupabaseJwtVerifier(
        jwt_secret=TEST_SECRET,
        expected_issuer=TEST_ISSUER,
        expected_audience=TEST_AUDIENCE,
        require_signature_verification=True,
    )
    monkeypatch.setattr(
        deps,
        "_request_subject_resolver",
        AuthSubjectResolver(jwt_verifier=verifier),
    )


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_create_agreement_then_trigger_manual_analysis(client: TestClient) -> None:
    create_payload = {
        "title": "Demo Terms",
        "source_url": "https://demo.example/terms",
        "terms_text": (
            "These terms include arbitration and a class action waiver. "
            "The subscription renews automatically unless canceled."
        ),
    }
    create_response = client.post(
        "/api/v1/agreements",
        json=create_payload,
        headers=_auth_headers("user-a"),
    )
    assert create_response.status_code == 201
    agreement = create_response.json()
    assert agreement["id"]
    assert agreement["title"] == "Demo Terms"

    analyze_response = client.post(
        f"/api/v1/agreements/{agreement['id']}/analyses",
        json={"trigger": "manual"},
        headers=_auth_headers("user-a"),
    )
    assert analyze_response.status_code == 201
    report = analyze_response.json()
    assert report["summary"]
    assert report["trust_score"] >= 0
    assert report["flagged_clauses"] != []


def test_create_agreement_rejects_short_terms_text(client: TestClient) -> None:
    response = client.post(
        "/api/v1/agreements",
        json={"terms_text": "too short"},
        headers=_auth_headers("user-a"),
    )
    assert response.status_code == 422


def test_trigger_manual_analysis_rejects_invalid_trigger(client: TestClient) -> None:
    create_response = client.post(
        "/api/v1/agreements",
        json={"terms_text": "This is a valid terms body with enough characters."},
        headers=_auth_headers("user-a"),
    )
    agreement_id = create_response.json()["id"]

    response = client.post(
        f"/api/v1/agreements/{agreement_id}/analyses",
        json={"trigger": "automatic"},
        headers=_auth_headers("user-a"),
    )
    assert response.status_code == 400
    assert "manual" in response.json()["detail"]
