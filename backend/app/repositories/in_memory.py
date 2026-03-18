"""In-memory repository implementation used for local MVP wiring before DB integration.

This module mirrors the repository contracts so the service and route layers stay stable
when a Supabase/Postgres implementation is introduced.
"""

from datetime import datetime, timezone
from uuid import UUID, uuid4

from .models import StoredAgreement, StoredFlaggedClause, StoredReport


class InMemoryStorage:
    """Simple in-process storage container for local development and tests."""

    def __init__(self) -> None:
        self.agreements: dict[UUID, StoredAgreement] = {}
        self.reports: dict[UUID, StoredReport] = {}

    def clear(self) -> None:
        self.agreements.clear()
        self.reports.clear()


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
        status: str,
        summary: str,
        trust_score: int,
        model_name: str,
        flagged_clauses: list[StoredFlaggedClause],
        completed_at: datetime | None,
    ) -> StoredReport:
        report = StoredReport(
            id=uuid4(),
            agreement_id=agreement_id,
            subject_type=subject_type,
            subject_id=subject_id,
            source_type=source_type,
            source_value=source_value,
            raw_input_excerpt=raw_input_excerpt,
            status=status,
            summary=summary,
            trust_score=trust_score,
            model_name=model_name,
            flagged_clauses=flagged_clauses,
            created_at=datetime.now(timezone.utc),
            completed_at=completed_at,
        )
        self._storage.reports[report.id] = report
        return report

    def list_for_subject(self, *, subject_type: str, subject_id: str) -> list[StoredReport]:
        reports = [
            report
            for report in self._storage.reports.values()
            if report.subject_type == subject_type and report.subject_id == subject_id
        ]
        return sorted(reports, key=lambda report: report.created_at, reverse=True)

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
