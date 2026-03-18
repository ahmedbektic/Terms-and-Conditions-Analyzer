"""Request subject resolution for JWT-authenticated callers.

This module maps `Authorization: Bearer <jwt>` to the service-layer ownership
tuple (subject_type + subject_id).
"""

from dataclasses import dataclass

from .supabase_jwt import SupabaseJwtVerificationError, SupabaseJwtVerifier

AUTHENTICATED_SUBJECT_TYPE = "supabase_user"


@dataclass(frozen=True)
class ResolvedSubject:
    """Ownership identity passed to service/repository layers."""

    subject_type: str
    subject_id: str


class SubjectResolutionError(Exception):
    """Transport-facing auth/identity resolution error."""

    def __init__(self, *, status_code: int, detail: str) -> None:
        super().__init__(detail)
        self.status_code = status_code
        self.detail = detail


class AuthSubjectResolver:
    """Resolve request ownership subject from Authorization header.

    JWT-only ownership contract:
    - authenticated caller -> (`supabase_user`, <jwt sub>)
    """

    def __init__(
        self,
        *,
        jwt_verifier: SupabaseJwtVerifier,
    ) -> None:
        self._jwt_verifier = jwt_verifier

    def resolve(
        self,
        *,
        authorization_header: str | None,
    ) -> ResolvedSubject:
        # In JWT-only mode, every request owner must come from bearer token.
        bearer_token = _extract_bearer_token(authorization_header)
        if not bearer_token:
            raise SubjectResolutionError(
                status_code=401,
                detail="Missing Bearer token.",
            )
        return self._resolve_from_bearer(bearer_token)

    def _resolve_from_bearer(self, bearer_token: str) -> ResolvedSubject:
        try:
            principal = self._jwt_verifier.verify_access_token(bearer_token)
        except SupabaseJwtVerificationError as error:
            raise SubjectResolutionError(status_code=401, detail=str(error)) from error
        return ResolvedSubject(
            subject_type=AUTHENTICATED_SUBJECT_TYPE,
            subject_id=principal.user_id,
        )


def _extract_bearer_token(authorization_header: str | None) -> str | None:
    """Extract compact JWT string from Authorization header, if present."""

    if not authorization_header:
        return None

    scheme, separator, token = authorization_header.partition(" ")
    if separator == "" or scheme.lower() != "bearer" or not token.strip():
        raise SubjectResolutionError(
            status_code=401,
            detail="Invalid Authorization header. Expected format: Bearer <token>.",
        )
    return token.strip()
