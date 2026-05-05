"""Tracked-policy watchlist orchestration.

This service owns the authenticated watchlist workflow:
- canonicalize and verify a submitted policy URL
- secure a reusable saved baseline report for each enrolled policy URL
- prevent duplicate active registrations per owner
- persist owner-scoped tracked-policy records
- expose active-list and soft-delete behavior to the API layer

It still keeps ongoing manual checks separate from report orchestration, but
watchlist enrollment now coordinates with the analysis service so tracked
policies always start from a real saved baseline and an initial stored
snapshot.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Literal
from uuid import UUID

from ..repositories.errors import ActiveTrackedPolicyConflictError
from ..repositories.interfaces import (
    PolicyChangeEventRepository,
    PolicySnapshotRepository,
    TrackedPolicyCheckExecutionRepository,
    TrackedPolicyRepository,
)
from ..repositories.models import (
    PolicySnapshotCreateInput,
    StoredReport,
    StoredTrackedPolicy,
    StoredTrackedPolicyCheckExecution,
)
from ..repositories.policy_capture_status import PolicyCaptureStatus
from ..repositories.policy_change_status import PolicyChangeStatus
from ..repositories.policy_tracking_status import PolicyTrackingStatus
from ..repositories.tracked_policy_check_execution_status import TrackedPolicyCheckExecutionStatus
from .analysis_service import (
    AgreementNotFoundError,
    AnalysisOrchestrationService,
    InvalidSubmissionError,
    ReportNotFoundError,
)
from .policy_change_email_notification_service import PolicyChangeEmailNotificationService
from .policy_text_canonicalizer import PolicyTextCanonicalizer
from .policy_snapshot_service import (
    PolicySnapshotCheckFailedError,
    PolicySnapshotService,
    PolicySnapshotTrackedPolicyNotFoundError,
)
from .request_subject import RequestSubject
from .tracked_policy_check_execution_service import (
    TrackedPolicyNotFoundError as CheckExecutionTrackedPolicyNotFoundError,
    TrackedPolicyCheckExecutionResult,
    TrackedPolicyCheckExecutionService,
)
from .web_source import (
    PublicWebSourceInspector,
    WebSourceInspectionError,
    canonicalize_public_source_url,
)


class DuplicateTrackedPolicyError(Exception):
    """Raised when the owner already has an active tracked policy for the URL."""


class TrackedPolicyNotFoundError(Exception):
    """Raised when a tracked policy is not found for the active owner subject."""


class InvalidTrackedPolicySourceError(Exception):
    """Raised when a submitted source URL cannot be used for watchlist tracking."""


class TrackedPolicyBaselineReportError(Exception):
    """Raised when watchlist enrollment cannot secure a usable saved baseline report."""


class TrackedPolicyCheckFailedError(Exception):
    """Raised when a tracked policy check fails after the row state was updated."""


@dataclass(frozen=True)
class TrackedPolicyEnrollmentResult:
    """Tracked-policy creation result plus the saved report baseline used for enrollment."""

    tracked_policy: StoredTrackedPolicy
    baseline_report: StoredReport
    baseline_report_action: Literal["created", "reused"]


class TrackedPolicyService:
    """Coordinate watchlist enrollment, listing, manual checks, and removal."""

    def __init__(
        self,
        *,
        tracked_policy_repository: TrackedPolicyRepository,
        policy_snapshot_repository: PolicySnapshotRepository,
        check_execution_repository: TrackedPolicyCheckExecutionRepository,
        analysis_service: AnalysisOrchestrationService,
        policy_change_event_repository: PolicyChangeEventRepository | None = None,
        public_web_source_inspector: PublicWebSourceInspector | None = None,
        policy_snapshot_service: PolicySnapshotService | None = None,
        check_execution_service: TrackedPolicyCheckExecutionService | None = None,
        policy_text_canonicalizer: PolicyTextCanonicalizer | None = None,
        policy_change_notification_service: PolicyChangeEmailNotificationService | None = None,
    ) -> None:
        self._tracked_policy_repository = tracked_policy_repository
        self._policy_snapshot_repository = policy_snapshot_repository
        self._analysis_service = analysis_service
        self._public_web_source_inspector = (
            public_web_source_inspector or PublicWebSourceInspector()
        )
        self._policy_text_canonicalizer = policy_text_canonicalizer or PolicyTextCanonicalizer()
        self._policy_snapshot_service = policy_snapshot_service or PolicySnapshotService(
            tracked_policy_repository=tracked_policy_repository,
            policy_snapshot_repository=policy_snapshot_repository,
            policy_change_event_repository=policy_change_event_repository,
            analysis_service=analysis_service,
            public_web_source_inspector=self._public_web_source_inspector,
        )
        self._check_execution_service = (
            check_execution_service
            or TrackedPolicyCheckExecutionService(
                tracked_policy_repository=tracked_policy_repository,
                check_execution_repository=check_execution_repository,
                policy_snapshot_service=self._policy_snapshot_service,
                policy_change_notification_service=policy_change_notification_service,
            )
        )

    def create_tracked_policy(
        self, *, subject: RequestSubject, source_url: str
    ) -> TrackedPolicyEnrollmentResult:
        """Verify a URL, secure a saved baseline, and seed the first tracked snapshot."""

        try:
            canonical_url = canonicalize_public_source_url(source_url)
        except ValueError as error:
            raise InvalidTrackedPolicySourceError(str(error)) from error

        existing_tracked_policy = (
            self._tracked_policy_repository.get_active_by_canonical_url_for_subject(
                canonical_url=canonical_url,
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
            )
        )
        if existing_tracked_policy is not None:
            raise DuplicateTrackedPolicyError(
                "That policy is already in your watchlist. Remove the existing entry if you want to add it again."
            )

        try:
            captured_source = self._public_web_source_inspector.capture_trackable_source(
                source_url=canonical_url
            )
        except WebSourceInspectionError as error:
            raise InvalidTrackedPolicySourceError(str(error)) from error

        baseline_report = self._analysis_service.find_latest_eligible_baseline_report(
            subject=subject,
            canonical_source_url=captured_source.canonical_url,
        )
        baseline_report_action: Literal["created", "reused"] = "reused"
        baseline_snapshot_text = captured_source.captured_text
        if baseline_report is None:
            try:
                baseline_report = self._analysis_service.create_report_from_verified_url_capture(
                    subject=subject,
                    canonical_source_url=captured_source.canonical_url,
                    display_name=captured_source.display_name,
                    captured_text=captured_source.captured_text,
                )
            except InvalidSubmissionError as error:
                raise TrackedPolicyBaselineReportError(str(error)) from error
            baseline_report_action = "created"
        else:
            try:
                baseline_snapshot_text = self._analysis_service.get_report_terms_text(
                    subject=subject,
                    report_id=baseline_report.id,
                )
            except (AgreementNotFoundError, ReportNotFoundError) as error:
                raise TrackedPolicyBaselineReportError(
                    "We couldn't recover the saved baseline text for that policy. Generate a new report for the URL and try again."
                ) from error
        canonicalized_baseline = self._policy_text_canonicalizer.canonicalize_text(
            baseline_snapshot_text
        )

        try:
            tracked_policy = self._tracked_policy_repository.create(
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
                canonical_url=captured_source.canonical_url,
                display_name=captured_source.display_name,
                source_type=captured_source.source_type,
                tracking_status=PolicyTrackingStatus.ACTIVE,
                last_checked_at=captured_source.checked_at,
                active=True,
            )
        except ActiveTrackedPolicyConflictError as error:
            raise DuplicateTrackedPolicyError(
                "That policy is already in your watchlist. Remove the existing entry if you want to add it again."
            ) from error

        self._policy_snapshot_repository.append_for_tracked_policy_if_changed(
            tracked_policy_id=tracked_policy.id,
            snapshot=PolicySnapshotCreateInput(
                raw_text_body=baseline_snapshot_text,
                normalized_text_body=canonicalized_baseline.comparison_text_body,
                captured_at=captured_source.checked_at,
                source_url=captured_source.canonical_url,
                final_url=captured_source.canonical_url,
                extractor_name="tracked_policy_service",
                extraction_strategy="report_backed_watchlist_enrollment",
                normalization_version=canonicalized_baseline.normalization_version,
            ),
        )
        hydrated_tracked_policy = self._tracked_policy_repository.update_tracked_policy_check_state(
            tracked_policy_id=tracked_policy.id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            last_checked_at=captured_source.checked_at,
            tracking_status=PolicyTrackingStatus.ACTIVE,
            latest_capture_status=PolicyCaptureStatus.CAPTURED,
            latest_capture_message=None,
            latest_change_status=PolicyChangeStatus.NOT_EVALUATED,
            latest_change_detected_at=None,
        )
        if hydrated_tracked_policy is None:
            raise TrackedPolicyNotFoundError(f"Tracked policy {tracked_policy.id} was not found.")
        return TrackedPolicyEnrollmentResult(
            tracked_policy=hydrated_tracked_policy,
            baseline_report=baseline_report,
            baseline_report_action=baseline_report_action,
        )

    def list_tracked_policies(self, *, subject: RequestSubject) -> list[StoredTrackedPolicy]:
        """Return active tracked policies for the request subject, newest first."""

        return self._tracked_policy_repository.list_active_for_subject(
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )

    def remove_tracked_policy(self, *, subject: RequestSubject, tracked_policy_id: UUID) -> None:
        """Soft-delete one active tracked policy for the request subject."""

        deactivated_policy = self._tracked_policy_repository.deactivate_for_subject(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )
        if deactivated_policy is None:
            raise TrackedPolicyNotFoundError(f"Tracked policy {tracked_policy_id} was not found.")

    def check_tracked_policy(
        self, *, subject: RequestSubject, tracked_policy_id: UUID
    ) -> TrackedPolicyCheckExecutionResult:
        """Fetch current policy text, store a new snapshot when it changes, and refresh status."""

        # Note: In future PRs, this synchronously returns an execution object instead of the policy.
        # For now, we still return the resulting tracked policy to keep the API stable,
        # but we drive it entirely through the execution deduplication seam.
        try:
            result = self._check_execution_service.execute_check(
                subject=subject,
                tracked_policy_id=tracked_policy_id,
            )
        except CheckExecutionTrackedPolicyNotFoundError as error:
            raise TrackedPolicyNotFoundError(str(error)) from error
        if (
            result.tracked_policy is None
            and result.execution.status != TrackedPolicyCheckExecutionStatus.PENDING
        ):
            raise TrackedPolicyNotFoundError(f"Tracked policy {tracked_policy_id} was not found.")

        return result

    def get_tracked_policy_execution(
        self, *, subject: RequestSubject, execution_id: UUID
    ) -> StoredTrackedPolicyCheckExecution:
        """Return one stored execution for the request subject."""

        return self._check_execution_service.get_tracked_policy_execution(
            subject=subject,
            execution_id=execution_id,
        )
