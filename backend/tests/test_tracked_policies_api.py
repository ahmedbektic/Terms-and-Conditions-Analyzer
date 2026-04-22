from datetime import datetime, timedelta, timezone
from uuid import uuid4

from fastapi.testclient import TestClient
import httpx
import jwt
import pytest

from app.api import deps
from app.api.deps import reset_demo_storage
from app.auth.subject_resolver import AuthSubjectResolver
from app.auth.supabase_jwt import SupabaseJwtVerifier
from app.main import create_app
from app.test_support_policy_text_samples import (
    LEGACY_NOISY_POLICY_TEXT_AFTER,
    LEGACY_NOISY_POLICY_TEXT_BEFORE,
)
from app.repositories.in_memory import (
    InMemoryAgreementRepository,
    InMemoryPolicyChangeEventRepository,
    InMemoryPolicySnapshotRepository,
    InMemoryReportRepository,
    InMemoryStorage,
    InMemoryTrackedPolicyCheckExecutionRepository,
    InMemoryTrackedPolicyRepository,
)
from app.repositories.models import PolicySnapshotCreateInput
from app.repositories.policy_tracking_status import PolicyTrackingStatus
from app.services.ai_provider import DeterministicAnalysisProvider
from app.services.ai_provider import AnalysisProviderInvocationError
from app.services.analysis_execution import SyncAnalysisExecutionStrategy
from app.services.analysis_service import AnalysisOrchestrationService, InvalidSubmissionError
from app.services.request_subject import RequestSubject
from app.services.submission_preparation import SubmissionPreparationService
from app.services.tracked_policy_service import TrackedPolicyService
from app.services.tracked_policy_versions_service import TrackedPolicyVersionsService
from app.services.web_source import (
    CapturedPolicySnapshotSource,
    CapturedWebSource,
    InspectedWebSource,
    PublicWebSourceInspector,
    UrlFetchPayload,
    WebSourceInspectionError,
)

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


class _StatusErrorUrlFetcher:
    def __init__(self, status_code: int) -> None:
        self._status_code = status_code

    def fetch(self, *, url: str) -> UrlFetchPayload:
        request = httpx.Request("GET", url)
        response = httpx.Response(self._status_code, request=request)
        raise httpx.HTTPStatusError(
            f"{self._status_code} error while fetching {url}",
            request=request,
            response=response,
        )


class _InspectorDouble:
    def __init__(
        self,
        inspected_source: InspectedWebSource,
        *,
        captured_text: str = (
            "These terms include arbitration, automatic renewal, and privacy clauses."
        ),
        create_capture_error: WebSourceInspectionError | None = None,
        check_capture_error: WebSourceInspectionError | None = None,
        check_captured_texts: list[str] | None = None,
    ) -> None:
        self._inspected_source = inspected_source
        self._captured_text = captured_text
        self._create_capture_error = create_capture_error
        self._check_capture_error = check_capture_error
        self._check_captured_texts = list(check_captured_texts or [])

    def inspect_url(self, *, source_url: str) -> InspectedWebSource:
        _ = source_url
        return self._inspected_source

    def capture_trackable_source(self, *, source_url: str) -> CapturedWebSource:
        _ = source_url
        if self._create_capture_error is not None:
            raise self._create_capture_error
        return CapturedWebSource(
            canonical_url=self._inspected_source.canonical_url,
            display_name=self._inspected_source.display_name,
            source_type=self._inspected_source.source_type,
            checked_at=self._inspected_source.last_checked_at,
            captured_text=self._captured_text,
            normalization_version=2,
        )

    def capture_policy_snapshot_source(self, *, canonical_url: str) -> CapturedPolicySnapshotSource:
        _ = canonical_url
        if self._check_capture_error is not None:
            raise self._check_capture_error
        captured_text = self._captured_text
        if self._check_captured_texts:
            captured_text = self._check_captured_texts.pop(0)
        checked_at = datetime.now(timezone.utc)
        return CapturedPolicySnapshotSource(
            canonical_url=self._inspected_source.canonical_url,
            display_name=self._inspected_source.display_name,
            source_type=self._inspected_source.source_type,
            checked_at=checked_at,
            raw_text_body=captured_text,
            normalized_text_body=captured_text,
            final_url=self._inspected_source.canonical_url,
            http_status=200,
            redirect_count=0,
            fetch_duration_ms=20,
            extractor_name="inspector_double",
            extraction_strategy="stub_capture",
            normalization_version=2,
        )

    def capture_policy_text(self, *, canonical_url: str) -> str:
        return self.capture_policy_snapshot_source(canonical_url=canonical_url).normalized_text_body


