"""Read-only tracked-policy history and compare workflow."""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from difflib import SequenceMatcher
from uuid import UUID

from ..repositories.interfaces import (
    PolicyChangeEventRepository,
    PolicySnapshotRepository,
    TrackedPolicyRepository,
)
from ..repositories.models import StoredPolicySnapshot, StoredTrackedPolicy
from ..repositories.policy_change_status import PolicyChangeStatus
from .policy_text_canonicalizer import (
    CURRENT_POLICY_TEXT_NORMALIZATION_VERSION,
    CanonicalizedPolicyText,
    PolicyTextCanonicalizer,
)
from .request_subject import RequestSubject


class TrackedPolicyVersionNotFoundError(Exception):
    """Raised when a tracked policy is not available for the active owner."""


class TrackedPolicySnapshotNotFoundError(Exception):
    """Raised when one or more requested snapshots are not available for the policy."""


class TrackedPolicyVersionComparisonError(Exception):
    """Raised when a comparison request is invalid."""


@dataclass(frozen=True)
class TrackedPolicySnapshotVersion:
    """One stored snapshot as exposed to history/compare clients."""

    snapshot_id: UUID
    version_number: int
    captured_at: datetime
    source_url: str | None
    final_url: str | None
    capture_status: str
    change_status: str | None


@dataclass(frozen=True)
class TrackedPolicyComparisonBlock:
    """One structured diff block derived from normalized snapshot text."""

    change_type: str
    older_text: str | None
    newer_text: str | None


@dataclass(frozen=True)
class TrackedPolicyComparisonResult:
    """Owner-scoped comparison result for two stored versions of one policy."""

    tracked_policy: StoredTrackedPolicy
    older_snapshot: TrackedPolicySnapshotVersion
    newer_snapshot: TrackedPolicySnapshotVersion
    diff_blocks: list[TrackedPolicyComparisonBlock]
    comparison_outcome: str
    normalization_notice: str | None


@dataclass(frozen=True)
class _PreparedSnapshotComparisonText:
    snapshot: StoredPolicySnapshot
    comparison_text: str
    diagnostics: CanonicalizedPolicyText


