"""Authenticated notification preference routes."""

from fastapi import APIRouter, Depends

from ..deps import get_notification_preference_repository, get_request_subject
from ...schemas.notification_preferences import (
    NotificationPreferenceResponse,
    NotificationPreferenceUpdateRequest,
)
from ...services.request_subject import RequestSubject

router = APIRouter(prefix="/notification-preferences")


@router.get("", response_model=NotificationPreferenceResponse)
def get_notification_preferences(
    subject: RequestSubject = Depends(get_request_subject),
    preference_repository=Depends(get_notification_preference_repository),
) -> NotificationPreferenceResponse:
    """Return whether policy-change emails are enabled for the authenticated owner."""

    enabled = preference_repository.get_effective_policy_change_email_enabled(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
    )
    return NotificationPreferenceResponse(policy_change_email_enabled=enabled)


@router.patch("", response_model=NotificationPreferenceResponse)
def update_notification_preferences(
    payload: NotificationPreferenceUpdateRequest,
    subject: RequestSubject = Depends(get_request_subject),
    preference_repository=Depends(get_notification_preference_repository),
) -> NotificationPreferenceResponse:
    """Persist the policy-change email toggle for the authenticated owner."""

    preference_repository.upsert_policy_change_email_enabled(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        policy_change_email_enabled=payload.policy_change_email_enabled,
    )
    return NotificationPreferenceResponse(policy_change_email_enabled=payload.policy_change_email_enabled)
