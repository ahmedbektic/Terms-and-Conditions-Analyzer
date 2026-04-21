"""Postgres-backed repositories for terms analysis persistence.

This module keeps database concerns isolated from route handlers and services.
It intentionally mirrors existing repository contracts so memory and Postgres
implementations can be swapped via configuration.
"""

from contextlib import contextmanager
from datetime import datetime
import json
from urllib.parse import urlsplit
from uuid import UUID, uuid4

import psycopg
from psycopg import errors as psycopg_errors
from psycopg.rows import dict_row

from ..repositories.analysis_status import (
    AnalysisLifecycleStatus,
    normalize_analysis_lifecycle_status,
)
from ..repositories.errors import ActiveTrackedPolicyConflictError
from ..repositories.models import (
    PolicyChangeEventCreateInput,
    PolicySnapshotAppendResult,
    PolicySnapshotCreateInput,
    StoredPolicyChangeEvent,
    StoredPolicySnapshot,
    StoredAgreement,
    StoredFlaggedClause,
    StoredReport,
    StoredTrackedPolicy,
)
from ..repositories.policy_capture_status import (
    PolicyCaptureStatus,
    PolicySnapshotStatus,
    normalize_policy_capture_status,
    normalize_policy_snapshot_status,
)
from ..repositories.policy_change_status import (
    PolicyChangeStatus,
    normalize_policy_change_status,
)
from ..repositories.policy_snapshot_hash import build_policy_snapshot_content_hash
from ..repositories.policy_tracking_status import (
    PolicyTrackingStatus,
    normalize_policy_tracking_status,
)
from ..repositories.report_capture_kind import (
    ReportContentCaptureKind,
    normalize_report_content_capture_kind,
)

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
  canonical_source_url TEXT NULL,
  content_capture_kind TEXT NOT NULL DEFAULT 'legacy_unknown',
  tracked_policy_id UUID NULL,
  tracked_policy_snapshot_id UUID NULL,
  tracked_policy_version_number INTEGER NULL,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
  completed_at TIMESTAMPTZ NULL
);

ALTER TABLE reports
  ADD COLUMN IF NOT EXISTS canonical_source_url TEXT NULL;

ALTER TABLE reports
  ADD COLUMN IF NOT EXISTS content_capture_kind TEXT NOT NULL DEFAULT 'legacy_unknown';

ALTER TABLE reports
  ADD COLUMN IF NOT EXISTS tracked_policy_id UUID NULL;

ALTER TABLE reports
  ADD COLUMN IF NOT EXISTS tracked_policy_snapshot_id UUID NULL;

ALTER TABLE reports
  ADD COLUMN IF NOT EXISTS tracked_policy_version_number INTEGER NULL;

CREATE INDEX IF NOT EXISTS idx_reports_owner_created
  ON reports (subject_type, subject_id, created_at DESC);

CREATE INDEX IF NOT EXISTS idx_reports_owner_canonical_capture_created
  ON reports (
    subject_type,
    subject_id,
    canonical_source_url,
    content_capture_kind,
    created_at DESC
  );

CREATE INDEX IF NOT EXISTS idx_reports_owner_tracked_policy_version_created
  ON reports (
    subject_type,
    subject_id,
    tracked_policy_id,
    tracked_policy_version_number,
    created_at DESC
  );

CREATE TABLE IF NOT EXISTS tracked_policies (
  id UUID PRIMARY KEY,
  subject_type TEXT NOT NULL,
  subject_id TEXT NOT NULL,
  canonical_url TEXT NOT NULL,
  display_name TEXT NOT NULL,
  source_type TEXT NOT NULL,
  tracking_status TEXT NOT NULL CHECK (
    tracking_status IN ('pending_first_snapshot', 'active', 'invalid_source')
  ),
  latest_capture_status TEXT NOT NULL DEFAULT 'never_captured' CHECK (
    latest_capture_status IN ('never_captured', 'captured', 'capture_failed')
  ),
  latest_capture_message TEXT NULL,
  latest_change_status TEXT NOT NULL DEFAULT 'not_evaluated' CHECK (
    latest_change_status IN ('not_evaluated', 'unchanged', 'updated', 'comparison_incomplete')
  ),
  latest_change_detected_at TIMESTAMPTZ NULL,
  last_checked_at TIMESTAMPTZ NULL,
  active BOOLEAN NOT NULL DEFAULT TRUE,
  created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
);

