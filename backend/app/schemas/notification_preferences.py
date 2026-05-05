"""HTTP schemas for notification preference endpoints."""

from pydantic import BaseModel


class NotificationPreferenceResponse(BaseModel):
    """Effective preference payload returned to dashboard callers."""

    policy_change_email_enabled: bool


class NotificationPreferenceUpdateRequest(BaseModel):
    """Update payload for the policy-change email preference flag."""

    policy_change_email_enabled: bool
