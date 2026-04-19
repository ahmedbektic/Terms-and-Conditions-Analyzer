"""Repository contracts used by the service layer.

Layer: domain persistence boundary.
Concrete implementations live in memory/Postgres modules and must satisfy these
interfaces so business logic remains storage-agnostic.
"""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from .analysis_status import AnalysisLifecycleStatus
from .models import StoredAgreement, StoredFlaggedClause, StoredReport, StoredTrackedPolicy
from .policy_tracking_status import PolicyTrackingStatus
from .report_capture_kind import ReportContentCaptureKind


class AgreementRepository(Protocol):
    """Persistence operations for agreements."""

    def create(
        self,
        *,
        subject_type: str,
        subject_id: str,
        title: str | None,
        source_url: str | None,
        agreed_at: datetime | None,
        terms_text: str,
    ) -> StoredAgreement: ...

    def get_for_subject(
        self,
        *,
        agreement_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredAgreement | None: ...


class ReportRepository(Protocol):
    """Persistence operations for analysis reports."""

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
    ) -> StoredReport: ...

    def list_for_subject(self, *, subject_type: str, subject_id: str) -> list[StoredReport]: ...

    def get_for_subject(
        self,
        *,
        report_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredReport | None: ...

    def get_latest_eligible_baseline_report_for_subject(
        self,
        *,
        canonical_source_url: str,
        subject_type: str,
        subject_id: str,
    ) -> StoredReport | None: ...


class TrackedPolicyRepository(Protocol):
    """Persistence operations for active/inactive tracked policy watchlist rows."""

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
    ) -> StoredTrackedPolicy: ...

    def list_active_for_subject(
        self, *, subject_type: str, subject_id: str
    ) -> list[StoredTrackedPolicy]: ...

    def get_active_for_subject(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None: ...

    def get_active_by_canonical_url_for_subject(
        self,
        *,
        canonical_url: str,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None: ...

    def deactivate_for_subject(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None: ...

    def append_snapshot_if_text_changed(
        self,
        *,
        tracked_policy_id: UUID,
        terms_text: str,
        captured_at: datetime,
    ) -> bool: ...

    def update_tracked_policy_check_state(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
        last_checked_at: datetime,
        tracking_status: PolicyTrackingStatus,
    ) -> StoredTrackedPolicy | None: ...
