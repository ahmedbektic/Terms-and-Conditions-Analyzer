from uuid import uuid4

import pytest

from app.repositories.in_memory import (
    InMemoryTrackedPolicyCheckExecutionRepository,
    InMemoryStorage,
)
from app.repositories.tracked_policy_check_execution_status import (
    TrackedPolicyCheckExecutionStatus,
    is_active_execution_status,
    normalize_tracked_policy_check_execution_status,
)


def test_execution_status_enum_has_required_values() -> None:
    assert TrackedPolicyCheckExecutionStatus.PENDING.value == "pending"
    assert TrackedPolicyCheckExecutionStatus.RUNNING.value == "running"
    assert TrackedPolicyCheckExecutionStatus.SUCCEEDED.value == "succeeded"
    assert TrackedPolicyCheckExecutionStatus.FAILED.value == "failed"
    assert TrackedPolicyCheckExecutionStatus.TIMED_OUT.value == "timed_out"


def test_active_status_helper_identifies_active_and_terminal_states() -> None:
    assert is_active_execution_status(TrackedPolicyCheckExecutionStatus.PENDING) is True
    assert is_active_execution_status(TrackedPolicyCheckExecutionStatus.RUNNING) is True
    assert is_active_execution_status(TrackedPolicyCheckExecutionStatus.SUCCEEDED) is False
    assert is_active_execution_status(TrackedPolicyCheckExecutionStatus.FAILED) is False
    assert is_active_execution_status(TrackedPolicyCheckExecutionStatus.TIMED_OUT) is False


def test_normalize_execution_status_accepts_string_and_enum() -> None:
    assert (
        normalize_tracked_policy_check_execution_status("pending")
        == TrackedPolicyCheckExecutionStatus.PENDING
    )
    assert (
        normalize_tracked_policy_check_execution_status(TrackedPolicyCheckExecutionStatus.FAILED)
        == TrackedPolicyCheckExecutionStatus.FAILED
    )


def test_normalize_execution_status_rejects_unknown_value() -> None:
    with pytest.raises(ValueError, match="Unsupported check execution status"):
        normalize_tracked_policy_check_execution_status("bogus")


# ── In-memory repository contract tests ──────────────────────────────────


def _build_repo() -> InMemoryTrackedPolicyCheckExecutionRepository:
    return InMemoryTrackedPolicyCheckExecutionRepository(InMemoryStorage())


TRACKED_POLICY_ID = uuid4()
OWNER = {"subject_type": "supabase_user", "subject_id": "user-a"}
OTHER_OWNER = {"subject_type": "supabase_user", "subject_id": "user-b"}


def test_create_returns_pending_execution_with_timestamps() -> None:
    repo = _build_repo()
    execution = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)

    assert execution.status == TrackedPolicyCheckExecutionStatus.PENDING
    assert execution.tracked_policy_id == TRACKED_POLICY_ID
    assert execution.subject_type == OWNER["subject_type"]
    assert execution.subject_id == OWNER["subject_id"]
    assert execution.created_at is not None
    assert execution.started_at is None
    assert execution.completed_at is None
    assert execution.failure_code is None
    assert execution.result_snapshot_created is None


def test_get_by_id_returns_execution_for_owner() -> None:
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    fetched = repo.get_by_id(execution_id=created.id, **OWNER)

    assert fetched is not None
    assert fetched.id == created.id


def test_get_by_id_returns_none_for_different_owner() -> None:
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    fetched = repo.get_by_id(execution_id=created.id, **OTHER_OWNER)

    assert fetched is None


def test_get_by_id_returns_none_for_unknown_id() -> None:
    repo = _build_repo()
    fetched = repo.get_by_id(execution_id=uuid4(), **OWNER)

    assert fetched is None


def test_get_active_returns_pending_execution() -> None:
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    active = repo.get_active_for_tracked_policy(
        tracked_policy_id=TRACKED_POLICY_ID, **OWNER
    )

    assert active is not None
    assert active.id == created.id


def test_get_active_returns_running_execution() -> None:
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    repo.mark_running(execution_id=created.id)
    active = repo.get_active_for_tracked_policy(
        tracked_policy_id=TRACKED_POLICY_ID, **OWNER
    )

    assert active is not None
    assert active.status == TrackedPolicyCheckExecutionStatus.RUNNING


