"""Shared public-web-source utilities used by URL-based workflows.

This module owns the neutral URL boundary for:
- validating and canonicalizing public source URLs
- performing lightweight fetches against readable web pages
- extracting simple text/title metadata from fetched responses

It deliberately stays generic so both watchlist registration and future
URL-driven workflows can reuse the same fetch and inspection seams without
depending on report-ingestion internals.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from html import unescape
import re
import time
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from ..core.input_validation import normalize_untrusted_text, validate_external_source_url

DEFAULT_WEB_SOURCE_TIMEOUT_SECONDS = 8.0
MIN_TRACKABLE_SOURCE_TEXT_LENGTH = 20

_TITLE_PATTERN = re.compile(r"(?is)<title[^>]*>(.*?)</title>")
_LOGIN_WALL_PATTERN = re.compile(
    r"(?i)\b(sign in|log in|login|password|account required|access denied)\b"
)


class WebSourceInspectionError(Exception):
    """Raised when a public web source cannot be verified for tracking use."""

    def __init__(self, public_message: str, *, invalidates_tracking: bool = True) -> None:
        super().__init__(public_message)
        self.public_message = public_message
        self.invalidates_tracking = invalidates_tracking


@dataclass(frozen=True)
class UrlFetchPayload:
    """Raw HTTP response payload returned by a URL fetcher."""

    body_text: str
    content_type: str
    final_url: str | None = None
    status_code: int | None = None
    redirect_count: int | None = None
    fetch_duration_ms: int | None = None


@dataclass(frozen=True)
class InspectedWebSource:
    """Verified public web source information used by registration workflows."""

    canonical_url: str
    display_name: str
    source_type: str
    last_checked_at: datetime


@dataclass(frozen=True)
class CapturedWebSource:
    """Verified public web source plus the readable policy text captured from it."""

    canonical_url: str
    display_name: str
    source_type: str
    checked_at: datetime
    captured_text: str
    raw_text_body: str | None = None
    final_url: str | None = None
    http_status: int | None = None
    redirect_count: int | None = None
    fetch_duration_ms: int | None = None
    extractor_name: str | None = None
    extraction_strategy: str | None = None


@dataclass(frozen=True)
class ExtractedFetchedContent:
    """Normalized extraction result used by snapshot capture workflows."""

    raw_text_body: str
    normalized_text_body: str
    extraction_strategy: str
    extractor_name: str


@dataclass(frozen=True)
class CapturedPolicySnapshotSource:
    """Rich policy capture result used by tracked-policy snapshot checks."""

    canonical_url: str
    display_name: str
    source_type: str
    checked_at: datetime
    raw_text_body: str
    normalized_text_body: str
    final_url: str | None
    http_status: int | None
    redirect_count: int | None
    fetch_duration_ms: int | None
    extractor_name: str
    extraction_strategy: str


class UrlContentFetcher(Protocol):
    """Protocol for swappable URL content acquisition implementations."""

    def fetch(self, *, url: str) -> UrlFetchPayload: ...


class FetchedContentExtractor(Protocol):
    """Protocol for swappable fetched-content extraction implementations."""

    def extract(self, *, body_text: str, content_type: str) -> tuple[str, str]: ...

    def extract_title(self, *, body_text: str, content_type: str) -> str | None: ...


class HttpxUrlContentFetcher:
    """HTTP fetcher implementation for sync URL inspection and ingestion."""

    def __init__(
        self,
        *,
        timeout_seconds: float = DEFAULT_WEB_SOURCE_TIMEOUT_SECONDS,
    ) -> None:
        self._timeout_seconds = timeout_seconds

    def fetch(self, *, url: str) -> UrlFetchPayload:
        """Fetch URL content and return body text plus response metadata."""

        safe_url = validate_external_source_url(url)
        started_at = time.monotonic()
        response = httpx.get(
            safe_url,
            follow_redirects=True,
            timeout=self._timeout_seconds,
            headers={
                "User-Agent": ("TermsAnalyzerBot/0.1 (+https://example.invalid/content-ingestion)")
            },
        )
        response.raise_for_status()
        return UrlFetchPayload(
            body_text=response.text,
            content_type=response.headers.get("content-type", ""),
            final_url=str(response.url),
            status_code=response.status_code,
            redirect_count=len(response.history),
            fetch_duration_ms=int((time.monotonic() - started_at) * 1000),
        )


class SimpleFetchedContentExtractor:
    """Lightweight fetched-content extractor for readable web pages."""

    def extract(self, *, body_text: str, content_type: str) -> tuple[str, str]:
        normalized_content_type = content_type.lower()
        if "html" in normalized_content_type or self._looks_like_html(body_text):
            return self._extract_text_from_html(body_text), "url_fetch_html_tag_strip"
        return self._normalize_text(unescape(body_text)), "url_fetch_plain_text"

    def extract_title(self, *, body_text: str, content_type: str) -> str | None:
        normalized_content_type = content_type.lower()
        if "html" not in normalized_content_type and not self._looks_like_html(body_text):
            return None

        match = _TITLE_PATTERN.search(body_text)
        if not match:
            return None
        title = self._normalize_text(unescape(match.group(1)))
        return title or None

    def looks_like_html(self, *, body_text: str, content_type: str) -> bool:
        """Return whether the fetched payload should be treated as HTML-like."""

        normalized_content_type = content_type.lower()
        return "html" in normalized_content_type or self._looks_like_html(body_text)

    def _extract_text_from_html(self, html_text: str) -> str:
        """Extract plain text from HTML via lightweight regex-based stripping."""

        return self._normalize_text(self._extract_raw_text_from_html(html_text))

    def extract_for_snapshot(self, *, body_text: str, content_type: str) -> ExtractedFetchedContent:
        """Return both raw and normalized extracted text for snapshot storage."""

        normalized_content_type = content_type.lower()
        if "html" in normalized_content_type or self._looks_like_html(body_text):
            raw_text = self._extract_raw_text_from_html(body_text)
            return ExtractedFetchedContent(
                raw_text_body=raw_text,
                normalized_text_body=self._normalize_text(raw_text),
                extraction_strategy="url_fetch_html_tag_strip",
                extractor_name="simple_fetched_content_extractor",
            )

        raw_text = unescape(body_text)
        return ExtractedFetchedContent(
            raw_text_body=raw_text,
            normalized_text_body=self._normalize_text(raw_text),
            extraction_strategy="url_fetch_plain_text",
            extractor_name="simple_fetched_content_extractor",
        )

    def _extract_raw_text_from_html(self, html_text: str) -> str:
        """Extract raw plain text from HTML without whitespace normalization."""

        without_scripts = re.sub(
            r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>",
            " ",
            html_text,
        )
        without_comments = re.sub(r"(?s)<!--.*?-->", " ", without_scripts)
        return unescape(re.sub(r"(?s)<[^>]+>", " ", without_comments))

    def _normalize_text(self, value: str) -> str:
        return normalize_untrusted_text(value)

    def _looks_like_html(self, text: str) -> bool:
        lowered = text.lower()
        return "<html" in lowered or "<body" in lowered or "<div" in lowered


def canonicalize_public_source_url(value: str) -> str:
    """Return a stable canonical representation for a validated public URL."""

    validated_url = validate_external_source_url(value)
    parsed = urlsplit(validated_url)

    normalized_scheme = parsed.scheme.lower()
    normalized_hostname = (parsed.hostname or "").lower()
    normalized_port = parsed.port

    if normalized_port is not None and (
        (normalized_scheme == "http" and normalized_port == 80)
        or (normalized_scheme == "https" and normalized_port == 443)
    ):
        normalized_port = None

    normalized_netloc = _build_netloc(hostname=normalized_hostname, port=normalized_port)
    normalized_path = parsed.path or "/"
    normalized_query = urlencode(
        sorted(parse_qsl(parsed.query, keep_blank_values=True)),
        doseq=True,
    )

    return urlunsplit((normalized_scheme, normalized_netloc, normalized_path, normalized_query, ""))


class PublicWebSourceInspector:
    """Verify that a public URL points to a readable page suitable for tracking."""

    def __init__(
        self,
        *,
        url_content_fetcher: UrlContentFetcher | None = None,
        fetched_content_extractor: FetchedContentExtractor | None = None,
    ) -> None:
        self._url_content_fetcher = url_content_fetcher or HttpxUrlContentFetcher()
        self._fetched_content_extractor = (
            fetched_content_extractor or SimpleFetchedContentExtractor()
        )

    def inspect_url(self, *, source_url: str) -> InspectedWebSource:
        """Canonicalize, fetch, and verify a source URL for watchlist registration."""

        captured_source = self.capture_trackable_source(source_url=source_url)
        return InspectedWebSource(
            canonical_url=captured_source.canonical_url,
            display_name=captured_source.display_name,
            source_type=captured_source.source_type,
            last_checked_at=captured_source.checked_at,
        )

    def capture_trackable_source(self, *, source_url: str) -> CapturedWebSource:
        """Canonicalize, verify, and capture readable policy text in one pass."""

        snapshot_source = self.capture_policy_snapshot_source(canonical_url=source_url)
        return CapturedWebSource(
            canonical_url=snapshot_source.canonical_url,
            display_name=snapshot_source.display_name,
            source_type=snapshot_source.source_type,
            checked_at=snapshot_source.checked_at,
            captured_text=snapshot_source.normalized_text_body,
            raw_text_body=snapshot_source.raw_text_body,
            final_url=snapshot_source.final_url,
            http_status=snapshot_source.http_status,
            redirect_count=snapshot_source.redirect_count,
            fetch_duration_ms=snapshot_source.fetch_duration_ms,
            extractor_name=snapshot_source.extractor_name,
            extraction_strategy=snapshot_source.extraction_strategy,
        )

    def capture_policy_text(self, *, canonical_url: str) -> str:
        """Fetch a canonical policy URL and return normalized, readable policy text.

        Raises WebSourceInspectionError when the page cannot be reached or is unsuitable
        for snapshot storage (same rules as watchlist registration).
        """

        return self.capture_policy_snapshot_source(canonical_url=canonical_url).normalized_text_body

    def capture_policy_snapshot_source(self, *, canonical_url: str) -> CapturedPolicySnapshotSource:
        """Fetch a canonical policy URL and return rich snapshot-capture metadata."""

        stable_canonical_url = canonicalize_public_source_url(canonical_url)
        payload, extracted = self._fetch_extract_and_validate(canonical_url=stable_canonical_url)
        display_name = self._derive_display_name(
            canonical_url=stable_canonical_url,
            body_text=payload.body_text,
            content_type=payload.content_type,
        )
        return CapturedPolicySnapshotSource(
            canonical_url=stable_canonical_url,
            display_name=display_name,
            source_type="url",
            checked_at=datetime.now(timezone.utc),
            raw_text_body=extracted.raw_text_body,
            normalized_text_body=extracted.normalized_text_body,
            final_url=payload.final_url,
            http_status=payload.status_code,
            redirect_count=payload.redirect_count,
            fetch_duration_ms=payload.fetch_duration_ms,
            extractor_name=extracted.extractor_name,
            extraction_strategy=extracted.extraction_strategy,
        )

    def _fetch_extract_and_validate(
        self, *, canonical_url: str
    ) -> tuple[UrlFetchPayload, ExtractedFetchedContent]:
        try:
            payload = self._url_content_fetcher.fetch(url=canonical_url)
        except (httpx.HTTPError, ValueError) as error:
            public_message, invalidates_tracking = _build_fetch_error_details(error)
            raise WebSourceInspectionError(
                public_message,
                invalidates_tracking=invalidates_tracking,
            ) from error

        extracted = self._extract_for_snapshot(
            body_text=payload.body_text,
            content_type=payload.content_type,
        )
        normalized_content_type = payload.content_type.lower()
        if "pdf" in normalized_content_type:
            raise WebSourceInspectionError(
                "That URL points to a PDF download. Use the service's public web page for the policy instead."
            )
        if not self._is_readable_source(
            extracted_text=extracted.normalized_text_body,
            body_text=payload.body_text,
            content_type=payload.content_type,
        ):
            raise WebSourceInspectionError(
                _build_unreadable_source_message(
                    extracted_text=extracted.normalized_text_body,
                    body_text=payload.body_text,
                )
            )
        if len(extracted.normalized_text_body) < MIN_TRACKABLE_SOURCE_TEXT_LENGTH:
            raise WebSourceInspectionError(
                "That page did not contain enough readable policy text to track. Use the service's full terms, privacy, or legal page instead."
            )
        return payload, extracted

    def _extract_for_snapshot(
        self, *, body_text: str, content_type: str
    ) -> ExtractedFetchedContent:
        extractor = self._fetched_content_extractor
        extract_for_snapshot = getattr(extractor, "extract_for_snapshot", None)
        if callable(extract_for_snapshot):
            extracted = extract_for_snapshot(body_text=body_text, content_type=content_type)
            if isinstance(extracted, ExtractedFetchedContent):
                return extracted

        normalized_text, extraction_strategy = extractor.extract(
            body_text=body_text,
            content_type=content_type,
        )
        return ExtractedFetchedContent(
            raw_text_body=normalized_text,
            normalized_text_body=normalized_text,
            extraction_strategy=extraction_strategy,
            extractor_name=extractor.__class__.__name__.lower(),
        )

    def _derive_display_name(
        self,
        *,
        canonical_url: str,
        body_text: str,
        content_type: str,
    ) -> str:
        title = self._fetched_content_extractor.extract_title(
            body_text=body_text,
            content_type=content_type,
        )
        if title:
            return title

        parsed = urlsplit(canonical_url)
        return (parsed.hostname or canonical_url).lower()

    def _is_readable_source(
        self,
        *,
        extracted_text: str,
        body_text: str,
        content_type: str,
    ) -> bool:
        lowered_content_type = content_type.lower()
        if not lowered_content_type:
            return bool(extracted_text)
        if lowered_content_type.startswith("text/"):
            return True
        if "html" in lowered_content_type or "xhtml" in lowered_content_type:
            return True
        extractor = self._fetched_content_extractor
        looks_like_html = getattr(extractor, "looks_like_html", None)
        if callable(looks_like_html):
            return bool(looks_like_html(body_text=body_text, content_type=content_type))
        return bool(extracted_text)


def _build_netloc(*, hostname: str, port: int | None) -> str:
    if ":" in hostname and not hostname.startswith("["):
        normalized_hostname = f"[{hostname}]"
    else:
        normalized_hostname = hostname
    if port is None:
        return normalized_hostname
    return f"{normalized_hostname}:{port}"


def _build_fetch_error_details(error: Exception) -> tuple[str, bool]:
    """Map low-level fetch failures into actionable messages and tracking impact."""

    if isinstance(error, httpx.TimeoutException):
        return (
            "That policy page took too long to respond. Open it in your browser and try again in a moment.",
            False,
        )

    if isinstance(error, httpx.TooManyRedirects):
        return (
            "That policy page kept redirecting. Use the service's final public terms or privacy URL instead.",
            True,
        )

    if isinstance(error, httpx.HTTPStatusError):
        status_code = error.response.status_code
        if status_code == 404:
            return (
                "That policy page returned 404 Not Found. Check that the link is current or use the service's public legal page.",
                True,
            )
        if status_code in {401, 403}:
            return (
                "That policy page is blocking access. Use a public terms or privacy page that does not require sign-in.",
                True,
            )
        if status_code == 429:
            return (
                "That policy page is rate limiting requests right now. Try again in a moment.",
                False,
            )
        if status_code >= 500:
            return (
                "That policy page is temporarily unavailable right now. Try again in a moment.",
                False,
            )
        return (
            f"That policy page returned HTTP {status_code}. Check the link or use the service's public terms or privacy page.",
            True,
        )

    if isinstance(error, httpx.ConnectError):
        return (
            "We couldn't connect to that policy page. Check the URL and make sure the site is reachable.",
            False,
        )

    return ("We couldn't reach that policy page. Check the URL and try again.", False)


def _build_unreadable_source_message(*, extracted_text: str, body_text: str) -> str:
    normalized_body_text = normalize_untrusted_text(body_text)
    if _LOGIN_WALL_PATTERN.search(normalized_body_text):
        return "That page appears to require sign-in or special access. Use a public terms or privacy page that anyone can open."
    if not extracted_text.strip():
        return "That page did not expose readable policy text. Use the service's public terms, privacy, or legal page instead."
    return "That URL does not look like a readable policy page. Use the service's public terms, privacy, or legal page instead."
