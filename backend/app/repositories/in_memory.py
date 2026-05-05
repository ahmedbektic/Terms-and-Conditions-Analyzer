"""In-memory repository implementation used for local MVP wiring before DB integration.

This module mirrors the repository contracts so the service and route layers stay stable
when a Supabase/Postgres implementation is introduced.
"""

from datetime import datetime, timezone
from dataclasses import replace
from uuid import UUID, uuid4

from .analysis_status import AnalysisLifecycleStatus, normalize_analysis_lifecycle_status
from .errors import ActiveTrackedPolicyCheckExecutionConflictError
from .models import (
    PolicyChangeEventCreateInput,
    PolicySnapshotAppendResult,
    PolicySnapshotCreateInput,
    StoredAgreement,
    StoredFlaggedClause,
    StoredNotificationPreference,
    StoredPolicyChangeEvent,
    StoredPolicyChangeNotification,
    StoredPolicyChangeNotificationStatusEvent,
    StoredPolicySnapshot,
    StoredReport,
    StoredTrackedPolicy,
    StoredTrackedPolicyCheckExecution,
)
from .policy_capture_status import (
    PolicyCaptureStatus,
    PolicySnapshotStatus,
    normalize_policy_capture_status,
    normalize_policy_snapshot_status,
)
from .policy_change_notification_delivery_status import (
    PolicyChangeNotificationDeliveryStatus,
    normalize_policy_change_notification_delivery_status,
)
from .policy_change_status import PolicyChangeStatus, normalize_policy_change_status
from .policy_snapshot_hash import build_policy_snapshot_content_hash
from .policy_tracking_status import PolicyTrackingStatus, normalize_policy_tracking_status
from .report_capture_kind import (
    ReportContentCaptureKind,
    normalize_report_content_capture_kind,
)
from .tracked_policy_check_execution_status import (
    TrackedPolicyCheckExecutionStatus,
    is_active_execution_status,
)


class InMemoryStorage:
    """Simple in-process storage container for local development and tests."""

    def __init__(self) -> None:
        self.agreements: dict[UUID, StoredAgreement] = {}
        self.reports: dict[UUID, StoredReport] = {}
        self.tracked_policies: dict[UUID, StoredTrackedPolicy] = {}
        self.policy_snapshots: dict[UUID, list[StoredPolicySnapshot]] = {}
        self.policy_change_events: dict[UUID, list[StoredPolicyChangeEvent]] = {}
        self.check_executions: dict[UUID, StoredTrackedPolicyCheckExecution] = {}
        self.notification_preferences: dict[tuple[str, str], StoredNotificationPreference] = {}
        self.policy_change_notifications: dict[UUID, StoredPolicyChangeNotification] = {}
        self.policy_change_notifications_by_event: dict[UUID, UUID] = {}
        self.policy_change_notification_status_events: dict[UUID, list[StoredPolicyChangeNotificationStatusEvent]] = {}

    def clear(self) -> None:
        self.agreements.clear()
        self.reports.clear()
        self.tracked_policies.clear()
        self.policy_snapshots.clear()
        self.policy_change_events.clear()
        self.check_executions.clear()
        self.notification_preferences.clear()
        self.policy_change_notifications.clear()
        self.policy_change_notifications_by_event.clear()
        self.policy_change_notification_status_events.clear()


