"""Storage-facing domain models shared across repositories and services.

Layer: domain model.
These dataclasses intentionally avoid transport-specific naming so the API layer
can map them to request/response contracts.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .analysis_status import AnalysisLifecycleStatus
from .policy_capture_status import PolicyCaptureStatus, PolicySnapshotStatus
from .policy_change_status import PolicyChangeStatus
from .policy_tracking_status import PolicyTrackingStatus
from .report_capture_kind import ReportContentCaptureKind


@dataclass(frozen=True)
class StoredFlaggedClause:
    """Normalized representation of one flagged clause in persisted reports."""

    clause_type: str
    severity: str
    excerpt: str
    explanation: str


@dataclass(frozen=True)
class StoredAgreement:
    """Persisted terms agreement record."""

    id: UUID
    subject_type: str
    subject_id: str
    title: str | None
    source_url: str | None
    agreed_at: datetime | None
    terms_text: str
    created_at: datetime


@dataclass(frozen=True)
class StoredReport:
    """Persisted analysis report record with explicit lifecycle status."""

    id: UUID
    agreement_id: UUID
    subject_type: str
    subject_id: str
    source_type: str
    source_value: str
    raw_input_excerpt: str
    status: AnalysisLifecycleStatus
    summary: str
    trust_score: int
    model_name: str
    flagged_clauses: list[StoredFlaggedClause]
    created_at: datetime
    completed_at: datetime | None
    canonical_source_url: str | None = None
    content_capture_kind: ReportContentCaptureKind = ReportContentCaptureKind.LEGACY_UNKNOWN
    tracked_policy_id: UUID | None = None
    tracked_policy_snapshot_id: UUID | None = None
    tracked_policy_version_number: int | None = None


@dataclass(frozen=True)
class StoredTrackedPolicy:
    """Persisted watchlist entry for an authenticated user's tracked policy URL."""

    id: UUID
    subject_type: str
    subject_id: str
    canonical_url: str
    display_name: str
    source_type: str
    tracking_status: PolicyTrackingStatus
    last_checked_at: datetime | None
    last_successful_capture_at: datetime | None
    latest_capture_status: PolicyCaptureStatus
    latest_capture_message: str | None
    latest_change_status: PolicyChangeStatus
    latest_change_detected_at: datetime | None
    active: bool
    created_at: datetime
    snapshot_version_count: int


@dataclass(frozen=True)
class PolicySnapshotCreateInput:
    """Write-model for one tracked-policy snapshot attempt."""

    raw_text_body: str
    normalized_text_body: str
    captured_at: datetime
    source_url: str | None = None
    final_url: str | None = None
    http_status: int | None = None
    redirect_count: int | None = None
    fetch_duration_ms: int | None = None
    extractor_name: str | None = None
    extraction_strategy: str | None = None
    capture_status: PolicySnapshotStatus = PolicySnapshotStatus.CAPTURED
    capture_error_message: str | None = None


@dataclass(frozen=True)
class StoredPolicySnapshot:
    """Persisted snapshot row with richer capture metadata."""

    id: UUID
    tracked_policy_id: UUID
    raw_text_body: str
    normalized_text_body: str
    content_hash: str
    captured_at: datetime
    capture_status: PolicySnapshotStatus
    source_url: str | None
    final_url: str | None
    http_status: int | None
    redirect_count: int | None
    fetch_duration_ms: int | None
    extractor_name: str | None
    extraction_strategy: str | None
    capture_error_message: str | None


@dataclass(frozen=True)
class PolicySnapshotAppendResult:
    """Result of attempting to append a tracked-policy snapshot."""

    snapshot: StoredPolicySnapshot
    created: bool


@dataclass(frozen=True)
class PolicyChangeEventCreateInput:
    """Write-model for one tracked-policy change-detection result."""

    tracked_policy_id: UUID
    previous_snapshot_id: UUID | None
    new_snapshot_id: UUID | None
    detected_at: datetime
    change_status: PolicyChangeStatus
    detection_method: str
    content_changed: bool | None = None
    previous_section_count: int | None = None
    new_section_count: int | None = None
    section_delta: int | None = None


@dataclass(frozen=True)
class StoredPolicyChangeEvent:
    """Persisted change-detection result for one tracked-policy scan."""

    id: UUID
    tracked_policy_id: UUID
    previous_snapshot_id: UUID | None
    new_snapshot_id: UUID | None
    detected_at: datetime
    change_status: PolicyChangeStatus
    detection_method: str
    content_changed: bool | None
    previous_section_count: int | None
    new_section_count: int | None
    section_delta: int | None
