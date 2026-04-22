"""Execution-status enum for tracked-policy check runs.

These values describe the lifecycle of one check execution, not the tracked
policy itself.  The enum is intentionally separate from
``PolicyTrackingStatus`` so execution history does not pollute watchlist state.
"""

from enum import Enum

__all__ = [
    "TrackedPolicyCheckExecutionStatus",
    "normalize_tracked_policy_check_execution_status",
]


class TrackedPolicyCheckExecutionStatus(str, Enum):
    """Lifecycle states for one tracked-policy check execution."""

    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    TIMED_OUT = "timed_out"


_ACTIVE_STATUSES = frozenset(
    {
        TrackedPolicyCheckExecutionStatus.PENDING,
        TrackedPolicyCheckExecutionStatus.RUNNING,
    }
)


def is_active_execution_status(status: TrackedPolicyCheckExecutionStatus) -> bool:
    """Return True when the status represents an in-progress execution."""

    return status in _ACTIVE_STATUSES


def normalize_tracked_policy_check_execution_status(
    value: TrackedPolicyCheckExecutionStatus | str,
) -> TrackedPolicyCheckExecutionStatus:
    """Normalize execution status values, raising for unknown strings."""

    if isinstance(value, TrackedPolicyCheckExecutionStatus):
        return value
    try:
        return TrackedPolicyCheckExecutionStatus(str(value).strip().lower())
    except ValueError as error:
        raise ValueError(f"Unsupported check execution status: {value}") from error
