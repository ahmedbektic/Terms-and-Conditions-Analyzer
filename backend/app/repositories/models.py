"""Storage-facing domain models shared across repositories and services.

Layer: domain model.
These dataclasses intentionally avoid transport-specific naming so the API layer
can map them to request/response contracts.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from .analysis_status import AnalysisLifecycleStatus
from .policy_tracking_status import PolicyTrackingStatus


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
    active: bool
    created_at: datetime
