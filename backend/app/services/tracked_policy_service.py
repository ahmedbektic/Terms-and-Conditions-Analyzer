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
from datetime import datetime, timezone
from typing import Literal
from uuid import UUID

from ..repositories.errors import ActiveTrackedPolicyConflictError
from ..repositories.interfaces import TrackedPolicyRepository
from ..repositories.models import StoredReport, StoredTrackedPolicy
from ..repositories.policy_tracking_status import PolicyTrackingStatus
from .analysis_service import (
    AgreementNotFoundError,
    AnalysisOrchestrationService,
    InvalidSubmissionError,
    ReportNotFoundError,
)
from .request_subject import RequestSubject
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
        analysis_service: AnalysisOrchestrationService,
        public_web_source_inspector: PublicWebSourceInspector | None = None,
    ) -> None:
        self._tracked_policy_repository = tracked_policy_repository
        self._analysis_service = analysis_service
        self._public_web_source_inspector = (
            public_web_source_inspector or PublicWebSourceInspector()
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

        self._tracked_policy_repository.append_snapshot_if_text_changed(
            tracked_policy_id=tracked_policy.id,
            terms_text=baseline_snapshot_text,
            captured_at=captured_source.checked_at,
        )
        hydrated_tracked_policy = self._tracked_policy_repository.update_tracked_policy_check_state(
            tracked_policy_id=tracked_policy.id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            last_checked_at=captured_source.checked_at,
            tracking_status=PolicyTrackingStatus.ACTIVE,
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
    ) -> StoredTrackedPolicy:
        """Fetch current policy text, store a new snapshot when it changes, and refresh status."""

        existing = self._tracked_policy_repository.get_active_for_subject(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )
        if existing is None:
            raise TrackedPolicyNotFoundError(f"Tracked policy {tracked_policy_id} was not found.")

        checked_at = datetime.now(timezone.utc)
        try:
            policy_text = self._public_web_source_inspector.capture_policy_text(
                canonical_url=existing.canonical_url
            )
        except WebSourceInspectionError as error:
            updated = self._tracked_policy_repository.update_tracked_policy_check_state(
                tracked_policy_id=tracked_policy_id,
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
                last_checked_at=checked_at,
                tracking_status=PolicyTrackingStatus.INVALID_SOURCE,
            )
            if updated is None:
                raise TrackedPolicyNotFoundError(
                    f"Tracked policy {tracked_policy_id} was not found."
                )
            raise TrackedPolicyCheckFailedError(str(error)) from error

        self._tracked_policy_repository.append_snapshot_if_text_changed(
            tracked_policy_id=tracked_policy_id,
            terms_text=policy_text,
            captured_at=checked_at,
        )
        updated = self._tracked_policy_repository.update_tracked_policy_check_state(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            last_checked_at=checked_at,
            tracking_status=PolicyTrackingStatus.ACTIVE,
        )
        if updated is None:
            raise TrackedPolicyNotFoundError(f"Tracked policy {tracked_policy_id} was not found.")
        return updated
