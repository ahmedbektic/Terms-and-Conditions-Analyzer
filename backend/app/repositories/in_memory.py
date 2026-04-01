"""In-memory repository implementation used for local MVP wiring before DB integration.

This module mirrors the repository contracts so the service and route layers stay stable
when a Supabase/Postgres implementation is introduced.
"""

from datetime import datetime, timezone
from dataclasses import replace
from uuid import UUID, uuid4

from .analysis_status import AnalysisLifecycleStatus, normalize_analysis_lifecycle_status
from .models import StoredAgreement, StoredFlaggedClause, StoredReport, StoredTrackedPolicy
from .policy_tracking_status import PolicyTrackingStatus, normalize_policy_tracking_status


class InMemoryStorage:
    """Simple in-process storage container for local development and tests."""

    def __init__(self) -> None:
        self.agreements: dict[UUID, StoredAgreement] = {}
        self.reports: dict[UUID, StoredReport] = {}
        self.tracked_policies: dict[UUID, StoredTrackedPolicy] = {}
        self.policy_snapshots: dict[UUID, list[tuple[str, datetime]]] = {}

    def clear(self) -> None:
        self.agreements.clear()
        self.reports.clear()
        self.tracked_policies.clear()
        self.policy_snapshots.clear()


class InMemoryAgreementRepository:
    """In-memory agreement repository implementation."""

    def __init__(self, storage: InMemoryStorage) -> None:
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
        agreement = StoredAgreement(
            id=uuid4(),
            subject_type=subject_type,
            subject_id=subject_id,
            title=title,
            source_url=source_url,
            agreed_at=agreed_at,
            terms_text=terms_text,
            created_at=datetime.now(timezone.utc),
        )
        self._storage.agreements[agreement.id] = agreement
        return agreement

    def get_for_subject(
        self,
        *,
        agreement_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredAgreement | None:
        agreement = self._storage.agreements.get(agreement_id)
        if agreement is None:
            return None
        if agreement.subject_type != subject_type or agreement.subject_id != subject_id:
            return None
        return agreement


class InMemoryReportRepository:
    """In-memory report repository implementation."""

    def __init__(self, storage: InMemoryStorage) -> None:
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
        normalized_status = normalize_analysis_lifecycle_status(status)
        report = StoredReport(
            id=uuid4(),
            agreement_id=agreement_id,
            subject_type=subject_type,
            subject_id=subject_id,
            source_type=source_type,
            source_value=source_value,
            raw_input_excerpt=raw_input_excerpt,
            status=normalized_status,
            summary=summary,
            trust_score=trust_score,
            model_name=model_name,
            flagged_clauses=flagged_clauses,
            created_at=datetime.now(timezone.utc),
            completed_at=completed_at,
        )
        self._storage.reports[report.id] = report
        return report

    def list_for_subject(self, *, subject_type: str, subject_id: str) -> list[StoredReport]:
        reports = [
            report
            for report in self._storage.reports.values()
            if report.subject_type == subject_type and report.subject_id == subject_id
        ]
        return sorted(reports, key=lambda report: report.created_at, reverse=True)

    def get_for_subject(
        self,
        *,
        report_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredReport | None:
        report = self._storage.reports.get(report_id)
        if report is None:
            return None
        if report.subject_type != subject_type or report.subject_id != subject_id:
            return None
        return report


class InMemoryTrackedPolicyRepository:
    """In-memory tracked-policy repository implementation."""

    def __init__(self, storage: InMemoryStorage) -> None:
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
        tracked_policy = StoredTrackedPolicy(
            id=uuid4(),
            subject_type=subject_type,
            subject_id=subject_id,
            canonical_url=canonical_url,
            display_name=display_name,
            source_type=source_type,
            tracking_status=normalize_policy_tracking_status(tracking_status),
            last_checked_at=last_checked_at,
            active=active,
            created_at=datetime.now(timezone.utc),
            snapshot_version_count=0,
        )
        self._storage.tracked_policies[tracked_policy.id] = tracked_policy
        return tracked_policy

    def list_active_for_subject(
        self, *, subject_type: str, subject_id: str
    ) -> list[StoredTrackedPolicy]:
        tracked_policies = [
            tracked_policy
            for tracked_policy in self._storage.tracked_policies.values()
            if tracked_policy.subject_type == subject_type
            and tracked_policy.subject_id == subject_id
            and tracked_policy.active
        ]
        return sorted(
            (
                replace(
                    tracked_policy,
                    snapshot_version_count=len(
                        self._storage.policy_snapshots.get(tracked_policy.id, [])
                    ),
                )
                for tracked_policy in tracked_policies
            ),
            key=lambda tracked_policy: tracked_policy.created_at,
            reverse=True,
        )

    def get_active_for_subject(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None:
        tracked_policy = self._storage.tracked_policies.get(tracked_policy_id)
        if tracked_policy is None or not tracked_policy.active:
            return None
        if tracked_policy.subject_type != subject_type or tracked_policy.subject_id != subject_id:
            return None
        count = len(self._storage.policy_snapshots.get(tracked_policy_id, []))
        if tracked_policy.snapshot_version_count != count:
            return replace(tracked_policy, snapshot_version_count=count)
        return tracked_policy

    def get_active_by_canonical_url_for_subject(
        self,
        *,
        canonical_url: str,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None:
        for tracked_policy in self._storage.tracked_policies.values():
            if (
                tracked_policy.subject_type == subject_type
                and tracked_policy.subject_id == subject_id
                and tracked_policy.canonical_url == canonical_url
                and tracked_policy.active
            ):
                count = len(self._storage.policy_snapshots.get(tracked_policy.id, []))
                if tracked_policy.snapshot_version_count != count:
                    return replace(tracked_policy, snapshot_version_count=count)
                return tracked_policy
        return None

    def deactivate_for_subject(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
    ) -> StoredTrackedPolicy | None:
        tracked_policy = self.get_active_for_subject(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        if tracked_policy is None:
            return None
        count = len(self._storage.policy_snapshots.get(tracked_policy_id, []))
        deactivated_policy = replace(
            tracked_policy, active=False, snapshot_version_count=count
        )
        self._storage.tracked_policies[tracked_policy_id] = deactivated_policy
        return deactivated_policy

    def append_snapshot_if_text_changed(
        self,
        *,
        tracked_policy_id: UUID,
        terms_text: str,
        captured_at: datetime,
    ) -> bool:
        stored = self._storage.policy_snapshots.setdefault(tracked_policy_id, [])
        if stored and stored[-1][0] == terms_text:
            return False
        stored.append((terms_text, captured_at))
        return True

    def update_tracked_policy_check_state(
        self,
        *,
        tracked_policy_id: UUID,
        subject_type: str,
        subject_id: str,
        last_checked_at: datetime,
        tracking_status: PolicyTrackingStatus,
    ) -> StoredTrackedPolicy | None:
        tracked_policy = self.get_active_for_subject(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject_type,
            subject_id=subject_id,
        )
        if tracked_policy is None:
            return None
        count = len(self._storage.policy_snapshots.get(tracked_policy_id, []))
        updated = replace(
            tracked_policy,
            last_checked_at=last_checked_at,
            tracking_status=normalize_policy_tracking_status(tracking_status),
            snapshot_version_count=count,
        )
        self._storage.tracked_policies[tracked_policy_id] = updated
        return updated
