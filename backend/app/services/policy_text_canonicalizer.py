"""Deterministic cleanup and line synthesis for tracked-policy text comparison."""

from __future__ import annotations

from dataclasses import dataclass
from html import unescape
import re
from typing import Literal
import unicodedata


CURRENT_POLICY_TEXT_NORMALIZATION_VERSION = 2

_CONTROL_CHARACTER_PATTERN = re.compile(r"[\x00-\x08\x0b\x0c\x0e-\x1f\x7f]")
_MULTISPACE_PATTERN = re.compile(r"[ \t\f\v]+")
_MULTINEWLINE_PATTERN = re.compile(r"\n{3,}")
_FIELD_LABEL_BREAK_PATTERN = re.compile(
    r"\s+(?=(?:Name|First|Last|Email|Phone|Confirm Email|Confirm Phone|Quote Source|"
    r"Request a Callback|Get a Quote|Save your cart|Close|This field is hidden|"
    r"This field is for validation purposes)\b)",
    re.IGNORECASE,
)
_POLICY_TITLE_BREAK_PATTERN = re.compile(
    r"\s+(?=(?:\[\s*)?(?:terms of service|terms and conditions|privacy policy|effective date)\b)",
    re.IGNORECASE,
)
_SENTENCE_BREAK_PATTERN = re.compile(r'([.!?;:])\s+(?=(?:[A-Z(0-9"\u201c]))')
_NUMBERED_SECTION_PATTERN = re.compile(r"\s+(?=(?:(?:\d+\.\d+|\d+[.)])\s+[A-Z]))")
_LETTERED_SECTION_PATTERN = re.compile(r"\s+(?=(?:\([a-z]\)|[a-z]\))\s+[A-Z])", re.IGNORECASE)
_BULLET_PATTERN = re.compile(r"\s*([\u2022*-])\s*")
_PHONE_NUMBER_PATTERN = re.compile(r"(?:\(\d{3}\)|\b\d{3}[-.\s]\d{3}[-.\s]\d{4}\b)")
_HOURS_PATTERN = re.compile(
    r"(?i)\b(?:monday|tuesday|wednesday|thursday|friday|saturday|sunday)\b.*\b(?:am|pm)\b"
)
_STRONG_JUNK_PATTERN = re.compile(
    r"(?i)\b("
    r"skip to (?:main content|content|footer)|"
    r"save your cart|"
    r"request a callback|"
    r"get a quote|"
    r"quote source|"
    r"this field is hidden when viewing the form|"
    r"this field is for validation purposes|"
    r"confirm email|confirm phone|"
    r"no strings attached|"
    r"fill out the form below|"
    r"return your call|"
    r"free consultation|"
    r"continue your knowledge journey|"
    r"click here|"
    r"see full article|"
    r"contact us today to learn more|"
    r"contractors need a door supplier|"
    r"heading text\s*#?\d+|"
    r"delivering customized solutions that exceed your expectations|"
    r"close"
    r")\b"
)
_JUNK_HINT_PATTERN = re.compile(
    r"(?i)\b("
    r"menu|cart|callback|quote|shipping policy|return policy|"
    r"measurement forms|"
    r"gallery|customer care|"
    r"support|contact us|"
    r"all rights reserved|"
    r"factory hours|"
    r"fast nationwide shipping|free consultations|"
    r"return your call|return call|"
    r"fire safe rooms|"
    r"door unpacking and installation|"
    r"contractor|"
    r"employment|"
    r"privacy policy|"
    r"skip to|"
    r"newsletter|modal|popup|"
    r"required"
    r")\b"
)
_LEGAL_HINT_PATTERN = re.compile(
    r"(?i)\b("
    r"terms|privacy|effective date|eligibility|license|cookies|user comments|"
    r"user-generated content|intellectual property|third-party|disclaimer|"
    r"warranties|liability|indemnification|termination|governing law|"
    r"contact us|arbitration|cancellation|renewal|policy|rights|responsibility|"
    r"we reserve the right"
    r")\b"
)

