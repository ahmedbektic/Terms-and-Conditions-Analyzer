"""HTTP routes for agreement creation and manual analysis trigger.

Layer: transport handlers.
These routes expose explicit agreement lifecycle endpoints that can later be
reused by browser-extension ingestion flows.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import get_analysis_service, get_request_subject
from ..mappers.reports import to_report_response
from ...schemas.agreements import AgreementCreateRequest, AgreementResponse
from ...schemas.reports import AnalysisTriggerRequest, ReportResponse
from ...services.analysis_service import (
    AgreementNotFoundError,
    AnalysisOrchestrationService,
    InvalidSubmissionError,
    RequestSubject,
)

router = APIRouter(prefix="/agreements")


@router.post("", response_model=AgreementResponse, status_code=status.HTTP_201_CREATED)
def create_agreement(
    payload: AgreementCreateRequest,
    subject: RequestSubject = Depends(get_request_subject),
    service: AnalysisOrchestrationService = Depends(get_analysis_service),
) -> AgreementResponse:
    """Persist an agreement record without running analysis."""

    try:
        agreement = service.create_agreement(
            subject=subject,
            title=payload.title,
            source_url=payload.source_url,
            agreed_at=payload.agreed_at,
            terms_text=payload.terms_text,
        )
    except InvalidSubmissionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    return AgreementResponse(
        id=agreement.id,
        title=agreement.title,
        source_url=agreement.source_url,
        agreed_at=agreement.agreed_at,
        created_at=agreement.created_at,
    )


@router.post(
    "/{agreement_id}/analyses",
    response_model=ReportResponse,
    status_code=status.HTTP_201_CREATED,
)
def trigger_manual_analysis(
    agreement_id: UUID,
    payload: AnalysisTriggerRequest,
    subject: RequestSubject = Depends(get_request_subject),
    service: AnalysisOrchestrationService = Depends(get_analysis_service),
) -> ReportResponse:
    """Run manual analysis for an existing agreement and return saved report."""

    if payload.trigger != "manual":
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail='Only trigger="manual" is currently supported.',
        )
    try:
        report = service.trigger_manual_analysis(subject=subject, agreement_id=agreement_id)
    except AgreementNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return to_report_response(report)
