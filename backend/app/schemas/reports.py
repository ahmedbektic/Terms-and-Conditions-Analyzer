"""Pydantic request/response contracts for report endpoints.

Layer: transport schema.
These models define the API contract consumed by the dashboard client.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field, model_validator


class AnalysisTriggerRequest(BaseModel):
    """Request body for manual analysis trigger endpoint."""

    trigger: str = Field(default="manual")


class ReportAnalyzeRequest(BaseModel):
    """Request body for one-shot submit-and-analyze flow."""

    title: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=2048)
    agreed_at: datetime | None = None
    terms_text: str | None = None

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

    clause_type: str
    severity: str
    excerpt: str
    explanation: str


class ReportResponse(BaseModel):
    """Full report payload for detail views and immediate analyze responses."""

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

    id: UUID
    agreement_id: UUID
    source_type: str
    source_value: str
    status: str
    trust_score: int
    model_name: str
    created_at: datetime
