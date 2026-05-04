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
    latest_change_status: str
    latest_change_detected_at: datetime | None
    created_at: datetime
    snapshot_version_count: int


class TrackedPolicyCreateResponse(TrackedPolicyResponse):
    """Create-response payload including the saved report baseline used for enrollment."""

    baseline_report_id: UUID
    baseline_report_action: Literal["created", "reused"]


class TrackedPolicySnapshotResponse(BaseModel):
    """Serialized tracked-policy snapshot metadata used by history/compare clients."""

    model_config = ConfigDict(extra="forbid")

    snapshot_id: UUID
    version_number: int
    captured_at: datetime
    source_url: str | None
    final_url: str | None
    capture_status: str
    change_status: str | None


class TrackedPolicySnapshotCompareBlockResponse(BaseModel):
    """One structured diff block for tracked-policy comparisons."""

    model_config = ConfigDict(extra="forbid")

    change_type: Literal["unchanged", "added", "removed"]
    older_text: str | None
    newer_text: str | None


class TrackedPolicySnapshotComparisonResponse(BaseModel):
    """Serialized compare payload for two stored versions of one tracked policy."""

    model_config = ConfigDict(extra="forbid")

    tracked_policy: TrackedPolicyResponse
    older_snapshot: TrackedPolicySnapshotResponse
    newer_snapshot: TrackedPolicySnapshotResponse
    diff_blocks: list[TrackedPolicySnapshotCompareBlockResponse]
    comparison_outcome: Literal["meaningful_changes", "no_meaningful_changes"]
    normalization_notice: str | None
    render_mode: Literal["split_or_unified"]


class TrackedPolicyCheckExecutionResponse(BaseModel):
    """Serialized tracked-policy check execution payload."""

    model_config = ConfigDict(extra="forbid")

    id: UUID
    tracked_policy_id: UUID
    status: str
    result_snapshot_created: bool | None
    failure_message: str | None
    execute_started_at: datetime | None
    execute_finished_at: datetime | None


class TrackedPolicyCheckExecutionEnvelope(BaseModel):
    """Response payload enclosing the execution model and optionally the resulting policy."""

    model_config = ConfigDict(extra="forbid")

    execution: TrackedPolicyCheckExecutionResponse
    tracked_policy: TrackedPolicyResponse | None
