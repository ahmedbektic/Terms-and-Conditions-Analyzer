from datetime import datetime, timedelta, timezone

import httpx
import pytest

from app.repositories.in_memory import (
    InMemoryAgreementRepository,
    InMemoryPolicyChangeEventRepository,
    InMemoryPolicySnapshotRepository,
    InMemoryReportRepository,
    InMemoryStorage,
    InMemoryTrackedPolicyRepository,
)
from app.repositories.policy_capture_status import PolicyCaptureStatus
from app.repositories.policy_change_status import PolicyChangeStatus
from app.repositories.policy_tracking_status import PolicyTrackingStatus
from app.repositories.report_capture_kind import ReportContentCaptureKind
from app.services.ai_provider import DeterministicAnalysisProvider
from app.services.analysis_execution import SyncAnalysisExecutionStrategy
from app.services.analysis_service import (
    AnalysisOrchestrationService,
    AnalysisSubmission,
    InvalidSubmissionError,
)
from app.services.request_subject import RequestSubject
from app.services.submission_preparation import SubmissionPreparationService
from app.services.tracked_policy_service import (
    DuplicateTrackedPolicyError,
    InvalidTrackedPolicySourceError,
    TrackedPolicyBaselineReportError,
    TrackedPolicyCheckFailedError,
    TrackedPolicyService,
)
from app.services.web_source import (
    CapturedPolicySnapshotSource,
    CapturedWebSource,
    InspectedWebSource,
    PublicWebSourceInspector,
    UrlFetchPayload,
    WebSourceInspectionError,
    canonicalize_public_source_url,
)


class _StaticUrlFetcher:
    def __init__(self, payload: UrlFetchPayload) -> None:
        self._payload = payload

    def fetch(self, *, url: str) -> UrlFetchPayload:
        _ = url
        return self._payload


class _FailingUrlFetcher:
    def fetch(self, *, url: str) -> UrlFetchPayload:
        raise ValueError(f"failed to fetch {url}")


class _TimeoutUrlFetcher:
    def fetch(self, *, url: str) -> UrlFetchPayload:
        raise httpx.ReadTimeout("timed out", request=httpx.Request("GET", url))


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


