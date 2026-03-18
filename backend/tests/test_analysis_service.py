from datetime import datetime, timezone
import uuid

import pytest

from app.repositories.in_memory import (
    InMemoryAgreementRepository,
    InMemoryReportRepository,
    InMemoryStorage,
)
from app.services.ai_provider import DeterministicAnalysisProvider
from app.services.analysis_service import (
    AgreementNotFoundError,
    AnalysisOrchestrationService,
    AnalysisSubmission,
    InvalidSubmissionError,
    RequestSubject,
)


def _build_service() -> AnalysisOrchestrationService:
    storage = InMemoryStorage()
    return AnalysisOrchestrationService(
        agreement_repository=InMemoryAgreementRepository(storage),
        report_repository=InMemoryReportRepository(storage),
        analysis_provider=DeterministicAnalysisProvider(),
    )


def test_submit_and_analyze_returns_summary_flags_and_trust_score() -> None:
    service = _build_service()
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
    service = _build_service()
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
    service = _build_service()
    subject = RequestSubject(subject_type="supabase_user", subject_id="user-a")

    with pytest.raises(AgreementNotFoundError):
        service.trigger_manual_analysis(subject=subject, agreement_id=uuid.uuid4())
