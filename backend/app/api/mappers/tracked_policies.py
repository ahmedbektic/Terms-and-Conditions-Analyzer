"""Transport mappers for tracked-policy response payloads."""

from ...repositories.models import StoredTrackedPolicy
from ...schemas.tracked_policies import (
    TrackedPolicyCreateResponse,
    TrackedPolicyCheckExecutionEnvelope,
    TrackedPolicyCheckExecutionResponse,
    TrackedPolicyResponse,
    TrackedPolicySnapshotCompareBlockResponse,
    TrackedPolicySnapshotComparisonResponse,
    TrackedPolicySnapshotResponse,
)
from ...services.tracked_policy_check_execution_service import (
    TrackedPolicyCheckExecutionResult,
)
from ...services.tracked_policy_service import TrackedPolicyEnrollmentResult
from ...services.tracked_policy_versions_service import (
    TrackedPolicyComparisonBlock,
    TrackedPolicyComparisonResult,
    TrackedPolicySnapshotVersion,
)


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


def to_tracked_policy_snapshot_response(
    snapshot_version: TrackedPolicySnapshotVersion,
) -> TrackedPolicySnapshotResponse:
    """Map tracked-policy snapshot history metadata to the API response contract."""

    return TrackedPolicySnapshotResponse(
        snapshot_id=snapshot_version.snapshot_id,
        version_number=snapshot_version.version_number,
        captured_at=snapshot_version.captured_at,
        source_url=snapshot_version.source_url,
        final_url=snapshot_version.final_url,
        capture_status=snapshot_version.capture_status,
        change_status=snapshot_version.change_status,
    )


def to_tracked_policy_compare_block_response(
    block: TrackedPolicyComparisonBlock,
) -> TrackedPolicySnapshotCompareBlockResponse:
    """Map one diff block to the tracked-policy compare response contract."""

    return TrackedPolicySnapshotCompareBlockResponse(
        change_type=block.change_type,
        older_text=block.older_text,
        newer_text=block.newer_text,
    )


def to_tracked_policy_snapshot_comparison_response(
    comparison_result: TrackedPolicyComparisonResult,
) -> TrackedPolicySnapshotComparisonResponse:
    """Map tracked-policy compare service output to the API response contract."""

    return TrackedPolicySnapshotComparisonResponse(
        tracked_policy=to_tracked_policy_response(comparison_result.tracked_policy),
        older_snapshot=to_tracked_policy_snapshot_response(comparison_result.older_snapshot),
        newer_snapshot=to_tracked_policy_snapshot_response(comparison_result.newer_snapshot),
        diff_blocks=[
            to_tracked_policy_compare_block_response(block)
            for block in comparison_result.diff_blocks
        ],
        comparison_outcome=comparison_result.comparison_outcome,
        normalization_notice=comparison_result.normalization_notice,
        render_mode="split_or_unified",
    )


def to_tracked_policy_check_execution_envelope(
    execution_result: TrackedPolicyCheckExecutionResult,
) -> TrackedPolicyCheckExecutionEnvelope:
    """Map an execution model and resolving policy to the API check-envelope contract."""
    execution = execution_result.execution

    response_execution = TrackedPolicyCheckExecutionResponse(
        id=execution.id,
        tracked_policy_id=execution.tracked_policy_id,
        status=execution.status.value,
        result_snapshot_created=execution.result_snapshot_created,
        failure_message=execution.failure_message,
        execute_started_at=execution.started_at,
        execute_finished_at=execution.completed_at,
    )

    response_tracked_policy = None
    if execution_result.tracked_policy:
        response_tracked_policy = to_tracked_policy_response(execution_result.tracked_policy)

    return TrackedPolicyCheckExecutionEnvelope(
        execution=response_execution,
        tracked_policy=response_tracked_policy,
    )
