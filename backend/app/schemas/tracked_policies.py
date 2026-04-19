"""Pydantic request/response contracts for tracked-policy watchlist endpoints."""

from datetime import datetime
from typing import Literal
from uuid import UUID

from pydantic import BaseModel, ConfigDict, Field, StrictStr, field_validator

from ..core.input_validation import MAX_SOURCE_URL_LENGTH, validate_external_source_url


class TrackedPolicyCreateRequest(BaseModel):
    """Request payload for registering a new tracked policy URL."""

    model_config = ConfigDict(extra="forbid")

    source_url: StrictStr = Field(max_length=MAX_SOURCE_URL_LENGTH)

    @field_validator("source_url")
    @classmethod
    def sanitize_source_url(cls, value: str) -> str:
        return validate_external_source_url(value)


class TrackedPolicyResponse(BaseModel):
    """Serialized tracked-policy payload returned to dashboard clients."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    canonical_url: str
    display_name: str
    source_type: str
    tracking_status: str
    last_checked_at: datetime | None
    last_successful_capture_at: datetime | None
    latest_capture_status: str
    latest_capture_message: str | None
    created_at: datetime
    snapshot_version_count: int


class TrackedPolicyCreateResponse(TrackedPolicyResponse):
    """Create-response payload including the saved report baseline used for enrollment."""

    baseline_report_id: UUID
    baseline_report_action: Literal["created", "reused"]
