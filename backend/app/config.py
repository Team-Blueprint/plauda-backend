from functools import lru_cache

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    """Runtime configuration, loaded from environment variables / .env."""

    model_config = SettingsConfigDict(
        env_file=".env",
        env_file_encoding="utf-8",
        extra="ignore",
    )

    # App
    app_name: str = "plauda"
    env: str = "dev"
    app_base_url: str = "http://localhost:8000"
    frontend_base_url: str = "http://localhost:5173"
    log_level: str = "INFO"

    # Database (Supabase Postgres)
    database_url: str = ""
    test_database_url: str = ""
    # asyncpg sslmode: verify-full (default), verify-ca, require, prefer, allow, disable.
    # Use "require" only when the local network intercepts TLS (self-signed chain).
    database_ssl_mode: str = "verify-full"

    # Supabase Storage (product images)
    supabase_url: str = ""
    supabase_service_key: str = ""
    supabase_storage_bucket: str = "product-images"

    # Auth
    jwt_secret: str = "change-me"
    jwt_algorithm: str = "HS256"
    jwt_expiry_minutes: int = 60 * 24

    # CORS
    cors_origins: list[str] = ["http://localhost:5173"]

    # Embeddings (Phase 1 — placeholders, not wired yet)
    embedding_provider: str = "ollama_local"
    cf_account_id: str = ""
    cf_api_token: str = ""
    gemini_api_key: str = ""
    ollama_base_url: str = "http://localhost:11434"

    # Agent LLM (Phase 2 — placeholders, not wired yet)
    groq_api_key: str = ""
    groq_agent_model: str = "llama-3.3-70b-versatile"
    groq_cheap_model: str = "llama-3.1-8b-instant"

    # PayPal (Phase 4 — placeholders, not wired yet)
    paypal_client_id: str = ""
    paypal_client_secret: str = ""
    paypal_env: str = "sandbox"
    credential_encryption_key: str = ""

    @property
    def database_url_async(self) -> str:
        """SQLAlchemy URL with the asyncpg driver, accepting plain postgres URLs."""
        url = self.database_url
        if url.startswith("postgresql+asyncpg://"):
            return url
        if url.startswith("postgresql://"):
            return "postgresql+asyncpg://" + url.removeprefix("postgresql://")
        if url.startswith("postgres://"):
            return "postgresql+asyncpg://" + url.removeprefix("postgres://")
        return url


@lru_cache
def get_settings() -> Settings:
    return Settings()
