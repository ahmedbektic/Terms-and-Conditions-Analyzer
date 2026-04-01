"""Environment-backed settings for backend wiring.

Layer: infrastructure configuration.
Other layers read from `settings` so persistence/runtime switches are centralized.
"""

import os
from dataclasses import dataclass


def _env_bool(name: str, default: str) -> bool:
    value = os.getenv(name, default).strip().lower()
    return value == "true"


def _env_int(name: str, default: str) -> int:
    raw_value = os.getenv(name, default).strip()
    try:
        return int(raw_value)
    except ValueError as error:
        raise ValueError(f"Environment variable {name} must be an integer.") from error


def _env_float(name: str, default: str) -> float:
    raw_value = os.getenv(name, default).strip()
    try:
        return float(raw_value)
    except ValueError as error:
        raise ValueError(f"Environment variable {name} must be a number.") from error


@dataclass(frozen=True)
class Settings:
    """Typed access to backend environment variables."""

    app_env: str = os.getenv("APP_ENV", "development")
    persistence_backend: str = os.getenv("PERSISTENCE_BACKEND", "memory").lower()
    supabase_database_url: str = os.getenv("SUPABASE_DATABASE_URL", "")
    database_url: str = os.getenv("DATABASE_URL", "")
    postgres_auto_create_schema: bool = _env_bool("POSTGRES_AUTO_CREATE_SCHEMA", "true")
    # JWT signature verification should remain enabled in normal operation.
    auth_require_jwt_signature_verification: bool = _env_bool(
        "AUTH_REQUIRE_JWT_SIGNATURE_VERIFICATION", "true"
    )
    supabase_url: str = os.getenv("SUPABASE_URL", "")
    supabase_jwt_secret: str = os.getenv("SUPABASE_JWT_SECRET", "")
    supabase_jwt_issuer: str = os.getenv("SUPABASE_JWT_ISSUER", "")
    supabase_jwt_audience: str = os.getenv("SUPABASE_JWT_AUDIENCE", "authenticated")
    supabase_jwt_jwks_url: str = os.getenv("SUPABASE_JWT_JWKS_URL", "")
    supabase_jwks_cache_ttl_seconds: int = _env_int("SUPABASE_JWKS_CACHE_TTL_SECONDS", "300")
    supabase_jwks_http_timeout_seconds: float = _env_float(
        "SUPABASE_JWKS_HTTP_TIMEOUT_SECONDS", "5"
    )
    supabase_jwt_leeway_seconds: int = _env_int("SUPABASE_JWT_LEEWAY_SECONDS", "30")
    # Analysis provider runtime selection.
    # deterministic -> deterministic provider only (default safe mode)
    # ai -> selected AI provider path (with deterministic fallback if enabled)
    analysis_provider_mode: str = os.getenv("ANALYSIS_PROVIDER_MODE", "deterministic").lower()
    # Gemini is the intended default provider when AI mode is enabled.
    analysis_ai_provider_kind: str = os.getenv("ANALYSIS_AI_PROVIDER_KIND", "gemini").lower()
    # OpenAI-compatible provider settings. Legacy ANALYSIS_AI_* vars are accepted
    # as fallbacks to preserve existing local configuration behavior.
    analysis_openai_compatible_api_key: str = os.getenv(
        "ANALYSIS_OPENAI_COMPATIBLE_API_KEY",
        os.getenv("ANALYSIS_AI_API_KEY", ""),
    )
    analysis_openai_compatible_model: str = os.getenv(
        "ANALYSIS_OPENAI_COMPATIBLE_MODEL",
        os.getenv("ANALYSIS_AI_MODEL", ""),
    )
    analysis_openai_compatible_base_url: str = os.getenv(
        "ANALYSIS_OPENAI_COMPATIBLE_BASE_URL",
        os.getenv("ANALYSIS_AI_BASE_URL", "https://api.openai.com/v1"),
    )
    # Gemini native provider settings.
    analysis_gemini_api_key: str = os.getenv(
        "ANALYSIS_GEMINI_API_KEY",
        os.getenv("ANALYSIS_AI_API_KEY", ""),
    )
    analysis_gemini_model: str = os.getenv(
        "ANALYSIS_GEMINI_MODEL",
        os.getenv("ANALYSIS_AI_MODEL", "gemini-2.5-flash"),
    )
    analysis_gemini_base_url: str = os.getenv(
        "ANALYSIS_GEMINI_BASE_URL", "https://generativelanguage.googleapis.com/v1beta"
    )
    analysis_gemini_max_input_tokens: int = _env_int("ANALYSIS_GEMINI_MAX_INPUT_TOKENS", "250000")
    analysis_gemini_estimated_chars_per_token: int = _env_int(
        "ANALYSIS_GEMINI_ESTIMATED_CHARS_PER_TOKEN", "3"
    )
    analysis_ai_timeout_seconds: float = _env_float("ANALYSIS_AI_TIMEOUT_SECONDS", "20")
    analysis_ai_temperature: float = _env_float("ANALYSIS_AI_TEMPERATURE", "0.1")
    analysis_ai_fallback_to_deterministic: bool = _env_bool(
        "ANALYSIS_AI_FALLBACK_TO_DETERMINISTIC", "true"
    )
    # Internal execution seam: sync is active now, queued modes can be added later.
    analysis_execution_mode: str = os.getenv("ANALYSIS_EXECUTION_MODE", "sync").lower()
    # Transport-layer abuse protection defaults.
    api_rate_limit_requests_per_window: int = _env_int("API_RATE_LIMIT_REQUESTS_PER_WINDOW", "60")
    api_rate_limit_window_seconds: int = _env_int("API_RATE_LIMIT_WINDOW_SECONDS", "60")
    agreement_create_rate_limit_requests: int = _env_int(
        "AGREEMENT_CREATE_RATE_LIMIT_REQUESTS", "10"
    )
    agreement_create_rate_limit_window_seconds: int = _env_int(
        "AGREEMENT_CREATE_RATE_LIMIT_WINDOW_SECONDS", "600"
    )
    analysis_rate_limit_requests: int = _env_int("ANALYSIS_RATE_LIMIT_REQUESTS", "5")
    analysis_rate_limit_window_seconds: int = _env_int("ANALYSIS_RATE_LIMIT_WINDOW_SECONDS", "300")
    analysis_hourly_rate_limit_requests: int = _env_int("ANALYSIS_HOURLY_RATE_LIMIT_REQUESTS", "20")
    analysis_hourly_rate_limit_window_seconds: int = _env_int(
        "ANALYSIS_HOURLY_RATE_LIMIT_WINDOW_SECONDS", "3600"
    )
    cors_allowed_origins_csv: str = os.getenv(
        "CORS_ALLOWED_ORIGINS",
        "http://localhost:5173,http://127.0.0.1:5173",
    )

    @property
    def effective_database_url(self) -> str:
        """Return the first configured Postgres connection string."""

        return self.supabase_database_url or self.database_url

    @property
    def effective_supabase_jwt_issuer(self) -> str:
        """Resolve JWT issuer from explicit setting or SUPABASE_URL."""

        explicit = self.supabase_jwt_issuer.strip().rstrip("/")
        if explicit:
            return explicit

        supabase_base = self.supabase_url.strip().rstrip("/")
        if not supabase_base:
            return ""
        return f"{supabase_base}/auth/v1"

    @property
    def effective_supabase_jwks_url(self) -> str:
        """Resolve JWKS endpoint from explicit setting or derived issuer URL."""

        explicit = self.supabase_jwt_jwks_url.strip()
        if explicit:
            return explicit

        issuer = self.effective_supabase_jwt_issuer
        if not issuer:
            return ""
        return f"{issuer}/.well-known/jwks.json"

    @property
    def cors_allowed_origins(self) -> list[str]:
        """Parse CORS origins from a comma-separated env var."""

        return [
            origin.strip() for origin in self.cors_allowed_origins_csv.split(",") if origin.strip()
        ]


settings = Settings()
