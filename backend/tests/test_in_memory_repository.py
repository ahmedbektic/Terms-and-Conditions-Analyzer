from datetime import datetime, timezone
import time

import pytest

from app.repositories.in_memory import (
    InMemoryAgreementRepository,
    InMemoryReportRepository,
    InMemoryTrackedPolicyRepository,
    InMemoryStorage,
)
from app.repositories.analysis_status import AnalysisLifecycleStatus
from app.repositories.policy_tracking_status import PolicyTrackingStatus
from app.repositories.report_capture_kind import ReportContentCaptureKind
from app.repositories.models import StoredFlaggedClause


def test_report_repository_scopes_reports_by_owner() -> None:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)

    agreement_a = agreement_repository.create(
        subject_type="supabase_user",
        subject_id="user-a",
        title="A",
        source_url=None,
        agreed_at=None,
        terms_text="This terms text is long enough to pass validation.",
    )
    agreement_b = agreement_repository.create(
        subject_type="supabase_user",
        subject_id="user-b",
        title="B",
        source_url=None,
        agreed_at=None,
        terms_text="Another long enough terms text body for testing.",
    )

    report_repository.create(
        agreement_id=agreement_a.id,
        subject_type="supabase_user",
        subject_id="user-a",
        source_type="text",
        source_value="A",
        raw_input_excerpt="A excerpt",
        status=AnalysisLifecycleStatus.COMPLETED,
        summary="summary A",
        trust_score=70,
        model_name="test-model",
        flagged_clauses=[],
        completed_at=datetime.now(timezone.utc),
    )
    report_repository.create(
        agreement_id=agreement_b.id,
        subject_type="supabase_user",
        subject_id="user-b",
        source_type="text",
        source_value="B",
        raw_input_excerpt="B excerpt",
        status=AnalysisLifecycleStatus.COMPLETED,
        summary="summary B",
        trust_score=60,
        model_name="test-model",
        flagged_clauses=[],
        completed_at=datetime.now(timezone.utc),
    )

    owner_a_reports = report_repository.list_for_subject(
        subject_type="supabase_user",
        subject_id="user-a",
    )
    owner_b_reports = report_repository.list_for_subject(
        subject_type="supabase_user",
        subject_id="user-b",
    )

    assert len(owner_a_reports) == 1
    assert len(owner_b_reports) == 1
    assert owner_a_reports[0].summary == "summary A"
    assert owner_b_reports[0].summary == "summary B"


def test_report_repository_lists_newest_first() -> None:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)
    agreement = agreement_repository.create(
        subject_type="supabase_user",
        subject_id="user-a",
        title="A",
        source_url=None,
        agreed_at=None,
        terms_text="This terms text is long enough to pass validation.",
    )
    report_one = report_repository.create(
        agreement_id=agreement.id,
        subject_type="supabase_user",
        subject_id="user-a",
        source_type="text",
        source_value="A",
        raw_input_excerpt="first excerpt",
        status=AnalysisLifecycleStatus.COMPLETED,
        summary="first summary",
        trust_score=80,
        model_name="test-model",
        flagged_clauses=[
            StoredFlaggedClause(
                clause_type="forced_arbitration",
                severity="high",
                excerpt="arbitration excerpt",
                explanation="risk",
            )
        ],
        completed_at=datetime.now(timezone.utc),
    )

    # Small sleep avoids same-timestamp ordering collisions on fast environments.
    time.sleep(0.001)

    report_two = report_repository.create(
        agreement_id=agreement.id,
        subject_type="supabase_user",
        subject_id="user-a",
        source_type="text",
        source_value="A",
        raw_input_excerpt="second excerpt",
        status=AnalysisLifecycleStatus.COMPLETED,
        summary="second summary",
        trust_score=55,
        model_name="test-model",
        flagged_clauses=[],
        completed_at=datetime.now(timezone.utc),
    )

    reports = report_repository.list_for_subject(
        subject_type="supabase_user",
        subject_id="user-a",
    )
    assert [report.id for report in reports] == [report_two.id, report_one.id]


def test_report_repository_supports_lifecycle_status_values() -> None:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)
    agreement = agreement_repository.create(
        subject_type="supabase_user",
        subject_id="user-a",
        title="A",
        source_url=None,
        agreed_at=None,
        terms_text="This terms text is long enough to pass validation.",
    )

    lifecycle_states = (
        AnalysisLifecycleStatus.PENDING,
        AnalysisLifecycleStatus.RUNNING,
        AnalysisLifecycleStatus.COMPLETED,
        AnalysisLifecycleStatus.FAILED,
    )
    for lifecycle_state in lifecycle_states:
        report_repository.create(
            agreement_id=agreement.id,
            subject_type="supabase_user",
            subject_id="user-a",
            source_type="text",
            source_value="A",
            raw_input_excerpt="excerpt",
            status=lifecycle_state,
            summary=f"{lifecycle_state.value} summary",
            trust_score=50,
            model_name="test-model",
            flagged_clauses=[],
            completed_at=datetime.now(timezone.utc),
        )

    reports = report_repository.list_for_subject(
        subject_type="supabase_user",
        subject_id="user-a",
    )
    report_statuses = {report.status for report in reports}
    assert report_statuses == set(lifecycle_states)


