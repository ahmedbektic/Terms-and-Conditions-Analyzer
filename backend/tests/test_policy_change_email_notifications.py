"""Tests for policy-change email notifications after successful tracked-policy checks."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID, uuid4

import pytest

from app.repositories.in_memory import (
    InMemoryNotificationPreferenceRepository,
    InMemoryPolicyChangeNotificationRepository,
    InMemoryStorage,
    InMemoryTrackedPolicyRepository,
)
from app.repositories.models import StoredTrackedPolicy
from app.repositories.policy_capture_status import PolicyCaptureStatus
from app.repositories.policy_change_notification_delivery_status import (
    PolicyChangeNotificationDeliveryStatus,
)
from app.repositories.policy_change_status import PolicyChangeStatus
from app.repositories.policy_tracking_status import PolicyTrackingStatus
from app.repositories.tracked_policy_check_execution_status import TrackedPolicyCheckExecutionStatus
from app.services.policy_change_email_notification_service import PolicyChangeEmailNotificationService
from app.services.policy_snapshot_service import PolicySnapshotCheckResult
from app.services.request_subject import RequestSubject
from app.services.tracked_policy_check_execution_service import TrackedPolicyCheckExecutionService


def _subject(*, email: str | None = "owner@example.com") -> RequestSubject:
    return RequestSubject(
        subject_type="supabase_user",
        subject_id="user-1",
        owner_email=email,
    )


def _tracked_policy_row() -> StoredTrackedPolicy:
    now = datetime.now(timezone.utc)
    return StoredTrackedPolicy(
        id=uuid4(),
        subject_type="supabase_user",
        subject_id="user-1",
        canonical_url="https://example.com/terms",
        display_name="Example Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=now,
        last_successful_capture_at=now,
        latest_capture_status=PolicyCaptureStatus.CAPTURED,
        latest_capture_message=None,
        latest_change_status=PolicyChangeStatus.UNCHANGED,
        latest_change_detected_at=None,
        active=True,
        created_at=now,
        snapshot_version_count=2,
    )


@pytest.fixture
def notification_storage() -> InMemoryStorage:
    return InMemoryStorage()


@pytest.fixture
def tracked_policy_repository(notification_storage: InMemoryStorage):
    return InMemoryTrackedPolicyRepository(notification_storage)


@pytest.fixture
def preference_repository(notification_storage: InMemoryStorage):
    return InMemoryNotificationPreferenceRepository(notification_storage)


@pytest.fixture
def notification_repository(notification_storage: InMemoryStorage):
    return InMemoryPolicyChangeNotificationRepository(notification_storage)


@dataclass
class RecordingMailer:
    messages: list[tuple[str, str, str]]
    fail_next: bool = False

    def send_plain_text(self, *, to_email: str, subject_line: str, body_text: str) -> None:
        if self.fail_next:
            self.fail_next = False
            raise RuntimeError("SMTP unavailable")
        self.messages.append((to_email, subject_line, body_text))


def _service(
    *,
    preference_repository,
    notification_repository,
    tracked_policy_repository,
    mailer: RecordingMailer,
    dashboard_base_url: str = "http://localhost:5173",
):
    return PolicyChangeEmailNotificationService(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=tracked_policy_repository,
        email_sender=mailer,
        dashboard_base_url=dashboard_base_url,
    )


def test_dispatch_skipped_without_meaningful_change_event(
    preference_repository,
    notification_repository,
    tracked_policy_repository,
):
    mailer = RecordingMailer(messages=[])
    service = _service(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=tracked_policy_repository,
        mailer=mailer,
    )
    tracked = _tracked_policy_row()

    service.dispatch_after_successful_check(
        subject=_subject(),
        tracked_policy=tracked,
        meaningful_change_event_id=None,
        snapshot_created=True,
    )

    assert mailer.messages == []


def test_dispatch_skipped_when_snapshot_not_created_even_if_uuid_provided(
    preference_repository,
    notification_repository,
    tracked_policy_repository,
):
    mailer = RecordingMailer(messages=[])
    service = _service(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=tracked_policy_repository,
        mailer=mailer,
    )
    tracked = _tracked_policy_row()

    service.dispatch_after_successful_check(
        subject=_subject(),
        tracked_policy=tracked,
        meaningful_change_event_id=uuid4(),
        snapshot_created=False,
    )

    assert mailer.messages == []


def test_dispatch_suppressed_when_preference_disabled(
    preference_repository,
    notification_repository,
    tracked_policy_repository,
):
    mailer = RecordingMailer(messages=[])
    service = _service(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=tracked_policy_repository,
        mailer=mailer,
    )
    pref_subject = _subject()
    preference_repository.upsert_policy_change_email_enabled(
        subject_type=pref_subject.subject_type,
        subject_id=pref_subject.subject_id,
        policy_change_email_enabled=False,
    )
    tracked = _tracked_policy_row()
    event_id = uuid4()

    service.dispatch_after_successful_check(
        subject=pref_subject,
        tracked_policy=tracked,
        meaningful_change_event_id=event_id,
        snapshot_created=True,
    )

    assert mailer.messages == []
    stored = notification_repository.get_by_change_event_id(policy_change_event_id=event_id)
    assert stored is not None
    assert stored.status == PolicyChangeNotificationDeliveryStatus.SUPPRESSED
    hist = notification_repository.list_status_history(notification_id=stored.id)
    assert [h.status for h in hist] == [PolicyChangeNotificationDeliveryStatus.SUPPRESSED]
    assert "preference_disabled" in (hist[0].detail or "").lower()


def test_dispatch_suppressed_when_missing_owner_email(
    preference_repository,
    notification_repository,
    tracked_policy_repository,
):
    mailer = RecordingMailer(messages=[])
    service = _service(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=tracked_policy_repository,
        mailer=mailer,
    )
    tracked = _tracked_policy_row()
    event_id = uuid4()

    service.dispatch_after_successful_check(
        subject=_subject(email=None),
        tracked_policy=tracked,
        meaningful_change_event_id=event_id,
        snapshot_created=True,
    )

    assert mailer.messages == []
    stored = notification_repository.get_by_change_event_id(policy_change_event_id=event_id)
    assert stored is not None
    assert stored.status == PolicyChangeNotificationDeliveryStatus.SUPPRESSED
    hist = notification_repository.list_status_history(notification_id=stored.id)
    assert "recipient" in (hist[0].detail or "").lower()


def test_dispatch_sends_email_and_records_sent_history(
    preference_repository,
    notification_repository,
    tracked_policy_repository,
):
    mailer = RecordingMailer(messages=[])
    service = _service(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=tracked_policy_repository,
        mailer=mailer,
        dashboard_base_url="http://localhost:5173",
    )
    tracked = _tracked_policy_row()
    event_id = uuid4()

    service.dispatch_after_successful_check(
        subject=_subject(email="hello@example.com"),
        tracked_policy=tracked,
        meaningful_change_event_id=event_id,
        snapshot_created=True,
    )

    assert len(mailer.messages) == 1
    to_email, subject_line, body = mailer.messages[0]
    assert to_email == "hello@example.com"
    assert "Example Terms" in subject_line
    assert tracked.display_name in body
    assert "localhost:5173" in body
    stored = notification_repository.get_by_change_event_id(policy_change_event_id=event_id)
    assert stored is not None
    assert stored.status == PolicyChangeNotificationDeliveryStatus.SENT
    hist = notification_repository.list_status_history(notification_id=stored.id)
    assert [h.status for h in hist] == [
        PolicyChangeNotificationDeliveryStatus.PENDING,
        PolicyChangeNotificationDeliveryStatus.SENT,
    ]


def test_dispatch_failure_records_failed_without_raising(
    preference_repository,
    notification_repository,
    tracked_policy_repository,
):
    mailer = RecordingMailer(messages=[], fail_next=True)
    service = _service(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=tracked_policy_repository,
        mailer=mailer,
    )
    tracked = _tracked_policy_row()
    event_id = uuid4()

    service.dispatch_after_successful_check(
        subject=_subject(),
        tracked_policy=tracked,
        meaningful_change_event_id=event_id,
        snapshot_created=True,
    )

    stored = notification_repository.get_by_change_event_id(policy_change_event_id=event_id)
    assert stored is not None
    assert stored.status == PolicyChangeNotificationDeliveryStatus.FAILED
    hist = notification_repository.list_status_history(notification_id=stored.id)
    assert hist[-1].status == PolicyChangeNotificationDeliveryStatus.FAILED


def test_dispatch_duplicate_change_event_is_idempotent(
    preference_repository,
    notification_repository,
    tracked_policy_repository,
):
    mailer = RecordingMailer(messages=[])
    service = _service(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=tracked_policy_repository,
        mailer=mailer,
    )
    tracked = _tracked_policy_row()
    event_id = uuid4()

    service.dispatch_after_successful_check(
        subject=_subject(),
        tracked_policy=tracked,
        meaningful_change_event_id=event_id,
        snapshot_created=True,
    )
    service.dispatch_after_successful_check(
        subject=_subject(),
        tracked_policy=tracked,
        meaningful_change_event_id=event_id,
        snapshot_created=True,
    )

    assert len(mailer.messages) == 1
    assert notification_repository.count_notifications() == 1


def test_retry_failed_dispatch_attempts_send_again(
    preference_repository,
    notification_repository,
    exec_deps,
):
    mailer = RecordingMailer(messages=[], fail_next=True)
    service = PolicyChangeEmailNotificationService(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=exec_deps["tracked_repo"],
        email_sender=mailer,
        dashboard_base_url="http://localhost:5173",
    )
    tracked = exec_deps["tracked"]
    event_id = uuid4()

    service.dispatch_after_successful_check(
        subject=_subject(),
        tracked_policy=tracked,
        meaningful_change_event_id=event_id,
        snapshot_created=True,
    )

    n = notification_repository.get_by_change_event_id(policy_change_event_id=event_id)
    assert n is not None

    service.retry_failed_delivery(notification_id=n.id)

    stored = notification_repository.get_by_change_event_id(policy_change_event_id=event_id)
    assert stored is not None
    assert stored.status == PolicyChangeNotificationDeliveryStatus.SENT
    assert len(mailer.messages) == 1


class _StubSnapshotServiceForNotifications:
    def __init__(self, *, result: PolicySnapshotCheckResult):
        self._result = result
        self.calls: list[tuple[RequestSubject, UUID]] = []

    def check_tracked_policy(self, *, subject: RequestSubject, tracked_policy_id: UUID):
        self.calls.append((subject, tracked_policy_id))
        return self._result


@pytest.fixture
def exec_deps(notification_storage):
    from app.repositories.in_memory import (
        InMemoryTrackedPolicyCheckExecutionRepository,
        InMemoryTrackedPolicyRepository,
    )

    tracked_repo = InMemoryTrackedPolicyRepository(notification_storage)
    exec_repo = InMemoryTrackedPolicyCheckExecutionRepository(notification_storage)
    subject = _subject()
    tracked = tracked_repo.create(
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
        canonical_url="https://example.com/terms",
        display_name="Example Terms",
        source_type="url",
        tracking_status=PolicyTrackingStatus.ACTIVE,
        last_checked_at=None,
        active=True,
    )
    return {
        "tracked_repo": tracked_repo,
        "exec_repo": exec_repo,
        "subject": subject,
        "tracked": tracked,
    }


def test_execute_check_passes_change_event_id_to_completed_execution(
    exec_deps,
    preference_repository,
    notification_repository,
):
    mailer = RecordingMailer(messages=[])
    notifier = PolicyChangeEmailNotificationService(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=exec_deps["tracked_repo"],
        email_sender=mailer,
        dashboard_base_url="http://localhost:5173",
    )
    change_event_id = uuid4()
    snapshot_service = _StubSnapshotServiceForNotifications(
        result=PolicySnapshotCheckResult(
            tracked_policy=exec_deps["tracked"],
            snapshot_created=True,
            meaningful_change_event_id=change_event_id,
        )
    )
    execution_service = TrackedPolicyCheckExecutionService(
        tracked_policy_repository=exec_deps["tracked_repo"],
        check_execution_repository=exec_deps["exec_repo"],
        policy_snapshot_service=snapshot_service,
        policy_change_notification_service=notifier,
    )

    result = execution_service.execute_check(
        subject=exec_deps["subject"],
        tracked_policy_id=exec_deps["tracked"].id,
    )

    assert result.execution.status == TrackedPolicyCheckExecutionStatus.SUCCEEDED
    assert result.execution.result_change_event_id == change_event_id
    assert len(mailer.messages) == 1


def test_execute_check_swallows_notification_delivery_failure(
    exec_deps,
    preference_repository,
    notification_repository,
):
    mailer = RecordingMailer(messages=[], fail_next=True)
    notifier = PolicyChangeEmailNotificationService(
        preference_repository=preference_repository,
        notification_repository=notification_repository,
        tracked_policy_repository=exec_deps["tracked_repo"],
        email_sender=mailer,
        dashboard_base_url="http://localhost:5173",
    )
    change_event_id = uuid4()
    snapshot_service = _StubSnapshotServiceForNotifications(
        result=PolicySnapshotCheckResult(
            tracked_policy=exec_deps["tracked"],
            snapshot_created=True,
            meaningful_change_event_id=change_event_id,
        )
    )
    execution_service = TrackedPolicyCheckExecutionService(
        tracked_policy_repository=exec_deps["tracked_repo"],
        check_execution_repository=exec_deps["exec_repo"],
        policy_snapshot_service=snapshot_service,
        policy_change_notification_service=notifier,
    )

    result = execution_service.execute_check(
        subject=exec_deps["subject"],
        tracked_policy_id=exec_deps["tracked"].id,
    )

    assert result.execution.status == TrackedPolicyCheckExecutionStatus.SUCCEEDED
    stored = notification_repository.get_by_change_event_id(policy_change_event_id=change_event_id)
    assert stored is not None
    assert stored.status == PolicyChangeNotificationDeliveryStatus.FAILED
