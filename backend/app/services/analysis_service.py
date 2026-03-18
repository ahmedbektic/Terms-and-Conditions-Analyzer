"""Agreement/report orchestration service.

Responsibilities in this module:
- coordinate agreement creation and report persistence workflow
- delegate report execution through the analysis execution seam
- enforce owner-scoped repository access for report retrieval

Dependencies:
- repository interfaces (persistence boundary)
- analysis execution strategy (sync/queued execution boundary)
- submission preparation service (source normalization/resolution boundary)

What depends on this module:
- API route handlers in `backend/app/api/routes/*`

Architectural boundary:
- Source-preparation logic lives in `submission_preparation.py`.
- This module stays focused on orchestration decisions so execution mode can
  later evolve from sync-in-request to queued worker processing.
- Provider-input adaptation is owned by the execution layer, not orchestration.
"""

from dataclasses import dataclass
from datetime import datetime
from uuid import UUID

from ..repositories.interfaces import AgreementRepository, ReportRepository
from ..repositories.models import StoredAgreement, StoredReport
from .analysis_execution import AnalysisExecutionRequest, AnalysisExecutionStrategy
from .extraction_contracts import ExtractionIngestionResult
from .submission_preparation import (
    AnalysisSubmission,
    InvalidSubmissionError,
    SubmissionPreparationService,
)

__all__ = [
    "AgreementNotFoundError",
    "AnalysisOrchestrationService",
    "AnalysisSubmission",
    "InvalidSubmissionError",
    "ReportNotFoundError",
    "RequestSubject",
]


@dataclass(frozen=True)
class RequestSubject:
    """Identity tuple used for owner-scoped data access."""

    subject_type: str
    subject_id: str


class AgreementNotFoundError(Exception):
    """Raised when an agreement is not found for the active owner subject."""


class ReportNotFoundError(Exception):
    """Raised when a report is not found for the active owner subject."""


class AnalysisOrchestrationService:
    """Coordinate agreement/report persistence and analysis execution.

    This service deliberately avoids source-preparation details. Both one-shot
    and manual-analysis flows consume prepared ingestion results from
    `SubmissionPreparationService`, keeping orchestration focused on workflow
    order and boundary coordination. Execution mode concerns are delegated to
    `AnalysisExecutionStrategy`.
    """

    def __init__(
        self,
        *,
        agreement_repository: AgreementRepository,
        report_repository: ReportRepository,
        analysis_execution_strategy: AnalysisExecutionStrategy,
        submission_preparation_service: SubmissionPreparationService,
    ) -> None:
        self._agreement_repository = agreement_repository
        self._report_repository = report_repository
        self._analysis_execution_strategy = analysis_execution_strategy
        self._submission_preparation_service = submission_preparation_service

    def create_agreement(
        self,
        *,
        subject: RequestSubject,
        title: str | None,
        source_url: str | None,
        agreed_at: datetime | None,
        terms_text: str,
    ) -> StoredAgreement:
        """Persist agreement text for later manual analysis."""

        normalized_terms_text = self._submission_preparation_service.prepare_terms_text_for_storage(
            terms_text=terms_text
        )
        normalized_title = self._submission_preparation_service.normalize_optional_metadata_value(
            title
        )
        normalized_source_url = (
            self._submission_preparation_service.normalize_optional_metadata_value(source_url)
        )

        return self._agreement_repository.create(
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            title=normalized_title,
            source_url=normalized_source_url,
            agreed_at=agreed_at,
            terms_text=normalized_terms_text,
        )

    def submit_and_analyze(
        self,
        *,
        subject: RequestSubject,
        submission: AnalysisSubmission,
    ) -> StoredReport:
        """Run end-to-end flow: prepare source, persist agreement, analyze, store report."""

        ingestion_result = self._submission_preparation_service.prepare_submission(
            submission=submission
        )
        agreement = self._agreement_repository.create(
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            title=ingestion_result.title,
            source_url=ingestion_result.source_url,
            agreed_at=ingestion_result.agreed_at,
            terms_text=ingestion_result.normalized_text,
        )
        return self._execute_analysis_and_persist_report(
            subject=subject,
            agreement=agreement,
            ingestion_result=ingestion_result,
        )

    def trigger_manual_analysis(
        self, *, subject: RequestSubject, agreement_id: UUID
    ) -> StoredReport:
        """Analyze an existing agreement and persist a new report."""

        agreement = self._agreement_repository.get_for_subject(
            agreement_id=agreement_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )
        if agreement is None:
            raise AgreementNotFoundError(f"Agreement {agreement_id} was not found.")

        ingestion_result = (
            self._submission_preparation_service.prepare_existing_agreement_for_analysis(
                title=agreement.title,
                source_url=agreement.source_url,
                agreed_at=agreement.agreed_at,
                terms_text=agreement.terms_text,
            )
        )
        return self._execute_analysis_and_persist_report(
            subject=subject,
            agreement=agreement,
            ingestion_result=ingestion_result,
        )

    def list_reports(self, *, subject: RequestSubject) -> list[StoredReport]:
        """Return newest-first report history scoped to the request subject."""

        return self._report_repository.list_for_subject(
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )

    def get_report(self, *, subject: RequestSubject, report_id: UUID) -> StoredReport:
        """Return a single report owned by the request subject."""

        report = self._report_repository.get_for_subject(
            report_id=report_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )
        if report is None:
            raise ReportNotFoundError(f"Report {report_id} was not found.")
        return report

    def _execute_analysis_and_persist_report(
        self,
        *,
        subject: RequestSubject,
        agreement: StoredAgreement,
        ingestion_result: ExtractionIngestionResult,
    ) -> StoredReport:
        """Execute report generation through the configured execution strategy.

        Orchestration passes the ingestion DTO through unchanged so execution
        mode implementations (sync today, queued later) own provider-adaptation
        details and persistence timing.
        """

        return self._analysis_execution_strategy.execute(
            request=AnalysisExecutionRequest(
                subject_type=subject.subject_type,
                subject_id=subject.subject_id,
                agreement=agreement,
                ingestion_result=ingestion_result,
            )
        )
