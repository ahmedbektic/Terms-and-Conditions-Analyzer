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
