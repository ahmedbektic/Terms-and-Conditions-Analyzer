from datetime import datetime, timedelta, timezone

from fastapi.testclient import TestClient
import jwt
import pytest

from app.api import deps
from app.auth.subject_resolver import AuthSubjectResolver
from app.auth.supabase_jwt import SupabaseJwtVerifier
from app.main import create_app
from app.repositories.in_memory import InMemoryStorage, InMemoryTrackedPolicyRepository
from app.services.tracked_policy_service import TrackedPolicyService
from app.services.web_source import PublicWebSourceInspector, UrlFetchPayload

TEST_SECRET = "b" * 48
TEST_ISSUER = "https://tracked-policy-test.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"


class _StaticUrlFetcher:
    def __init__(self, payload: UrlFetchPayload) -> None:
        self._payload = payload

    def fetch(self, *, url: str) -> UrlFetchPayload:
        _ = url
        return self._payload


class _FailingUrlFetcher:
    def fetch(self, *, url: str) -> UrlFetchPayload:
        raise ValueError(f"failed to fetch {url}")


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


def _build_tracked_policy_service(*, url_fetcher) -> TrackedPolicyService:
    storage = InMemoryStorage()
    repository = InMemoryTrackedPolicyRepository(storage)
    return TrackedPolicyService(
        tracked_policy_repository=repository,
        public_web_source_inspector=PublicWebSourceInspector(url_content_fetcher=url_fetcher),
    )


@pytest.fixture(autouse=True)
def _jwt_subject_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    verifier = SupabaseJwtVerifier(
        jwt_secret=TEST_SECRET,
        expected_issuer=TEST_ISSUER,
        expected_audience=TEST_AUDIENCE,
        require_signature_verification=True,
    )
    resolver = AuthSubjectResolver(jwt_verifier=verifier)
    monkeypatch.setattr(deps, "_request_subject_resolver", resolver)


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_tracked_policies_endpoint_requires_bearer_token(client: TestClient) -> None:
    response = client.get("/api/v1/tracked-policies")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Bearer token."


def test_authenticated_user_can_create_list_and_delete_tracked_policies(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        deps,
        "_tracked_policy_service",
        _build_tracked_policy_service(
            url_fetcher=_StaticUrlFetcher(
                UrlFetchPayload(
                    body_text=(
                        "<html><head><title>Example Terms</title></head>"
                        "<body>These terms include arbitration and automatic renewal clauses."
                        "</body></html>"
                    ),
                    content_type="text/html",
                )
            )
        ),
    )
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://Example.com:443/terms?b=2&a=1#frag"},
        headers=owner_headers,
    )
    assert create_response.status_code == 201
    created_tracked_policy = create_response.json()
    assert created_tracked_policy["canonical_url"] == "https://example.com/terms?a=1&b=2"
    assert created_tracked_policy["display_name"] == "Example Terms"
    assert created_tracked_policy["tracking_status"] == "pending_first_snapshot"
    assert created_tracked_policy["last_checked_at"] is not None

    list_response = client.get("/api/v1/tracked-policies", headers=owner_headers)
    assert list_response.status_code == 200
    assert list_response.json() == [created_tracked_policy]

    delete_response = client.delete(
        f"/api/v1/tracked-policies/{created_tracked_policy['id']}",
        headers=owner_headers,
    )
    assert delete_response.status_code == 204

    list_after_delete = client.get("/api/v1/tracked-policies", headers=owner_headers)
    assert list_after_delete.status_code == 200
    assert list_after_delete.json() == []


def test_tracked_policies_are_filtered_by_authenticated_owner(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        deps,
        "_tracked_policy_service",
        _build_tracked_policy_service(
            url_fetcher=_StaticUrlFetcher(
                UrlFetchPayload(
                    body_text=(
                        "<html><body>These terms cover liability, privacy, and cancellation."
                        "</body></html>"
                    ),
                    content_type="text/html",
                )
            )
        ),
    )

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://owner-a.example/terms"},
        headers=_auth_headers("auth-user-a"),
    )
    assert create_response.status_code == 201
    tracked_policy_id = create_response.json()["id"]

    list_owner_a = client.get("/api/v1/tracked-policies", headers=_auth_headers("auth-user-a"))
    list_owner_b = client.get("/api/v1/tracked-policies", headers=_auth_headers("auth-user-b"))
    delete_owner_b = client.delete(
        f"/api/v1/tracked-policies/{tracked_policy_id}",
        headers=_auth_headers("auth-user-b"),
    )

    assert len(list_owner_a.json()) == 1
    assert list_owner_b.json() == []
    assert delete_owner_b.status_code == 404


def test_tracked_policy_create_returns_conflict_for_active_duplicate(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        deps,
        "_tracked_policy_service",
        _build_tracked_policy_service(
            url_fetcher=_StaticUrlFetcher(
                UrlFetchPayload(
                    body_text=(
                        "<html><body>These terms cover liability, privacy, and cancellation."
                        "</body></html>"
                    ),
                    content_type="text/html",
                )
            )
        ),
    )
    owner_headers = _auth_headers("auth-user-a")

    first_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms?b=2&a=1"},
        headers=owner_headers,
    )
    second_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://Example.com:443/terms?a=1&b=2#fragment"},
        headers=owner_headers,
    )

    assert first_response.status_code == 201
    assert second_response.status_code == 409
    assert "already in your watchlist" in second_response.json()["detail"].lower()


def test_tracked_policy_create_rejects_unreachable_source_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setattr(
        deps,
        "_tracked_policy_service",
        _build_tracked_policy_service(url_fetcher=_FailingUrlFetcher()),
    )

    response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=_auth_headers("auth-user-a"),
    )

    assert response.status_code == 422
    assert "couldn't reach" in response.json()["detail"].lower()


def test_tracked_policy_create_rejects_private_source_url(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "http://localhost/private-terms"},
        headers=_auth_headers("auth-user-a"),
    )

    assert response.status_code == 422
    assert "public hostname" in str(response.json()).lower()
