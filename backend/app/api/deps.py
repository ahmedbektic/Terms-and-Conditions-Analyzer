"""Dependency providers for API routes.

Repository implementations are selected via config so routes/services remain
unchanged whether persistence is memory or Postgres/Supabase.
"""

from fastapi import Header, HTTPException, status

from ..core.config import settings
from ..repositories.in_memory import (
    InMemoryAgreementRepository,
    InMemoryReportRepository,
    InMemoryStorage,
)
from ..services.ai_provider import DeterministicAnalysisProvider
from ..services.analysis_service import AnalysisOrchestrationService, RequestSubject


def _build_persistence_dependencies():
    """Create repository/storage objects based on configured persistence backend."""

    backend = settings.persistence_backend
    if backend == "postgres":
        database_url = settings.effective_database_url
        if not database_url:
            raise RuntimeError(
                "PERSISTENCE_BACKEND=postgres requires SUPABASE_DATABASE_URL or DATABASE_URL."
            )

        from ..persistence.postgres import (  # Imported lazily to keep memory-mode lightweight.
            PostgresAgreementRepository,
            PostgresReportRepository,
            PostgresStorage,
        )

        storage = PostgresStorage(
            database_url=database_url,
            auto_create_schema=settings.postgres_auto_create_schema,
        )
        agreement_repository = PostgresAgreementRepository(storage)
        report_repository = PostgresReportRepository(storage)
        return agreement_repository, report_repository, storage

    if backend not in {"memory", ""}:
        raise RuntimeError(
            f"Unsupported PERSISTENCE_BACKEND value: {backend}. Expected 'memory' or 'postgres'."
        )

    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)
    return agreement_repository, report_repository, storage


_agreement_repository, _report_repository, _persistence_storage = (
    _build_persistence_dependencies()
)
_analysis_provider = DeterministicAnalysisProvider()
_analysis_service = AnalysisOrchestrationService(
    agreement_repository=_agreement_repository,
    report_repository=_report_repository,
    analysis_provider=_analysis_provider,
)


def get_analysis_service() -> AnalysisOrchestrationService:
    """Return the singleton orchestration service used by request handlers."""

    return _analysis_service


def get_request_subject(x_session_id: str | None = Header(default=None)) -> RequestSubject:
    """Resolve the caller identity used for owner-scoped report access.

    TODO: Replace session-header extraction with auth-token/JWT subject extraction
    once authentication is introduced.
    """

    if not x_session_id:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail="Missing required X-Session-Id header.",
        )
    return RequestSubject(subject_type="anonymous_session", subject_id=x_session_id)


def reset_demo_storage() -> None:
    """Testing utility for clearing temporary storage state."""

    clear_method = getattr(_persistence_storage, "clear", None)
    if callable(clear_method):
        clear_method()