ALTER TABLE tracked_policies
  ADD COLUMN IF NOT EXISTS latest_capture_status TEXT NOT NULL DEFAULT 'never_captured';

ALTER TABLE tracked_policies
  ADD COLUMN IF NOT EXISTS latest_capture_message TEXT NULL;

ALTER TABLE tracked_policies
  ADD COLUMN IF NOT EXISTS latest_change_status TEXT NOT NULL DEFAULT 'not_evaluated';

ALTER TABLE tracked_policies
  ADD COLUMN IF NOT EXISTS latest_change_detected_at TIMESTAMPTZ NULL;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints
    WHERE constraint_name = 'reports_tracked_policy_id_fkey'
      AND table_name = 'reports'
  ) THEN
    ALTER TABLE reports
      ADD CONSTRAINT reports_tracked_policy_id_fkey
      FOREIGN KEY (tracked_policy_id) REFERENCES tracked_policies(id) ON DELETE SET NULL;
  END IF;
END $$;

CREATE INDEX IF NOT EXISTS idx_tracked_policies_owner_created
  ON tracked_policies (subject_type, subject_id, created_at DESC);

CREATE UNIQUE INDEX IF NOT EXISTS idx_tracked_policies_owner_url_active
  ON tracked_policies (subject_type, subject_id, canonical_url)
  WHERE active = TRUE;

CREATE TABLE IF NOT EXISTS policy_change_events (
  id UUID PRIMARY KEY,
  tracked_policy_id UUID NOT NULL REFERENCES tracked_policies(id) ON DELETE CASCADE,
  previous_snapshot_id UUID NULL,
  new_snapshot_id UUID NULL,
  detected_at TIMESTAMPTZ NOT NULL,
  change_status TEXT NOT NULL CHECK (
    change_status IN ('not_evaluated', 'unchanged', 'updated', 'comparison_incomplete')
  ),
  detection_method TEXT NOT NULL,
  content_changed BOOLEAN NULL,
  previous_section_count INTEGER NULL,
  new_section_count INTEGER NULL,
  section_delta INTEGER NULL
);

CREATE INDEX IF NOT EXISTS idx_policy_change_events_policy_detected
  ON policy_change_events (tracked_policy_id, detected_at DESC);

CREATE TABLE IF NOT EXISTS policy_snapshots (
  id UUID PRIMARY KEY,
  tracked_policy_id UUID NOT NULL REFERENCES tracked_policies(id) ON DELETE CASCADE,
  terms_text TEXT NOT NULL,
  raw_text_body TEXT NULL,
  normalized_text_body TEXT NULL,
  normalization_version INTEGER NULL,
  content_hash TEXT NULL,
  capture_status TEXT NOT NULL DEFAULT 'captured',
  source_url TEXT NULL,
  final_url TEXT NULL,
  http_status INTEGER NULL,
  redirect_count INTEGER NULL,
  fetch_duration_ms INTEGER NULL,
  extractor_name TEXT NULL,
  extraction_strategy TEXT NULL,
  capture_error_message TEXT NULL,
  captured_at TIMESTAMPTZ NOT NULL
);

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS raw_text_body TEXT NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS normalized_text_body TEXT NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS normalization_version INTEGER NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS content_hash TEXT NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS capture_status TEXT NOT NULL DEFAULT 'captured';

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS source_url TEXT NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS final_url TEXT NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS http_status INTEGER NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS redirect_count INTEGER NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS fetch_duration_ms INTEGER NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS extractor_name TEXT NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS extraction_strategy TEXT NULL;

ALTER TABLE policy_snapshots
  ADD COLUMN IF NOT EXISTS capture_error_message TEXT NULL;

CREATE INDEX IF NOT EXISTS idx_policy_snapshots_policy_captured
  ON policy_snapshots (tracked_policy_id, captured_at DESC);

CREATE INDEX IF NOT EXISTS idx_policy_snapshots_policy_hash
  ON policy_snapshots (tracked_policy_id, content_hash, captured_at DESC);

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints
    WHERE constraint_name = 'policy_change_events_previous_snapshot_id_fkey'
      AND table_name = 'policy_change_events'
  ) THEN
    ALTER TABLE policy_change_events
      ADD CONSTRAINT policy_change_events_previous_snapshot_id_fkey
      FOREIGN KEY (previous_snapshot_id) REFERENCES policy_snapshots(id) ON DELETE SET NULL;
  END IF;