class _FailingBaselineAnalysisService:
    def find_latest_eligible_baseline_report(
        self,
        *,
        subject: RequestSubject,
        canonical_source_url: str,
    ):
        _ = subject
        _ = canonical_source_url
        return None

    def create_report_from_verified_url_capture(
        self,
        *,
        subject: RequestSubject,
        canonical_source_url: str,
        display_name: str | None,
        captured_text: str,
    ):
        _ = subject
        _ = canonical_source_url
        _ = display_name
        _ = captured_text
        raise InvalidSubmissionError(
            "We couldn't generate a saved baseline report for that policy because the analysis input was invalid."
        )

    def get_report_terms_text(self, *, subject: RequestSubject, report_id) -> str:
        _ = subject
        _ = report_id
        raise AssertionError(
            "get_report_terms_text should not be called when baseline creation fails"
        )


class _TimeoutTrackedSnapshotAnalysisService:
    def __init__(self, delegate: AnalysisOrchestrationService) -> None:
        self._delegate = delegate

    def find_latest_eligible_baseline_report(self, **kwargs):
        return self._delegate.find_latest_eligible_baseline_report(**kwargs)

    def create_report_from_verified_url_capture(self, **kwargs):
        if kwargs.get("tracked_policy_id") is not None:
            raise AnalysisProviderInvocationError("Gemini invocation failed (ReadTimeout).")
        return self._delegate.create_report_from_verified_url_capture(**kwargs)

    def get_report_terms_text(self, **kwargs) -> str:
        return self._delegate.get_report_terms_text(**kwargs)

    def list_reports(self, **kwargs):
        return self._delegate.list_reports(**kwargs)


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


def _build_shared_services(
    *,
    url_fetcher=None,
    inspector=None,
    analysis_service=None,
) -> tuple[TrackedPolicyService, AnalysisOrchestrationService | _FailingBaselineAnalysisService]:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)
    tracked_policy_repository = InMemoryTrackedPolicyRepository(storage)
    check_execution_repository = InMemoryTrackedPolicyCheckExecutionRepository(storage)
    policy_snapshot_repository = InMemoryPolicySnapshotRepository(storage)
    policy_change_event_repository = InMemoryPolicyChangeEventRepository(storage)
    effective_analysis_service = analysis_service or AnalysisOrchestrationService(
        agreement_repository=agreement_repository,
        report_repository=report_repository,
        analysis_execution_strategy=SyncAnalysisExecutionStrategy(
            analysis_provider=DeterministicAnalysisProvider(),
            report_repository=report_repository,
        ),
        submission_preparation_service=SubmissionPreparationService(),
    )
    effective_inspector = inspector or PublicWebSourceInspector(url_content_fetcher=url_fetcher)
    tracked_policy_service = TrackedPolicyService(
        tracked_policy_repository=tracked_policy_repository,
        policy_snapshot_repository=policy_snapshot_repository,
        check_execution_repository=check_execution_repository,
        analysis_service=effective_analysis_service,
        policy_change_event_repository=policy_change_event_repository,
        public_web_source_inspector=effective_inspector,
    )
    return tracked_policy_service, effective_analysis_service


