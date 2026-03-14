"""Service layer for agreement/report orchestration.

Route handlers delegate to this module so HTTP transport concerns stay thin and
all workflow decisions remain testable in one place.
"""

from dataclasses import dataclass
from datetime import datetime
import re
from uuid import UUID

from ..repositories.interfaces import AgreementRepository, ReportRepository
from ..repositories.models import StoredAgreement, StoredReport
from .ai_provider import AnalysisInput, AnalysisProvider


@dataclass(frozen=True)
class RequestSubject:
    """Identity tuple used for owner-scoped data access."""

    subject_type: str
    subject_id: str


@dataclass(frozen=True)
class AnalysisSubmission:
    """Input payload for one-shot submit-and-analyze flow."""

    title: str | None
    source_url: str | None
    agreed_at: datetime | None
    terms_text: str | None


@dataclass(frozen=True)
class PreparedSubmission:
    """Normalized and validated submission used internally by the service."""

    title: str | None
    source_url: str | None
    agreed_at: datetime | None
    normalized_terms_text: str
    source_type: str
    source_value: str
    raw_input_excerpt: str


class AgreementNotFoundError(Exception):
    pass


class ReportNotFoundError(Exception):
    pass


class InvalidSubmissionError(Exception):
    pass


class AnalysisOrchestrationService:
    """Orchestrates agreement creation, analysis execution, and report persistence.

    Layer: business/service logic.
    This class is intentionally independent from FastAPI and database details.
    """

    def __init__(
        self,
        *,
        agreement_repository: AgreementRepository,
        report_repository: ReportRepository,
        analysis_provider: AnalysisProvider,
    ) -> None:
        self._agreement_repository = agreement_repository
        self._report_repository = report_repository
        self._analysis_provider = analysis_provider

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

        normalized_terms_text = self._normalize_text(terms_text)
        if len(normalized_terms_text) < 20:
            raise InvalidSubmissionError("Agreement text must be at least 20 characters.")

        return self._agreement_repository.create(
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            title=title.strip() if title else None,
            source_url=source_url.strip() if source_url else None,
            agreed_at=agreed_at,
            terms_text=normalized_terms_text,
        )

    def submit_and_analyze(
        self,
        *,
        subject: RequestSubject,
        submission: AnalysisSubmission,
    ) -> StoredReport:
        """Run end-to-end flow: validate input, save agreement, analyze, save report."""

        prepared = self._prepare_submission(submission)
        agreement = self._agreement_repository.create(
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            title=prepared.title,
            source_url=prepared.source_url,
            agreed_at=prepared.agreed_at,
            terms_text=prepared.normalized_terms_text,
        )
        return self._create_report_from_agreement(
            subject=subject,
            agreement=agreement,
            source_type=prepared.source_type,
            source_value=prepared.source_value,
            raw_input_excerpt=prepared.raw_input_excerpt,
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

        source_type = "url" if agreement.source_url else "text"
        source_value = agreement.source_url or agreement.title or "manual_text_submission"
        raw_input_excerpt = self._build_excerpt(agreement.terms_text)
        return self._create_report_from_agreement(
            subject=subject,
            agreement=agreement,
            source_type=source_type,
            source_value=source_value,
            raw_input_excerpt=raw_input_excerpt,
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

    def _prepare_submission(self, submission: AnalysisSubmission) -> PreparedSubmission:
        """Normalize input and enforce required content rules for analysis."""

        title = submission.title.strip() if submission.title else None
        source_url = submission.source_url.strip() if submission.source_url else None
        terms_text = self._normalize_text(submission.terms_text or "")

        if not terms_text and not source_url:
            raise InvalidSubmissionError("Provide either terms_text or source_url.")

        if source_url:
            source_type = "url"
            source_value = source_url
        else:
            source_type = "text"
            source_value = title or "manual_text_submission"

        if not terms_text:
            terms_text = (
                f"Terms and conditions were submitted with URL {source_url}. "
                "The full terms text was not provided in this request."
            )

        if len(terms_text) < 20:
            raise InvalidSubmissionError("Submission content must be at least 20 characters.")

        return PreparedSubmission(
            title=title,
            source_url=source_url,
            agreed_at=submission.agreed_at,
            normalized_terms_text=terms_text,
            source_type=source_type,
            source_value=source_value,
            raw_input_excerpt=self._build_excerpt(terms_text),
        )

    def _create_report_from_agreement(
        self,
        *,
        subject: RequestSubject,
        agreement: StoredAgreement,
        source_type: str,
        source_value: str,
        raw_input_excerpt: str,
    ) -> StoredReport:
        """Delegate text analysis to provider and persist completed report."""

        provider_result = self._analysis_provider.analyze(
            analysis_input=AnalysisInput(
                source_type=source_type,
                source_value=source_value,
                normalized_text=agreement.terms_text,
            )
        )
        return self._report_repository.create(
            agreement_id=agreement.id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
            source_type=source_type,
            source_value=source_value,
            raw_input_excerpt=raw_input_excerpt,
            status="completed",
            summary=provider_result.summary,
            trust_score=provider_result.trust_score,
            model_name=provider_result.model_name,
            flagged_clauses=provider_result.flagged_clauses,
            completed_at=provider_result.completed_at,
        )

    def _normalize_text(self, value: str) -> str:
        """Collapse whitespace to keep storage and keyword matching deterministic."""

        return re.sub(r"\s+", " ", value).strip()

    def _build_excerpt(self, text: str, max_length: int = 280) -> str:
        """Create a short report excerpt for list/detail displays."""

        normalized = self._normalize_text(text)
        return normalized[:max_length]
