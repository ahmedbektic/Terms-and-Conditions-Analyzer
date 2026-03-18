"""Repository contracts used by the service layer.

Layer: domain persistence boundary.
Concrete implementations live in memory/Postgres modules and must satisfy these
interfaces so business logic remains storage-agnostic.
"""

from datetime import datetime
from typing import Protocol
from uuid import UUID

from .analysis_status import AnalysisLifecycleStatus
from .models import StoredAgreement, StoredFlaggedClause, StoredReport


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
    ) -> StoredReport: ...

    def list_for_subject(self, *, subject_type: str, subject_id: str) -> list[StoredReport]: ...

    def get_for_subject(
        self,
        *,
        report_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredReport | None: ...
