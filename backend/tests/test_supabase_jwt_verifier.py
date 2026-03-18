"""Unit tests for Supabase JWT verification behavior.

These tests focus on token-validation outcomes, not storage or route wiring.
"""

from datetime import datetime, timedelta, timezone

import jwt
import pytest

from app.auth.supabase_jwt import SupabaseJwtVerificationError, SupabaseJwtVerifier

TEST_SECRET = "a" * 48
TEST_ISSUER = "https://unit-test.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"


def _issue_token(*, sub: str = "user-1", exp_offset_seconds: int = 300, **overrides: object) -> str:
    payload: dict[str, object] = {
        "sub": sub,
        "aud": TEST_AUDIENCE,
        "iss": TEST_ISSUER,
        "exp": int(
            (datetime.now(timezone.utc) + timedelta(seconds=exp_offset_seconds)).timestamp()
        ),
        "email": "user@example.com",
    }
    payload.update(overrides)
    return jwt.encode(payload, TEST_SECRET, algorithm="HS256")


def _build_verifier() -> SupabaseJwtVerifier:
    return SupabaseJwtVerifier(
        jwt_secret=TEST_SECRET,
        expected_issuer=TEST_ISSUER,
        expected_audience=TEST_AUDIENCE,
        require_signature_verification=True,
    )


def test_verify_access_token_returns_principal_for_valid_token() -> None:
    verifier = _build_verifier()
    token = _issue_token(sub="user-123")

    principal = verifier.verify_access_token(token)

    assert principal.user_id == "user-123"
    assert principal.email == "user@example.com"
    assert principal.expires_at is not None
    assert principal.raw_claims["aud"] == TEST_AUDIENCE


def test_verify_access_token_rejects_malformed_token() -> None:
    verifier = _build_verifier()

    with pytest.raises(SupabaseJwtVerificationError):
        verifier.verify_access_token("not.a.valid.jwt")


def test_verify_access_token_rejects_expired_token() -> None:
    verifier = _build_verifier()
    token = _issue_token(exp_offset_seconds=-30)

    with pytest.raises(SupabaseJwtVerificationError):
        verifier.verify_access_token(token)


def test_verify_access_token_rejects_wrong_audience() -> None:
    verifier = _build_verifier()
    token = _issue_token(aud="not-authenticated")

    with pytest.raises(SupabaseJwtVerificationError):
        verifier.verify_access_token(token)


def test_verify_access_token_rejects_wrong_issuer() -> None:
    verifier = _build_verifier()
    token = _issue_token(iss="https://other.supabase.co/auth/v1")

    with pytest.raises(SupabaseJwtVerificationError):
        verifier.verify_access_token(token)