def _build_versions_service(
    tracked_policy_service: TrackedPolicyService,
) -> TrackedPolicyVersionsService:
    return TrackedPolicyVersionsService(
        tracked_policy_repository=tracked_policy_service._tracked_policy_repository,  # type: ignore[attr-defined]
        policy_snapshot_repository=tracked_policy_service._policy_snapshot_repository,  # type: ignore[attr-defined]
        policy_change_event_repository=tracked_policy_service._policy_snapshot_service._policy_change_event_repository,  # type: ignore[attr-defined]
    )


@pytest.fixture(autouse=True)
def _jwt_subject_resolver(monkeypatch: pytest.MonkeyPatch) -> None:
    reset_demo_storage()
    verifier = SupabaseJwtVerifier(
        jwt_secret=TEST_SECRET,
        expected_issuer=TEST_ISSUER,
        expected_audience=TEST_AUDIENCE,
        require_signature_verification=True,
    )
    resolver = AuthSubjectResolver(jwt_verifier=verifier)
    monkeypatch.setattr(deps, "_request_subject_resolver", resolver)
    yield
    reset_demo_storage()


@pytest.fixture()
def client() -> TestClient:
    return TestClient(create_app())


def test_tracked_policies_endpoint_requires_bearer_token(client: TestClient) -> None:
    response = client.get("/api/v1/tracked-policies")

    assert response.status_code == 401
    assert response.json()["detail"] == "Missing Bearer token."


