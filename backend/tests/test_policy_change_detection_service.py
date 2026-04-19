from datetime import datetime, timezone
from uuid import uuid4

from app.repositories.models import StoredPolicySnapshot
from app.repositories.policy_capture_status import PolicySnapshotStatus
from app.repositories.policy_change_status import PolicyChangeStatus
from app.repositories.policy_snapshot_hash import build_policy_snapshot_content_hash
from app.services.policy_change_detection_service import PolicyChangeDetectionService


def _snapshot(text: str) -> StoredPolicySnapshot:
    return StoredPolicySnapshot(
        id=uuid4(),
        tracked_policy_id=uuid4(),
        raw_text_body=text,
        normalized_text_body=text,
        content_hash=build_policy_snapshot_content_hash(text),
        captured_at=datetime.now(timezone.utc),
        capture_status=PolicySnapshotStatus.CAPTURED,
        source_url="https://example.com/terms",
        final_url="https://example.com/terms",
        http_status=200,
        redirect_count=0,
        fetch_duration_ms=50,
        extractor_name="test",
        extraction_strategy="test",
        capture_error_message=None,
    )


def test_detect_change_returns_not_evaluated_without_prior_snapshot() -> None:
    service = PolicyChangeDetectionService()

    result = service.detect_change(
        previous_snapshot=None,
        normalized_text_body="These terms include arbitration and cancellation rights.",
    )

    assert result.change_status == PolicyChangeStatus.NOT_EVALUATED
    assert result.should_create_snapshot is True
    assert result.content_changed is None


def test_detect_change_returns_unchanged_for_exact_hash_match() -> None:
    service = PolicyChangeDetectionService()
    previous_snapshot = _snapshot("These terms include arbitration and cancellation rights.")

    result = service.detect_change(
        previous_snapshot=previous_snapshot,
        normalized_text_body="These terms include arbitration and cancellation rights.",
    )

    assert result.change_status == PolicyChangeStatus.UNCHANGED
    assert result.detection_method == "exact_hash_match"
    assert result.should_create_snapshot is False
    assert result.content_changed is False


def test_detect_change_suppresses_trivial_punctuation_changes() -> None:
    service = PolicyChangeDetectionService()
    previous_snapshot = _snapshot("These terms include arbitration and cancellation rights.")

    result = service.detect_change(
        previous_snapshot=previous_snapshot,
        normalized_text_body="These terms include arbitration, and cancellation rights!",
    )

    assert result.change_status == PolicyChangeStatus.UNCHANGED
    assert result.detection_method == "trivial_formatting_suppressed"
    assert result.should_create_snapshot is False
    assert result.content_changed is False


def test_detect_change_marks_meaningful_updates() -> None:
    service = PolicyChangeDetectionService()
    previous_snapshot = _snapshot("These terms include arbitration and cancellation rights.")

    result = service.detect_change(
        previous_snapshot=previous_snapshot,
        normalized_text_body=(
            "These updated terms include arbitration, cancellation rights, and mandatory venue clauses."
        ),
    )

    assert result.change_status == PolicyChangeStatus.UPDATED
    assert result.detection_method == "meaningful_text_change"
    assert result.should_create_snapshot is True
    assert result.content_changed is True
