"""AI provider abstraction and deterministic MVP analyzer implementation.

The service layer calls this module through the `AnalysisProvider` protocol, so a real
LLM-backed provider can replace this implementation without API or repository changes.
"""

from dataclasses import dataclass
from datetime import datetime, timezone
import re
from typing import Protocol

from ..repositories.models import StoredFlaggedClause


@dataclass(frozen=True)
class AnalysisInput:
    """Normalized analysis input contract used by provider implementations."""

    source_type: str
    source_value: str
    normalized_text: str


@dataclass(frozen=True)
class ProviderAnalysisResult:
    """Structured analysis output returned to orchestration service."""

    summary: str
    trust_score: int
    model_name: str
    flagged_clauses: list[StoredFlaggedClause]
    completed_at: datetime


class AnalysisProvider(Protocol):
    """Behavior contract for swappable analysis implementations."""

    def analyze(self, *, analysis_input: AnalysisInput) -> ProviderAnalysisResult: ...


@dataclass(frozen=True)
class ClauseRule:
    """One deterministic detection rule for MVP keyword scanning."""

    clause_type: str
    severity: str
    keywords: tuple[str, ...]
    penalty: int
    explanation: str


class DeterministicAnalysisProvider:
    """Keyword-based analyzer used for MVP until LLM integration is added."""

    _RULES: tuple[ClauseRule, ...] = (
        ClauseRule(
            clause_type="auto_renewal",
            severity="high",
            keywords=("auto-renew", "automatic renewal", "renews automatically"),
            penalty=18,
            explanation="Automatic renewal can lead to unexpected charges if cancellation terms are strict.",
        ),
        ClauseRule(
            clause_type="forced_arbitration",
            severity="high",
            keywords=("arbitration", "waive class action", "class action waiver"),
            penalty=20,
            explanation="Mandatory arbitration can limit legal options and collective action rights.",
        ),
        ClauseRule(
            clause_type="broad_data_sharing",
            severity="medium",
            keywords=("share your data", "third parties", "affiliates", "advertising partners"),
            penalty=14,
            explanation="Broad third-party data sharing may reduce control over personal information.",
        ),
        ClauseRule(
            clause_type="liability_limitation",
            severity="medium",
            keywords=("not liable", "liability", "as is", "no warranties"),
            penalty=12,
            explanation="Liability limitations can cap compensation even when harm occurs.",
        ),
        ClauseRule(
            clause_type="unilateral_changes",
            severity="medium",
            keywords=("may change these terms", "at any time", "without notice"),
            penalty=10,
            explanation="Unilateral change clauses can alter obligations without clear user consent.",
        ),
    )

    def analyze(self, *, analysis_input: AnalysisInput) -> ProviderAnalysisResult:
        """Generate deterministic summary, flags, and score from normalized text."""

        normalized_text = analysis_input.normalized_text.strip()
        lowered_text = normalized_text.lower()

        flagged_clauses: list[StoredFlaggedClause] = []
        trust_score = 88

        for rule in self._RULES:
            if any(keyword in lowered_text for keyword in rule.keywords):
                trust_score -= rule.penalty
                flagged_clauses.append(
                    StoredFlaggedClause(
                        clause_type=rule.clause_type,
                        severity=rule.severity,
                        excerpt=self._extract_excerpt(normalized_text, rule.keywords),
                        explanation=rule.explanation,
                    )
                )

        # Clamp the score to avoid signaling false certainty at either extreme.
        trust_score = max(5, min(95, trust_score))
        summary = self._build_summary(
            source_type=analysis_input.source_type,
            source_value=analysis_input.source_value,
            text=normalized_text,
            flagged_clauses=flagged_clauses,
            trust_score=trust_score,
        )

        return ProviderAnalysisResult(
            summary=summary,
            trust_score=trust_score,
            model_name="deterministic-keyword-v1",
            flagged_clauses=flagged_clauses,
            completed_at=datetime.now(timezone.utc),
        )

    def _extract_excerpt(self, text: str, keywords: tuple[str, ...]) -> str:
        """Return a short snippet around the first matched keyword."""

        lowered = text.lower()
        for keyword in keywords:
            index = lowered.find(keyword)
            if index >= 0:
                start = max(0, index - 80)
                end = min(len(text), index + len(keyword) + 80)
                return " ".join(text[start:end].split())
        return " ".join(text[:160].split())

    def _build_summary(
        self,
        *,
        source_type: str,
        source_value: str,
        text: str,
        flagged_clauses: list[StoredFlaggedClause],
        trust_score: int,
    ) -> str:
        """Create a human-readable summary from provider findings."""

        word_count = len(re.findall(r"\b\w+\b", text))
        source_descriptor = (
            f"URL source ({source_value})" if source_type == "url" else "direct text submission"
        )

        if flagged_clauses:
            flagged_types = ", ".join(clause.clause_type for clause in flagged_clauses[:3])
            return (
                f"Analyzed {source_descriptor} with approximately {word_count} words. "
                f"Detected {len(flagged_clauses)} potentially risky clause categories, "
                f"including {flagged_types}. Overall trust score: {trust_score}/100."
            )

        return (
            f"Analyzed {source_descriptor} with approximately {word_count} words. "
            "No known high-risk keyword patterns were detected by the MVP analyzer. "
            f"Overall trust score: {trust_score}/100."
        )