END $$;

DO $$
BEGIN
  IF NOT EXISTS (
    SELECT 1
    FROM information_schema.table_constraints
    WHERE constraint_name = 'policy_change_events_new_snapshot_id_fkey'
      AND table_name = 'policy_change_events'
  ) THEN
    ALTER TABLE policy_change_events
      ADD CONSTRAINT policy_change_events_new_snapshot_id_fkey
      FOREIGN KEY (new_snapshot_id) REFERENCES policy_snapshots(id) ON DELETE SET NULL;
  END IF;
END $$;
"""


def _database_hostname(database_url: str) -> str:
    """Extract the hostname from a Postgres connection string."""

    return urlsplit(database_url).hostname or ""


def _is_direct_supabase_database_host(hostname: str) -> bool:
    """Return True when the host matches Supabase's direct IPv6 endpoint pattern."""

    normalized = hostname.strip().lower()
    return normalized.startswith("db.") and normalized.endswith(".supabase.co")


def _build_database_connection_error_message(
    database_url: str,
    error: Exception,
) -> str:
    """Build an actionable startup error without leaking credentials."""

    hostname = _database_hostname(database_url) or "<unknown>"
    message = f"Postgres connection failed for host '{hostname}': {error}"
    if _is_direct_supabase_database_host(hostname):
        message = (
            f"{message} The configured hostname looks like Supabase's direct database endpoint, "
            "which uses IPv6. For Docker, Render, and other IPv4-only environments, update "
            "SUPABASE_DATABASE_URL or DATABASE_URL to the exact 'Session pooler' connection "
            "string from the Supabase dashboard."
        )
    return message


class PostgresStorage:
    """Connection and schema utility for Postgres-backed repositories."""

    def __init__(self, *, database_url: str, auto_create_schema: bool = True) -> None:
        self._database_url = database_url
        if auto_create_schema:
            self.ensure_schema()

    @contextmanager
    def connection(self):
        """Yield a short-lived database connection."""

        try:
            with psycopg.connect(self._database_url, row_factory=dict_row) as conn:
                yield conn
        except psycopg.OperationalError as error:
            raise psycopg.OperationalError(
                _build_database_connection_error_message(self._database_url, error)
            ) from error

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
                cursor.execute(
                    "TRUNCATE TABLE policy_change_events, policy_snapshots, reports, agreements, tracked_policies;"
                )
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
        canonical_source_url: str | None = None,
        content_capture_kind: ReportContentCaptureKind | str = (
            ReportContentCaptureKind.LEGACY_UNKNOWN
        ),
        tracked_policy_id: UUID | None = None,
        tracked_policy_snapshot_id: UUID | None = None,
        tracked_policy_version_number: int | None = None,
    ) -> StoredReport:
        report_id = uuid4()
        normalized_status = normalize_analysis_lifecycle_status(status)
        normalized_capture_kind = normalize_report_content_capture_kind(content_capture_kind)
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
                      raw_input_excerpt, status, summary, trust_score, model_name, flagged_clauses,
                      canonical_source_url, content_capture_kind, tracked_policy_id,
                      tracked_policy_snapshot_id, tracked_policy_version_number, completed_at
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s::jsonb, %s, %s, %s, %s, %s, %s)
                    RETURNING
                      id, agreement_id, subject_type, subject_id, source_type, source_value,
                      raw_input_excerpt, status, summary, trust_score, model_name,
                      flagged_clauses, canonical_source_url, content_capture_kind,
                      tracked_policy_id, tracked_policy_snapshot_id, tracked_policy_version_number,
                      created_at, completed_at;
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
                        canonical_source_url,
                        normalized_capture_kind.value,
                        tracked_policy_id,
                        tracked_policy_snapshot_id,
                        tracked_policy_version_number,
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
                      flagged_clauses, canonical_source_url, content_capture_kind,
                      tracked_policy_id, tracked_policy_snapshot_id, tracked_policy_version_number,
                      created_at, completed_at
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
                      flagged_clauses, canonical_source_url, content_capture_kind,
                      tracked_policy_id, tracked_policy_snapshot_id, tracked_policy_version_number,
                      created_at, completed_at
                    FROM reports
                    WHERE id = %s AND subject_type = %s AND subject_id = %s;
                    """,
                    (report_id, subject_type, subject_id),
                )
                row = cursor.fetchone()
        return _report_from_row(row) if row else None

    def get_latest_eligible_baseline_report_for_subject(
        self,
        *,
        canonical_source_url: str,
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
                      flagged_clauses, canonical_source_url, content_capture_kind,
                      tracked_policy_id, tracked_policy_snapshot_id, tracked_policy_version_number,
                      created_at, completed_at
                    FROM reports
                    WHERE subject_type = %s
                      AND subject_id = %s
                      AND canonical_source_url = %s
                      AND content_capture_kind = %s
                    ORDER BY created_at DESC
                    LIMIT 1;
                    """,
                    (
                        subject_type,
                        subject_id,
                        canonical_source_url,
                        ReportContentCaptureKind.FETCHED_URL.value,
                    ),
                )
                row = cursor.fetchone()
        return _report_from_row(row) if row else None


