"""Analysis provider seam with deterministic and AI-backed implementations.

Module responsibilities:
- define the provider interface and typed provider I/O contracts
- host provider selection/fallback wiring for runtime configuration
- isolate provider-specific invocation logic (OpenAI-compatible + Gemini)

Architectural boundary:
- Orchestration calls `AnalysisProvider` only.
- Route/repository layers stay provider-agnostic.
- New providers can be added by registering one builder in `_AI_PROVIDER_BUILDERS`.
"""

from dataclasses import dataclass, field, replace
from datetime import datetime, timezone
import json
import logging
import re
from typing import Callable, Mapping, Protocol

import httpx

from ..repositories.models import StoredFlaggedClause

__all__ = [
    "AnalysisInput",
    "AnalysisInputMetadata",
    "AnalysisProviderRuntimeConfig",
    "AnalysisProviderConfigurationError",
    "AnalysisProviderInvocationError",
    "AnalysisProvider",
    "DeterministicAnalysisProvider",
    "FallbackAnalysisProvider",
    "GeminiAnalysisProvider",
    "OpenAICompatibleAnalysisProvider",
    "ProviderAnalysisResult",
    "ProviderExecutionMetadata",
    "ProviderIdentity",
    "build_analysis_provider",
]

LOGGER = logging.getLogger(__name__)


@dataclass(frozen=True)
class AnalysisInputMetadata:
    """Input-side metadata providers can consume for richer behavior/traceability."""

    source_kind: str | None = None
    extraction_strategy: str | None = None
    extractor_name: str | None = None
    extraction_confidence: float | None = None
    extraction_warnings: tuple[str, ...] = ()
    extraction_errors: tuple[str, ...] = ()
    trace_id: str | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class AnalysisInput:
    """Normalized provider input contract."""

    source_type: str
    source_value: str
    normalized_text: str
    metadata: AnalysisInputMetadata = field(default_factory=AnalysisInputMetadata)


@dataclass(frozen=True)
class ProviderIdentity:
    """Provider/model identity metadata for downstream traceability."""

    provider_name: str
    model_name: str
    model_version: str | None = None


@dataclass(frozen=True)
class ProviderExecutionMetadata:
    """Execution metadata emitted by providers."""

    confidence: float | None = None
    warnings: tuple[str, ...] = ()
    trace_id: str | None = None
    attributes: Mapping[str, str] = field(default_factory=dict)


@dataclass(frozen=True)
class ProviderAnalysisResult:
    """Structured analysis output contract returned to orchestration."""

    summary: str
    trust_score: int
    flagged_clauses: list[StoredFlaggedClause]
    completed_at: datetime
    provider_identity: ProviderIdentity
    execution_metadata: ProviderExecutionMetadata = field(default_factory=ProviderExecutionMetadata)

    @property
    def model_name(self) -> str:
        """Compatibility accessor for persisted report schema."""

        return self.provider_identity.model_name


class AnalysisProvider(Protocol):
    """Behavior contract for swappable analysis implementations."""

    def analyze(self, *, analysis_input: AnalysisInput) -> ProviderAnalysisResult: ...


@dataclass(frozen=True)
class AnalysisProviderRuntimeConfig:
    """Runtime config for provider selection and provider-specific credentials.

    `mode`:
    - `deterministic`: deterministic provider only
    - `ai`: use selected AI provider kind, with optional deterministic fallback
    """

    mode: str = "deterministic"
    ai_provider_kind: str = "gemini"
    ai_timeout_seconds: float = 20.0
    ai_temperature: float = 0.1
    ai_fallback_to_deterministic: bool = True
    openai_compatible_api_key: str = ""
    openai_compatible_model_name: str = ""
    openai_compatible_base_url: str = "https://api.openai.com/v1"
    gemini_api_key: str = ""
    gemini_model_name: str = "gemini-2.0-flash"
    gemini_base_url: str = "https://generativelanguage.googleapis.com/v1beta"


class AnalysisProviderConfigurationError(Exception):
    """Raised when runtime config is insufficient for selected provider."""


class AnalysisProviderInvocationError(Exception):
    """Raised when a provider cannot complete invocation/parsing."""


@dataclass(frozen=True)
class _AIProviderInvocationResult:
    """Internal normalized output from provider-specific HTTP invocation."""

    model_name: str
    model_version: str | None
    trace_id: str | None
    response_content: str
    attributes: Mapping[str, str] = field(default_factory=dict)


