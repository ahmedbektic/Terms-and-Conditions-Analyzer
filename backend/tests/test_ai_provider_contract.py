import httpx
import pytest

from app.services.ai_provider import (
    AnalysisInput,
    AnalysisInputMetadata,
    AnalysisProviderInvocationError,
    AnalysisProviderRuntimeConfig,
    DeterministicAnalysisProvider,
    FallbackAnalysisProvider,
    GeminiAnalysisProvider,
    OpenAICompatibleAnalysisProvider,
    build_analysis_provider,
)


def test_deterministic_provider_returns_identity_and_compat_model_name() -> None:
    provider = DeterministicAnalysisProvider()
    result = provider.analyze(
        analysis_input=AnalysisInput(
            source_type="text",
            source_value="manual_text_submission",
            normalized_text=("These terms include arbitration and automatic renewal language."),
        )
    )

    assert result.provider_identity.provider_name == "deterministic_keyword_provider"
    assert result.provider_identity.model_name == "deterministic-keyword-v1"
    assert result.model_name == "deterministic-keyword-v1"


def test_deterministic_provider_propagates_ingestion_warnings() -> None:
    provider = DeterministicAnalysisProvider()
    result = provider.analyze(
        analysis_input=AnalysisInput(
            source_type="url",
            source_value="https://example.com/terms",
            normalized_text=("These terms include arbitration and class action waiver language."),
            metadata=AnalysisInputMetadata(
                source_kind="url",
                extraction_warnings=("URL fetch failed; fallback used.",),
                extraction_errors=("fetch timeout",),
            ),
        )
    )

    assert result.execution_metadata.warnings != ()
    assert "fallback" in " ".join(result.execution_metadata.warnings).lower()


def test_provider_builder_defaults_to_deterministic_mode() -> None:
    provider = build_analysis_provider(config=AnalysisProviderRuntimeConfig())

    assert isinstance(provider, DeterministicAnalysisProvider)


def test_provider_builder_falls_back_when_gemini_config_missing() -> None:
    provider = build_analysis_provider(
        config=AnalysisProviderRuntimeConfig(
            mode="ai",
            ai_provider_kind="gemini",
            gemini_api_key="",
            gemini_model_name="gemini-2.0-flash",
        )
    )

    assert isinstance(provider, DeterministicAnalysisProvider)


def test_provider_builder_returns_gemini_provider_when_configured() -> None:
    provider = build_analysis_provider(
        config=AnalysisProviderRuntimeConfig(
            mode="ai",
            ai_provider_kind="gemini",
            gemini_api_key="test-key",
            gemini_model_name="gemini-2.0-flash",
            ai_fallback_to_deterministic=False,
        )
    )

    assert isinstance(provider, GeminiAnalysisProvider)


def test_provider_builder_prefers_gemini_by_default_in_ai_mode() -> None:
    provider = build_analysis_provider(
        config=AnalysisProviderRuntimeConfig(
            mode="ai",
            gemini_api_key="test-key",
            gemini_model_name="gemini-2.0-flash",
            ai_fallback_to_deterministic=False,
        )
    )

    assert isinstance(provider, GeminiAnalysisProvider)


def test_provider_builder_returns_openai_compatible_provider_when_configured() -> None:
    provider = build_analysis_provider(
        config=AnalysisProviderRuntimeConfig(
            mode="ai",
            ai_provider_kind="openai_compatible",
            openai_compatible_api_key="test-key",
            openai_compatible_model_name="test-model",
            ai_fallback_to_deterministic=False,
        )
    )

    assert isinstance(provider, OpenAICompatibleAnalysisProvider)


def test_provider_builder_wraps_provider_with_fallback_when_enabled() -> None:
    provider = build_analysis_provider(
        config=AnalysisProviderRuntimeConfig(
            mode="ai",
            ai_provider_kind="gemini",
            gemini_api_key="test-key",
            gemini_model_name="gemini-2.0-flash",
            ai_fallback_to_deterministic=True,
        )
    )

    assert isinstance(provider, FallbackAnalysisProvider)


def test_provider_builder_falls_back_for_unknown_provider_kind() -> None:
    provider = build_analysis_provider(
        config=AnalysisProviderRuntimeConfig(
            mode="ai",
            ai_provider_kind="not_supported",
        )
    )

    assert isinstance(provider, DeterministicAnalysisProvider)


def test_fallback_provider_uses_deterministic_when_primary_fails() -> None:
    class _FailingProvider:
        def analyze(self, *, analysis_input: AnalysisInput):
            raise RuntimeError("simulated provider failure")

    provider = FallbackAnalysisProvider(
        primary=_FailingProvider(),
        fallback=DeterministicAnalysisProvider(),
    )
    result = provider.analyze(
        analysis_input=AnalysisInput(
            source_type="text",
            source_value="manual_text_submission",
            normalized_text="These terms include automatic renewal and arbitration.",
        )
    )

    assert result.provider_identity.provider_name == "deterministic_keyword_provider"
    assert any("fallback" in warning.lower() for warning in result.execution_metadata.warnings)


def test_provider_builder_fallback_handles_runtime_ai_invocation_failure(
    monkeypatch,
) -> None:
    def _raise_connect_error(*_args, **_kwargs):
        raise httpx.ConnectError("network failure")

    monkeypatch.setattr("app.services.ai_provider.httpx.post", _raise_connect_error)

    provider = build_analysis_provider(
        config=AnalysisProviderRuntimeConfig(
            mode="ai",
            ai_provider_kind="gemini",
            gemini_api_key="test-key",
            gemini_model_name="gemini-2.0-flash",
            ai_fallback_to_deterministic=True,
        )
    )
    result = provider.analyze(
        analysis_input=AnalysisInput(
            source_type="text",
            source_value="manual_text_submission",
            normalized_text="These terms include automatic renewal and arbitration.",
        )
    )

    assert result.provider_identity.provider_name == "deterministic_keyword_provider"
    assert any("fallback" in warning.lower() for warning in result.execution_metadata.warnings)


def test_provider_builder_without_fallback_raises_on_runtime_ai_failure(
    monkeypatch,
) -> None:
    def _raise_connect_error(*_args, **_kwargs):
        raise httpx.ConnectError("network failure")

    monkeypatch.setattr("app.services.ai_provider.httpx.post", _raise_connect_error)

    provider = build_analysis_provider(
        config=AnalysisProviderRuntimeConfig(
            mode="ai",
            ai_provider_kind="gemini",
            gemini_api_key="test-key",
            gemini_model_name="gemini-2.0-flash",
            ai_fallback_to_deterministic=False,
        )
    )

    with pytest.raises(AnalysisProviderInvocationError):
        provider.analyze(
            analysis_input=AnalysisInput(
                source_type="text",
                source_value="manual_text_submission",
                normalized_text="These terms include automatic renewal and arbitration.",
            )
        )