_TRACKED_POLICY_SELECT_FIELDS = """
      tp.id, tp.subject_type, tp.subject_id, tp.canonical_url, tp.display_name,
      tp.source_type, tp.tracking_status, tp.latest_capture_status, tp.latest_capture_message,
      tp.latest_change_status, tp.latest_change_detected_at,
      tp.last_checked_at, tp.active, tp.created_at, sc.last_successful_capture_at,
      COALESCE(sc.cnt, 0) AS snapshot_version_count
"""

_TRACKED_POLICY_SNAPSHOT_AGGREGATE_JOIN = """
                    LEFT JOIN (
                      SELECT
                        tracked_policy_id,
                        COUNT(*)::int AS cnt,
                        MAX(
                          CASE
                            WHEN COALESCE(capture_status, 'captured') = 'captured'
                            THEN captured_at
                            ELSE NULL
                          END
                        ) AS last_successful_capture_at
                      FROM policy_snapshots
                      GROUP BY tracked_policy_id
                    ) sc ON sc.tracked_policy_id = tp.id
"""


class PostgresTrackedPolicyRepository:
    """Postgres implementation of tracked-policy persistence."""

    def __init__(self, storage: PostgresStorage) -> None:
        self._storage = storage

    def create(
        self,
        *,
        subject_type: str,
        subject_id: str,
        canonical_url: str,
        display_name: str,
        source_type: str,
        tracking_status: PolicyTrackingStatus,
        last_checked_at: datetime | None,
        active: bool = True,
    ) -> StoredTrackedPolicy:
        tracked_policy_id = uuid4()
        normalized_status = normalize_policy_tracking_status(tracking_status)

        try:
            with self._storage.connection() as conn:
                with conn.cursor() as cursor:
                    cursor.execute(
                        """
                        INSERT INTO tracked_policies (
                          id, subject_type, subject_id, canonical_url, display_name,
                          source_type, tracking_status, latest_capture_status,
                          latest_capture_message, latest_change_status,
                          latest_change_detected_at, last_checked_at, active
                        ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                        RETURNING
                          id, subject_type, subject_id, canonical_url, display_name,
                          source_type, tracking_status, latest_capture_status,
                          latest_capture_message, latest_change_status,
                          latest_change_detected_at, last_checked_at, active, created_at;
                        """,
                        (
                            tracked_policy_id,
                            subject_type,
                            subject_id,
                            canonical_url,
                            display_name,
                            source_type,
                            normalized_status.value,
                            PolicyCaptureStatus.NEVER_CAPTURED.value,
                            None,
                            PolicyChangeStatus.NOT_EVALUATED.value,
                            None,
                            last_checked_at,
                            active,
                        ),
                    )
                    row = cursor.fetchone()
                conn.commit()
        except psycopg_errors.UniqueViolation as error:
            raise ActiveTrackedPolicyConflictError(
                "An active tracked policy already exists for this canonical URL."
            ) from error

        return _tracked_policy_from_row(row)

    def list_active_for_subject(
        self, *, subject_type: str, subject_id: str
    ) -> list[StoredTrackedPolicy]:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {_TRACKED_POLICY_SELECT_FIELDS.strip()}
                    FROM tracked_policies tp
                    {_TRACKED_POLICY_SNAPSHOT_AGGREGATE_JOIN.strip()}
                    WHERE tp.subject_type = %s AND tp.subject_id = %s AND tp.active = TRUE
                    ORDER BY tp.created_at DESC;
                    """,
                    (subject_type, subject_id),
                )
                rows = cursor.fetchall()
        return [_tracked_policy_from_row(row) for row in rows]

    def get_active_for_subject(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {_TRACKED_POLICY_SELECT_FIELDS.strip()}
                    FROM tracked_policies tp
                    {_TRACKED_POLICY_SNAPSHOT_AGGREGATE_JOIN.strip()}
                    WHERE tp.id = %s AND tp.subject_type = %s AND tp.subject_id = %s AND tp.active = TRUE;
                    """,
                    (tracked_policy_id, subject_type, subject_id),
                )
                row = cursor.fetchone()
        return _tracked_policy_from_row(row) if row else None

    def get_active_by_canonical_url_for_subject(
        self,
        *,
        canonical_url: str,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {_TRACKED_POLICY_SELECT_FIELDS.strip()}
                    FROM tracked_policies tp
                    {_TRACKED_POLICY_SNAPSHOT_AGGREGATE_JOIN.strip()}
                    WHERE tp.canonical_url = %s AND tp.subject_type = %s AND tp.subject_id = %s
                      AND tp.active = TRUE;
                    """,
                    (canonical_url, subject_type, subject_id),
                )
                row = cursor.fetchone()
        return _tracked_policy_from_row(row) if row else None

    def update_tracked_policy_check_state(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
        last_checked_at: datetime,
        tracking_status: PolicyTrackingStatus,
        latest_capture_status: PolicyCaptureStatus,
        latest_capture_message: str | None,
        latest_change_status: PolicyChangeStatus,
        latest_change_detected_at: datetime | None,
    ) -> StoredTrackedPolicy | None:
        normalized_status = normalize_policy_tracking_status(tracking_status)
        normalized_capture_status = normalize_policy_capture_status(latest_capture_status)
        normalized_change_status = normalize_policy_change_status(latest_change_status)
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tracked_policies
                    SET last_checked_at = %s,
                        tracking_status = %s,
                        latest_capture_status = %s,
                        latest_capture_message = %s,
                        latest_change_status = %s,
                        latest_change_detected_at = %s
                    WHERE id = %s AND subject_type = %s AND subject_id = %s AND active = TRUE
                    RETURNING id;
                    """,
                    (
                        last_checked_at,
                        normalized_status.value,
                        normalized_capture_status.value,
                        latest_capture_message,
                        normalized_change_status.value,
                        latest_change_detected_at,
                        tracked_policy_id,
                        subject_type,
                        subject_id,
                    ),
                )
                updated = cursor.fetchone()
            if updated is None:
                conn.commit()
                return None
            with conn.cursor() as cursor:
                cursor.execute(
                    f"""
                    SELECT {_TRACKED_POLICY_SELECT_FIELDS.strip()}
                    FROM tracked_policies tp
                    {_TRACKED_POLICY_SNAPSHOT_AGGREGATE_JOIN.strip()}
                    WHERE tp.id = %s AND tp.subject_type = %s AND tp.subject_id = %s AND tp.active = TRUE;
                    """,
                    (tracked_policy_id, subject_type, subject_id),
                )
                row = cursor.fetchone()
            conn.commit()
        return _tracked_policy_from_row(row) if row else None

    def deactivate_for_subject(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    UPDATE tracked_policies
                    SET active = FALSE
                    WHERE id = %s AND subject_type = %s AND subject_id = %s AND active = TRUE
                    RETURNING
                      id, subject_type, subject_id, canonical_url, display_name,
                      source_type, tracking_status, latest_capture_status,
                      latest_capture_message, latest_change_status,
                      latest_change_detected_at, last_checked_at, active, created_at;
                    """,
                    (tracked_policy_id, subject_type, subject_id),
                )
                row = cursor.fetchone()
                if row is not None:
                    cursor.execute(
                        """
                        SELECT COUNT(*)::int AS cnt
                             , MAX(
                                 CASE
                                   WHEN COALESCE(capture_status, 'captured') = 'captured'
                                   THEN captured_at
                                   ELSE NULL
                                 END
                               ) AS last_successful_capture_at
                        FROM policy_snapshots
                        WHERE tracked_policy_id = %s;
                        """,
                        (tracked_policy_id,),
                    )
                    count_row = cursor.fetchone()
                    row = dict(row)
                    row["snapshot_version_count"] = count_row["cnt"] if count_row else 0
                    row["last_successful_capture_at"] = (
                        count_row["last_successful_capture_at"] if count_row else None
                    )
            conn.commit()
        return _tracked_policy_from_row(row) if row else None


class PostgresPolicySnapshotRepository:
    """Postgres implementation of tracked-policy snapshot persistence."""

    def __init__(self, storage: PostgresStorage) -> None:
        self._storage = storage

    def append_for_tracked_policy_if_changed(
        self,
        *,
        tracked_policy_id: UUID,
        snapshot: PolicySnapshotCreateInput,
    ) -> PolicySnapshotAppendResult:
        normalized_status = normalize_policy_snapshot_status(snapshot.capture_status)
        content_hash = build_policy_snapshot_content_hash(snapshot.normalized_text_body)

        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                # Serialize snapshot appends per tracked policy so repeated manual
                # checks or future background retries do not create duplicate rows.
                cursor.execute(
                    """
                    SELECT id
                    FROM tracked_policies
                    WHERE id = %s
                    FOR UPDATE;
                    """,
                    (tracked_policy_id,),
                )
                cursor.execute(
                    """
                    SELECT
                      id,
                      tracked_policy_id,
                      COALESCE(raw_text_body, terms_text) AS raw_text_body,
                      COALESCE(normalized_text_body, terms_text) AS normalized_text_body,
                      normalization_version,
                      content_hash,
                      captured_at,
                      COALESCE(capture_status, 'captured') AS capture_status,
                      source_url,
                      final_url,
                      http_status,
                      redirect_count,
                      fetch_duration_ms,
                      extractor_name,
                      extraction_strategy,
                      capture_error_message
                    FROM policy_snapshots
                    WHERE tracked_policy_id = %s
                    ORDER BY captured_at DESC
                    LIMIT 1;
                    """,
                    (tracked_policy_id,),
                )
                latest_row = cursor.fetchone()
                if latest_row is not None:
                    latest_snapshot = _policy_snapshot_from_row(latest_row)
                    if (
                        latest_snapshot.capture_status == PolicySnapshotStatus.CAPTURED
                        and latest_snapshot.content_hash == content_hash
                        and latest_snapshot.normalized_text_body == snapshot.normalized_text_body
                    ):
                        conn.commit()
                        return PolicySnapshotAppendResult(
                            snapshot=latest_snapshot,
                            created=False,
                        )

                snapshot_id = uuid4()
                cursor.execute(
                    """
                    INSERT INTO policy_snapshots (
                      id,
                      tracked_policy_id,
                      terms_text,
                      raw_text_body,
                      normalized_text_body,
                      normalization_version,
                      content_hash,
                      capture_status,
                      source_url,
                      final_url,
                      http_status,
                      redirect_count,
                      fetch_duration_ms,
                      extractor_name,
                      extraction_strategy,
                      capture_error_message,
                      captured_at
                    ) VALUES (
                      %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s
                    )
                    RETURNING
                      id,
                      tracked_policy_id,
                      COALESCE(raw_text_body, terms_text) AS raw_text_body,
                      COALESCE(normalized_text_body, terms_text) AS normalized_text_body,
                      normalization_version,
                      content_hash,
                      captured_at,
                      COALESCE(capture_status, 'captured') AS capture_status,
                      source_url,
                      final_url,
                      http_status,
                      redirect_count,
                      fetch_duration_ms,
                      extractor_name,
                      extraction_strategy,
                      capture_error_message;
                    """,
                    (
                        snapshot_id,
                        tracked_policy_id,
                        snapshot.raw_text_body,
                        snapshot.raw_text_body,
                        snapshot.normalized_text_body,
                        snapshot.normalization_version,
                        content_hash,
                        normalized_status.value,
                        snapshot.source_url,
                        snapshot.final_url,
                        snapshot.http_status,
                        snapshot.redirect_count,
                        snapshot.fetch_duration_ms,
                        snapshot.extractor_name,
                        snapshot.extraction_strategy,
                        snapshot.capture_error_message,
                        snapshot.captured_at,
                    ),
                )
                stored_row = cursor.fetchone()
            conn.commit()

        return PolicySnapshotAppendResult(
            snapshot=_policy_snapshot_from_row(stored_row),
            created=True,
        )

    def get_latest_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
    ) -> StoredPolicySnapshot | None:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      id,
                      tracked_policy_id,
                      COALESCE(raw_text_body, terms_text) AS raw_text_body,
                      COALESCE(normalized_text_body, terms_text) AS normalized_text_body,
                      normalization_version,
                      content_hash,
                      captured_at,
                      COALESCE(capture_status, 'captured') AS capture_status,
                      source_url,
                      final_url,
                      http_status,
                      redirect_count,
                      fetch_duration_ms,
                      extractor_name,
                      extraction_strategy,
                      capture_error_message
                    FROM policy_snapshots
                    WHERE tracked_policy_id = %s
                    ORDER BY captured_at DESC
                    LIMIT 1;
                    """,
                    (tracked_policy_id,),
                )
                row = cursor.fetchone()
        return _policy_snapshot_from_row(row) if row else None

    def list_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
    ) -> list[StoredPolicySnapshot]:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      id,
                      tracked_policy_id,
                      COALESCE(raw_text_body, terms_text) AS raw_text_body,
                      COALESCE(normalized_text_body, terms_text) AS normalized_text_body,
                      normalization_version,
                      content_hash,
                      captured_at,
                      COALESCE(capture_status, 'captured') AS capture_status,
                      source_url,
                      final_url,
                      http_status,
                      redirect_count,
                      fetch_duration_ms,
                      extractor_name,
                      extraction_strategy,
                      capture_error_message
                    FROM policy_snapshots
                    WHERE tracked_policy_id = %s
                    ORDER BY captured_at DESC;
                    """,
                    (tracked_policy_id,),
                )
                rows = cursor.fetchall()
        return [_policy_snapshot_from_row(row) for row in rows]

    def delete_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
        snapshot_id: UUID,
    ) -> bool:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    DELETE FROM policy_snapshots
                    WHERE id = %s AND tracked_policy_id = %s;
                    """,
                    (snapshot_id, tracked_policy_id),
                )
                deleted = cursor.rowcount > 0
            conn.commit()
        return deleted


