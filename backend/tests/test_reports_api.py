from datetime import datetime, timedelta, timezone
from fastapi.testclient import TestClient
import jwt
import pytest

from app.api import deps
from app.api.deps import reset_demo_storage
from app.auth.subject_resolver import AuthSubjectResolver
from app.auth.supabase_jwt import SupabaseJwtVerifier
from app.main import create_app
from app.repositories.in_memory import (
    InMemoryAgreementRepository,
    InMemoryReportRepository,
    InMemoryStorage,
)
from app.services.ai_provider import DeterministicAnalysisProvider
from app.services.analysis_execution import SyncAnalysisExecutionStrategy
from app.services.analysis_service import AnalysisOrchestrationService
from app.services.content_ingestion import ContentIngestionService, UrlFetchPayload
from app.services.submission_preparation import SubmissionPreparationService

TEST_SECRET = "e" * 48
TEST_ISSUER = "https://reports-test.supabase.co/auth/v1"
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


class _StaticUrlFetcher:
    def __init__(self, payload: UrlFetchPayload) -> None:
        self._payload = payload

    def fetch(self, *, url: str) -> UrlFetchPayload:
        _ = url
        return self._payload


def _build_analysis_service_for_test(
    *,
    content_ingestion_service: ContentIngestionService | None = None,
) -> AnalysisOrchestrationService:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)

    return AnalysisOrchestrationService(
        agreement_repository=agreement_repository,
        report_repository=report_repository,
        analysis_execution_strategy=SyncAnalysisExecutionStrategy(
            analysis_provider=DeterministicAnalysisProvider(),
            report_repository=report_repository,
        ),
        submission_preparation_service=SubmissionPreparationService(
            content_ingestion_service=content_ingestion_service or ContentIngestionService()
        ),
    )


def _assert_report_response_contract(report: dict) -> None:
    assert set(report.keys()) == {
        "id",
        "agreement_id",
        "source_type",
        "source_value",
        "raw_input_excerpt",
        "status",
        "summary",
        "trust_score",
        "model_name",
        "flagged_clauses",
        "created_at",
        "completed_at",
    }
    assert report["status"] == "completed"
    assert isinstance(report["summary"], str)
    assert isinstance(report["trust_score"], int)
    assert isinstance(report["flagged_clauses"], list)

    for clause in report["flagged_clauses"]:
        assert set(clause.keys()) == {
            "clause_type",
            "severity",
            "excerpt",
            "explanation",
        }


def _assert_report_list_item_contract(report: dict) -> None:
    assert set(report.keys()) == {
        "id",
        "agreement_id",
        "source_type",
        "source_value",
        "status",
        "trust_score",
        "model_name",
        "created_at",
    }
    assert report["status"] == "completed"


def test_submit_analyze_and_fetch_history(client: TestClient) -> None:
    payload = {
        "title": "Acme Terms",
        "source_url": "https://acme.example/terms",
        "terms_text": (
            "These terms include mandatory arbitration and a class action waiver. "
            "The subscription renews automatically unless canceled. "
            "We may change these terms at any time without notice."
        ),
    }

    create_response = client.post(
        "/api/v1/reports/analyze",
        json=payload,
        headers=_auth_headers("user-a"),
    )
    assert create_response.status_code == 201
    created_report = create_response.json()

    assert created_report["summary"]
    assert created_report["source_type"] == "url"
    assert created_report["source_value"] == payload["source_url"]
    assert created_report["status"] == "completed"
    assert 0 <= created_report["trust_score"] <= 100
    assert len(created_report["flagged_clauses"]) >= 1

    list_response = client.get("/api/v1/reports", headers=_auth_headers("user-a"))
    assert list_response.status_code == 200
    report_list = list_response.json()
    assert len(report_list) == 1
    _assert_report_list_item_contract(report_list[0])
    assert report_list[0]["id"] == created_report["id"]

    get_response = client.get(
        f"/api/v1/reports/{created_report['id']}",
        headers=_auth_headers("user-a"),
    )
    assert get_response.status_code == 200
    fetched_report = get_response.json()
    _assert_report_response_contract(fetched_report)
    assert fetched_report["id"] == created_report["id"]


def test_reports_are_scoped_by_authenticated_owner(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reports/analyze",
        json={"source_url": "https://example.com/terms"},
        headers=_auth_headers("user-a"),
    )
    assert response.status_code == 201

    list_owner_a = client.get("/api/v1/reports", headers=_auth_headers("user-a"))
    list_owner_b = client.get("/api/v1/reports", headers=_auth_headers("user-b"))

    assert list_owner_a.status_code == 200
    assert list_owner_b.status_code == 200
    assert len(list_owner_a.json()) == 1
    assert list_owner_b.json() == []


def test_submit_analyze_requires_bearer_token(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reports/analyze",
        json={"terms_text": "This content is valid and sufficiently long for analysis."},
    )
    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Bearer token."


def test_submit_analyze_rejects_missing_input(client: TestClient) -> None:
    response = client.post(
        "/api/v1/reports/analyze",
        json={},
        headers=_auth_headers("user-a"),
    )
    assert response.status_code == 422


def test_get_report_returns_404_when_report_not_found(client: TestClient) -> None:
    response = client.get(
        "/api/v1/reports/11111111-1111-1111-1111-111111111111",
        headers=_auth_headers("user-a"),
    )
    assert response.status_code == 404


def test_analyze_payload_contract_is_shared_for_web_and_extension(client: TestClient) -> None:
    web_response = client.post(
        "/api/v1/reports/analyze",
        json={
            "title": "Web Terms",
            "terms_text": (
                "These terms include arbitration and class action waiver language "
                "for service disputes."
            ),
        },
        headers=_auth_headers("user-a"),
    )
    extension_response = client.post(
        "/api/v1/reports/analyze",
        json={
            "title": "Extension Terms",
            "source_url": "https://service.example/terms",
            "terms_text": (
                "These terms include arbitration and automatic renewal clauses "
                "captured from the extension content script."
            ),
        },
        headers=_auth_headers("user-a"),
    )

    assert web_response.status_code == 201
    assert extension_response.status_code == 201

    web_report = web_response.json()
    extension_report = extension_response.json()
    _assert_report_response_contract(web_report)
    _assert_report_response_contract(extension_report)
    assert set(web_report.keys()) == set(extension_report.keys())
    assert web_report["source_type"] == "text"
    assert extension_report["source_type"] == "url"


def test_submit_analyze_url_only_uses_ingestion_fetch_path_when_available(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    reset_demo_storage()
    test_service = _build_analysis_service_for_test(
        content_ingestion_service=ContentIngestionService(
            url_content_fetcher=_StaticUrlFetcher(
                UrlFetchPayload(
                    body_text=(
                        "<html><body><h1>Terms</h1>"
                        "<p>These terms include arbitration and automatic renewal clauses."
                        "</p></body></html>"
                    ),
                    content_type="text/html",
                )
            )
        )
    )
    monkeypatch.setattr(deps, "_analysis_service", test_service)

    response = client.post(
        "/api/v1/reports/analyze",
        json={"source_url": "https://service.example/terms"},
        headers=_auth_headers("user-a"),
    )

    assert response.status_code == 201
    report = response.json()
    _assert_report_response_contract(report)
    assert report["source_type"] == "url"
    assert "could not be fetched" not in report["raw_input_excerpt"].lower()
