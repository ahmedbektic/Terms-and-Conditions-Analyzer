"""Submission/source preparation service for analysis orchestration.

Responsibilities in this module:
- normalize raw user input text
- adapt current one-shot API payloads into extraction ingestion requests
- delegate ingestion execution to the content-ingestion boundary

Dependencies:
- standard library (`dataclasses`, `datetime`, `regex`)
- backend-internal extraction DTOs from `extraction_contracts.py`
- backend ingestion boundary from `content_ingestion.py`

Used by:
- `AnalysisOrchestrationService` in `analysis_service.py`

Architectural boundary:
- This keeps source-preparation concerns out of orchestration workflow code.
- URL fetch/extract internals live in `content_ingestion.py`.
"""

from dataclasses import dataclass
from datetime import datetime
import re

from .content_ingestion import (
    ContentIngestionError,
    ContentIngestionService,
    MIN_ANALYZABLE_TEXT_LENGTH,
)
from .extraction_contracts import (
    ExtractionIngestionRequest,
    ExtractionIngestionResult,
    ExtractionSourceKind,
)


@dataclass(frozen=True)
class AnalysisSubmission:
    """Input payload for one-shot submit-and-analyze flow."""

    title: str | None
    source_url: str | None
    agreed_at: datetime | None
    terms_text: str | None


@dataclass(frozen=True)
class ResolvedIngestionSource:
    """Resolved source identity used for ingestion requests."""

    source_kind: ExtractionSourceKind
    original_source_value: str


class InvalidSubmissionError(Exception):
    """Raised when source text or metadata cannot be prepared safely."""


class SubmissionPreparationService:
    """Prepare request payloads before orchestration persists or analyzes them.

    This adapter keeps route-facing payload semantics stable while the
    ingestion implementation evolves behind `ContentIngestionService`.
    """

    def __init__(
        self,
        *,
        content_ingestion_service: ContentIngestionService | None = None,
    ) -> None:
        self._content_ingestion_service = (
            content_ingestion_service or ContentIngestionService()
        )

    def prepare_terms_text_for_storage(self, *, terms_text: str) -> str:
        """Normalize and validate direct agreement text submissions."""

        normalized_terms_text = self.normalize_text(terms_text)
        if len(normalized_terms_text) < MIN_ANALYZABLE_TEXT_LENGTH:
            raise InvalidSubmissionError("Agreement text must be at least 20 characters.")
        return normalized_terms_text

    def prepare_submission(
        self, *, submission: AnalysisSubmission
    ) -> ExtractionIngestionResult:
        """Prepare legacy one-shot API payloads into extraction boundary DTOs."""

        normalized_title = self._normalize_optional_value(submission.title)
        normalized_source_url = self._normalize_optional_value(submission.source_url)
        normalized_terms_text = self.normalize_text(submission.terms_text or "")

        if not normalized_terms_text and not normalized_source_url:
            raise InvalidSubmissionError("Provide either terms_text or source_url.")

        resolved_source = self._resolve_ingestion_source(
            normalized_source_url=normalized_source_url,
            normalized_title=normalized_title,
        )

        return self.prepare_ingestion_request(
            request=ExtractionIngestionRequest(
                source_kind=resolved_source.source_kind,
                original_source_value=resolved_source.original_source_value,
                submitted_text=normalized_terms_text or None,
                title=normalized_title,
                agreed_at=submission.agreed_at,
                source_metadata={},
            )
        )

    def prepare_existing_agreement_for_analysis(
        self,
        *,
        title: str | None,
        source_url: str | None,
        agreed_at: datetime | None,
        terms_text: str,
    ) -> ExtractionIngestionResult:
        """Prepare persisted agreement content for a manual analysis run.

        This keeps manual-analysis source interpretation aligned with the same
        ingestion boundary used by one-shot submission flow.
        """

        normalized_title = self._normalize_optional_value(title)
        normalized_source_url = self._normalize_optional_value(source_url)

        resolved_source = self._resolve_ingestion_source(
            normalized_source_url=normalized_source_url,
            normalized_title=normalized_title,
        )

        return self.prepare_ingestion_request(
            request=ExtractionIngestionRequest(
                source_kind=resolved_source.source_kind,
                original_source_value=resolved_source.original_source_value,
                submitted_text=terms_text,
                title=normalized_title,
                agreed_at=agreed_at,
                source_metadata={"ingestion_origin": "stored_agreement"},
            )
        )

    def prepare_ingestion_request(
        self, *, request: ExtractionIngestionRequest
    ) -> ExtractionIngestionResult:
        """Delegate ingestion request execution to the ingestion boundary."""

        normalized_request = ExtractionIngestionRequest(
            source_kind=request.source_kind,
            original_source_value=self.normalize_text(request.original_source_value),
            submitted_text=self._normalize_optional_value(request.submitted_text),
            title=self._normalize_optional_value(request.title),
            agreed_at=request.agreed_at,
            source_metadata=dict(request.source_metadata),
        )
        try:
            return self._content_ingestion_service.ingest(request=normalized_request)
        except ContentIngestionError as error:
            raise InvalidSubmissionError(str(error)) from error

    def normalize_optional_metadata_value(self, value: str | None) -> str | None:
        """Normalize optional title/source metadata fields for persistence."""

        return self._normalize_optional_value(value)

    def normalize_text(self, value: str) -> str:
        """Collapse whitespace to keep storage and analysis inputs deterministic."""

        return re.sub(r"\s+", " ", value).strip()

    def _normalize_optional_value(self, value: str | None) -> str | None:
        """Normalize optional strings and collapse empty values to `None`."""

        if value is None:
            return None
        normalized = self.normalize_text(value)
        return normalized or None

    def _resolve_ingestion_source(
        self,
        *,
        normalized_source_url: str | None,
        normalized_title: str | None,
    ) -> ResolvedIngestionSource:
        """Resolve source identity for ingestion requests.

        This central helper ensures one-shot and manual-analysis flows stay
        aligned as source-resolution rules evolve (for example extension source
        kinds or richer non-URL source identifiers).
        """

        if normalized_source_url:
            return ResolvedIngestionSource(
                source_kind=ExtractionSourceKind.URL,
                original_source_value=normalized_source_url,
            )

        return ResolvedIngestionSource(
            source_kind=ExtractionSourceKind.RAW_TEXT,
            original_source_value=normalized_title or "manual_text_submission",
        )
