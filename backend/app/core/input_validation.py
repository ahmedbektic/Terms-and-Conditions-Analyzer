"""Shared input validation and sanitization helpers.

Layer: transport/core validation.
These helpers harden every untrusted string before it reaches persistence,
remote-fetch logic, or downstream rendering surfaces.
"""

from __future__ import annotations

from datetime import datetime, timedelta, timezone
from html import unescape
import ipaddress
import re
import unicodedata
from urllib.parse import urlsplit, urlunsplit

MAX_TITLE_LENGTH = 200
MAX_SOURCE_URL_LENGTH = 2048
MAX_TERMS_TEXT_LENGTH = 200_000
MAX_TRIGGER_LENGTH = 32
MAX_EMAIL_LENGTH = 320

_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_UNSAFE_HTML_BLOCK_PATTERN = re.compile(
    r"(?is)<(script|style|iframe|object|embed|svg|noscript)[^>]*>.*?</\1>"
)
_HTML_TAG_PATTERN = re.compile(r"(?s)<[^>]+>")
_WHITESPACE_PATTERN = re.compile(r"\s+")


def sanitize_single_line_text(
    value: str,
    *,
    field_name: str,
    max_length: int,
    min_length: int = 0,
) -> str:
    """Return a normalized single-line text value or raise validation error."""

    normalized = normalize_untrusted_text(value)
    if not normalized:
        raise ValueError(f"{field_name} cannot be blank.")
    if len(normalized) < min_length:
        raise ValueError(f"{field_name} must be at least {min_length} characters.")
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer.")
    return normalized


def sanitize_optional_single_line_text(
    value: str | None,
    *,
    field_name: str,
    max_length: int,
) -> str | None:
    """Normalize optional text values and collapse empty values to None."""

    if value is None:
        return None
    normalized = normalize_untrusted_text(value)
    if not normalized:
        return None
    if len(normalized) > max_length:
        raise ValueError(f"{field_name} must be {max_length} characters or fewer.")
    return normalized


def sanitize_terms_text(value: str, *, min_length: int = 20, max_length: int | None = None) -> str:
    """Normalize submitted terms text into plain text suitable for storage/analysis."""

    normalized = normalize_untrusted_text(value)
    if not normalized:
        raise ValueError("Agreement text cannot be blank.")
    if len(normalized) < min_length:
        raise ValueError(f"Agreement text must be at least {min_length} characters.")
    effective_max_length = max_length or MAX_TERMS_TEXT_LENGTH
    if len(normalized) > effective_max_length:
        raise ValueError(f"Agreement text must be {effective_max_length} characters or fewer.")
    return normalized


def sanitize_optional_terms_text(
    value: str | None,
    *,
    min_length: int = 20,
    max_length: int | None = None,
) -> str | None:
    """Normalize optional terms text while preserving missing values."""

    if value is None:
        return None
    normalized = normalize_untrusted_text(value)
    if not normalized:
        return None
    return sanitize_terms_text(
        normalized,
        min_length=min_length,
        max_length=max_length,
    )


def validate_external_source_url(value: str) -> str:
    """Validate a user-submitted source URL for safe server-side fetching."""

    normalized = sanitize_single_line_text(
        value,
        field_name="Source URL",
        max_length=MAX_SOURCE_URL_LENGTH,
    )

    try:
        parsed = urlsplit(normalized)
    except ValueError as error:
        raise ValueError("Source URL must be a valid absolute URL.") from error

    scheme = parsed.scheme.lower()
    if scheme not in {"http", "https"}:
        raise ValueError("Source URL must use http or https.")
    if not parsed.netloc or not parsed.hostname:
        raise ValueError("Source URL must include a hostname.")
    if parsed.username or parsed.password:
        raise ValueError("Source URL cannot include embedded credentials.")
    if _is_disallowed_hostname(parsed.hostname):
        raise ValueError("Source URL must target a public hostname.")

    return urlunsplit((scheme, parsed.netloc, parsed.path or "", parsed.query, ""))


def validate_agreed_at(value: datetime | None) -> datetime | None:
    """Reject implausible future agreement timestamps."""

    if value is None:
        return None

    now = datetime.now(tz=value.tzinfo or timezone.utc)
    if value > now + timedelta(days=1):
        raise ValueError("Agreed date cannot be in the future.")
    return value


def sanitize_email_address(value: str) -> str:
    """Normalize an email address into a strict credential identifier."""

    normalized = sanitize_single_line_text(
        value,
        field_name="Email",
        max_length=MAX_EMAIL_LENGTH,
    ).lower()
    if not re.fullmatch(r"[^@\s]+@[^@\s]+\.[^@\s]+", normalized):
        raise ValueError("Email address is invalid.")
    return normalized


def normalize_untrusted_text(value: str) -> str:
    """Normalize untrusted text into plain text without enforcing field lengths."""

    normalized = unicodedata.normalize("NFKC", value)
    normalized = _CONTROL_CHARACTER_PATTERN.sub(" ", normalized)
    normalized = _UNSAFE_HTML_BLOCK_PATTERN.sub(" ", normalized)
    normalized = _HTML_TAG_PATTERN.sub(" ", normalized)
    normalized = unescape(normalized)
    return _WHITESPACE_PATTERN.sub(" ", normalized).strip()


def _is_disallowed_hostname(hostname: str) -> bool:
    normalized = hostname.strip().rstrip(".").lower()
    if not normalized:
        return True
    if normalized in {"localhost", "0.0.0.0"}:
        return True
    if normalized.endswith((".local", ".internal", ".localhost")):
        return True

    try:
        address = ipaddress.ip_address(normalized)
    except ValueError:
        return False

    return bool(
        address.is_private
        or address.is_loopback
        or address.is_link_local
        or address.is_multicast
        or address.is_reserved
        or address.is_unspecified
    )
