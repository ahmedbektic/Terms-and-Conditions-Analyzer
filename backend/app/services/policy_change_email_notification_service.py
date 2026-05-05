"""Owner email alerts after meaningful tracked-policy content updates."""

from __future__ import annotations

import logging
from typing import Protocol
from uuid import UUID

from ..repositories.interfaces import (
    NotificationPreferenceRepository,
    PolicyChangeNotificationRepository,
    TrackedPolicyRepository,
)
from ..repositories.models import StoredTrackedPolicy
from ..repositories.policy_change_notification_delivery_status import (
    PolicyChangeNotificationDeliveryStatus,
)
from .request_subject import RequestSubject

logger = logging.getLogger(__name__)


class PlainTextEmailSender(Protocol):
    """Minimal outbound mail boundary used by policy-change notifications."""

    def send_plain_text(self, *, to_email: str, subject_line: str, body_text: str) -> None: ...


class LoggingPlainTextEmailSender:
    """Development-safe sender that records intent via structured logs."""

    def send_plain_text(self, *, to_email: str, subject_line: str, body_text: str) -> None:
        logger.info(
            "policy_change_email_dispatch",
            extra={
                "email_to": to_email,
                "email_subject": subject_line,
                "email_body_chars": len(body_text),
            },
        )


class PolicyChangeEmailNotificationService:
    """Persist notification lifecycle rows and attempt plain-text delivery."""

    def __init__(
        self,
        *,
        preference_repository: NotificationPreferenceRepository,
        notification_repository: PolicyChangeNotificationRepository,
        tracked_policy_repository: TrackedPolicyRepository,
        email_sender: PlainTextEmailSender,
        dashboard_base_url: str,
    ) -> None:
        self._preference_repository = preference_repository
        self._notification_repository = notification_repository
        self._tracked_policy_repository = tracked_policy_repository
        self._email_sender = email_sender
        base = dashboard_base_url.strip().rstrip("/")
        self._dashboard_base_url = base

    def dispatch_after_successful_check(
        self,
        *,
        subject: RequestSubject,
        tracked_policy: StoredTrackedPolicy,
        meaningful_change_event_id: UUID | None,
        snapshot_created: bool,
    ) -> None:
        if meaningful_change_event_id is None or not snapshot_created:
            return

        already = self._notification_repository.get_by_change_event_id(
            policy_change_event_id=meaningful_change_event_id
        )
        if already is not None:
            return

        pref_ok = self._preference_repository.get_effective_policy_change_email_enabled(
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )
        if not pref_ok:
            self._notification_repository.create_notification(
                policy_change_event_id=meaningful_change_event_id,
                tracked_policy_id=tracked_policy.id,
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
                recipient_email=None,
                initial_status=PolicyChangeNotificationDeliveryStatus.SUPPRESSED,
                initial_detail="preference_disabled_policy_change_emails",
            )
            return

        recipient = (subject.owner_email or "").strip() or None
        if recipient is None:
            self._notification_repository.create_notification(
                policy_change_event_id=meaningful_change_event_id,
                tracked_policy_id=tracked_policy.id,
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
                recipient_email=None,
                initial_status=PolicyChangeNotificationDeliveryStatus.SUPPRESSED,
                initial_detail="missing_recipient_email",
            )
            return

        notification = self._notification_repository.create_notification(
            policy_change_event_id=meaningful_change_event_id,
            tracked_policy_id=tracked_policy.id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            recipient_email=recipient,
            initial_status=PolicyChangeNotificationDeliveryStatus.PENDING,
            initial_detail=None,
        )

        subject_line, body_text = self._render_email(tracked_policy=tracked_policy)
        try:
            self._email_sender.send_plain_text(
                to_email=recipient,
                subject_line=subject_line,
                body_text=body_text,
            )
            self._notification_repository.transition_status(
                notification_id=notification.id,
                status=PolicyChangeNotificationDeliveryStatus.SENT,
                detail=None,
            )
        except Exception as exc:
            logger.warning(
                "policy_change_email_send_failed",
                extra={
                    "notification_id": str(notification.id),
                    "tracked_policy_id": str(tracked_policy.id),
                    "policy_change_event_id": str(meaningful_change_event_id),
                },
                exc_info=True,
            )
            self._notification_repository.transition_status(
                notification_id=notification.id,
                status=PolicyChangeNotificationDeliveryStatus.FAILED,
                detail=str(exc),
            )

    def retry_failed_delivery(self, *, notification_id: UUID) -> None:
        notification = self._notification_repository.get_by_id(notification_id=notification_id)
        if notification is None or notification.status != PolicyChangeNotificationDeliveryStatus.FAILED:
            return

        recipient = (notification.recipient_email or "").strip() or None
        if recipient is None:
            return

        updated = self._notification_repository.transition_status(
            notification_id=notification_id,
            status=PolicyChangeNotificationDeliveryStatus.PENDING,
            detail="retry",
        )
        if updated is None:
            return

        tracked_policy = self._tracked_policy_repository.get_active_for_subject(
            tracked_policy_id=notification.tracked_policy_id,
            subject_type=notification.subject_type,
            subject_id=notification.subject_id,
        )
        if tracked_policy is None:
            subject_line = "Policy update detected"
            dashboard_link = f"{self._dashboard_base_url}/"
            body_text = (
                "We detected a meaningful policy update on your watchlist.\n\n"
                f"Open your dashboard for details:\n{dashboard_link}\n"
            )
        else:
            subject_line, body_text = self._render_email(tracked_policy=tracked_policy)
        try:
            self._email_sender.send_plain_text(
                to_email=recipient,
                subject_line=subject_line,
                body_text=body_text,
            )
            self._notification_repository.transition_status(
                notification_id=notification_id,
                status=PolicyChangeNotificationDeliveryStatus.SENT,
                detail=None,
            )
        except Exception as exc:
            logger.warning(
                "policy_change_email_retry_failed",
                extra={"notification_id": str(notification_id)},
                exc_info=True,
            )
            self._notification_repository.transition_status(
                notification_id=notification_id,
                status=PolicyChangeNotificationDeliveryStatus.FAILED,
                detail=str(exc),
            )

    def _render_email(self, *, tracked_policy: StoredTrackedPolicy) -> tuple[str, str]:
        dashboard_link = f"{self._dashboard_base_url}/"
        subject_line = f"Policy update detected: {tracked_policy.display_name}"
        body_text = (
            f"We detected a meaningful update to {tracked_policy.display_name} "
            f"({tracked_policy.canonical_url}).\n\n"
            "Open your dashboard for comparison details and the captured snapshot timeline:\n"
            f"{dashboard_link}\n"
        )
        return subject_line, body_text
