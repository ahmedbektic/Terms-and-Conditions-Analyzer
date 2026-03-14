"""Supabase JWT verification utilities.

This module is the backend auth integration boundary:
- verifies Supabase-issued access tokens
- maps validated claims to a provider-agnostic principal object
- keeps Supabase-specific verification details out of route/service layers

Verification strategy supports two Supabase signing models:
1) shared JWT secret (legacy/common projects, HS256)
2) asymmetric JWKS keys (newer key-management flow, typically RS256)

The caller only consumes `SupabasePrincipal`; no route/service code needs to
know which signature strategy was used.
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone
from threading import Lock
import time
from typing import Any

import httpx
import jwt
from jwt import ExpiredSignatureError, InvalidAudienceError, InvalidIssuerError, InvalidTokenError
from jwt import PyJWK

ALLOWED_ASYMMETRIC_ALGORITHMS = ("RS256", "RS384", "RS512", "ES256", "ES384", "EdDSA")
ALLOWED_SUPABASE_SECRET_ALGORITHMS = ("HS256",)


class SupabaseJwtConfigurationError(Exception):
    """Raised when verifier settings are incomplete for configured verification."""


class SupabaseJwtVerificationError(Exception):
    """Raised when access token claims cannot be accepted."""


@dataclass(frozen=True)
class SupabasePrincipal:
    """Authenticated user identity extracted from a Supabase access token."""

    user_id: str
    email: str | None
    issued_at: datetime | None
    expires_at: datetime | None
    raw_claims: dict[str, Any]


class SupabaseJwtVerifier:
    """Verify Supabase access tokens and extract a normalized user principal.

    Design note:
    - Verification is handled here so request-subject resolution can stay small.
    - Routes/services never parse JWTs directly.
    - Future clients (web dashboard, extension, CLI) can share the same backend
      Bearer-token contract because this verifier is transport-agnostic.
    """

    def __init__(
        self,
        *,
        jwks_url: str = "",
        jwt_secret: str = "",
        expected_issuer: str = "",
        expected_audience: str = "",
        require_signature_verification: bool = True,
        jwks_cache_ttl_seconds: int = 300,
        jwks_http_timeout_seconds: float = 5.0,
        jwt_leeway_seconds: int = 30,
    ) -> None:
        self._jwks_url = jwks_url.strip()
        self._jwt_secret = jwt_secret.strip()
        self._expected_issuer = expected_issuer.strip()
        self._expected_audience = expected_audience.strip()
        self._require_signature_verification = require_signature_verification
        self._jwks_cache_ttl_seconds = max(0, int(jwks_cache_ttl_seconds))
        self._jwks_http_timeout_seconds = max(0.1, float(jwks_http_timeout_seconds))
        self._jwt_leeway_seconds = max(0, int(jwt_leeway_seconds))

        self._jwks_cache_lock = Lock()
        self._jwks_cache_payload: dict[str, Any] | None = None
        self._jwks_cached_at_monotonic: float = 0.0

        if self._require_signature_verification:
            if not self._jwt_secret and not self._jwks_url:
                raise SupabaseJwtConfigurationError(
                    "JWT signature verification requires SUPABASE_JWT_SECRET "
                    "or SUPABASE_JWT_JWKS_URL (or SUPABASE_URL-derived JWKS)."
                )

    def verify_access_token(self, token: str) -> SupabasePrincipal:
        """Validate token and return normalized principal for request ownership."""

        if not token or not token.strip():
            raise SupabaseJwtVerificationError("Missing bearer token.")
        compact_token = token.strip()

        claims = self._decode_and_verify_claims(compact_token)
        self._validate_subject_claim(claims)

        return SupabasePrincipal(
            user_id=str(claims["sub"]),
            email=str(claims["email"]) if claims.get("email") else None,
            issued_at=_parse_timestamp_claim(claims.get("iat")),
            expires_at=_parse_timestamp_claim(claims.get("exp")),
            raw_claims=claims,
        )

    def _decode_and_verify_claims(self, token: str) -> dict[str, Any]:
        if not self._require_signature_verification:
            return _decode_jwt_claims_without_signature_check(token)

        try:
            if self._jwt_secret:
                # When both secret and JWKS are configured, secret verification
                # takes precedence for deterministic behavior.
                return jwt.decode(
                    token,
                    key=self._jwt_secret,
                    algorithms=list(ALLOWED_SUPABASE_SECRET_ALGORITHMS),
                    audience=self._expected_audience or None,
                    issuer=self._expected_issuer or None,
                    options=self._build_decode_options(),
                    leeway=self._jwt_leeway_seconds,
                )

            token_header = self._decode_unverified_header(token)
            signing_key = self._resolve_jwks_signing_key(token_header)
            return jwt.decode(
                token,
                key=signing_key,
                algorithms=list(ALLOWED_ASYMMETRIC_ALGORITHMS),
                audience=self._expected_audience or None,
                issuer=self._expected_issuer or None,
                options=self._build_decode_options(),
                leeway=self._jwt_leeway_seconds,
            )
        except ExpiredSignatureError as error:
            raise SupabaseJwtVerificationError("Token has expired.") from error
        except InvalidAudienceError as error:
            raise SupabaseJwtVerificationError(
                "Token audience does not match configuration."
            ) from error
        except InvalidIssuerError as error:
            raise SupabaseJwtVerificationError(
                "Token issuer does not match configuration."
            ) from error
        except InvalidTokenError as error:
            raise SupabaseJwtVerificationError("Token verification failed.") from error
        except httpx.HTTPError as error:
            raise SupabaseJwtVerificationError(
                "Token verification is temporarily unavailable."
            ) from error

    def _build_decode_options(self) -> dict[str, Any]:
        options: dict[str, Any] = {"require": ["sub", "exp"]}
        if not self._expected_audience:
            options["verify_aud"] = False
        if not self._expected_issuer:
            options["verify_iss"] = False
        return options

    def _decode_unverified_header(self, token: str) -> dict[str, Any]:
        try:
            header = jwt.get_unverified_header(token)
        except InvalidTokenError as error:
            raise SupabaseJwtVerificationError("Malformed bearer token.") from error
        if not isinstance(header, dict):
            raise SupabaseJwtVerificationError("Malformed bearer token header.")
        return header

    def _resolve_jwks_signing_key(self, token_header: dict[str, Any]) -> Any:
        kid = token_header.get("kid")
        if not isinstance(kid, str) or not kid.strip():
            raise SupabaseJwtVerificationError("Token header is missing key id (kid).")

        jwk_payload = self._find_jwk_by_kid(kid)
        try:
            return PyJWK.from_dict(jwk_payload).key
        except Exception as error:  # pragma: no cover - defensive library boundary
            raise SupabaseJwtVerificationError("Unable to use JWT signing key.") from error

    def _find_jwk_by_kid(self, kid: str) -> dict[str, Any]:
        jwks_payload = self._get_jwks_payload()
        matched = _find_key_by_kid(jwks_payload, kid)
        if matched:
            return matched

        # A missing key might be due to Supabase key rotation. Force one refresh
        # before denying the request.
        refreshed_payload = self._get_jwks_payload(force_refresh=True)
        refreshed_match = _find_key_by_kid(refreshed_payload, kid)
        if refreshed_match:
            return refreshed_match

        raise SupabaseJwtVerificationError("Token signing key was not found in JWKS set.")

    def _get_jwks_payload(self, *, force_refresh: bool = False) -> dict[str, Any]:
        with self._jwks_cache_lock:
            if not force_refresh and self._jwks_cache_payload and not self._is_jwks_cache_expired():
                return self._jwks_cache_payload

            if not self._jwks_url:
                raise SupabaseJwtVerificationError("JWKS URL is not configured.")

            response = httpx.get(self._jwks_url, timeout=self._jwks_http_timeout_seconds)
            response.raise_for_status()
            payload = response.json()
            if not isinstance(payload, dict):
                raise SupabaseJwtVerificationError("JWKS payload is not a JSON object.")

            keys = payload.get("keys")
            if not isinstance(keys, list):
                raise SupabaseJwtVerificationError("JWKS payload is missing a valid keys list.")

            self._jwks_cache_payload = payload
            self._jwks_cached_at_monotonic = time.monotonic()
            return payload

    def _is_jwks_cache_expired(self) -> bool:
        if self._jwks_cache_ttl_seconds == 0:
            return True
        elapsed = time.monotonic() - self._jwks_cached_at_monotonic
        return elapsed >= self._jwks_cache_ttl_seconds

    def _validate_subject_claim(self, claims: dict[str, Any]) -> None:
        subject = claims.get("sub")
        if not isinstance(subject, str) or not subject.strip():
            raise SupabaseJwtVerificationError("Token is missing a valid 'sub' claim.")

        if claims.get("exp") is None:
            raise SupabaseJwtVerificationError("Token is missing an expiration claim.")

        # This duplicates validation already handled by `jwt.decode` when
        # signature verification is enabled, but keeps behavior consistent in
        # temporary signature-bypass mode used for compatibility/testing.
        expires_at = _parse_timestamp_claim(claims.get("exp"))
        if expires_at and expires_at <= datetime.now(timezone.utc):
            raise SupabaseJwtVerificationError("Token has expired.")


def _decode_jwt_claims_without_signature_check(token: str) -> dict[str, Any]:
    """Temporary fallback for environments explicitly disabling signature checks.

    This mode exists for constrained local/dev scenarios only. Production should
    keep signature verification enabled.
    """

    try:
        claims = jwt.decode(
            token,
            key=None,
            algorithms=list(ALLOWED_ASYMMETRIC_ALGORITHMS + ALLOWED_SUPABASE_SECRET_ALGORITHMS),
            options={"verify_signature": False, "verify_aud": False, "verify_iss": False},
        )
    except InvalidTokenError as error:
        raise SupabaseJwtVerificationError("Malformed bearer token.") from error
    if not isinstance(claims, dict):
        raise SupabaseJwtVerificationError("Token payload must be a JSON object.")
    return claims


def _find_key_by_kid(jwks_payload: dict[str, Any], kid: str) -> dict[str, Any] | None:
    for key_item in jwks_payload.get("keys", []):
        if isinstance(key_item, dict) and key_item.get("kid") == kid:
            return key_item
    return None


def _parse_timestamp_claim(value: Any) -> datetime | None:
    if value is None:
        return None
    if not isinstance(value, (int, float)):
        raise SupabaseJwtVerificationError("Token timestamp claims must be numeric.")
    return datetime.fromtimestamp(value, tz=timezone.utc)
