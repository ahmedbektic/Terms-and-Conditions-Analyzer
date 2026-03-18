"""Backend-internal extraction/ingestion boundary contracts.

Purpose:
- define stable DTOs for source ingestion and extraction output
- isolate orchestration and preparation from concrete extraction implementations
- carry upgrade-ready metadata (confidence, warnings, errors) without changing
  public API contracts consumed by web/extension clients

Dependencies:
- standard library only

Used by:
- `SubmissionPreparationService` today
- future URL ingestion/fetch and richer extraction pipelines

Boundary note:
- These contracts are intentionally backend-internal and are not exposed as
  external HTTP schemas. Route/API payloads remain unchanged.
"""

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum

__all__ = [
    "ExtractionIngestionRequest",
    "ExtractionIngestionResult",
    "ExtractionMetadata",
    "ExtractionSourceKind",
]


class ExtractionSourceKind(str, Enum):
    """Canonical source kinds supported by the ingestion boundary."""

    RAW_TEXT = "raw_text"
    URL = "url"
    EXTENSION_TEXT = "extension_text"


@dataclass(frozen=True)
class ExtractionIngestionRequest:
    """Normalized input to the backend extraction/ingestion boundary."""

    source_kind: ExtractionSourceKind
    original_source_value: str
    submitted_text: str | None
    title: str | None
    agreed_at: datetime | None
    source_metadata: dict[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ExtractionMetadata:
    """Metadata emitted by extraction/ingestion for observability and upgrades."""

    extraction_strategy: str
    extractor_name: str
    confidence: float | None = None
    warnings: tuple[str, ...] = ()
    errors: tuple[str, ...] = ()


@dataclass(frozen=True)
class ExtractionIngestionResult:
    """Structured extraction output consumed by orchestration and analysis."""

    source_kind: ExtractionSourceKind
    original_source_value: str
    normalized_text: str
    source_type: str
    source_value: str
    raw_input_excerpt: str
    title: str | None
    source_url: str | None
    agreed_at: datetime | None
    metadata: ExtractionMetadata