class PostgresPolicyChangeEventRepository:
    """Postgres implementation of tracked-policy change-event persistence."""

    def __init__(self, storage: PostgresStorage) -> None:
        self._storage = storage

    def create(self, *, event: PolicyChangeEventCreateInput) -> StoredPolicyChangeEvent:
        event_id = uuid4()
        normalized_status = normalize_policy_change_status(event.change_status)
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    INSERT INTO policy_change_events (
                      id,
                      tracked_policy_id,
                      previous_snapshot_id,
                      new_snapshot_id,
                      detected_at,
                      change_status,
                      detection_method,
                      content_changed,
                      previous_section_count,
                      new_section_count,
                      section_delta
                    ) VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                    RETURNING
                      id,
                      tracked_policy_id,
                      previous_snapshot_id,
                      new_snapshot_id,
                      detected_at,
                      change_status,
                      detection_method,
                      content_changed,
                      previous_section_count,
                      new_section_count,
                      section_delta;
                    """,
                    (
                        event_id,
                        event.tracked_policy_id,
                        event.previous_snapshot_id,
                        event.new_snapshot_id,
                        event.detected_at,
                        normalized_status.value,
                        event.detection_method,
                        event.content_changed,
                        event.previous_section_count,
                        event.new_section_count,
                        event.section_delta,
                    ),
                )
                row = cursor.fetchone()
            conn.commit()
        return _policy_change_event_from_row(row)

    def get_latest_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
    ) -> StoredPolicyChangeEvent | None:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      id,
                      tracked_policy_id,
                      previous_snapshot_id,
                      new_snapshot_id,
                      detected_at,
                      change_status,
                      detection_method,
                      content_changed,
                      previous_section_count,
                      new_section_count,
                      section_delta
                    FROM policy_change_events
                    WHERE tracked_policy_id = %s
                    ORDER BY detected_at DESC
                    LIMIT 1;
                    """,
                    (tracked_policy_id,),
                )
                row = cursor.fetchone()
        return _policy_change_event_from_row(row) if row else None

    def list_for_tracked_policy(
        self,
        *,
        tracked_policy_id: UUID,
    ) -> list[StoredPolicyChangeEvent]:
        with self._storage.connection() as conn:
            with conn.cursor() as cursor:
                cursor.execute(
                    """
                    SELECT
                      id,
                      tracked_policy_id,
                      previous_snapshot_id,
                      new_snapshot_id,
                      detected_at,
                      change_status,
                      detection_method,
                      content_changed,
                      previous_section_count,
                      new_section_count,
                      section_delta
                    FROM policy_change_events
                    WHERE tracked_policy_id = %s
                    ORDER BY detected_at DESC;
                    """,
                    (tracked_policy_id,),
                )
                rows = cursor.fetchall()
        return [_policy_change_event_from_row(row) for row in rows]


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
        canonical_source_url=row.get("canonical_source_url"),
        content_capture_kind=normalize_report_content_capture_kind(
            row.get("content_capture_kind", ReportContentCaptureKind.LEGACY_UNKNOWN.value)
        ),
        tracked_policy_id=row.get("tracked_policy_id"),
        tracked_policy_snapshot_id=row.get("tracked_policy_snapshot_id"),
        tracked_policy_version_number=row.get("tracked_policy_version_number"),
    )


