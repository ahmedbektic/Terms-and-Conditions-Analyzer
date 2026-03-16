"""Backend content-ingestion boundary for analysis preparation.

Purpose:
- prepare normalized text from ingestion requests
- support direct submitted text and URL fetch/extract paths
- emit stable extraction result DTOs with metadata for future upgrades

Dependencies:
- extraction DTOs (`extraction_contracts.py`)
- `httpx` for URL acquisition in sync MVP mode

Used by:
- `SubmissionPreparationService` as the ingestion execution boundary

Upgrade seam:
- URL fetch and extraction are intentionally encapsulated so richer fetchers,
  parsers, or queued worker execution can replace internals without changing
  orchestration or route contracts.
"""

from dataclasses import dataclass
from html import unescape
import re
from typing import Protocol
from urllib.parse import urlparse

import httpx

from .extraction_contracts import (
    ExtractionIngestionRequest,
    ExtractionIngestionResult,
    ExtractionMetadata,
    ExtractionSourceKind,
)


MIN_ANALYZABLE_TEXT_LENGTH = 20
DEFAULT_EXCERPT_MAX_LENGTH = 280
DEFAULT_INGEST_TIMEOUT_SECONDS = 8.0
DEFAULT_MAX_INGEST_CHARACTERS = 200_000


class ContentIngestionError(Exception):
    """Raised when content ingestion cannot produce usable analysis text."""


@dataclass(frozen=True)
class UrlFetchPayload:
    """Raw URL response payload from the fetch layer."""

    body_text: str
    content_type: str


class UrlContentFetcher(Protocol):
    """Protocol for swappable URL content acquisition implementations."""

    def fetch(self, *, url: str) -> UrlFetchPayload: ...


class FetchedContentExtractor(Protocol):
    """Protocol for swappable fetched-content extraction implementations."""

    def extract(self, *, body_text: str, content_type: str) -> tuple[str, str]: ...


