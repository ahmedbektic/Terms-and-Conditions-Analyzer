"""Dependency providers for API routes.

Repository implementations are selected via config so routes/services remain
unchanged whether persistence is memory or Postgres/Supabase.
"""

from fastapi import Header, HTTPException

from ..auth import (
    AuthSubjectResolver,
    SubjectResolutionError,
    build_request_subject_resolver,
)

from ..core.config import settings
from ..repositories.in_memory import (
    InMemoryAgreementRepository,
    InMemoryReportRepository,
    InMemoryStorage,
)
from ..services.ai_provider import AnalysisProviderRuntimeConfig, build_analysis_provider
from ..services.analysis_service import AnalysisOrchestrationService, RequestSubject
from ..services.content_ingestion import ContentIngestionService
from ..services.analysis_execution import build_analysis_execution_strategy
from ..services.submission_preparation import SubmissionPreparationService


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


_agreement_repository, _report_repository, _persistence_storage = _build_persistence_dependencies()
# Provider selection is runtime-configured; deterministic remains the safe default
# when AI mode is disabled or missing required credentials. In AI mode, Gemini
# is the preferred provider kind unless ANALYSIS_AI_PROVIDER_KIND is overridden.
_analysis_provider = build_analysis_provider(
    config=AnalysisProviderRuntimeConfig(
        mode=settings.analysis_provider_mode,
        ai_provider_kind=settings.analysis_ai_provider_kind,
        ai_timeout_seconds=settings.analysis_ai_timeout_seconds,
        ai_temperature=settings.analysis_ai_temperature,
        ai_fallback_to_deterministic=settings.analysis_ai_fallback_to_deterministic,
        openai_compatible_api_key=settings.analysis_openai_compatible_api_key,
        openai_compatible_model_name=settings.analysis_openai_compatible_model,
        openai_compatible_base_url=settings.analysis_openai_compatible_base_url,
        gemini_api_key=settings.analysis_gemini_api_key,
        gemini_model_name=settings.analysis_gemini_model,
        gemini_base_url=settings.analysis_gemini_base_url,
    )
)
_analysis_execution_strategy = build_analysis_execution_strategy(
    # This mode seam keeps request-path sync behavior today while allowing
    # future queued/worker execution to be introduced behind the same service.
    mode=settings.analysis_execution_mode,
    analysis_provider=_analysis_provider,
    report_repository=_report_repository,
)
_content_ingestion_service = ContentIngestionService()
_submission_preparation_service = SubmissionPreparationService(
    content_ingestion_service=_content_ingestion_service
)
_analysis_service = AnalysisOrchestrationService(
    agreement_repository=_agreement_repository,
    report_repository=_report_repository,
    analysis_execution_strategy=_analysis_execution_strategy,
    submission_preparation_service=_submission_preparation_service,
)


def _build_subject_resolver() -> AuthSubjectResolver:
    """Create auth subject resolver with startup-time config validation.

    This is the only place that wires verifier + ownership policy settings.
    Routes consume `get_request_subject` and stay unaware of verification details.
    """

    return build_request_subject_resolver(
        jwt_secret=settings.supabase_jwt_secret,
        jwks_url=settings.effective_supabase_jwks_url,
        expected_issuer=settings.effective_supabase_jwt_issuer,
        expected_audience=settings.supabase_jwt_audience,
        require_signature_verification=settings.auth_require_jwt_signature_verification,
        jwks_cache_ttl_seconds=settings.supabase_jwks_cache_ttl_seconds,
        jwks_http_timeout_seconds=settings.supabase_jwks_http_timeout_seconds,
        jwt_leeway_seconds=settings.supabase_jwt_leeway_seconds,
    )


_request_subject_resolver = _build_subject_resolver()


def get_analysis_service() -> AnalysisOrchestrationService:
    """Return the singleton orchestration service used by request handlers."""

    return _analysis_service


def get_request_subject(
    authorization: str | None = Header(default=None),
) -> RequestSubject:
    """Resolve the owner subject from auth headers.

    Dashboard and future extension callers share this transport boundary:
    - `Authorization: Bearer <supabase_access_token>` for authenticated access

    Request flow:
    1) extract auth headers from transport
    2) resolve owner from bearer token
    3) map to service-layer `RequestSubject`

    This keeps auth parsing/verification at the dependency layer so services
    and repositories continue to operate on abstract ownership fields only.
    extension callers should reuse the same Bearer-token path.
    """

    try:
        resolved = _request_subject_resolver.resolve(
            authorization_header=authorization,
        )
    except SubjectResolutionError as error:
        raise HTTPException(status_code=error.status_code, detail=error.detail) from error

    return RequestSubject(
        subject_type=resolved.subject_type,
        subject_id=resolved.subject_id,
    )


def reset_demo_storage() -> None:
    """Testing utility for clearing temporary storage state.

    Note: test suites may also monkeypatch `_request_subject_resolver` to run
    deterministic auth-mode scenarios without process-level env rewiring.
    """

    clear_method = getattr(_persistence_storage, "clear", None)
    if callable(clear_method):
        clear_method()
