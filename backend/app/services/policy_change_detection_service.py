"""Change-detection logic for tracked-policy snapshot checks."""

from __future__ import annotations

from dataclasses import dataclass
import re

from ..repositories.models import StoredPolicySnapshot
from ..repositories.policy_change_status import PolicyChangeStatus
from ..repositories.policy_snapshot_hash import build_policy_snapshot_content_hash
from .policy_text_canonicalizer import (
    CURRENT_POLICY_TEXT_NORMALIZATION_VERSION,
    PolicyTextCanonicalizer,
)

_TRIVIAL_FORMATTING_PATTERN = re.compile(r"[^0-9a-z]+", re.IGNORECASE)
_SECTION_SPLIT_PATTERN = re.compile(r"(?:\n+|[.!?;:]\s+)")


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

    def __init__(self, *, policy_text_canonicalizer: PolicyTextCanonicalizer | None = None) -> None:
        self._policy_text_canonicalizer = policy_text_canonicalizer or PolicyTextCanonicalizer()

    def detect_change(
        self,
        *,
        previous_snapshot: StoredPolicySnapshot | None,
        raw_text_body: str | None,
        normalized_text_body: str,
        normalization_version: int | None = None,
    ) -> PolicyChangeDetectionResult:
        current_text = self._canonicalize_current_text(
            raw_text_body=raw_text_body,
            normalized_text_body=normalized_text_body,
            normalization_version=normalization_version,
        )

        if previous_snapshot is None:
            return PolicyChangeDetectionResult(
                change_status=PolicyChangeStatus.NOT_EVALUATED,
                detection_method="no_prior_snapshot",
                content_changed=None,
                previous_section_count=None,
                new_section_count=self._count_sections(current_text),
                section_delta=None,
                should_create_snapshot=True,
            )

        previous_text = self._canonicalize_previous_snapshot(previous_snapshot)
        previous_section_count = self._count_sections(previous_text)
        new_section_count = self._count_sections(current_text)
        section_delta = new_section_count - previous_section_count
        current_hash = build_policy_snapshot_content_hash(current_text)

        if (
            previous_snapshot.normalization_version == CURRENT_POLICY_TEXT_NORMALIZATION_VERSION
            and previous_snapshot.content_hash == current_hash
        ):
            return PolicyChangeDetectionResult(
                change_status=PolicyChangeStatus.UNCHANGED,
                detection_method="exact_hash_match",
                content_changed=False,
                previous_section_count=previous_section_count,
                new_section_count=new_section_count,
                section_delta=section_delta,
                should_create_snapshot=False,
            )

        if previous_text == current_text:
            return PolicyChangeDetectionResult(
                change_status=PolicyChangeStatus.UNCHANGED,
                detection_method=self._text_match_method(previous_snapshot),
                content_changed=False,
                previous_section_count=previous_section_count,
                new_section_count=new_section_count,
                section_delta=section_delta,
                should_create_snapshot=False,
            )

        if self._normalize_trivial_formatting(previous_text) == self._normalize_trivial_formatting(
            current_text
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

    def _canonicalize_current_text(
        self,
        *,
        raw_text_body: str | None,
        normalized_text_body: str,
        normalization_version: int | None,
    ) -> str:
        if normalization_version == CURRENT_POLICY_TEXT_NORMALIZATION_VERSION:
            return normalized_text_body
        source_text = raw_text_body or normalized_text_body
        return self._policy_text_canonicalizer.canonicalize_text(
            source_text,
            legacy_upgrade_applied=True,
        ).comparison_text_body

    def _canonicalize_previous_snapshot(self, snapshot: StoredPolicySnapshot) -> str:
        if snapshot.normalization_version == CURRENT_POLICY_TEXT_NORMALIZATION_VERSION:
            return snapshot.normalized_text_body
        source_text = snapshot.raw_text_body or snapshot.normalized_text_body
        return self._policy_text_canonicalizer.canonicalize_text(
            source_text,
            legacy_upgrade_applied=True,
        ).comparison_text_body

    def _text_match_method(self, snapshot: StoredPolicySnapshot) -> str:
        if snapshot.normalization_version == CURRENT_POLICY_TEXT_NORMALIZATION_VERSION:
            return "normalized_text_match"
        return "canonicalized_text_match"

    def _normalize_trivial_formatting(self, value: str) -> str:
        lowered = value.lower()
        return _TRIVIAL_FORMATTING_PATTERN.sub(" ", lowered).strip()

    def _count_sections(self, value: str) -> int:
        if not value.strip():
            return 0
        return len([item for item in _SECTION_SPLIT_PATTERN.split(value) if item.strip()])
