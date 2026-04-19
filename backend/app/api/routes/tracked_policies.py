"""HTTP routes for tracked-policy watchlist registration and management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Response, status

from ..deps import get_request_subject, get_tracked_policy_service
from ..mappers.tracked_policies import (
    to_tracked_policy_create_response,
    to_tracked_policy_response,
)
from ...schemas.tracked_policies import (
    TrackedPolicyCreateRequest,
    TrackedPolicyCreateResponse,
    TrackedPolicyResponse,
)
from ...services.request_subject import RequestSubject
from ...services.tracked_policy_service import (
    DuplicateTrackedPolicyError,
    InvalidTrackedPolicySourceError,
    TrackedPolicyBaselineReportError,
    TrackedPolicyCheckFailedError,
    TrackedPolicyNotFoundError,
    TrackedPolicyService,
)

router = APIRouter(prefix="/tracked-policies")


@router.post("", response_model=TrackedPolicyCreateResponse, status_code=status.HTTP_201_CREATED)
def create_tracked_policy(
    payload: TrackedPolicyCreateRequest,
    subject: RequestSubject = Depends(get_request_subject),
    service: TrackedPolicyService = Depends(get_tracked_policy_service),
) -> TrackedPolicyCreateResponse:
    """Register a verified policy URL after creating or reusing a saved baseline report."""

    try:
        enrollment_result = service.create_tracked_policy(
            subject=subject,
            source_url=payload.source_url,
        )
    except InvalidTrackedPolicySourceError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except TrackedPolicyBaselineReportError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except DuplicateTrackedPolicyError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail=str(error)) from error

    return to_tracked_policy_create_response(enrollment_result)


@router.get("", response_model=list[TrackedPolicyResponse])
def list_tracked_policies(
    subject: RequestSubject = Depends(get_request_subject),
    service: TrackedPolicyService = Depends(get_tracked_policy_service),
) -> list[TrackedPolicyResponse]:
    """Return active tracked policies for the authenticated request subject."""

    tracked_policies = service.list_tracked_policies(subject=subject)
    return [to_tracked_policy_response(tracked_policy) for tracked_policy in tracked_policies]


@router.post("/{tracked_policy_id}/check", response_model=TrackedPolicyResponse)
def check_tracked_policy(
    tracked_policy_id: UUID,
    subject: RequestSubject = Depends(get_request_subject),
    service: TrackedPolicyService = Depends(get_tracked_policy_service),
) -> TrackedPolicyResponse:
    """Fetch the live policy page, store a snapshot when text changes, and refresh status."""

    try:
        tracked_policy = service.check_tracked_policy(
            subject=subject,
            tracked_policy_id=tracked_policy_id,
        )
    except TrackedPolicyCheckFailedError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except TrackedPolicyNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return to_tracked_policy_response(tracked_policy)


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
