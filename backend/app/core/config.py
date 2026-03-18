"""Environment-backed settings for backend wiring.

Layer: infrastructure configuration.
Other layers read from `settings` so persistence/runtime switches are centralized.
"""

import os
from dataclasses import dataclass


@dataclass(frozen=True)
class Settings:
    """Typed access to backend environment variables."""

    app_env: str = os.getenv("APP_ENV", "development")
    persistence_backend: str = os.getenv("PERSISTENCE_BACKEND", "memory").lower()
    supabase_database_url: str = os.getenv("SUPABASE_DATABASE_URL", "")
    database_url: str = os.getenv("DATABASE_URL", "")
    postgres_auto_create_schema: bool = (
        os.getenv("POSTGRES_AUTO_CREATE_SCHEMA", "true").lower() == "true"
    )

    @property
    def effective_database_url(self) -> str:
        """Return the first configured Postgres connection string."""

        return self.supabase_database_url or self.database_url


settings = Settings()
