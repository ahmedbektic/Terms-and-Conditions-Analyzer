from datetime import datetime, timedelta, timezone
import re

from fastapi.testclient import TestClient
import jwt
import pytest

from app.api import deps
from app.api.deps import reset_demo_storage
from app.auth.subject_resolver import AuthSubjectResolver
from app.auth.supabase_jwt import SupabaseJwtVerifier
from app.main import create_app
from app.security.rate_limit import RateLimitPolicy, RequestRateLimiter

TEST_SECRET = "g" * 48
TEST_ISSUER = "https://rate-limit-test.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"
TEST_IP = "198.51.100.24"


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


def _auth_headers(user_id: str, *, ip: str = TEST_IP) -> dict[str, str]:
    return {
        "Authorization": f"Bearer {_issue_token(sub=user_id)}",
        "X-Forwarded-For": ip,
    }


def _build_rate_limiter(*policies: RateLimitPolicy) -> RequestRateLimiter:
    return RequestRateLimiter(
        policies=policies,
        subject_resolver_provider=lambda: deps._request_subject_resolver,
    )


@pytest.fixture(autouse=True)
def _reset_runtime(monkeypatch: pytest.MonkeyPatch) -> None:
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


def test_general_api_rate_limit_blocks_repeated_report_listing(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "_request_rate_limiter",
        _build_rate_limiter(
            RateLimitPolicy(
                name="api_requests",
                request_limit=1,
                window_seconds=60,
                methods=frozenset({"GET"}),
                path_pattern=re.compile(r"^/api/v1/reports$"),
                key_strategy="ip",
            )
        ),
    )
    client = TestClient(create_app())

    first_response = client.get("/api/v1/reports", headers=_auth_headers("user-a"))
    second_response = client.get("/api/v1/reports", headers=_auth_headers("user-a"))

    assert first_response.status_code == 200
    assert second_response.status_code == 429
    assert second_response.json()["policy"] == "api_requests"
    assert second_response.headers["X-RateLimit-Policy"] == "api_requests"
    assert int(second_response.headers["Retry-After"]) >= 1


def test_agreement_creation_rate_limit_blocks_repeated_submissions(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "_request_rate_limiter",
        _build_rate_limiter(
            RateLimitPolicy(
                name="agreement_creation",
                request_limit=1,
                window_seconds=600,
                methods=frozenset({"POST"}),
                path_pattern=re.compile(r"^/api/v1/agreements$"),
                key_strategy="subject_or_ip",
            )
        ),
    )
    client = TestClient(create_app())
    payload = {
        "terms_text": (
            "These terms include arbitration, auto-renewal, and broad unilateral "
            "change rights that should be analyzed carefully."
        )
    }

    first_response = client.post(
        "/api/v1/agreements", json=payload, headers=_auth_headers("user-a")
    )
    second_response = client.post(
        "/api/v1/agreements",
        json=payload,
        headers=_auth_headers("user-a"),
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 429
    assert second_response.json()["policy"] == "agreement_creation"


def test_analysis_generation_limit_is_scoped_by_authenticated_subject(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        deps,
        "_request_rate_limiter",
        _build_rate_limiter(
            RateLimitPolicy(
                name="analysis_generation_burst",
                request_limit=1,
                window_seconds=300,
                methods=frozenset({"POST"}),
                path_pattern=re.compile(r"^/api/v1/reports/analyze$"),
                key_strategy="subject_or_ip",
            )
        ),
    )
    client = TestClient(create_app())
    payload = {
        "terms_text": (
            "These terms include mandatory arbitration, auto-renewal, and a broad "
            "right to change terms without notice."
        )
    }

    first_user_first_response = client.post(
        "/api/v1/reports/analyze",
        json=payload,
        headers=_auth_headers("user-a"),
    )
    first_user_second_response = client.post(
        "/api/v1/reports/analyze",
        json=payload,
        headers=_auth_headers("user-a"),
    )
    second_user_response = client.post(
        "/api/v1/reports/analyze",
        json=payload,
        headers=_auth_headers("user-b"),
    )

    assert first_user_first_response.status_code == 201
    assert first_user_second_response.status_code == 429
    assert first_user_second_response.json()["policy"] == "analysis_generation_burst"
    assert second_user_response.status_code == 201
