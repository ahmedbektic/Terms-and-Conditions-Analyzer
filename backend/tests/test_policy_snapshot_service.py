from datetime import datetime, timezone

import httpx
import pytest

from app.test_support_policy_text_samples import (
    LEGACY_NOISY_POLICY_TEXT_AFTER,
    LEGACY_NOISY_POLICY_TEXT_BEFORE,
)
from app.repositories.in_memory import (
    InMemoryPolicyChangeEventRepository,
    InMemoryPolicySnapshotRepository,
    InMemoryStorage,
    InMemoryTrackedPolicyRepository,
)
from app.repositories.models import PolicySnapshotCreateInput
from app.repositories.policy_capture_status import PolicyCaptureStatus
from app.repositories.policy_change_status import PolicyChangeStatus
from app.repositories.policy_tracking_status import PolicyTrackingStatus
from app.services.ai_provider import AnalysisProviderInvocationError
from app.services.policy_snapshot_service import (
    PolicySnapshotCheckFailedError,
    PolicySnapshotService,
)
from app.services.policy_change_detection_service import PolicyChangeDetectionService
from app.services.request_subject import RequestSubject
from app.services.web_source import PublicWebSourceInspector, UrlFetchPayload


class _StaticUrlFetcher:
    def __init__(self, payload: UrlFetchPayload) -> None:
        self._payload = payload

    def fetch(self, *, url: str) -> UrlFetchPayload:
        _ = url
        return self._payload


class _SequenceUrlFetcher:
    def __init__(self, payloads: list[UrlFetchPayload]) -> None:
        self._payloads = list(payloads)

    def fetch(self, *, url: str) -> UrlFetchPayload:
        _ = url
        if not self._payloads:
            raise AssertionError("No more URL fetch payloads were configured.")
        return self._payloads.pop(0)


class _TimeoutUrlFetcher:
    def fetch(self, *, url: str) -> UrlFetchPayload:
        raise httpx.ReadTimeout("timed out", request=httpx.Request("GET", url))


class _TimeoutAnalysisService:
    def create_report_from_verified_url_capture(self, **kwargs):
        _ = kwargs
        raise AnalysisProviderInvocationError("Gemini invocation failed (ReadTimeout).")


def _build_service(
    *,
    inspector: PublicWebSourceInspector,
    analysis_service=None,
) -> tuple[
    PolicySnapshotService,
    InMemoryTrackedPolicyRepository,
    InMemoryPolicySnapshotRepository,
    InMemoryPolicyChangeEventRepository,
]:
    storage = InMemoryStorage()
    tracked_policy_repository = InMemoryTrackedPolicyRepository(storage)
    policy_snapshot_repository = InMemoryPolicySnapshotRepository(storage)
    policy_change_event_repository = InMemoryPolicyChangeEventRepository(storage)
    return (
        PolicySnapshotService(
            tracked_policy_repository=tracked_policy_repository,
            policy_snapshot_repository=policy_snapshot_repository,
            policy_change_event_repository=policy_change_event_repository,
            analysis_service=analysis_service,
            policy_change_detection_service=PolicyChangeDetectionService(),
            public_web_source_inspector=inspector,
        ),
        tracked_policy_repository,
        policy_snapshot_repository,
        policy_change_event_repository,
    )


def _subject() -> RequestSubject:
    return RequestSubject(subject_type="supabase_user", subject_id="user-a")


def _create_tracked_policy(
    repository: InMemoryTrackedPolicyRepository,
    *,
    tracking_status: PolicyTrackingStatus = PolicyTrackingStatus.ACTIVE,
) -> tuple[RequestSubject, object]:
    subject = _subject()
    tracked_policy = repository.create(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        canonical_url="https://example.com/terms",
        display_name="Example Terms",
        source_type="url",
        tracking_status=tracking_status,
        last_checked_at=None,
    )
    return subject, tracked_policy


