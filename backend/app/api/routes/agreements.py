"""HTTP routes for agreement creation and manual analysis trigger.

Layer: transport handlers.
These routes expose explicit agreement lifecycle endpoints that can later be
reused by browser-extension ingestion flows.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import get_analysis_service, get_request_subject
from ...repositories.models import StoredFlaggedClause
from ...schemas.agreements import AgreementCreateRequest, AgreementResponse
from ...schemas.reports import AnalysisTriggerRequest, FlaggedClauseResponse, ReportResponse
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

    return ReportResponse(
        id=report.id,
        agreement_id=report.agreement_id,
        source_type=report.source_type,
        source_value=report.source_value,
        raw_input_excerpt=report.raw_input_excerpt,
        status=report.status,
        summary=report.summary,
        trust_score=report.trust_score,
        model_name=report.model_name,
        flagged_clauses=[_to_flagged_clause_response(clause) for clause in report.flagged_clauses],
        created_at=report.created_at,
        completed_at=report.completed_at,
    )


def _to_flagged_clause_response(clause: StoredFlaggedClause) -> FlaggedClauseResponse:
    """Map persistence clause model to response schema."""

    return FlaggedClauseResponse(
        clause_type=clause.clause_type,
        severity=clause.severity,
        excerpt=clause.excerpt,
        explanation=clause.explanation,
    )
