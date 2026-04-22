"""Optional backend Sentry initialization and event filtering."""

from __future__ import annotations

from collections.abc import Mapping, MutableMapping
import logging
import re
from typing import Any

from .config import Settings

LOGGER = logging.getLogger(__name__)

_FILTERED_VALUE = "[Filtered]"
_NOISE_PATHS = {"/health"}
_SENTRY_INITIALIZED = False
_COMMON_EVENT_TAGS: dict[str, str] = {}
_SERVICE_NAME = "backend-api"
_SERVICE_SURFACE = "fastapi-api"
_SENSITIVE_KEY_PARTS = (
    "authorization",
    "cookie",
    "token",
    "secret",
    "password",
    "apikey",
    "jwt",
)
_POLICY_TEXT_KEYS = {
    "body",
    "requestbody",
    "termstext",
    "submittedtext",
    "normalizedtext",
    "normalizedtextbody",
    "rawtextbody",
    "capturedtext",
    "policytext",
    "rawpolicytext",
    "fullpolicytext",
    "rawinputexcerpt",
}


def init_sentry(*, settings: Settings) -> bool:
    """Initialize Sentry when a DSN is configured.

    The backend must remain safe in local and unset-DSN environments, so this
    function returns without side effects when Sentry is not configured.
    """

    global _SENTRY_INITIALIZED

    if _SENTRY_INITIALIZED:
        return True

    dsn = settings.sentry_dsn.strip()
    if not dsn:
        return False

    try:
        import sentry_sdk
        from sentry_sdk.integrations.fastapi import FastApiIntegration
    except ImportError:
        LOGGER.warning(
            "Sentry DSN is configured but sentry-sdk is not installed; skipping backend Sentry initialization."
        )
        return False

    release = settings.sentry_release.strip()
    environment = settings.effective_sentry_environment
    _COMMON_EVENT_TAGS.clear()
    _COMMON_EVENT_TAGS.update(
        {
            "service": _SERVICE_NAME,
            "service_surface": _SERVICE_SURFACE,
            "deployment_environment": environment,
        }
    )
    if release:
        _COMMON_EVENT_TAGS["release"] = release

    sentry_sdk.init(
        dsn=dsn,
        environment=environment,
        release=release or None,
        traces_sample_rate=_normalize_sample_rate(settings.sentry_traces_sample_rate),
        send_default_pii=False,
        max_request_body_size="never",
        before_send=_before_send,
        before_send_transaction=_before_send_transaction,
        integrations=[FastApiIntegration(transaction_style="url")],
    )
    for tag_name, tag_value in _COMMON_EVENT_TAGS.items():
        sentry_sdk.set_tag(tag_name, tag_value)
    _SENTRY_INITIALIZED = True
    return True


def _before_send(event: Any, hint: dict[str, Any]) -> dict[str, Any] | None:
    """Filter low-value events and scrub request details before sending."""

    _ = hint
    if not isinstance(event, MutableMapping):
        return None

    if _is_noise_event(event):
        return None

    _apply_common_tags(event)
    _scrub_request_data(event)
    _scrub_event_payload(event)
    return event


def _before_send_transaction(event: Any, hint: dict[str, Any]) -> dict[str, Any] | None:
    """Drop noisy transactions such as health checks."""

    _ = hint
    if not isinstance(event, MutableMapping):
        return None

    if _is_noise_event(event):
        return None
    _apply_common_tags(event)
    _scrub_event_payload(event)
    return event


def _is_noise_event(event: object) -> bool:
    if not isinstance(event, Mapping):
        return False

    transaction_name = str(event.get("transaction") or "").strip()
    if transaction_name in _NOISE_PATHS or transaction_name.endswith("/health"):
        return True

    request_data = event.get("request")
    if not isinstance(request_data, Mapping):
        return False

    request_url = str(request_data.get("url") or "").strip()
    if not request_url:
        return False

    return any(request_url.endswith(path) or f"{path}?" in request_url for path in _NOISE_PATHS)


def _scrub_request_data(event: MutableMapping[str, Any]) -> None:
    request_data = event.get("request")
    if not isinstance(request_data, MutableMapping):
        return

    headers = request_data.get("headers")
    if isinstance(headers, MutableMapping):
        for header_name in tuple(headers.keys()):
            if str(header_name).strip().lower() in {
                "authorization",
                "cookie",
                "set-cookie",
                "x-api-key",
            }:
                headers[header_name] = _FILTERED_VALUE

    for field_name in ("data", "cookies"):
        if field_name in request_data:
            request_data[field_name] = _FILTERED_VALUE


def _apply_common_tags(event: MutableMapping[str, Any]) -> None:
    tags = event.get("tags")
    if not isinstance(tags, MutableMapping):
        tags = {}
        event["tags"] = tags

    for tag_name, tag_value in _COMMON_EVENT_TAGS.items():
        tags.setdefault(tag_name, tag_value)


def _scrub_event_payload(event: MutableMapping[str, Any]) -> None:
    _scrub_mapping(event)


def _scrub_mapping(payload: MutableMapping[str, Any]) -> None:
    for key, value in tuple(payload.items()):
        if _should_filter_key(key):
            payload[key] = _FILTERED_VALUE
            continue

        if isinstance(value, MutableMapping):
            _scrub_mapping(value)
            continue

        if isinstance(value, list):
            _scrub_sequence(value)


def _scrub_sequence(values: list[Any]) -> None:
    for index, value in enumerate(values):
        if isinstance(value, MutableMapping):
            _scrub_mapping(value)
            continue

        if isinstance(value, list):
            _scrub_sequence(value)
            continue

        if isinstance(value, str) and _looks_like_bearer_token(value):
            values[index] = _FILTERED_VALUE


def _should_filter_key(key: object) -> bool:
    normalized_key = _normalize_key(str(key))
    if normalized_key in _POLICY_TEXT_KEYS:
        return True
    return any(part in normalized_key for part in _SENSITIVE_KEY_PARTS)


def _normalize_key(key: str) -> str:
    return re.sub(r"[^a-z0-9]+", "", key.lower())


def _looks_like_bearer_token(value: str) -> bool:
    return value.strip().lower().startswith("bearer ")


def _normalize_sample_rate(sample_rate: float) -> float:
    if sample_rate < 0:
        return 0.0
    if sample_rate > 1:
        return 1.0
    return sample_rate
