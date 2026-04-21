from datetime import datetime, timezone
from uuid import uuid4

from app.test_support_policy_text_samples import (
    LEGACY_NOISY_POLICY_TEXT_AFTER,
    LEGACY_NOISY_POLICY_TEXT_BEFORE,
)
from app.repositories.models import StoredPolicySnapshot
from app.repositories.policy_capture_status import PolicySnapshotStatus
from app.repositories.policy_change_status import PolicyChangeStatus
from app.repositories.policy_snapshot_hash import build_policy_snapshot_content_hash
from app.services.policy_change_detection_service import PolicyChangeDetectionService
from app.services.policy_text_canonicalizer import CURRENT_POLICY_TEXT_NORMALIZATION_VERSION


def _snapshot(
    text: str,
    *,
    raw_text_body: str | None = None,
    normalization_version: int | None = CURRENT_POLICY_TEXT_NORMALIZATION_VERSION,
) -> StoredPolicySnapshot:
    return StoredPolicySnapshot(
        id=uuid4(),
        tracked_policy_id=uuid4(),
        raw_text_body=raw_text_body if raw_text_body is not None else text,
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
        normalization_version=normalization_version,
    )


def test_detect_change_returns_not_evaluated_without_prior_snapshot() -> None:
    service = PolicyChangeDetectionService()

    result = service.detect_change(
        previous_snapshot=None,
        raw_text_body=None,
        normalized_text_body="These terms include arbitration and cancellation rights.",
        normalization_version=CURRENT_POLICY_TEXT_NORMALIZATION_VERSION,
    )

    assert result.change_status == PolicyChangeStatus.NOT_EVALUATED
    assert result.should_create_snapshot is True
    assert result.content_changed is None


def test_detect_change_returns_unchanged_for_exact_hash_match() -> None:
    service = PolicyChangeDetectionService()
    previous_snapshot = _snapshot("These terms include arbitration and cancellation rights.")

    result = service.detect_change(
        previous_snapshot=previous_snapshot,
        raw_text_body=None,
        normalized_text_body="These terms include arbitration and cancellation rights.",
        normalization_version=CURRENT_POLICY_TEXT_NORMALIZATION_VERSION,
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
        raw_text_body=None,
        normalized_text_body="These terms include arbitration, and cancellation rights!",
        normalization_version=CURRENT_POLICY_TEXT_NORMALIZATION_VERSION,
    )

    assert result.change_status == PolicyChangeStatus.UNCHANGED
    assert result.detection_method == "trivial_formatting_suppressed"
    assert result.should_create_snapshot is False
    assert result.content_changed is False


def test_detect_change_suppresses_legacy_form_noise_differences() -> None:
    service = PolicyChangeDetectionService()
    previous_snapshot = _snapshot(
        LEGACY_NOISY_POLICY_TEXT_BEFORE,
        raw_text_body=LEGACY_NOISY_POLICY_TEXT_BEFORE,
        normalization_version=None,
    )

    result = service.detect_change(
        previous_snapshot=previous_snapshot,
        raw_text_body=LEGACY_NOISY_POLICY_TEXT_AFTER,
        normalized_text_body=LEGACY_NOISY_POLICY_TEXT_AFTER,
        normalization_version=None,
    )

    assert result.change_status == PolicyChangeStatus.UNCHANGED
    assert result.detection_method == "canonicalized_text_match"
    assert result.should_create_snapshot is False
    assert result.content_changed is False


def test_detect_change_marks_meaningful_updates_inside_flat_legacy_text() -> None:
    service = PolicyChangeDetectionService()
    previous_snapshot = _snapshot(
        "Terms of Service Users must resolve disputes in Texas. Billing remains monthly.",
        raw_text_body="Terms of Service Users must resolve disputes in Texas. Billing remains monthly.",
        normalization_version=None,
    )

    result = service.detect_change(
        previous_snapshot=previous_snapshot,
        raw_text_body=(
            "Terms of Service Users must resolve disputes in Delaware. Billing remains monthly."
        ),
        normalized_text_body=(
            "Terms of Service Users must resolve disputes in Delaware. Billing remains monthly."
        ),
        normalization_version=None,
    )

    assert result.change_status == PolicyChangeStatus.UPDATED
    assert result.detection_method == "meaningful_text_change"
    assert result.should_create_snapshot is True
    assert result.content_changed is True
