"""Internal report provenance model used for watchlist-baseline eligibility."""

from enum import Enum

__all__ = [
    "ReportContentCaptureKind",
    "normalize_report_content_capture_kind",
]


class ReportContentCaptureKind(str, Enum):
    """Supported content-capture provenance states for saved reports."""

    FETCHED_URL = "fetched_url"
    SUBMITTED_TEXT = "submitted_text"
    FALLBACK_PLACEHOLDER = "fallback_placeholder"
    LEGACY_UNKNOWN = "legacy_unknown"


def normalize_report_content_capture_kind(
    value: ReportContentCaptureKind | str,
) -> ReportContentCaptureKind:
    """Return a normalized capture-kind enum or raise for unknown values."""

    if isinstance(value, ReportContentCaptureKind):
        return value
    try:
        return ReportContentCaptureKind(str(value).strip().lower())
    except ValueError as error:
        raise ValueError(f"Unsupported report content capture kind: {value}") from error
