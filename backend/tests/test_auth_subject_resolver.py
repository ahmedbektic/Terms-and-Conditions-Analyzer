"""Tests for ownership-subject resolution policy.

These tests validate JWT-only mapping from Authorization header to
service-layer ownership identity.
"""

import jwt
import pytest

from app.auth.subject_resolver import AuthSubjectResolver, SubjectResolutionError
from app.auth.supabase_jwt import SupabaseJwtVerifier

TEST_SECRET = "b" * 48
TEST_ISSUER = "https://resolver-test.supabase.co/auth/v1"
TEST_AUDIENCE = "authenticated"


def _issue_token(sub: str) -> str:
    return jwt.encode(
        {
            "sub": sub,
            "aud": TEST_AUDIENCE,
            "iss": TEST_ISSUER,
            "exp": 4070908800,  # Year 2099 for deterministic non-expired unit tests.
        },
        TEST_SECRET,
        algorithm="HS256",
    )


def _build_verifier() -> SupabaseJwtVerifier:
    return SupabaseJwtVerifier(
        jwt_secret=TEST_SECRET,
        expected_issuer=TEST_ISSUER,
        expected_audience=TEST_AUDIENCE,
        require_signature_verification=True,
    )


def test_jwt_mode_resolves_authenticated_subject_from_bearer_token() -> None:
    resolver = AuthSubjectResolver(jwt_verifier=_build_verifier())

    resolved = resolver.resolve(
        authorization_header=f"Bearer {_issue_token('jwt-user-1')}",
    )

    assert resolved.subject_type == "supabase_user"
    assert resolved.subject_id == "jwt-user-1"


def test_jwt_mode_requires_bearer_token() -> None:
    resolver = AuthSubjectResolver(jwt_verifier=_build_verifier())

    with pytest.raises(SubjectResolutionError) as error:
        resolver.resolve(authorization_header=None)

    assert error.value.status_code == 401
    assert "Missing Bearer token." == error.value.detail
