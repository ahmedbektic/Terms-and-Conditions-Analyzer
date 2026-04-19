"""Capture-status enums shared by tracked-policy and snapshot persistence."""

from enum import Enum

__all__ = [
    "PolicyCaptureStatus",
    "PolicySnapshotStatus",
    "normalize_policy_capture_status",
    "normalize_policy_snapshot_status",
]


class PolicyCaptureStatus(str, Enum):
    """Latest tracked-policy capture outcome."""

    NEVER_CAPTURED = "never_captured"
    CAPTURED = "captured"
    CAPTURE_FAILED = "capture_failed"


class PolicySnapshotStatus(str, Enum):
    """Persisted snapshot capture status."""

    CAPTURED = "captured"
    CAPTURE_FAILED = "capture_failed"


def normalize_policy_capture_status(value: PolicyCaptureStatus | str) -> PolicyCaptureStatus:
    """Normalize tracked-policy capture status values."""

    if isinstance(value, PolicyCaptureStatus):
        return value
    return PolicyCaptureStatus(str(value).strip().lower())


def normalize_policy_snapshot_status(value: PolicySnapshotStatus | str) -> PolicySnapshotStatus:
    """Normalize snapshot capture status values."""

    if isinstance(value, PolicySnapshotStatus):
        return value
    return PolicySnapshotStatus(str(value).strip().lower())
