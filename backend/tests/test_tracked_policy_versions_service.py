from datetime import datetime, timezone
from pathlib import Path

import pytest

from app.repositories.in_memory import (
    InMemoryPolicyChangeEventRepository,
    InMemoryPolicySnapshotRepository,
    InMemoryStorage,
    InMemoryTrackedPolicyRepository,
)
from app.repositories.models import PolicyChangeEventCreateInput, PolicySnapshotCreateInput
from app.repositories.policy_capture_status import PolicyCaptureStatus
from app.repositories.policy_change_status import PolicyChangeStatus
from app.repositories.policy_tracking_status import PolicyTrackingStatus
from app.services.policy_text_canonicalizer import CURRENT_POLICY_TEXT_NORMALIZATION_VERSION
from app.services.request_subject import RequestSubject
from app.services.tracked_policy_versions_service import (
    TrackedPolicySnapshotNotFoundError,
    TrackedPolicyVersionComparisonError,
    TrackedPolicyVersionsService,
)


def _build_service():
    storage = InMemoryStorage()
    tracked_policy_repository = InMemoryTrackedPolicyRepository(storage)
    policy_snapshot_repository = InMemoryPolicySnapshotRepository(storage)
    policy_change_event_repository = InMemoryPolicyChangeEventRepository(storage)
    service = TrackedPolicyVersionsService(
        tracked_policy_repository=tracked_policy_repository,
        policy_snapshot_repository=policy_snapshot_repository,
        policy_change_event_repository=policy_change_event_repository,
    )
    return (
        service,
        tracked_policy_repository,
        policy_snapshot_repository,
        policy_change_event_repository,
    )


def test_list_snapshot_history_returns_newest_first_with_version_numbers() -> None:
    (
        service,
        tracked_policy_repository,
        policy_snapshot_repository,
        policy_change_event_repository,
    ) = _build_service()
    subject = RequestSubject(subject_type="supabase_user", subject_id="owner-a")
    tracked_policy = tracked_policy_repository.create(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        canonical_url="https://example.com/terms",
        display_name="Example Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        active=True,
    )
    baseline_snapshot = policy_snapshot_repository.append_for_tracked_policy_if_changed(
        tracked_policy_id=tracked_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body="Paragraph one.\n\nParagraph two.",
            normalized_text_body="Paragraph one.\n\nParagraph two.",
            normalization_version=CURRENT_POLICY_TEXT_NORMALIZATION_VERSION,
            captured_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
            source_url="https://example.com/terms",
            final_url="https://example.com/terms",
        ),
    ).snapshot
    tracked_policy_repository.update_tracked_policy_check_state(
        tracked_policy_id=tracked_policy.id,
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        last_checked_at=baseline_snapshot.captured_at,
        tracking_status=PolicyTrackingStatus.ACTIVE,
        latest_capture_status=PolicyCaptureStatus.CAPTURED,
        latest_capture_message=None,
        latest_change_status=PolicyChangeStatus.NOT_EVALUATED,
        latest_change_detected_at=None,
    )
    updated_snapshot = policy_snapshot_repository.append_for_tracked_policy_if_changed(
        tracked_policy_id=tracked_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body="Paragraph one updated.\n\nParagraph two.",
            normalized_text_body="Paragraph one updated.\n\nParagraph two.",
            normalization_version=CURRENT_POLICY_TEXT_NORMALIZATION_VERSION,
            captured_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
            source_url="https://example.com/terms",
            final_url="https://example.com/terms",
        ),
    ).snapshot
    policy_change_event_repository.create(
        event=PolicyChangeEventCreateInput(
            tracked_policy_id=tracked_policy.id,
            previous_snapshot_id=baseline_snapshot.id,
            new_snapshot_id=updated_snapshot.id,
            detected_at=updated_snapshot.captured_at,
            change_status=PolicyChangeStatus.UPDATED,
            detection_method="structured_diff",
            content_changed=True,
        )
    )

    returned_policy, history = service.list_snapshot_history(
        subject=subject,
        tracked_policy_id=tracked_policy.id,
    )

    assert returned_policy.id == tracked_policy.id
    assert [snapshot.version_number for snapshot in history] == [2, 1]
    assert [snapshot.snapshot_id for snapshot in history] == [
        updated_snapshot.id,
        baseline_snapshot.id,
    ]
    assert history[0].change_status == "updated"
    assert history[1].change_status is None


