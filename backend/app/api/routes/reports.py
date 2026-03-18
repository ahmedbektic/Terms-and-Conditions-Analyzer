"""HTTP routes for report submission and retrieval.

Layer: transport handlers.
Handlers only validate request/response transport concerns and delegate workflow
to `AnalysisOrchestrationService`.
"""

from uuid import UUID

from fastapi import APIRouter, Depends, HTTPException, status

from ..deps import get_analysis_service, get_request_subject
from ..mappers.reports import to_report_response
from ...schemas.reports import (
    ReportAnalyzeRequest,
    ReportListItemResponse,
    ReportResponse,
)
from ...services.analysis_service import (
    AnalysisOrchestrationService,
    AnalysisSubmission,
    InvalidSubmissionError,
    ReportNotFoundError,
    RequestSubject,
)

router = APIRouter(prefix="/reports")


@router.post("/analyze", response_model=ReportResponse, status_code=status.HTTP_201_CREATED)
def submit_and_analyze(
    payload: ReportAnalyzeRequest,
    subject: RequestSubject = Depends(get_request_subject),
    service: AnalysisOrchestrationService = Depends(get_analysis_service),
) -> ReportResponse:
    """Submit terms/URL, run analysis, persist report, and return full report payload."""

    try:
        report = service.submit_and_analyze(
            subject=subject,
            submission=AnalysisSubmission(
                title=payload.title,
                source_url=payload.source_url,
                agreed_at=payload.agreed_at,
                terms_text=payload.terms_text,
            ),
        )
    except InvalidSubmissionError as error:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail=str(error)
        ) from error

    return to_report_response(report)


@router.get("", response_model=list[ReportListItemResponse])
def list_reports(
    subject: RequestSubject = Depends(get_request_subject),
    service: AnalysisOrchestrationService = Depends(get_analysis_service),
) -> list[ReportListItemResponse]:
    """Return owner-scoped report history for dashboard list rendering."""

    reports = service.list_reports(subject=subject)
    return [
        ReportListItemResponse(
            id=report.id,
            agreement_id=report.agreement_id,
            source_type=report.source_type,
            source_value=report.source_value,
            status=report.status.value,
            trust_score=report.trust_score,
            model_name=report.model_name,
            created_at=report.created_at,
        )
        for report in reports
    ]


@router.get("/{report_id}", response_model=ReportResponse)
def get_report(
    report_id: UUID,
    subject: RequestSubject = Depends(get_request_subject),
    service: AnalysisOrchestrationService = Depends(get_analysis_service),
) -> ReportResponse:
    """Fetch one saved report by id for the active request subject."""

    try:
        report = service.get_report(subject=subject, report_id=report_id)
    except ReportNotFoundError as error:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail=str(error)) from error

    return to_report_response(report)
