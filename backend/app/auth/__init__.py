"""Authentication boundary utilities.

This package centralizes request-auth concerns so route handlers can stay thin
and service/repository layers remain auth-agnostic.
"""

from .subject_resolver import AuthSubjectResolver, ResolvedSubject, SubjectResolutionError
from .runtime import build_request_subject_resolver
from .supabase_jwt import (
    SupabaseJwtConfigurationError,
    SupabaseJwtVerificationError,
    SupabaseJwtVerifier,
)

__all__ = [
    "AuthSubjectResolver",
    "ResolvedSubject",
    "SubjectResolutionError",
    "build_request_subject_resolver",
    "SupabaseJwtConfigurationError",
    "SupabaseJwtVerificationError",
    "SupabaseJwtVerifier",
]
