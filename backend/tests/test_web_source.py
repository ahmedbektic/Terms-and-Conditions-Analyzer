import importlib.util

import pytest

from app.services.web_source import SimpleFetchedContentExtractor

pytestmark = pytest.mark.skipif(
    importlib.util.find_spec("bs4") is None,
    reason="beautifulsoup4 not installed",
)


def test_html_extraction_removes_obvious_navigation_form_and_footer_noise() -> None:
    extractor = SimpleFetchedContentExtractor()

    extracted = extractor.extract_for_snapshot(
        body_text=(
            "<html><body>"
            "<nav>Menu Contact Us</nav>"
            "<main>"
            "<h1>Terms of Service</h1>"
            "<p>Users must resolve disputes in Texas.</p>"
            "<p>Billing renews every month.</p>"
            "<form>Email Phone This field is for validation purposes.</form>"
            "</main>"
            "<footer>Save your cart Contact us today to learn more.</footer>"
            "</body></html>"
        ),
        content_type="text/html",
    )

    assert extracted.extraction_strategy == "url_fetch_html_dom_canonicalized"
    assert extracted.normalization_version == 2
    assert "users must resolve disputes in texas" in extracted.normalized_text_body.lower()
    assert "billing renews every month" in extracted.normalized_text_body.lower()
    assert "menu" not in extracted.raw_text_body.lower()
    assert "validation purposes" not in extracted.normalized_text_body.lower()
    assert "save your cart" not in extracted.normalized_text_body.lower()