def test_policy_snapshot_service_creates_first_snapshot_for_legacy_policy_without_history() -> None:
    service, tracked_policy_repository, snapshot_repository, _ = _build_service(
        inspector=PublicWebSourceInspector(
            url_content_fetcher=_StaticUrlFetcher(
                UrlFetchPayload(
                    body_text=(
                        "<html><head><title>Example Terms</title></head><body>"
                        "<main>These terms include arbitration, privacy disclosures, "
                        "and cancellation rights.</main></body></html>"
                    ),
                    content_type="text/html",
                    final_url="https://example.com/legal/terms",
                    status_code=200,
                    redirect_count=1,
                    fetch_duration_ms=145,
                )
            )
        )
    )
    subject, tracked_policy = _create_tracked_policy(
        tracked_policy_repository,
        tracking_status=PolicyTrackingStatus.PENDING_FIRST_SNAPSHOT,
    )

    result = service.check_tracked_policy(subject=subject, tracked_policy_id=tracked_policy.id)

    assert result.snapshot_created is True
    assert result.tracked_policy.tracking_status == PolicyTrackingStatus.ACTIVE
    assert result.tracked_policy.latest_capture_status == PolicyCaptureStatus.CAPTURED
    assert result.tracked_policy.latest_capture_message is None
    assert result.tracked_policy.latest_change_status == PolicyChangeStatus.NOT_EVALUATED
    assert result.tracked_policy.latest_change_detected_at is None
    assert result.tracked_policy.snapshot_version_count == 1
    latest_snapshot = snapshot_repository.get_latest_for_tracked_policy(
        tracked_policy_id=tracked_policy.id
    )
    assert latest_snapshot is not None
    assert latest_snapshot.final_url == "https://example.com/legal/terms"
    assert latest_snapshot.http_status == 200
    assert latest_snapshot.redirect_count == 1
    assert latest_snapshot.fetch_duration_ms == 145
    assert latest_snapshot.extractor_name == "simple_fetched_content_extractor"
    assert latest_snapshot.extraction_strategy == "url_fetch_html_dom_canonicalized"
    assert latest_snapshot.normalization_version == 2


def test_policy_snapshot_service_keeps_version_count_stable_when_content_is_unchanged() -> None:
    service, tracked_policy_repository, snapshot_repository, change_event_repository = (
        _build_service(
            inspector=PublicWebSourceInspector(
                url_content_fetcher=_StaticUrlFetcher(
                    UrlFetchPayload(
                        body_text=(
                            "<html><body><main>These terms include arbitration and cancellation "
                            "rights.</main></body></html>"
                        ),
                        content_type="text/html",
                        final_url="https://example.com/terms",
                        status_code=200,
                        redirect_count=0,
                        fetch_duration_ms=80,
                    )
                )
            )
        )
    )
    subject, tracked_policy = _create_tracked_policy(tracked_policy_repository)
    first_result = service.check_tracked_policy(
        subject=subject, tracked_policy_id=tracked_policy.id
    )

    second_result = service.check_tracked_policy(
        subject=subject,
        tracked_policy_id=tracked_policy.id,
    )

    assert first_result.snapshot_created is True
    assert second_result.snapshot_created is False
    assert second_result.tracked_policy.snapshot_version_count == 1
    assert second_result.tracked_policy.latest_change_status == PolicyChangeStatus.UNCHANGED
    assert (
        "no meaningful policy changes"
        in (second_result.tracked_policy.latest_capture_message or "").lower()
    )
    latest_change_event = change_event_repository.get_latest_for_tracked_policy(
        tracked_policy_id=tracked_policy.id
    )
    assert latest_change_event is not None
    assert latest_change_event.change_status == PolicyChangeStatus.UNCHANGED
    assert latest_change_event.new_snapshot_id is None
    assert (
        len(snapshot_repository.list_for_tracked_policy(tracked_policy_id=tracked_policy.id)) == 1
    )