def _tracked_policy_from_row(row: dict | None) -> StoredTrackedPolicy:
    """Map a DB row dict to `StoredTrackedPolicy`."""

    if row is None:
        raise ValueError("Tracked policy row cannot be None.")
    return StoredTrackedPolicy(
        id=row["id"],
        subject_type=row["subject_type"],
        subject_id=row["subject_id"],
        canonical_url=row["canonical_url"],
        display_name=row["display_name"],
        source_type=row["source_type"],
        tracking_status=normalize_policy_tracking_status(row["tracking_status"]),
        last_checked_at=row["last_checked_at"],
        last_successful_capture_at=row.get("last_successful_capture_at"),
        latest_capture_status=normalize_policy_capture_status(
            row.get("latest_capture_status", PolicyCaptureStatus.NEVER_CAPTURED.value)
        ),
        latest_capture_message=row.get("latest_capture_message"),
        latest_change_status=normalize_policy_change_status(
            row.get("latest_change_status", PolicyChangeStatus.NOT_EVALUATED.value)
        ),
        latest_change_detected_at=row.get("latest_change_detected_at"),
        active=row["active"],
        created_at=row["created_at"],
        snapshot_version_count=int(row.get("snapshot_version_count", 0)),
    )


def _policy_snapshot_from_row(row: dict | None) -> StoredPolicySnapshot:
    """Map a DB row dict to `StoredPolicySnapshot`."""

    if row is None:
        raise ValueError("Policy snapshot row cannot be None.")

    normalized_text_body = row.get("normalized_text_body") or row.get("terms_text") or ""
    return StoredPolicySnapshot(
        id=row["id"],
        tracked_policy_id=row["tracked_policy_id"],
        raw_text_body=row.get("raw_text_body") or row.get("terms_text") or normalized_text_body,
        normalized_text_body=normalized_text_body,
        content_hash=row.get("content_hash")
        or build_policy_snapshot_content_hash(normalized_text_body),
        captured_at=row["captured_at"],
        capture_status=normalize_policy_snapshot_status(
            row.get("capture_status", PolicySnapshotStatus.CAPTURED.value)
        ),
        source_url=row.get("source_url"),
        final_url=row.get("final_url"),
        http_status=row.get("http_status"),
        redirect_count=row.get("redirect_count"),
        fetch_duration_ms=row.get("fetch_duration_ms"),
        extractor_name=row.get("extractor_name"),
        extraction_strategy=row.get("extraction_strategy"),
        capture_error_message=row.get("capture_error_message"),
        normalization_version=row.get("normalization_version"),
    )


def _policy_change_event_from_row(row: dict | None) -> StoredPolicyChangeEvent:
    """Map a DB row dict to `StoredPolicyChangeEvent`."""

    if row is None:
        raise ValueError("Policy change event row cannot be None.")

    return StoredPolicyChangeEvent(
        id=row["id"],
        tracked_policy_id=row["tracked_policy_id"],
        previous_snapshot_id=row.get("previous_snapshot_id"),
        new_snapshot_id=row.get("new_snapshot_id"),
        detected_at=row["detected_at"],
        change_status=normalize_policy_change_status(row["change_status"]),
        detection_method=row["detection_method"],
        content_changed=row.get("content_changed"),
        previous_section_count=row.get("previous_section_count"),
        new_section_count=row.get("new_section_count"),
        section_delta=row.get("section_delta"),
    )
