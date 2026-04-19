"""Transport mappers for tracked-policy response payloads."""

from ...repositories.models import StoredTrackedPolicy
from ...services.tracked_policy_service import TrackedPolicyEnrollmentResult
from ...schemas.tracked_policies import TrackedPolicyCreateResponse, TrackedPolicyResponse


def to_tracked_policy_response(tracked_policy: StoredTrackedPolicy) -> TrackedPolicyResponse:
    """Map a persistence tracked-policy model to the API response contract."""

    return TrackedPolicyResponse(
        id=tracked_policy.id,
        canonical_url=tracked_policy.canonical_url,
        display_name=tracked_policy.display_name,
        source_type=tracked_policy.source_type,
        tracking_status=tracked_policy.tracking_status.value,
        last_checked_at=tracked_policy.last_checked_at,
        last_successful_capture_at=tracked_policy.last_successful_capture_at,
        latest_capture_status=tracked_policy.latest_capture_status.value,
        latest_capture_message=tracked_policy.latest_capture_message,
        latest_change_status=tracked_policy.latest_change_status.value,
        latest_change_detected_at=tracked_policy.latest_change_detected_at,
        created_at=tracked_policy.created_at,
        snapshot_version_count=tracked_policy.snapshot_version_count,
    )


def to_tracked_policy_create_response(
    enrollment_result: TrackedPolicyEnrollmentResult,
) -> TrackedPolicyCreateResponse:
    """Map watchlist-enrollment result to the create-response API contract."""

    tracked_policy = enrollment_result.tracked_policy
    return TrackedPolicyCreateResponse(
        id=tracked_policy.id,
        canonical_url=tracked_policy.canonical_url,
        display_name=tracked_policy.display_name,
        source_type=tracked_policy.source_type,
        tracking_status=tracked_policy.tracking_status.value,
        last_checked_at=tracked_policy.last_checked_at,
        last_successful_capture_at=tracked_policy.last_successful_capture_at,
        latest_capture_status=tracked_policy.latest_capture_status.value,
        latest_capture_message=tracked_policy.latest_capture_message,
        latest_change_status=tracked_policy.latest_change_status.value,
        latest_change_detected_at=tracked_policy.latest_change_detected_at,
        created_at=tracked_policy.created_at,
        snapshot_version_count=tracked_policy.snapshot_version_count,
        baseline_report_id=enrollment_result.baseline_report.id,
        baseline_report_action=enrollment_result.baseline_report_action,
    )