def test_policy_snapshot_service_creates_new_snapshot_when_content_changes() -> None:
    service, tracked_policy_repository, snapshot_repository, change_event_repository = (
        _build_service(
            inspector=PublicWebSourceInspector(
                url_content_fetcher=_SequenceUrlFetcher(
                    [
                        UrlFetchPayload(
                            body_text=(
                                "<html><body>These terms include arbitration and cancellation "
                                "rights.</body></html>"
                            ),
                            content_type="text/html",
                            final_url="https://example.com/terms",
                            status_code=200,
                            redirect_count=0,
                            fetch_duration_ms=70,
                        ),
                        UrlFetchPayload(
                            body_text=(
                                "<html><body>These updated terms include arbitration, "
                                "cancellation rights, and mandatory venue clauses.</body></html>"
                            ),
                            content_type="text/html",
                            final_url="https://example.com/terms",
                            status_code=200,
                            redirect_count=0,
                            fetch_duration_ms=74,
                        ),
                    ]
                )
            )
        )
    )
    subject, tracked_policy = _create_tracked_policy(tracked_policy_repository)
    first_result = service.check_tracked_policy(
        subject=subject, tracked_policy_id=tracked_policy.id
    )

    second_result = service.check_tracked_policy(
        subject=subject,
        tracked_policy_id=tracked_policy.id,
    )

    assert first_result.snapshot_created is True
    assert second_result.snapshot_created is True
    assert second_result.tracked_policy.snapshot_version_count == 2
    assert second_result.tracked_policy.latest_capture_message is None
    assert second_result.tracked_policy.latest_change_status == PolicyChangeStatus.UPDATED
    assert second_result.tracked_policy.latest_change_detected_at is not None
    latest_snapshot = snapshot_repository.get_latest_for_tracked_policy(
        tracked_policy_id=tracked_policy.id
    )
    assert latest_snapshot is not None
    assert "mandatory venue clauses" in latest_snapshot.normalized_text_body.lower()
    latest_change_event = change_event_repository.get_latest_for_tracked_policy(
        tracked_policy_id=tracked_policy.id
    )
    assert latest_change_event is not None
    assert latest_change_event.change_status == PolicyChangeStatus.UPDATED
    assert latest_change_event.new_snapshot_id == latest_snapshot.id


def test_policy_snapshot_service_keeps_active_policy_on_transient_fetch_failure() -> None:
    service, tracked_policy_repository, snapshot_repository, change_event_repository = (
        _build_service(inspector=PublicWebSourceInspector(url_content_fetcher=_TimeoutUrlFetcher()))
    )
    subject, tracked_policy = _create_tracked_policy(tracked_policy_repository)
    snapshot_repository.append_for_tracked_policy_if_changed(
        tracked_policy_id=tracked_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body="These terms include arbitration and cancellation rights.",
            normalized_text_body="These terms include arbitration and cancellation rights.",
            captured_at=datetime.now(timezone.utc),
            source_url="https://example.com/terms",
            final_url="https://example.com/terms",
            http_status=200,
            redirect_count=0,
            fetch_duration_ms=70,
            extractor_name="seed",
            extraction_strategy="seed",
        ),
    )

    with pytest.raises(PolicySnapshotCheckFailedError) as error_info:
        service.check_tracked_policy(subject=subject, tracked_policy_id=tracked_policy.id)

    assert "took too long" in str(error_info.value).lower()
    refreshed = tracked_policy_repository.get_active_for_subject(
        tracked_policy_id=tracked_policy.id,
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
    )
    assert refreshed is not None
    assert refreshed.tracking_status == PolicyTrackingStatus.ACTIVE
    assert refreshed.latest_capture_status == PolicyCaptureStatus.CAPTURE_FAILED
    assert refreshed.latest_change_status == PolicyChangeStatus.COMPARISON_INCOMPLETE
    assert "try again in a moment" in (refreshed.latest_capture_message or "").lower()
    assert refreshed.snapshot_version_count == 1
    latest_change_event = change_event_repository.get_latest_for_tracked_policy(
        tracked_policy_id=tracked_policy.id
    )
    assert latest_change_event is not None
    assert latest_change_event.change_status == PolicyChangeStatus.COMPARISON_INCOMPLETE


def test_policy_snapshot_service_marks_policy_invalid_source_for_malformed_page() -> None:
    service, tracked_policy_repository, snapshot_repository, change_event_repository = (
        _build_service(
            inspector=PublicWebSourceInspector(
                url_content_fetcher=_StaticUrlFetcher(
                    UrlFetchPayload(
                        body_text="<html><body></body></html>",
                        content_type="text/html",
                        final_url="https://example.com/terms",
                        status_code=200,
                        redirect_count=0,
                        fetch_duration_ms=60,
                    )
                )
            )
        )
    )
    subject, tracked_policy = _create_tracked_policy(tracked_policy_repository)

    with pytest.raises(PolicySnapshotCheckFailedError) as error_info:
        service.check_tracked_policy(subject=subject, tracked_policy_id=tracked_policy.id)

    assert "not contain enough readable policy text" in str(error_info.value).lower()
    refreshed = tracked_policy_repository.get_active_for_subject(
        tracked_policy_id=tracked_policy.id,
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
    )
    assert refreshed is not None
    assert refreshed.tracking_status == PolicyTrackingStatus.INVALID_SOURCE
    assert refreshed.latest_capture_status == PolicyCaptureStatus.CAPTURE_FAILED
    assert refreshed.latest_change_status == PolicyChangeStatus.COMPARISON_INCOMPLETE
    assert refreshed.snapshot_version_count == 0
    assert snapshot_repository.list_for_tracked_policy(tracked_policy_id=tracked_policy.id) == []
    latest_change_event = change_event_repository.get_latest_for_tracked_policy(
        tracked_policy_id=tracked_policy.id
    )
    assert latest_change_event is not None
    assert latest_change_event.change_status == PolicyChangeStatus.COMPARISON_INCOMPLETE


