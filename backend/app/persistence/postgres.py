"""Postgres-backed repositories for terms analysis persistence.

This module keeps database concerns isolated from route handlers and services.
It intentionally mirrors existing repository contracts so memory and Postgres
implementations can be swapped via configuration.
"""

from contextlib import contextmanager
from datetime import datetime
import json
from uuid import UUID, uuid4

import psycopg
from psycopg.rows import dict_row

from ..repositories.analysis_status import (
    AnalysisLifecycleStatus,
    normalize_analysis_lifecycle_status,
)
from ..repositories.models import StoredAgreement, StoredFlaggedClause, StoredReport

SCHEMA_SQL = """
CREATE TABLE IF NOT EXISTS agreements (
  id UUID PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  title TEXT NULL,
  source_url TEXT NULL,
  agreed_at TIMESTAMPTZ NULL,
  terms_text TEXT NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

-- subject_* columns are the ownership seam used by service/repository layers.
-- we use Supabase JWT subject values (subject_type='supabase_user').
CREATE INDEX IF NOT EXISTS idx_agreements_owner_created
  ON agreements (subject_type, subject_id, created_at DESC);

CREATE TABLE IF NOT EXISTS reports (
  id UUID PRIMARY KEY,
  agreement_id UUID NOT NULL REFERENCES agreements(id) ON DELETE CASCADE,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  source_type TEXT NOT NULL,
  source_value TEXT NOT NULL,
  raw_input_excerpt TEXT NOT NULL,
  status TEXT NOT NULL CHECK (status IN ('pending', 'running', 'completed', 'failed')),
  summary TEXT NOT NULL,
  trust_score INTEGER NOT NULL CHECK (trust_score >= 0 AND trust_score <= 100),
  model_name TEXT NOT NULL,
  flagged_clauses JSONB NOT NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ NULL
);

CREATE INDEX IF NOT EXISTS idx_reports_owner_created
  ON reports (subject_type, subject_id, created_at DESC);
"""


class PostgresStorage:
    """Connection and schema utility for Postgres-backed repositories."""

    def __init__(self, *, database_url: str, auto_create_schema: bool = True) -> None:
        self._database_url = database_url
        if auto_create_schema:
            self.ensure_schema()

    @contextmanager
    def connection(self):
        """Yield a short-lived database connection."""

        with psycopg.connect(self._database_url, row_factory=dict_row) as conn:
            yield conn

    def ensure_schema(self) -> None:
        """Create required tables/indexes if they do not already exist."""

        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(SCHEMA_SQL)
            conn.commit()

    def clear(self) -> None:
        """Test helper to clear persistence tables for deterministic tests."""

        with self.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute("TRUNCATE TABLE reports, agreements;")
            conn.commit()


class PostgresAgreementRepository:
    """Postgres implementation of agreement persistence."""

    def __init__(self, storage: PostgresStorage) -> None:
        self._storage = storage

    def create(
        self,
        *,
        subject_type: str,
        subject_id: str,
        title: str | None,
        source_url: str | None,
        agreed_at: datetime | None,
        terms_text: str,
    ) -> StoredAgreement:
        agreement_id = uuid4()
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO agreements (
                      id, subject_type, subject_id, title, source_url, agreed_at, terms_text
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s)
                    RETURNING id, subject_type, subject_id, title, source_url, agreed_at, terms_text, created_at;
                    """,
                    (
                        agreement_id,
                        subject_type,
                        subject_id,
                        title,
                        source_url,
                        agreed_at,
                        terms_text,
                    ),
                )
                row = cursor.fetchone()
            conn.commit()
        return _agreement_from_row(row)

    def get_for_subject(
        self,
        *,
        agreement_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredAgreement | None:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT id, subject_type, subject_id, title, source_url, agreed_at, terms_text, created_at
                    FROM agreements
                    WHERE id = %s AND subject_type = %s AND subject_id = %s;
                    """,
                    (agreement_id, subject_type, subject_id),
                )
                row = cursor.fetchone()
        return _agreement_from_row(row) if row else None


