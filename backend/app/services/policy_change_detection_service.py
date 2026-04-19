"""Change-detection logic for tracked-policy snapshot checks."""

from __future__ import annotations

from dataclasses import dataclass
import re

from ..repositories.models import StoredPolicySnapshot
from ..repositories.policy_change_status import PolicyChangeStatus
from ..repositories.policy_snapshot_hash import build_policy_snapshot_content_hash

_TRIVIAL_FORMATTING_PATTERN = re.compile(r"[^0-9a-z]+", re.IGNORECASE)
_SECTION_SPLIT_PATTERN = re.compile(r"(?:[.!?;:]\s+)")


@dataclass(frozen=True)
class PolicyChangeDetectionResult:
    """Structured result of comparing a captured policy body to the prior snapshot."""

    change_status: PolicyChangeStatus
    detection_method: str
    content_changed: bool | None
    previous_section_count: int | None
    new_section_count: int | None
    section_delta: int | None
    should_create_snapshot: bool


class PolicyChangeDetectionService:
    """Decide whether a new policy capture is meaningfully different."""

    def detect_change(
        self,
        *,
        previous_snapshot: StoredPolicySnapshot | None,
        normalized_text_body: str,
    ) -> PolicyChangeDetectionResult:
        if previous_snapshot is None:
            return PolicyChangeDetectionResult(
                change_status=PolicyChangeStatus.NOT_EVALUATED,
                detection_method="no_prior_snapshot",
                content_changed=None,
                previous_section_count=None,
                new_section_count=self._count_sections(normalized_text_body),
                section_delta=None,
                should_create_snapshot=True,
            )

        previous_text = previous_snapshot.normalized_text_body
        previous_section_count = self._count_sections(previous_text)
        new_section_count = self._count_sections(normalized_text_body)
        section_delta = new_section_count - previous_section_count
        current_hash = build_policy_snapshot_content_hash(normalized_text_body)

        if previous_snapshot.content_hash == current_hash:
            return PolicyChangeDetectionResult(
                change_status=PolicyChangeStatus.UNCHANGED,
                detection_method="exact_hash_match",
                content_changed=False,
                previous_section_count=previous_section_count,
                new_section_count=new_section_count,
                section_delta=section_delta,
                should_create_snapshot=False,
            )

        if previous_text == normalized_text_body:
            return PolicyChangeDetectionResult(
                change_status=PolicyChangeStatus.UNCHANGED,
                detection_method="normalized_text_match",
                content_changed=False,
                previous_section_count=previous_section_count,
                new_section_count=new_section_count,
                section_delta=section_delta,
                should_create_snapshot=False,
            )

        if self._normalize_trivial_formatting(previous_text) == self._normalize_trivial_formatting(
            normalized_text_body
        ):
            return PolicyChangeDetectionResult(
                change_status=PolicyChangeStatus.UNCHANGED,
                detection_method="trivial_formatting_suppressed",
                content_changed=False,
                previous_section_count=previous_section_count,
                new_section_count=new_section_count,
                section_delta=section_delta,
                should_create_snapshot=False,
            )

        return PolicyChangeDetectionResult(
            change_status=PolicyChangeStatus.UPDATED,
            detection_method="meaningful_text_change",
            content_changed=True,
            previous_section_count=previous_section_count,
            new_section_count=new_section_count,
            section_delta=section_delta,
            should_create_snapshot=True,
        )

    def _normalize_trivial_formatting(self, value: str) -> str:
        lowered = value.lower()
        return _TRIVIAL_FORMATTING_PATTERN.sub(" ", lowered).strip()

    def _count_sections(self, value: str) -> int:
        if not value.strip():
            return 0
        return len([item for item in _SECTION_SPLIT_PATTERN.split(value) if item.strip()])
