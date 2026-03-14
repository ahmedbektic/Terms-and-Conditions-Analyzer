from datetime import datetime, timezone
import time

from app.repositories.in_memory import (
    InMemoryAgreementRepository,
    InMemoryReportRepository,
    InMemoryStorage,
)
from app.repositories.models import StoredFlaggedClause


def test_report_repository_scopes_reports_by_owner() -> None:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)

    agreement_a = agreement_repository.create(
        subject_type="anonymous_session",
        subject_id="session-a",
        title="A",
        source_url=None,
        agreed_at=None,
        terms_text="This terms text is long enough to pass validation.",
    )
    agreement_b = agreement_repository.create(
        subject_type="anonymous_session",
        subject_id="session-b",
        title="B",
        source_url=None,
        agreed_at=None,
        terms_text="Another long enough terms text body for testing.",
    )

    report_repository.create(
        agreement_id=agreement_a.id,
        subject_type="anonymous_session",
        subject_id="session-a",
        source_type="text",
        source_value="A",
        raw_input_excerpt="A excerpt",
        status="completed",
        summary="summary A",
        trust_score=70,
        model_name="test-model",
        flagged_clauses=[],
        completed_at=datetime.now(timezone.utc),
    )
    report_repository.create(
        agreement_id=agreement_b.id,
        subject_type="anonymous_session",
        subject_id="session-b",
        source_type="text",
        source_value="B",
        raw_input_excerpt="B excerpt",
        status="completed",
        summary="summary B",
        trust_score=60,
        model_name="test-model",
        flagged_clauses=[],
        completed_at=datetime.now(timezone.utc),
    )

    owner_a_reports = report_repository.list_for_subject(
        subject_type="anonymous_session",
        subject_id="session-a",
    )
    owner_b_reports = report_repository.list_for_subject(
        subject_type="anonymous_session",
        subject_id="session-b",
    )

    assert len(owner_a_reports) == 1
    assert len(owner_b_reports) == 1
    assert owner_a_reports[0].summary == "summary A"
    assert owner_b_reports[0].summary == "summary B"


def test_report_repository_lists_newest_first() -> None:
    storage = InMemoryStorage()
    agreement_repository = InMemoryAgreementRepository(storage)
    report_repository = InMemoryReportRepository(storage)
    agreement = agreement_repository.create(
        subject_type="anonymous_session",
        subject_id="session-a",
        title="A",
        source_url=None,
        agreed_at=None,
        terms_text="This terms text is long enough to pass validation.",
    )
    report_one = report_repository.create(
        agreement_id=agreement.id,
        subject_type="anonymous_session",
        subject_id="session-a",
        source_type="text",
        source_value="A",
        raw_input_excerpt="first excerpt",
        status="completed",
        summary="first summary",
        trust_score=80,
        model_name="test-model",
        flagged_clauses=[
            StoredFlaggedClause(
                clause_type="forced_arbitration",
                severity="high",
                excerpt="arbitration excerpt",
                explanation="risk",
            )
        ],
        completed_at=datetime.now(timezone.utc),
    )

    # Small sleep avoids same-timestamp ordering collisions on fast environments.
    time.sleep(0.001)

    report_two = report_repository.create(
        agreement_id=agreement.id,
        subject_type="anonymous_session",
        subject_id="session-a",
        source_type="text",
        source_value="A",
        raw_input_excerpt="second excerpt",
        status="completed",
        summary="second summary",
        trust_score=55,
        model_name="test-model",
        flagged_clauses=[],
        completed_at=datetime.now(timezone.utc),
    )

    reports = report_repository.list_for_subject(
        subject_type="anonymous_session",
        subject_id="session-a",
    )
    assert [report.id for report in reports] == [report_two.id, report_one.id]
