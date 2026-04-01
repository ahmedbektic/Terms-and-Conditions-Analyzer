from datetime import datetime, timedelta, timezone

import pytest

from app.repositories.in_memory import InMemoryStorage, InMemoryTrackedPolicyRepository
from app.repositories.policy_tracking_status import PolicyTrackingStatus
from app.services.request_subject import RequestSubject
from app.services.tracked_policy_service import (
    DuplicateTrackedPolicyError,
    InvalidTrackedPolicySourceError,
    TrackedPolicyService,
)
from app.services.web_source import (
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


class _StubInspector:
    def __init__(self, inspected_source: InspectedWebSource) -> None:
        self._inspected_source = inspected_source
        self.calls = 0

    def inspect_url(self, *, source_url: str) -> InspectedWebSource:
        _ = source_url
        self.calls += 1
        return self._inspected_source


def _build_service(*, inspector: PublicWebSourceInspector | _StubInspector) -> TrackedPolicyService:
    storage = InMemoryStorage()
    repository = InMemoryTrackedPolicyRepository(storage)
    return TrackedPolicyService(
        tracked_policy_repository=repository,
        public_web_source_inspector=inspector,
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


def test_tracked_policy_service_rejects_unreachable_source_with_plain_language_error() -> None:
    service = _build_service(
        inspector=PublicWebSourceInspector(url_content_fetcher=_FailingUrlFetcher())
    )

    with pytest.raises(InvalidTrackedPolicySourceError) as error_info:
        service.create_tracked_policy(
            subject=RequestSubject(subject_type="supabase_user", subject_id="user-a"),
            source_url="https://example.com/terms",
        )

    assert "couldn't reach" in str(error_info.value).lower()


def test_tracked_policy_service_rejects_duplicate_active_canonical_url_per_owner() -> None:
    checked_at = datetime.now(timezone.utc) - timedelta(minutes=5)
    service = _build_service(
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

    created_tracked_policy = service.create_tracked_policy(
        subject=subject,
        source_url="https://example.com/terms?b=2&a=1",
    )

    assert created_tracked_policy.tracking_status == PolicyTrackingStatus.PENDING_FIRST_SNAPSHOT
    assert created_tracked_policy.last_checked_at == checked_at

    with pytest.raises(DuplicateTrackedPolicyError):
        service.create_tracked_policy(
            subject=subject,
            source_url="https://Example.com:443/terms?a=1&b=2#fragment",
        )
