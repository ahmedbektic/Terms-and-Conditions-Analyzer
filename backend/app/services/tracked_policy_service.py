"""Tracked-policy watchlist orchestration.

This service owns the authenticated watchlist workflow:
- canonicalize and verify a submitted policy URL
- prevent duplicate active registrations per owner
- persist owner-scoped tracked-policy records
- expose active-list and soft-delete behavior to the API layer

It intentionally stays separate from analysis-report orchestration so policy
tracking can evolve into its own snapshot/versioning slice without inheriting
report-specific responsibilities.
"""

from __future__ import annotations

from uuid import UUID

from ..repositories.errors import ActiveTrackedPolicyConflictError
from ..repositories.interfaces import TrackedPolicyRepository
from ..repositories.models import StoredTrackedPolicy
from ..repositories.policy_tracking_status import PolicyTrackingStatus
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


class TrackedPolicyService:
    """Coordinate tracked-policy registration, listing, and removal."""

    def __init__(
        self,
        *,
        tracked_policy_repository: TrackedPolicyRepository,
        public_web_source_inspector: PublicWebSourceInspector | None = None,
    ) -> None:
        self._tracked_policy_repository = tracked_policy_repository
        self._public_web_source_inspector = (
            public_web_source_inspector or PublicWebSourceInspector()
        )

    def create_tracked_policy(
        self, *, subject: RequestSubject, source_url: str
    ) -> StoredTrackedPolicy:
        """Verify and persist one tracked policy for the active owner subject."""

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
            raise DuplicateTrackedPolicyError("That policy is already in your watchlist.")

        try:
            inspected_source = self._public_web_source_inspector.inspect_url(
                source_url=canonical_url
            )
        except WebSourceInspectionError as error:
            raise InvalidTrackedPolicySourceError(str(error)) from error

        try:
            return self._tracked_policy_repository.create(
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
                canonical_url=inspected_source.canonical_url,
                display_name=inspected_source.display_name,
                source_type=inspected_source.source_type,
                tracking_status=PolicyTrackingStatus.PENDING_FIRST_SNAPSHOT,
                last_checked_at=inspected_source.last_checked_at,
                active=True,
            )
        except ActiveTrackedPolicyConflictError as error:
            raise DuplicateTrackedPolicyError(
                "That policy is already in your watchlist."
            ) from error

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