def test_policy_snapshot_service_retry_safe_deduplication_reuses_existing_snapshot() -> None:
    service, tracked_policy_repository, snapshot_repository, _ = _build_service(
        inspector=PublicWebSourceInspector(
            url_content_fetcher=_SequenceUrlFetcher(
                [
                    UrlFetchPayload(
                        body_text=(
                            "<html><body>These terms include arbitration and cancellation "
                            "rights.</body></html>"
                        ),
                        content_type="text/html",
                        final_url="https://example.com/terms",
                        status_code=200,
                        redirect_count=0,
                        fetch_duration_ms=70,
                    ),
                    UrlFetchPayload(
                        body_text=(
                            "<html><body>These terms include arbitration and cancellation "
                            "rights.</body></html>"
                        ),
                        content_type="text/html",
                        final_url="https://example.com/terms",
                        status_code=200,
                        redirect_count=0,
                        fetch_duration_ms=71,
                    ),
                ]
            )
        )
    )
    subject, tracked_policy = _create_tracked_policy(tracked_policy_repository)

    first_result = service.check_tracked_policy(
        subject=subject, tracked_policy_id=tracked_policy.id
    )
    second_result = service.check_tracked_policy(
        subject=subject,
        tracked_policy_id=tracked_policy.id,
    )

    assert first_result.snapshot_created is True
    assert second_result.snapshot_created is False
    assert second_result.tracked_policy.snapshot_version_count == 1
    assert second_result.tracked_policy.latest_change_status == PolicyChangeStatus.UNCHANGED
    assert (
        len(snapshot_repository.list_for_tracked_policy(tracked_policy_id=tracked_policy.id)) == 1
    )


def test_policy_snapshot_service_suppresses_trivial_punctuation_only_changes() -> None:
    (
        service,
        tracked_policy_repository,
        snapshot_repository,
        change_event_repository,
    ) = _build_service(
        inspector=PublicWebSourceInspector(
            url_content_fetcher=_SequenceUrlFetcher(
                [
                    UrlFetchPayload(
                        body_text="<html><body>These terms include arbitration and cancellation rights.</body></html>",
                        content_type="text/html",
                        final_url="https://example.com/terms",
                        status_code=200,
                        redirect_count=0,
                        fetch_duration_ms=70,
                    ),
                    UrlFetchPayload(
                        body_text="<html><body>These terms include arbitration, and cancellation rights!</body></html>",
                        content_type="text/html",
                        final_url="https://example.com/terms",
                        status_code=200,
                        redirect_count=0,
                        fetch_duration_ms=71,
                    ),
                ]
            )
        )
    )
    subject, tracked_policy = _create_tracked_policy(tracked_policy_repository)

    first_result = service.check_tracked_policy(
        subject=subject, tracked_policy_id=tracked_policy.id
    )
    second_result = service.check_tracked_policy(
        subject=subject,
        tracked_policy_id=tracked_policy.id,
    )

    assert first_result.snapshot_created is True
    assert second_result.snapshot_created is False
    assert second_result.tracked_policy.latest_change_status == PolicyChangeStatus.UNCHANGED
    assert second_result.tracked_policy.snapshot_version_count == 1
    latest_change_event = change_event_repository.get_latest_for_tracked_policy(
        tracked_policy_id=tracked_policy.id
    )
    assert latest_change_event is not None
    assert latest_change_event.detection_method == "trivial_formatting_suppressed"
    assert (
        len(snapshot_repository.list_for_tracked_policy(tracked_policy_id=tracked_policy.id)) == 1
    )


