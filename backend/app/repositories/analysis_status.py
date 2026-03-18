"""Internal report-analysis lifecycle status model.

This keeps status values explicit and shared across repositories/services while
preserving transport contracts that currently expose `status` as a string.
"""

from enum import Enum

__all__ = [
    "AnalysisLifecycleStatus",
    "normalize_analysis_lifecycle_status",
]


class AnalysisLifecycleStatus(str, Enum):
    """Supported lifecycle states for analysis execution."""

    PENDING = "pending"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"


def normalize_analysis_lifecycle_status(
    status: str | AnalysisLifecycleStatus,
) -> AnalysisLifecycleStatus:
    """Coerce input status to enum and reject unsupported values."""

    if isinstance(status, AnalysisLifecycleStatus):
        return status
    normalized = str(status).strip().lower()
    try:
        return AnalysisLifecycleStatus(normalized)
    except ValueError as error:
        raise ValueError(
            "Unsupported analysis lifecycle status. Expected one of: "
            "pending, running, completed, failed."
        ) from error
