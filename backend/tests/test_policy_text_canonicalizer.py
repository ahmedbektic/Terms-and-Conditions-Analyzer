from app.test_support_policy_text_samples import (
    LEGACY_NOISY_POLICY_TEXT_AFTER,
    LEGACY_NOISY_POLICY_TEXT_BEFORE,
)
from app.services.policy_text_canonicalizer import PolicyTextCanonicalizer


def test_canonicalizer_suppresses_real_form_noise_from_legacy_samples() -> None:
    canonicalizer = PolicyTextCanonicalizer()

    result_one = canonicalizer.canonicalize_text(
        LEGACY_NOISY_POLICY_TEXT_BEFORE,
        legacy_upgrade_applied=True,
    )
    result_two = canonicalizer.canonicalize_text(
        LEGACY_NOISY_POLICY_TEXT_AFTER,
        legacy_upgrade_applied=True,
    )

    assert result_one.comparison_text_body == result_two.comparison_text_body
    assert "welcome to concise, a news aggregation platform" in (
        result_one.comparison_text_body.lower()
    )
    assert "this field is for validation purposes" not in result_one.comparison_text_body.lower()
    assert "save your cart" not in result_one.comparison_text_body.lower()


def test_canonicalizer_synthesizes_multiple_compare_lines_from_flat_text() -> None:
    canonicalizer = PolicyTextCanonicalizer()

    result = canonicalizer.canonicalize_text(
        "Terms of Service Users must arbitrate disputes. 1. Billing You agree to pay monthly. "
        "Email This field is for validation purposes and should be left unchanged."
    )

    lines = result.comparison_text_body.splitlines()
    assert len(lines) >= 3
    assert any("users must arbitrate disputes" in line.lower() for line in lines)
    assert any("billing you agree to pay monthly" in line.lower() for line in lines)
    assert all("validation purposes" not in line.lower() for line in lines)


def test_canonicalizer_falls_back_when_cleanup_would_strip_too_much() -> None:
    canonicalizer = PolicyTextCanonicalizer()

    result = canonicalizer.canonicalize_text("Skip to content Save your cart Close")

    assert result.comparison_text_body
    assert result.used_fallback is True
    assert result.confidence == "low"