def test_policy_snapshot_service_keeps_version_count_stable_for_legacy_scrape_noise_only_changes() -> (
    None
):
    (
        service,
        tracked_policy_repository,
        snapshot_repository,
        change_event_repository,
    ) = _build_service(
        inspector=PublicWebSourceInspector(
            url_content_fetcher=_SequenceUrlFetcher(
                [
                    UrlFetchPayload(
                        body_text=LEGACY_NOISY_POLICY_TEXT_BEFORE,
                        content_type="text/plain",
                        final_url="https://example.com/terms",
                        status_code=200,
                        redirect_count=0,
                        fetch_duration_ms=70,
                    ),
                    UrlFetchPayload(
                        body_text=LEGACY_NOISY_POLICY_TEXT_AFTER,
                        content_type="text/plain",
                        final_url="https://example.com/terms",
                        status_code=200,
                        redirect_count=0,
                        fetch_duration_ms=71,
                    ),
                ]
            )
        )
    )
    subject, tracked_policy = _create_tracked_policy(tracked_policy_repository)

    first_result = service.check_tracked_policy(
        subject=subject, tracked_policy_id=tracked_policy.id
    )
    second_result = service.check_tracked_policy(
        subject=subject,
        tracked_policy_id=tracked_policy.id,
    )

    assert first_result.snapshot_created is True
    assert second_result.snapshot_created is False
    assert second_result.tracked_policy.latest_change_status == PolicyChangeStatus.UNCHANGED
    assert second_result.tracked_policy.snapshot_version_count == 1
    latest_change_event = change_event_repository.get_latest_for_tracked_policy(
        tracked_policy_id=tracked_policy.id
    )
    assert latest_change_event is not None
    assert latest_change_event.change_status == PolicyChangeStatus.UNCHANGED
    assert (
        len(snapshot_repository.list_for_tracked_policy(tracked_policy_id=tracked_policy.id)) == 1
    )


def test_policy_snapshot_service_rolls_back_new_snapshot_when_report_creation_times_out() -> None:
    initial_inspector = PublicWebSourceInspector(
        url_content_fetcher=_StaticUrlFetcher(
            UrlFetchPayload(
                body_text="<html><body>These terms include arbitration and cancellation rights.</body></html>",
                content_type="text/html",
                final_url="https://example.com/terms",
                status_code=200,
                redirect_count=0,
                fetch_duration_ms=70,
            )
        )
    )
    (
        initial_service,
        tracked_policy_repository,
        snapshot_repository,
        change_event_repository,
    ) = _build_service(inspector=initial_inspector)
    subject, tracked_policy = _create_tracked_policy(tracked_policy_repository)
    first_result = initial_service.check_tracked_policy(
        subject=subject, tracked_policy_id=tracked_policy.id
    )

    timeout_service = PolicySnapshotService(
        tracked_policy_repository=tracked_policy_repository,
        policy_snapshot_repository=snapshot_repository,
        policy_change_event_repository=change_event_repository,
        analysis_service=_TimeoutAnalysisService(),
        policy_change_detection_service=PolicyChangeDetectionService(),
        public_web_source_inspector=PublicWebSourceInspector(
            url_content_fetcher=_StaticUrlFetcher(
                UrlFetchPayload(
                    body_text=(
                        "<html><body>These updated terms include arbitration, cancellation rights, "
                        "and mandatory venue clauses.</body></html>"
                    ),
                    content_type="text/html",
                    final_url="https://example.com/terms",
                    status_code=200,
                    redirect_count=0,
                    fetch_duration_ms=71,
                )
            )
        ),
    )

    with pytest.raises(PolicySnapshotCheckFailedError) as error_info:
        timeout_service.check_tracked_policy(
            subject=subject,
            tracked_policy_id=tracked_policy.id,
        )

    assert first_result.snapshot_created is True
    assert "timed out" in str(error_info.value).lower()
    refreshed = tracked_policy_repository.get_active_for_subject(
        tracked_policy_id=tracked_policy.id,
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
    )
    assert refreshed is not None
    assert refreshed.latest_capture_status == PolicyCaptureStatus.CAPTURE_FAILED
    assert refreshed.latest_change_status == PolicyChangeStatus.COMPARISON_INCOMPLETE
    assert refreshed.snapshot_version_count == 1
    assert (
        len(snapshot_repository.list_for_tracked_policy(tracked_policy_id=tracked_policy.id)) == 1
    )
    latest_change_event = change_event_repository.get_latest_for_tracked_policy(
        tracked_policy_id=tracked_policy.id
    )
    assert latest_change_event is not None
    assert latest_change_event.change_status == PolicyChangeStatus.COMPARISON_INCOMPLETE