def test_authenticated_user_can_create_list_and_delete_tracked_policies_with_saved_baseline_report(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked_policy_service, analysis_service = _build_shared_services(
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
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
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
    assert created_tracked_policy["tracking_status"] == "active"
    assert created_tracked_policy["last_checked_at"] is not None
    assert created_tracked_policy["last_successful_capture_at"] is not None
    assert created_tracked_policy["latest_capture_status"] == "captured"
    assert created_tracked_policy["latest_capture_message"] is None
    assert created_tracked_policy["latest_change_status"] == "not_evaluated"
    assert created_tracked_policy["latest_change_detected_at"] is None
    assert created_tracked_policy["snapshot_version_count"] == 1
    assert created_tracked_policy["baseline_report_action"] == "created"
    assert created_tracked_policy["baseline_report_id"]

    report_list_response = client.get("/api/v1/reports", headers=owner_headers)
    assert report_list_response.status_code == 200
    report_list = report_list_response.json()
    assert len(report_list) == 1
    assert report_list[0]["id"] == created_tracked_policy["baseline_report_id"]

    list_response = client.get("/api/v1/tracked-policies", headers=owner_headers)
    assert list_response.status_code == 200
    listed_tracked_policies = list_response.json()
    assert len(listed_tracked_policies) == 1
    assert listed_tracked_policies[0]["id"] == created_tracked_policy["id"]
    assert "baseline_report_id" not in listed_tracked_policies[0]

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
    tracked_policy_service, analysis_service = _build_shared_services(
        url_fetcher=_StaticUrlFetcher(
            UrlFetchPayload(
                body_text=(
                    "<html><body>These terms cover liability, privacy, and cancellation."
                    "</body></html>"
                ),
                content_type="text/html",
            )
        )
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)

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
    tracked_policy_service, analysis_service = _build_shared_services(
        url_fetcher=_StaticUrlFetcher(
            UrlFetchPayload(
                body_text=(
                    "<html><body>These terms cover liability, privacy, and cancellation."
                    "</body></html>"
                ),
                content_type="text/html",
            )
        )
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
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
    message = second_response.json()["detail"].lower()
    assert "already in your watchlist" in message
    assert "remove the existing entry" in message

    report_list_response = client.get("/api/v1/reports", headers=owner_headers)
    assert len(report_list_response.json()) == 1


def test_tracked_policy_create_reuses_existing_baseline_report_without_duplication(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    tracked_policy_service, analysis_service = _build_shared_services(
        inspector=_InspectorDouble(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        )
    )
    existing_baseline = analysis_service.create_report_from_verified_url_capture(
        subject=RequestSubject(subject_type="supabase_user", subject_id="auth-user-a"),
        canonical_source_url="https://example.com/terms",
        display_name="Example Terms",
        captured_text="These terms include arbitration and privacy clauses.",
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=owner_headers,
    )

    assert create_response.status_code == 201
    assert create_response.json()["baseline_report_action"] == "reused"
    assert create_response.json()["baseline_report_id"] == str(existing_baseline.id)
    assert create_response.json()["tracking_status"] == "active"
    assert create_response.json()["latest_capture_status"] == "captured"
    assert create_response.json()["latest_change_status"] == "not_evaluated"
    assert create_response.json()["snapshot_version_count"] == 1

    report_list_response = client.get("/api/v1/reports", headers=owner_headers)
    assert len(report_list_response.json()) == 1


def test_tracked_policy_create_rejects_unreachable_source_url(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked_policy_service, analysis_service = _build_shared_services(
        url_fetcher=_FailingUrlFetcher()
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)

    response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=_auth_headers("auth-user-a"),
    )

    assert response.status_code == 422
    assert "couldn't reach" in response.json()["detail"].lower()


def test_tracked_policy_create_reports_actionable_message_for_not_found_page(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked_policy_service, analysis_service = _build_shared_services(
        url_fetcher=_StatusErrorUrlFetcher(404)
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)

    response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/missing-terms"},
        headers=_auth_headers("auth-user-a"),
    )

    assert response.status_code == 422
    message = response.json()["detail"].lower()
    assert "404 not found" in message
    assert "public legal page" in message


def test_tracked_policy_create_rejects_private_source_url(client: TestClient) -> None:
    response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "http://localhost/private-terms"},
        headers=_auth_headers("auth-user-a"),
    )

    assert response.status_code == 422
    assert "public hostname" in str(response.json()).lower()


def test_tracked_policy_create_returns_actionable_error_and_no_watchlist_row_when_baseline_generation_fails(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    tracked_policy_service, failing_analysis_service = _build_shared_services(
        inspector=_InspectorDouble(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        ),
        analysis_service=_FailingBaselineAnalysisService(),
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", failing_analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=owner_headers,
    )

    assert create_response.status_code == 422
    assert "saved baseline report" in create_response.json()["detail"].lower()

    list_response = client.get("/api/v1/tracked-policies", headers=owner_headers)
    assert list_response.status_code == 200
    assert list_response.json() == []


def test_tracked_policy_check_returns_actionable_error_and_marks_policy_invalid_source(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    tracked_policy_service, analysis_service = _build_shared_services(
        inspector=_InspectorDouble(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            ),
            check_capture_error=WebSourceInspectionError(
                "That policy page is blocking access. Use a public terms or privacy page that does not require sign-in."
            ),
        )
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=owner_headers,
    )
    tracked_policy_id = create_response.json()["id"]
    baseline_report_id = create_response.json()["baseline_report_id"]

    check_response = client.post(
        f"/api/v1/tracked-policies/{tracked_policy_id}/check",
        headers=owner_headers,
    )

    assert check_response.status_code == 200
    assert check_response.json()["execution"]["status"] == "failed"
    message = check_response.json()["execution"]["failure_message"].lower()
    assert "blocking access" in message
    assert "does not require sign-in" in message

    list_response = client.get("/api/v1/tracked-policies", headers=owner_headers)
    tracked_policies = list_response.json()
    assert len(tracked_policies) == 1
    assert tracked_policies[0]["tracking_status"] == "invalid_source"
    assert tracked_policies[0]["latest_capture_status"] == "capture_failed"
    assert tracked_policies[0]["latest_change_status"] == "comparison_incomplete"
    assert "blocking access" in tracked_policies[0]["latest_capture_message"].lower()
    assert tracked_policies[0]["last_successful_capture_at"] is not None
    assert tracked_policies[0]["snapshot_version_count"] == 1

    report_list_response = client.get("/api/v1/reports", headers=owner_headers)
    report_list = report_list_response.json()
    assert len(report_list) == 1
    assert report_list[0]["id"] == baseline_report_id


def test_tracked_policy_check_returns_no_change_message_without_creating_duplicate_snapshot(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    tracked_policy_service, analysis_service = _build_shared_services(
        inspector=_InspectorDouble(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        )
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=owner_headers,
    )
    tracked_policy_id = create_response.json()["id"]

    check_response = client.post(
        f"/api/v1/tracked-policies/{tracked_policy_id}/check",
        headers=owner_headers,
    )

    assert check_response.status_code == 200
    assert check_response.json()["execution"]["status"] == "succeeded"
    tracked_policy = check_response.json()["tracked_policy"]
    assert tracked_policy["latest_change_status"] == "unchanged"
    assert tracked_policy["snapshot_version_count"] == 1
    assert (
        "no meaningful policy changes" in (tracked_policy["latest_capture_message"] or "").lower()
    )


def test_tracked_policy_check_creates_new_snapshot_when_content_changes(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    tracked_policy_service, analysis_service = _build_shared_services(
        inspector=_InspectorDouble(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            ),
            check_captured_texts=[
                "These updated terms include arbitration, privacy, and mandatory venue clauses."
            ],
        )
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=owner_headers,
    )
    tracked_policy_id = create_response.json()["id"]

    check_response = client.post(
        f"/api/v1/tracked-policies/{tracked_policy_id}/check",
        headers=owner_headers,
    )

    assert check_response.status_code == 200
    assert check_response.json()["execution"]["status"] == "succeeded"
    tracked_policy = check_response.json()["tracked_policy"]
    assert tracked_policy["latest_change_status"] == "updated"
    assert tracked_policy["latest_change_detected_at"] is not None
    assert tracked_policy["snapshot_version_count"] == 2
    assert tracked_policy["latest_capture_message"] is None

    report_list_response = client.get("/api/v1/reports", headers=owner_headers)
    report_list = report_list_response.json()
    assert len(report_list) == 2
    assert report_list[0]["tracked_policy_id"] == tracked_policy_id
    assert report_list[0]["tracked_policy_snapshot_id"] is not None
    assert report_list[0]["tracked_policy_version_number"] == 2


def test_tracked_policy_check_returns_actionable_error_and_does_not_increment_versions_when_report_generation_times_out(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    tracked_policy_service, analysis_service = _build_shared_services(
        inspector=_InspectorDouble(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            ),
            check_captured_texts=[
                "These updated terms include arbitration, privacy, and mandatory venue clauses."
            ],
        )
    )
    timeout_analysis_service = _TimeoutTrackedSnapshotAnalysisService(analysis_service)
    tracked_policy_service = TrackedPolicyService(
        tracked_policy_repository=tracked_policy_service._tracked_policy_repository,  # type: ignore[attr-defined]
        check_execution_repository=tracked_policy_service._check_execution_service._check_execution_repository,  # type: ignore[attr-defined]
        policy_snapshot_repository=tracked_policy_service._policy_snapshot_repository,  # type: ignore[attr-defined]
        analysis_service=timeout_analysis_service,
        policy_change_event_repository=tracked_policy_service._policy_snapshot_service._policy_change_event_repository,  # type: ignore[attr-defined]
        public_web_source_inspector=tracked_policy_service._public_web_source_inspector,  # type: ignore[attr-defined]
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", timeout_analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=owner_headers,
    )
    tracked_policy_id = create_response.json()["id"]

    check_response = client.post(
        f"/api/v1/tracked-policies/{tracked_policy_id}/check",
        headers=owner_headers,
    )

    assert check_response.status_code == 200
    assert check_response.json()["execution"]["status"] == "timed_out"
    assert "timed out" in check_response.json()["execution"]["failure_message"].lower()

    list_response = client.get("/api/v1/tracked-policies", headers=owner_headers)
    tracked_policies = list_response.json()
    assert tracked_policies[0]["latest_change_status"] == "comparison_incomplete"
    assert tracked_policies[0]["latest_capture_status"] == "capture_failed"
    assert tracked_policies[0]["snapshot_version_count"] == 1

    report_list_response = client.get("/api/v1/reports", headers=owner_headers)
    assert len(report_list_response.json()) == 1


def test_tracked_policy_snapshot_history_returns_versions_newest_first(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    tracked_policy_service, analysis_service = _build_shared_services(
        inspector=_InspectorDouble(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            ),
            check_captured_texts=[
                "These updated terms include arbitration, privacy, and mandatory venue clauses."
            ],
        )
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(
        deps, "_tracked_policy_versions_service", _build_versions_service(tracked_policy_service)
    )
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=owner_headers,
    )
    tracked_policy_id = create_response.json()["id"]

    check_response = client.post(
        f"/api/v1/tracked-policies/{tracked_policy_id}/check",
        headers=owner_headers,
    )
    assert check_response.status_code == 200

    history_response = client.get(
        f"/api/v1/tracked-policies/{tracked_policy_id}/snapshots",
        headers=owner_headers,
    )

    assert history_response.status_code == 200
    history = history_response.json()
    assert [snapshot["version_number"] for snapshot in history] == [2, 1]
    assert history[0]["change_status"] == "updated"
    assert history[1]["change_status"] in {None, "not_evaluated"}


def test_tracked_policy_compare_returns_older_newer_metadata_and_diff_blocks(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    tracked_policy_service, analysis_service = _build_shared_services(
        inspector=_InspectorDouble(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            ),
            check_captured_texts=[
                "These updated terms include arbitration, privacy, and mandatory venue clauses."
            ],
        )
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(
        deps, "_tracked_policy_versions_service", _build_versions_service(tracked_policy_service)
    )
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=owner_headers,
    )
    tracked_policy_id = create_response.json()["id"]

    client.post(
        f"/api/v1/tracked-policies/{tracked_policy_id}/check",
        headers=owner_headers,
    )
    history_response = client.get(
        f"/api/v1/tracked-policies/{tracked_policy_id}/snapshots",
        headers=owner_headers,
    )
    history = history_response.json()

    compare_response = client.get(
        (
            f"/api/v1/tracked-policies/{tracked_policy_id}/compare"
            f"?snapshot_a={history[0]['snapshot_id']}&snapshot_b={history[1]['snapshot_id']}"
        ),
        headers=owner_headers,
    )

    assert compare_response.status_code == 200
    payload = compare_response.json()
    assert payload["older_snapshot"]["version_number"] == 1
    assert payload["newer_snapshot"]["version_number"] == 2
    assert payload["tracked_policy"]["id"] == tracked_policy_id
    assert payload["comparison_outcome"] == "meaningful_changes"
    assert payload["normalization_notice"] is None
    assert payload["render_mode"] == "split_or_unified"
    assert {block["change_type"] for block in payload["diff_blocks"]} >= {"added", "removed"}


def test_tracked_policy_compare_returns_no_meaningful_changes_for_legacy_noise_only_differences(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked_policy_service, analysis_service = _build_shared_services()
    tracked_policy = tracked_policy_service._tracked_policy_repository.create(  # type: ignore[attr-defined]
        subject_type="supabase_user",
        subject_id="auth-user-a",
        canonical_url="https://example.com/terms",
        display_name="Example Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=datetime.now(timezone.utc) - timedelta(minutes=5),
        active=True,
    )
    older_snapshot = tracked_policy_service._policy_snapshot_repository.append_for_tracked_policy_if_changed(  # type: ignore[attr-defined]
        tracked_policy_id=tracked_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body=LEGACY_NOISY_POLICY_TEXT_BEFORE,
            normalized_text_body=LEGACY_NOISY_POLICY_TEXT_BEFORE,
            captured_at=datetime(2026, 3, 24, 9, 0, tzinfo=timezone.utc),
            source_url="https://example.com/terms",
            final_url="https://example.com/terms",
        ),
    ).snapshot
    newer_snapshot = tracked_policy_service._policy_snapshot_repository.append_for_tracked_policy_if_changed(  # type: ignore[attr-defined]
        tracked_policy_id=tracked_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body=LEGACY_NOISY_POLICY_TEXT_AFTER,
            normalized_text_body=LEGACY_NOISY_POLICY_TEXT_AFTER,
            captured_at=datetime(2026, 3, 25, 9, 0, tzinfo=timezone.utc),
            source_url="https://example.com/terms",
            final_url="https://example.com/terms",
        ),
    ).snapshot
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(
        deps,
        "_tracked_policy_versions_service",
        _build_versions_service(tracked_policy_service),
    )
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    compare_response = client.get(
        (
            f"/api/v1/tracked-policies/{tracked_policy.id}/compare"
            f"?snapshot_a={newer_snapshot.id}&snapshot_b={older_snapshot.id}"
        ),
        headers=owner_headers,
    )

    assert compare_response.status_code == 200
    payload = compare_response.json()
    assert payload["comparison_outcome"] == "no_meaningful_changes"
    assert payload["diff_blocks"] == []
    assert "normalized before comparison" in (payload["normalization_notice"] or "").lower()


def test_tracked_policy_compare_rejects_duplicate_snapshot_ids(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    tracked_policy_service, analysis_service = _build_shared_services(
        inspector=_InspectorDouble(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        )
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(
        deps, "_tracked_policy_versions_service", _build_versions_service(tracked_policy_service)
    )
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=owner_headers,
    )
    tracked_policy_id = create_response.json()["id"]
    history_response = client.get(
        f"/api/v1/tracked-policies/{tracked_policy_id}/snapshots",
        headers=owner_headers,
    )
    snapshot_id = history_response.json()[0]["snapshot_id"]

    compare_response = client.get(
        (
            f"/api/v1/tracked-policies/{tracked_policy_id}/compare"
            f"?snapshot_a={snapshot_id}&snapshot_b={snapshot_id}"
        ),
        headers=owner_headers,
    )

    assert compare_response.status_code == 422
    assert "choose two different" in compare_response.json()["detail"].lower()


def test_tracked_policy_execution_status_returns_execution_record(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    tracked_policy_service, analysis_service = _build_shared_services(
        inspector=_InspectorDouble(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        )
    )
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
    owner_headers = _auth_headers("auth-user-a")

    create_response = client.post(
        "/api/v1/tracked-policies",
        json={"source_url": "https://example.com/terms"},
        headers=owner_headers,
    )
    tracked_policy_id = create_response.json()["id"]

    check_response = client.post(
        f"/api/v1/tracked-policies/{tracked_policy_id}/check",
        headers=owner_headers,
    )
    execution_id = check_response.json()["execution"]["id"]

    status_response = client.get(
        f"/api/v1/tracked-policies/executions/{execution_id}",
        headers=owner_headers,
    )

    assert status_response.status_code == 200
    assert status_response.json()["id"] == execution_id
    assert status_response.json()["status"] == "succeeded"
    assert status_response.json()["tracked_policy_id"] == tracked_policy_id


def test_tracked_policy_execution_status_returns_404_for_unknown_execution(
    client: TestClient, monkeypatch: pytest.MonkeyPatch
) -> None:
    tracked_policy_service, analysis_service = _build_shared_services()
    monkeypatch.setattr(deps, "_tracked_policy_service", tracked_policy_service)
    monkeypatch.setattr(deps, "_analysis_service", analysis_service)
    owner_headers = _auth_headers("auth-user-a")
    execution_id = uuid4()

    status_response = client.get(
        f"/api/v1/tracked-policies/executions/{execution_id}",
        headers=owner_headers,
    )

    assert status_response.status_code == 404
    assert (
        status_response.json()["detail"]
        == f"Tracked policy check execution {execution_id} was not found."
    )
