"""Pydantic request/response contracts for agreement endpoints.

Layer: transport schema.
Agreement creation is separated from report generation to support future manual
or extension-triggered analysis workflows.
"""

from datetime import datetime
from uuid import UUID

from pydantic import BaseModel, Field


class AgreementCreateRequest(BaseModel):
    """Request payload for creating a persisted agreement record."""

    title: str | None = Field(default=None, max_length=200)
    source_url: str | None = Field(default=None, max_length=2048)
    agreed_at: datetime | None = None
    terms_text: str = Field(min_length=20)


class AgreementResponse(BaseModel):
    """Serialized agreement payload returned after creation."""

    id: UUID
    title: str | None
    source_url: str | None
    agreed_at: datetime | None
    created_at: datetime