def test_compare_snapshots_returns_localized_diff_blocks_for_real_clause_change() -> None:
    (
        service,
        tracked_policy_repository,
        policy_snapshot_repository,
        policy_change_event_repository,
    ) = _build_service()
    subject = RequestSubject(subject_type="supabase_user", subject_id="owner-a")
    tracked_policy = tracked_policy_repository.create(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        canonical_url="https://example.com/terms",
        display_name="Example Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        active=True,
    )
    older_snapshot = policy_snapshot_repository.append_for_tracked_policy_if_changed(
        tracked_policy_id=tracked_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body=(
                "Terms of Service Users must resolve disputes in Texas. Billing remains monthly."
            ),
            normalized_text_body=(
                "Terms of Service Users must resolve disputes in Texas. Billing remains monthly."
            ),
            captured_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
            source_url="https://example.com/terms",
            final_url="https://example.com/terms",
        ),
    ).snapshot
    newer_snapshot = policy_snapshot_repository.append_for_tracked_policy_if_changed(
        tracked_policy_id=tracked_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body=(
                "Terms of Service Users must resolve disputes in Delaware. Billing remains monthly."
            ),
            normalized_text_body=(
                "Terms of Service Users must resolve disputes in Delaware. Billing remains monthly."
            ),
            captured_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
            source_url="https://example.com/terms",
            final_url="https://example.com/terms",
        ),
    ).snapshot
    policy_change_event_repository.create(
        event=PolicyChangeEventCreateInput(
            tracked_policy_id=tracked_policy.id,
            previous_snapshot_id=older_snapshot.id,
            new_snapshot_id=newer_snapshot.id,
            detected_at=newer_snapshot.captured_at,
            change_status=PolicyChangeStatus.UPDATED,
            detection_method="structured_diff",
            content_changed=True,
        )
    )

    comparison = service.compare_snapshots(
        subject=subject,
        tracked_policy_id=tracked_policy.id,
        snapshot_a_id=newer_snapshot.id,
        snapshot_b_id=older_snapshot.id,
    )

    assert comparison.older_snapshot.snapshot_id == older_snapshot.id
    assert comparison.newer_snapshot.snapshot_id == newer_snapshot.id
    assert comparison.comparison_outcome == "meaningful_changes"
    assert comparison.diff_blocks[0].older_text == "Terms of Service Users must resolve disputes in Texas."
    assert comparison.diff_blocks[1].newer_text == (
        "Terms of Service Users must resolve disputes in Delaware."
    )
    assert comparison.diff_blocks[-1].change_type == "unchanged"


def test_compare_snapshots_returns_no_meaningful_changes_for_legacy_noise_only_differences() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    term1 = (repo_root / "term1.txt").read_text(encoding="utf-8")
    term2 = (repo_root / "term2.txt").read_text(encoding="utf-8")
    (
        service,
        tracked_policy_repository,
        policy_snapshot_repository,
        _,
    ) = _build_service()
    subject = RequestSubject(subject_type="supabase_user", subject_id="owner-a")
    tracked_policy = tracked_policy_repository.create(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        canonical_url="https://example.com/terms",
        display_name="Example Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        active=True,
    )
    older_snapshot = policy_snapshot_repository.append_for_tracked_policy_if_changed(
        tracked_policy_id=tracked_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body=term1,
            normalized_text_body=term1,
            captured_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
            source_url="https://example.com/terms",
            final_url="https://example.com/terms",
        ),
    ).snapshot
    newer_snapshot = policy_snapshot_repository.append_for_tracked_policy_if_changed(
        tracked_policy_id=tracked_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body=term2,
            normalized_text_body=term2,
            captured_at=datetime(2026, 3, 2, 12, 0, tzinfo=timezone.utc),
            source_url="https://example.com/terms",
            final_url="https://example.com/terms",
        ),
    ).snapshot

    comparison = service.compare_snapshots(
        subject=subject,
        tracked_policy_id=tracked_policy.id,
        snapshot_a_id=newer_snapshot.id,
        snapshot_b_id=older_snapshot.id,
    )

    assert comparison.comparison_outcome == "no_meaningful_changes"
    assert comparison.diff_blocks == []
    assert comparison.normalization_notice is not None
    assert "normalized before comparison" in comparison.normalization_notice.lower()


def test_compare_snapshots_rejects_duplicate_snapshot_ids() -> None:
    service, tracked_policy_repository, policy_snapshot_repository, _ = _build_service()
    subject = RequestSubject(subject_type="supabase_user", subject_id="owner-a")
    tracked_policy = tracked_policy_repository.create(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        canonical_url="https://example.com/terms",
        display_name="Example Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        active=True,
    )
    snapshot = policy_snapshot_repository.append_for_tracked_policy_if_changed(
        tracked_policy_id=tracked_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body="Alpha paragraph.",
            normalized_text_body="Alpha paragraph.",
            captured_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        ),
    ).snapshot

    with pytest.raises(TrackedPolicyVersionComparisonError):
        service.compare_snapshots(
            subject=subject,
            tracked_policy_id=tracked_policy.id,
            snapshot_a_id=snapshot.id,
            snapshot_b_id=snapshot.id,
        )


def test_compare_snapshots_rejects_snapshot_ids_outside_the_policy() -> None:
    service, tracked_policy_repository, policy_snapshot_repository, _ = _build_service()
    subject = RequestSubject(subject_type="supabase_user", subject_id="owner-a")
    first_policy = tracked_policy_repository.create(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        canonical_url="https://example.com/terms",
        display_name="Example Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        active=True,
    )
    second_policy = tracked_policy_repository.create(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        canonical_url="https://example.com/privacy",
        display_name="Example Privacy",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=datetime(2026, 3, 1, 13, 0, tzinfo=timezone.utc),
        active=True,
    )
    first_snapshot = policy_snapshot_repository.append_for_tracked_policy_if_changed(
        tracked_policy_id=first_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body="Alpha paragraph.",
            normalized_text_body="Alpha paragraph.",
            captured_at=datetime(2026, 3, 1, 12, 0, tzinfo=timezone.utc),
        ),
    ).snapshot
    outside_snapshot = policy_snapshot_repository.append_for_tracked_policy_if_changed(
        tracked_policy_id=second_policy.id,
        snapshot=PolicySnapshotCreateInput(
            raw_text_body="Beta paragraph.",
            normalized_text_body="Beta paragraph.",
            captured_at=datetime(2026, 3, 1, 13, 0, tzinfo=timezone.utc),
        ),
    ).snapshot

    with pytest.raises(TrackedPolicySnapshotNotFoundError):
        service.compare_snapshots(
            subject=subject,
            tracked_policy_id=first_policy.id,
            snapshot_a_id=first_snapshot.id,
            snapshot_b_id=outside_snapshot.id,
        )
