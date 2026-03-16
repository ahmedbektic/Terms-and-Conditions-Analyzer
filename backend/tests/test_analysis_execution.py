from app.repositories.in_memory import (
    InMemoryAgreementRepository,
    InMemoryReportRepository,
    InMemoryStorage,
)
from app.repositories.analysis_status import AnalysisLifecycleStatus
from app.services.ai_provider import DeterministicAnalysisProvider
from app.services.analysis_execution import (
    AnalysisExecutionRequest,
    SyncAnalysisExecutionStrategy,
    build_analysis_execution_strategy,
)
from app.services.extraction_contracts import (
    ExtractionIngestionResult,
    ExtractionMetadata,
    ExtractionSourceKind,
)


def test_build_analysis_execution_strategy_defaults_to_sync() -> None:
    storage = InMemoryStorage()
    strategy = build_analysis_execution_strategy(
        mode="sync",
        analysis_provider=DeterministicAnalysisProvider(),
        report_repository=InMemoryReportRepository(storage),
    )

    assert isinstance(strategy, SyncAnalysisExecutionStrategy)


def test_build_analysis_execution_strategy_falls_back_for_unknown_mode() -> None:
    storage = InMemoryStorage()
    strategy = build_analysis_execution_strategy(
        mode="queued",
        analysis_provider=DeterministicAnalysisProvider(),
        report_repository=InMemoryReportRepository(storage),
    )

    assert isinstance(strategy, SyncAnalysisExecutionStrategy)


def test_sync_execution_strategy_creates_completed_report() -> None:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)
    strategy = SyncAnalysisExecutionStrategy(
        analysis_provider=DeterministicAnalysisProvider(),
        report_repository=report_repository,
    )
    agreement = agreement_repository.create(
        subject_type="supabase_user",
        subject_id="user-a",
        title="Terms",
        source_url="https://example.com/terms",
        agreed_at=None,
        terms_text="These terms include arbitration and automatic renewal clauses.",
    )

    report = strategy.execute(
        request=AnalysisExecutionRequest(
            subject_type="supabase_user",
            subject_id="user-a",
            agreement=agreement,
            ingestion_result=ExtractionIngestionResult(
                source_kind=ExtractionSourceKind.URL,
                original_source_value="https://example.com/terms",
                normalized_text=(
                    "These terms include arbitration and automatic renewal clauses."
                ),
                source_type="url",
                source_value="https://example.com/terms",
                raw_input_excerpt=(
                    "These terms include arbitration and automatic renewal clauses."
                ),
                title="Terms",
                source_url="https://example.com/terms",
                agreed_at=None,
                metadata=ExtractionMetadata(
                    extraction_strategy="url_with_submitted_text",
                    extractor_name="test",
                ),
            ),
        )
    )

    assert report.status == AnalysisLifecycleStatus.COMPLETED
    assert report.model_name
    assert report.summary