class _StubInspector:
    def __init__(
        self,
        inspected_source: InspectedWebSource,
        *,
        captured_text: str = (
            "These terms include arbitration, auto-renewal, privacy, and cancellation clauses."
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
        self.inspect_calls = 0
        self.capture_trackable_calls = 0
        self.capture_policy_snapshot_source_calls = 0
        self.capture_policy_text_calls = 0

    def inspect_url(self, *, source_url: str) -> InspectedWebSource:
        _ = source_url
        self.inspect_calls += 1
        return self._inspected_source

    def capture_trackable_source(self, *, source_url: str) -> CapturedWebSource:
        _ = source_url
        self.capture_trackable_calls += 1
        if self._create_capture_error is not None:
            raise self._create_capture_error
        return CapturedWebSource(
            canonical_url=self._inspected_source.canonical_url,
            display_name=self._inspected_source.display_name,
            source_type=self._inspected_source.source_type,
            checked_at=self._inspected_source.last_checked_at,
            captured_text=self._captured_text,
        )

    def capture_policy_snapshot_source(self, *, canonical_url: str) -> CapturedPolicySnapshotSource:
        _ = canonical_url
        self.capture_policy_snapshot_source_calls += 1
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
            fetch_duration_ms=25,
            extractor_name="stub_inspector",
            extraction_strategy="stub_capture",
        )

    def capture_policy_text(self, *, canonical_url: str) -> str:
        _ = canonical_url
        self.capture_policy_text_calls += 1
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

    def get_report_terms_text(
        self,
        *,
        subject: RequestSubject,
        report_id,
    ) -> str:
        _ = subject
        _ = report_id
        raise AssertionError(
            "get_report_terms_text should not be called when baseline creation fails"
        )


def _build_services(
    *,
    inspector: PublicWebSourceInspector | _StubInspector,
    analysis_service: AnalysisOrchestrationService | _FailingBaselineAnalysisService | None = None,
) -> tuple[TrackedPolicyService, AnalysisOrchestrationService | _FailingBaselineAnalysisService]:
    storage = InMemoryStorage()
    tracked_policy_repository = InMemoryTrackedPolicyRepository(storage)
    policy_snapshot_repository = InMemoryPolicySnapshotRepository(storage)
    policy_change_event_repository = InMemoryPolicyChangeEventRepository(storage)

    effective_analysis_service = analysis_service
    if effective_analysis_service is None:
        agreement_repository = InMemoryAgreementRepository(storage)
        report_repository = InMemoryReportRepository(storage)
        effective_analysis_service = AnalysisOrchestrationService(
            agreement_repository=agreement_repository,
            report_repository=report_repository,
            analysis_execution_strategy=SyncAnalysisExecutionStrategy(
                analysis_provider=DeterministicAnalysisProvider(),
                report_repository=report_repository,
            ),
            submission_preparation_service=SubmissionPreparationService(),
        )

    return (
        TrackedPolicyService(
            tracked_policy_repository=tracked_policy_repository,
            policy_snapshot_repository=policy_snapshot_repository,
            analysis_service=effective_analysis_service,
            policy_change_event_repository=policy_change_event_repository,
            public_web_source_inspector=inspector,
        ),
        effective_analysis_service,
    )


def test_canonicalize_public_source_url_normalizes_host_default_port_and_query_order() -> None:
    canonical_url = canonicalize_public_source_url(
        "HTTPS://Example.com:443/terms?b=2&a=1&a=0#section"
    )

    assert canonical_url == "https://example.com/terms?a=0&a=1&b=2"


def test_public_web_source_inspector_uses_page_title_for_display_name() -> None:
    inspector = PublicWebSourceInspector(
        url_content_fetcher=_StaticUrlFetcher(
            UrlFetchPayload(
                body_text=(
                    "<html><head><title>Example Terms of Service</title></head>"
                    "<body><main>These terms describe arbitration and automatic renewal clauses."
                    "</main></body></html>"
                ),
                content_type="text/html; charset=utf-8",
            )
        )
    )

    inspected_source = inspector.inspect_url(source_url="https://example.com/legal")

    assert inspected_source.display_name == "Example Terms of Service"
    assert inspected_source.source_type == "url"


def test_public_web_source_inspector_falls_back_to_hostname_when_title_missing() -> None:
    inspector = PublicWebSourceInspector(
        url_content_fetcher=_StaticUrlFetcher(
            UrlFetchPayload(
                body_text=(
                    "<html><body>These terms describe cancellation, data sharing, "
                    "and liability limits in readable text.</body></html>"
                ),
                content_type="text/html",
            )
        )
    )

    inspected_source = inspector.inspect_url(source_url="https://Example.com/legal")

    assert inspected_source.display_name == "example.com"


def test_public_web_source_inspector_reports_not_found_pages_with_actionable_message() -> None:
    inspector = PublicWebSourceInspector(url_content_fetcher=_StatusErrorUrlFetcher(404))

    with pytest.raises(WebSourceInspectionError) as error_info:
        inspector.inspect_url(source_url="https://example.com/missing-terms")

    message = str(error_info.value).lower()
    assert "404 not found" in message
    assert "public legal page" in message


def test_public_web_source_inspector_reports_access_blocked_pages_with_actionable_message() -> None:
    inspector = PublicWebSourceInspector(url_content_fetcher=_StatusErrorUrlFetcher(403))

    with pytest.raises(WebSourceInspectionError) as error_info:
        inspector.inspect_url(source_url="https://example.com/private-terms")

    message = str(error_info.value).lower()
    assert "blocking access" in message
    assert "does not require sign-in" in message


def test_public_web_source_inspector_reports_timeouts_with_actionable_message() -> None:
    inspector = PublicWebSourceInspector(url_content_fetcher=_TimeoutUrlFetcher())

    with pytest.raises(WebSourceInspectionError) as error_info:
        inspector.inspect_url(source_url="https://example.com/slow-terms")

    message = str(error_info.value).lower()
    assert "took too long" in message
    assert "try again in a moment" in message


def test_public_web_source_inspector_rejects_pdf_download_urls_with_actionable_message() -> None:
    inspector = PublicWebSourceInspector(
        url_content_fetcher=_StaticUrlFetcher(
            UrlFetchPayload(
                body_text="%PDF-1.7 sample pdf bytes represented as text",
                content_type="application/pdf",
            )
        )
    )

    with pytest.raises(WebSourceInspectionError) as error_info:
        inspector.inspect_url(source_url="https://example.com/terms.pdf")

    message = str(error_info.value).lower()
    assert "pdf download" in message
    assert "public web page" in message


def test_tracked_policy_service_rejects_unreachable_source_with_plain_language_error() -> None:
    service, _ = _build_services(
        inspector=PublicWebSourceInspector(url_content_fetcher=_FailingUrlFetcher())
    )

    with pytest.raises(InvalidTrackedPolicySourceError) as error_info:
        service.create_tracked_policy(
            subject=RequestSubject(subject_type="supabase_user", subject_id="user-a"),
            source_url="https://example.com/terms",
        )

    assert "couldn't reach" in str(error_info.value).lower()


def test_tracked_policy_service_creates_saved_fetched_url_baseline_when_none_exists() -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    service, analysis_service = _build_services(
        inspector=_StubInspector(
            InspectedWebSource(
                canonical_url="https://example.com/terms?a=1&b=2",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        )
    )
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    enrollment = service.create_tracked_policy(
        subject=subject,
        source_url="https://example.com/terms?b=2&a=1",
    )

    assert enrollment.baseline_report_action == "created"
    assert enrollment.tracked_policy.tracking_status == PolicyTrackingStatus.ACTIVE
    assert enrollment.tracked_policy.last_checked_at == checked_at
    assert enrollment.tracked_policy.last_successful_capture_at == checked_at
    assert enrollment.tracked_policy.latest_capture_status == PolicyCaptureStatus.CAPTURED
    assert enrollment.tracked_policy.latest_capture_message is None
    assert enrollment.tracked_policy.latest_change_status == PolicyChangeStatus.NOT_EVALUATED
    assert enrollment.tracked_policy.latest_change_detected_at is None
    assert enrollment.tracked_policy.snapshot_version_count == 1
    assert enrollment.baseline_report.canonical_source_url == "https://example.com/terms?a=1&b=2"
    assert enrollment.baseline_report.content_capture_kind == ReportContentCaptureKind.FETCHED_URL

    reports = analysis_service.list_reports(subject=subject)
    assert len(reports) == 1
    assert reports[0].id == enrollment.baseline_report.id


def test_tracked_policy_service_reuses_existing_fetched_url_baseline_report() -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    service, analysis_service = _build_services(
        inspector=_StubInspector(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        )
    )
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    existing_baseline = analysis_service.create_report_from_verified_url_capture(
        subject=subject,
        canonical_source_url="https://example.com/terms",
        display_name="Example Terms",
        captured_text="These terms include arbitration, privacy, and cancellation clauses.",
    )

    enrollment = service.create_tracked_policy(
        subject=subject,
        source_url="https://example.com/terms",
    )

    assert enrollment.baseline_report_action == "reused"
    assert enrollment.baseline_report.id == existing_baseline.id
    assert enrollment.tracked_policy.tracking_status == PolicyTrackingStatus.ACTIVE
    assert enrollment.tracked_policy.last_successful_capture_at == checked_at
    assert enrollment.tracked_policy.latest_capture_status == PolicyCaptureStatus.CAPTURED
    assert enrollment.tracked_policy.latest_change_status == PolicyChangeStatus.NOT_EVALUATED
    assert enrollment.tracked_policy.snapshot_version_count == 1
    reports = analysis_service.list_reports(subject=subject)
    assert len(reports) == 1


def test_tracked_policy_service_creates_fresh_baseline_when_only_submitted_text_report_exists() -> (
    None
):
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    service, analysis_service = _build_services(
        inspector=_StubInspector(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        )
    )
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    submitted_text_report = analysis_service.submit_and_analyze(
        subject=subject,
        submission=AnalysisSubmission(
            title="Example Terms",
            source_url="https://example.com/terms",
            agreed_at=None,
            terms_text="These terms were pasted by the user and include arbitration clauses.",
        ),
    )
    assert submitted_text_report.content_capture_kind == ReportContentCaptureKind.SUBMITTED_TEXT

    enrollment = service.create_tracked_policy(
        subject=subject,
        source_url="https://example.com/terms",
    )

    reports = analysis_service.list_reports(subject=subject)
    assert len(reports) == 2
    assert enrollment.baseline_report_action == "created"
    assert enrollment.baseline_report.id != submitted_text_report.id
    assert enrollment.tracked_policy.latest_capture_status == PolicyCaptureStatus.CAPTURED
    assert enrollment.tracked_policy.latest_change_status == PolicyChangeStatus.NOT_EVALUATED
    assert enrollment.tracked_policy.snapshot_version_count == 1
    created_baseline_report = next(
        report for report in reports if report.id == enrollment.baseline_report.id
    )
    assert created_baseline_report.content_capture_kind == ReportContentCaptureKind.FETCHED_URL


def test_tracked_policy_service_rejects_duplicate_active_canonical_url_per_owner_before_new_baseline_work() -> (
    None
):
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    inspector = _StubInspector(
        InspectedWebSource(
            canonical_url="https://example.com/terms?a=1&b=2",
            display_name="Example Terms",
            source_type="url",
            last_checked_at=checked_at,
        )
    )
    service, analysis_service = _build_services(inspector=inspector)
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    service.create_tracked_policy(
        subject=subject,
        source_url="https://example.com/terms?b=2&a=1",
    )

    with pytest.raises(DuplicateTrackedPolicyError) as error_info:
        service.create_tracked_policy(
            subject=subject,
            source_url="https://Example.com:443/terms?a=1&b=2#fragment",
        )

    message = str(error_info.value).lower()
    assert "already in your watchlist" in message
    assert "remove the existing entry" in message
    assert inspector.capture_trackable_calls == 1
    assert len(analysis_service.list_reports(subject=subject)) == 1


def test_tracked_policy_service_does_not_persist_watchlist_row_when_baseline_generation_fails() -> (
    None
):
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    service, _ = _build_services(
        inspector=_StubInspector(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        ),
        analysis_service=_FailingBaselineAnalysisService(),
    )
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    with pytest.raises(TrackedPolicyBaselineReportError) as error_info:
        service.create_tracked_policy(
            subject=subject,
            source_url="https://example.com/terms",
        )

    assert "saved baseline report" in str(error_info.value).lower()
    assert service.list_tracked_policies(subject=subject) == []


def test_tracked_policy_service_marks_policy_invalid_source_and_does_not_create_new_saved_reports_when_check_fails() -> (
    None
):
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    service, analysis_service = _build_services(
        inspector=_StubInspector(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            ),
            check_capture_error=WebSourceInspectionError(
                "That policy page returned 404 Not Found. Check that the link is current or use the service's public legal page."
            ),
        )
    )
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    enrollment = service.create_tracked_policy(
        subject=subject,
        source_url="https://example.com/terms",
    )

    with pytest.raises(TrackedPolicyCheckFailedError) as error_info:
        service.check_tracked_policy(
            subject=subject,
            tracked_policy_id=enrollment.tracked_policy.id,
        )

    message = str(error_info.value).lower()
    assert "404 not found" in message
    assert "public legal page" in message

    tracked_policies = service.list_tracked_policies(subject=subject)
    assert len(tracked_policies) == 1
    assert tracked_policies[0].tracking_status == PolicyTrackingStatus.INVALID_SOURCE
    assert tracked_policies[0].latest_capture_status == PolicyCaptureStatus.CAPTURE_FAILED
    assert tracked_policies[0].latest_change_status == PolicyChangeStatus.COMPARISON_INCOMPLETE
    assert "404 not found" in (tracked_policies[0].latest_capture_message or "").lower()
    assert tracked_policies[0].last_successful_capture_at == checked_at
    assert tracked_policies[0].snapshot_version_count == 1
    assert len(analysis_service.list_reports(subject=subject)) == 1


def test_tracked_policy_check_does_not_create_new_saved_reports() -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    service, analysis_service = _build_services(
        inspector=_StubInspector(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        )
    )
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    enrollment = service.create_tracked_policy(
        subject=subject,
        source_url="https://example.com/terms",
    )

    updated = service.check_tracked_policy(
        subject=subject,
        tracked_policy_id=enrollment.tracked_policy.id,
    )

    assert updated.tracking_status == PolicyTrackingStatus.ACTIVE
    assert updated.latest_capture_status == PolicyCaptureStatus.CAPTURED
    assert updated.latest_change_status == PolicyChangeStatus.UNCHANGED
    assert "no meaningful policy changes" in (updated.latest_capture_message or "").lower()
    assert updated.last_successful_capture_at is not None
    assert updated.snapshot_version_count == 1
    assert len(analysis_service.list_reports(subject=subject)) == 1


def test_tracked_policy_check_does_not_increment_version_count_when_baseline_snapshot_matches() -> (
    None
):
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    service, _ = _build_services(
        inspector=_StubInspector(
            InspectedWebSource(
                canonical_url="https://example.com/terms",
                display_name="Example Terms",
                source_type="url",
                last_checked_at=checked_at,
            )
        )
    )
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    enrollment = service.create_tracked_policy(
        subject=subject,
        source_url="https://example.com/terms",
    )

    updated = service.check_tracked_policy(
        subject=subject,
        tracked_policy_id=enrollment.tracked_policy.id,
    )

    assert updated.latest_capture_status == PolicyCaptureStatus.CAPTURED
    assert updated.latest_change_status == PolicyChangeStatus.UNCHANGED
    assert "no meaningful policy changes" in (updated.latest_capture_message or "").lower()
    assert updated.snapshot_version_count == 1


def test_tracked_policy_check_creates_saved_report_for_new_snapshot_version() -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    service, analysis_service = _build_services(
        inspector=_StubInspector(
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
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    enrollment = service.create_tracked_policy(
        subject=subject,
        source_url="https://example.com/terms",
    )

    updated = service.check_tracked_policy(
        subject=subject,
        tracked_policy_id=enrollment.tracked_policy.id,
    )

    reports = analysis_service.list_reports(subject=subject)
    assert updated.latest_change_status == PolicyChangeStatus.UPDATED
    assert updated.latest_change_detected_at is not None
    assert updated.snapshot_version_count == 2
    assert len(reports) == 2
    assert reports[0].tracked_policy_id == enrollment.tracked_policy.id
    assert reports[0].tracked_policy_snapshot_id is not None
    assert reports[0].tracked_policy_version_number == 2
    assert reports[1].tracked_policy_version_number is None
