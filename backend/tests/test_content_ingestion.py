from app.services.content_ingestion import (
    ContentIngestionService,
    UrlFetchPayload,
)
from app.services.extraction_contracts import (
    ExtractionIngestionRequest,
    ExtractionSourceKind,
)


class _StaticUrlFetcher:
    def __init__(self, payload: UrlFetchPayload) -> None:
        self._payload = payload

    def fetch(self, *, url: str) -> UrlFetchPayload:
        _ = url
        return self._payload


class _FailingUrlFetcher:
    def fetch(self, *, url: str) -> UrlFetchPayload:
        _ = url
        raise ValueError("fetch failed")


class _TrackingUrlFetcher:
    def __init__(self, payload: UrlFetchPayload) -> None:
        self._payload = payload
        self.calls = 0

    def fetch(self, *, url: str) -> UrlFetchPayload:
        _ = url
        self.calls += 1
        return self._payload


class _CustomFetchedContentExtractor:
    def __init__(self) -> None:
        self.calls = 0

    def extract(self, *, body_text: str, content_type: str) -> tuple[str, str]:
        _ = body_text
        _ = content_type
        self.calls += 1
        return "custom extracted terms content", "custom_extractor"


def test_ingest_direct_text_submission_returns_normalized_text() -> None:
    service = ContentIngestionService(
        url_content_fetcher=_StaticUrlFetcher(UrlFetchPayload("", ""))
    )
    result = service.ingest(
        request=ExtractionIngestionRequest(
            source_kind=ExtractionSourceKind.RAW_TEXT,
            original_source_value="manual",
            submitted_text="   These   terms   are   valid   for   analysis.   ",
            title="Demo",
            agreed_at=None,
            source_metadata={},
        )
    )

    assert result.normalized_text == "These terms are valid for analysis."
    assert result.source_type == "text"
    assert result.metadata.extraction_strategy == "direct_text_submission"


def test_ingest_url_submission_fetches_and_extracts_html_text() -> None:
    service = ContentIngestionService(
        url_content_fetcher=_StaticUrlFetcher(
            UrlFetchPayload(
                body_text=(
                    "<html><body><h1>Terms</h1><p>These terms include arbitration "
                    "and automatic renewal clauses.</p></body></html>"
                ),
                content_type="text/html; charset=utf-8",
            )
        )
    )
    result = service.ingest(
        request=ExtractionIngestionRequest(
            source_kind=ExtractionSourceKind.URL,
            original_source_value="https://example.com/terms",
            submitted_text=None,
            title=None,
            agreed_at=None,
            source_metadata={},
        )
    )

    assert result.source_type == "url"
    assert result.source_value == "https://example.com/terms"
    assert "arbitration" in result.normalized_text.lower()
    assert result.metadata.extraction_strategy == "url_fetch_html_tag_strip"


def test_ingest_url_submission_falls_back_to_placeholder_when_fetch_fails() -> None:
    service = ContentIngestionService(url_content_fetcher=_FailingUrlFetcher())
    result = service.ingest(
        request=ExtractionIngestionRequest(
            source_kind=ExtractionSourceKind.URL,
            original_source_value="https://example.com/terms",
            submitted_text=None,
            title=None,
            agreed_at=None,
            source_metadata={},
        )
    )

    assert "could not be fetched" in result.normalized_text.lower()
    assert result.metadata.extraction_strategy == "url_fetch_fallback_placeholder"
    assert result.metadata.warnings != ()
    assert result.metadata.errors != ()


def test_ingest_extension_text_uses_submitted_text_without_url_fetch() -> None:
    fetcher = _TrackingUrlFetcher(
        UrlFetchPayload(
            body_text="This text should not be used when submitted text exists.",
            content_type="text/plain",
        )
    )
    service = ContentIngestionService(url_content_fetcher=fetcher)

    result = service.ingest(
        request=ExtractionIngestionRequest(
            source_kind=ExtractionSourceKind.EXTENSION_TEXT,
            original_source_value="https://example.com/terms",
            submitted_text=(
                "These terms include arbitration and automatic renewal language."
            ),
            title="Example Terms",
            agreed_at=None,
            source_metadata={},
        )
    )

    assert fetcher.calls == 0
    assert result.source_type == "url"
    assert result.source_value == "https://example.com/terms"
    assert result.metadata.extraction_strategy == "extension_text_submission"
    assert "automatic renewal" in result.normalized_text.lower()


def test_ingest_url_submission_prefers_submitted_text_when_present() -> None:
    fetcher = _TrackingUrlFetcher(
        UrlFetchPayload(
            body_text="This fetched body should not be used when terms_text exists.",
            content_type="text/plain",
        )
    )
    service = ContentIngestionService(url_content_fetcher=fetcher)

    result = service.ingest(
        request=ExtractionIngestionRequest(
            source_kind=ExtractionSourceKind.URL,
            original_source_value="https://example.com/terms",
            submitted_text="Provided terms text should win over fetched text.",
            title=None,
            agreed_at=None,
            source_metadata={},
        )
    )

    assert fetcher.calls == 0
    assert result.source_type == "url"
    assert result.metadata.extraction_strategy == "url_with_submitted_text"
    assert "provided terms text should win" in result.normalized_text.lower()


def test_ingest_url_submission_supports_swappable_fetched_content_extractor() -> None:
    custom_extractor = _CustomFetchedContentExtractor()
    service = ContentIngestionService(
        url_content_fetcher=_StaticUrlFetcher(
            UrlFetchPayload(
                body_text="<html><body>ignored</body></html>",
                content_type="text/html",
            )
        ),
        fetched_content_extractor=custom_extractor,
    )

    result = service.ingest(
        request=ExtractionIngestionRequest(
            source_kind=ExtractionSourceKind.URL,
            original_source_value="https://example.com/terms",
            submitted_text=None,
            title=None,
            agreed_at=None,
            source_metadata={},
        )
    )

    assert custom_extractor.calls == 1
    assert result.normalized_text == "custom extracted terms content"
    assert result.metadata.extraction_strategy == "custom_extractor"
