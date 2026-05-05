"""Orchestration of tracked-policy check executions.

This service introduces a durable execution model around the existing
synchronous check logic, adding deduplication and structured failure records.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from uuid import UUID

from ..repositories.errors import ActiveTrackedPolicyCheckExecutionConflictError
from ..repositories.interfaces import (
    TrackedPolicyCheckExecutionRepository,
    TrackedPolicyRepository,
)
from ..repositories.models import (
    StoredTrackedPolicy,
    StoredTrackedPolicyCheckExecution,
)
from ..repositories.tracked_policy_check_execution_status import TrackedPolicyCheckExecutionStatus
from .policy_snapshot_service import (
    PolicySnapshotCheckFailedError,
    PolicySnapshotService,
    PolicySnapshotTrackedPolicyNotFoundError,
)
from .request_subject import RequestSubject

logger = logging.getLogger(__name__)


class TrackedPolicyNotFoundError(Exception):
    """Raised when a tracked policy is not found for the active owner subject."""


class TrackedPolicyCheckExecutionNotFoundError(Exception):
    """Raised when a specific check execution is not found."""


@dataclass(frozen=True)
class TrackedPolicyCheckExecutionResult:
    """Result of an execution submission or check."""

    execution: StoredTrackedPolicyCheckExecution
    tracked_policy: StoredTrackedPolicy | None


class TrackedPolicyCheckExecutionService:
    """Coordinate check execution lifecycle and deduplication."""

    def __init__(
        self,
        *,
        tracked_policy_repository: TrackedPolicyRepository,
        check_execution_repository: TrackedPolicyCheckExecutionRepository,
        policy_snapshot_service: PolicySnapshotService,
        policy_change_notification_service: object | None = None,
    ) -> None:
        self._tracked_policy_repository = tracked_policy_repository
        self._check_execution_repository = check_execution_repository
        self._policy_snapshot_service = policy_snapshot_service
        self._policy_change_notification_service = policy_change_notification_service

    def execute_check(
        self, *, subject: RequestSubject, tracked_policy_id: UUID
    ) -> TrackedPolicyCheckExecutionResult:
        """Submit and synchronously process a tracked-policy check execution."""

        # 1. Ownership Lookup
        tracked_policy = self._tracked_policy_repository.get_active_for_subject(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )
        if tracked_policy is None:
            raise TrackedPolicyNotFoundError(f"Tracked policy {tracked_policy_id} was not found.")

        # 2. Deduplication
        active_execution = self._check_execution_repository.get_active_for_tracked_policy(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )
        if active_execution is not None:
            return TrackedPolicyCheckExecutionResult(
                execution=active_execution,
                tracked_policy=tracked_policy,
            )

        # 3. Execution Record Creation
        try:
            execution = self._check_execution_repository.create(
                tracked_policy_id=tracked_policy_id,
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
            )
        except ActiveTrackedPolicyCheckExecutionConflictError:
            active_execution = self._check_execution_repository.get_active_for_tracked_policy(
                tracked_policy_id=tracked_policy_id,
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
            )
            if active_execution is None:
                raise RuntimeError(
                    "Tracked-policy check execution create conflicted, but no active execution "
                    "could be reloaded."
                ) from None
            return TrackedPolicyCheckExecutionResult(
                execution=active_execution,
                tracked_policy=tracked_policy,
            )

        self._check_execution_repository.mark_running(execution_id=execution.id)

        # 4. Invocation & State Transitions
        try:
            result = self._policy_snapshot_service.check_tracked_policy(
                subject=subject,
                tracked_policy_id=tracked_policy_id,
            )
            completed_execution = self._check_execution_repository.mark_completed(
                execution_id=execution.id,
                status=TrackedPolicyCheckExecutionStatus.SUCCEEDED,
                result_snapshot_created=result.snapshot_created,
                result_change_event_id=result.meaningful_change_event_id,
            )
            if completed_execution is None:
                raise ValueError(f"Could not complete execution {execution.id}")

            notifier = self._policy_change_notification_service
            if notifier is not None:
                try:
                    notifier.dispatch_after_successful_check(
                        subject=subject,
                        tracked_policy=result.tracked_policy,
                        meaningful_change_event_id=result.meaningful_change_event_id,
                        snapshot_created=result.snapshot_created,
                    )
                except Exception:
                    logger.exception(
                        "policy_change_notification_dispatch_failed",
                        extra={
                            "tracked_policy_id": str(tracked_policy_id),
                            "execution_id": str(execution.id),
                        },
                    )

            return TrackedPolicyCheckExecutionResult(
                execution=completed_execution,
                tracked_policy=result.tracked_policy,
            )

        except PolicySnapshotTrackedPolicyNotFoundError as error:
            _ = self._check_execution_repository.mark_completed(
                execution_id=execution.id,
                status=TrackedPolicyCheckExecutionStatus.FAILED,
                failure_message=str(error),
                failure_stage="ownership_check",
            )
            raise TrackedPolicyNotFoundError(str(error)) from error

        except Exception as error:
            # 5. Structured failure classification
            failure_message = str(error)
            status = TrackedPolicyCheckExecutionStatus.FAILED

            # Check for timeout semantics in the error message
            if "timed out" in failure_message.lower() or isinstance(error, TimeoutError):
                status = TrackedPolicyCheckExecutionStatus.TIMED_OUT

            completed_execution = self._check_execution_repository.mark_completed(
                execution_id=execution.id,
                status=status,
                failure_message=failure_message,
                failure_stage="capture_and_analysis",
            )
            if completed_execution is None:
                raise ValueError(f"Could not complete execution {execution.id}")

            # Refetch the tracked policy to return the updated error states (like latest_capture_status)
            updated_tracked_policy = self._tracked_policy_repository.get_active_for_subject(
                tracked_policy_id=tracked_policy_id,
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
            )
            return TrackedPolicyCheckExecutionResult(
                execution=completed_execution,
                tracked_policy=updated_tracked_policy,
            )

    def get_tracked_policy_execution(
        self, *, subject: RequestSubject, execution_id: UUID
    ) -> StoredTrackedPolicyCheckExecution:
        """Return one stored execution scoped to the request subject."""

        execution = self._check_execution_repository.get_by_id(
            execution_id=execution_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )
        if execution is None:
            raise TrackedPolicyCheckExecutionNotFoundError(
                f"Tracked policy check execution {execution_id} was not found."
            )
        return execution
