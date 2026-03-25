"""Pydantic request/response contracts for agreement endpoints.

Layer: transport schema.
Agreement creation is separated from report generation to support future manual
or extension-triggered analysis workflows.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from ..core.input_validation import (
    MAX_SOURCE_URL_LENGTH,
    MAX_TERMS_TEXT_LENGTH,
    MAX_TITLE_LENGTH,
    sanitize_optional_single_line_text,
    sanitize_terms_text,
    validate_agreed_at,
    validate_external_source_url,
)


class AgreementCreateRequest(BaseModel):
    """Request payload for creating a persisted agreement record."""

    model_config = ConfigDict(extra="forbid")

    title: StrictStr | None = Field(default=None, max_length=MAX_TITLE_LENGTH)
    source_url: StrictStr | None = Field(default=None, max_length=MAX_SOURCE_URL_LENGTH)
    agreed_at: datetime | None = None
    terms_text: StrictStr = Field(min_length=20, max_length=MAX_TERMS_TEXT_LENGTH)

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

    @field_validator("agreed_at")
    @classmethod
    def validate_agreed_at_value(cls, value: datetime | None) -> datetime | None:
        return validate_agreed_at(value)

    @field_validator("terms_text")
    @classmethod
    def sanitize_terms_text_value(cls, value: str) -> str:
        return sanitize_terms_text(
            value,
            max_length=MAX_TERMS_TEXT_LENGTH,
        )


class AgreementResponse(BaseModel):
    """Serialized agreement payload returned after creation."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    title: str | None
    source_url: str | None
    agreed_at: datetime | None
    created_at: datetime