def test_report_repository_rejects_unknown_lifecycle_status() -> None:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)
    agreement = agreement_repository.create(
        subject_type="supabase_user",
        subject_id="user-a",
        title="A",
        source_url=None,
        agreed_at=None,
        terms_text="This terms text is long enough to pass validation.",
    )

    with pytest.raises(ValueError):
        report_repository.create(
            agreement_id=agreement.id,
            subject_type="supabase_user",
            subject_id="user-a",
            source_type="text",
            source_value="A",
            raw_input_excerpt="excerpt",
            status="unknown_status",
            summary="summary",
            trust_score=50,
            model_name="test-model",
            flagged_clauses=[],
            completed_at=datetime.now(timezone.utc),
        )


def test_report_repository_returns_latest_eligible_baseline_report_for_canonical_url() -> None:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)
    agreement = agreement_repository.create(
        subject_type="supabase_user",
        subject_id="user-a",
        title="Terms",
        source_url="https://example.com/terms",
        agreed_at=None,
        terms_text="This terms text is long enough to pass validation.",
    )

    report_repository.create(
        agreement_id=agreement.id,
        subject_type="supabase_user",
        subject_id="user-a",
        source_type="url",
        source_value="https://example.com/terms",
        raw_input_excerpt="fallback excerpt",
        status=AnalysisLifecycleStatus.COMPLETED,
        summary="fallback summary",
        trust_score=50,
        model_name="test-model",
        flagged_clauses=[],
        completed_at=datetime.now(timezone.utc),
        canonical_source_url="https://example.com/terms",
        content_capture_kind=ReportContentCaptureKind.FALLBACK_PLACEHOLDER,
    )

    time.sleep(0.001)

    fetched_report = report_repository.create(
        agreement_id=agreement.id,
        subject_type="supabase_user",
        subject_id="user-a",
        source_type="url",
        source_value="https://example.com/terms",
        raw_input_excerpt="fetched excerpt",
        status=AnalysisLifecycleStatus.COMPLETED,
        summary="fetched summary",
        trust_score=55,
        model_name="test-model",
        flagged_clauses=[],
        completed_at=datetime.now(timezone.utc),
        canonical_source_url="https://example.com/terms",
        content_capture_kind=ReportContentCaptureKind.FETCHED_URL,
    )

    latest_baseline = report_repository.get_latest_eligible_baseline_report_for_subject(
        canonical_source_url="https://example.com/terms",
        subject_type="supabase_user",
        subject_id="user-a",
    )

    assert latest_baseline is not None
    assert latest_baseline.id == fetched_report.id


def test_report_repository_ignores_legacy_or_submitted_reports_for_baseline_lookup() -> None:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)
    agreement = agreement_repository.create(
        subject_type="supabase_user",
        subject_id="user-a",
        title="Terms",
        source_url="https://example.com/terms",
        agreed_at=None,
        terms_text="This terms text is long enough to pass validation.",
    )

    report_repository.create(
        agreement_id=agreement.id,
        subject_type="supabase_user",
        subject_id="user-a",
        source_type="url",
        source_value="https://example.com/terms",
        raw_input_excerpt="submitted excerpt",
        status=AnalysisLifecycleStatus.COMPLETED,
        summary="submitted summary",
        trust_score=60,
        model_name="test-model",
        flagged_clauses=[],
        completed_at=datetime.now(timezone.utc),
        canonical_source_url="https://example.com/terms",
        content_capture_kind=ReportContentCaptureKind.SUBMITTED_TEXT,
    )

    latest_baseline = report_repository.get_latest_eligible_baseline_report_for_subject(
        canonical_source_url="https://example.com/terms",
        subject_type="supabase_user",
        subject_id="user-a",
    )

    assert latest_baseline is None


def test_tracked_policy_repository_scopes_active_policies_by_owner_and_hides_inactive() -> None:
    storage = InMemoryStorage()
    repository = InMemoryTrackedPolicyRepository(storage)

    owner_a_policy = repository.create(
        subject_type="supabase_user",
        subject_id="user-a",
        canonical_url="https://service-a.example/terms",
        display_name="Service A Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.PENDING_FIRST_SNAPSHOT,
        last_checked_at=datetime.now(timezone.utc),
    )
    repository.create(
        subject_type="supabase_user",
        subject_id="user-b",
        canonical_url="https://service-b.example/terms",
        display_name="Service B Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=datetime.now(timezone.utc),
    )

    deactivated_policy = repository.deactivate_for_subject(
        tracked_policy_id=owner_a_policy.id,
        subject_type="supabase_user",
        subject_id="user-a",
    )

    assert deactivated_policy is not None
    assert deactivated_policy.active is False
    assert (
        repository.list_active_for_subject(
            subject_type="supabase_user",
            subject_id="user-a",
        )
        == []
    )
    assert (
        len(
            repository.list_active_for_subject(
                subject_type="supabase_user",
                subject_id="user-b",
            )
        )
        == 1
    )


def test_tracked_policy_repository_lists_newest_active_first() -> None:
    storage = InMemoryStorage()
    repository = InMemoryTrackedPolicyRepository(storage)

    older_policy = repository.create(
        subject_type="supabase_user",
        subject_id="user-a",
        canonical_url="https://service-a.example/terms",
        display_name="Service A Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.PENDING_FIRST_SNAPSHOT,
        last_checked_at=datetime.now(timezone.utc),
    )

    time.sleep(0.001)

    newer_policy = repository.create(
        subject_type="supabase_user",
        subject_id="user-a",
        canonical_url="https://service-b.example/terms",
        display_name="Service B Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=datetime.now(timezone.utc),
    )

    tracked_policies = repository.list_active_for_subject(
        subject_type="supabase_user",
        subject_id="user-a",
    )

    assert [tracked_policy.id for tracked_policy in tracked_policies] == [
        newer_policy.id,
        older_policy.id,
    ]