_MOJIBAKE_REPLACEMENTS = {
    "\u00c3\u00a2\u20ac\u2122": "\u2019",
    "\u00c3\u00a2\u20ac\u0153": "\u201c",
    "\u00c3\u00a2\u20ac\u009d": "\u201d",
    "\u00c3\u00a2\u20ac\u02dc": "\u2018",
    "\u00c3\u00a2\u20ac\u201d": "\u2014",
    "\u00c3\u00a2\u20ac\u201c": "\u2013",
    "\u00c3\u00a2\u20ac\u00a2": "\u2022",
    "\u00c3\u00a2\u20ac\u00a6": "\u2026",
    "\u00c3\u201a\u00a9": "\u00a9",
    "\u00c3\u201a\u00ae": "\u00ae",
    "\u00c3\u201a ": " ",
}


@dataclass(frozen=True)
class CanonicalizedPolicyText:
    """Canonical comparison text plus internal diagnostics for future extensions."""

    comparison_text_body: str
    normalization_version: int
    cleanup_steps: tuple[str, ...]
    removed_line_count: int
    used_fallback: bool
    confidence: Literal["high", "low"]
    legacy_upgrade_applied: bool


class PolicyTextCanonicalizer:
    """Convert noisy extracted policy text into stable comparison text."""

    def canonicalize_text(
        self,
        text: str,
        *,
        legacy_upgrade_applied: bool = False,
    ) -> CanonicalizedPolicyText:
        normalized_text = self._normalize_text(text)
        candidate_lines = self._synthesize_candidate_lines(normalized_text)
        deduped_lines = self._dedupe_consecutive_lines(candidate_lines)
        filtered_lines, removed_line_count = self._suppress_boilerplate_lines(deduped_lines)

        cleanup_steps: list[str] = ["unicode_normalized", "comparison_lines_synthesized"]
        if deduped_lines != candidate_lines:
            cleanup_steps.append("duplicate_lines_removed")
        if removed_line_count:
            cleanup_steps.append("boilerplate_suppressed")

        if self._should_fallback(
            original_lines=deduped_lines,
            filtered_lines=filtered_lines,
            removed_line_count=removed_line_count,
        ):
            filtered_lines = self._fallback_lines(deduped_lines)
            cleanup_steps.append("fallback_preserved_content")
            used_fallback = True
            confidence: Literal["high", "low"] = "low"
        else:
            used_fallback = False
            confidence = "high"

        comparison_text_body = "\n".join(filtered_lines).strip()
        if not comparison_text_body:
            fallback_lines = self._fallback_lines(deduped_lines) or deduped_lines
            comparison_text_body = "\n".join(fallback_lines).strip()
            cleanup_steps.append("empty_output_fallback")
            used_fallback = True
            confidence = "low"

        return CanonicalizedPolicyText(
            comparison_text_body=comparison_text_body,
            normalization_version=CURRENT_POLICY_TEXT_NORMALIZATION_VERSION,
            cleanup_steps=tuple(cleanup_steps),
            removed_line_count=removed_line_count,
            used_fallback=used_fallback,
            confidence=confidence,
            legacy_upgrade_applied=legacy_upgrade_applied,
        )

    def _normalize_text(self, value: str) -> str:
        normalized = unicodedata.normalize("NFKC", value)
        normalized = unescape(normalized)
        for source, replacement in _MOJIBAKE_REPLACEMENTS.items():
            normalized = normalized.replace(source, replacement)
        normalized = normalized.replace("\r\n", "\n").replace("\r", "\n")
        normalized = _CONTROL_CHARACTER_PATTERN.sub(" ", normalized)
        normalized = _MULTISPACE_PATTERN.sub(" ", normalized)
        normalized = re.sub(r" *\n *", "\n", normalized)
        normalized = _MULTINEWLINE_PATTERN.sub("\n\n", normalized)
        return normalized.strip()

    def _synthesize_candidate_lines(self, text: str) -> list[str]:
        if not text:
            return []

        synthesized = text
        synthesized = _POLICY_TITLE_BREAK_PATTERN.sub("\n", synthesized)
        synthesized = _FIELD_LABEL_BREAK_PATTERN.sub("\n", synthesized)
        synthesized = _NUMBERED_SECTION_PATTERN.sub("\n", synthesized)
        synthesized = _LETTERED_SECTION_PATTERN.sub("\n", synthesized)
        synthesized = _SENTENCE_BREAK_PATTERN.sub(r"\1\n", synthesized)
        synthesized = _BULLET_PATTERN.sub(r"\n\1 ", synthesized)
        lines = [self._cleanup_line(line) for line in synthesized.split("\n")]
        return [line for line in lines if line]

    def _cleanup_line(self, value: str) -> str:
        cleaned = _MULTISPACE_PATTERN.sub(" ", value).strip(" \t-")
        cleaned = cleaned.replace("[", "").replace("]", "")
        return cleaned.strip()

    def _dedupe_consecutive_lines(self, lines: list[str]) -> list[str]:
        deduped_lines: list[str] = []
        previous_normalized: str | None = None
        for line in lines:
            normalized = re.sub(r"\W+", " ", line.lower()).strip()
            if normalized and normalized == previous_normalized:
                continue
            deduped_lines.append(line)
            previous_normalized = normalized or None
        return deduped_lines

    def _suppress_boilerplate_lines(self, lines: list[str]) -> tuple[list[str], int]:
        if not lines:
            return [], 0

        filtered_lines: list[str] = []
        removed_line_count = 0
        saw_legal_candidate = False
        first_legal_index = self._find_first_legal_index(lines)

        for index, line in enumerate(lines):
            if saw_legal_candidate and self._looks_like_policy_title(line) and len(line.split()) <= 4:
                removed_line_count += 1
                continue

            classification = self._classify_line(line)
            if first_legal_index is not None and index < first_legal_index:
                removed_line_count += 1
                continue
            if classification == "junk":
                removed_line_count += 1
                continue
            if classification == "legal_candidate":
                saw_legal_candidate = True
                filtered_lines.append(line)
                continue
            if saw_legal_candidate or self._looks_like_policy_title(line):
                filtered_lines.append(line)
                continue
            if index < 3:
                removed_line_count += 1
                continue
            filtered_lines.append(line)

        return filtered_lines, removed_line_count

    def _find_first_legal_index(self, lines: list[str]) -> int | None:
        for index, line in enumerate(lines):
            if self._classify_line(line) == "legal_candidate" or self._looks_like_policy_title(line):
                return index
        return None

    def _classify_line(self, line: str) -> Literal["junk", "legal_candidate", "neutral"]:
        lowered_line = line.lower()
        word_count = len(line.split())

        if _STRONG_JUNK_PATTERN.search(lowered_line):
            return "junk"
        if re.fullmatch(r"(?:name|first|last|email|phone|confirm|close|x)", lowered_line):
            return "junk"
        if line.startswith("\u00a9") or "all rights reserved" in lowered_line:
            return "junk"
        if _PHONE_NUMBER_PATTERN.search(line) and not self._looks_like_policy_title(line):
            return "junk"
        if _HOURS_PATTERN.search(line) and not self._looks_like_policy_title(line):
            return "junk"
        if lowered_line.startswith("monday") and ("am" in lowered_line or "pm" in lowered_line):
            return "junk"
        if len(_JUNK_HINT_PATTERN.findall(lowered_line)) >= 2 and not self._looks_like_policy_title(line):
            return "junk"

        if _LEGAL_HINT_PATTERN.search(lowered_line):
            return "legal_candidate"
        if re.match(r"^(?:\d+\.\d+|\d+[.)])\s+[A-Z]", line):
            return "legal_candidate"
        if re.match(r"^(?:\([a-z]\)|[a-z]\))\s", line, flags=re.IGNORECASE):
            return "legal_candidate"
        if word_count >= 12 and any(marker in line for marker in (".", ";", ":")):
            return "legal_candidate"
        if word_count <= 3 and _JUNK_HINT_PATTERN.search(lowered_line):
            return "junk"

        return "neutral"

    def _looks_like_policy_title(self, line: str) -> bool:
        lowered_line = line.lower()
        return bool(
            "terms of service" in lowered_line
            or "terms and conditions" in lowered_line
            or "privacy policy" in lowered_line
            or "effective date" in lowered_line
        )

    def _should_fallback(
        self,
        *,
        original_lines: list[str],
        filtered_lines: list[str],
        removed_line_count: int,
    ) -> bool:
        if not original_lines:
            return False
        if not filtered_lines:
            return True
        if removed_line_count < 3:
            return False
        original_word_count = sum(len(line.split()) for line in original_lines)
        filtered_word_count = sum(len(line.split()) for line in filtered_lines)
        if filtered_word_count < 25:
            return True
        return filtered_word_count < max(20, int(original_word_count * 0.2))

    def _fallback_lines(self, lines: list[str]) -> list[str]:
        return [line for line in lines if line and not _STRONG_JUNK_PATTERN.search(line.lower())]
