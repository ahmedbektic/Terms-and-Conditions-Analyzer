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
from typing import Protocol
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

import httpx

from ..core.input_validation import normalize_untrusted_text, validate_external_source_url

DEFAULT_WEB_SOURCE_TIMEOUT_SECONDS = 8.0
MIN_TRACKABLE_SOURCE_TEXT_LENGTH = 20

_TITLE_PATTERN = re.compile(r"(?is)<title[^>]*>(.*?)</title>")


class WebSourceInspectionError(Exception):
    """Raised when a public web source cannot be verified for tracking use."""


@dataclass(frozen=True)
class UrlFetchPayload:
    """Raw HTTP response payload returned by a URL fetcher."""

    body_text: str
    content_type: str
    final_url: str | None = None


@dataclass(frozen=True)
class InspectedWebSource:
    """Verified public web source information used by registration workflows."""

    canonical_url: str
    display_name: str
    source_type: str
    last_checked_at: datetime


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

        without_scripts = re.sub(
            r"(?is)<(script|style|noscript|svg)[^>]*>.*?</\1>",
            " ",
            html_text,
        )
        without_tags = re.sub(r"(?s)<[^>]+>", " ", without_scripts)
        return self._normalize_text(unescape(without_tags))

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

    if (
        normalized_port is not None
        and ((normalized_scheme == "http" and normalized_port == 80) or (normalized_scheme == "https" and normalized_port == 443))
    ):
        normalized_port = None

    normalized_netloc = _build_netloc(hostname=normalized_hostname, port=normalized_port)
    normalized_path = parsed.path or "/"
    normalized_query = urlencode(
        sorted(parse_qsl(parsed.query, keep_blank_values=True)),
        doseq=True,
    )

    return urlunsplit(
        (normalized_scheme, normalized_netloc, normalized_path, normalized_query, "")
    )


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

        canonical_url = canonicalize_public_source_url(source_url)
        try:
            payload = self._url_content_fetcher.fetch(url=canonical_url)
        except (httpx.HTTPError, ValueError) as error:
            raise WebSourceInspectionError(
                "We couldn't reach that policy page. Check the URL and try again."
            ) from error

        extracted_text, _ = self._fetched_content_extractor.extract(
            body_text=payload.body_text,
            content_type=payload.content_type,
        )
        if not self._is_readable_source(
            extracted_text=extracted_text,
            body_text=payload.body_text,
            content_type=payload.content_type,
        ):
            raise WebSourceInspectionError(
                "That URL does not appear to be a readable policy page."
            )
        if len(extracted_text) < MIN_TRACKABLE_SOURCE_TEXT_LENGTH:
            raise WebSourceInspectionError(
                "That page did not contain enough readable policy text to track."
            )

        display_name = self._derive_display_name(
            canonical_url=canonical_url,
            body_text=payload.body_text,
            content_type=payload.content_type,
        )
        return InspectedWebSource(
            canonical_url=canonical_url,
            display_name=display_name,
            source_type="url",
            last_checked_at=datetime.now(timezone.utc),
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
