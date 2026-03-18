from datetime import datetime, timezone
import uuid

import pytest

from app.repositories.in_memory import (
    InMemoryAgreementRepository,
    InMemoryReportRepository,
    InMemoryStorage,
)
from app.repositories.analysis_status import AnalysisLifecycleStatus
from app.services.ai_provider import DeterministicAnalysisProvider
from app.services.analysis_execution import SyncAnalysisExecutionStrategy
from app.services.analysis_service import (
    AgreementNotFoundError,
    AnalysisOrchestrationService,
    AnalysisSubmission,
    InvalidSubmissionError,
    RequestSubject,
)
from app.services.content_ingestion import ContentIngestionService, UrlFetchPayload
from app.services.submission_preparation import SubmissionPreparationService


class _StaticUrlFetcher:
    def __init__(self, payload: UrlFetchPayload) -> None:
        self._payload = payload

    def fetch(self, *, url: str) -> UrlFetchPayload:
        _ = url
        return self._payload


def _build_service(
    *,
    submission_preparation_service: SubmissionPreparationService | None = None,
) -> tuple[AnalysisOrchestrationService, InMemoryAgreementRepository]:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)
    service = AnalysisOrchestrationService(
        agreement_repository=agreement_repository,
        report_repository=report_repository,
        analysis_execution_strategy=SyncAnalysisExecutionStrategy(
            analysis_provider=DeterministicAnalysisProvider(),
            report_repository=report_repository,
        ),
        submission_preparation_service=(
            submission_preparation_service or SubmissionPreparationService()
        ),
    )
    return service, agreement_repository


def test_submit_and_analyze_returns_summary_flags_and_trust_score() -> None:
    service, _agreement_repository = _build_service()
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    report = service.submit_and_analyze(
        subject=subject,
        submission=AnalysisSubmission(
            title="Service Terms",
            source_url="https://service.example/terms",
            agreed_at=datetime.now(timezone.utc),
            terms_text=(
                "These terms include arbitration, class action waiver, and automatic renewal."
            ),
        ),
    )

    assert report.summary
    assert 0 <= report.trust_score <= 100
    assert report.flagged_clauses
    assert report.source_type == "url"
    assert report.source_value == "https://service.example/terms"


def test_submit_and_analyze_rejects_missing_input() -> None:
    service, _agreement_repository = _build_service()
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    with pytest.raises(InvalidSubmissionError):
        service.submit_and_analyze(
            subject=subject,
            submission=AnalysisSubmission(
                title=None,
                source_url=None,
                agreed_at=None,
                terms_text=None,
            ),
        )


def test_trigger_manual_analysis_raises_when_agreement_not_found() -> None:
    service, _agreement_repository = _build_service()
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    with pytest.raises(AgreementNotFoundError):
        service.trigger_manual_analysis(subject=subject, agreement_id=uuid.uuid4())


def test_trigger_manual_analysis_uses_prepared_source_fields() -> None:
    service, _agreement_repository = _build_service()
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")
    agreement = service.create_agreement(
        subject=subject,
        title="Demo Terms",
        source_url="https://demo.example/terms",
        agreed_at=None,
        terms_text=(
            "These terms include arbitration and automatic renewal clauses that "
            "are long enough for analysis."
        ),
    )

    report = service.trigger_manual_analysis(subject=subject, agreement_id=agreement.id)

    assert report.source_type == "url"
    assert report.source_value == "https://demo.example/terms"


def test_submit_and_analyze_url_only_uses_ingested_fetched_content() -> None:
    submission_preparation_service = SubmissionPreparationService(
        content_ingestion_service=ContentIngestionService(
            url_content_fetcher=_StaticUrlFetcher(
                UrlFetchPayload(
                    body_text=(
                        "<html><body><h1>Terms</h1>"
                        "<p>These terms include arbitration and automatic renewal clauses."
                        "</p></body></html>"
                    ),
                    content_type="text/html",
                )
            )
        )
    )
    service, agreement_repository = _build_service(
        submission_preparation_service=submission_preparation_service
    )
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    report = service.submit_and_analyze(
        subject=subject,
        submission=AnalysisSubmission(
            title="Fetched Terms",
            source_url="https://service.example/terms",
            agreed_at=None,
            terms_text=None,
        ),
    )

    agreement = agreement_repository.get_for_subject(
        agreement_id=report.agreement_id,
        subject_type=subject.subject_type,
        subject_id=subject.subject_id,
    )
    assert agreement is not None
    assert "could not be fetched" not in agreement.terms_text.lower()
    assert "arbitration" in agreement.terms_text.lower()
    assert report.status == AnalysisLifecycleStatus.COMPLETED
    assert report.source_type == "url"
    assert "could not be fetched" not in report.raw_input_excerpt.lower()
