"""Internal tracked-policy lifecycle status model.

These values describe watchlist registration and later background-processing
state. The current story only persists `pending_first_snapshot`, but the enum
already reserves future states so the transport and persistence seams do not
need churn when snapshot processing is added.
"""

from enum import Enum


class PolicyTrackingStatus(str, Enum):
    """Lifecycle states for tracked-policy rows."""

    PENDING_FIRST_SNAPSHOT = "pending_first_snapshot"
    ACTIVE = "active"
    INVALID_SOURCE = "invalid_source"


def normalize_policy_tracking_status(value: PolicyTrackingStatus | str) -> PolicyTrackingStatus:
    """Return a normalized tracking status enum or raise for unknown values."""

    if isinstance(value, PolicyTrackingStatus):
        return value
    try:
        return PolicyTrackingStatus(str(value))
    except ValueError as error:
        raise ValueError(f"Unsupported policy tracking status: {value}") from error