class FallbackAnalysisProvider:
    """Wrapper that falls back to deterministic analysis on primary failures."""

    def __init__(self, *, primary: AnalysisProvider, fallback: AnalysisProvider) -> None:
        self._primary = primary
        self._fallback = fallback

    def analyze(self, *, analysis_input: AnalysisInput) -> ProviderAnalysisResult:
        try:
            return self._primary.analyze(analysis_input=analysis_input)
        except Exception as error:
            fallback_result = self._fallback.analyze(analysis_input=analysis_input)
            warning = (
                "Primary AI provider invocation failed; deterministic fallback was used "
                f"({error.__class__.__name__})."
            )
            return _append_execution_warning(fallback_result, warning)


class OpenAICompatibleAnalysisProvider:
    """Generic provider for OpenAI-compatible chat-completions APIs."""

    _SYSTEM_PROMPT = (
        "Analyze Terms and Conditions text and return strict JSON only. "
        "Schema: {"
        '"summary": string, '
        '"trust_score": integer 0..100, '
        '"flagged_clauses": [{"clause_type": string, "severity": "low|medium|high", '
        '"excerpt": string, "explanation": string}], '
        '"confidence": number 0..1 optional, '
        '"warnings": [string] optional'
        "}."
    )

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float,
        temperature: float,
        provider_name: str = "openai_compatible",
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature
        self._provider_name = provider_name

    def analyze(self, *, analysis_input: AnalysisInput) -> ProviderAnalysisResult:
        invocation = self._invoke_chat_completions(analysis_input=analysis_input)
        return _build_provider_analysis_result(
            analysis_input=analysis_input,
            provider_name=self._provider_name,
            invocation=invocation,
        )

    def _invoke_chat_completions(
        self, *, analysis_input: AnalysisInput
    ) -> _AIProviderInvocationResult:
        endpoint = f"{self._base_url}/chat/completions"
        user_payload = _build_provider_user_payload(analysis_input)

        try:
            response = httpx.post(
                endpoint,
                timeout=self._timeout_seconds,
                headers={
                    "Authorization": f"Bearer {self._api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self._model_name,
                    "temperature": self._temperature,
                    "response_format": {"type": "json_object"},
                    "messages": [
                        {"role": "system", "content": self._SYSTEM_PROMPT},
                        {
                            "role": "user",
                            "content": (
                                "Analyze this submission payload and return JSON only:\n"
                                f"{json.dumps(user_payload)}"
                            ),
                        },
                    ],
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise AnalysisProviderInvocationError(
                "OpenAI-compatible invocation failed " f"({error.__class__.__name__})."
            ) from error

        if not isinstance(payload, Mapping):
            raise AnalysisProviderInvocationError("OpenAI-compatible response was not an object.")

        choices = payload.get("choices")
        if not isinstance(choices, list) or not choices:
            raise AnalysisProviderInvocationError(
                "OpenAI-compatible response did not include choices."
            )

        first_choice = choices[0]
        if not isinstance(first_choice, Mapping):
            raise AnalysisProviderInvocationError("OpenAI-compatible choice payload was invalid.")

        message = first_choice.get("message")
        if not isinstance(message, Mapping):
            raise AnalysisProviderInvocationError("OpenAI-compatible message payload was missing.")

        content = _extract_text_from_provider_content(message.get("content"))
        if not content:
            raise AnalysisProviderInvocationError("OpenAI-compatible message content was empty.")

        finish_reason = first_choice.get("finish_reason")
        trace_id = response.headers.get("x-request-id")
        return _AIProviderInvocationResult(
            model_name=str(payload.get("model") or self._model_name),
            model_version=None,
            trace_id=trace_id,
            response_content=content,
            attributes={
                "analysis_mode": "openai_compatible_chat_completion_json",
                "finish_reason": str(finish_reason) if finish_reason is not None else "unknown",
            },
        )


class GeminiAnalysisProvider:
    """First-class Gemini provider using Gemini native `generateContent` API."""

    _SYSTEM_PROMPT = OpenAICompatibleAnalysisProvider._SYSTEM_PROMPT

    def __init__(
        self,
        *,
        api_key: str,
        model_name: str,
        base_url: str,
        timeout_seconds: float,
        temperature: float,
    ) -> None:
        self._api_key = api_key
        self._model_name = model_name
        self._base_url = base_url.rstrip("/")
        self._timeout_seconds = timeout_seconds
        self._temperature = temperature

    def analyze(self, *, analysis_input: AnalysisInput) -> ProviderAnalysisResult:
        invocation = self._invoke_generate_content(analysis_input=analysis_input)
        return _build_provider_analysis_result(
            analysis_input=analysis_input,
            provider_name="gemini",
            invocation=invocation,
        )

    def _invoke_generate_content(
        self, *, analysis_input: AnalysisInput
    ) -> _AIProviderInvocationResult:
        endpoint = f"{self._base_url}/models/{self._model_name}:generateContent?key={self._api_key}"
        user_payload = _build_provider_user_payload(analysis_input)

        try:
            response = httpx.post(
                endpoint,
                timeout=self._timeout_seconds,
                headers={"Content-Type": "application/json"},
                json={
                    "systemInstruction": {"parts": [{"text": self._SYSTEM_PROMPT}]},
                    "contents": [
                        {
                            "role": "user",
                            "parts": [
                                {
                                    "text": (
                                        "Analyze this submission payload and return JSON only:\n"
                                        f"{json.dumps(user_payload)}"
                                    )
                                }
                            ],
                        }
                    ],
                    "generationConfig": {
                        "temperature": self._temperature,
                        "responseMimeType": "application/json",
                    },
                },
            )
            response.raise_for_status()
            payload = response.json()
        except (httpx.HTTPError, ValueError) as error:
            raise AnalysisProviderInvocationError(
                f"Gemini invocation failed ({error.__class__.__name__})."
            ) from error

        if not isinstance(payload, Mapping):
            raise AnalysisProviderInvocationError("Gemini response was not an object.")

        candidates = payload.get("candidates")
        if not isinstance(candidates, list) or not candidates:
            raise AnalysisProviderInvocationError("Gemini response did not include candidates.")

        first_candidate = candidates[0]
        if not isinstance(first_candidate, Mapping):
            raise AnalysisProviderInvocationError("Gemini candidate payload was invalid.")

        content_mapping = first_candidate.get("content")
        if not isinstance(content_mapping, Mapping):
            raise AnalysisProviderInvocationError("Gemini candidate content payload was missing.")

        parts = content_mapping.get("parts")
        content = _extract_text_from_provider_content(parts)
        if not content:
            raise AnalysisProviderInvocationError("Gemini candidate content was empty.")

        finish_reason = first_candidate.get("finishReason")
        model_version = payload.get("modelVersion")
        trace_id = response.headers.get("x-goog-request-id") or response.headers.get("x-request-id")

        return _AIProviderInvocationResult(
            model_name=self._model_name,
            model_version=str(model_version) if model_version else None,
            trace_id=trace_id,
            response_content=content,
            attributes={
                "analysis_mode": "gemini_generate_content_json",
                "finish_reason": str(finish_reason) if finish_reason is not None else "unknown",
            },
        )


@dataclass(frozen=True)
class ClauseRule:
    """One deterministic detection rule for MVP keyword scanning."""

    clause_type: str
    severity: str
    keywords: tuple[str, ...]
    penalty: int
    explanation: str


class DeterministicAnalysisProvider:
    """Keyword-based analyzer used for MVP and runtime fallback safety."""

    _RULES: tuple[ClauseRule, ...] = (
        ClauseRule(
            clause_type="auto_renewal",
            severity="high",
            keywords=("auto-renew", "automatic renewal", "renews automatically"),
            penalty=18,
            explanation=(
                "Automatic renewal can lead to unexpected charges if cancellation terms are strict."
            ),
        ),
        ClauseRule(
            clause_type="forced_arbitration",
            severity="high",
            keywords=("arbitration", "waive class action", "class action waiver"),
            penalty=20,
            explanation=(
                "Mandatory arbitration can limit legal options and collective action rights."
            ),
        ),
        ClauseRule(
            clause_type="broad_data_sharing",
            severity="medium",
            keywords=("share your data", "third parties", "affiliates", "advertising partners"),
            penalty=14,
            explanation=(
                "Broad third-party data sharing may reduce control over personal information."
            ),
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
        execution_warnings = analysis_input.metadata.extraction_warnings
        if analysis_input.metadata.extraction_errors:
            execution_warnings = execution_warnings + (
                "Analysis ran with ingestion fallback/errors present.",
            )

        return ProviderAnalysisResult(
            summary=summary,
            trust_score=trust_score,
            flagged_clauses=flagged_clauses,
            completed_at=datetime.now(timezone.utc),
            provider_identity=ProviderIdentity(
                provider_name="deterministic_keyword_provider",
                model_name="deterministic-keyword-v1",
                model_version="1",
            ),
            execution_metadata=ProviderExecutionMetadata(
                confidence=0.6,
                warnings=execution_warnings,
                trace_id=None,
                attributes={
                    "analysis_mode": "deterministic_keyword_rules",
                    "source_kind": analysis_input.metadata.source_kind or "unknown",
                },
            ),
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


def build_analysis_provider(*, config: AnalysisProviderRuntimeConfig) -> AnalysisProvider:
    """Build provider from runtime config with deterministic-safe fallback behavior.

    Selection model:
    - `mode=deterministic` -> deterministic provider only.
    - `mode=ai` -> provider-kind lookup from `_AI_PROVIDER_BUILDERS`.
    - unknown mode / invalid provider config -> deterministic provider.
    """

    deterministic_provider = DeterministicAnalysisProvider()
    mode = config.mode.strip().lower()

    if mode in {"", "deterministic"}:
        return deterministic_provider

    if mode != "ai":
        LOGGER.warning(
            "Unknown ANALYSIS_PROVIDER_MODE '%s'; falling back to deterministic provider.",
            config.mode,
        )
        return deterministic_provider

    provider_kind = config.ai_provider_kind.strip().lower() or "gemini"
    ai_builder = _AI_PROVIDER_BUILDERS.get(provider_kind)
    if ai_builder is None:
        LOGGER.warning(
            "Unsupported ANALYSIS_AI_PROVIDER_KIND '%s'; falling back to deterministic provider.",
            config.ai_provider_kind,
        )
        return deterministic_provider

    try:
        ai_provider = ai_builder(config)
    except AnalysisProviderConfigurationError as error:
        LOGGER.warning("%s Falling back to deterministic provider.", error)
        return deterministic_provider

    if config.ai_fallback_to_deterministic:
        return FallbackAnalysisProvider(primary=ai_provider, fallback=deterministic_provider)
    return ai_provider


def _build_provider_user_payload(analysis_input: AnalysisInput) -> dict:
    """Shape the normalized provider request payload for AI model prompts."""

    return {
        "source_type": analysis_input.source_type,
        "source_value": analysis_input.source_value,
        "normalized_text": analysis_input.normalized_text,
        "metadata": {
            "source_kind": analysis_input.metadata.source_kind,
            "extraction_strategy": analysis_input.metadata.extraction_strategy,
            "extractor_name": analysis_input.metadata.extractor_name,
            "extraction_confidence": analysis_input.metadata.extraction_confidence,
            "warnings": list(analysis_input.metadata.extraction_warnings),
            "errors": list(analysis_input.metadata.extraction_errors),
        },
    }


def _extract_text_from_provider_content(content: object) -> str:
    """Extract text from provider content shapes (string or parts list)."""

    if isinstance(content, str):
        return content.strip()

    if not isinstance(content, list):
        return ""

    text_parts: list[str] = []
    for item in content:
        if isinstance(item, Mapping):
            text_value = item.get("text")
            if isinstance(text_value, str) and text_value.strip():
                text_parts.append(text_value.strip())
    return "\n".join(text_parts).strip()


def _build_provider_analysis_result(
    *,
    analysis_input: AnalysisInput,
    provider_name: str,
    invocation: _AIProviderInvocationResult,
) -> ProviderAnalysisResult:
    """Convert provider invocation output into the stable provider result contract."""

    parsed = _parse_json_response_content(invocation.response_content)
    provider_warnings = _coerce_warnings(parsed.get("warnings"))
    execution_warnings = analysis_input.metadata.extraction_warnings + provider_warnings
    if analysis_input.metadata.extraction_errors:
        execution_warnings = execution_warnings + (
            "Analysis input included extraction/ingestion errors.",
        )

    attributes = dict(invocation.attributes)
    attributes["source_kind"] = analysis_input.metadata.source_kind or "unknown"

    return ProviderAnalysisResult(
        summary=_coerce_summary(parsed.get("summary"), analysis_input=analysis_input),
        trust_score=_coerce_trust_score(parsed.get("trust_score")),
        flagged_clauses=_parse_flagged_clauses(
            parsed.get("flagged_clauses"), source_text=analysis_input.normalized_text
        ),
        completed_at=datetime.now(timezone.utc),
        provider_identity=ProviderIdentity(
            provider_name=provider_name,
            model_name=invocation.model_name,
            model_version=invocation.model_version,
        ),
        execution_metadata=ProviderExecutionMetadata(
            confidence=_coerce_optional_confidence(parsed.get("confidence")),
            warnings=execution_warnings,
            trace_id=invocation.trace_id,
            attributes=attributes,
        ),
    )


def _parse_json_response_content(raw_content: str) -> dict:
    """Parse a JSON object from provider response text."""

    content = raw_content.strip()
    if content.startswith("```"):
        content = re.sub(r"^```(?:json)?\s*", "", content)
        content = re.sub(r"\s*```$", "", content)

    try:
        parsed = json.loads(content)
    except json.JSONDecodeError:
        object_match = re.search(r"\{.*\}", content, flags=re.DOTALL)
        if object_match is None:
            raise AnalysisProviderInvocationError("AI provider response was not valid JSON.")
        try:
            parsed = json.loads(object_match.group(0))
        except json.JSONDecodeError as error:
            raise AnalysisProviderInvocationError(
                "AI provider response JSON could not be parsed."
            ) from error

    if not isinstance(parsed, dict):
        raise AnalysisProviderInvocationError("AI provider response JSON must be an object.")
    return parsed


def _parse_flagged_clauses(raw_value: object, *, source_text: str) -> list[StoredFlaggedClause]:
    if not isinstance(raw_value, list):
        return []

    clauses: list[StoredFlaggedClause] = []
    for item in raw_value:
        if not isinstance(item, Mapping):
            continue

        clause_type = str(item.get("clause_type") or "unspecified_clause")
        severity = str(item.get("severity") or "medium").lower()
        if severity not in {"low", "medium", "high"}:
            severity = "medium"

        excerpt = str(item.get("excerpt") or "").strip()
        if not excerpt:
            excerpt = " ".join(source_text.split()[:160])

        explanation = str(item.get("explanation") or "").strip()
        if not explanation:
            explanation = "Potentially risky clause identified by AI provider."

        clauses.append(
            StoredFlaggedClause(
                clause_type=clause_type,
                severity=severity,
                excerpt=excerpt,
                explanation=explanation,
            )
        )
    return clauses


def _coerce_summary(raw_value: object, *, analysis_input: AnalysisInput) -> str:
    if isinstance(raw_value, str) and raw_value.strip():
        return raw_value.strip()

    source_descriptor = (
        f"URL source ({analysis_input.source_value})"
        if analysis_input.source_type == "url"
        else "direct text submission"
    )
    word_count = len(re.findall(r"\b\w+\b", analysis_input.normalized_text))
    return f"AI analysis completed for {source_descriptor} with approximately {word_count} words."


def _coerce_trust_score(raw_value: object) -> int:
    if isinstance(raw_value, (int, float)):
        return max(0, min(100, int(raw_value)))
    return 50


def _coerce_optional_confidence(raw_value: object) -> float | None:
    if isinstance(raw_value, (int, float)):
        confidence = float(raw_value)
        return max(0.0, min(1.0, confidence))
    return None


def _coerce_warnings(raw_value: object) -> tuple[str, ...]:
    if not isinstance(raw_value, list):
        return ()
    warnings: list[str] = []
    for warning in raw_value:
        if isinstance(warning, str) and warning.strip():
            warnings.append(warning.strip())
    return tuple(warnings)


def _append_execution_warning(
    result: ProviderAnalysisResult, warning: str
) -> ProviderAnalysisResult:
    """Return result copy with one additional execution warning."""

    updated_metadata = replace(
        result.execution_metadata,
        warnings=result.execution_metadata.warnings + (warning,),
    )
    return replace(result, execution_metadata=updated_metadata)


def _build_openai_compatible_provider(
    config: AnalysisProviderRuntimeConfig,
) -> AnalysisProvider:
    api_key = config.openai_compatible_api_key.strip()
    model_name = config.openai_compatible_model_name.strip()
    if not api_key or not model_name:
        raise AnalysisProviderConfigurationError(
            "OpenAI-compatible provider selected but credentials/model are missing."
        )
    return OpenAICompatibleAnalysisProvider(
        api_key=api_key,
        model_name=model_name,
        base_url=config.openai_compatible_base_url,
        timeout_seconds=config.ai_timeout_seconds,
        temperature=config.ai_temperature,
    )


def _build_gemini_provider(config: AnalysisProviderRuntimeConfig) -> AnalysisProvider:
    api_key = config.gemini_api_key.strip()
    model_name = config.gemini_model_name.strip()
    if not api_key or not model_name:
        raise AnalysisProviderConfigurationError(
            "Gemini provider selected but ANALYSIS_GEMINI_API_KEY or ANALYSIS_GEMINI_MODEL is missing."
        )
    return GeminiAnalysisProvider(
        api_key=api_key,
        model_name=model_name,
        base_url=config.gemini_base_url,
        timeout_seconds=config.ai_timeout_seconds,
        temperature=config.ai_temperature,
    )


_AI_PROVIDER_BUILDERS: dict[str, Callable[[AnalysisProviderRuntimeConfig], AnalysisProvider]] = {
    "gemini": _build_gemini_provider,
    "openai_compatible": _build_openai_compatible_provider,
}