class TrackedPolicyVersionsService:
    """Expose owner-scoped tracked-policy version history and comparisons."""

    def __init__(
        self,
        *,
        tracked_policy_repository: TrackedPolicyRepository,
        policy_snapshot_repository: PolicySnapshotRepository,
        policy_change_event_repository: PolicyChangeEventRepository | None = None,
        policy_text_canonicalizer: PolicyTextCanonicalizer | None = None,
    ) -> None:
        self._tracked_policy_repository = tracked_policy_repository
        self._policy_snapshot_repository = policy_snapshot_repository
        self._policy_change_event_repository = policy_change_event_repository
        self._policy_text_canonicalizer = (
            policy_text_canonicalizer or PolicyTextCanonicalizer()
        )

    def list_snapshot_history(
        self, *, subject: RequestSubject, tracked_policy_id: UUID
    ) -> tuple[StoredTrackedPolicy, list[TrackedPolicySnapshotVersion]]:
        tracked_policy = self._get_tracked_policy(
            subject=subject,
            tracked_policy_id=tracked_policy_id,
        )
        snapshots = self._policy_snapshot_repository.list_for_tracked_policy(
            tracked_policy_id=tracked_policy_id
        )
        return tracked_policy, self._build_snapshot_versions(
            tracked_policy=tracked_policy,
            snapshots=snapshots,
        )

    def compare_snapshots(
        self,
        *,
        subject: RequestSubject,
        tracked_policy_id: UUID,
        snapshot_a_id: UUID,
        snapshot_b_id: UUID,
    ) -> TrackedPolicyComparisonResult:
        if snapshot_a_id == snapshot_b_id:
            raise TrackedPolicyVersionComparisonError(
                "Choose two different stored versions to compare."
            )

        tracked_policy, snapshot_versions = self.list_snapshot_history(
            subject=subject,
            tracked_policy_id=tracked_policy_id,
        )
        snapshots = self._policy_snapshot_repository.list_for_tracked_policy(
            tracked_policy_id=tracked_policy_id
        )
        snapshots_by_id = {snapshot.id: snapshot for snapshot in snapshots}
        versions_by_id = {
            snapshot_version.snapshot_id: snapshot_version
            for snapshot_version in snapshot_versions
        }

        try:
            snapshot_a = snapshots_by_id[snapshot_a_id]
            snapshot_b = snapshots_by_id[snapshot_b_id]
        except KeyError as error:
            raise TrackedPolicySnapshotNotFoundError(
                "One or both selected stored versions were not found for this policy."
            ) from error

        older_snapshot_record, newer_snapshot_record = self._order_snapshots(
            first_snapshot=snapshot_a,
            second_snapshot=snapshot_b,
        )
        older_snapshot = versions_by_id[older_snapshot_record.id]
        newer_snapshot = versions_by_id[newer_snapshot_record.id]
        prepared_older = self._prepare_snapshot_for_compare(older_snapshot_record)
        prepared_newer = self._prepare_snapshot_for_compare(newer_snapshot_record)
        comparison_outcome = self._determine_comparison_outcome(
            older_text=prepared_older.comparison_text,
            newer_text=prepared_newer.comparison_text,
        )

        return TrackedPolicyComparisonResult(
            tracked_policy=tracked_policy,
            older_snapshot=older_snapshot,
            newer_snapshot=newer_snapshot,
            diff_blocks=(
                []
                if comparison_outcome == "no_meaningful_changes"
                else self._build_diff_blocks(
                    older_text=prepared_older.comparison_text,
                    newer_text=prepared_newer.comparison_text,
                )
            ),
            comparison_outcome=comparison_outcome,
            normalization_notice=self._build_normalization_notice(
                older=prepared_older.diagnostics,
                newer=prepared_newer.diagnostics,
                comparison_outcome=comparison_outcome,
            ),
        )

    def _get_tracked_policy(
        self, *, subject: RequestSubject, tracked_policy_id: UUID
    ) -> StoredTrackedPolicy:
        tracked_policy = self._tracked_policy_repository.get_active_for_subject(
            tracked_policy_id=tracked_policy_id,
            subject_type=subject.subject_type,
            subject_id=subject.subject_id,
        )
        if tracked_policy is None:
            raise TrackedPolicyVersionNotFoundError(
                f"Tracked policy {tracked_policy_id} was not found."
            )
        return tracked_policy

    def _build_snapshot_versions(
        self,
        *,
        tracked_policy: StoredTrackedPolicy,
        snapshots: list[StoredPolicySnapshot],
    ) -> list[TrackedPolicySnapshotVersion]:
        total_snapshots = len(snapshots)
        change_status_by_snapshot_id: dict[UUID, str] = {}
        if self._policy_change_event_repository is not None:
            for event in self._policy_change_event_repository.list_for_tracked_policy(
                tracked_policy_id=tracked_policy.id
            ):
                if event.new_snapshot_id is None:
                    continue
                change_status_by_snapshot_id[event.new_snapshot_id] = event.change_status.value

        snapshot_versions: list[TrackedPolicySnapshotVersion] = []
        for index, snapshot in enumerate(snapshots):
            version_number = total_snapshots - index
            change_status = change_status_by_snapshot_id.get(snapshot.id)
            if (
                change_status is None
                and total_snapshots == 1
                and tracked_policy.latest_change_status == PolicyChangeStatus.NOT_EVALUATED
            ):
                change_status = tracked_policy.latest_change_status.value
            snapshot_versions.append(
                TrackedPolicySnapshotVersion(
                    snapshot_id=snapshot.id,
                    version_number=version_number,
                    captured_at=snapshot.captured_at,
                    source_url=snapshot.source_url,
                    final_url=snapshot.final_url,
                    capture_status=snapshot.capture_status.value,
                    change_status=change_status,
                )
            )
        return snapshot_versions

    def _prepare_snapshot_for_compare(
        self, snapshot: StoredPolicySnapshot
    ) -> _PreparedSnapshotComparisonText:
        if snapshot.normalization_version == CURRENT_POLICY_TEXT_NORMALIZATION_VERSION:
            diagnostics = CanonicalizedPolicyText(
                comparison_text_body=snapshot.normalized_text_body,
                normalization_version=snapshot.normalization_version,
                cleanup_steps=(),
                removed_line_count=0,
                used_fallback=False,
                confidence="high",
                legacy_upgrade_applied=False,
            )
            return _PreparedSnapshotComparisonText(
                snapshot=snapshot,
                comparison_text=snapshot.normalized_text_body,
                diagnostics=diagnostics,
            )

        source_text = snapshot.raw_text_body or snapshot.normalized_text_body
        diagnostics = self._policy_text_canonicalizer.canonicalize_text(
            source_text,
            legacy_upgrade_applied=True,
        )
        return _PreparedSnapshotComparisonText(
            snapshot=snapshot,
            comparison_text=diagnostics.comparison_text_body,
            diagnostics=diagnostics,
        )

    def _order_snapshots(
        self,
        *,
        first_snapshot: StoredPolicySnapshot,
        second_snapshot: StoredPolicySnapshot,
    ) -> tuple[StoredPolicySnapshot, StoredPolicySnapshot]:
        if first_snapshot.captured_at < second_snapshot.captured_at:
            return first_snapshot, second_snapshot
        if first_snapshot.captured_at > second_snapshot.captured_at:
            return second_snapshot, first_snapshot
        if first_snapshot.id.hex < second_snapshot.id.hex:
            return first_snapshot, second_snapshot
        return second_snapshot, first_snapshot

    def _determine_comparison_outcome(self, *, older_text: str, newer_text: str) -> str:
        if older_text == newer_text:
            return "no_meaningful_changes"
        return "meaningful_changes"

    def _build_diff_blocks(
        self, *, older_text: str, newer_text: str
    ) -> list[TrackedPolicyComparisonBlock]:
        older_segments = self._segment_text(older_text)
        newer_segments = self._segment_text(newer_text)
        matcher = SequenceMatcher(a=older_segments, b=newer_segments, autojunk=False)
        diff_blocks: list[TrackedPolicyComparisonBlock] = []

        for tag, older_start, older_end, newer_start, newer_end in matcher.get_opcodes():
            older_block = self._join_segments(older_segments[older_start:older_end])
            newer_block = self._join_segments(newer_segments[newer_start:newer_end])

            if tag == "equal":
                diff_blocks.append(
                    TrackedPolicyComparisonBlock(
                        change_type="unchanged",
                        older_text=older_block,
                        newer_text=newer_block,
                    )
                )
                continue

            if tag in {"delete", "replace"} and older_block is not None:
                diff_blocks.append(
                    TrackedPolicyComparisonBlock(
                        change_type="removed",
                        older_text=older_block,
                        newer_text=None,
                    )
                )
            if tag in {"insert", "replace"} and newer_block is not None:
                diff_blocks.append(
                    TrackedPolicyComparisonBlock(
                        change_type="added",
                        older_text=None,
                        newer_text=newer_block,
                    )
                )

        return diff_blocks

    def _segment_text(self, text: str) -> list[str]:
        return [line.strip() for line in text.splitlines() if line.strip()]

    def _join_segments(self, segments: list[str]) -> str | None:
        if not segments:
            return None
        return "\n".join(segments)

    def _build_normalization_notice(
        self,
        *,
        older: CanonicalizedPolicyText,
        newer: CanonicalizedPolicyText,
        comparison_outcome: str,
    ) -> str | None:
        legacy_upgrade_applied = older.legacy_upgrade_applied or newer.legacy_upgrade_applied
        suppressed_noise = older.removed_line_count > 0 or newer.removed_line_count > 0
        used_fallback = older.used_fallback or newer.used_fallback

        if comparison_outcome == "no_meaningful_changes" and (
            legacy_upgrade_applied or suppressed_noise
        ):
            return (
                "Stored versions were normalized before comparison so scraper and page-chrome noise did not appear as a policy change."
            )
        if legacy_upgrade_applied:
            return (
                "One or both stored versions were upgraded with the latest normalization rules before comparison."
            )
        if used_fallback:
            return (
                "Comparison used a conservative fallback cleanup path to avoid over-stripping policy text."
            )
        return None
