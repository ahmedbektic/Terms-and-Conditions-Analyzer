"""HTTP routes for tracked-policy watchlist registration and management."""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, Query, Response, status

from ..deps import (
    get_request_subject,
    get_tracked_policy_service,
    get_tracked_policy_versions_service,
)
from ..mappers.tracked_policies import (
    to_tracked_policy_check_execution_envelope,
    to_tracked_policy_create_response,
    to_tracked_policy_response,
    to_tracked_policy_snapshot_comparison_response,
    to_tracked_policy_snapshot_response,
)
from ...schemas.tracked_policies import (
    TrackedPolicyCheckExecutionEnvelope,
    TrackedPolicyCheckExecutionResponse,
    TrackedPolicyCreateRequest,
    TrackedPolicyCreateResponse,
    TrackedPolicyResponse,
    TrackedPolicySnapshotComparisonResponse,
    TrackedPolicySnapshotResponse,
)
from ...services.request_subject import RequestSubject
from ...services.tracked_policy_check_execution_service import (
    TrackedPolicyCheckExecutionNotFoundError,
    TrackedPolicyCheckExecutionResult,
)
from ...services.tracked_policy_service import (
    DuplicateTrackedPolicyError,
    InvalidTrackedPolicySourceError,
    TrackedPolicyBaselineReportError,
    TrackedPolicyNotFoundError,
    TrackedPolicyService,
)
from ...services.tracked_policy_versions_service import (
    TrackedPolicySnapshotNotFoundError,
    TrackedPolicyVersionComparisonError,
    TrackedPolicyVersionNotFoundError,
    TrackedPolicyVersionsService,
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


@router.post("/{tracked_policy_id}/check", response_model=TrackedPolicyCheckExecutionEnvelope)
def check_tracked_policy(
    tracked_policy_id: UUID,
    subject: RequestSubject = Depends(get_request_subject),
    service: TrackedPolicyService = Depends(get_tracked_policy_service),
) -> TrackedPolicyCheckExecutionEnvelope:
    """Fetch the live policy page, store a snapshot when text changes, and refresh status."""

    try:
        execution_result = service.check_tracked_policy(
            subject=subject,
            tracked_policy_id=tracked_policy_id,
        )
    except TrackedPolicyNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return to_tracked_policy_check_execution_envelope(execution_result)


@router.get("/executions/{execution_id}", response_model=TrackedPolicyCheckExecutionResponse)
def get_tracked_policy_execution(
    execution_id: UUID,
    subject: RequestSubject = Depends(get_request_subject),
    service: TrackedPolicyService = Depends(get_tracked_policy_service),
) -> TrackedPolicyCheckExecutionResponse:
    """Retrieve the status of a specific tracked-policy check execution."""

    try:
        execution = service.get_tracked_policy_execution(
            subject=subject,
            execution_id=execution_id,
        )
    except TrackedPolicyCheckExecutionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return to_tracked_policy_check_execution_envelope(
        execution_result=TrackedPolicyCheckExecutionResult(
            execution=execution,
            tracked_policy=None,
        )
    ).execution


@router.get(
    "/{tracked_policy_id}/snapshots",
    response_model=list[TrackedPolicySnapshotResponse],
)
def list_tracked_policy_snapshots(
    tracked_policy_id: UUID,
    subject: RequestSubject = Depends(get_request_subject),
    service: TrackedPolicyVersionsService = Depends(get_tracked_policy_versions_service),
) -> list[TrackedPolicySnapshotResponse]:
    """Return stored version history for one tracked policy owned by the caller."""

    try:
        _, snapshots = service.list_snapshot_history(
            subject=subject,
            tracked_policy_id=tracked_policy_id,
        )
    except TrackedPolicyVersionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return [to_tracked_policy_snapshot_response(snapshot) for snapshot in snapshots]


@router.get(
    "/{tracked_policy_id}/compare",
    response_model=TrackedPolicySnapshotComparisonResponse,
)
def compare_tracked_policy_snapshots(
    tracked_policy_id: UUID,
    snapshot_a: UUID = Query(...),
    snapshot_b: UUID = Query(...),
    subject: RequestSubject = Depends(get_request_subject),
    service: TrackedPolicyVersionsService = Depends(get_tracked_policy_versions_service),
) -> TrackedPolicySnapshotComparisonResponse:
    """Compare two stored versions from one tracked policy owned by the caller."""

    try:
        comparison_result = service.compare_snapshots(
            subject=subject,
            tracked_policy_id=tracked_policy_id,
            snapshot_a_id=snapshot_a,
            snapshot_b_id=snapshot_b,
        )
    except TrackedPolicyVersionComparisonError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_CONTENT,
            detail=str(error),
        ) from error
    except TrackedPolicySnapshotNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error
    except TrackedPolicyVersionNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return to_tracked_policy_snapshot_comparison_response(comparison_result)


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
