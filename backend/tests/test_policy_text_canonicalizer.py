from pathlib import Path

from app.services.policy_text_canonicalizer import PolicyTextCanonicalizer


def test_canonicalizer_suppresses_real_form_noise_from_legacy_samples() -> None:
    repo_root = Path(__file__).resolve().parents[2]
    term1 = (repo_root / "term1.txt").read_text(encoding="utf-8")
    term2 = (repo_root / "term2.txt").read_text(encoding="utf-8")
    canonicalizer = PolicyTextCanonicalizer()

    result_one = canonicalizer.canonicalize_text(term1, legacy_upgrade_applied=True)
    result_two = canonicalizer.canonicalize_text(term2, legacy_upgrade_applied=True)

    assert result_one.comparison_text_body == result_two.comparison_text_body
    assert "terms and conditions outline the rules" in result_one.comparison_text_body.lower()
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