class InMemoryAgreementRepository:
    """In-memory agreement repository implementation."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._storage = storage

    def create(
        self,
        *,
        subject_type: str,
        subject_id: str,
        title: str | None,
        source_url: str | None,
        agreed_at: datetime | None,
        terms_text: str,
    ) -> StoredAgreement:
        agreement = StoredAgreement(
            id=uuid4(),
            subject_type=subject_type,
            subject_id=subject_id,
            title=title,
            source_url=source_url,
            agreed_at=agreed_at,
            terms_text=terms_text,
            created_at=datetime.now(timezone.utc),
        )
        self._storage.agreements[agreement.id] = agreement
        return agreement

    def get_for_subject(
        self,
        *,
        agreement_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredAgreement | None:
        agreement = self._storage.agreements.get(agreement_id)
        if agreement is None:
            return None
        if agreement.subject_type != subject_type or agreement.subject_id != subject_id:
            return None
        return agreement


class InMemoryReportRepository:
    """In-memory report repository implementation."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._storage = storage

    def create(
        self,
        *,
        agreement_id: UUID,
        subject_type: str,
        subject_id: str,
        source_type: str,
        source_value: str,
        raw_input_excerpt: str,
        status: AnalysisLifecycleStatus,
        summary: str,
        trust_score: int,
        model_name: str,
        flagged_clauses: list[StoredFlaggedClause],
        completed_at: datetime | None,
        canonical_source_url: str | None = None,
        content_capture_kind: ReportContentCaptureKind | str = (
            ReportContentCaptureKind.LEGACY_UNKNOWN
        ),
        tracked_policy_id: UUID | None = None,
        tracked_policy_snapshot_id: UUID | None = None,
        tracked_policy_version_number: int | None = None,
    ) -> StoredReport:
        normalized_status = normalize_analysis_lifecycle_status(status)
        normalized_capture_kind = normalize_report_content_capture_kind(content_capture_kind)
        report = StoredReport(
            id=uuid4(),
            agreement_id=agreement_id,
            subject_type=subject_type,
            subject_id=subject_id,
            source_type=source_type,
            source_value=source_value,
            raw_input_excerpt=raw_input_excerpt,
            status=normalized_status,
            summary=summary,
            trust_score=trust_score,
            model_name=model_name,
            flagged_clauses=flagged_clauses,
            created_at=datetime.now(timezone.utc),
            completed_at=completed_at,
            canonical_source_url=canonical_source_url,
            content_capture_kind=normalized_capture_kind,
            tracked_policy_id=tracked_policy_id,
            tracked_policy_snapshot_id=tracked_policy_snapshot_id,
            tracked_policy_version_number=tracked_policy_version_number,
        )
        self._storage.reports[report.id] = report
        return report

    def list_for_subject(self, *, subject_type: str, subject_id: str) -> list[StoredReport]:
        reports = [
            report
            for report in self._storage.reports.values()
            if report.subject_type == subject_type and report.subject_id == subject_id
        ]
        return self._sort_reports_newest_first(reports)

    def get_for_subject(
        self,
        *,
        report_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredReport | None:
        report = self._storage.reports.get(report_id)
        if report is None:
            return None
        if report.subject_type != subject_type or report.subject_id != subject_id:
            return None
        return report

    def get_latest_eligible_baseline_report_for_subject(
        self,
        *,
        canonical_source_url: str,
        subject_type: str,
        subject_id: str,
    ) -> StoredReport | None:
        eligible_reports = [
            report
            for report in self._storage.reports.values()
            if report.subject_type == subject_type
            and report.subject_id == subject_id
            and report.canonical_source_url == canonical_source_url
            and report.content_capture_kind == ReportContentCaptureKind.FETCHED_URL
        ]
        if not eligible_reports:
            return None
        return self._sort_reports_newest_first(eligible_reports)[0]

    def _sort_reports_newest_first(self, reports: list[StoredReport]) -> list[StoredReport]:
        indexed_reports = list(enumerate(reports))
        return [
            report
            for _, report in sorted(
                indexed_reports,
                key=lambda item: (item[1].created_at, item[0]),
                reverse=True,
            )
        ]


class InMemoryTrackedPolicyRepository:
    """In-memory tracked-policy repository implementation."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._storage = storage

    def create(
        self,
        *,
        subject_type: str,
        subject_id: str,
        canonical_url: str,
        display_name: str,
        source_type: str,
        tracking_status: PolicyTrackingStatus,
        last_checked_at: datetime | None,
        active: bool = True,
    ) -> StoredTrackedPolicy:
        tracked_policy = StoredTrackedPolicy(
            id=uuid4(),
            subject_type=subject_type,
            subject_id=subject_id,
            canonical_url=canonical_url,
            display_name=display_name,
            source_type=source_type,
            tracking_status=normalize_policy_tracking_status(tracking_status),
            last_checked_at=last_checked_at,
            last_successful_capture_at=None,
            latest_capture_status=PolicyCaptureStatus.NEVER_CAPTURED,
            latest_capture_message=None,
            latest_change_status=PolicyChangeStatus.NOT_EVALUATED,
            latest_change_detected_at=None,
            active=active,
            created_at=datetime.now(timezone.utc),
            snapshot_version_count=0,
        )
        self._storage.tracked_policies[tracked_policy.id] = tracked_policy
        return tracked_policy

    def list_active_for_subject(
        self, *, subject_type: str, subject_id: str
    ) -> list[StoredTrackedPolicy]:
        tracked_policies = [
            tracked_policy
            for tracked_policy in self._storage.tracked_policies.values()
            if tracked_policy.subject_type == subject_type
            and tracked_policy.subject_id == subject_id
            and tracked_policy.active
        ]
        return sorted(
            (self._hydrate_tracked_policy(tracked_policy) for tracked_policy in tracked_policies),
            key=lambda tracked_policy: tracked_policy.created_at,
            reverse=True,
        )

    def get_active_for_subject(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None:
        tracked_policy = self._storage.tracked_policies.get(tracked_policy_id)
        if tracked_policy is None or not tracked_policy.active:
            return None
        if tracked_policy.subject_type != subject_type or tracked_policy.subject_id != subject_id:
            return None
        return self._hydrate_tracked_policy(tracked_policy)

    def get_active_by_canonical_url_for_subject(
        self,
        *,
        canonical_url: str,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None:
        for tracked_policy in self._storage.tracked_policies.values():
            if (
                tracked_policy.subject_type == subject_type
                and tracked_policy.subject_id == subject_id
                and tracked_policy.canonical_url == canonical_url
                and tracked_policy.active
            ):
                return self._hydrate_tracked_policy(tracked_policy)
        return None

    def deactivate_for_subject(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None:
        tracked_policy = self.get_active_for_subject(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        if tracked_policy is None:
            return None
        hydrated_policy = self._hydrate_tracked_policy(tracked_policy)
        deactivated_policy = replace(hydrated_policy, active=False)
        self._storage.tracked_policies[tracked_policy_id] = deactivated_policy
        return deactivated_policy

    def update_tracked_policy_check_state(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
        last_checked_at: datetime,
        tracking_status: PolicyTrackingStatus,
        latest_capture_status: PolicyCaptureStatus,
        latest_capture_message: str | None,
        latest_change_status: PolicyChangeStatus,
        latest_change_detected_at: datetime | None,
    ) -> StoredTrackedPolicy | None:
        tracked_policy = self.get_active_for_subject(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        if tracked_policy is None:
            return None
        last_successful_capture_at = tracked_policy.last_successful_capture_at
        normalized_capture_status = normalize_policy_capture_status(latest_capture_status)
        if normalized_capture_status == PolicyCaptureStatus.CAPTURED:
            latest_snapshot = self._get_latest_snapshot(tracked_policy_id)
            last_successful_capture_at = (
                latest_snapshot.captured_at
                if latest_snapshot is not None
                else last_successful_capture_at
            )
        updated = replace(
            tracked_policy,
            last_checked_at=last_checked_at,
            tracking_status=normalize_policy_tracking_status(tracking_status),
            last_successful_capture_at=last_successful_capture_at,
            latest_capture_status=normalized_capture_status,
            latest_capture_message=latest_capture_message,
            latest_change_status=normalize_policy_change_status(latest_change_status),
            latest_change_detected_at=latest_change_detected_at,
        )
        self._storage.tracked_policies[tracked_policy_id] = updated
        return self._hydrate_tracked_policy(updated)

    def _get_latest_snapshot(self, tracked_policy_id: UUID) -> StoredPolicySnapshot | None:
        snapshots = self._storage.policy_snapshots.get(tracked_policy_id, [])
        if not snapshots:
            return None
        return snapshots[-1]

    def _get_last_successful_capture_at(self, tracked_policy_id: UUID) -> datetime | None:
        for snapshot in reversed(self._storage.policy_snapshots.get(tracked_policy_id, [])):
            if snapshot.capture_status == PolicySnapshotStatus.CAPTURED:
                return snapshot.captured_at
        return None

    def _hydrate_tracked_policy(self, tracked_policy: StoredTrackedPolicy) -> StoredTrackedPolicy:
        snapshots = self._storage.policy_snapshots.get(tracked_policy.id, [])
        return replace(
            tracked_policy,
            snapshot_version_count=len(snapshots),
            last_successful_capture_at=self._get_last_successful_capture_at(tracked_policy.id),
        )


class InMemoryPolicySnapshotRepository:
    """In-memory tracked-policy snapshot repository implementation."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._storage = storage

    def append_for_tracked_policy_if_changed(
        self,
        *,
        tracked_policy_id: UUID,
        snapshot: PolicySnapshotCreateInput,
    ) -> PolicySnapshotAppendResult:
        normalized_status = normalize_policy_snapshot_status(snapshot.capture_status)
        content_hash = build_policy_snapshot_content_hash(snapshot.normalized_text_body)
        stored_snapshots = self._storage.policy_snapshots.setdefault(tracked_policy_id, [])
        latest_snapshot = stored_snapshots[-1] if stored_snapshots else None
        if (
            latest_snapshot is not None
            and latest_snapshot.capture_status == PolicySnapshotStatus.CAPTURED
            and latest_snapshot.content_hash == content_hash
            and latest_snapshot.normalized_text_body == snapshot.normalized_text_body
        ):
            return PolicySnapshotAppendResult(snapshot=latest_snapshot, created=False)

        stored_snapshot = StoredPolicySnapshot(
            id=uuid4(),
            tracked_policy_id=tracked_policy_id,
            raw_text_body=snapshot.raw_text_body,
            normalized_text_body=snapshot.normalized_text_body,
            content_hash=content_hash,
            captured_at=snapshot.captured_at,
            capture_status=normalized_status,
            source_url=snapshot.source_url,
            final_url=snapshot.final_url,
            http_status=snapshot.http_status,
            redirect_count=snapshot.redirect_count,
            fetch_duration_ms=snapshot.fetch_duration_ms,
            extractor_name=snapshot.extractor_name,
            extraction_strategy=snapshot.extraction_strategy,
            capture_error_message=snapshot.capture_error_message,
            normalization_version=snapshot.normalization_version,
        )
        stored_snapshots.append(stored_snapshot)
        return PolicySnapshotAppendResult(snapshot=stored_snapshot, created=True)

    def get_latest_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
    ) -> StoredPolicySnapshot | None:
        snapshots = self._storage.policy_snapshots.get(tracked_policy_id, [])
        if not snapshots:
            return None
        return snapshots[-1]

    def list_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
    ) -> list[StoredPolicySnapshot]:
        snapshots = self._storage.policy_snapshots.get(tracked_policy_id, [])
        return list(reversed(snapshots))

    def delete_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
        snapshot_id: UUID,
    ) -> bool:
        snapshots = self._storage.policy_snapshots.get(tracked_policy_id, [])
        for index, snapshot in enumerate(snapshots):
            if snapshot.id == snapshot_id:
                del snapshots[index]
                return True
        return False


