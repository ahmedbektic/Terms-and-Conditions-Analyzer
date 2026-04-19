"""Change-detection enums shared by tracked-policy persistence and services."""

from enum import Enum

__all__ = [
    "PolicyChangeStatus",
    "normalize_policy_change_status",
]


class PolicyChangeStatus(str, Enum):
    """Latest tracked-policy change-detection state."""

    NOT_EVALUATED = "not_evaluated"
    UNCHANGED = "unchanged"
    UPDATED = "updated"
    COMPARISON_INCOMPLETE = "comparison_incomplete"


def normalize_policy_change_status(value: PolicyChangeStatus | str) -> PolicyChangeStatus:
    """Normalize change-detection status values."""

    if isinstance(value, PolicyChangeStatus):
        return value
    return PolicyChangeStatus(str(value).strip().lower())
