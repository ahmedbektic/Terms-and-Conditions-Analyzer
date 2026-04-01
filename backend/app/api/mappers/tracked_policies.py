"""Transport mappers for tracked-policy response payloads."""

from ...repositories.models import StoredTrackedPolicy
from ...schemas.tracked_policies import TrackedPolicyResponse


def to_tracked_policy_response(tracked_policy: StoredTrackedPolicy) -> TrackedPolicyResponse:
    """Map a persistence tracked-policy model to the API response contract."""

    return TrackedPolicyResponse(
        id=tracked_policy.id,
        canonical_url=tracked_policy.canonical_url,
        display_name=tracked_policy.display_name,
        source_type=tracked_policy.source_type,
        tracking_status=tracked_policy.tracking_status.value,
        last_checked_at=tracked_policy.last_checked_at,
        created_at=tracked_policy.created_at,
    )
