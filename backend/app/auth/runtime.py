"""Auth runtime wiring for request-subject resolution.

This module keeps provider-specific verifier construction inside the auth
package so API dependency modules can stay focused on transport wiring.
"""

from .subject_resolver import AuthSubjectResolver
from .supabase_jwt import (
    SupabaseJwtConfigurationError,
    SupabaseJwtVerifier,
)


def build_request_subject_resolver(
    *,
    jwt_secret: str,
    jwks_url: str,
    expected_issuer: str,
    expected_audience: str,
    require_signature_verification: bool,
    jwks_cache_ttl_seconds: int,
    jwks_http_timeout_seconds: float,
    jwt_leeway_seconds: int,
) -> AuthSubjectResolver:
    """Build JWT-backed request subject resolver for API dependencies.

    Raises:
        RuntimeError: when JWT verification configuration is incomplete.
    """

    try:
        jwt_verifier = SupabaseJwtVerifier(
            jwt_secret=jwt_secret,
            jwks_url=jwks_url,
            expected_issuer=expected_issuer,
            expected_audience=expected_audience,
            require_signature_verification=require_signature_verification,
            jwks_cache_ttl_seconds=jwks_cache_ttl_seconds,
            jwks_http_timeout_seconds=jwks_http_timeout_seconds,
            jwt_leeway_seconds=jwt_leeway_seconds,
        )
    except SupabaseJwtConfigurationError as error:
        raise RuntimeError(f"Invalid auth configuration: {error}") from error

    return AuthSubjectResolver(jwt_verifier=jwt_verifier)
