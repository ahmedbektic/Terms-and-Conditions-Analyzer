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

from ..repositories.interfaces import PolicySnapshotRepository, TrackedPolicyRepository
from ..repositories.models import (
    PolicySnapshotAppendResult,
    PolicySnapshotCreateInput,
    StoredTrackedPolicy,
)
from ..repositories.policy_capture_status import PolicyCaptureStatus
from ..repositories.policy_tracking_status import PolicyTrackingStatus
from .analysis_service import AnalysisOrchestrationService, InvalidSubmissionError
from .request_subject import RequestSubject
from .web_source import (
    CapturedPolicySnapshotSource,
    PublicWebSourceInspector,
    WebSourceInspectionError,
)

_NO_CHANGE_CAPTURE_MESSAGE = (
    "No policy text changes were detected, so no new stored version was created."
)
_REPORT_CREATION_FAILED_MESSAGE = (
    "A new stored version was captured, but its saved analysis report could not be created."
)


class PolicySnapshotTrackedPolicyNotFoundError(Exception):
    """Raised when a tracked policy is not found for the active owner."""


class PolicySnapshotCheckFailedError(Exception):
    """Raised when a tracked-policy check fails after row state is refreshed."""


@dataclass(frozen=True)
class PolicySnapshotCheckResult:
    """Result of a manual tracked-policy check."""

    tracked_policy: StoredTrackedPolicy
    snapshot_created: bool


class PolicySnapshotService:
    """Capture and persist tracked-policy snapshots for manual checks."""

    def __init__(
        self,
        *,
        tracked_policy_repository: TrackedPolicyRepository,
        policy_snapshot_repository: PolicySnapshotRepository,
        analysis_service: AnalysisOrchestrationService | None = None,
        public_web_source_inspector: PublicWebSourceInspector | None = None,
    ) -> None:
        self._tracked_policy_repository = tracked_policy_repository
        self._policy_snapshot_repository = policy_snapshot_repository
        self._analysis_service = analysis_service
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

        attempted_at = datetime.now(timezone.utc)
        try:
            captured_source = self._public_web_source_inspector.capture_policy_snapshot_source(
                canonical_url=existing.canonical_url
            )
        except WebSourceInspectionError as error:
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
            )
            if updated is None:
                raise PolicySnapshotTrackedPolicyNotFoundError(
                    f"Tracked policy {tracked_policy_id} was not found."
                )
            raise PolicySnapshotCheckFailedError(str(error)) from error

        append_result = self._policy_snapshot_repository.append_for_tracked_policy_if_changed(
            tracked_policy_id=tracked_policy_id,
            snapshot=self._build_snapshot_input(captured_source=captured_source),
        )
        updated = self._tracked_policy_repository.update_tracked_policy_check_state(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            last_checked_at=captured_source.checked_at,
            tracking_status=PolicyTrackingStatus.ACTIVE,
            latest_capture_status=PolicyCaptureStatus.CAPTURED,
            latest_capture_message=self._build_capture_message(append_result),
        )
        if updated is None:
            raise PolicySnapshotTrackedPolicyNotFoundError(
                f"Tracked policy {tracked_policy_id} was not found."
            )
        updated_with_report_state = self._create_tracked_snapshot_report_if_needed(
            subject=subject,
            tracked_policy=updated,
            append_result=append_result,
            captured_source=captured_source,
        )
        return PolicySnapshotCheckResult(
            tracked_policy=updated_with_report_state,
            snapshot_created=append_result.created,
        )

    def _build_snapshot_input(
        self, *, captured_source: CapturedPolicySnapshotSource
    ) -> PolicySnapshotCreateInput:
        return PolicySnapshotCreateInput(
            raw_text_body=captured_source.raw_text_body,
            normalized_text_body=captured_source.normalized_text_body,
            captured_at=captured_source.checked_at,
            source_url=captured_source.canonical_url,
            final_url=captured_source.final_url,
            http_status=captured_source.http_status,
            redirect_count=captured_source.redirect_count,
            fetch_duration_ms=captured_source.fetch_duration_ms,
            extractor_name=captured_source.extractor_name,
            extraction_strategy=captured_source.extraction_strategy,
        )

    def _build_capture_message(self, append_result: PolicySnapshotAppendResult) -> str | None:
        if append_result.created:
            return None
        return _NO_CHANGE_CAPTURE_MESSAGE

    def _create_tracked_snapshot_report_if_needed(
        self,
        *,
        subject: RequestSubject,
        tracked_policy: StoredTrackedPolicy,
        append_result: PolicySnapshotAppendResult,
        captured_source: CapturedPolicySnapshotSource,
    ) -> StoredTrackedPolicy:
        if not append_result.created or self._analysis_service is None:
            return tracked_policy

        try:
            self._analysis_service.create_report_from_verified_url_capture(
                subject=subject,
                canonical_source_url=captured_source.canonical_url,
                display_name=tracked_policy.display_name,
                captured_text=append_result.snapshot.normalized_text_body,
                tracked_policy_id=tracked_policy.id,
                tracked_policy_snapshot_id=append_result.snapshot.id,
                tracked_policy_version_number=tracked_policy.snapshot_version_count,
            )
        except InvalidSubmissionError:
            updated = self._tracked_policy_repository.update_tracked_policy_check_state(
                tracked_policy_id=tracked_policy.id,
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
                last_checked_at=tracked_policy.last_checked_at or captured_source.checked_at,
                tracking_status=tracked_policy.tracking_status,
                latest_capture_status=tracked_policy.latest_capture_status,
                latest_capture_message=_REPORT_CREATION_FAILED_MESSAGE,
            )
            if updated is not None:
                return updated
        return tracked_policy

    def _tracking_status_after_failure(
        self,
        *,
        existing: StoredTrackedPolicy,
        error: WebSourceInspectionError,
    ) -> PolicyTrackingStatus:
        if error.invalidates_tracking:
            return PolicyTrackingStatus.INVALID_SOURCE
        return existing.tracking_status
