from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    app_name: str = "crm-backend"
    api_prefix: str = "/api"
    # database_url: str = "postgresql+psycopg://crm:crm@localhost:5432/crm"
    database_url: str = "postgresql+psycopg://crm:crm@db:5432/crm"

    # Attachment storage. Paths are resolved relative to the backend working
    # directory; the tree is created lazily on first write.
    attachments_dir: str = "./var/attachments"
    max_upload_bytes: int = 10 * 1024 * 1024

    portal_session_ttl_days: int = 14

    # AI integration (Story 08). Every AI capability across the arc must
    # degrade to StubAIProvider when ai_enabled is False or no key is
    # configured -- see app/services/ai/provider.py:get_ai_provider(). Never
    # make Anthropic reachability a hard dependency for tests or local dev.
    anthropic_api_key: str | None = None
    ai_model: str = "claude-opus-5"
    ai_enabled: bool = False

    model_config = SettingsConfigDict(env_file=".env", env_prefix="CRM_", extra="ignore")


settings = Settings()
