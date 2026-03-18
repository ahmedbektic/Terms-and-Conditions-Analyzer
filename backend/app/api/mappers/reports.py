"""Transport mappers for report response payloads.

Keeping response mapping in one place avoids divergence between route modules
that return the same report schema.
"""

from ...repositories.models import StoredFlaggedClause, StoredReport
from ...schemas.reports import FlaggedClauseResponse, ReportResponse


def to_report_response(report: StoredReport) -> ReportResponse:
    """Map persistence report model to API response schema."""

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
        flagged_clauses=[to_flagged_clause_response(clause) for clause in report.flagged_clauses],
        created_at=report.created_at,
        completed_at=report.completed_at,
    )


def to_flagged_clause_response(clause: StoredFlaggedClause) -> FlaggedClauseResponse:
    """Map one persistence flagged clause model to API schema."""

    return FlaggedClauseResponse(
        clause_type=clause.clause_type,
        severity=clause.severity,
        excerpt=clause.excerpt,
        explanation=clause.explanation,
    )
