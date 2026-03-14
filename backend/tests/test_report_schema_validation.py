from pydantic import ValidationError
import pytest

from app.schemas.reports import ReportAnalyzeRequest


def test_report_analyze_request_accepts_terms_text_only() -> None:
    request = ReportAnalyzeRequest(terms_text="This terms text is sufficiently long.")
    assert request.terms_text == "This terms text is sufficiently long."


def test_report_analyze_request_accepts_source_url_only() -> None:
    request = ReportAnalyzeRequest(source_url="https://example.com/terms")
    assert request.source_url == "https://example.com/terms"


def test_report_analyze_request_rejects_missing_terms_and_url() -> None:
    with pytest.raises(ValidationError):
        ReportAnalyzeRequest()


def test_report_analyze_request_rejects_blank_terms_and_url() -> None:
    with pytest.raises(ValidationError):
        ReportAnalyzeRequest(source_url="  ", terms_text="   ")
