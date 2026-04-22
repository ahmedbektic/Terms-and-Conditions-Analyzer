from dataclasses import dataclass
from uuid import UUID, uuid4

import pytest

from app.repositories.in_memory import (
    InMemoryStorage,
    InMemoryTrackedPolicyRepository,
    InMemoryTrackedPolicyCheckExecutionRepository,
)
from app.repositories.models import StoredTrackedPolicy
from app.repositories.policy_capture_status import PolicyCaptureStatus
from app.repositories.policy_change_status import PolicyChangeStatus
from app.repositories.policy_tracking_status import PolicyTrackingStatus
from app.repositories.tracked_policy_check_execution_status import TrackedPolicyCheckExecutionStatus
from app.services.policy_snapshot_service import (
    PolicySnapshotCheckFailedError,
    PolicySnapshotCheckResult,
    PolicySnapshotTrackedPolicyNotFoundError,
)
from app.services.request_subject import RequestSubject
from app.services.tracked_policy_check_execution_service import (
    TrackedPolicyCheckExecutionResult,
    TrackedPolicyCheckExecutionService,
    TrackedPolicyNotFoundError,
)


class _StubSnapshotService:
    def __init__(self):
        self.check_calls = []
        self.mock_result: PolicySnapshotCheckResult | None = None
        self.mock_error: Exception | None = None

    def check_tracked_policy(
        self, *, subject: RequestSubject, tracked_policy_id: UUID
    ) -> PolicySnapshotCheckResult:
        self.check_calls.append((subject, tracked_policy_id))
        if self.mock_error is not None:
            raise self.mock_error
        if self.mock_result is not None:
            return self.mock_result
        raise NotImplementedError("Stub missing mock_result or mock_error")


@pytest.fixture
def storage():
    return InMemoryStorage()


@pytest.fixture
def tracked_policy_repository(storage):
    return InMemoryTrackedPolicyRepository(storage)


@pytest.fixture
def execution_repository(storage):
    return InMemoryTrackedPolicyCheckExecutionRepository(storage)


@pytest.fixture
def snapshot_service():
    return _StubSnapshotService()


@pytest.fixture
def execution_service(tracked_policy_repository, execution_repository, snapshot_service):
    return TrackedPolicyCheckExecutionService(
        tracked_policy_repository=tracked_policy_repository,
        check_execution_repository=execution_repository,
        policy_snapshot_service=snapshot_service,
    )


@pytest.fixture
def subject():
    return RequestSubject(subject_type="supabase_user", subject_id="user-a")


@pytest.fixture
def tracked_policy(tracked_policy_repository, subject):
    return tracked_policy_repository.create(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        canonical_url="https://example.com/terms",
        display_name="Example Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=None,
        active=True,
    )


def test_execute_check_raises_not_found_for_missing_policy(execution_service, subject):
    with pytest.raises(TrackedPolicyNotFoundError):
        execution_service.execute_check(subject=subject, tracked_policy_id=uuid4())


def test_execute_check_creates_successful_execution(
    execution_service, snapshot_service, subject, tracked_policy
):
    snapshot_service.mock_result = PolicySnapshotCheckResult(
        tracked_policy=tracked_policy, snapshot_created=True
    )

    result = execution_service.execute_check(subject=subject, tracked_policy_id=tracked_policy.id)

    assert result.execution is not None
    assert result.execution.status == TrackedPolicyCheckExecutionStatus.SUCCEEDED
    assert result.execution.result_snapshot_created is True
    assert result.tracked_policy == tracked_policy
    assert len(snapshot_service.check_calls) == 1


def test_execute_check_deduplicates_active_execution(
    execution_service, execution_repository, snapshot_service, subject, tracked_policy
):
    # Seed an active execution
    pending_exec = execution_repository.create(
        tracked_policy_id=tracked_policy.id,
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
    )

    result = execution_service.execute_check(subject=subject, tracked_policy_id=tracked_policy.id)

    # Deduped result should return the pending execution and the existing policy,
    # without calling the snapshot service or changing the execution status.
    assert result.execution.id == pending_exec.id
    assert result.execution.status == TrackedPolicyCheckExecutionStatus.PENDING
    assert result.tracked_policy.id == tracked_policy.id
    assert len(snapshot_service.check_calls) == 0


def test_execute_check_handles_capture_failure(
    execution_service, snapshot_service, subject, tracked_policy
):
    error_msg = "Could not connect to the site"
    snapshot_service.mock_error = PolicySnapshotCheckFailedError(error_msg)

    result = execution_service.execute_check(subject=subject, tracked_policy_id=tracked_policy.id)

    assert result.execution.status == TrackedPolicyCheckExecutionStatus.FAILED
    assert result.execution.failure_message == error_msg
    # It still returns the existing policy state when we fail during check.
    assert result.tracked_policy.id == tracked_policy.id


def test_execute_check_classifies_timeout_error(
    execution_service, snapshot_service, subject, tracked_policy
):
    snapshot_service.mock_error = PolicySnapshotCheckFailedError("Analysis timed out after 30s")

    result = execution_service.execute_check(subject=subject, tracked_policy_id=tracked_policy.id)

    assert result.execution.status == TrackedPolicyCheckExecutionStatus.TIMED_OUT
    assert "timed out" in result.execution.failure_message