class InMemoryPolicyChangeEventRepository:
    """In-memory tracked-policy change-event repository implementation."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._storage = storage

    def create(self, *, event: PolicyChangeEventCreateInput) -> StoredPolicyChangeEvent:
        stored_event = StoredPolicyChangeEvent(
            id=uuid4(),
            tracked_policy_id=event.tracked_policy_id,
            previous_snapshot_id=event.previous_snapshot_id,
            new_snapshot_id=event.new_snapshot_id,
            detected_at=event.detected_at,
            change_status=normalize_policy_change_status(event.change_status),
            detection_method=event.detection_method,
            content_changed=event.content_changed,
            previous_section_count=event.previous_section_count,
            new_section_count=event.new_section_count,
            section_delta=event.section_delta,
        )
        stored_events = self._storage.policy_change_events.setdefault(event.tracked_policy_id, [])
        stored_events.append(stored_event)
        return stored_event

    def get_latest_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
    ) -> StoredPolicyChangeEvent | None:
        events = self._storage.policy_change_events.get(tracked_policy_id, [])
        if not events:
            return None
        return events[-1]

    def list_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
    ) -> list[StoredPolicyChangeEvent]:
        events = self._storage.policy_change_events.get(tracked_policy_id, [])
        return list(reversed(events))


class InMemoryTrackedPolicyCheckExecutionRepository:
    """In-memory implementation of tracked-policy check execution persistence."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._storage = storage

    def create(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicyCheckExecution:
        existing_active_execution = self.get_active_for_tracked_policy(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        if existing_active_execution is not None:
            raise ActiveTrackedPolicyCheckExecutionConflictError(
                "An active tracked-policy check execution already exists for this policy."
            )

        now = datetime.now(timezone.utc)
        execution = StoredTrackedPolicyCheckExecution(
            id=uuid4(),
            tracked_policy_id=tracked_policy_id,
            subject_type=subject_type,
            subject_id=subject_id,
            status=TrackedPolicyCheckExecutionStatus.PENDING,
            created_at=now,
            started_at=None,
            completed_at=None,
            failure_code=None,
            failure_stage=None,
            failure_message=None,
            failure_retryable=None,
            result_snapshot_created=None,
            result_previous_snapshot_id=None,
            result_new_snapshot_id=None,
            result_change_event_id=None,
        )
        self._storage.check_executions[execution.id] = execution
        return execution

    def get_by_id(
        self,
        *,
        execution_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicyCheckExecution | None:
        execution = self._storage.check_executions.get(execution_id)
        if execution is None:
            return None
        if execution.subject_type != subject_type or execution.subject_id != subject_id:
            return None
        return execution

    def get_active_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicyCheckExecution | None:
        for execution in self._storage.check_executions.values():
            if (
                execution.tracked_policy_id == tracked_policy_id
                and execution.subject_type == subject_type
                and execution.subject_id == subject_id
                and is_active_execution_status(execution.status)
            ):
                return execution
        return None

    def mark_running(
        self,
        *,
        execution_id: UUID,
    ) -> StoredTrackedPolicyCheckExecution | None:
        execution = self._storage.check_executions.get(execution_id)
        if execution is None:
            return None
        if execution.status != TrackedPolicyCheckExecutionStatus.PENDING:
            return None
        updated = replace(
            execution,
            status=TrackedPolicyCheckExecutionStatus.RUNNING,
            started_at=datetime.now(timezone.utc),
        )
        self._storage.check_executions[execution_id] = updated
        return updated

    def mark_completed(
        self,
        *,
        execution_id: UUID,
        status: TrackedPolicyCheckExecutionStatus,
        failure_code: str | None = None,
        failure_stage: str | None = None,
        failure_message: str | None = None,
        failure_retryable: bool | None = None,
        result_snapshot_created: bool | None = None,
        result_previous_snapshot_id: UUID | None = None,
        result_new_snapshot_id: UUID | None = None,
        result_change_event_id: UUID | None = None,
    ) -> StoredTrackedPolicyCheckExecution | None:
        execution = self._storage.check_executions.get(execution_id)
        if execution is None:
            return None
        if not is_active_execution_status(execution.status):
            return None
        now = datetime.now(timezone.utc)
        updated = replace(
            execution,
            status=status,
            started_at=execution.started_at or now,
            completed_at=now,
            failure_code=failure_code,
            failure_stage=failure_stage,
            failure_message=failure_message,
            failure_retryable=failure_retryable,
            result_snapshot_created=result_snapshot_created,
            result_previous_snapshot_id=result_previous_snapshot_id,
            result_new_snapshot_id=result_new_snapshot_id,
            result_change_event_id=result_change_event_id,
        )
        self._storage.check_executions[execution_id] = updated
        return updated


class InMemoryNotificationPreferenceRepository:
    """In-memory notification preference persistence."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._storage = storage

    def get_effective_policy_change_email_enabled(
        self,
        *,
        subject_type: str,
        subject_id: str,
    ) -> bool:
        row = self._storage.notification_preferences.get((subject_type, subject_id))
        if row is None:
            return True
        return row.policy_change_email_enabled

    def upsert_policy_change_email_enabled(
        self,
        *,
        subject_type: str,
        subject_id: str,
        policy_change_email_enabled: bool,
    ) -> StoredNotificationPreference:
        now = datetime.now(timezone.utc)
        stored = StoredNotificationPreference(
            subject_type=subject_type,
            subject_id=subject_id,
            policy_change_email_enabled=policy_change_email_enabled,
            updated_at=now,
        )
        self._storage.notification_preferences[(subject_type, subject_id)] = stored
        return stored


class InMemoryPolicyChangeNotificationRepository:
    """In-memory notification rows and append-only status history."""

    def __init__(self, storage: InMemoryStorage) -> None:
        self._storage = storage

    def count_notifications(self) -> int:
        return len(self._storage.policy_change_notifications)

    def get_by_change_event_id(
        self,
        *,
        policy_change_event_id: UUID,
    ) -> StoredPolicyChangeNotification | None:
        notification_id = self._storage.policy_change_notifications_by_event.get(
            policy_change_event_id
        )
        if notification_id is None:
            return None
        return self._storage.policy_change_notifications.get(notification_id)

    def get_by_id(self, *, notification_id: UUID) -> StoredPolicyChangeNotification | None:
        return self._storage.policy_change_notifications.get(notification_id)

    def create_notification(
        self,
        *,
        policy_change_event_id: UUID,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
        recipient_email: str | None,
        initial_status: PolicyChangeNotificationDeliveryStatus,
        initial_detail: str | None,
    ) -> StoredPolicyChangeNotification:
        if policy_change_event_id in self._storage.policy_change_notifications_by_event:
            raise ValueError("Notification already exists for this policy change event.")

        notification_id = uuid4()
        now = datetime.now(timezone.utc)
        normalized_status = normalize_policy_change_notification_delivery_status(initial_status)
        stored = StoredPolicyChangeNotification(
            id=notification_id,
            policy_change_event_id=policy_change_event_id,
            tracked_policy_id=tracked_policy_id,
            subject_type=subject_type,
            subject_id=subject_id,
            recipient_email=recipient_email,
            status=normalized_status,
            created_at=now,
            updated_at=now,
        )
        self._storage.policy_change_notifications[notification_id] = stored
        self._storage.policy_change_notifications_by_event[policy_change_event_id] = notification_id
        self._storage.policy_change_notification_status_events.setdefault(notification_id, [])
        self._record_event(notification_id, normalized_status, initial_detail, recorded_at=now)
        return stored

    def transition_status(
        self,
        *,
        notification_id: UUID,
        status: PolicyChangeNotificationDeliveryStatus,
        detail: str | None,
    ) -> StoredPolicyChangeNotification | None:
        existing = self._storage.policy_change_notifications.get(notification_id)
        if existing is None:
            return None
        normalized = normalize_policy_change_notification_delivery_status(status)
        now = datetime.now(timezone.utc)
        updated = replace(
            existing,
            status=normalized,
            updated_at=now,
        )
        self._storage.policy_change_notifications[notification_id] = updated
        self._record_event(notification_id, normalized, detail, recorded_at=now)
        return updated

    def list_status_history(
        self,
        *,
        notification_id: UUID,
    ) -> list[StoredPolicyChangeNotificationStatusEvent]:
        return list(self._storage.policy_change_notification_status_events.get(notification_id, []))

    def _record_event(
        self,
        notification_id: UUID,
        status: PolicyChangeNotificationDeliveryStatus,
        detail: str | None,
        *,
        recorded_at: datetime,
    ) -> None:
        entry = StoredPolicyChangeNotificationStatusEvent(
            id=uuid4(),
            notification_id=notification_id,
            status=status,
            detail=detail,
            recorded_at=recorded_at,
        )
        self._storage.policy_change_notification_status_events.setdefault(notification_id, []).append(
            entry
        )