def test_get_active_returns_none_after_completion() -> None:
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    repo.mark_running(execution_id=created.id)
    repo.mark_completed(
        execution_id=created.id,
        status=TrackedPolicyCheckExecutionStatus.SUCCEEDED,
        result_snapshot_created=True,
    )
    active = repo.get_active_for_tracked_policy(
        tracked_policy_id=TRACKED_POLICY_ID, **OWNER
    )

    assert active is None


def test_get_active_scopes_to_owner() -> None:
    repo = _build_repo()
    repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    active = repo.get_active_for_tracked_policy(
        tracked_policy_id=TRACKED_POLICY_ID, **OTHER_OWNER
    )

    assert active is None


def test_mark_running_transitions_pending_to_running_with_started_at() -> None:
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    running = repo.mark_running(execution_id=created.id)

    assert running is not None
    assert running.status == TrackedPolicyCheckExecutionStatus.RUNNING
    assert running.started_at is not None


def test_mark_running_rejects_non_pending_execution() -> None:
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    repo.mark_running(execution_id=created.id)
    second_attempt = repo.mark_running(execution_id=created.id)

    assert second_attempt is None


def test_mark_completed_with_success_sets_terminal_fields() -> None:
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    repo.mark_running(execution_id=created.id)
    snapshot_id = uuid4()
    change_event_id = uuid4()
    completed = repo.mark_completed(
        execution_id=created.id,
        status=TrackedPolicyCheckExecutionStatus.SUCCEEDED,
        result_snapshot_created=True,
        result_new_snapshot_id=snapshot_id,
        result_change_event_id=change_event_id,
    )

    assert completed is not None
    assert completed.status == TrackedPolicyCheckExecutionStatus.SUCCEEDED
    assert completed.completed_at is not None
    assert completed.result_snapshot_created is True
    assert completed.result_new_snapshot_id == snapshot_id
    assert completed.result_change_event_id == change_event_id
    assert completed.failure_code is None


def test_mark_completed_with_failure_records_structured_metadata() -> None:
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    repo.mark_running(execution_id=created.id)
    failed = repo.mark_completed(
        execution_id=created.id,
        status=TrackedPolicyCheckExecutionStatus.FAILED,
        failure_code="capture_failed",
        failure_stage="fetch",
        failure_message="403 Forbidden",
        failure_retryable=True,
    )

    assert failed is not None
    assert failed.status == TrackedPolicyCheckExecutionStatus.FAILED
    assert failed.failure_code == "capture_failed"
    assert failed.failure_stage == "fetch"
    assert failed.failure_message == "403 Forbidden"
    assert failed.failure_retryable is True
    assert failed.result_snapshot_created is None


def test_mark_completed_rejects_already_terminal_execution() -> None:
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    repo.mark_running(execution_id=created.id)
    repo.mark_completed(
        execution_id=created.id,
        status=TrackedPolicyCheckExecutionStatus.SUCCEEDED,
    )
    second = repo.mark_completed(
        execution_id=created.id,
        status=TrackedPolicyCheckExecutionStatus.FAILED,
        failure_code="late_failure",
    )

    assert second is None


def test_mark_completed_can_transition_directly_from_pending() -> None:
    """A pending execution can be marked completed without going through running."""
    repo = _build_repo()
    created = repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    completed = repo.mark_completed(
        execution_id=created.id,
        status=TrackedPolicyCheckExecutionStatus.FAILED,
        failure_code="validation_error",
        failure_message="Tracked policy not found",
    )

    assert completed is not None
    assert completed.status == TrackedPolicyCheckExecutionStatus.FAILED
    assert completed.started_at is not None  # backfilled
    assert completed.completed_at is not None


def test_storage_clear_removes_check_executions() -> None:
    storage = InMemoryStorage()
    repo = InMemoryTrackedPolicyCheckExecutionRepository(storage)
    repo.create(tracked_policy_id=TRACKED_POLICY_ID, **OWNER)
    storage.clear()

    assert repo.get_active_for_tracked_policy(
        tracked_policy_id=TRACKED_POLICY_ID, **OWNER
    ) is None
