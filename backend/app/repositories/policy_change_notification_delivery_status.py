"""Delivery lifecycle for policy-change email notifications."""

from enum import Enum

__all__ = [
    "PolicyChangeNotificationDeliveryStatus",
    "normalize_policy_change_notification_delivery_status",
]


class PolicyChangeNotificationDeliveryStatus(str, Enum):
    """Persisted notification delivery outcomes."""

    PENDING = "pending"
    SENT = "sent"
    FAILED = "failed"
    SUPPRESSED = "suppressed"


def normalize_policy_change_notification_delivery_status(
    value: PolicyChangeNotificationDeliveryStatus | str,
) -> PolicyChangeNotificationDeliveryStatus:
    if isinstance(value, PolicyChangeNotificationDeliveryStatus):
        return value
    return PolicyChangeNotificationDeliveryStatus(str(value).strip().lower())
