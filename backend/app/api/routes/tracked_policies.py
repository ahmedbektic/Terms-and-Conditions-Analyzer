"""HTTP routes for tracked-policy watchlist registration and management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..deps import get_request_subject, get_tracked_policy_service
from ..mappers.tracked_policies import to_tracked_policy_response
from ...schemas.tracked_policies import TrackedPolicyCreateRequest, TrackedPolicyResponse
from ...services.request_subject import RequestSubject
from ...services.tracked_policy_service import (
    DuplicateTrackedPolicyError,
    InvalidTrackedPolicySourceError,
    TrackedPolicyNotFoundError,
    TrackedPolicyService,
)

router = APIRouter(prefix="/tracked-policies")


@router.post("", response_model=TrackedPolicyResponse, status_code=status.HTTP_201_CREATED)
def create_tracked_policy(
    payload: TrackedPolicyCreateRequest,
    subject: RequestSubject = Depends(get_request_subject),
    service: TrackedPolicyService = Depends(get_tracked_policy_service),
) -> TrackedPolicyResponse:
    """Register a verified tracked policy URL for the active request subject."""

    try:
        tracked_policy = service.create_tracked_policy(
            subject=subject,
            source_url=payload.source_url,
        )
    except InvalidTrackedPolicySourceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail=str(error),
        ) from error
    except DuplicateTrackedPolicyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    return to_tracked_policy_response(tracked_policy)


@router.get("", response_model=list[TrackedPolicyResponse])
def list_tracked_policies(
    subject: RequestSubject = Depends(get_request_subject),
    service: TrackedPolicyService = Depends(get_tracked_policy_service),
) -> list[TrackedPolicyResponse]:
    """Return active tracked policies for the authenticated request subject."""

    tracked_policies = service.list_tracked_policies(subject=subject)
    return [to_tracked_policy_response(tracked_policy) for tracked_policy in tracked_policies]


@router.delete("/{tracked_policy_id}", status_code=status.HTTP_204_NO_CONTENT)
def remove_tracked_policy(
    tracked_policy_id: UUID,
    subject: RequestSubject = Depends(get_request_subject),
    service: TrackedPolicyService = Depends(get_tracked_policy_service),
) -> Response:
    """Soft-delete one tracked policy for the authenticated request subject."""

    try:
        service.remove_tracked_policy(subject=subject, tracked_policy_id=tracked_policy_id)
    except TrackedPolicyNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return Response(status_code=status.HTTP_204_NO_CONTENT)
