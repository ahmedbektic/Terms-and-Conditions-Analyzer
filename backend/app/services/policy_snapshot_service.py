"""Tracked-policy snapshot capture orchestration.

This service owns the manual check path for tracked policies:
- load the owner-scoped tracked policy row
- capture normalized policy text plus fetch metadata from the public URL seam
- store a new snapshot only when the normalized content changed
- refresh tracked-policy status fields for success, no-change, and failure cases

The route/API layer still deals in tracked-policy responses only, while this
service keeps snapshot-specific mechanics isolated for future background-job
and change-detection work.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from uuid import UUID

from ..repositories.interfaces import (
    PolicyChangeEventRepository,
    PolicySnapshotRepository,
    TrackedPolicyRepository,
)
from ..repositories.models import (
    PolicyChangeEventCreateInput,
    PolicySnapshotAppendResult,
    PolicySnapshotCreateInput,
    StoredPolicyChangeEvent,
    StoredPolicySnapshot,
    StoredTrackedPolicy,
)
from ..repositories.policy_capture_status import PolicyCaptureStatus
from ..repositories.policy_change_status import PolicyChangeStatus
from ..repositories.policy_tracking_status import PolicyTrackingStatus
from .analysis_service import AnalysisOrchestrationService, InvalidSubmissionError
from .ai_provider import AnalysisProviderInvocationError
from .policy_change_detection_service import (
    PolicyChangeDetectionResult,
    PolicyChangeDetectionService,
)
from .request_subject import RequestSubject
from .web_source import (
    CapturedPolicySnapshotSource,
    PublicWebSourceInspector,
    WebSourceInspectionError,
)

_NO_CHANGE_CAPTURE_MESSAGE = (
    "No meaningful policy changes were detected, so no new stored version was created."
)
_REPORT_CREATION_FAILED_MESSAGE = "We detected a possible update, but couldn't finish saving a new stored version. No new stored version was added. Try checking again in a moment."
_REPORT_CREATION_TIMEOUT_MESSAGE = "We detected a possible update, but the AI analysis timed out before a new stored version could be saved. No new stored version was added. Try checking again in a moment."


class PolicySnapshotTrackedPolicyNotFoundError(Exception):
    """Raised when a tracked policy is not found for the active owner."""


class PolicySnapshotCheckFailedError(Exception):
    """Raised when a tracked-policy check fails after row state is refreshed."""


@dataclass(frozen=True)
class PolicySnapshotCheckResult:
    """Result of a manual tracked-policy check."""

    tracked_policy: StoredTrackedPolicy
    snapshot_created: bool
    meaningful_change_event_id: UUID | None = None


class PolicySnapshotService:
    """Capture and persist tracked-policy snapshots for manual checks."""

    def __init__(
        self,
        *,
        tracked_policy_repository: TrackedPolicyRepository,
        policy_snapshot_repository: PolicySnapshotRepository,
        policy_change_event_repository: PolicyChangeEventRepository | None = None,
        analysis_service: AnalysisOrchestrationService | None = None,
        policy_change_detection_service: PolicyChangeDetectionService | None = None,
        public_web_source_inspector: PublicWebSourceInspector | None = None,
    ) -> None:
        self._tracked_policy_repository = tracked_policy_repository
        self._policy_snapshot_repository = policy_snapshot_repository
        self._policy_change_event_repository = policy_change_event_repository
        self._analysis_service = analysis_service
        self._policy_change_detection_service = (
            policy_change_detection_service or PolicyChangeDetectionService()
        )
        self._public_web_source_inspector = (
            public_web_source_inspector or PublicWebSourceInspector()
        )

    def check_tracked_policy(
        self, *, subject: RequestSubject, tracked_policy_id: UUID
    ) -> PolicySnapshotCheckResult:
        """Capture a new tracked-policy snapshot when the normalized content changed."""

        existing = self._tracked_policy_repository.get_active_for_subject(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )
        if existing is None:
            raise PolicySnapshotTrackedPolicyNotFoundError(
                f"Tracked policy {tracked_policy_id} was not found."
            )

        previous_snapshot = self._policy_snapshot_repository.get_latest_for_tracked_policy(
            tracked_policy_id=tracked_policy_id
        )
        attempted_at = datetime.now(timezone.utc)
        try:
            captured_source = self._public_web_source_inspector.capture_policy_snapshot_source(
                canonical_url=existing.canonical_url
            )
        except WebSourceInspectionError as error:
            self._store_change_event(
                tracked_policy_id=tracked_policy_id,
                previous_snapshot=previous_snapshot,
                new_snapshot=None,
                detected_at=attempted_at,
                change_status=PolicyChangeStatus.COMPARISON_INCOMPLETE,
                detection_method="capture_failed",
                content_changed=None,
                previous_section_count=None,
                new_section_count=None,
                section_delta=None,
            )
            updated = self._tracked_policy_repository.update_tracked_policy_check_state(
                tracked_policy_id=tracked_policy_id,
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
                last_checked_at=attempted_at,
                tracking_status=self._tracking_status_after_failure(
                    existing=existing,
                    error=error,
                ),
                latest_capture_status=PolicyCaptureStatus.CAPTURE_FAILED,
                latest_capture_message=str(error),
                latest_change_status=PolicyChangeStatus.COMPARISON_INCOMPLETE,
                latest_change_detected_at=existing.latest_change_detected_at,
            )
            if updated is None:
                raise PolicySnapshotTrackedPolicyNotFoundError(
                    f"Tracked policy {tracked_policy_id} was not found."
                )
            raise PolicySnapshotCheckFailedError(str(error)) from error

        detection_result = self._policy_change_detection_service.detect_change(
            previous_snapshot=previous_snapshot,
            raw_text_body=captured_source.raw_text_body,
            normalized_text_body=captured_source.normalized_text_body,
            normalization_version=captured_source.normalization_version,
        )
        append_result = self._append_snapshot_if_needed(
            tracked_policy_id=tracked_policy_id,
            captured_source=captured_source,
            detection_result=detection_result,
        )
        latest_change_detected_at = (
            captured_source.checked_at
            if detection_result.change_status == PolicyChangeStatus.UPDATED
            else existing.latest_change_detected_at
        )
        tracked_policy_version_number = (
            existing.snapshot_version_count + 1
            if append_result is not None and append_result.created
            else existing.snapshot_version_count
        )
        report_creation_error = self._create_tracked_snapshot_report_if_needed(
            subject=subject,
            tracked_policy_id=tracked_policy_id,
            tracked_policy_version_number=tracked_policy_version_number,
            append_result=append_result,
            captured_source=captured_source,
        )
        if report_creation_error is not None:
            if append_result is not None and append_result.created:
                self._policy_snapshot_repository.delete_for_tracked_policy(
                    tracked_policy_id=tracked_policy_id,
                    snapshot_id=append_result.snapshot.id,
                )
            message = self._build_report_creation_failure_message(report_creation_error)
            self._store_change_event(
                tracked_policy_id=tracked_policy_id,
                previous_snapshot=previous_snapshot,
                new_snapshot=None,
                detected_at=captured_source.checked_at,
                change_status=PolicyChangeStatus.COMPARISON_INCOMPLETE,
                detection_method="report_creation_failed",
                content_changed=None,
                previous_section_count=detection_result.previous_section_count,
                new_section_count=detection_result.new_section_count,
                section_delta=detection_result.section_delta,
            )
            updated = self._tracked_policy_repository.update_tracked_policy_check_state(
                tracked_policy_id=tracked_policy_id,
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
                last_checked_at=captured_source.checked_at,
                tracking_status=PolicyTrackingStatus.ACTIVE,
                latest_capture_status=PolicyCaptureStatus.CAPTURE_FAILED,
                latest_capture_message=message,
                latest_change_status=PolicyChangeStatus.COMPARISON_INCOMPLETE,
                latest_change_detected_at=existing.latest_change_detected_at,
            )
            if updated is None:
                raise PolicySnapshotTrackedPolicyNotFoundError(
                    f"Tracked policy {tracked_policy_id} was not found."
                )
            raise PolicySnapshotCheckFailedError(message) from report_creation_error

        stored_change_event = self._store_change_event(
            tracked_policy_id=tracked_policy_id,
            previous_snapshot=previous_snapshot,
            new_snapshot=(
                append_result.snapshot
                if append_result is not None
                and detection_result.change_status == PolicyChangeStatus.UPDATED
                else None
            ),
            detected_at=captured_source.checked_at,
            change_status=detection_result.change_status,
            detection_method=detection_result.detection_method,
            content_changed=detection_result.content_changed,
            previous_section_count=detection_result.previous_section_count,
            new_section_count=detection_result.new_section_count,
            section_delta=detection_result.section_delta,
        )
        updated = self._tracked_policy_repository.update_tracked_policy_check_state(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            last_checked_at=captured_source.checked_at,
            tracking_status=PolicyTrackingStatus.ACTIVE,
            latest_capture_status=PolicyCaptureStatus.CAPTURED,
            latest_capture_message=self._build_capture_message(
                detection_result=detection_result,
                append_result=append_result,
            ),
            latest_change_status=detection_result.change_status,
            latest_change_detected_at=latest_change_detected_at,
        )
        if updated is None:
            raise PolicySnapshotTrackedPolicyNotFoundError(
                f"Tracked policy {tracked_policy_id} was not found."
            )
        meaningful_change_event_id = None
        if (
            stored_change_event is not None
            and stored_change_event.change_status == PolicyChangeStatus.UPDATED
            and append_result is not None
            and append_result.created
        ):
            meaningful_change_event_id = stored_change_event.id

        return PolicySnapshotCheckResult(
            tracked_policy=updated,
            snapshot_created=bool(append_result and append_result.created),
            meaningful_change_event_id=meaningful_change_event_id,
        )

    def _build_snapshot_input(
        self, *, captured_source: CapturedPolicySnapshotSource
    ) -> PolicySnapshotCreateInput:
        return PolicySnapshotCreateInput(
            raw_text_body=captured_source.raw_text_body,
            normalized_text_body=captured_source.normalized_text_body,
            normalization_version=captured_source.normalization_version,
            captured_at=captured_source.checked_at,
            source_url=captured_source.canonical_url,
            final_url=captured_source.final_url,
            http_status=captured_source.http_status,
            redirect_count=captured_source.redirect_count,
            fetch_duration_ms=captured_source.fetch_duration_ms,
            extractor_name=captured_source.extractor_name,
            extraction_strategy=captured_source.extraction_strategy,
        )

    def _build_capture_message(
        self,
        *,
        detection_result: PolicyChangeDetectionResult,
        append_result: PolicySnapshotAppendResult | None,
    ) -> str | None:
        if detection_result.change_status == PolicyChangeStatus.UNCHANGED:
            return _NO_CHANGE_CAPTURE_MESSAGE
        if append_result is not None and append_result.created:
            return None
        return None

    def _create_tracked_snapshot_report_if_needed(
        self,
        *,
        subject: RequestSubject,
        tracked_policy_id: UUID,
        tracked_policy_version_number: int,
        append_result: PolicySnapshotAppendResult | None,
        captured_source: CapturedPolicySnapshotSource,
    ) -> Exception | None:
        if append_result is None or not append_result.created or self._analysis_service is None:
            return None

        try:
            self._analysis_service.create_report_from_verified_url_capture(
                subject=subject,
                canonical_source_url=captured_source.canonical_url,
                display_name=captured_source.display_name,
                captured_text=append_result.snapshot.normalized_text_body,
                tracked_policy_id=tracked_policy_id,
                tracked_policy_snapshot_id=append_result.snapshot.id,
                tracked_policy_version_number=tracked_policy_version_number,
            )
        except (InvalidSubmissionError, AnalysisProviderInvocationError) as error:
            return error
        return None

    def _append_snapshot_if_needed(
        self,
        *,
        tracked_policy_id: UUID,
        captured_source: CapturedPolicySnapshotSource,
        detection_result: PolicyChangeDetectionResult,
    ) -> PolicySnapshotAppendResult | None:
        if not detection_result.should_create_snapshot:
            return None
        return self._policy_snapshot_repository.append_for_tracked_policy_if_changed(
            tracked_policy_id=tracked_policy_id,
            snapshot=self._build_snapshot_input(captured_source=captured_source),
        )

    def _store_change_event(
        self,
        *,
        tracked_policy_id: UUID,
        previous_snapshot: StoredPolicySnapshot | None,
        new_snapshot: StoredPolicySnapshot | None,
        detected_at: datetime,
        change_status: PolicyChangeStatus,
        detection_method: str,
        content_changed: bool | None,
        previous_section_count: int | None,
        new_section_count: int | None,
        section_delta: int | None,
    ) -> StoredPolicyChangeEvent | None:
        if (
            self._policy_change_event_repository is None
            or change_status == PolicyChangeStatus.NOT_EVALUATED
        ):
            return None
        return self._policy_change_event_repository.create(
            event=PolicyChangeEventCreateInput(
                tracked_policy_id=tracked_policy_id,
                previous_snapshot_id=(
                    previous_snapshot.id if previous_snapshot is not None else None
                ),
                new_snapshot_id=new_snapshot.id if new_snapshot is not None else None,
                detected_at=detected_at,
                change_status=change_status,
                detection_method=detection_method,
                content_changed=content_changed,
                previous_section_count=previous_section_count,
                new_section_count=new_section_count,
                section_delta=section_delta,
            )
        )

    def _tracking_status_after_failure(
        self,
        *,
        existing: StoredTrackedPolicy,
        error: WebSourceInspectionError,
    ) -> PolicyTrackingStatus:
        if error.invalidates_tracking:
            return PolicyTrackingStatus.INVALID_SOURCE
        return existing.tracking_status

    def _build_report_creation_failure_message(self, error: Exception) -> str:
        if isinstance(error, AnalysisProviderInvocationError) and "ReadTimeout" in str(error):
            return _REPORT_CREATION_TIMEOUT_MESSAGE
        return _REPORT_CREATION_FAILED_MESSAGE