class HttpxUrlContentFetcher:
    """HTTP fetcher implementation for sync MVP ingestion."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_INGEST_TIMEOUT_SECONDS,
    ) -> None:
        self._timeout_seconds = timeout_seconds

    def fetch(self, *, url: str) -> UrlFetchPayload:
        """Fetch URL content and return body text plus response content type."""

        parsed = urlparse(url)
        if parsed.scheme not in {"http", "https"}:
            raise ContentIngestionError("URL ingestion supports only http/https sources.")

        response = httpx.get(
            url,
            follow_redirects=True,
            timeout=self._timeout_seconds,
            headers={
                "User-Agent": (
                    "TermsAnalyzerBot/0.1 (+https://example.invalid/content-ingestion)"
                )
            },
        )
        response.raise_for_status()
        return UrlFetchPayload(
            body_text=response.text,
            content_type=response.headers.get("content-type", ""),
        )


class SimpleFetchedContentExtractor:
    """Lightweight fetched-content extractor for sync MVP ingestion.

    This extraction strategy is intentionally simple. It is designed to be
    replaced later by richer HTML/article extraction while preserving the same
    ingestion service interface.
    """

    def extract(self, *, body_text: str, content_type: str) -> tuple[str, str]:
        normalized_content_type = content_type.lower()
        if "html" in normalized_content_type or self._looks_like_html(body_text):
            return self._extract_text_from_html(body_text), "url_fetch_html_tag_strip"
        return self._normalize_text(unescape(body_text)), "url_fetch_plain_text"

    def _extract_text_from_html(self, html_text: str) -> str:
        """Extract plain text from HTML via lightweight regex-based stripping."""

        without_scripts = re.sub(
            r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>",
            " ",
            html_text,
        )
        without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
        return self._normalize_text(unescape(without_tags))

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def _looks_like_html(self, text: str) -> bool:
        lowered = text.lower()
        return "<html" in lowered or "<body" in lowered or "<div" in lowered


class ContentIngestionService:
    """Prepare extraction ingestion requests into normalized analysis text."""

    def __init__(
        self,
        *,
        url_content_fetcher: UrlContentFetcher | None = None,
        fetched_content_extractor: FetchedContentExtractor | None = None,
        max_ingest_characters: int = DEFAULT_MAX_INGEST_CHARACTERS,
    ) -> None:
        self._url_content_fetcher = url_content_fetcher or HttpxUrlContentFetcher()
        self._fetched_content_extractor = (
            fetched_content_extractor or SimpleFetchedContentExtractor()
        )
        self._max_ingest_characters = max_ingest_characters

    def ingest(self, *, request: ExtractionIngestionRequest) -> ExtractionIngestionResult:
        """Return normalized text + metadata for downstream orchestration."""

        original_source_value = self._normalize_text(request.original_source_value)
        normalized_title = self._normalize_optional_text(request.title)
        submitted_text = self._normalize_optional_text(request.submitted_text)

        source_type, source_value, source_url = self._resolve_report_source(
            source_kind=request.source_kind,
            original_source_value=original_source_value,
            normalized_title=normalized_title,
        )

        if submitted_text:
            normalized_text = submitted_text
            metadata = self._metadata_for_submitted_text(source_kind=request.source_kind)
        elif request.source_kind == ExtractionSourceKind.URL:
            normalized_text, metadata = self._ingest_from_url(url=source_value)
        else:
            raise ContentIngestionError("Submission content must include extractable text.")

        if len(normalized_text) < MIN_ANALYZABLE_TEXT_LENGTH:
            raise ContentIngestionError("Submission content must be at least 20 characters.")

        return ExtractionIngestionResult(
            source_kind=request.source_kind,
            original_source_value=original_source_value,
            normalized_text=normalized_text,
            source_type=source_type,
            source_value=source_value,
            raw_input_excerpt=self._build_excerpt(normalized_text),
            title=normalized_title,
            source_url=source_url,
            agreed_at=request.agreed_at,
            metadata=metadata,
        )

    def _ingest_from_url(self, *, url: str) -> tuple[str, ExtractionMetadata]:
        """Fetch and extract URL text with MVP fallback for transient failures."""

        try:
            payload = self._url_content_fetcher.fetch(url=url)
            extracted_text, extraction_strategy = self._fetched_content_extractor.extract(
                body_text=payload.body_text,
                content_type=payload.content_type,
            )
            bounded_text, bounded_warning = self._bound_text_length(extracted_text)
            if len(bounded_text) < MIN_ANALYZABLE_TEXT_LENGTH:
                raise ContentIngestionError("Fetched URL content is too short for analysis.")
            warnings: tuple[str, ...] = (bounded_warning,) if bounded_warning else ()
            return bounded_text, ExtractionMetadata(
                extraction_strategy=extraction_strategy,
                extractor_name="content_ingestion_service",
                confidence=0.8,
                warnings=warnings,
                errors=(),
            )
        except (ContentIngestionError, httpx.HTTPError, ValueError) as error:
            # Keep current sync request-path behavior resilient while URL
            # ingestion is still an MVP implementation.
            fallback_text = (
                f"Terms and conditions were submitted with URL {url}. "
                "The full terms text could not be fetched in this request."
            )
            return fallback_text, ExtractionMetadata(
                extraction_strategy="url_fetch_fallback_placeholder",
                extractor_name="content_ingestion_service",
                confidence=0.2,
                warnings=("URL fetch failed; using placeholder text for MVP continuity.",),
                errors=(str(error),),
            )

    def _resolve_report_source(
        self,
        *,
        source_kind: ExtractionSourceKind,
        original_source_value: str,
        normalized_title: str | None,
    ) -> tuple[str, str, str | None]:
        """Map ingestion source kind to existing report source fields."""

        if source_kind == ExtractionSourceKind.URL:
            source_value = original_source_value or "url_submission"
            return "url", source_value, source_value

        if source_kind == ExtractionSourceKind.EXTENSION_TEXT and self._looks_like_url(
            original_source_value
        ):
            return "url", original_source_value, original_source_value

        source_value = normalized_title or original_source_value or "manual_text_submission"
        return "text", source_value, None

    def _metadata_for_submitted_text(
        self, *, source_kind: ExtractionSourceKind
    ) -> ExtractionMetadata:
        """Emit metadata when request already provides terms text."""

        if source_kind == ExtractionSourceKind.EXTENSION_TEXT:
            strategy = "extension_text_submission"
            confidence = 0.85
        elif source_kind == ExtractionSourceKind.URL:
            strategy = "url_with_submitted_text"
            confidence = 0.9
        else:
            strategy = "direct_text_submission"
            confidence = 0.95

        return ExtractionMetadata(
            extraction_strategy=strategy,
            extractor_name="content_ingestion_service",
            confidence=confidence,
            warnings=(),
            errors=(),
        )

    def _bound_text_length(self, text: str) -> tuple[str, str | None]:
        """Bound extracted text length to keep sync ingestion memory-safe."""

        if len(text) <= self._max_ingest_characters:
            return text, None
        return (
            text[: self._max_ingest_characters],
            "Fetched content exceeded max length and was truncated.",
        )

    def _build_excerpt(
        self, text: str, max_length: int = DEFAULT_EXCERPT_MAX_LENGTH
    ) -> str:
        normalized = self._normalize_text(text)
        return normalized[:max_length]

    def _normalize_text(self, value: str) -> str:
        return re.sub(r"\s+", " ", value).strip()

    def _normalize_optional_text(self, value: str | None) -> str | None:
        if value is None:
            return None
        normalized = self._normalize_text(value)
        return normalized or None

    def _looks_like_url(self, value: str) -> bool:
        lowered = value.lower()
        return lowered.startswith("http://") or lowered.startswith("https://")
