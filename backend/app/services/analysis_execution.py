"""Internal analysis execution seam for sync-vs-queued evolution.

Purpose:
- encapsulate how analysis is executed and persisted as reports
- keep orchestration focused on workflow coordination
- provide a mode-based seam so future queued/worker execution can replace
  sync behavior without changing route contracts

Current state:
- only synchronous in-request execution is implemented
- unknown/unsupported modes safely fall back to synchronous execution
"""

from dataclasses import dataclass
from logging import getLogger
from typing import Protocol

from ..repositories.analysis_status import AnalysisLifecycleStatus
from ..repositories.interfaces import ReportRepository
from ..repositories.models import StoredAgreement, StoredReport
from .extraction_contracts import ExtractionIngestionResult
from .ai_provider import AnalysisInput, AnalysisInputMetadata, AnalysisProvider

LOGGER = getLogger(__name__)

DEFAULT_ANALYSIS_EXECUTION_MODE = "sync"

__all__ = [
    "AnalysisExecutionRequest",
    "AnalysisExecutionStrategy",
    "DEFAULT_ANALYSIS_EXECUTION_MODE",
    "SyncAnalysisExecutionStrategy",
    "build_analysis_execution_strategy",
]


@dataclass(frozen=True)
class AnalysisExecutionRequest:
    """Execution payload required to produce and persist one report.

    `ingestion_result` is the service-boundary payload produced by submission
    preparation/ingestion. Keeping execution input centered on this DTO helps
    future queued-worker modes consume the same prepared payload shape.
    """

    subject_type: str
    subject_id: str
    agreement: StoredAgreement
    ingestion_result: ExtractionIngestionResult


class AnalysisExecutionStrategy(Protocol):
    """Execution-mode contract used by orchestration."""

    def execute(self, *, request: AnalysisExecutionRequest) -> StoredReport: ...


class SyncAnalysisExecutionStrategy:
    """Synchronous execution strategy used by current HTTP request flow."""

    def __init__(
        self,
        *,
        analysis_provider: AnalysisProvider,
        report_repository: ReportRepository,
    ) -> None:
        self._analysis_provider = analysis_provider
        self._report_repository = report_repository

    def execute(self, *, request: AnalysisExecutionRequest) -> StoredReport:
        """Run provider analysis inline and persist a completed report."""

        provider_result = self._analysis_provider.analyze(
            analysis_input=AnalysisInput(
                source_type=request.ingestion_result.source_type,
                source_value=request.ingestion_result.source_value,
                normalized_text=request.agreement.terms_text,
                metadata=_to_analysis_input_metadata(request.ingestion_result),
            )
        )
        return self._report_repository.create(
            agreement_id=request.agreement.id,
            subject_type=request.subject_type,
            subject_id=request.subject_id,
            source_type=request.ingestion_result.source_type,
            source_value=request.ingestion_result.source_value,
            raw_input_excerpt=request.ingestion_result.raw_input_excerpt,
            status=AnalysisLifecycleStatus.COMPLETED,
            summary=provider_result.summary,
            trust_score=provider_result.trust_score,
            model_name=provider_result.model_name,
            flagged_clauses=provider_result.flagged_clauses,
            completed_at=provider_result.completed_at,
        )


def build_analysis_execution_strategy(
    *,
    mode: str,
    analysis_provider: AnalysisProvider,
    report_repository: ReportRepository,
) -> AnalysisExecutionStrategy:
    """Return the configured execution strategy; currently sync-only."""

    normalized_mode = mode.strip().lower()
    if normalized_mode in {"", DEFAULT_ANALYSIS_EXECUTION_MODE}:
        return SyncAnalysisExecutionStrategy(
            analysis_provider=analysis_provider,
            report_repository=report_repository,
        )

    # Future modes (for example queued worker execution) should be added here.
    LOGGER.warning(
        "Unsupported ANALYSIS_EXECUTION_MODE '%s'; falling back to synchronous execution.",
        mode,
    )
    return SyncAnalysisExecutionStrategy(
        analysis_provider=analysis_provider,
        report_repository=report_repository,
    )


def _to_analysis_input_metadata(
    ingestion_result: ExtractionIngestionResult,
) -> AnalysisInputMetadata:
    """Adapt ingestion metadata to provider input metadata at the execution seam.

    This keeps provider-contract details out of orchestration and routes.
    When execution moves to queued workers, the same adapter can be reused in
    worker consumers without changing submission/orchestration contracts.
    """

    return AnalysisInputMetadata(
        source_kind=ingestion_result.source_kind.value,
        extraction_strategy=ingestion_result.metadata.extraction_strategy,
        extractor_name=ingestion_result.metadata.extractor_name,
        extraction_confidence=ingestion_result.metadata.confidence,
        extraction_warnings=ingestion_result.metadata.warnings,
        extraction_errors=ingestion_result.metadata.errors,
        trace_id=None,
        attributes={},
    )