class PostgresReportRepository:
    """Postgres implementation of report persistence."""

    def __init__(self, storage: PostgresStorage) -> None:
        self._storage = storage

    def create(
        self,
        *,
        agreement_id: UUID,
        subject_type: str,
        subject_id: str,
        source_type: str,
        source_value: str,
        raw_input_excerpt: str,
        status: AnalysisLifecycleStatus,
        summary: str,
        trust_score: int,
        model_name: str,
        flagged_clauses: list[StoredFlaggedClause],
        completed_at: datetime | None,
    ) -> StoredReport:
        report_id = uuid4()
        normalized_status = normalize_analysis_lifecycle_status(status)
        flagged_clause_payload = [
            {
                "clause_type": clause.clause_type,
                "severity": clause.severity,
                "excerpt": clause.excerpt,
                "explanation": clause.explanation,
            }
            for clause in flagged_clauses
        ]

        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO reports (
                      id, agreement_id, subject_type, subject_id, source_type, source_value,
                      raw_input_excerpt, status, summary, trust_score, model_name, flagged_clauses, completed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s)
                    RETURNING
                      id, agreement_id, subject_type, subject_id, source_type, source_value,
                      raw_input_excerpt, status, summary, trust_score, model_name,
                      flagged_clauses, created_at, completed_at;
                    """,
                    (
                        report_id,
                        agreement_id,
                        subject_type,
                        subject_id,
                        source_type,
                        source_value,
                        raw_input_excerpt,
                        normalized_status.value,
                        summary,
                        trust_score,
                        model_name,
                        json.dumps(flagged_clause_payload),
                        completed_at,
                    ),
                )
                row = cursor.fetchone()
            conn.commit()
        return _report_from_row(row)

    def list_for_subject(self, *, subject_type: str, subject_id: str) -> list[StoredReport]:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      id, agreement_id, subject_type, subject_id, source_type, source_value,
                      raw_input_excerpt, status, summary, trust_score, model_name,
                      flagged_clauses, created_at, completed_at
                    FROM reports
                    WHERE subject_type = %s AND subject_id = %s
                    ORDER BY created_at DESC;
                    """,
                    (subject_type, subject_id),
                )
                rows = cursor.fetchall()
        return [_report_from_row(row) for row in rows]

    def get_for_subject(
        self,
        *,
        report_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredReport | None:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      id, agreement_id, subject_type, subject_id, source_type, source_value,
                      raw_input_excerpt, status, summary, trust_score, model_name,
                      flagged_clauses, created_at, completed_at
                    FROM reports
                    WHERE id = %s AND subject_type = %s AND subject_id = %s;
                    """,
                    (report_id, subject_type, subject_id),
                )
                row = cursor.fetchone()
        return _report_from_row(row) if row else None


def _agreement_from_row(row: dict | None) -> StoredAgreement:
    """Map a DB row dict to `StoredAgreement`."""

    if row is None:
        raise ValueError("Agreement row cannot be None.")
    return StoredAgreement(
        id=row["id"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        title=row["title"],
        source_url=row["source_url"],
        agreed_at=row["agreed_at"],
        terms_text=row["terms_text"],
        created_at=row["created_at"],
    )


def _report_from_row(row: dict | None) -> StoredReport:
    """Map a DB row dict to `StoredReport`, including JSONB clause payload."""

    if row is None:
        raise ValueError("Report row cannot be None.")
    clause_items = row["flagged_clauses"] or []
    flagged_clauses = [
        StoredFlaggedClause(
            clause_type=item["clause_type"],
            severity=item["severity"],
            excerpt=item["excerpt"],
            explanation=item["explanation"],
        )
        for item in clause_items
    ]

    return StoredReport(
        id=row["id"],
        agreement_id=row["agreement_id"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        source_type=row["source_type"],
        source_value=row["source_value"],
        raw_input_excerpt=row["raw_input_excerpt"],
        status=normalize_analysis_lifecycle_status(row["status"]),
        summary=row["summary"],
        trust_score=row["trust_score"],
        model_name=row["model_name"],
        flagged_clauses=flagged_clauses,
        created_at=row["created_at"],
        completed_at=row["completed_at"],
    )
