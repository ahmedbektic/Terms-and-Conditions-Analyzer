"""Pydantic request/response contracts for report endpoints.

Layer: transport schema.
These models define the API contract consumed by the dashboard client.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator, model_validator

from ..core.input_validation import (
    MAX_SOURCE_URL_LENGTH,
    MAX_TERMS_TEXT_LENGTH,
    MAX_TITLE_LENGTH,
    MAX_TRIGGER_LENGTH,
    sanitize_optional_single_line_text,
    sanitize_optional_terms_text,
    sanitize_single_line_text,
    validate_agreed_at,
    validate_external_source_url,
)


class AnalysisTriggerRequest(BaseModel):
    """Request body for manual analysis trigger endpoint."""

    model_config = ConfigDict(extra="forbid")

    trigger: StrictStr = Field(default="manual", max_length=MAX_TRIGGER_LENGTH)

    @field_validator("trigger")
    @classmethod
    def validate_trigger(cls, value: str) -> str:
        return sanitize_single_line_text(
            value,
            field_name="Trigger",
            max_length=MAX_TRIGGER_LENGTH,
        )


class ReportAnalyzeRequest(BaseModel):
    """Request body for one-shot submit-and-analyze flow."""

    model_config = ConfigDict(extra="forbid")

    title: StrictStr | None = Field(default=None, max_length=MAX_TITLE_LENGTH)
    source_url: StrictStr | None = Field(default=None, max_length=MAX_SOURCE_URL_LENGTH)
    agreed_at: datetime | None = None
    terms_text: StrictStr | None = Field(default=None, max_length=MAX_TERMS_TEXT_LENGTH)

    @field_validator("title")
    @classmethod
    def sanitize_title(cls, value: str | None) -> str | None:
        return sanitize_optional_single_line_text(
            value,
            field_name="Title",
            max_length=MAX_TITLE_LENGTH,
        )

    @field_validator("source_url")
    @classmethod
    def sanitize_source_url(cls, value: str | None) -> str | None:
        if value is None:
            return None
        return validate_external_source_url(value)

    @field_validator("terms_text")
    @classmethod
    def sanitize_terms_text_value(cls, value: str | None) -> str | None:
        return sanitize_optional_terms_text(
            value,
            max_length=MAX_TERMS_TEXT_LENGTH,
        )

    @field_validator("agreed_at")
    @classmethod
    def validate_agreed_at_value(cls, value: datetime | None) -> datetime | None:
        return validate_agreed_at(value)

    @model_validator(mode="after")
    def validate_input(self) -> "ReportAnalyzeRequest":
        """Ensure at least one analyzable source is provided."""

        has_terms_text = bool(self.terms_text and self.terms_text.strip())
        has_source_url = bool(self.source_url and self.source_url.strip())
        if not has_terms_text and not has_source_url:
            raise ValueError("Either terms_text or source_url must be provided.")
        return self


class FlaggedClauseResponse(BaseModel):
    """Serialized flagged clause entry returned to clients."""

    model_config = ConfigDict(extra="forbid")

    clause_type: str
    severity: str
    excerpt: str
    explanation: str


class ReportResponse(BaseModel):
    """Full report payload for detail views and immediate analyze responses."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    agreement_id: UUID
    source_type: str
    source_value: str
    raw_input_excerpt: str
    status: str
    summary: str
    trust_score: int
    model_name: str
    flagged_clauses: list[FlaggedClauseResponse]
    created_at: datetime
    completed_at: datetime | None


class ReportListItemResponse(BaseModel):
    """Compact report payload for history listings."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    agreement_id: UUID
    source_type: str
    source_value: str
    status: str
    trust_score: int
    model_name: str
    created_at: datetime
